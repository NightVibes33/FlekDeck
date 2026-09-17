#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift")
s = path.read_text()
start = s.find("    private static func seedBundled32BitRuntime(using fm: FileManager) throws {")
end = s.find("    \n    // appDataFolderNames", start)
if start < 0 or end < 0:
    raise SystemExit(f"{path}: bundled runtime seed function markers missing")

replacement = r'''    private static func seedBundled32BitRuntime(using fm: FileManager) throws {
        let bundledURL = Bundle.main.bundleURL.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)
        guard fm.fileExists(atPath: bundledURL.path) else { return }

        func runtimeIsHealthy(_ url: URL, requirePinnedBuild: Bool) -> Bool {
            let infoURL = url.appendingPathComponent("Info.plist")
            guard let info = NSDictionary(contentsOf: infoURL),
                  info["LC32BitTranslationLayer"] as? Bool == true else { return false }
            if requirePinnedBuild {
                guard info["LCBundledSourceCommit"] as? String == bundled32BitRuntimeCommit,
                      info["LCBundledBuildRevision"] as? String == bundled32BitRuntimeRevision else { return false }
            }
            guard let loadPath = info["LC32BitEmulatorLoadPath"] as? String, !loadPath.isEmpty,
                  let entry = info["LC32BitEmulatorEntrySymbol"] as? String, !entry.isEmpty else { return false }
            let sharedImage = url.appendingPathComponent(loadPath)
            var isDirectory: ObjCBool = false
            guard fm.fileExists(atPath: sharedImage.path, isDirectory: &isDirectory), !isDirectory.boolValue,
                  fm.isReadableFile(atPath: sharedImage.path) else { return false }
            let rootFS = url.appendingPathComponent("RootFS", isDirectory: true)
            var rootIsDirectory: ObjCBool = false
            guard fm.fileExists(atPath: rootFS.path, isDirectory: &rootIsDirectory), rootIsDirectory.boolValue else { return false }
            guard let launcherName = info["CFBundleExecutable"] as? String, !launcherName.isEmpty else { return false }
            let launcher = url.appendingPathComponent(launcherName)
            guard fm.fileExists(atPath: launcher.path), fm.isExecutableFile(atPath: launcher.path) else { return false }
            return true
        }

        guard runtimeIsHealthy(bundledURL, requirePinnedBuild: true) else {
            NSLog("[FlekDeck/LC32] Embedded LiveExec32 payload is invalid or incomplete")
            return
        }

        try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)
        let installedURL = LCPath.bundlePath.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)
        let stagingURL = LCPath.bundlePath.appendingPathComponent(".LiveExec32.app.staging", isDirectory: true)
        let backupURL = LCPath.bundlePath.appendingPathComponent(".LiveExec32.app.backup", isDirectory: true)

        let installedInfo = NSDictionary(contentsOf: installedURL.appendingPathComponent("Info.plist"))
        let installedPinned = installedInfo?["LCBundledSourceCommit"] as? String == bundled32BitRuntimeCommit &&
                              installedInfo?["LCBundledBuildRevision"] as? String == bundled32BitRuntimeRevision
        let installedHealthy = installedPinned && runtimeIsHealthy(installedURL, requirePinnedBuild: true)

        if !installedHealthy {
            // Build a complete replacement beside the current runtime first. Do
            // not remove the known-old runtime until the replacement validates.
            if fm.fileExists(atPath: stagingURL.path) { try fm.removeItem(at: stagingURL) }
            try fm.copyItem(at: bundledURL, to: stagingURL)

            let runtimeAppInfo: [String: Any] = [
                "isHidden": true,
                "isLocked": true,
                "dontSign": true
            ]
            let runtimeAppInfoData = try PropertyListSerialization.data(
                fromPropertyList: runtimeAppInfo, format: .binary, options: 0
            )
            try runtimeAppInfoData.write(
                to: stagingURL.appendingPathComponent("LCAppInfo.plist"),
                options: .atomic
            )

            guard runtimeIsHealthy(stagingURL, requirePinnedBuild: true) else {
                try? fm.removeItem(at: stagingURL)
                throw NSError(
                    domain: "FlekDeck.LiveExec32Seed",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "The staged LiveExec32 runtime failed integrity validation."]
                )
            }

            if fm.fileExists(atPath: backupURL.path) { try fm.removeItem(at: backupURL) }
            let hadInstalledRuntime = fm.fileExists(atPath: installedURL.path)
            if hadInstalledRuntime {
                try fm.moveItem(at: installedURL, to: backupURL)
            }

            do {
                try fm.moveItem(at: stagingURL, to: installedURL)
                if fm.fileExists(atPath: backupURL.path) { try fm.removeItem(at: backupURL) }
                NSLog("[FlekDeck/LC32] Atomically installed/repaired LiveExec32 revision %@", bundled32BitRuntimeRevision)
            } catch {
                // Restore the previous runtime if the final rename failed.
                try? fm.removeItem(at: installedURL)
                if hadInstalledRuntime, fm.fileExists(atPath: backupURL.path) {
                    try? fm.moveItem(at: backupURL, to: installedURL)
                }
                try? fm.removeItem(at: stagingURL)
                throw error
            }
        } else {
            // Old builds may have a healthy runtime but no hidden metadata.
            let appInfoURL = installedURL.appendingPathComponent("LCAppInfo.plist")
            if !fm.fileExists(atPath: appInfoURL.path) {
                let runtimeAppInfo: [String: Any] = ["isHidden": true, "isLocked": true, "dontSign": true]
                let data = try PropertyListSerialization.data(fromPropertyList: runtimeAppInfo, format: .binary, options: 0)
                try data.write(to: appInfoURL, options: .atomic)
            }
        }

        let defaults = LCUtils.appGroupUserDefault
        if (defaults.string(forKey: "LCSelected32BitEmulator") ?? "").isEmpty {
            defaults.set(bundled32BitRuntimeName, forKey: "LCSelected32BitEmulator")
        }
    }
'''

s = s[:start] + replacement + s[end:]
path.write_text(s)

final = path.read_text()
for marker in (
    'runtimeIsHealthy',
    '.LiveExec32.app.staging',
    '.LiveExec32.app.backup',
    'Atomically installed/repaired LiveExec32 revision',
    'The staged LiveExec32 runtime failed integrity validation.',
):
    if marker not in final:
        raise SystemExit(f"{path}: atomic runtime seed marker missing: {marker}")
if 'try fm.removeItem(at: installedURL)\n            try fm.copyItem(at: bundledURL, to: installedURL)' in final:
    raise SystemExit(f"{path}: destructive delete-then-copy runtime seeding survived")

print("FlekDeck bundled LiveExec32 seeding made atomic, self-validating, and recoverable")
