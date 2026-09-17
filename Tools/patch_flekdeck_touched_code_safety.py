#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


# App Settings: user-facing alerts/importers must never force unwrap optional
# text, bundle metadata, or an optional container assembled from external storage.
settings = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
s = settings.read_text()
s = s.replace(
    'renameFolderInput.close(result: newText!)',
    'renameFolderInput.close(result: newText ?? "")'
)

create_anchor = '''        let fm = FileManager()\n        let dest : URL\n'''
create_replacement = '''        guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty else {\n            errorInfo = "This app does not have a valid bundle identifier."\n            errorShow = true\n            return\n        }\n        let fm = FileManager()\n        let dest : URL\n'''
if create_replacement not in s:
    if create_anchor not in s:
        raise SystemExit(f"{settings}: create-folder identifier anchor missing")
    s = s.replace(create_anchor, create_replacement, 1)
s = s.replace(
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: freeKeyChainGroup)',
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)',
    1
)

import_anchor = '''            guard url.startAccessingSecurityScopedResource() else {\n                errorInfo = "unable to access directory, startAccessingSecurityScopedResource returns false"\n                errorShow = true\n                return\n            }\n            let path = url.path\n'''
import_replacement = '''            guard url.startAccessingSecurityScopedResource() else {\n                errorInfo = "Unable to access the selected directory."\n                errorShow = true\n                return\n            }\n            defer { url.stopAccessingSecurityScopedResource() }\n            guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty else {\n                errorInfo = "This app does not have a valid bundle identifier."\n                errorShow = true\n                return\n            }\n            let path = url.path\n'''
if import_replacement not in s:
    if import_anchor not in s:
        raise SystemExit(f"{settings}: external-container access anchor missing")
    s = s.replace(import_anchor, import_replacement, 1)

# This occurrence is inside importDataStorage after the createFolder occurrence
# above was already replaced.
s = s.replace(
    'container!.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: freeKeyChainGroup)',
    'container!.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)',
    1
)

# Collapse the final optional container before using it. The construction paths
# above should always populate it, but malformed LCContainerInfo must be a visible
# error rather than an unexpected nil trap.
container_anchor = '''            model.uiContainers.append(container!)\n            appInfo.containers = model.uiContainers;\n            if model.uiSelectedContainer == nil {\n                model.uiSelectedContainer = container;\n            }\n'''
container_replacement = '''            guard let resolvedContainer = container else {\n                errorInfo = "Unable to create a data-container record for the selected directory."\n                errorShow = true\n                return\n            }\n            model.uiContainers.append(resolvedContainer)\n            appInfo.containers = model.uiContainers\n            if model.uiSelectedContainer == nil {\n                model.uiSelectedContainer = resolvedContainer\n            }\n'''
if container_replacement not in s:
    if container_anchor not in s:
        raise SystemExit(f"{settings}: external-container finalization anchor missing")
    s = s.replace(container_anchor, container_replacement, 1)

s = s.replace(
    '''    func getBundleId() -> String {\n        return model.appInfo.bundleIdentifier()!\n    }''',
    '''    func getBundleId() -> String {\n        return model.appInfo.bundleIdentifier() ?? ""\n    }'''
)

save_anchor = '''    func saveContainer(container: LCContainer) {\n        container.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: container.keychainGroupId)\n        appInfo.containers = model.uiContainers\n        model.objectWillChange.send()\n    }'''
save_replacement = '''    func saveContainer(container: LCContainer) {\n        guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty else {\n            errorInfo = "This app does not have a valid bundle identifier."\n            errorShow = true\n            return\n        }\n        container.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: container.keychainGroupId)\n        appInfo.containers = model.uiContainers\n        model.objectWillChange.send()\n    }'''
if save_replacement not in s:
    if save_anchor not in s:
        raise SystemExit(f"{settings}: save-container identifier anchor missing")
    s = s.replace(save_anchor, save_replacement, 1)

add_anchor = '''    func addContainers(containers: Set<String>) {\n        if containers.count + model.uiContainers.count > SharedModel.keychainAccessGroupCount {'''
add_replacement = '''    func addContainers(containers: Set<String>) {\n        guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty else {\n            errorInfo = "This app does not have a valid bundle identifier."\n            errorShow = true\n            return\n        }\n        if containers.count + model.uiContainers.count > SharedModel.keychainAccessGroupCount {'''
if add_replacement not in s:
    if add_anchor not in s:
        raise SystemExit(f"{settings}: add-containers identifier anchor missing")
    s = s.replace(add_anchor, add_replacement, 1)
s = s.replace(
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: freeKeyChainGroup)',
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)'
)
settings.write_text(s)


# Launch model: malformed guest metadata/URL state returns a real error instead of
# force-unwrapping. This does not alter the main-derived App Switcher decision.
model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
m = model.read_text()
run_container_anchor = '''        if uiContainers.isEmpty {\n            let newName = NSUUID().uuidString\n            let newContainer = LCContainer(folderName: newName, name: newName, isShared: uiIsShared)'''
run_container_replacement = '''        if uiContainers.isEmpty {\n            guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty else {\n                throw "The selected app does not have a valid bundle identifier."\n            }\n            let newName = NSUUID().uuidString\n            let newContainer = LCContainer(folderName: newName, name: newName, isShared: uiIsShared)'''
if run_container_replacement not in m:
    if run_container_anchor not in m:
        raise SystemExit(f"{model}: new-container identifier anchor missing")
    m = m.replace(run_container_anchor, run_container_replacement, 1)
m = m.replace(
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: Int.random(in: 0..<SharedModel.keychainAccessGroupCount))',
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: Int.random(in: 0..<SharedModel.keychainAccessGroupCount))',
    1
)
url_anchor = '''            if await UIApplication.shared.canOpenURL(openURLComp.url!) {\n                await UIApplication.shared.open(openURLComp.url!)\n                return\n            }'''
url_replacement = '''            if let openURL = openURLComp.url, await UIApplication.shared.canOpenURL(openURL) {\n                await UIApplication.shared.open(openURL)\n                return\n            }'''
if url_replacement not in m:
    if url_anchor not in m:
        raise SystemExit(f"{model}: cross-container URL anchor missing")
    m = m.replace(url_anchor, url_replacement, 1)
metal_anchor = '''            if #available(iOS 26.0, *), FileManager.default.fileExists(atPath: "\\(appInfo.bundlePath()!)/Frameworks/MetalANGLE.framework/MetalANGLE") {\n                let fileContents = "\\(appInfo.bundlePath()!)/Frameworks/MetalANGLE.framework/MetalANGLE".data(using: .utf8)'''
metal_replacement = '''            if #available(iOS 26.0, *),\n               let bundlePath = appInfo.bundlePath(),\n               FileManager.default.fileExists(atPath: "\\(bundlePath)/Frameworks/MetalANGLE.framework/MetalANGLE") {\n                let fileContents = "\\(bundlePath)/Frameworks/MetalANGLE.framework/MetalANGLE".data(using: .utf8)'''
if metal_replacement not in m:
    if metal_anchor not in m:
        raise SystemExit(f"{model}: MetalANGLE path anchor missing")
    m = m.replace(metal_anchor, metal_replacement, 1)
model.write_text(m)


# Home/list visibility bookkeeping: malformed URL-scheme metadata must not crash
# when an app is hidden or unhidden.
app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
l = app_list.read_text()
unsafe = 'app.appInfo.urlSchemes() as! [Any]'
safe = '((app.appInfo.urlSchemes() as? [String]) ?? []).map { $0 as Any }'
if unsafe in l:
    l = l.replace(unsafe, safe)
app_list.write_text(l)


# JIT-less refresh should never keep stale certificate/result values from the
# previous refresh when the next entitlement/certificate read fails.
diag = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift")
d = diag.read_text()
diag_anchor = '''    func onAppear() {\n        let task = SecTaskCreateFromSelf(nil)'''
diag_replacement = '''    func onAppear() {\n        appGroupId = "Unknown"\n        appGroupIdColor = .gray\n        appGroupAccessible = false\n        certificateDataFound = false\n        certificatePasswordFound = false\n        certTeamId = nil\n        expectedTeamId = nil\n        certLastUpdateDateStr = nil\n        certificateStatus = -1\n        certificateValidateUntil = nil\n\n        let task = SecTaskCreateFromSelf(nil)'''
if diag_replacement not in d:
    if diag_anchor not in d:
        raise SystemExit(f"{diag}: refresh-reset anchor missing")
    d = d.replace(diag_anchor, diag_replacement, 1)
diag.write_text(d)


checks = {
    settings: [
        'renameFolderInput.close(result: newText ?? "")',
        'defer { url.stopAccessingSecurityScopedResource() }',
        'guard let resolvedContainer = container else',
        'return model.appInfo.bundleIdentifier() ?? ""',
    ],
    model: [
        'throw "The selected app does not have a valid bundle identifier."',
        'if let openURL = openURLComp.url',
        'let bundlePath = appInfo.bundlePath()',
    ],
    app_list: ['urlSchemes() as? [String]'],
    diag: ['certTeamId = nil', 'certificateValidateUntil = nil'],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: safety marker missing: {needle}")

# Explicitly reject the crash-prone forms this sweep owns.
for path, needle in [
    (settings, 'renameFolderInput.close(result: newText!)'),
    (model, 'canOpenURL(openURLComp.url!)'),
    (model, 'appInfo.bundlePath()!)/Frameworks/MetalANGLE'),
    (app_list, 'app.appInfo.urlSchemes() as! [Any]'),
]:
    if needle in path.read_text():
        raise SystemExit(f"{path}: unsafe form remains: {needle}")

print("FlekDeck touched-code safety sweep applied")
