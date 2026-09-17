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
# ARM32 translator discovery. Keep translators out of the normal Home list, but
# make them available to the global and per-app runtime pickers.
# ---------------------------------------------------------------------------
shared = Path("LiveContainerSwiftUI/Utilities/Shared.swift")
replace_once(
    shared,
    '    @Published var apps : [LCAppModel] = []\n    @Published var hiddenApps : [LCAppModel] = []',
    '    @Published var apps : [LCAppModel] = []\n#if is32BitSupported\n    @Published var arm32EmuApps : [LCAppModel] = []\n#endif\n    @Published var hiddenApps : [LCAppModel] = []',
    "ARM32 translator model list",
)

app_info_h = Path("LiveContainerSwiftUI/Models/LCAppInfo.h")
replace_once(
    app_info_h,
    '#if is32BitSupported\n@property bool is32bit;\n#endif',
    '#if is32BitSupported\n@property bool is32bit;\n@property (nonatomic, strong) NSString* selected32BitEmulator;\n@property(readonly) bool is32bitEmulator;\n#endif',
    "ARM32 app-info properties",
)

app_info_m = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
replace_once(
    app_info_m,
    '''#if is32BitSupported
- (bool)is32bit {
    if(_info[@"is32bit"] != nil) {
        return [_info[@"is32bit"] boolValue];
    } else {
        return NO;
    }
}
- (void)setIs32bit:(bool)is32bit {
    _info[@"is32bit"] = [NSNumber numberWithBool:is32bit];
    [self save];
    
}
#endif''',
    '''#if is32BitSupported
- (bool)is32bit {
    if(_info[@"is32bit"] != nil) {
        return [_info[@"is32bit"] boolValue];
    } else {
        return NO;
    }
}
- (void)setIs32bit:(bool)is32bit {
    _info[@"is32bit"] = [NSNumber numberWithBool:is32bit];
    [self save];
}
- (NSString *)selected32BitEmulator {
    return _info[@"selected32BitEmulator"];
}
- (void)setSelected32BitEmulator:(NSString *)selected32BitEmulator {
    if(selected32BitEmulator.length > 0) {
        _info[@"selected32BitEmulator"] = selected32BitEmulator;
    } else {
        [_info removeObjectForKey:@"selected32BitEmulator"];
    }
    [self save];
}
- (bool)is32bitEmulator {
    return [_infoPlist[@"LC32BitTranslationLayer"] boolValue];
}
#endif''',
    "ARM32 translator metadata accessors",
)

app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    app_model,
    '''#if is32BitSupported
    @Published var uiIs32bit : Bool
#endif''',
    '''#if is32BitSupported
    @Published var uiIs32bit : Bool
    @Published var uiIs32bitEmulator : Bool
    @Published var uiSelected32BitEmulator : String {
        didSet { appInfo.selected32BitEmulator = uiSelected32BitEmulator }
    }
#endif''',
    "ARM32 app-model state",
)
replace_once(
    app_model,
    '''#if is32BitSupported
        self.uiIs32bit = appInfo.is32bit
#endif''',
    '''#if is32BitSupported
        self.uiIs32bit = appInfo.is32bit
        self.uiIs32bitEmulator = appInfo.is32bitEmulator
        self.uiSelected32BitEmulator = appInfo.selected32BitEmulator ?? ""
#endif''',
    "ARM32 app-model initialization",
)

app = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift")
replace_once(
    app,
    '        var tempApps: [LCAppModel] = []\n        var tempHiddenApps: [LCAppModel] = []',
    '        var tempApps: [LCAppModel] = []\n#if is32BitSupported\n        var tempArm32EmuApps: [LCAppModel] = []\n#endif\n        var tempHiddenApps: [LCAppModel] = []',
    "ARM32 translator startup accumulator",
)
text = app.read_text()
needle_private = '''                if newApp.isHidden {
                    tempHiddenApps.append(LCAppModel(appInfo: newApp))
                } else {
                    tempApps.append(LCAppModel(appInfo: newApp))
                    tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
                }'''
replacement_private = needle_private + '''
#if is32BitSupported
                if newApp.is32bitEmulator {
                    tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                }
#endif'''
if replacement_private not in text:
    if text.count(needle_private) < 1:
        raise SystemExit(f"{app}: private app-load anchor missing")
    text = text.replace(needle_private, replacement_private, 1)
needle_shared = '''                    if newApp.isHidden {
                        tempHiddenApps.append(LCAppModel(appInfo: newApp))
                    } else {
                        tempApps.append(LCAppModel(appInfo: newApp))
                        tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
                    }'''
replacement_shared = needle_shared + '''
#if is32BitSupported
                    if newApp.is32bitEmulator {
                        tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                    }
#endif'''
if replacement_shared not in text:
    if needle_shared not in text:
        raise SystemExit(f"{app}: shared app-load anchor missing")
    text = text.replace(needle_shared, replacement_shared, 1)
assignment = '        DataManager.shared.model.apps = tempApps\n        DataManager.shared.model.hiddenApps = tempHiddenApps'
assignment_new = '        DataManager.shared.model.apps = tempApps\n#if is32BitSupported\n        DataManager.shared.model.arm32EmuApps = tempArm32EmuApps\n#endif\n        DataManager.shared.model.hiddenApps = tempHiddenApps'
if assignment_new not in text:
    if assignment not in text:
        raise SystemExit(f"{app}: model assignment anchor missing")
    text = text.replace(assignment, assignment_new, 1)
app.write_text(text)

# ---------------------------------------------------------------------------
# Per-app settings. This adapter is only invoked by the dedicated ARM32 build,
# so keep the generated Swift structurally simple instead of splitting a chained
# Toggle modifier across #if directives.
# ---------------------------------------------------------------------------
app_settings = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
replace_once(
    app_settings,
    '''                Toggle(isOn: $model.uiIsJITNeeded) {
                    Text("lc.appSettings.launchWithJit".loc)
                }
                if #available(iOS 26.0, *), model.uiIsJITNeeded {''',
    '''                Toggle(isOn: $model.uiIsJITNeeded) {
                    Text("lc.appSettings.launchWithJit".loc)
                }
                .disabled(model.uiIs32bit)
                if #available(iOS 26.0, *), model.uiIsJITNeeded, !model.uiIs32bit {''',
    "ARM32 JIT control gating",
)
text = app_settings.read_text()
script_end = '''                    }
                }
            } footer: {'''
translator_picker = '''                    }
                }
                if model.uiIs32bit {
                    Picker(selection: $model.uiSelected32BitEmulator) {
                        Text("lc.common.default".loc).tag("")
                        ForEach(sharedModel.arm32EmuApps, id: \\.self) { app in
                            Text(app.appInfo.displayName()).tag(app.appInfo.relativeBundlePath ?? "")
                        }
                    } label: {
                        Text("32-bit Runtime")
                    }
                }
            } footer: {'''
if translator_picker not in text:
    if script_end not in text:
        raise SystemExit(f"{app_settings}: translator picker anchor missing")
    text = text.replace(script_end, translator_picker, 1)
app_settings.write_text(text)

# ---------------------------------------------------------------------------
# Global Settings: keep Flek's category architecture, fill only missing controls.
# ---------------------------------------------------------------------------
settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
text = settings.read_text()
jit_end = '''                
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.jit".loc).font(.headline) } }
    }'''
jit_new = '''
#if is32BitSupported
                Section {
                    Picker(selection: $liveExec32Path) {
                        Text("Bundled LiveExec32 (r89)").tag("LiveExec32.app")
                        ForEach(sharedModel.arm32EmuApps.filter { $0.appInfo.relativeBundlePath != "LiveExec32.app" }, id: \\.self) { app in
                            Text(app.appInfo.displayName()).tag(app.appInfo.relativeBundlePath ?? "")
                        }
                    } label: {
                        Text("Default 32-bit Runtime")
                    }
                    HStack {
                        Text("Runtime Revision")
                        Spacer()
                        Text("89")
                            .foregroundStyle(.secondary)
                    }
                } footer: {
                    Text("Used for ARM32 apps. Per-app settings can override this selection.")
                }
#endif
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.jit".loc).font(.headline) } }
    }'''
if jit_new not in text:
    if jit_end not in text:
        raise SystemExit(f"{settings}: JIT page end anchor missing")
    text = text.replace(jit_end, jit_new, 1)

data_old = '''                Section {
                    NavigationLink {
                        LCDataManagementView()
                    } label: {
                        Text("lc.settings.dataManagement".loc)
                    }
                }'''
data_new = '''                Section {
                    if sharedModel.multiLCStatus != 2 {
                        NavigationLink {
                            LCStorageManagementView()
                        } label: {
                            Text("lc.settings.storageManagement".loc)
                        }
                    }
                    NavigationLink {
                        LCDataManagementView()
                    } label: {
                        Text("lc.settings.dataManagement".loc)
                    }
                    Button {
                        clearNotifications()
                    } label: {
                        Text("lc.settings.clearNotifications".loc)
                    }
                }'''
if data_new not in text:
    if data_old not in text:
        raise SystemExit(f"{settings}: data-management anchor missing")
    text = text.replace(data_old, data_new, 1)
settings.write_text(text)

# ---------------------------------------------------------------------------
# Open Data Folder: expose Flek's existing richer resolver for shared containers
# too, and surface a real error instead of silently doing nothing.
# ---------------------------------------------------------------------------
banner = Path("LiveContainerSwiftUI/Views/AppList/LCAppBanner/LCAppBannerViewController.swift")
text = banner.read_text().replace(
    'if !model.uiIsShared, model.uiSelectedContainer != nil {',
    'if model.uiSelectedContainer != nil {',
    1,
)
old_open = '''    private func openDataFolder() {
        guard let container = configuration.model.uiSelectedContainer,
              let url = container.filesAppURL else {
            return
        }
        UIApplication.shared.open(url)
    }'''
new_open = '''    private func openDataFolder() {
        guard let container = configuration.model.uiSelectedContainer else {
            showError("No data container is selected.")
            return
        }
        guard let url = container.filesAppURL else {
            showError("Unable to create a Files URL for this data container.")
            return
        }
        UIApplication.shared.open(url, options: [:]) { [weak self] success in
            guard !success else { return }
            DispatchQueue.main.async {
                self?.showError("Files could not open this data container.")
            }
        }
    }'''
if new_open not in text:
    if old_open not in text:
        raise SystemExit(f"{banner}: open-data-folder anchor missing")
    text = text.replace(old_open, new_open, 1)
banner.write_text(text)

# ---------------------------------------------------------------------------
# Crash report: expose LiveExec32's own log when it exists; keep Copy on iOS 15.
# ---------------------------------------------------------------------------
tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
replace_once(
    tab,
    '''                    ToolbarItem(placement: .topBarLeading) {
                        Button("lc.common.copy".loc, action: {
                            copyError()
                        })
                    }''',
    '''                    ToolbarItem(placement: .topBarLeading) {
                        if #available(iOS 16.0, *) {
                            if let log = UserDefaults.lcShared().url(forKey: "LC32BitTranslationLayerLogFile") {
                                ShareLink(item: log)
                            } else {
                                ShareLink(item: errorInfo)
                            }
                        } else {
                            Button("lc.common.copy".loc) { copyError() }
                        }
                    }''',
    "ARM32 crash-log sharing",
)

checks = {
    shared: ["arm32EmuApps"],
    app_info_h: ["selected32BitEmulator", "is32bitEmulator"],
    app_info_m: ["LC32BitTranslationLayer", "selected32BitEmulator"],
    app_model: ["uiSelected32BitEmulator", "uiIs32bitEmulator"],
    app: ["tempArm32EmuApps", "DataManager.shared.model.arm32EmuApps"],
    app_settings: ["32-bit Runtime", ".disabled(model.uiIs32bit)"],
    settings: ["Default 32-bit Runtime", "LCStorageManagementView()", "clearNotifications()"],
    banner: ["Files could not open this data container."],
    tab: ["LC32BitTranslationLayerLogFile", "ShareLink(item: log)"],
}
for path, needles in checks.items():
    value = path.read_text()
    for needle in needles:
        if needle not in value:
            raise SystemExit(f"{path}: missing parity marker: {needle}")

print("FlekDeck LiveContainer parity controls applied without replacing App Switcher/Parallel/PiP")
