/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 FlekDeck bridge to its configured ZSign identity for ROM payloads.
*/

#import "FlekROMSigning.h"
#import "../../Utilities/LCUtils.h"
#import "../../../LiveContainer/LCSharedUtils.h"
#import <dispatch/dispatch.h>
#import <Security/Security.h>
#import "../../../ZSign/zsigner.h"
#import <objc/runtime.h>
#import <objc/message.h>
#import <mach/mach.h>
#import <fcntl.h>
#import <limits.h>
#import <stdio.h>
#import <stdlib.h>
#import <unistd.h>
#import <dlfcn.h>

// The pinned Vibe signer is loaded dynamically; ROMs use the same native
// ZSigner, but must validate arguments before its asynchronous C++ worker.
// A missing p12 or password otherwise becomes std::string(nullptr) and
// crashes the whole host while the recovery console is still visible.
@interface LCUtils (FlekROMZSignLoading)
+ (void)loadStoreFrameworksWithError2:(NSError * _Nullable * _Nullable)error;
@end

static NSError *FlekROMSigningError(NSInteger code, NSString *description)
{
    return [NSError errorWithDomain:@"com.fs.flekdeck.bootloader.signing"
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

// Nyxian's ROM initializer owns FrontBoard process registration. The
// upstream ROM calls FBProcessManager registerProcessForAuditToken: after
// resolving the LiveProcess extension's RunningBoard handle. Never replace
// that API with an invented constructor or fail a preflight based on the
// availability of unrelated private selectors. In particular, successful
// upstream Nyxian ROM boot on the same iOS 27 device disproves the previous
// "unsupported OS" diagnosis.
static void FlekROMTrace(const char *event)
{
    const char *home = getenv("HOME");
    if (!home || !event) return;
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/Documents/BootLogs/current-boot.log", home) >= sizeof(path)) return;
    int fd = open(path, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0) return;
    char line[180];
    int n = snprintf(line, sizeof(line), "pid=%d %s\n", getpid(), event);
    if (n > 0 && n < sizeof(line)) {
        (void)write(fd, line, (size_t)n);
        (void)fsync(fd);
    }
    close(fd);
}

static void FlekROMTraceRegisteredExtension(NSString *identifier)
{
    // Mirror Nyxian PEExtension's discovery path, read-only. Do not invoke
    // PEExtensionHasGetTaskAllowed here: its dispatch_once caches failure and
    // early preflights can poison the ROM's own boot attempt.
    Class extensionClass = NSClassFromString(@"NSExtension");
    SEL factory = NSSelectorFromString(@"extensionWithIdentifier:error:");
    if (!extensionClass || ![extensionClass respondsToSelector:factory]) {
        FlekROMTrace("rom-registration-nsextension-unavailable");
        return;
    }
    NSError *registrationError = nil;
    id extension = ((id (*)(id, SEL, id, NSError **))objc_msgSend)(
        extensionClass, factory, identifier, &registrationError);
    if (!extension || registrationError) {
        FlekROMTrace("rom-registration-extension-lookup-failed");
        return;
    }
    FlekROMTrace("rom-registration-extension-resolved");
    SEL plugIn = NSSelectorFromString(@"_plugIn");
    if (![extension respondsToSelector:plugIn]) {
        FlekROMTrace("rom-registration-plugin-selector-unavailable");
        return;
    }
    id plugin = ((id (*)(id, SEL))objc_msgSend)(extension, plugIn);
    SEL entitlementsSelector = NSSelectorFromString(@"entitlements");
    if (!plugin || ![plugin respondsToSelector:entitlementsSelector]) {
        FlekROMTrace("rom-registration-plugin-entitlements-unavailable");
        return;
    }
    id entitlements = ((id (*)(id, SEL))objc_msgSend)(plugin, entitlementsSelector);
    if (![entitlements isKindOfClass:NSDictionary.class]) {
        FlekROMTrace("rom-registration-entitlements-not-a-dictionary");
        return;
    }
    NSNumber *getTaskAllow = entitlements[@"get-task-allow"];
    BOOL allowed = [getTaskAllow isKindOfClass:NSNumber.class] && getTaskAllow.boolValue;
    FlekROMTrace(allowed ? "rom-registration-get-task-allow-ok" :
                           "rom-registration-get-task-allow-denied");
}

void FlekDeckTraceROMProcessEnvironment(void)
{
    // Diagnostic-only preflight. Nyxian performs registration inside the ROM
    // itself; FlekDeck must not gate it or install Objective-C method hooks.
    NSString *extensionPath = [NSBundle.mainBundle.builtInPlugInsPath
        stringByAppendingPathComponent:@"LiveProcess.appex"];
    NSString *infoPath = [extensionPath stringByAppendingPathComponent:@"Info.plist"];
    NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:infoPath];
    NSString *executable = info[@"CFBundleExecutable"];
    NSString *executablePath = [extensionPath stringByAppendingPathComponent:
        [executable isKindOfClass:NSString.class] ? executable : @"LiveProcess"];
    NSString *extensionIdentifier = info[@"CFBundleIdentifier"];
    FlekROMTrace(info ? "rom-liveprocess-info-present" : "rom-liveprocess-info-missing");
    FlekROMTrace([NSFileManager.defaultManager isReadableFileAtPath:executablePath] ?
        "rom-liveprocess-executable-present" : "rom-liveprocess-executable-missing");
    FlekROMTrace([extensionIdentifier isKindOfClass:NSString.class] && extensionIdentifier.length ?
        "rom-liveprocess-bundle-identifier-present" : "rom-liveprocess-bundle-identifier-missing");
    if ([extensionIdentifier isKindOfClass:NSString.class] && extensionIdentifier.length) {
        FlekROMTraceRegisteredExtension(extensionIdentifier);
    } else {
        FlekROMTrace("rom-registration-cannot-check-missing-bundle-identifier");
    }
    // Nyxian still owns the actual RBS audit-token and FBProcess registration.
    // Never replace it with a guessed private selector on newer iOS releases.
    FlekROMTrace("rom-frontboard-native-nyxian-registration-unmodified");
}

static NSData *FlekROMCertificateFromBuiltinSideStore(void)
{
    // Same keychain entry and lookup already used by the existing Settings
    // "Import from SideStore" flow. Do not log, persist, or expose its bytes.
    NSDictionary *query = @{
        (__bridge NSString *)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge NSString *)kSecAttrAccount: @"signingCertificate",
        (__bridge NSString *)kSecAttrService: @"com.kdt.livecontainer",
        (__bridge NSString *)kSecReturnData: @YES,
        (__bridge NSString *)kSecMatchLimit: (__bridge id)kSecMatchLimitOne,
        (__bridge NSString *)kSecAttrSynchronizable: (__bridge id)kSecAttrSynchronizableAny,
    };
    CFTypeRef item = NULL;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &item);
    if (status != errSecSuccess || item == NULL) {
        if (item) CFRelease(item);
        return nil;
    }
    id value = CFBridgingRelease(item);
    return [value isKindOfClass:NSData.class] && [value length] > 0 ? value : nil;
}

BOOL FlekDeckSignROMFilesWithZSign(NSArray<NSURL *> *files, NSError **error)
{
    if (files.count == 0) return YES;

    NSData *certificate = LCUtils.certificateData;
    NSString *password = LCSharedUtils.certificatePassword;
    if (![certificate isKindOfClass:NSData.class] || certificate.length == 0) {
        id fallback = [NSUserDefaults.standardUserDefaults objectForKey:@"LCCertificateData"];
        certificate = [fallback isKindOfClass:NSData.class] ? fallback : nil;
    }
    if (![certificate isKindOfClass:NSData.class] || certificate.length == 0) {
        certificate = FlekROMCertificateFromBuiltinSideStore();
        if (certificate.length > 0) password = @"";
    }
    if (![certificate isKindOfClass:NSData.class] || certificate.length == 0) {
        if (error) *error = FlekROMSigningError(2,
            @"No ROM signing certificate is available. In FlekDeck Settings > Signing, import your SideStore/ESign .p12 or use Import from SideStore, then flash the ZIP again.");
        return NO;
    }

    // An empty p12 password is valid. Nil is NOT a valid C-string and must
    // never reach ZSignAsset's implicit std::string constructor.
    if (![password isKindOfClass:NSString.class]) password = @"";
    NSString *bundleID = NSBundle.mainBundle.bundleIdentifier;
    if (![bundleID isKindOfClass:NSString.class] || bundleID.length == 0) {
        bundleID = NSBundle.mainBundle.infoDictionary[@"CFBundleIdentifier"];
    }
    if (![bundleID isKindOfClass:NSString.class] || bundleID.length == 0) {
        bundleID = @"com.fs.flekdeck";
    }

    NSMutableArray<NSString *> *paths = [NSMutableArray arrayWithCapacity:files.count];
    for (id entry in files) {
        if (![entry isKindOfClass:NSURL.class] || ![entry isFileURL] ||
            ![entry path].length ||
            ![NSFileManager.defaultManager isReadableFileAtPath:[entry path]]) {
            if (error) *error = FlekROMSigningError(3, @"A ROM executable is missing or unreadable.");
            return NO;
        }
        [paths addObject:[entry path]];
    }

    // ZSign.dylib is bundled with FlekDeck. Load it from the host bundle
    // explicitly: the UI's lazy LCUtils loader can return without registering
    // ZSigner when a dynamically re-signed app changes its executable layout.
    // Do not depend on the separate SideStore signing service at ROM flash time.
    NSString *frameworks = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Frameworks"];
    NSString *opensslPath = [frameworks stringByAppendingPathComponent:@"OpenSSL.framework/OpenSSL"];
    NSString *zsignPath = [frameworks stringByAppendingPathComponent:@"ZSign.dylib"];
    if (![NSFileManager.defaultManager isReadableFileAtPath:zsignPath]) {
        FlekROMTrace("rom-zsign-missing-in-installed-bundle");
        if (error) *error = FlekROMSigningError(4, @"The installed FlekDeck app is missing Frameworks/ZSign.dylib. Reinstall with extensions and frameworks preserved.");
        return NO;
    }
    // ZSign's LC_LOAD_DYLIB references @rpath/OpenSSL.framework/OpenSSL.
    // Resolve its dependency first; keep both images mapped for async signing.
    if (![NSFileManager.defaultManager isReadableFileAtPath:opensslPath]) {
        FlekROMTrace("rom-zsign-openssl-missing");
        if (error) *error = FlekROMSigningError(5, @"The installed FlekDeck app is missing OpenSSL.framework.");
        return NO;
    }
    void *opensslHandle = dlopen(opensslPath.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
    if (!opensslHandle) {
        const char *why = dlerror();
        FlekROMTrace("rom-zsign-openssl-dlopen-failed");
        if (error) *error = FlekROMSigningError(6,
            [NSString stringWithFormat:@"Could not load OpenSSL: %s", why ?: "unknown loader error"]);
        return NO;
    }
    void *zsignHandle = dlopen(zsignPath.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
    if (!zsignHandle) {
        const char *why = dlerror();
        FlekROMTrace("rom-zsign-dlopen-failed");
        if (error) *error = FlekROMSigningError(7,
            [NSString stringWithFormat:@"Could not load ZSign.dylib: %s", why ?: "unknown loader error"]);
        return NO;
    }
    Class signer = NSClassFromString(@"ZSigner");
    SEL action = @selector(signMachOPathArr:bundleId:cert:pass:completionHandler:);
    if (signer == Nil || ![signer respondsToSelector:action]) {
        FlekROMTrace(signer == Nil ? "rom-zsign-class-unavailable" : "rom-zsign-selector-unavailable");
        if (error) *error = FlekROMSigningError(8, @"ZSign was loaded, but the required ZSigner class or method was not registered.");
        return NO;
    }
    FlekROMTrace("rom-zsign-ready");

    dispatch_semaphore_t completed = dispatch_semaphore_create(0);
    __block BOOL succeeded = NO;
    __block NSError *signingError = nil;
    NSProgress *progress = [signer signMachOPathArr:paths
                                         bundleId:bundleID
                                             cert:certificate
                                             pass:password
                                completionHandler:^(BOOL success, NSError * _Nullable callbackError) {
        succeeded = success && callbackError == nil;
        signingError = callbackError;
        dispatch_semaphore_signal(completed);
    }];
    if (progress == nil) {
        if (error) *error = FlekROMSigningError(5, @"Could not start the native ROM signer.");
        return NO;
    }
    dispatch_semaphore_wait(completed, DISPATCH_TIME_FOREVER);
    if (!succeeded && error) {
        *error = signingError ?: FlekROMSigningError(1, @"The selected certificate could not sign the ROM executables.");
    }
    return succeeded;
}

NSURL * _Nullable FlekDeckBootSharedRootURL(void)
{
    NSURL *appGroupURL = [LCSharedUtils appGroupPath];
    if(appGroupURL == nil)
    {
        return nil;
    }
    return [appGroupURL URLByAppendingPathComponent:@"FlekDeck/Boot" isDirectory:YES];
}


#pragma mark - Integrated Procursus workspace bridge

// Use Nyxian's own LDEApplicationWorkspace runtime object loaded by ROM init.
// DO NOT create a second process manager, parse a fake app list, launch Mach-O
// in the host, or bypass the ROM's entitlement/process-registration checks.
static id FlekDeckProcursusWorkspace(void)
{
    Class workspaceClass = NSClassFromString(@"LDEApplicationWorkspace");
    SEL shared = @selector(shared);
    if (!workspaceClass || ![workspaceClass respondsToSelector:shared]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(workspaceClass, shared);
}

NSArray<NSDictionary<NSString *, id> *> *FlekDeckListProcursusApps(void)
{
    id workspace = FlekDeckProcursusWorkspace();
    SEL query = NSSelectorFromString(@"allApplicationObjects");
    if (!workspace || ![workspace respondsToSelector:query]) {
        FlekROMTrace("procursus-app-registry-not-ready");
        return @[];
    }
    NSArray *objects = ((id (*)(id, SEL))objc_msgSend)(workspace, query);
    if (![objects isKindOfClass:NSArray.class]) return @[];
    NSMutableArray<NSDictionary<NSString *, id> *> *result = [NSMutableArray array];
    for (id app in objects) {
        SEL identifierSel = NSSelectorFromString(@"bundleIdentifier");
        SEL titleSel = NSSelectorFromString(@"localizedName");
        SEL iconSel = NSSelectorFromString(@"icon");
        if (![app respondsToSelector:identifierSel]) continue;
        id identifier = ((id (*)(id, SEL))objc_msgSend)(app, identifierSel);
        if (![identifier isKindOfClass:NSString.class] || ![identifier length]) continue;
        // The ROM's own SpringBoard is a system process, not a tappable app.
        if ([identifier isEqualToString:@"com.apple.springboard"]) continue;
        id title = [app respondsToSelector:titleSel] ?
            ((id (*)(id, SEL))objc_msgSend)(app, titleSel) : nil;
        id icon = [app respondsToSelector:iconSel] ?
            ((id (*)(id, SEL))objc_msgSend)(app, iconSel) : nil;
        NSMutableDictionary *entry = [@{
            @"bundleID": identifier,
            @"title": ([title isKindOfClass:NSString.class] && [title length])
                     ? title : identifier
        } mutableCopy];
        if ([icon isKindOfClass:NSClassFromString(@"UIImage")]) {
            entry[@"icon"] = icon;
        }
        [result addObject:entry];
    }
    [result sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [a[@"title"] localizedCaseInsensitiveCompare:b[@"title"]];
    }];
    FlekROMTrace("procursus-app-registry-enumerated");
    return result;
}

BOOL FlekDeckLaunchProcursusApp(NSString *bundleID)
{
    if (![bundleID isKindOfClass:NSString.class] || !bundleID.length) return NO;
    id workspace = FlekDeckProcursusWorkspace();
    SEL present = NSSelectorFromString(@"openApplicationWithBundleID:");
    if (!workspace || ![workspace respondsToSelector:present]) {
        FlekROMTrace("procursus-app-launch-workspace-unavailable");
        return NO;
    }
    // Confirm the target is actually present before asking bootstrapd to
    // launch it. Never show a pre-populated/fake installed application.
    BOOL exists = NO;
    for (NSDictionary *entry in FlekDeckListProcursusApps()) {
        if ([entry[@"bundleID"] isEqual:bundleID]) { exists = YES; break; }
    }
    if (!exists) {
        FlekROMTrace("procursus-app-launch-target-not-installed");
        return NO;
    }
    BOOL launched = ((BOOL (*)(id, SEL, id))objc_msgSend)(workspace, present, bundleID);
    FlekROMTrace(launched ? "procursus-app-launch-accepted" : "procursus-app-launch-rejected");
    return launched;
}
