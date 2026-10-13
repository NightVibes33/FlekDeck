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
        var tempHiddenApps: [LCAppModel] = []
        var tempURLSchemes: Set<String>? = DataManager.shared.model.multiLCStatus != 2 ? Set() : nil

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
                let newApp = LCAppInfo(bundlePath: "\(LCPath.bundlePath.path)/\(appDir)")!
                newApp.relativeBundlePath = appDir
                newApp.isShared = false
                if newApp.isHidden {
                    tempHiddenApps.append(LCAppModel(appInfo: newApp))
                } else {
                    tempApps.append(LCAppModel(appInfo: newApp))
                    tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
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
                    let newApp = LCAppInfo(bundlePath: "\(LCPath.lcGroupBundlePath.path)/\(appDir)")!
                    newApp.relativeBundlePath = appDir
                    newApp.isShared = true
                    if newApp.isHidden {
                        tempHiddenApps.append(LCAppModel(appInfo: newApp))
                    } else {
                        tempApps.append(LCAppModel(appInfo: newApp))
                        tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
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
        DataManager.shared.model.hiddenApps = tempHiddenApps
        DataManager.shared.model.appDataFolderNames = tempAppDataFolderNames
        DataManager.shared.model.tweakFolderNames = tempTweakFolderNames
        if let tempURLSchemes {
            UserDefaults.lcShared().set(Array(tempURLSchemes), forKey: "LCGuestURLSchemes")
        }
    }
    
    var body: some Scene {
        WindowGroup(id: "Main") {
            FlekDeckBootGateView {
                LCTabView()
            }
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

