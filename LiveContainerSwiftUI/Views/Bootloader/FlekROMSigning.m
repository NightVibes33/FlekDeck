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
