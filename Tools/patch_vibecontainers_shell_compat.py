from pathlib import Path

# FlekDeck shell adapter for the VibeContainers LiveContainer-3.8.0 core.
# The files copied from VibeContainers are never edited here. Only fork UI/shell
# files are adapted to call that exact core.

# 1) FlekDeck download queue -> VibeContainers install/patch/sign sequence.
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()
start_sig = "    func installIpaFile(_ url:URL, item: InstallItem) async throws {"
end_sig = "\n    func startInstallFromUrl() async {"
start = s.index(start_sig)
end = s.index(end_sig, start)
installer = r'''    func installIpaFile(_ url:URL, item: InstallItem) async throws {
        let fm = FileManager()

        let installProgress = Progress.discreteProgress(totalUnitCount: 100)
        let observedItem = item
        let queue = installQueue
        let installObserver = installProgress.observe(\.fractionCompleted) { p, _ in
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
        var sameBundleIdApp = sharedModel.apps.filter { app in
            return app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()
        }
        if sameBundleIdApp.count == 0 {
            sameBundleIdApp = sharedModel.hiddenApps.filter { app in
                return app.appInfo.bundleIdentifier()! == newAppInfo.bundleIdentifier()
            }
            if sameBundleIdApp.count > 0 && !sharedModel.isHiddenAppUnlocked {
                if !(try await LCUtils.authenticateUser()) {
                    throw CancellationError()
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

        try fm.moveItem(at: appFolderPath, to: outputFolder)
        let finalNewApp = LCAppInfo(bundlePath: outputFolder.path)
        finalNewApp?.relativeBundlePath = appRelativePath
        guard let finalNewApp else {
            errorInfo = "lc.appList.appInfoInitError".loc
            errorShow = true
            return
        }

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

        if let signError {
            if signSuccess {
                errorInfo = "\("lc.appList.signSuccessWithError".loc)\n\n\(signError)"
            } else {
                errorInfo = signError.loc
            }
            errorShow = true
        }

        if let appToReplace {
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
            finalNewApp.autoSaveDisabled = false
            finalNewApp.save()
        } else {
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

# 2) Certificate import/callback is the VibeContainers LiveContainer-3.8.0 flow.
p = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
s = p.read_text()
start = s.index("    func importCertificate() async {")
# FlekDeck still carries the old embedded-certificate helper after this function.
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

# 3) VibeContainers 3.8.0 predates Classic Mode. Remove only that newer Flek UI.
p = Path("LiveContainerSwiftUI/Views/AppList/AppSettings/LCAppSettingsView.swift")
s = p.read_text()
classic = '''            if #available(iOS 16.0, *) {
                Section {
                    Toggle(isOn: $model.uiClassicMode) {
                        Text("lc.appSettings.classicMode".loc)
                    }
                } footer: {
                    Text("lc.appSettings.classicModeDesc".loc)
                }
            }
            
'''
s = s.replace(classic, "")
p.write_text(s)

# 4) Flek shared/private conversion is shell functionality. Keep it outside Vibe's
# LCUtils by using a local preflighted mover rather than adding APIs to Vibe core.
p = Path("LiveContainerSwiftUI/Models/LCAppModel+Conversion.swift")
s = p.read_text()
s = s.replace("try LCUtils.moveFilesAtomicallyAfterPreflight(moves)", "try flekMoveFilesAtomicallyAfterPreflight(moves)")
anchor = "    /// Whether the bundle still has to be moved, has already been moved by an\n"
if "private func flekMoveFilesAtomicallyAfterPreflight" not in s:
    helper = '''    private func flekMoveFilesAtomicallyAfterPreflight(_ moves: [(URL, URL)]) throws {
        let fm = FileManager.default
        for (source, destination) in moves {
            guard fm.fileExists(atPath: source.path) else { continue }
            if fm.fileExists(atPath: destination.path) {
                throw ConversionRefused(message: "A destination already exists at \\(destination.lastPathComponent).")
            }
        }
        var completed: [(URL, URL)] = []
        do {
            for (source, destination) in moves {
                guard fm.fileExists(atPath: source.path) else { continue }
                try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
                try fm.moveItem(at: source, to: destination)
                completed.append((source, destination))
            }
        } catch {
            for (source, destination) in completed.reversed() {
                if fm.fileExists(atPath: destination.path), !fm.fileExists(atPath: source.path) {
                    try? fm.moveItem(at: destination, to: source)
                }
            }
            throw error
        }
    }

'''
    idx = s.index(anchor)
    s = s[:idx] + helper + s[idx:]
p.write_text(s)

print("Applied FlekDeck shell adapters around exact VibeContainers signing/JIT core.")
