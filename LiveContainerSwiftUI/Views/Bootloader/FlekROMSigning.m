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

// iOS 27 FrontBoard process bootstrap reports XPC send-right corruption while
// registering Nyxian's LiveProcess using registerProcessForAuditToken:.
// Leave Nyxian ROM code unchanged: reuse any registered FBProcess for this PID,
// otherwise hand FrontBoard its already verified RBSProcessHandle instead of
// asking it to reconstruct and bootstrap one from a raw audit token.
// Scope this compatibility adapter to FlekDeck ROM boot on iOS 27+ only.
BOOL FlekDeckPrepareROMFrontBoardRegistration(NSError **error)
{
    if (NSProcessInfo.processInfo.operatingSystemVersion.majorVersion < 27) return YES;
    static BOOL installed = NO;
    static dispatch_once_t once;
    static NSError *setupError = nil;
    dispatch_once(&once, ^{
        Class manager = NSClassFromString(@"FBProcessManager");
        Class predicate = NSClassFromString(@"RBSProcessPredicate");
        Class handleClass = NSClassFromString(@"RBSProcessHandle");
        SEL auditSelector = NSSelectorFromString(@"registerProcessForAuditToken:");
        SEL existingSelector = NSSelectorFromString(@"processForPID:");
        SEL handleSelector = NSSelectorFromString(@"registerProcessForHandle:");
        SEL predicateSelector = NSSelectorFromString(@"predicateMatchingIdentifier:");
        SEL lookupSelector = NSSelectorFromString(@"handleForPredicate:error:");
        Method auditMethod = manager ? class_getInstanceMethod(manager, auditSelector) : NULL;
        if (!auditMethod || !class_getInstanceMethod(manager, existingSelector) ||
            !class_getInstanceMethod(manager, handleSelector) ||
            ![predicate respondsToSelector:predicateSelector] ||
            ![handleClass respondsToSelector:lookupSelector]) {
            setupError = FlekROMSigningError(20, @"The iOS 27 ROM process-registration APIs are not available.");
            return;
        }
        id (^adapter)(id, audit_token_t) = ^id(id target, audit_token_t token) {
            pid_t pid = (pid_t)token.val[5];
            if (pid <= 0) return nil;
            id existing = ((id (*)(id, SEL, pid_t))objc_msgSend)(target, existingSelector, pid);
            if (existing != nil) {
                SEL runningSelector = NSSelectorFromString(@"isRunning");
                if (![existing respondsToSelector:runningSelector] ||
                    ((BOOL (*)(id, SEL))objc_msgSend)(existing, runningSelector)) {
                    return existing;
                }
            }
            // A process must never be repeatedly registered while a private
            // framework's registerForHandle implementation is in flight.
            static __thread BOOL inRegistration = NO;
            if (inRegistration) return nil;
            inRegistration = YES;
            id result = nil;
            @try {
                id rbsPredicate = ((id (*)(id, SEL, id))objc_msgSend)(
                    predicate, predicateSelector, @(pid));
                NSError *lookupError = nil;
                id rbsHandle = rbsPredicate ?
                    ((id (*)(id, SEL, id, NSError **))objc_msgSend)(
                        handleClass, lookupSelector, rbsPredicate, &lookupError) : nil;
                if (rbsHandle && !lookupError) {
                    result = ((id (*)(id, SEL, id))objc_msgSend)(
                        target, handleSelector, rbsHandle);
                }
            } @finally {
                inRegistration = NO;
            }
            return result;
        };
        IMP replacement = imp_implementationWithBlock(adapter);
        if (!replacement) {
            setupError = FlekROMSigningError(21, @"Could not install the iOS 27 ROM registration adapter.");
            return;
        }
        method_setImplementation(auditMethod, replacement);
        installed = YES;
    });
    if (!installed && error) *error = setupError ?: FlekROMSigningError(22, @"ROM process registration is unavailable.");
    return installed;
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

    NSError *loadError = nil;
    [LCUtils loadStoreFrameworksWithError2:&loadError];
    if (loadError) {
        if (error) *error = loadError;
        return NO;
    }
    Class signer = NSClassFromString(@"ZSigner");
    SEL action = @selector(signMachOPathArr:bundleId:cert:pass:completionHandler:);
    if (signer == Nil || ![signer respondsToSelector:action]) {
        if (error) *error = FlekROMSigningError(4, @"The native ZSign service is unavailable in this installation.");
        return NO;
    }

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
