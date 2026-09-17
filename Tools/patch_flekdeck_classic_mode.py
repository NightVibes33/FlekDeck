#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Persist Classic Mode and calculate the actual FrontBoard mode with FlekDeck's
# existing offline probe. This stays a per-app single-process compatibility mode.
# ---------------------------------------------------------------------------
h = Path("LiveContainerSwiftUI/Models/LCAppInfo.h")
replace_once(
    h,
    '@property bool isJITNeeded;\n@property bool isLocked;',
    '@property bool isJITNeeded;\n@property bool classicMode;\n@property (nonatomic, readonly) NSUInteger defaultClassicMode;\n@property bool isLocked;',
    "Classic Mode app-info properties",
)

m = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = m.read_text()
if 'NSNumber *LCGetDefaultClassicMode(NSURL *appURL);' not in text:
    anchor = 'uint32_t dyld_get_sdk_version(const struct mach_header* mh);\n'
    if anchor not in text:
        raise SystemExit(f"{m}: Classic Mode probe declaration anchor missing")
    text = text.replace(anchor, anchor + 'NSNumber *LCGetDefaultClassicMode(NSURL *appURL);\n', 1)
m.write_text(text)

replace_once(
    m,
    '''- (void)setIsJITNeeded:(bool)isJITNeeded {
    _info[@"isJITNeeded"] = [NSNumber numberWithBool:isJITNeeded];
    [self save];
    
}

- (bool)isLocked {''',
    '''- (void)setIsJITNeeded:(bool)isJITNeeded {
    _info[@"isJITNeeded"] = [NSNumber numberWithBool:isJITNeeded];
    [self save];
    
}

- (bool)classicMode {
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
    NSUInteger value = [mode isKindOfClass:NSNumber.class] ? mode.unsignedIntegerValue : 0;
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": @(value),
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return value;
}

- (bool)isLocked {''',
    "Classic Mode accessors",
)

# ARM32 is a single-process compatibility guest and the proven branch enables
# Classic Mode automatically for it.
text = m.read_text()
old_arm32 = '''            self.isJITNeeded = YES;
            self.spoofSDKVersion = YES;'''
new_arm32 = '''            self.isJITNeeded = YES;
            self.classicMode = YES;
            self.spoofSDKVersion = YES;'''
if new_arm32 not in text:
    if old_arm32 not in text:
        raise SystemExit(f"{m}: ARM32 compatibility anchor missing")
    text = text.replace(old_arm32, new_arm32, 1)
m.write_text(text)

# ---------------------------------------------------------------------------
# Model/routing. Classic Mode and ARM32 can never enter FlekDeck's Parallel /
# App Switcher process path; normal FlekDeck apps keep their existing behavior.
# ---------------------------------------------------------------------------
model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    model,
    '''    func jitLaunch(appName: String) async
    func jitLaunch(withScript script: String, appName: String) async''',
    '''    func jitLaunch(appName: String, classicMode: UInt) async
    func jitLaunch(withScript script: String, appName: String, classicMode: UInt) async''',
    "Classic Mode delegate API",
)
replace_once(
    model,
    '''    @Published var uiIsJITNeeded : Bool {
        didSet {
            appInfo.isJITNeeded = uiIsJITNeeded
        }
    }
    @Published var uiIsHidden : Bool''',
    '''    @Published var uiIsJITNeeded : Bool {
        didSet {
            appInfo.isJITNeeded = uiIsJITNeeded
        }
    }
    @Published var uiClassicMode : Bool {
        didSet {
            appInfo.classicMode = uiClassicMode
        }
    }
    @Published var uiIsHidden : Bool''',
    "Classic Mode model state",
)
replace_once(
    model,
    '        self.uiIsJITNeeded = appInfo.isJITNeeded\n        self.uiIsHidden = appInfo.isHidden',
    '        self.uiIsJITNeeded = appInfo.isJITNeeded\n        self.uiClassicMode = appInfo.classicMode\n        self.uiIsHidden = appInfo.isHidden',
    "Classic Mode model init",
)

text = model.read_text()
old_route = '''#if is32BitSupported
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif'''
new_route = '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        let multitask = (appInfo.is32bit || classicMode != 0) ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = classicMode != 0 ? false : (multitask ?? shouldLaunchInMultitaskMode)
#endif'''
if new_route not in text:
    if old_route not in text:
        # Direct source before the ARM32 routing patch; support local parse/testing too.
        old_route = '        let multitask = multitask ?? shouldLaunchInMultitaskMode;'
        if old_route not in text:
            raise SystemExit(f"{model}: launch routing anchor missing")
    text = text.replace(old_route, new_route, 1)

text = text.replace(
    'await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName())',
    'await delegate?.jitLaunch(withScript: scriptData, appName: self.appInfo.displayName(), classicMode: classicMode)',
)
text = text.replace(
    'await delegate?.jitLaunch(appName: self.appInfo.displayName())',
    'await delegate?.jitLaunch(appName: self.appInfo.displayName(), classicMode: classicMode)',
)
text = text.replace(
    'LCSharedUtils.launchToGuestApp()\n        }',
    'LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)\n        }',
    1,
)
model.write_text(text)

# ---------------------------------------------------------------------------
# Objective-C relaunch API. Classic=0 delegates to FlekDeck's existing launch
# implementation. Non-zero mode adds only the FrontBoard option upstream uses.
# ---------------------------------------------------------------------------
shared_h = Path("LiveContainer/LCSharedUtils.h")
replace_once(
    shared_h,
    '+ (BOOL)launchToGuestApp;\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url;',
    '+ (BOOL)launchToGuestApp;\n+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode;\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url;',
    "Classic Mode relaunch declaration",
)

shared_m = Path("LiveContainer/LCSharedUtils.m")
text = shared_m.read_text()
anchor = '\n+ (BOOL)launchToGuestAppWithURL:(NSURL *)url {'
classic_impl = '''
+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {
    if(classicMode == 0) {
        return [self launchToGuestApp];
    }

    void (^completionHandler)(BOOL) = ^(BOOL success) {
        (void)success;
        __asm__ __volatile__ (
            "mov x0, #31\\n"
            "mov x16, #26\\n"
            "svc #0x80\\n"
        );
        raise(SIGKILL);
    };

    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    configuration.frontBoardOptions = @{
        FBSOpenApplicationOptionKeyActivateAsClassic: @(classicMode)
    };
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];
    for(int i = 0; i < 2; i++) {
        [workspace openApplicationWithBundleIdentifier:NSBundle.mainBundle.bundleIdentifier
                                         configuration:configuration
                                     completionHandler:^(BOOL success, NSError *error) {
            NSLog(@"[FlekDeck/ClassicMode] success=%d error=%@ mode=%lu", success, error, (unsigned long)classicMode);
            completionHandler(success);
        }];
    }
    return YES;
}
'''
if classic_impl.strip() not in text:
    if anchor not in text:
        raise SystemExit(f"{shared_m}: Classic Mode launch insertion anchor missing")
    text = text.replace(anchor, '\n' + classic_impl + anchor, 1)
shared_m.write_text(text)

# ---------------------------------------------------------------------------
# Per-app UI. ARM32 is forced on, so expose the setting read-only there.
# ---------------------------------------------------------------------------
settings = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
text = settings.read_text()
anchor_ui = '''            Section {
                Toggle(isOn: $model.uiSpoofSDKVersion) {
                    Text("lc.appSettings.spoofSDKVersion".loc)
                }
            } footer: {'''
classic_ui = '''            if #available(iOS 16.0, *) {
                Section {
                    Toggle(isOn: $model.uiClassicMode) {
                        Text("lc.appSettings.classicMode".loc)
                    }
#if is32BitSupported
                    .disabled(model.uiIs32bit)
#endif
                } footer: {
#if is32BitSupported
                    if model.uiIs32bit {
                        Text("Classic Mode is required for 32-bit apps and is enabled automatically.")
                    } else {
                        Text("lc.appSettings.classicModeDesc".loc)
                    }
#else
                    Text("lc.appSettings.classicModeDesc".loc)
#endif
                }
            }
            
'''
if classic_ui.strip() not in text:
    if anchor_ui not in text:
        raise SystemExit(f"{settings}: Classic Mode UI anchor missing")
    text = text.replace(anchor_ui, classic_ui + anchor_ui, 1)
settings.write_text(text)

# Preserve the choice across in-place app replacement if the shell installer is
# present in this build.
shell = Path("Tools/patch_vibecontainers_shell_compat.py")
if shell.exists():
    text = shell.read_text()
    old = '            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified\n            finalNewApp.autoSaveDisabled = false'
    new = '            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified\n            finalNewApp.classicMode = appToReplace.appInfo.classicMode\n            finalNewApp.autoSaveDisabled = false'
    if new not in text and old in text:
        shell.write_text(text.replace(old, new, 1))

checks = {
    h: ["classicMode", "defaultClassicMode"],
    m: ["LCGetDefaultClassicMode", "LCClassicModeCache", "self.classicMode = YES"],
    model: ["uiClassicMode", "classicMode != 0", "jitLaunch(appName: String, classicMode: UInt)", "launchToGuestApp(withClassicMode: classicMode)"],
    shared_h: ["launchToGuestAppWithClassicMode"],
    shared_m: ["FBSOpenApplicationOptionKeyActivateAsClassic", "launchToGuestAppWithClassicMode"],
    settings: ["uiClassicMode", "Classic Mode is required for 32-bit apps"],
}
for path, needles in checks.items():
    content = path.read_text()
    for needle in needles:
        if needle not in content:
            raise SystemExit(f"{path}: missing Classic Mode marker: {needle}")

print("FlekDeck Classic Mode restored on the single-process path; Parallel/App Switcher preserved")
