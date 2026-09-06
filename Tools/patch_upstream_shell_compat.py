from pathlib import Path


# 1) Share-sheet IPA handoff: use Duy LiveContainer's bookmark/original-file flow.
# Only the app URL scheme stays FlekDeck-specific.
p = Path("ShareExtension/ShareExtensionViewModel.swift")
s = p.read_text()
start = s.index("    func installSharedFileInLiveContainer(context: NSExtensionContext?) async {")
end = s.index("\n    /// Copies the shared file into the app group", start)
replacement = '''    func installSharedFileInLiveContainer(context: NSExtensionContext?) async {
        if isLaunching {
            return
        }
        guard case .file(let fileURL) = payload.kind else {
            return
        }
        isLaunching = true
        defer { isLaunching = false }

        do {
            try storeBookmark(for: fileURL)
            guard var components = URLComponents(string: "flekdeck://install") else {
                throw ShareExtensionError("Unable to build install URL.")
            }
            components.queryItems = [
                URLQueryItem(name: "url", value: fileURL.absoluteString)
            ]
            guard let installURL = components.url else {
                throw ShareExtensionError("Unable to build install URL.")
            }

            LCShareExtensionLauncher.openURL(fromShareExtension: installURL)
            (context ?? currentContext)?.completeRequest(returningItems: nil, completionHandler: nil)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
'''
s = s[:start] + replacement + s[end:]
p.write_text(s)


# 2) Upstream no longer stages shared IPAs into a fork-only app-group inbox.
p = Path("LiveContainerSwiftUI/Utilities/Shared.swift")
s = p.read_text()
start = s.index("    public static func clearStaleShareInbox() {")
end = s.index("\n    /// Appended to the folder of an app that is being replaced", start)
s = s[:start] + '''    public static func clearStaleShareInbox() {
        // Duy upstream hands shared IPA URLs over by security-scoped bookmark.
        // There is no separate staged app-group inbox in this parity build.
    }
''' + s[end:]
p.write_text(s)


# 3) Flek's queue remains the download/progress shell, but the actual IPA install
# sequence below mirrors Duy LiveContainer: Payload/*.app -> replacement choice ->
# move -> exact LCAppInfo patch/sign -> copy previous config -> publish model.
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()

staged_cleanup = '''                        // A copy the share extension staged in the app group is
                        // ours to remove, and exists for no other reason than to
                        // have reached us. It sits in a folder of its own.
                        if let shareInbox = LCSharedUtils.shareInboxPath(),
                           fileURL.path.hasPrefix(shareInbox.path + "/") {
                            try? fm.removeItem(at: fileURL.deletingLastPathComponent())
                        }
'''
s = s.replace(staged_cleanup, "")

install_start = "    func installIpaFile(_ url:URL, item: InstallItem) async throws {"
install_end = "\n    func startInstallFromUrl() async {"
start = s.index(install_start)
end = s.index(install_end, start)

installer = r'''    func installIpaFile(_ url:URL, item: InstallItem) async throws {
        let fm = FileManager()

        let installProgress = Progress.discreteProgress(totalUnitCount: 100)
        // FlekDeck-only UI adapter: Duy uses installProgressPercentage here.
        // This observer changes presentation only; it does not alter install/signing.
        let observedItem = item
        let queue = installQueue
        let installObserver = installProgress.observe(\.fractionCompleted) { p, v in
            DispatchQueue.main.async {
                queue.updateInstallProgress(observedItem, fraction: p.fractionCompleted)
            }
        }
        _ = installObserver

        let decompressProgress = Progress.discreteProgress(totalUnitCount: 100)
        installProgress.addChild(decompressProgress, withPendingUnitCount: 80)
        let payloadPath = fm.temporaryDirectory.appendingPathComponent("Payload")
        if fm.fileExists(atPath: payloadPath.path) {
            try fm.removeItem(at: payloadPath)
        }

        // decompress
        guard await decompress(url.path, fm.temporaryDirectory.path, decompressProgress) == 0 else {
            throw "lc.appList.urlFileIsNotIpaError".loc
        }

        let payloadContents = try fm.contentsOfDirectory(atPath: payloadPath.path)
        var appBundleName : String? = nil
        for fileName in payloadContents {
            if fileName.hasSuffix(".app") {
                appBundleName = fileName
                break
            }
        }
        guard let appBundleName = appBundleName else {
            throw "lc.appList.bundleNotFondError".loc
        }

        let appFolderPath = payloadPath.appendingPathComponent(appBundleName)

        guard let newAppInfo = LCAppInfo(bundlePath: appFolderPath.path) else {
            throw "lc.appList.infoPlistCannotReadError".loc
        }

        var appRelativePath = "\(newAppInfo.bundleIdentifier()!.sanitizeNonACSII()).app"
        var outputFolder = LCPath.bundlePath.appendingPathComponent(appRelativePath)
        var appToReplace : LCAppModel? = nil
        // Folder exist! show alert for user to choose which bundle to replace
        var sameBundleIdApp = sharedModel.apps.filter { app in
            return app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()
        }
        if sameBundleIdApp.count == 0 {
            sameBundleIdApp = sharedModel.hiddenApps.filter { app in
                return app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()
            }

            // we found a hidden app, we need to authenticate before proceeding
            if sameBundleIdApp.count > 0 && !sharedModel.isHiddenAppUnlocked {
                do {
                    if !(try await LCUtils.authenticateUser()) {
                        throw CancellationError()
                    }
                } catch {
                    throw error
                }
            }
        }

        if fm.fileExists(atPath: outputFolder.path) || sameBundleIdApp.count > 0 {
            appRelativePath = "\(newAppInfo.bundleIdentifier()!)_\(Int(CFAbsoluteTimeGetCurrent())).app"

            self.installOptions = [AppReplaceOption(isReplace: false, nameOfFolderToInstall: appRelativePath)]

            for app in sameBundleIdApp {
                self.installOptions.append(AppReplaceOption(isReplace: true, nameOfFolderToInstall: app.appInfo.relativeBundlePath, appToReplace: app))
            }

            guard let installOptionChosen = await installReplaceAlert.open() else {
                throw CancellationError()
            }

            if let appToReplace = installOptionChosen.appToReplace, appToReplace.uiIsShared {
                outputFolder = LCPath.lcGroupBundlePath.appendingPathComponent(installOptionChosen.nameOfFolderToInstall)
            } else {
                outputFolder = LCPath.bundlePath.appendingPathComponent(installOptionChosen.nameOfFolderToInstall)
            }
            appRelativePath = installOptionChosen.nameOfFolderToInstall
            appToReplace = installOptionChosen.appToReplace
            if installOptionChosen.isReplace {
                try fm.removeItem(at: outputFolder)
            }
        }
        // Move it!
        try fm.moveItem(at: appFolderPath, to: outputFolder)
        let finalNewApp = LCAppInfo(bundlePath: outputFolder.path)
        finalNewApp?.relativeBundlePath = appRelativePath

        guard let finalNewApp else {
            errorInfo = "lc.appList.appInfoInitError".loc
            errorShow = true
            return
        }

        // patch and sign it -- exact upstream LCAppInfo implementation.
        var signError : String? = nil
        var signSuccess = false
        await withUnsafeContinuation({ c in
            if appToReplace?.uiDontSign ?? false || LCUtils.appGroupUserDefault.bool(forKey: "LCDontSignApp") {
                finalNewApp.dontSign = true
            }
            finalNewApp.patchExecAndSignIfNeed(completionHandler: { success, error in
                signError = error
                signSuccess = success
                c.resume()
            }, progressHandler: { signProgress in
                installProgress.addChild(signProgress!, withPendingUnitCount: 20)
            }, forceSign: false)
        })

        // we leave it unsigned even if signing failed
        if let signError {
            if signSuccess {
                errorInfo = "\("lc.appList.signSuccessWithError".loc)\n\n\(signError)"
            } else {
                errorInfo = signError.loc
            }
            errorShow = true
        }

        if let appToReplace {
            // copy previous configration to new app
            finalNewApp.autoSaveDisabled = true
            finalNewApp.isLocked = appToReplace.appInfo.isLocked
            finalNewApp.isHidden = appToReplace.appInfo.isHidden
            finalNewApp.isJITNeeded = appToReplace.appInfo.isJITNeeded
            finalNewApp.isShared = appToReplace.appInfo.isShared
            finalNewApp.spoofSDKVersion = appToReplace.appInfo.spoofSDKVersion
            finalNewApp.doSymlinkInbox = appToReplace.appInfo.doSymlinkInbox
            finalNewApp.containerInfo = appToReplace.appInfo.containerInfo
            finalNewApp.tweakFolder = appToReplace.appInfo.tweakFolder
            finalNewApp.selectedLanguage = appToReplace.appInfo.selectedLanguage
            finalNewApp.dataUUID = appToReplace.appInfo.dataUUID
            finalNewApp.orientationLock = appToReplace.appInfo.orientationLock
            finalNewApp.dontInjectTweakLoader = appToReplace.appInfo.dontInjectTweakLoader
            finalNewApp.hideLiveContainer = appToReplace.appInfo.hideLiveContainer
            finalNewApp.dontLoadTweakLoader = appToReplace.appInfo.dontLoadTweakLoader
            finalNewApp.doUseLCBundleId = appToReplace.appInfo.doUseLCBundleId
            finalNewApp.fixFilePickerNew = appToReplace.appInfo.fixFilePickerNew
            finalNewApp.fixLocalNotification = appToReplace.appInfo.fixLocalNotification
            finalNewApp.lastLaunched = appToReplace.appInfo.lastLaunched
            finalNewApp.jitLaunchScriptJs = appToReplace.appInfo.jitLaunchScriptJs
            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified
            finalNewApp.classicMode = appToReplace.appInfo.classicMode
            finalNewApp.autoSaveDisabled = false
            finalNewApp.save()
        } else {
            // enable SDK version spoof by defalut
            finalNewApp.spoofSDKVersion = true
        }
        finalNewApp.installationDate = Date.now

        await MainActor.run {
            if let appToReplace {
                let newAppModel = LCAppModel(appInfo: finalNewApp, delegate: self)

                if appToReplace.uiIsHidden {
                    sharedModel.hiddenApps.removeAll { $0 == appToReplace }
                    sharedModel.hiddenApps.append(newAppModel)
                } else {
                    sharedModel.apps.removeAll { $0 == appToReplace }
                    sharedModel.apps.append(newAppModel)
                }
            } else {
                let newAppModel = LCAppModel(appInfo: finalNewApp, delegate: self)
                sharedModel.apps.append(newAppModel)

                // add url schemes
                if let urlSchemes = finalNewApp.urlSchemes(), urlSchemes.count > 0 {
                    UserDefaults.lcShared().mutableArrayValue(forKey: "LCGuestURLSchemes")
                        .addObjects(from: urlSchemes as! [Any])
                }
            }
        }
    }
'''

s = s[:start] + installer + s[end:]
p.write_text(s)


# 4) Certificate persistence: use Duy's exact manual p12 path and exact callback
# storage keys. The only SideStore callback difference elsewhere is the FlekDeck
# URL scheme required to route the callback into this app.
p = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
s = p.read_text()
start = s.index("    func importCertificate() async {")
end = s.index("\n    func importEmbeddedCertificate() async {", start)
manual_import = '''    func importCertificate() async {
        guard let doImport = await certificateImportAlert.open(), doImport else {
            return
        }
        guard let certificateURL = await certificateImportFileAlert.open() else {
            return
        }
        guard let certificatePassword = await certificateImportPasswordAlert.open() else {
            return
        }
        let certificateData : Data
        do {
            certificateData = try Data(contentsOf: certificateURL)
        } catch {
            errorInfo = error.localizedDescription
            errorShow = true
            return
        }

        guard let _ = LCUtils.getCertTeamId(withKeyData: certificateData, password: certificatePassword) else {
            errorInfo = "lc.settings.invalidCertError".loc
            errorShow = true
            return
        }

        LCUtils.appGroupUserDefault.set(certificateData, forKey: "LCCertificateData")
        LCUtils.appGroupUserDefault.set(certificatePassword, forKey: "LCCertificatePassword")
        LCUtils.appGroupUserDefault.set(NSDate.now, forKey: "LCCertificateUpdateDate")
        certificateDataFound = true

        UserDefaults.standard.set(LCSharedUtils.appGroupID(), forKey: "LCAppGroupID")
    }
'''
s = s[:start] + manual_import + s[end:]

cb_start = s.index("    func onSideStoreCertificateCallback(certificateData: Data, password: String) {")
cb_end = s.index("\n    func removeCertificate() async {", cb_start)
callback = '''    func onSideStoreCertificateCallback(certificateData: Data, password: String) {
        LCUtils.appGroupUserDefault.set(certificateData, forKey: "LCCertificateData")
        LCUtils.appGroupUserDefault.set(password, forKey: "LCCertificatePassword")
        LCUtils.appGroupUserDefault.set(NSDate.now, forKey: "LCCertificateUpdateDate")
        certificateDataFound = true
    }
'''
s = s[:cb_start] + callback + s[cb_end:]
p.write_text(s)


# 5) Flek's conversion UI had a resumable move classifier that Duy upstream does
# not expose. Localize only the classifier; the actual atomic mover remains the
# exact upstream LCUtils.moveFilesAtomicallyAfterPreflight implementation.
p = Path("LiveContainerSwiftUI/Models/LCAppModel+Conversion.swift")
s = p.read_text()
s = s.replace("LCUtils.MoveStep", "FlekMoveStep")
s = s.replace("LCUtils.planMove(from: source, to: destination)", "flekPlanMove(from: source, to: destination)")

classifier_anchor = "    /// Whether the bundle still has to be moved, has already been moved by an\n"
if "private enum FlekMoveStep" not in s:
    classifier = '''    private enum FlekMoveStep {
        case pending
        case alreadyDone
        case missing
        case blocked
    }

    private func flekPlanMove(from source: URL, to destination: URL) -> FlekMoveStep {
        let fm = FileManager.default
        let sourceExists = fm.fileExists(atPath: source.standardizedFileURL.path)
        let destinationExists = fm.fileExists(atPath: destination.standardizedFileURL.path)
        switch (sourceExists, destinationExists) {
        case (true, false): return .pending
        case (true, true): return .blocked
        case (false, true): return .alreadyDone
        case (false, false): return .missing
        }
    }

'''
    idx = s.index(classifier_anchor)
    s = s[:idx] + classifier + s[idx:]

if "private enum FlekUninstallRefused" not in s:
    s += '''

private enum FlekUninstallRefused: LocalizedError {
    case sharedBundle

    var errorDescription: String? {
        switch self {
        case .sharedBundle:
            return "This app is stored in the shared folder, so every FlekDeck on this device uses the same copy — deleting it here would remove it for all of them.\\n\\nTo delete it, open the app's settings and tap \\"Convert to Private App\\" first."
        }
    }
}

extension LCAppModel {
    var isBundleMissing: Bool {
        guard let bundlePath = appInfo.bundlePath(), !bundlePath.isEmpty else {
            return true
        }
        return !FileManager.default.fileExists(atPath: bundlePath)
    }

    var isUninstallable: Bool {
        !uiIsShared || isBundleMissing
    }

    func uninstall(removingContainers: Bool) throws {
        guard isUninstallable else {
            throw FlekUninstallRefused.sharedBundle
        }

        let fm = FileManager.default
        if let bundlePath = appInfo.bundlePath(), !isBundleMissing {
            try fm.removeItem(atPath: bundlePath)
        }

        guard removingContainers else { return }
        for container in uiContainers {
            let folderName = container.folderName
            if container.storageBookMark == nil {
                try? fm.removeItem(at: container.containerURL)
            }
            LCUtils.removeAppKeychain(dataUUID: folderName)
            DispatchQueue.main.async {
                DataManager.shared.model.appDataFolderNames.removeAll { $0 == folderName }
            }
        }
    }
}
'''

p.write_text(s)

print("Applied Flek shell compatibility with Duy-parity certificate, IPA install, signing and JIT core.")
