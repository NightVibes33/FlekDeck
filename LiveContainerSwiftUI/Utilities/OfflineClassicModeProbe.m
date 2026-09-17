#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <mach-o/loader.h>
#import <mach-o/utils.h>
#import <mach-o/dyld.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import "LCUtils.h"

static void LCFlekClassicProbeBypass(void (^block)(void)) {
    if (block) block();
}

static BOOL LCSetScalarIvar(id object, const char *name, const void *value, size_t size) {
    if (!object || !name || !value) return NO;
    Ivar ivar = class_getInstanceVariable(object_getClass(object), name);
    if (!ivar) return NO;
    ptrdiff_t offset = ivar_getOffset(ivar);
    memcpy((uint8_t *)(__bridge void *)object + offset, value, size);
    return YES;
}

@interface LCStaticDiskUsage : NSObject
@end
@implementation LCStaticDiskUsage
- (NSNumber *)staticUsage { return @0; }
@end

@interface LCFakeApplicationRecord : NSObject
@end
@implementation LCFakeApplicationRecord
- (unsigned)codeSignatureVersion { return 0; }
- (BOOL)wasBuiltWithThreadSanitizer { return NO; }
@end

@interface LCFakeApplicationIdentity : NSObject
@end
@implementation LCFakeApplicationIdentity
- (instancetype)copy { return self; }
@end

@interface LCFakeProcessIdentity : NSObject <NSCopying>
@end
@implementation LCFakeProcessIdentity
- (id)copyWithZone:(NSZone *)zone { (void)zone; return self; }
@end

@interface LCFakeApplicationProxy : NSObject
- (instancetype)initWithBundle:(NSBundle *)bundle
                  executableURL:(NSURL *)executableURL
                     sdkVersion:(NSString *)sdkVersion
                   entitlements:(NSDictionary *)entitlements;
@property(nonatomic, readonly) NSBundle *bundle;
@property(nonatomic, readonly) NSURL *executableURL;
@property(nonatomic, readonly) NSString *linkedSDKVersion;
@property(nonatomic, readonly) NSDictionary *codeEntitlements;
@end

@interface _LSApplicationState : NSObject
@end
@interface LSBundleInfoCachedValues : NSObject
- (instancetype)_initWithKeys:(NSSet *)keys forDictionary:(NSDictionary *)dict;
@end
@interface SBApplicationInfo : NSObject
- (instancetype)_initWithApplicationProxy:(id)proxy overrideURL:(NSURL *)overrideURL;
- (instancetype)_initWithApplicationProxy:(id)proxy
                                    record:(id)record
                               appIdentity:(id)identity
                           processIdentity:(id)identity2
                               overrideURL:(NSURL *)overrideURL;
@end
@interface SBApplication : NSObject
- (instancetype)initWithApplicationInfo:(SBApplicationInfo *)info;
- (NSInteger)_defaultClassicMode;
@end

@implementation LCFakeApplicationProxy {
    _LSApplicationState *_state;
    LCStaticDiskUsage *_diskUsage;
    NSUUID *_cacheGUID;
}

- (instancetype)initWithBundle:(NSBundle *)bundle
                  executableURL:(NSURL *)executableURL
                     sdkVersion:(NSString *)sdkVersion
                   entitlements:(NSDictionary *)entitlements {
    self = [super init];
    if (self) {
        _bundle = bundle;
        _executableURL = executableURL;
        _linkedSDKVersion = [sdkVersion copy] ?: @"0.0.0";
        _codeEntitlements = [entitlements copy] ?: @{};
        Class stateClass = PrivClass(_LSApplicationState);
        if (stateClass) {
            _LSApplicationState *state = [stateClass alloc];
            uint64_t stateFlags = 0x14;
            LCSetScalarIvar(state, "_stateFlags", &stateFlags, sizeof(stateFlags));
            _state = state;
        }
        _diskUsage = [LCStaticDiskUsage new];
        _cacheGUID = [NSUUID UUID];
    }
    return self;
}

- (NSString *)bundleIdentifier { return self.bundle.bundleIdentifier; }
- (NSURL *)bundleURL { return self.bundle.bundleURL; }
- (NSString *)bundleVersion { return [self.bundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"0"; }
- (NSString *)bundleType { return @"Application"; }
- (NSString *)localizedName {
    return [self.bundle objectForInfoDictionaryKey:@"CFBundleDisplayName"]
        ?: [self.bundle objectForInfoDictionaryKey:@"CFBundleName"]
        ?: self.bundleIdentifier;
}
- (NSString *)localizedShortName { return [self localizedName]; }
- (NSString *)bundleExecutable { return [self.bundle objectForInfoDictionaryKey:@"CFBundleExecutable"]; }
- (NSString *)canonicalExecutablePath { return self.executableURL.path; }
- (NSString *)sdkVersion { return self.linkedSDKVersion; }
- (NSURL *)bundleContainerURL { return self.bundleURL.URLByDeletingLastPathComponent; }
- (NSURL *)dataContainerURL { return nil; }
- (NSURL *)containerURL { return nil; }
- (NSUInteger)sequenceNumber { return 0; }
- (NSUInteger)compatibilityState { return 0; }
- (NSUUID *)cacheGUID { return _cacheGUID; }
- (NSNumber *)genreID { return @0; }

- (LSBundleInfoCachedValues *)objectsForInfoDictionaryKeys:(NSSet *)keys {
    NSMutableDictionary *result = [NSMutableDictionary dictionaryWithCapacity:keys.count];
    for (NSString *key in keys) {
        id value = [self.bundle objectForInfoDictionaryKey:key];
        if (value) result[key] = value;
    }
    Class valuesClass = PrivClass(LSBundleInfoCachedValues);
    if (!valuesClass) return nil;
    return [[valuesClass alloc] _initWithKeys:keys forDictionary:result];
}
- (NSDictionary *)entitlementValuesForKeys:(NSSet *)keys {
    Class valuesClass = PrivClass(LSBundleInfoCachedValues);
    if (!valuesClass) return nil;
    return (id)[[valuesClass alloc] _initWithKeys:keys forDictionary:@{}];
}
- (NSDictionary *)entitlements { return self.codeEntitlements; }
- (NSDictionary *)environmentVariables { return @{}; }
- (NSArray *)machOUUIDs { return @[]; }
- (NSDictionary *)groupContainerURLs { return @{}; }
- (NSString *)shortVersionString { return [self.bundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"]; }
- (NSString *)applicationIdentifier { return self.codeEntitlements[@"application-identifier"] ?: self.bundleIdentifier; }
- (NSString *)appIDPrefix { return nil; }
- (NSString *)applicationDSID { return nil; }
- (NSNumber *)platform { return @2; }
- (NSNumber *)staticDiskUsage { return @0; }
- (NSNumber *)dynamicDiskUsage { return @0; }
- (id)appState { return _state; }
- (NSString *)applicationType { return @"User"; }
- (NSArray *)deviceFamily {
    id value = [self.bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];
    return [value isKindOfClass:NSArray.class] ? value : nil;
}
- (NSArray *)requiredDeviceCapabilities {
    id value = [self.bundle objectForInfoDictionaryKey:@"UIRequiredDeviceCapabilities"];
    return [value isKindOfClass:NSArray.class] ? value : nil;
}
- (NSString *)signerIdentity { return nil; }
- (NSString *)teamID { return self.codeEntitlements[@"com.apple.developer.team-identifier"]; }
- (NSString *)teamIdentifier { return [self teamID]; }
- (BOOL)profileValidated { return YES; }
- (BOOL)UPPValidated { return NO; }
- (BOOL)freeProfileValidated { return NO; }
- (BOOL)isBetaApp { return NO; }
- (BOOL)isBeta { return NO; }
- (BOOL)isRestricted { return NO; }
- (BOOL)isPlaceholder { return NO; }
- (BOOL)isInstalled { return YES; }
- (BOOL)isDeletable { return NO; }
- (BOOL)isDeletableIgnoringRestrictions { return NO; }
- (BOOL)isRemoveableSystemApp { return NO; }
- (BOOL)isRemovedSystemApp { return NO; }
- (BOOL)isAppUpdate { return NO; }
- (BOOL)isDeviceBasedVPP { return NO; }
- (BOOL)isPurchasedReDownload { return NO; }
- (BOOL)isWhitelisted { return YES; }
- (BOOL)missingRequiredSINF { return NO; }
- (BOOL)fileSharingEnabled { return NO; }
- (BOOL)hasMIDBasedSINF { return YES; }
- (BOOL)isGameCenterEnabled { return NO; }
- (BOOL)gameCenterEverEnabled { return NO; }
- (BOOL)isArcadeApp { return NO; }
- (NSUInteger)installType { return 1; }
- (NSUInteger)originalInstallType { return 1; }
- (NSInteger)deviceManagementPolicy { return 0; }
- (NSNumber *)ratingRank { return @0; }
- (NSNumber *)itemID { return nil; }
- (NSNumber *)purchaserDSID { return nil; }
- (NSNumber *)downloaderDSID { return nil; }
- (id)diskUsage { return _diskUsage; }
- (NSString *)genre { return nil; }
- (NSArray *)subgenres { return nil; }
- (NSString *)vendorName { return nil; }
- (NSArray *)UIBackgroundModes { return nil; }
- (NSArray *)appTags { return nil; }
- (BOOL)supportsMultiwindow { return NO; }
- (LCFakeApplicationRecord *)correspondingApplicationRecord { return nil; }
- (LCFakeApplicationRecord *)fbs_correspondingApplicationRecord { return nil; }
@end

static BOOL LCLoadSpringBoardFramework(void) {
    __block BOOL loaded = NO;
    LCFlekClassicProbeBypass(^{
        dlerror();
        void *springBoard = dlopen("/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard",
                                   RTLD_LAZY | RTLD_GLOBAL);
        loaded = springBoard != NULL;
        if (!loaded) {
            NSLog(@"[FlekDeck/ClassicMode] SpringBoard.framework unavailable: %s",
                  dlerror() ?: "unknown dlopen error");
        }
    });
    return loaded;
}

static NSString *LCVersionString(uint32_t version) {
    return [NSString stringWithFormat:@"%u.%u.%u", version >> 16, (version >> 8) & 0xff, version & 0xff];
}

NSNumber *LCGetDefaultClassicMode(NSURL *appURL) {
    @try {
        NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;
        NSURL *executableURL = bundle.executableURL;
        if (!bundle || !executableURL) return @0;

        if (@available(iOS 27.0, *)) {
            // Avoid instantiating private SBApplication/SBApplicationInfo on iOS
            // 27+. The private object graph can abort the host on ABI drift. The
            // launch option itself remains supported by the guarded LS workspace
            // path: 1 is the phone Classic mode, 12 is the iPad Classic mode.
            NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];
            BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] &&
                                    [families containsObject:@2];
            NSUInteger mode = (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad &&
                               guestSupportsPad) ? 12 : 1;
            NSLog(@"[FlekDeck/ClassicMode] iOS 27+ safe mode=%lu for %@",
                  (unsigned long)mode, bundle.bundleIdentifier ?: bundle.bundleURL.lastPathComponent);
            return @(mode);
        }

        if (@available(iOS 27.0, *)) {
            NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];
            BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] && [families containsObject:@2];
            NSUInteger safeClassicMode =
                (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad && guestSupportsPad)
                    ? 12u : 1u;
            NSLog(@"[FlekDeck/ClassicMode] iOS 27 safe mode=%lu; private SpringBoard probe skipped",
                  (unsigned long)safeClassicMode);
            return @(safeClassicMode);
        }

        static Class SBApplicationClass = Nil;
        static Class SBApplicationInfoClass = Nil;
        @synchronized([LCFakeApplicationProxy class]) {
            if (!SBApplicationClass || !SBApplicationInfoClass) {
                if (!LCLoadSpringBoardFramework()) return @0;
                SBApplicationClass = PrivClass(SBApplication);
                SBApplicationInfoClass = PrivClass(SBApplicationInfo);
            }
        }
        if (!SBApplicationClass || !SBApplicationInfoClass) return @0;

        bool hasArm64 = false, hasArm32 = false, encrypted = false;
        NSString *archError = LCInspectMachOArchitectures(executableURL.fileSystemRepresentation,
                                                           &hasArm64, &hasArm32, &encrypted);
        if (archError) {
            NSLog(@"[FlekDeck/ClassicMode] architecture inspection failed: %@", archError);
            return @0;
        }
        uint32_t sdk = 0;
        NSString *sdkError = LCReadMachOSDKVersion(executableURL.fileSystemRepresentation,
                                                    !hasArm64 && hasArm32,
                                                    &sdk);
        if (sdkError) {
            NSLog(@"[FlekDeck/ClassicMode] SDK inspection failed: %@", sdkError);
            return @0;
        }

        LCFakeApplicationProxy *proxy = [[LCFakeApplicationProxy alloc]
                                         initWithBundle:bundle
                                         executableURL:executableURL
                                         sdkVersion:LCVersionString(sdk)
                                         entitlements:@{}];
        if (!proxy) return @0;

        SBApplicationInfo *sbAppInfo = nil;
        SEL modernInit = @selector(_initWithApplicationProxy:record:appIdentity:processIdentity:overrideURL:);
        SEL legacyInit = @selector(_initWithApplicationProxy:overrideURL:);
        if ([SBApplicationInfoClass instancesRespondToSelector:modernInit]) {
            sbAppInfo = [[SBApplicationInfoClass alloc]
                         _initWithApplicationProxy:proxy
                         record:[LCFakeApplicationRecord new]
                         appIdentity:[LCFakeApplicationIdentity new]
                         processIdentity:[LCFakeProcessIdentity new]
                         overrideURL:appURL];
        } else if ([SBApplicationInfoClass instancesRespondToSelector:legacyInit]) {
            sbAppInfo = [[SBApplicationInfoClass alloc]
                         _initWithApplicationProxy:proxy
                         overrideURL:appURL];
        } else {
            NSLog(@"[FlekDeck/ClassicMode] unsupported SBApplicationInfo initializer");
            return @0;
        }
        if (!sbAppInfo) return @0;

        SBApplication *sbApp = [[SBApplicationClass alloc] initWithApplicationInfo:sbAppInfo];
        if (!sbApp || ![sbApp respondsToSelector:@selector(_defaultClassicMode)]) return @0;
        NSInteger mode = [sbApp _defaultClassicMode];
        return mode > 0 ? @(mode) : @0;
    } @catch (NSException *exception) {
        NSLog(@"[FlekDeck/ClassicMode] probe failed safely: %@ %@", exception.name, exception.reason);
        return @0;
    }
}
