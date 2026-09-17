#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


# Classic Mode already has an offline probe and extension support in FlekDeck;
# restore only the model/UI/relaunch plumbing removed by the Vibe core adapter.
app_info_h = Path("LiveContainerSwiftUI/Models/LCAppInfo.h")
replace_once(
    app_info_h,
    "@property bool isJITNeeded;",
    "@property bool isJITNeeded;\n@property bool classicMode;\n@property (nonatomic, readonly) NSUInteger defaultClassicMode;",
    "Classic Mode properties",
)

app_info_m = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = app_info_m.read_text()
classic_impl = '''- (bool)classicMode {
    return [_info[@"classicMode"] boolValue];
}

- (void)setClassicMode:(bool)classicMode {
    _info[@"classicMode"] = @(classicMode);
    if(classicMode) {
        (void)[self defaultClassicMode];
    } else {
        [_info removeObjectForKey:@"LCClassicModeCache"];
        [self save];
    }
}

- (NSUInteger)defaultClassicMode {
    if(!self.classicMode) return 0;

    NSInteger systemMajorVersion = NSProcessInfo.processInfo.operatingSystemVersion.majorVersion;
    NSDictionary *cache = _info[@"LCClassicModeCache"];
    NSNumber *cachedMode = cache[@"defaultClassicMode"];
    NSNumber *cachedSystemMajorVersion = cache[@"systemMajorVersion"];
    if([cachedMode isKindOfClass:NSNumber.class] &&
       [cachedSystemMajorVersion isKindOfClass:NSNumber.class] &&
       cachedSystemMajorVersion.integerValue == systemMajorVersion) {
        return cachedMode.unsignedIntegerValue;
    }

    NSNumber *mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": mode ?: @0,
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return mode.unsignedIntegerValue;
}

'''
if classic_impl not in text:
    anchor = "- (bool)isLocked {\n"
    if anchor not in text:
        raise SystemExit(f"{app_info_m}: Classic Mode implementation anchor missing")
    text = text.replace(anchor, classic_impl + anchor, 1)
# ARM32 uses the proven single-process compatibility route and should default to
# Classic Mode just like current LiveContainer.
text = text.replace(
    "            self.isJITNeeded = YES;\n            self.spoofSDKVersion = YES;",
    "            self.isJITNeeded = YES;\n            self.classicMode = YES;\n            self.spoofSDKVersion = YES;",
    1,
)
app_info_m.write_text(text)

app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    app_model,
    '''    func jitLaunch(appName: String) async
    func jitLaunch(withScript script: String, appName: String) async''',
    '''    func jitLaunch(appName: String, classicMode: UInt) async
    func jitLaunch(withScript script: String, appName: String, classicMode: UInt) async''',
    "Classic Mode delegate API",
)
replace_once(
    app_model,
    '''    @Published var uiIsJITNeeded : Bool {
        didSet {
            appInfo.isJITNeeded = uiIsJITNeeded
        }
    }''',
    '''    @Published var uiIsJITNeeded : Bool {
        didSet {
            appInfo.isJITNeeded = uiIsJITNeeded
        }
    }
    @Published var uiClassicMode : Bool {
        didSet {
            appInfo.classicMode = uiClassicMode
        }
    }''',
    "Classic Mode model state",
)
replace_once(
    app_model,
    "        self.uiIsJITNeeded = appInfo.isJITNeeded\n",
    "        self.uiIsJITNeeded = appInfo.isJITNeeded\n        self.uiClassicMode = appInfo.classicMode\n",
    "Classic Mode initialization",
)
text = app_model.read_text()
old_multitask = '''#if is32BitSupported
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif'''
new_multitask = '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // LiveExec32 and Classic Mode both require the single-process host path.
        let multitask = (appInfo.is32bit || classicMode != 0) ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = classicMode == 0 ? (multitask ?? shouldLaunchInMultitaskMode) : false
#endif'''
if new_multitask not in text:
    if old_multitask not in text:
        raise SystemExit(f"{app_model}: patched multitask anchor missing")
    text = text.replace(old_multitask, new_multitask, 1)
text = text.replace(
    "await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName())",
    "await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName(), classicMode: classicMode)",
    1,
)
text = text.replace(
    "await delegate?.jitLaunch(appName: self.appInfo.displayName())",
    "await delegate?.jitLaunch(appName: self.appInfo.displayName(), classicMode: classicMode)",
    1,
)
# Change only the normal single-app launch inside runApp.
needle = "            LCSharedUtils.launchToGuestApp()\n        }\n        \n        // Record the launch time"
replacement = "            LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)\n        }\n        \n        // Record the launch time"
if replacement not in text:
    if needle not in text:
        raise SystemExit(f"{app_model}: normal launch anchor missing")
    text = text.replace(needle, replacement, 1)
app_model.write_text(text)

# Restore the per-app switch without importing upstream Multitask UI.
app_settings = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
text = app_settings.read_text()
classic_ui = '''            if #available(iOS 16.0, *) {
                Section {
                    Toggle(isOn: $model.uiClassicMode) {
                        Text("lc.appSettings.classicMode".loc)
                    }
                } footer: {
                    Text("lc.appSettings.classicModeDesc".loc)
                }
            }
            
'''
if classic_ui not in text:
    anchor = '''            Section {
                Toggle(isOn: $model.uiIsLocked) {'''
    if anchor not in text:
        raise SystemExit(f"{app_settings}: Classic Mode UI anchor missing")
    text = text.replace(anchor, classic_ui + anchor, 1)
app_settings.write_text(text)

# Add Classic Mode relaunch as an additive API. Normal FlekDeck relaunch remains
# byte-for-byte on launchToGuestApp when classicMode == 0.
shared_h = Path("LiveContainer/LCSharedUtils.h")
replace_once(
    shared_h,
    "+ (BOOL)launchToGuestApp;",
    "+ (BOOL)launchToGuestApp;\n+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode;",
    "Classic Mode relaunch declaration",
)

shared_m = Path("LiveContainer/LCSharedUtils.m")
text = shared_m.read_text()
classic_launch = '''+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {
    if(classicMode == 0) {
        return [self launchToGuestApp];
    }

    void (^completionHandler)(BOOL) = ^(BOOL success) {
        __asm__ __volatile__ (
            "mov x0, #31\\n"
            "mov x16, #26\\n"
            "svc #0x80\\n"
        );
        raise(SIGKILL);
    };

    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    NSMutableDictionary *frontBoardOptions = [NSMutableDictionary new];
    frontBoardOptions[FBSOpenApplicationOptionKeyActivateAsClassic] = @(classicMode);
    configuration.frontBoardOptions = frontBoardOptions;

    NSString *bundleIdentifier = lcMainBundle.bundleIdentifier ?: NSBundle.mainBundle.bundleIdentifier;
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];
    for(int i = 0; i < 2; i++) {
        [workspace openApplicationWithBundleIdentifier:bundleIdentifier
                                         configuration:configuration
                                     completionHandler:^(BOOL success, NSError *error) {
            NSLog(@"[FlekDeck/ClassicMode] success=%d mode=%lu error=%@", success, (unsigned long)classicMode, error);
            completionHandler(success);
        }];
    }
    return YES;
}

'''
if classic_launch not in text:
    anchor = "+ (BOOL)launchToGuestAppWithURL:(NSURL *)url {\n"
    if anchor not in text:
        raise SystemExit(f"{shared_m}: Classic Mode relaunch anchor missing")
    text = text.replace(anchor, classic_launch + anchor, 1)
# Deep-link launches should retain the target app's cached mode.
old_url_launch = '''        [lcUserDefaults setObject:launchBundleId forKey:@"selected"];
        [lcUserDefaults setObject:containerFolderName forKey:@"selectedContainer"];
        return [self launchToGuestApp];'''
new_url_launch = '''        [lcUserDefaults setObject:launchBundleId forKey:@"selected"];
        [lcUserDefaults setObject:containerFolderName forKey:@"selectedContainer"];
        bool isSharedApp = false;
        NSBundle *appBundle = [self findBundleWithBundleId:launchBundleId isSharedAppOut:&isSharedApp];
        NSDictionary *appInfo = [NSDictionary dictionaryWithContentsOfFile:
            [appBundle.bundlePath stringByAppendingPathComponent:@"LCAppInfo.plist"]];
        NSUInteger classicMode = [appInfo[@"classicMode"] boolValue]
            ? [appInfo[@"LCClassicModeCache"][@"defaultClassicMode"] unsignedIntegerValue]
            : 0;
        return [self launchToGuestAppWithClassicMode:classicMode];'''
if new_url_launch not in text:
    if old_url_launch not in text:
        raise SystemExit(f"{shared_m}: deep-link launch anchor missing")
    text = text.replace(old_url_launch, new_url_launch, 1)
shared_m.write_text(text)

# JIT acquisition only needs the mode for immediate TrollStore relaunch; the
# provider-specific acquisition paths remain FlekDeck's existing implementation.
utils_ext = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
text = utils_ext.read_text()
text = text.replace(
    "public static func askForJIT(withScript script: String? = nil, appName: String? = nil, onServerMessage:",
    "public static func askForJIT(withScript script: String? = nil, appName: String? = nil, classicMode: UInt = 0, onServerMessage:",
    1,
)
# Only the TrollStore early-return belongs to this function before any provider selection.
text = text.replace(
    "            LCSharedUtils.launchToGuestApp()\n            return true",
    "            LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)\n            return true",
    1,
)
utils_ext.write_text(text)

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
text = text.replace(
    "let _ = await LCUtils.askForJIT(withScript: script, appName: appName) { newMsg in",
    "let _ = await LCUtils.askForJIT(withScript: script, appName: appName, classicMode: classicMode) { newMsg in",
    1,
)
# The existing compatibility overloads already carry classicMode; stop discarding it.
classic_func_anchor = "func jitLaunch(withScript script: String, appName: String, classicMode: UInt) async"
func_start = text.find(classic_func_anchor)
if func_start < 0:
    raise SystemExit(f"{app_list}: Classic Mode JIT overload missing")
launch_pos = text.find("        LCSharedUtils.launchToGuestApp()", func_start)
if launch_pos < 0:
    if "LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)" not in text[func_start:]:
        raise SystemExit(f"{app_list}: JIT relaunch anchor missing")
else:
    text = text[:launch_pos] + "        LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)" + text[launch_pos + len("        LCSharedUtils.launchToGuestApp()"):]
text = text.replace(
    "            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified\n            finalNewApp.autoSaveDisabled = false",
    "            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified\n            finalNewApp.classicMode = appToReplace.appInfo.classicMode\n            finalNewApp.autoSaveDisabled = false",
    1,
)
app_list.write_text(text)

checks = {
    app_info_h: ["@property bool classicMode;", "defaultClassicMode"],
    app_info_m: ["LCClassicModeCache", "LCGetDefaultClassicMode", "self.classicMode = YES;"],
    app_model: ["uiClassicMode", "let classicMode = appInfo.defaultClassicMode", "classicMode: classicMode"],
    app_settings: ["$model.uiClassicMode", "lc.appSettings.classicModeDesc"],
    shared_h: ["launchToGuestAppWithClassicMode"],
    shared_m: ["FBSOpenApplicationOptionKeyActivateAsClassic", "launchToGuestAppWithClassicMode:classicMode"],
    utils_ext: ["classicMode: UInt = 0", "launchToGuestApp(withClassicMode: classicMode)"],
    app_list: ["askForJIT(withScript: script, appName: appName, classicMode: classicMode)", "finalNewApp.classicMode"],
}
for path, needles in checks.items():
    value = path.read_text()
    for needle in needles:
        if needle not in value:
            raise SystemExit(f"{path}: missing Classic Mode marker: {needle}")

print("FlekDeck Classic Mode parity restored without replacing App Switcher/Parallel/PiP")
