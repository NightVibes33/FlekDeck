#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
s = path.read_text()

# The generic touched-code sweep already handles most optional metadata. This
# final pass owns the external-container sequence specifically: never dereference
# the optional LCContainer before it has been resolved.
s = s.replace(
    'renameFolderInput.close(result: newText!)',
    'renameFolderInput.close(result: newText ?? "")'
)

# Ensure createFolder has a stable bundle identifier before writing container info.
anchor = '''    func createFolder() async {\n        let newName = NSUUID().uuidString\n'''
replacement = '''    func createFolder() async {\n        guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty, appIdentifier != "Unknown" else {\n            errorInfo = "This app does not have a valid bundle identifier."\n            errorShow = true\n            return\n        }\n        let newName = NSUUID().uuidString\n'''
if replacement not in s:
    if anchor in s:
        s = s.replace(anchor, replacement, 1)
    elif 'func createFolder() async' not in s or 'guard let appIdentifier = appInfo.bundleIdentifier()' not in s:
        raise SystemExit(f"{path}: createFolder bundle-id guard anchor missing")
s = s.replace(
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: freeKeyChainGroup)',
    'newContainer.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)'
)

# Security-scoped access must be balanced, and the app ID is needed before any
# container metadata is written.
access_old = '''            guard url.startAccessingSecurityScopedResource() else {\n                errorInfo = "unable to access directory, startAccessingSecurityScopedResource returns false"\n                errorShow = true\n                return\n            }\n            let path = url.path\n'''
access_new = '''            guard url.startAccessingSecurityScopedResource() else {\n                errorInfo = "Unable to access the selected directory."\n                errorShow = true\n                return\n            }\n            defer { url.stopAccessingSecurityScopedResource() }\n            guard let appIdentifier = appInfo.bundleIdentifier(), !appIdentifier.isEmpty, appIdentifier != "Unknown" else {\n                errorInfo = "This app does not have a valid bundle identifier."\n                errorShow = true\n                return\n            }\n            let path = url.path\n'''
if access_new not in s:
    if access_old not in s:
        # The broad sweep may already have installed the defer/guard.
        if 'defer { url.stopAccessingSecurityScopedResource() }' not in s:
            raise SystemExit(f"{path}: security-scoped access anchor missing")
    else:
        s = s.replace(access_old, access_new, 1)

unsafe_block = '''                    if container!.bookmarkResolved {\n                        container!.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)\n                    }'''
safe_block = '''                    if let resolvedNewContainer = container, resolvedNewContainer.bookmarkResolved {\n                        resolvedNewContainer.makeLCContainerInfoPlist(appIdentifier: appIdentifier, keychainGroupId: freeKeyChainGroup)\n                    }'''
if unsafe_block in s:
    s = s.replace(unsafe_block, safe_block, 1)
# Handle source before the broad sweep changed the bundle-id argument.
s = s.replace(
    '''                    if container!.bookmarkResolved {\n                        container!.makeLCContainerInfoPlist(appIdentifier: appInfo.bundleIdentifier()!, keychainGroupId: freeKeyChainGroup)\n                    }''',
    safe_block,
    1,
)

append_old = '''            model.uiContainers.append(container!)\n            appInfo.containers = model.uiContainers;\n            if model.uiSelectedContainer == nil {\n                model.uiSelectedContainer = container;\n            }'''
append_new = '''            guard let resolvedContainer = container else {\n                errorInfo = "Unable to create a data-container record for the selected directory."\n                errorShow = true\n                return\n            }\n            model.uiContainers.append(resolvedContainer)\n            appInfo.containers = model.uiContainers\n            if model.uiSelectedContainer == nil {\n                model.uiSelectedContainer = resolvedContainer\n            }'''
if append_new not in s:
    if append_old not in s:
        if 'guard let resolvedContainer = container else' not in s:
            raise SystemExit(f"{path}: external-container finalization anchor missing")
    else:
        s = s.replace(append_old, append_new, 1)

path.write_text(s)

final = path.read_text()
for bad in (
    'renameFolderInput.close(result: newText!)',
    'container!.bookmarkResolved',
    'model.uiContainers.append(container!)',
    'appInfo.bundleIdentifier()!',
):
    if bad in final:
        raise SystemExit(f"{path}: unsafe app-settings form remains: {bad}")
for marker in (
    'defer { url.stopAccessingSecurityScopedResource() }',
    'guard let resolvedContainer = container else',
    'resolvedNewContainer.makeLCContainerInfoPlist',
):
    if marker not in final:
        raise SystemExit(f"{path}: required external-container safety marker missing: {marker}")

print("FlekDeck app-settings container/import force unwraps removed")
