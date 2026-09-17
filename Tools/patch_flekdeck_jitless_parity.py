#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


# Add a path-based entitlement reader while keeping the existing host helper.
h = Path("LiveContainer/LCMachOUtils.h")
replace_once(
    h,
    'NSString* getLCEntitlementXML(void);',
    'NSString* getExecutableEntitlementXML(NSString* executablePath);\nNSString* getLCEntitlementXML(void);',
    "path entitlement declaration",
)

m = Path("LiveContainer/LCMachOUtils.m")
replace_once(
    m,
    '''NSString* getLCEntitlementXML(void) {
    __block NSString* ans = @"Failed to find main executable?";
    // it seems the debug build messes the code signature region up, so we search the executable file on the disk instead.
    LCParseMachO(NSBundle.mainBundle.executablePath.UTF8String, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        ans = getEntitlementXML(header, 0);
    });
    return ans;
}''',
    '''NSString* getExecutableEntitlementXML(NSString* executablePath) {
    if(executablePath.length == 0) return nil;
    __block NSString* ans = @"Failed to find executable?";
    LCParseMachO(executablePath.UTF8String, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        ans = getEntitlementXML(header, 0);
    });
    return ans;
}

NSString* getLCEntitlementXML(void) {
    // Keep the historical API for callers that only need the host executable.
    return getExecutableEntitlementXML(NSBundle.mainBundle.executablePath);
}''',
    "path entitlement implementation",
)

view = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift")
text = view.read_text()

if 'struct LCEntitlementView : View {\n    @State var isLiveProcess: Bool' not in text:
    text = text.replace(
        'struct LCEntitlementView : View {\n    @State var loaded = false',
        'struct LCEntitlementView : View {\n    @State var isLiveProcess: Bool\n    @State var loaded = false',
        1,
    )

text = text.replace(
    '''                    HStack {
                        Text("lc.jitlessDiag.bundleId".loc)
                        Spacer()
                        Text(Bundle.main.bundleIdentifier ?? "lc.common.unknown".loc)
                            .foregroundStyle(entitlementReadSuccess && teamId != nil ? (isBundleIdCorrect ? .green : .red): .gray)
                            .textSelection(.enabled)
                    }
                    
                    if entitlementReadSuccess {''',
    '''                    if !isLiveProcess {
                        HStack {
                            Text("lc.jitlessDiag.bundleId".loc)
                            Spacer()
                            Text(Bundle.main.bundleIdentifier ?? "lc.common.unknown".loc)
                                .foregroundStyle(entitlementReadSuccess && teamId != nil ? (isBundleIdCorrect ? .green : .red): .gray)
                                .textSelection(.enabled)
                        }
                    }
                    
                    if entitlementReadSuccess {''',
    1,
)
text = text.replace(
    '                        if !isBundleIdCorrect && teamId != nil {',
    '                        if !isLiveProcess && !isBundleIdCorrect && teamId != nil {',
    1,
)
text = text.replace(
    '.navigationTitle("lc.jielessDiag.entitlement".loc)',
    '.navigationTitle(isLiveProcess ? "LiveProcess Entitlements" : "FlekDeck Entitlements")',
    1,
)
text = text.replace(
    '''        guard let entitlementXML = getLCEntitlementXML() else {
            entitlementContent = "Failed to load entitlement."
            return
        }''',
    '''        let executablePath: String?
        if isLiveProcess {
            executablePath = Bundle.main.builtInPlugInsURL?.appendingPathComponent("LiveProcess.appex/LiveProcess").path
            if let executablePath, !FileManager.default.fileExists(atPath: executablePath) {
                entitlementContent = "LiveProcess is not installed."
                return
            }
        } else {
            executablePath = Bundle.main.executablePath
        }
        guard let entitlementXML = getExecutableEntitlementXML(executablePath) else {
            entitlementContent = "Failed to load entitlement."
            return
        }''',
    1,
)

if '@State var appGroupIdColor : Color = .gray' not in text:
    text = text.replace(
        '@State var appGroupId = "Unknown"\n',
        '@State var appGroupId = "Unknown"\n    @State var appGroupIdColor : Color = .gray\n',
        1,
    )
text = text.replace(
    '.foregroundStyle(appGroupId == "Unknown" ? .red : .green)',
    '.foregroundStyle(appGroupIdColor)',
    1,
)
text = text.replace(
    '''                    NavigationLink {
                        LCEntitlementView()
                    } label: {
                        Text("lc.jielessDiag.entitlement".loc)
                    }''',
    '''                    NavigationLink {
                        LCEntitlementView(isLiveProcess: false)
                    } label: {
                        Text("FlekDeck Entitlements")
                    }
                    if sharedModel.multiLCStatus == 0 {
                        NavigationLink {
                            LCEntitlementView(isLiveProcess: true)
                        } label: {
                            Text("LiveProcess Entitlements")
                        }
                    }''',
    1,
)

old_appear = '''    func onAppear() {
        appGroupId = LCSharedUtils.appGroupID() ?? "lc.common.unknown".loc
        store = LCUtils.store()
        appGroupAccessible = LCSharedUtils.appGroupPath() != nil'''
new_appear = '''    func onAppear() {
        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "com.apple.developer.team-identifier" as CFString, nil),
              let teamId = value.takeRetainedValue() as? String else {
            errorInfo = "Failed to read com.apple.developer.team-identifier"
            errorShow = true
            return
        }
        expectedTeamId = teamId

        if let fetchedAppGroupId = LCSharedUtils.appGroupID(), fetchedAppGroupId != "Unknown" {
            appGroupId = fetchedAppGroupId
            if UserDefaults.sideStoreExist() && fetchedAppGroupId != "group.com.SideStore.SideStore." + teamId {
                appGroupIdColor = .orange
            } else {
                appGroupIdColor = .green
            }
        } else {
            appGroupId = "lc.common.unknown".loc
            appGroupIdColor = .red
        }
        store = LCUtils.store()
        appGroupAccessible = LCSharedUtils.appGroupPath() != nil'''
if new_appear not in text:
    if old_appear not in text:
        raise SystemExit(f"{view}: diagnose onAppear anchor missing")
    text = text.replace(old_appear, new_appear, 1)

# Remove the now-duplicate team-id probe later in Flek's original onAppear.
duplicate = '''        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "com.apple.developer.team-identifier" as CFString, nil), let teamId = value.takeRetainedValue() as? String else {
            errorInfo = "Failed to read com.apple.developer.team-identifier"
            errorShow = true
            return
        }
        expectedTeamId = teamId
        
        loaded = true'''
if duplicate in text:
    text = text.replace(duplicate, '        loaded = true', 1)

view.write_text(text)

for path, needles in {
    h: ["getExecutableEntitlementXML"],
    m: ["getExecutableEntitlementXML(NSString* executablePath)"],
    view: ["LiveProcess Entitlements", "LCEntitlementView(isLiveProcess: true)", "appGroupIdColor"],
}.items():
    content = path.read_text()
    for needle in needles:
        if needle not in content:
            raise SystemExit(f"{path}: missing JIT-less parity marker {needle}")

print("FlekDeck JIT-less diagnostics now include LiveProcess entitlement inspection")
