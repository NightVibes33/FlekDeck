#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    source = path.read_text()
    if new in source:
        return
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one {label} block, found {count}")
    path.write_text(source.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Persist ARM32 detection and keep ARM64-only patch/sign operations off ARM32.
# ---------------------------------------------------------------------------
app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
replace_once(
    app_info,
    '''    bool is32bit = false;
    if (needPatch) {''',
    '''#if is32BitSupported
    // Once an ARM32 guest has been identified, keep that fact on later launches.
    bool is32bit = self.is32bit;
#else
    bool is32bit = false;
#endif
    if (needPatch) {''',
    "ARM32 detection initializer",
)

replace_once(
    app_info,
    '''        is32bit = !has64bitSlice;
        LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
        if (isEncrypted) {''',
    '''        is32bit = !has64bitSlice;
#if is32BitSupported
        self.is32bit = is32bit;
#endif
        if (!is32bit) {
            LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
        } else {
#if is32BitSupported
            // LiveExec32 owns ARM32 execution. It requires JIT and SDK spoofing.
            self.isJITNeeded = YES;
            self.spoofSDKVersion = YES;
#endif
        }
        if (isEncrypted) {''',
    "ARM32 Mach-O detection",
)

replace_once(
    app_info,
    '''#if !is32BitSupported
    if(is32bit) {
        completetionHandler(NO, @"32-bit app is NOT supported!");
        return;
    }
#else
    self.is32Bit = is32bit;
#endif

    if (!LCSharedUtils.certificatePassword || is32bit || self.dontSign) {''',
    '''#if !is32BitSupported
    if(is32bit) {
        completetionHandler(NO, @"32-bit app is NOT supported!");
        return;
    }
#endif

    if (!LCSharedUtils.certificatePassword || self.is32bit || self.dontSign) {''',
    "legacy ARM32 property/signing block",
)

replace_once(
    app_info,
    '''        NSLog(@"[LC] sdkversion = %8x", sdkVersion);
        _info[@"spoofSDKVersion"] = [NSNumber numberWithUnsignedInt:sdkVersion];''',
    '''#if is32BitSupported
        // Keep the same compatibility floor as the proven LiveExec32 integration.
        uint32_t minSDK = self.is32bit ? 0x20000 : 0xb0000;
        if ((self.is32bit || sdkVersion) && sdkVersion < minSDK) {
            sdkVersion = minSDK;
        }
#else
        if (sdkVersion && sdkVersion < 0xb0000) {
            sdkVersion = 0xb0000;
        }
#endif
        NSLog(@"[LC] sdkversion = %8x", sdkVersion);
        _info[@"spoofSDKVersion"] = [NSNumber numberWithUnsignedInt:sdkVersion];''',
    "SDK spoof floor",
)

# ---------------------------------------------------------------------------
# The first temp loader patch used LC32RunGuest's 3-argument ABI for appMain too,
# which would change every native ARM64 guest call. Restore native appMain's
# two-argument ABI and give LiveExec32 a separate function pointer.
# ---------------------------------------------------------------------------
bootstrap = Path("LiveContainer/LCBootstrap.m")
replace_once(
    bootstrap,
    '''static int (*appMain)(int, char**, char**);''',
    '''static int (*appMain)(int, char**);''',
    "native appMain ABI",
)

replace_once(
    bootstrap,
    '''    NSString *emulatorLauncherPath = nil;
    NSString *emulatorEntrySymbol = nil;
    *path = appExecPath;''',
    '''    NSString *emulatorLauncherPath = nil;
    NSString *emulatorEntrySymbol = nil;
    int (*emulatorMain)(int, char **, char **) = NULL;
    *path = appExecPath;''',
    "emulator entrypoint state",
)

replace_once(
    bootstrap,
    '''        appMain = (int (*)(int, char **, char **))dlsym(appHandle, emulatorEntrySymbol.UTF8String);''',
    '''        emulatorMain = (int (*)(int, char **, char **))dlsym(appHandle, emulatorEntrySymbol.UTF8String);''',
    "LiveExec32 dlsym target",
)

replace_once(
    bootstrap,
    '''        appMain = (int (*)(int, char **, char **))getAppEntryPoint(appHandle);''',
    '''        appMain = getAppEntryPoint(appHandle);''',
    "native entrypoint type",
)

replace_once(
    bootstrap,
    '''    if (!appMain) {
        appError = @"Could not find the main entry point";
        NSLog(@"[LCBootstrap] %@", appError);
        *path = oldPath;
        return appError;
    }''',
    '''    if((is32bit && emulatorEntrySymbol.length > 0) ? (emulatorMain == NULL) : (appMain == NULL)) {
        appError = @"Could not find the main entry point";
        NSLog(@"[LCBootstrap] %@", appError);
        *path = oldPath;
        return appError;
    }''',
    "entrypoint validity check",
)

replace_once(
    bootstrap,
    '''        ret = appMain(argc, argv, environ);''',
    '''        ret = appMain(argc, argv);''',
    "native ARM64 main call",
)

replace_once(
    bootstrap,
    '''        ret = appMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32, environ);''',
    '''        if(emulatorMain) {
            ret = emulatorMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32, environ);
        } else {
            // Compatibility fallback for an older LiveExec32 bundle without the
            // shared-framework entrypoint contract.
            ret = appMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32);
        }''',
    "ARM32 emulator call",
)

# ---------------------------------------------------------------------------
# ARM32 is currently supported by the proven single-process JIT route. Never
# send a 32-bit guest through FlekDeck's Parallel/LiveProcess execution path.
# ARM64 behavior remains exactly as before.
# ---------------------------------------------------------------------------
app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    app_model,
    '''        let multitask = multitask ?? shouldLaunchInMultitaskMode;''',
    '''#if is32BitSupported
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif''',
    "ARM32 normal-mode routing",
)

# ---------------------------------------------------------------------------
# Fail the build if the temporary integration ever regresses these boundaries.
# ---------------------------------------------------------------------------
required_app_info = [
    "bool is32bit = self.is32bit;",
    "self.is32bit = is32bit;",
    "self.isJITNeeded = YES;",
    "self.spoofSDKVersion = YES;",
    "uint32_t minSDK = self.is32bit ? 0x20000 : 0xb0000;",
]
text = app_info.read_text()
for marker in required_app_info:
    if marker not in text:
        raise SystemExit(f"{app_info}: missing ARM32 marker: {marker}")
if "self.is32Bit = is32bit;" in text:
    raise SystemExit(f"{app_info}: stale mis-cased ARM32 property assignment remains")

bootstrap_text = bootstrap.read_text()
for marker in [
    "static int (*appMain)(int, char**);",
    "int (*emulatorMain)(int, char **, char **) = NULL;",
    "emulatorMain = (int (*)(int, char **, char **))dlsym",
    "ret = appMain(argc, argv);",
    "ret = emulatorMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32, environ);",
]:
    if marker not in bootstrap_text:
        raise SystemExit(f"{bootstrap}: missing ABI marker: {marker}")
if "static int (*appMain)(int, char**, char**);" in bootstrap_text:
    raise SystemExit(f"{bootstrap}: native appMain still has LiveExec32 ABI")

if "appInfo.is32bit ? false" not in app_model.read_text():
    raise SystemExit(f"{app_model}: ARM32 can still enter Parallel mode")

print("FlekDeck ARM32 persistence, ABI isolation, and normal-mode routing applied")
