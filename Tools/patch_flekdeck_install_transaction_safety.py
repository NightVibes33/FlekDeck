#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = path.read_text()

# 1. Validate bundle identity once and stop force-unwrapping malformed IPAs.
anchor = '''        guard let newAppInfo = LCAppInfo(bundlePath: appFolderPath.path) else {\n            throw "lc.appList.infoPlistCannotReadError".loc\n        }\n\n        var appRelativePath = "\\(newAppInfo.bundleIdentifier()!.sanitizeNonACSII()).app"'''
replacement = '''        guard let newAppInfo = LCAppInfo(bundlePath: appFolderPath.path) else {\n            throw "lc.appList.infoPlistCannotReadError".loc\n        }\n        guard let newBundleIdentifier = newAppInfo.bundleIdentifier(),\n              !newBundleIdentifier.isEmpty, newBundleIdentifier != "Unknown" else {\n            throw "The IPA does not contain a valid CFBundleIdentifier."\n        }\n\n        var appRelativePath = "\\(newBundleIdentifier.sanitizeNonACSII()).app"'''
if replacement not in s:
    if anchor not in s:
        raise SystemExit(f"{path}: new-app bundle identifier anchor missing")
    s = s.replace(anchor, replacement, 1)

s = s.replace(
    'return app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()',
    'return app.appInfo.bundleIdentifier() == newBundleIdentifier'
)
s = s.replace(
    'appRelativePath = "\\(newAppInfo.bundleIdentifier()!)_\\(Int(CFAbsoluteTimeGetCurrent())).app"',
    'appRelativePath = "\\(newBundleIdentifier)_\\(Int(CFAbsoluteTimeGetCurrent())).app"',
    1,
)

# 2. Track a parked old bundle instead of deleting it before the replacement is valid.
app_to_replace_anchor = '''        var outputFolder = LCPath.bundlePath.appendingPathComponent(appRelativePath)\n        var appToReplace : LCAppModel? = nil\n'''
app_to_replace_new = '''        var outputFolder = LCPath.bundlePath.appendingPathComponent(appRelativePath)\n        var appToReplace : LCAppModel? = nil\n        var replacementBackupURL: URL? = nil\n'''
if app_to_replace_new not in s:
    if app_to_replace_anchor not in s:
        raise SystemExit(f"{path}: replacement state anchor missing")
    s = s.replace(app_to_replace_anchor, app_to_replace_new, 1)

remove_old = '''            if installOptionChosen.isReplace {\n                try fm.removeItem(at: outputFolder)\n            }\n        }\n\n        try fm.moveItem(at: appFolderPath, to: outputFolder)\n        let finalNewApp = LCAppInfo(bundlePath: outputFolder.path)\n'''
remove_new = '''            if installOptionChosen.isReplace {\n                let backup = URL(fileURLWithPath: outputFolder.path + LCPath.replacingSuffix, isDirectory: true)\n                if fm.fileExists(atPath: backup.path) {\n                    try fm.removeItem(at: backup)\n                }\n                // Preserve the known-good app until the replacement has parsed and\n                // completed patch/sign successfully. Same-volume move is atomic.\n                try fm.moveItem(at: outputFolder, to: backup)\n                replacementBackupURL = backup\n            }\n        }\n\n        do {\n            try fm.moveItem(at: appFolderPath, to: outputFolder)\n        } catch {\n            if let backup = replacementBackupURL, fm.fileExists(atPath: backup.path) {\n                try? fm.moveItem(at: backup, to: outputFolder)\n            }\n            throw error\n        }\n        let finalNewApp = LCAppInfo(bundlePath: outputFolder.path)\n'''
if remove_new not in s:
    if remove_old not in s:
        raise SystemExit(f"{path}: destructive replacement anchor missing")
    s = s.replace(remove_old, remove_new, 1)

# 3. If LCAppInfo cannot initialize, restore the parked app instead of returning
# with a corrupt replacement in place.
init_old = '''        guard let finalNewApp else {\n            errorInfo = "lc.appList.appInfoInitError".loc\n            errorShow = true\n            return\n        }\n'''
init_new = '''        guard let finalNewApp else {\n            try? fm.removeItem(at: outputFolder)\n            if let backup = replacementBackupURL, fm.fileExists(atPath: backup.path) {\n                try? fm.moveItem(at: backup, to: outputFolder)\n            }\n            throw "lc.appList.appInfoInitError".loc\n        }\n'''
if init_new not in s:
    if init_old not in s:
        raise SystemExit(f"{path}: final app-info failure anchor missing")
    s = s.replace(init_old, init_new, 1)

# 4. Progress is optional. Never crash because an immediate signer failure has no NSProgress.
s = s.replace(
    '''            }, progressHandler: { signProgress in\n                installProgress.addChild(signProgress!, withPendingUnitCount: 20)\n            }, forceSign: false)''',
    '''            }, progressHandler: { signProgress in\n                if let signProgress {\n                    installProgress.addChild(signProgress, withPendingUnitCount: 20)\n                }\n            }, forceSign: false)''',
    1,
)

# 5. A failed patch/sign is fatal to this install. Roll the filesystem back and
# propagate the exact signer/patch message through the queue instead of installing anyway.
sign_anchor = '''        if let signError {\n            if signSuccess {\n                errorInfo = "\\("lc.appList.signSuccessWithError".loc)\\n\\n\\(signError)"\n            } else {\n                errorInfo = signError.loc\n            }\n            errorShow = true\n        }\n\n        if let appToReplace {'''
sign_replacement = '''        if !signSuccess {\n            try? fm.removeItem(at: outputFolder)\n            if let backup = replacementBackupURL, fm.fileExists(atPath: backup.path) {\n                try? fm.moveItem(at: backup, to: outputFolder)\n            }\n            throw signError?.loc ?? "App patch/sign failed without a diagnostic."\n        }\n        if let signError {\n            // The signer can succeed with a non-fatal warning. Preserve that\n            // exact warning without turning it into a failed install.\n            errorInfo = "\\("lc.appList.signSuccessWithError".loc)\\n\\n\\(signError)"\n            errorShow = true\n        }\n\n        if let appToReplace {'''
if sign_replacement not in s:
    if sign_anchor not in s:
        raise SystemExit(f"{path}: sign-result anchor missing")
    s = s.replace(sign_anchor, sign_replacement, 1)

# 6. Delete the parked old bundle only after model migration is committed.
commit_anchor = '''        finalNewApp.installationDate = Date.now\n\n        await MainActor.run {'''
commit_new = '''        finalNewApp.installationDate = Date.now\n\n        if let backup = replacementBackupURL, fm.fileExists(atPath: backup.path) {\n            do {\n                try fm.removeItem(at: backup)\n            } catch {\n                // The new app is valid and active. A leftover backup is recoverable\n                // by LCPath.recoverInterruptedReplaces on a later launch, so log it\n                // rather than destroying the successful install.\n                NSLog("[FlekDeck/Install] could not remove replacement backup: %@", error.localizedDescription)\n            }\n        }\n\n        await MainActor.run {'''
if commit_new not in s:
    if commit_anchor not in s:
        raise SystemExit(f"{path}: successful replacement commit anchor missing")
    s = s.replace(commit_anchor, commit_new, 1)

path.write_text(s)

final = path.read_text()
for bad in (
    'newAppInfo.bundleIdentifier()!',
    'app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()',
    'try fm.removeItem(at: outputFolder)\n            }\n        }\n\n        try fm.moveItem(at: appFolderPath',
    'installProgress.addChild(signProgress!',
):
    if bad in final:
        raise SystemExit(f"{path}: unsafe install form remains: {bad}")
for marker in (
    'replacementBackupURL',
    'LCPath.replacingSuffix',
    'if !signSuccess',
    'App patch/sign failed without a diagnostic.',
):
    if marker not in final:
        raise SystemExit(f"{path}: transactional install marker missing: {marker}")

print("FlekDeck IPA replacement/signing made transactional and malformed-ID safe")
