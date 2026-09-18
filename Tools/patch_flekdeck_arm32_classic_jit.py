#!/usr/bin/env python3
from pathlib import Path

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise SystemExit(f"{path}: {label} anchor missing or duplicated")
    path.write_text(text.replace(old, new, 1))

shared_h = Path("LiveContainer/LCSharedUtils.h")
replace_once(
    shared_h,
    "+ (BOOL)launchToGuestApp;\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url;",
    "+ (BOOL)launchToGuestApp;\n+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode;\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url;",
    "classic relaunch declaration",
)

shared_m = Path("LiveContainer/LCSharedUtils.m")
classic_method = r'''
+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {
    // Native guests keep FlekDeck main's exact relaunch path.
    if(classicMode == 0) {
        return [self launchToGuestApp];
    }

    void (^completionHandler)(BOOL) = ^(BOOL success) {
        __asm__ __volatile__ (
            "mov x0, #31\n"
            "mov x16, #26\n"
            "svc #0x80"
        );
        raise(SIGKILL);
    };

    if (!self.certificatePassword) {
        NSString *tsPath = [NSString stringWithFormat:@"%@/../_TrollStore", NSBundle.mainBundle.bundlePath];
        if (!access(tsPath.UTF8String, F_OK)) {
            NSURL *launchURL = [NSURL URLWithString:[NSString stringWithFormat:
                @"apple-magnifier://enable-jit?bundle-id=%@", NSBundle.mainBundle.bundleIdentifier]];
            UIApplication *application = [NSClassFromString(@"UIApplication") sharedApplication];
            [application openURL:launchURL options:@{} completionHandler:completionHandler];
            return YES;
        }
    }

    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];

    for (int i = 0; i < 2; i++) {
        [workspace openApplicationWithBundleIdentifier:NSUserDefaults.lcMainBundle.bundleIdentifier
                                         configuration:configuration
                                     completionHandler:^(BOOL success, NSError *error) {
            NSLog(@"[LC32] classic relaunch success=%d error=%@", success, error);
            completionHandler(success);
        }];
    }
    return YES;
}
'''
text = shared_m.read_text()
if "+ (BOOL)launchToGuestAppWithClassicMode:" not in text:
    marker = "\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url {"
    if text.count(marker) != 1:
        raise SystemExit(f"{shared_m}: classic relaunch insertion marker missing or duplicated")
    shared_m.write_text(text.replace(marker, "\n" + classic_method + marker, 1))

utils = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
replace_once(
    utils,
    "public static func askForJIT(withScript script: String? = nil, appName: String? = nil, onServerMessage: ((String) -> Void)? = nil) async -> Bool {",
    "public static func askForJIT(withScript script: String? = nil, appName: String? = nil, classicMode: UInt = 0, onServerMessage: ((String) -> Void)? = nil) async -> Bool {",
    "askForJIT classicMode parameter",
)
replace_once(
    utils,
    """if (access((tsPath as NSString).utf8String, 0) == 0) {
            LCSharedUtils.launchToGuestApp()
            return true
        }""",
    """if (access((tsPath as NSString).utf8String, 0) == 0) {
            LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)
            return true
        }""",
    "TrollStore classic relaunch",
)

model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    model,
    """    func jitLaunch(appName: String) async
    func jitLaunch(withScript script: String, appName: String) async
    func jitLaunch(withPID pid: Int, withScript script: String?, appName: String) async""",
    """    func jitLaunch(appName: String) async
    func jitLaunch(withScript script: String, appName: String) async
    func jitLaunch(appName: String, classicMode: UInt) async
    func jitLaunch(withScript script: String, appName: String, classicMode: UInt) async
    func jitLaunch(withPID pid: Int, withScript script: String?, appName: String) async""",
    "delegate classic overloads",
)
replace_once(
    model,
    """#if is32BitSupported
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif""",
    """#if is32BitSupported
        // LiveExec32 requires the Compatibility/Classic relaunch contract.
        // Native ARM64 guests keep FlekDeck main's exact Parallel decision.
        let classicMode: UInt = appInfo.is32bit ? appInfo.defaultClassicMode : 0
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let classicMode: UInt = 0
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif""",
    "ARM32 classic mode selection",
)
replace_once(
    model,
    "await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName())",
    "await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName(), classicMode: classicMode)",
    "script JIT classic propagation",
)
replace_once(
    model,
    "await delegate?.jitLaunch(appName: self.appInfo.displayName())",
    "await delegate?.jitLaunch(appName: self.appInfo.displayName(), classicMode: classicMode)",
    "JIT classic propagation",
)

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
start = text.find("    func jitLaunch(withScript script: String, appName: String, classicMode: UInt) async {")
end = text.find("    func jitLaunch(withPID pid: Int", start)
if start < 0 or end < 0:
    raise SystemExit(f"{app_list}: classic JIT overload block missing")
block = text[start:end]
if "askForJIT(withScript: script, appName: appName, classicMode: classicMode)" not in block:
    if block.count("LCUtils.askForJIT(withScript: script, appName: appName) {") != 1:
        raise SystemExit(f"{app_list}: askForJIT classic anchor missing or duplicated")
    block = block.replace(
        "LCUtils.askForJIT(withScript: script, appName: appName) {",
        "LCUtils.askForJIT(withScript: script, appName: appName, classicMode: classicMode) {",
        1,
    )
if "launchToGuestApp(withClassicMode: classicMode)" not in block:
    if block.count("LCSharedUtils.launchToGuestApp()") != 1:
        raise SystemExit(f"{app_list}: classic relaunch anchor missing or duplicated")
    block = block.replace(
        "LCSharedUtils.launchToGuestApp()",
        "LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)",
        1,
    )
app_list.write_text(text[:start] + block + text[end:])

checks = {
    shared_h: ["launchToGuestAppWithClassicMode"],
    shared_m: ['@"__ActivateAsClassic"', "if(classicMode == 0)"],
    utils: ["classicMode: UInt = 0", "launchToGuestApp(withClassicMode: classicMode)"],
    model: ["appInfo.is32bit ? appInfo.defaultClassicMode : 0", "classicMode: classicMode"],
    app_list: ["askForJIT(withScript: script, appName: appName, classicMode: classicMode)", "launchToGuestApp(withClassicMode: classicMode)"],
}
for path, markers in checks.items():
    value = path.read_text()
    for marker in markers:
        if marker not in value:
            raise SystemExit(f"{path}: missing ARM32 Classic/JIT marker: {marker}")

print("FlekDeck ARM32 Classic/JIT relaunch contract applied")
