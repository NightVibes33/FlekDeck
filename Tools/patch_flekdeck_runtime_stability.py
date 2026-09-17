#!/usr/bin/env python3
from pathlib import Path

# Runtime-only hardening for the parity/ARM32 integration. This script is
# deliberately idempotent and is meant to run AFTER all parity adapters.

# 1) Classic/Compatibility Mode probe: private APIs fail closed instead of
# asserting or assuming one SBApplicationInfo initializer forever.
probe = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m")
text = probe.read_text()
text = text.replace(
    "@implementation LCFakeApplicationIdentity\n@end",
    "@implementation LCFakeApplicationIdentity\n- (instancetype)copy { return self; }\n@end",
    1,
)
text = text.replace(
    "@interface SBApplicationInfo : NSObject\n- (instancetype)_initWithApplicationProxy:(id)proxy record:(id)record appIdentity:(id)identity processIdentity:(id)identity2 overrideURL:(NSURL*)overrideURL;\n@end",
    "@interface SBApplicationInfo : NSObject\n- (instancetype)_initWithApplicationProxy:(id)proxy overrideURL:(NSURL*)overrideURL;\n- (instancetype)_initWithApplicationProxy:(id)proxy record:(id)record appIdentity:(id)identity processIdentity:(id)identity2 overrideURL:(NSURL*)overrideURL;\n@end",
    1,
)
old_loader = '''void LCLoadSpringBoardFramework(void) {
    bypass_os_variant_has_internal_content(^{
        dlerror();
        void *springBoard = dlopen("/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard",
                                   RTLD_LAZY | RTLD_GLOBAL);
        
        NSCAssert(springBoard, @"Cannot load SpringBoard.framework: %s",
                  dlerror() ?: "unknown dlopen error");
    });
}'''
new_loader = '''void LCLoadSpringBoardFramework(void) {
    bypass_os_variant_has_internal_content(^{
        dlerror();
        void *springBoard = dlopen("/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard",
                                   RTLD_LAZY | RTLD_GLOBAL);
        if (!springBoard) {
            NSLog(@"[FlekDeck/ClassicMode] SpringBoard.framework unavailable: %s",
                  dlerror() ?: "unknown dlopen error");
        }
    });
}'''
if new_loader not in text:
    if old_loader not in text:
        raise SystemExit(f"{probe}: SpringBoard loader anchor missing")
    text = text.replace(old_loader, new_loader, 1)
start = text.find("NSNumber *LCGetDefaultClassicMode(NSURL *appURL) {")
end_token = "    return @(mode);\n}\n"
end = text.find(end_token, start)
if start < 0 or end < 0:
    raise SystemExit(f"{probe}: classic probe function anchor missing")
end += len(end_token)
safe_probe = '''NSNumber *LCGetDefaultClassicMode(NSURL *appURL) {
    @try {
        NSBundle *bundle = [NSBundle bundleWithURL:appURL];
        NSURL *executableURL = bundle.executableURL;
        if (!bundle || !executableURL) {
            NSLog(@"[FlekDeck/ClassicMode] app bundle or executable unavailable: %@", appURL);
            return @0;
        }

        static Class SBApplicationClass;
        static Class SBApplicationInfoClass;
        static dispatch_once_t onceToken;
        dispatch_once(&onceToken, ^{
            LCLoadSpringBoardFramework();
            SBApplicationClass = PrivClass(SBApplication);
            SBApplicationInfoClass = PrivClass(SBApplicationInfo);
        });
        if (!SBApplicationClass || !SBApplicationInfoClass) {
            NSLog(@"[FlekDeck/ClassicMode] SpringBoard compatibility classes unavailable");
            return @0;
        }

        __block uint32_t sdk = 0;
        NSString *parseError = LCParseMachO(
            executableURL.fileSystemRepresentation,
            true,
            ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
                sdk = dyld_get_sdk_version((const struct mach_header *)header);
            }
        );
        if (parseError) {
            NSLog(@"[FlekDeck/ClassicMode] unable to inspect guest executable: %@", parseError);
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
            NSLog(@"[FlekDeck/ClassicMode] no supported SBApplicationInfo initializer");
            return @0;
        }
        if (!sbAppInfo) return @0;

        SBApplication *sbApp = [[SBApplicationClass alloc] initWithApplicationInfo:sbAppInfo];
        if (!sbApp || ![sbApp respondsToSelector:@selector(_defaultClassicMode)]) return @0;
        return @([sbApp _defaultClassicMode]);
    } @catch (NSException *exception) {
        NSLog(@"[FlekDeck/ClassicMode] probe failed safely: %@ %@", exception.name, exception.reason);
        return @0;
    }
}
'''
text = text[:start] + safe_probe + text[end:]
probe.write_text(text)

# Guard the model as a second containment layer.
app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = app_info.read_text()
old = '''    NSNumber *mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": mode ?: @0,
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return mode.unsignedIntegerValue;'''
new = '''    NSNumber *mode = nil;
    @try {
        mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    } @catch (NSException *exception) {
        NSLog(@"[FlekDeck/ClassicMode] default-mode probe exception: %@ %@", exception.name, exception.reason);
    }
    if (![mode isKindOfClass:NSNumber.class]) mode = @0;
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": mode,
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return mode.unsignedIntegerValue;'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_info}: default Classic Mode cache anchor missing")
    text = text.replace(old, new, 1)
app_info.write_text(text)

# 2) Classic relaunch: only terminate after a confirmed successful relaunch.
shared = Path("LiveContainer/LCSharedUtils.m")
text = shared.read_text()
start = text.find("+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {")
end = text.find("+ (BOOL)launchToGuestAppWithURL:(NSURL *)url {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{shared}: Classic launch function markers missing")
safe_launch = r'''+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {
    if(classicMode == 0) return [self launchToGuestApp];

    Class configurationClass = PrivClass(_LSOpenConfiguration);
    Class workspaceClass = PrivClass(LSApplicationWorkspace);
    if (!configurationClass || !workspaceClass) {
        NSLog(@"[FlekDeck/ClassicMode] private relaunch classes unavailable; using normal launch");
        return [self launchToGuestApp];
    }

    _LSOpenConfiguration *configuration = [[configurationClass alloc] init];
    LSApplicationWorkspace *workspace = [workspaceClass defaultWorkspace];
    NSString *bundleIdentifier = lcMainBundle.bundleIdentifier ?: NSBundle.mainBundle.bundleIdentifier;
    if (!configuration || !workspace || bundleIdentifier.length == 0 ||
        ![workspace respondsToSelector:@selector(openApplicationWithBundleIdentifier:configuration:completionHandler:)]) {
        NSLog(@"[FlekDeck/ClassicMode] private relaunch API unavailable; using normal launch");
        return [self launchToGuestApp];
    }

    NSMutableDictionary *frontBoardOptions = [NSMutableDictionary new];
    frontBoardOptions[@"__ActivateAsClassic"] = @(classicMode);
    configuration.frontBoardOptions = frontBoardOptions;

    NSObject *completionLock = [NSObject new];
    __block NSInteger remainingAttempts = 2;
    __block BOOL finished = NO;
    __block NSError *lastError = nil;

    void (^terminateAfterSuccessfulRelaunch)(void) = ^{
        __asm__ __volatile__ (
            "mov x0, #31\n"
            "mov x16, #26\n"
            "svc #0x80\n"
        );
        raise(SIGKILL);
    };

    for(int i = 0; i < 2; i++) {
        [workspace openApplicationWithBundleIdentifier:bundleIdentifier
                                         configuration:configuration
                                     completionHandler:^(BOOL success, NSError *error) {
            NSLog(@"[FlekDeck/ClassicMode] success=%d mode=%lu error=%@", success, (unsigned long)classicMode, error);
            BOOL shouldTerminate = NO;
            BOOL shouldFallback = NO;
            @synchronized(completionLock) {
                if (finished) return;
                if (success) {
                    finished = YES;
                    shouldTerminate = YES;
                } else {
                    lastError = error;
                    remainingAttempts -= 1;
                    if (remainingAttempts <= 0) {
                        finished = YES;
                        shouldFallback = YES;
                    }
                }
            }
            if (shouldTerminate) {
                terminateAfterSuccessfulRelaunch();
                return;
            }
            if (shouldFallback) {
                NSString *detail = lastError.localizedDescription ?: @"unknown error";
                NSLog(@"[FlekDeck/ClassicMode] compatibility relaunch failed twice (%@); using normal launch", detail);
                [lcUserDefaults setObject:detail forKey:@"LCClassicModeLastError"];
                dispatch_async(dispatch_get_main_queue(), ^{ [self launchToGuestApp]; });
            }
        }];
    }
    return YES;
}

'''
text = text[:start] + safe_launch + text[end:]
shared.write_text(text)

# 3) Make Swift/UI and bootstrap use the same UserDefaults domain even when the
# app has no usable app-group entitlement.
utils = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
text = utils.read_text()
old = '    public static let appGroupUserDefault = UserDefaults.init(suiteName: LCSharedUtils.appGroupID()) ?? UserDefaults.standard'
new = '''    public static let appGroupUserDefault: UserDefaults = {
        let groupID = LCSharedUtils.appGroupID()
        guard !groupID.isEmpty,
              groupID != "Unknown",
              let defaults = UserDefaults(suiteName: groupID) else {
            return .standard
        }
        return defaults
    }()'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{utils}: app-group defaults anchor missing")
    text = text.replace(old, new, 1)
old = '''        guard let groupUserDefaults = UserDefaults(suiteName: LCSharedUtils.appGroupID()),
              let jitEnabler = JITEnablerType(rawValue: groupUserDefaults.integer(forKey: "LCJITEnablerType")) else {
            return false
        }'''
new = '''        let groupUserDefaults = LCUtils.appGroupUserDefault
        guard let jitEnabler = JITEnablerType(rawValue: groupUserDefaults.integer(forKey: "LCJITEnablerType")) else {
            return false
        }'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{utils}: JIT defaults anchor missing")
    text = text.replace(old, new, 1)
utils.write_text(text)

# 4) Remove the unsafe free-form global ARM32 runtime field. Keep the validated
# picker only. Hide FLEX entirely when it is not linked.
settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
text = settings.read_text()
raw_runtime = '''                        #if is32BitSupported
                        HStack {
                            Text("32-bit Runtime")
                            Spacer()
                            TextField("", text: $liveExec32Path)
                                .multilineTextAlignment(.trailing)
                        }
                        #endif
'''
text = text.replace(raw_runtime, "", 1)
old_flex = '''                        Button {
                            presentFLEXOverlay()
                        } label: {
                            Text("Show FLEX Overlay")
                        }
                        .disabled(NSClassFromString("FLEXManager") == nil)
'''
new_flex = '''                        if NSClassFromString("FLEXManager") != nil {
                            Button {
                                presentFLEXOverlay()
                            } label: {
                                Text("Show FLEX Overlay")
                            }
                        }
'''
text = text.replace(old_flex, new_flex, 1)
settings.write_text(text)

# 5) Robust Mach-O reading + ARM slices in FAT binaries.
macho = Path("LiveContainer/LCMachOUtils.m")
text = macho.read_text()
start = text.find("NSString *LCParseMachO(const char *path, bool readOnly, LCParseMachOCallback callback) {")
end = text.find("NSString *LCPatchMachOFixupARM64eSlice(const char *path) {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{macho}: LCParseMachO markers missing")
safe_parse = r'''NSString *LCParseMachO(const char *path, bool readOnly, LCParseMachOCallback callback) {
    if (!path || !callback) return @"Invalid Mach-O parser arguments";

    int fd = open(path, readOnly ? O_RDONLY : O_RDWR, readOnly ? 0400 : 0600);
    if (fd < 0) return [NSString stringWithFormat:@"Failed to open %s: %s", path, strerror(errno)];

    struct stat s = {0};
    if (fstat(fd, &s) != 0) {
        NSString *error = [NSString stringWithFormat:@"Failed to stat %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }
    if (s.st_size < (off_t)sizeof(uint32_t)) {
        close(fd);
        return @"Mach-O file is too small";
    }

    int protection = readOnly ? PROT_READ : (PROT_READ | PROT_WRITE);
    int flags = readOnly ? MAP_PRIVATE : MAP_SHARED;
    void *map = mmap(NULL, (size_t)s.st_size, protection, flags, fd, 0);
    if (map == MAP_FAILED) {
        NSString *error = [NSString stringWithFormat:@"Failed to map %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }

    NSString *result = nil;
    uint32_t magic = *(uint32_t *)map;
    if (magic == FAT_CIGAM) {
        struct fat_header *header = (struct fat_header *)map;
        uint32_t archCount = OSSwapInt32(header->nfat_arch);
        size_t tableSize = sizeof(struct fat_header) + ((size_t)archCount * sizeof(struct fat_arch));
        if (archCount > 128 || tableSize > (size_t)s.st_size) {
            result = @"Malformed FAT Mach-O architecture table";
        } else {
            struct fat_arch *arch = (struct fat_arch *)((uint8_t *)map + sizeof(struct fat_header));
            for (uint32_t i = 0; i < archCount; i++, arch++) {
                int cputype = OSSwapInt32(arch->cputype);
                if (cputype != CPU_TYPE_ARM64 && cputype != CPU_TYPE_ARM) continue;
                uint32_t offset = OSSwapInt32(arch->offset);
                uint32_t size = OSSwapInt32(arch->size);
                if ((uint64_t)offset + (uint64_t)size > (uint64_t)s.st_size || size < sizeof(struct mach_header)) {
                    result = @"Malformed FAT Mach-O slice";
                    break;
                }
                callback(path, (struct mach_header_64 *)((uint8_t *)map + offset), fd, map);
            }
        }
    } else if (magic == MH_MAGIC_64 || magic == MH_MAGIC) {
        callback(path, (struct mach_header_64 *)map, fd, map);
    } else {
        result = @"Not a Mach-O file";
    }

    if (!readOnly && result == nil) msync(map, (size_t)s.st_size, MS_SYNC);
    munmap(map, (size_t)s.st_size);
    close(fd);
    return result;
}

'''
text = text[:start] + safe_parse + text[end:]
macho.write_text(text)

# Keep the shell parity generator from restoring a permanently disabled FLEX row.
shell_gen = Path("Tools/patch_flekdeck_shell_parity.py")
if shell_gen.exists():
    gen = shell_gen.read_text()
    gen = gen.replace(
        '''                        Button {
                            presentFLEXOverlay()
                        } label: {
                            Text("Show FLEX Overlay")
                        }
                        .disabled(NSClassFromString("FLEXManager") == nil)
''',
        '''                        if NSClassFromString("FLEXManager") != nil {
                            Button {
                                presentFLEXOverlay()
                            } label: {
                                Text("Show FLEX Overlay")
                            }
                        }
'''
    )
    shell_gen.write_text(gen)

# Invariants: fail CI rather than ship a compile-only integration.
checks = {
    probe: ["instancesRespondToSelector:modernInit", "_initWithApplicationProxy:(id)proxy overrideURL", "probe failed safely", "- (instancetype)copy { return self; }"],
    app_info: ["default-mode probe exception", "mode = @0;"],
    shared: ["compatibility relaunch failed twice", "if (shouldTerminate)", "LCClassicModeLastError"],
    utils: ['groupID != "Unknown"', "let groupUserDefaults = LCUtils.appGroupUserDefault"],
    settings: ["Default 32-bit Runtime"],
    macho: ["cputype != CPU_TYPE_ARM64 && cputype != CPU_TYPE_ARM", "Malformed FAT Mach-O slice"],
}
for path, needles in checks.items():
    value = path.read_text()
    for needle in needles:
        if needle not in value:
            raise SystemExit(f"{path}: missing runtime-stability marker: {needle}")
if 'TextField("", text: $liveExec32Path)' in settings.read_text():
    raise SystemExit(f"{settings}: unsafe raw 32-bit runtime field still exists")
if "NSCAssert(springBoard" in probe.read_text():
    raise SystemExit(f"{probe}: Classic probe still asserts on missing SpringBoard.framework")

print("FlekDeck runtime stability fixes applied")
