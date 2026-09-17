#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    source = path.read_text()
    if new in source:
        return
    if old not in source:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(source.replace(old, new, 1))


# Keep FlekDeck's newer bootstrap and replace only its legacy ARM32 handoff.
bootstrap = Path("LiveContainer/LCBootstrap.m")
source = bootstrap.read_text()
if "extern char **environ;" not in source:
    source = source.replace(
        '#include <mach-o/ldsyms.h>\n\nstatic int (*appMain)(int, char**);',
        '#include <mach-o/ldsyms.h>\n\nextern char **environ;\nstatic int (*appMain)(int, char**, char**);',
        1,
    )
else:
    source = source.replace(
        'static int (*appMain)(int, char**);',
        'static int (*appMain)(int, char**, char**);',
        1,
    )
bootstrap.write_text(source)

replace_once(
    bootstrap,
    '''    const char *appExecPath = appBundle.executablePath.fileSystemRepresentation;\n    *path = appExecPath;\n    overwriteExecPath(appExecPath);''',
    '''    const char *appExecPath = appBundle.executablePath.fileSystemRepresentation;\n    NSString *emulatorLauncherPath = nil;\n    NSString *emulatorEntrySymbol = nil;\n    *path = appExecPath;\n    overwriteExecPath(appExecPath);''',
    "emulator loader state",
)

old_32 = '''#if is32BitSupported\n    bool is32bit = [guestAppInfo[@"is32bit"] boolValue];\n    if(is32bit) {\n        if (!isJitEnabled) {\n            return @"JIT is required to run 32-bit apps.";\n        }\n        \n        NSString *selected32BitLayer = [lcUserDefaults stringForKey:@"selected32BitLayer"];\n        if(!selected32BitLayer || [selected32BitLayer length] == 0) {\n            appError = @"No 32-bit translation layer installed";\n            NSLog(@"[LCBootstrap] %@", appError);\n            *path = oldPath;\n            return appError;\n        }\n        NSBundle *selected32bitLayerBundle = [NSBundle bundleWithPath:[docPath stringByAppendingPathComponent:selected32BitLayer]]; //TODO make it user friendly;\n        if(!selected32bitLayerBundle) {\n            appError = @"The specified LiveExec32.app path is not found";\n            NSLog(@"[LCBootstrap] %@", appError);\n            *path = oldPath;\n            return appError;\n        }\n        // maybe need to save selected32bitLayerBundle to static variable?\n        appExecPath = strdup(selected32bitLayerBundle.executablePath.UTF8String);\n    }\n#endif'''
new_32 = '''#if is32BitSupported\n    bool is32bit = [guestAppInfo[@"is32bit"] boolValue];\n    if(is32bit) {\n        if (!isJitEnabled) {\n            return @"JIT is required to run 32-bit apps.";\n        }\n\n        // Prefer an app-specific emulator, then the shared default. Keep the old\n        // selected32BitLayer key as a migration fallback for existing FlekDeck installs.\n        NSString *selected32BitLayer = guestAppInfo[@"selected32BitEmulator"];\n        if(selected32BitLayer.length == 0) {\n            selected32BitLayer = [lcSharedDefaults stringForKey:@"LCSelected32BitEmulator"];\n        }\n        if(selected32BitLayer.length == 0) {\n            selected32BitLayer = [lcUserDefaults stringForKey:@"selected32BitLayer"];\n        }\n        if(selected32BitLayer.length == 0) {\n            selected32BitLayer = @"LiveExec32.app";\n        }\n        selected32BitLayer = selected32BitLayer.lastPathComponent;\n\n        NSMutableArray<NSString *> *runtimeCandidates = [NSMutableArray array];\n        [runtimeCandidates addObject:[docPath stringByAppendingPathComponent:[@"Applications" stringByAppendingPathComponent:selected32BitLayer]]];\n        [runtimeCandidates addObject:[docPath stringByAppendingPathComponent:selected32BitLayer]];\n\n        NSURL *runtimeGroupRoot = [LCSharedUtils appGroupPath];\n        if(runtimeGroupRoot) {\n            NSString *groupRuntime = [[runtimeGroupRoot.path stringByAppendingPathComponent:@"LiveContainer/Applications"] stringByAppendingPathComponent:selected32BitLayer];\n            [runtimeCandidates addObject:groupRuntime];\n        }\n\n        NSBundle *selected32bitLayerBundle = nil;\n        for(NSString *candidate in runtimeCandidates) {\n            selected32bitLayerBundle = [NSBundle bundleWithPath:candidate];\n            if(selected32bitLayerBundle) break;\n        }\n        if(!selected32bitLayerBundle) {\n            appError = [NSString stringWithFormat:@"The selected 32-bit runtime %@ was not found", selected32BitLayer];\n            NSLog(@"[LCBootstrap] %@", appError);\n            *path = oldPath;\n            return appError;\n        }\n        if(![selected32bitLayerBundle.infoDictionary[@"LC32BitTranslationLayer"] boolValue]) {\n            appError = @"The selected app is not a valid LiveExec32 translation layer";\n            NSLog(@"[LCBootstrap] %@", appError);\n            *path = oldPath;\n            return appError;\n        }\n\n        emulatorLauncherPath = selected32bitLayerBundle.executablePath;\n        NSString *emulatorLoadPath = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorLoadPath"];\n        emulatorEntrySymbol = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorEntrySymbol"];\n        if(emulatorLoadPath.length > 0 && emulatorEntrySymbol.length > 0) {\n            NSString *resolvedLoadPath = [selected32bitLayerBundle.bundlePath stringByAppendingPathComponent:emulatorLoadPath];\n            if(![fm fileExistsAtPath:resolvedLoadPath]) {\n                appError = [NSString stringWithFormat:@"32-bit runtime load image is missing: %@", resolvedLoadPath];\n                NSLog(@"[LCBootstrap] %@", appError);\n                *path = oldPath;\n                return appError;\n            }\n            appExecPath = strdup(resolvedLoadPath.fileSystemRepresentation);\n            overwriteExecPath(emulatorLauncherPath.fileSystemRepresentation);\n        } else {\n            // Compatibility fallback for older LiveExec32 bundles.\n            appExecPath = strdup(selected32bitLayerBundle.executablePath.fileSystemRepresentation);\n            overwriteExecPath(appExecPath);\n        }\n    }\n#endif'''
replace_once(bootstrap, old_32, new_32, "32-bit runtime selection")

replace_once(
    bootstrap,
    '''    __block void *appHandle = 0;\n    void (^dlopenBlock)(void) = ^{\n        appHandle = dlopen_nolock(appExecPath, RTLD_LAZY|RTLD_GLOBAL|RTLD_FIRST);\n    };''',
    '''    __block void *appHandle = 0;\n    int appDlopenFlags = (is32bit && emulatorEntrySymbol.length > 0)\n        ? (RTLD_NOW | RTLD_GLOBAL)\n        : (RTLD_LAZY | RTLD_GLOBAL | RTLD_FIRST);\n    void (^dlopenBlock)(void) = ^{\n        appHandle = dlopen_nolock(appExecPath, appDlopenFlags);\n    };''',
    "32-bit dlopen mode",
)

replace_once(
    bootstrap,
    '''    // Find main()\n    appMain = getAppEntryPoint(appHandle);\n    if (!appMain) {\n        appError = @"Could not find the main entry point";\n        NSLog(@"[LCBootstrap] %@", appError);\n        *path = oldPath;\n        return appError;\n    }''',
    '''    // Find the exported LiveExec32 entry point for ARM32 guests, or normal main().\n    if(is32bit && emulatorEntrySymbol.length > 0) {\n        dlerror();\n        appMain = (int (*)(int, char **, char **))dlsym(appHandle, emulatorEntrySymbol.UTF8String);\n        const char *entryError = dlerror();\n        if(entryError != NULL) {\n            appError = [NSString stringWithFormat:@"Could not resolve 32-bit runtime entry point %@: %s", emulatorEntrySymbol, entryError];\n            NSLog(@"[LCBootstrap] %@", appError);\n            *path = oldPath;\n            return appError;\n        }\n    } else {\n        appMain = (int (*)(int, char **, char **))getAppEntryPoint(appHandle);\n    }\n    if (!appMain) {\n        appError = @"Could not find the main entry point";\n        NSLog(@"[LCBootstrap] %@", appError);\n        *path = oldPath;\n        return appError;\n    }''',
    "runtime entry point",
)

replace_once(
    bootstrap,
    '''        argv[0] = (char *)appExecPath;\n        ret = appMain(argc, argv);''',
    '''        argv[0] = (char *)appExecPath;\n        ret = appMain(argc, argv, environ);''',
    "normal main environment",
)
replace_once(
    bootstrap,
    '''    } else {\n        char *argv32[] = {(char*)appExecPath, (char*)*path, NULL};\n        ret = appMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32);\n    }''',
    '''    } else {\n        const char *emulatorArgv0 = emulatorLauncherPath.length > 0\n            ? emulatorLauncherPath.fileSystemRepresentation\n            : appExecPath;\n        char *argv32[] = {(char*)emulatorArgv0, (char*)*path, NULL};\n        ret = appMain(sizeof(argv32)/sizeof(*argv32) - 1, argv32, environ);\n    }''',
    "ARM32 emulator argv",
)

# Seed the embedded, validated runtime into Documents/Applications and select it by default.
app = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift")
source = app.read_text()
marker = '    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate\n'
seed_code = '''    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate\n\n    private static let bundled32BitRuntimeName = "LiveExec32.app"\n    private static let bundled32BitRuntimeCommit = "3f0390e1b2725a2d3c9ab6f3976650a5a295ffba"\n    private static let bundled32BitRuntimeRevision = "89"\n\n    private static func seedBundled32BitRuntime(using fm: FileManager) throws {\n        let bundledURL = Bundle.main.bundleURL.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)\n        guard fm.fileExists(atPath: bundledURL.path) else { return }\n\n        let bundledInfoURL = bundledURL.appendingPathComponent("Info.plist")\n        guard let bundledInfo = NSDictionary(contentsOf: bundledInfoURL),\n              bundledInfo["LC32BitTranslationLayer"] as? Bool == true,\n              bundledInfo["LCBundledSourceCommit"] as? String == bundled32BitRuntimeCommit,\n              bundledInfo["LCBundledBuildRevision"] as? String == bundled32BitRuntimeRevision else {\n            NSLog("[FlekDeck/LC32] Embedded LiveExec32 metadata is invalid or stale")\n            return\n        }\n\n        try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)\n        let installedURL = LCPath.bundlePath.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)\n        let installedInfo = NSDictionary(contentsOf: installedURL.appendingPathComponent("Info.plist"))\n        let installedCommit = installedInfo?["LCBundledSourceCommit"] as? String\n        let installedRevision = installedInfo?["LCBundledBuildRevision"] as? String\n        if installedCommit != bundled32BitRuntimeCommit || installedRevision != bundled32BitRuntimeRevision {\n            if fm.fileExists(atPath: installedURL.path) {\n                try fm.removeItem(at: installedURL)\n            }\n            try fm.copyItem(at: bundledURL, to: installedURL)\n\n            // Keep the runtime out of the normal app list. It is an implementation\n            // detail, not a user-launchable guest.\n            let runtimeAppInfo: [String: Any] = [\n                "isHidden": true,\n                "isLocked": true,\n                "dontSign": true\n            ]\n            let runtimeAppInfoData = try PropertyListSerialization.data(\n                fromPropertyList: runtimeAppInfo, format: .binary, options: 0\n            )\n            try runtimeAppInfoData.write(to: installedURL.appendingPathComponent("LCAppInfo.plist"))\n            NSLog("[FlekDeck/LC32] Installed bundled LiveExec32 revision %@", bundled32BitRuntimeRevision)\n        }\n\n        let defaults = LCUtils.appGroupUserDefault\n        if (defaults.string(forKey: "LCSelected32BitEmulator") ?? "").isEmpty {\n            defaults.set(bundled32BitRuntimeName, forKey: "LCSelected32BitEmulator")\n        }\n    }\n'''
if "seedBundled32BitRuntime" not in source:
    if marker not in source:
        raise SystemExit(f"{app}: app delegate anchor missing")
    source = source.replace(marker, seed_code, 1)

init_anchor = '''        do {\n            // load apps'''
if "try Self.seedBundled32BitRuntime(using: fm)" not in source:
    if init_anchor not in source:
        raise SystemExit(f"{app}: init load anchor missing")
    source = source.replace(
        init_anchor,
        '''        do {\n            try Self.seedBundled32BitRuntime(using: fm)\n\n            // load apps''',
        1,
    )
app.write_text(source)

# The menu existed, but FlekDeck hid it for shared/app-group guests. LCContainer.filesAppURL
# already resolves both private and shared storage, so expose the action for either.
banner = Path("LiveContainerSwiftUI/Views/AppList/LCAppBanner/LCAppBannerViewController.swift")
source = banner.read_text()
source = source.replace(
    'if !model.uiIsShared, model.uiSelectedContainer != nil {',
    'if model.uiSelectedContainer != nil {',
    1,
)
if 'if !model.uiIsShared, model.uiSelectedContainer != nil {' in source:
    raise SystemExit(f"{banner}: shared-container menu guard still present")
banner.write_text(source)

# Migrate the visible developer field to the new key while retaining the bootstrap fallback.
settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
source = settings.read_text()
source = source.replace(
    '@AppStorage("selected32BitLayer", store: LCUtils.appGroupUserDefault) var liveExec32Path : String = ""',
    '@AppStorage("LCSelected32BitEmulator", store: LCUtils.appGroupUserDefault) var liveExec32Path : String = "LiveExec32.app"',
    1,
)
source = source.replace('Text("LiveExec32 .app path")', 'Text("32-bit Runtime")', 1)
settings.write_text(source)

# Sanity markers used by CI.
checks = {
    bootstrap: [
        'LCSelected32BitEmulator',
        'LC32BitEmulatorLoadPath',
        'LC32BitEmulatorEntrySymbol',
        'dlsym(appHandle, emulatorEntrySymbol.UTF8String)',
        'appMain(argc, argv, environ)',
    ],
    app: ['seedBundled32BitRuntime', 'bundled32BitRuntimeRevision = "89"'],
    banner: ['if model.uiSelectedContainer != nil {', 'container.filesAppURL'],
    settings: ['@AppStorage("LCSelected32BitEmulator"'],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: expected marker missing: {needle}")

print("FlekDeck LiveExec32 + Open Data Folder integration applied")
