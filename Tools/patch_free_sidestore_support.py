from pathlib import Path

HOST_ERROR = (
    "FlekDeck itself is missing get-task-allow. Free Apple IDs are supported: "
    "install or Refresh All in SideStore with LocalDevVPN connected so SideStore "
    "signs FlekDeck with your personal development profile, then reopen FlekDeck."
)

p = Path("SideStoreSupport/SideStoreHooks.m")
s = p.read_text()
s = s.replace(
    '+ (NSString*)hook_appbundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_appbundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    'https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json',
    'https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json'
)
p.write_text(s)

p = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
s = p.read_text()
if "FlekHostHasDevelopmentSigning" not in s:
    s = s.replace(
        "import Foundation\n",
        '''import Foundation\n\n@inline(__always)\nprivate func FlekHostHasDevelopmentSigning() -> Bool {\n    let task = SecTaskCreateFromSelf(nil)\n    guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil) else {\n        return false\n    }\n    return (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false\n}\n\nprivate let FlekHostDevelopmentSigningError = "__ERROR__"\n\n'''.replace("__ERROR__", HOST_ERROR.replace('"', '\\"')),
        1
    )

anchor = '''    func runApp(multitask: Bool? = nil, containerFolderName : String? = nil, bundleIdOverride : String? = nil, urlStr : String? = nil, forceJIT: Bool? = nil) async throws{\n        if isAppRunning {\n            return\n        }\n'''
if "flekIsBuiltInSideStore" not in s:
    replacement = '''    func runApp(multitask: Bool? = nil, containerFolderName : String? = nil, bundleIdOverride : String? = nil, urlStr : String? = nil, forceJIT: Bool? = nil) async throws{\n        if isAppRunning {\n            return\n        }\n\n        let flekIsBuiltInSideStore = bundleIdOverride == "builtinSideStore"\n        let flekWillUseJIT = forceJIT ?? appInfo.isJITNeeded\n        if !flekIsBuiltInSideStore && !flekWillUseJIT && !FlekHostHasDevelopmentSigning() {\n            throw FlekHostDevelopmentSigningError\n        }\n'''
    if anchor not in s:
        raise SystemExit("LCAppModel.runApp anchor not found")
    s = s.replace(anchor, replacement, 1)
p.write_text(s)

p = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift")
s = p.read_text()
anchor = '''    func testJITLessMode() {\n        if !certificateDataFound {\n'''
if "FlekDeck host does not have get-task-allow" not in s:
    replacement = '''    func testJITLessMode() {\n        let hostTask = SecTaskCreateFromSelf(nil)\n        guard let hostValue = SecTaskCopyValueForEntitlement(hostTask, "get-task-allow" as CFString, nil),\n              (hostValue.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {\n            errorInfo = "FlekDeck host does not have get-task-allow. Free Apple IDs are supported: install or Refresh All in SideStore with LocalDevVPN connected, then reopen FlekDeck."\n            errorShow = true\n            return\n        }\n\n        if !certificateDataFound {\n'''
    if anchor not in s:
        raise SystemExit("JIT-less diagnostic anchor not found")
    s = s.replace(anchor, replacement, 1)
p.write_text(s)

print("Applied free SideStore host-signing compatibility")
