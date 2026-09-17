//
//  LiveContainerSwiftUIApp.swift
//  LiveContainer
//
//  Created by s s on 2025/5/16.
//
import SwiftUI

@main
struct LiveContainerSwiftUIApp : SwiftUI.App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    private static let bundled32BitRuntimeName = "LiveExec32.app"
    private static let bundled32BitRuntimeCommit = "3f0390e1b2725a2d3c9ab6f3976650a5a295ffba"
    private static let bundled32BitRuntimeRevision = "89"

    private static func seedBundled32BitRuntime(using fm: FileManager) throws {
        let bundledURL = Bundle.main.bundleURL.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)
        guard fm.fileExists(atPath: bundledURL.path) else { return }

        let bundledInfoURL = bundledURL.appendingPathComponent("Info.plist")
        guard let bundledInfo = NSDictionary(contentsOf: bundledInfoURL),
              bundledInfo["LC32BitTranslationLayer"] as? Bool == true,
              bundledInfo["LCBundledSourceCommit"] as? String == bundled32BitRuntimeCommit,
              bundledInfo["LCBundledBuildRevision"] as? String == bundled32BitRuntimeRevision else {
            NSLog("[FlekDeck/LC32] Embedded LiveExec32 metadata is invalid or stale")
            return
        }

        try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)
        let installedURL = LCPath.bundlePath.appendingPathComponent(bundled32BitRuntimeName, isDirectory: true)
        let installedInfo = NSDictionary(contentsOf: installedURL.appendingPathComponent("Info.plist"))
        let installedCommit = installedInfo?["LCBundledSourceCommit"] as? String
        let installedRevision = installedInfo?["LCBundledBuildRevision"] as? String
        if installedCommit != bundled32BitRuntimeCommit || installedRevision != bundled32BitRuntimeRevision {
            if fm.fileExists(atPath: installedURL.path) {
                try fm.removeItem(at: installedURL)
            }
            try fm.copyItem(at: bundledURL, to: installedURL)

            // Keep the runtime out of the normal app list. It is an implementation
            // detail, not a user-launchable guest.
            let runtimeAppInfo: [String: Any] = [
                "isHidden": true,
                "isLocked": true,
                "dontSign": true
            ]
            let runtimeAppInfoData = try PropertyListSerialization.data(
                fromPropertyList: runtimeAppInfo, format: .binary, options: 0
            )
            try runtimeAppInfoData.write(to: installedURL.appendingPathComponent("LCAppInfo.plist"))
            NSLog("[FlekDeck/LC32] Installed bundled LiveExec32 revision %@", bundled32BitRuntimeRevision)
        }

        let defaults = LCUtils.appGroupUserDefault
        if (defaults.string(forKey: "LCSelected32BitEmulator") ?? "").isEmpty {
            defaults.set(bundled32BitRuntimeName, forKey: "LCSelected32BitEmulator")
        }
    }
    
    // appDataFolderNames and tweakFolderNames used to be @State here and were
    // threaded down as bindings. Upstream moved them onto DataManager's shared
    // model, which is populated at the end of init() below, so the views read
    // them from the environment instead.
    @StateObject private var flekstoreSharedModel = FlekstoreSharedModel()
    
    init() {
        // The identifier guest apps check against lives in this app's Info.plist,
        // but a guest launched in parallel runs inside LiveProcess.appex and reads
        // the bundle of *that* process, which never carries it. Publish it to the
        // app group here so the extension is handed the value rather than having to
        // find this bundle on disk — a search that lands on the wrong app entirely
        // when the extension in use belongs to another LiveContainer install.
        if let hostEncryptedUdid = Bundle.main.infoDictionary?["encryptedUdid"] as? String,
           !hostEncryptedUdid.isEmpty {
            LCUtils.appGroupUserDefault.set(hostEncryptedUdid, forKey: "LCHostEncryptedUdid")
        }

        LCPath.clearStaleShareInbox()

        let fm = FileManager()
        var tempAppDataFolderNames : [String] = []
        var tempTweakFolderNames : [String] = []
        
        var tempApps: [LCAppModel] = []
#if is32BitSupported
        var tempArm32EmuApps: [LCAppModel] = []
#endif
        var tempHiddenApps: [LCAppModel] = []
        var tempURLSchemes: Set<String>? = DataManager.shared.model.multiLCStatus != 2 ? Set() : nil

        do {
            try Self.seedBundled32BitRuntime(using: fm)
        } catch {
            NSLog("[FlekDeck/LC32] Runtime seed failed without blocking app discovery: \(error)")
        }

        do {
            // load apps
            try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)
            var appDirs = try fm.contentsOfDirectory(atPath: LCPath.bundlePath.path)
            // Launch is the one moment nothing else is in these folders, so it is
            // where an install that died mid-replace gets its app back.
            if appDirs.contains(where: { $0.hasSuffix(LCPath.replacingSuffix) }) {
                LCPath.recoverInterruptedReplaces(in: LCPath.bundlePath, contents: appDirs)
                appDirs = try fm.contentsOfDirectory(atPath: LCPath.bundlePath.path)
            }
            for appDir in appDirs {
                if !appDir.hasSuffix(".app") {
                    continue
                }
                guard let newApp = LCAppInfo(bundlePath: "\(LCPath.bundlePath.path)/\(appDir)") else {
                    NSLog("[FlekDeck] Skipping malformed app bundle: %@", appDir)
                    continue
                }
                newApp.relativeBundlePath = appDir
                newApp.isShared = false
#if is32BitSupported
                if newApp.is32bitEmulator {
                    tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                    continue
                }
#endif
                if newApp.isHidden {
                    tempHiddenApps.append(LCAppModel(appInfo: newApp))
                } else {
                    tempApps.append(LCAppModel(appInfo: newApp))
                    tempURLSchemes?.formUnion((newApp.urlSchemes() as? [String]) ?? [])
                }
            }
            if LCPath.lcGroupDocPath != LCPath.docPath {
                try fm.createDirectory(at: LCPath.lcGroupBundlePath, withIntermediateDirectories: true)
                var appDirsShared = try fm.contentsOfDirectory(atPath: LCPath.lcGroupBundlePath.path)
                if appDirsShared.contains(where: { $0.hasSuffix(LCPath.replacingSuffix) }) {
                    LCPath.recoverInterruptedReplaces(in: LCPath.lcGroupBundlePath, contents: appDirsShared)
                    appDirsShared = try fm.contentsOfDirectory(atPath: LCPath.lcGroupBundlePath.path)
                }
                for appDir in appDirsShared {
                    if !appDir.hasSuffix(".app") {
                        continue
                    }
                    guard let newApp = LCAppInfo(bundlePath: "\(LCPath.lcGroupBundlePath.path)/\(appDir)") else {
                        NSLog("[FlekDeck] Skipping malformed shared app bundle: %@", appDir)
                        continue
                    }
                    newApp.relativeBundlePath = appDir
                    newApp.isShared = true
#if is32BitSupported
                    if newApp.is32bitEmulator {
                        tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                        continue
                    }
#endif
                    if newApp.isHidden {
                        tempHiddenApps.append(LCAppModel(appInfo: newApp))
                    } else {
                        tempApps.append(LCAppModel(appInfo: newApp))
                        tempURLSchemes?.formUnion((newApp.urlSchemes() as? [String]) ?? [])
                    }
                }
            }
            // load document folders
            try fm.createDirectory(at: LCPath.dataPath, withIntermediateDirectories: true)
            let dataDirs = try fm.contentsOfDirectory(atPath: LCPath.dataPath.path)
            for dataDir in dataDirs {
                let dataDirUrl = LCPath.dataPath.appendingPathComponent(dataDir)
                if !dataDirUrl.hasDirectoryPath {
                    continue
                }
                tempAppDataFolderNames.append(dataDir)
            }
            
            // load tweak folders
            try fm.createDirectory(at: LCPath.tweakPath, withIntermediateDirectories: true)
            let tweakDirs = try fm.contentsOfDirectory(atPath: LCPath.tweakPath.path)
            for tweakDir in tweakDirs {
                let tweakDirUrl = LCPath.tweakPath.appendingPathComponent(tweakDir)
                if !tweakDirUrl.hasDirectoryPath {
                    continue
                }
                let folderName = tweakDir.hasSuffix(".disabled") ? String(tweakDir.dropLast(".disabled".count)) : tweakDir
                tempTweakFolderNames.append(folderName)
            }
        } catch {
            NSLog("[LC] error:\(error)")
        }
        
        DataManager.shared.model.apps = tempApps
#if is32BitSupported
        DataManager.shared.model.arm32EmuApps = tempArm32EmuApps

        // Runtime choices are persisted across updates/removals. Normalize them
        // against the runtimes that actually exist now so a stale path cannot
        // make every ARM32 app fail forever. Per-app stale overrides fall back to
        // the global selection; the global selection prefers bundled LiveExec32.
        let available32BitRuntimeNames = Set(tempArm32EmuApps.compactMap { model in
            model.appInfo.relativeBundlePath.map { ($0 as NSString).lastPathComponent }
        })
        let runtimeDefaults = LCUtils.appGroupUserDefault
        let persistedDefault = runtimeDefaults.string(forKey: "LCSelected32BitEmulator") ?? ""
        let persistedDefaultName = (persistedDefault as NSString).lastPathComponent
        if !persistedDefaultName.isEmpty && !available32BitRuntimeNames.contains(persistedDefaultName) {
            if available32BitRuntimeNames.contains(Self.bundled32BitRuntimeName) {
                runtimeDefaults.set(Self.bundled32BitRuntimeName, forKey: "LCSelected32BitEmulator")
                NSLog("[FlekDeck/LC32] Repaired stale default runtime %@ -> %@", persistedDefaultName, Self.bundled32BitRuntimeName)
            } else if let firstRuntime = available32BitRuntimeNames.sorted().first {
                runtimeDefaults.set(firstRuntime, forKey: "LCSelected32BitEmulator")
                NSLog("[FlekDeck/LC32] Repaired stale default runtime %@ -> %@", persistedDefaultName, firstRuntime)
            } else {
                runtimeDefaults.removeObject(forKey: "LCSelected32BitEmulator")
            }
        }

        for model in tempApps + tempHiddenApps where model.appInfo.is32bit {
            guard let selected = model.appInfo.selected32BitEmulator, !selected.isEmpty else { continue }
            let selectedName = (selected as NSString).lastPathComponent
            if !available32BitRuntimeNames.contains(selectedName) {
                model.appInfo.selected32BitEmulator = ""
                model.uiSelected32BitEmulator = ""
                NSLog("[FlekDeck/LC32] Cleared stale per-app runtime %@ for %@", selectedName, model.appInfo.displayName())
            }
        }
#endif
        DataManager.shared.model.hiddenApps = tempHiddenApps
        DataManager.shared.model.appDataFolderNames = tempAppDataFolderNames
        DataManager.shared.model.tweakFolderNames = tempTweakFolderNames
        if let tempURLSchemes {
            UserDefaults.lcShared().set(Array(tempURLSchemes), forKey: "LCGuestURLSchemes")
        }
    }
    
    var body: some Scene {
        WindowGroup(id: "Main") {
            LCTabView()
                .handlesExternalEvents(preferring: ["*"], allowing: ["*"])
                .environmentObject(DataManager.shared.model)
                .environmentObject(LCAppSortManager.shared)
                .environmentObject(flekstoreSharedModel)
        }
        
        if UIApplication.shared.supportsMultipleScenes, #available(iOS 16.1, *) {
            MultitaskScene()
        }
    }

}

/// The multi-window scene, isolated behind its own availability-annotated type.
///
/// `WindowGroup(id:for:)` produces `PresentedWindowContent`, which is iOS 16.0+.
/// Inlined in `body` above, that type would land in the App's `Body` — and
/// SwiftUI resolves `Body` at launch, before any `#available` check runs, so
/// iOS 15 would trap on start rather than skipping the scene. Referencing
/// `MultitaskScene` instead is safe on every version because its metadata lives
/// in our own binary; its `Body` is only resolved if the scene is actually
/// built, which the guard above prevents. There is no `AnyScene`, so this
/// indirection is the Scene-level equivalent of the AnyView erasure used for
/// version-gated views.
@available(iOS 16.1, *)
private struct MultitaskScene: Scene {
    var body: some Scene {
        WindowGroup(id: "appView", for: String.self) { $id in
            if let id {
                MultitaskAppWindow(id: id)
            }
        }
    }
}
