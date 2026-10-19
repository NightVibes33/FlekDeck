//
//  LCSettingsView.swift
//  LiveContainerSwiftUI
//
//  Created by s s on 2024/8/21.
//

import Foundation
import SwiftUI
import UserNotifications

enum JITEnablerType : Int, CaseIterable, Identifiable {
    var id: Int { rawValue }
    case SideJITServer = 0
    case StikJIT = 1
    case JITStreamerEBLegacy = 2
    case StikJITLC = 3
    case SideStore = 4
    case StosDebug = 5
    case StosDebugLC = 6
    
    var displayName: String {
        switch self {
        case .StikJIT: "StikDebug"
        case .StikJITLC: "StikDebug (Another FlekDeck)"
        case .StosDebug: "StosDebug"
        case .StosDebugLC: "StosDebug (Another FlekDeck)"
        case .SideStore: "SideStore"
        case .JITStreamerEBLegacy: "JitStreamer-EB (Relaunch)"
        case .SideJITServer: "SideJITServer/JITStreamer 2.0"
        }
    }
}

struct LCSettingsView: View {
    @State var errorShow = false
    @State var errorInfo = ""
    @State var successShow = false
    @State var successInfo = ""
    @StateObject private var installLC2Alert = AlertHelper<Int>()
    @State private var certificateDataFound = false
    @State private var procursusInstalled = false
    @State private var procursusInstalling = false
    @State private var procursusInstallStatus = ""
    @State private var procursusProgress: [String: Any] = [:]
    
    @StateObject private var certificateImportAlert = YesNoHelper()
    @StateObject private var certificateImportFromBuiltInSideStoreAlert = YesNoHelper()
    @StateObject private var certificateRemoveAlert = YesNoHelper()
    @StateObject private var certificateImportFileAlert = AlertHelper<URL>()
    @StateObject private var certificateImportPasswordAlert = InputHelper()
    
    @AppStorage("LCFrameShortcutIcons") var frameShortIcon = false
    @AppStorage("LCSwitchAppWithoutAsking") var silentSwitchApp = false
    @AppStorage("LCOpenWebPageWithoutAsking") var silentOpenWebPage = false
    @AppStorage("LCDontSignApp", store: LCUtils.appGroupUserDefault) var dontSignApp = false
    @AppStorage("LCCustomBundleIdEnabled", store: LCUtils.appGroupUserDefault) var customBundleIdEnabled = false
    @AppStorage("LCStrictHiding", store: LCUtils.appGroupUserDefault) var strictHiding = false
    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault) var dynamicColors = true
    @AppStorage("darkModeIcon", store: LCUtils.appGroupUserDefault) var darkModeIcon = false
    
    @AppStorage("LCMultitaskMode", store: LCUtils.appGroupUserDefault) var multitaskMode: MultitaskMode = .virtualWindow
    @AppStorage("LCLaunchInMultitaskMode") var launchInMultitaskMode = true
    @AppStorage("LCLaunchMultitaskMaximized") var launchMultitaskMaximized = false
    // Multitask switcher bar: rounded (tall, concave corners) when on, flat short bar when off.
    // Bar rounding amount, 0 (flat) … 100 (fully rounded concave corners).
    @AppStorage("LCMultitaskBarLedgeAmount", store: LCUtils.appGroupUserDefault) var barLedgeAmount: Double = 60
    // Multitask control haptics: 0 (off) … 3 (strongest). Read back through
    // MultitaskDockManager, which also carries over the on/off switch this
    // slider replaced.
    @AppStorage("LCMultitaskHapticsLevel", store: LCUtils.appGroupUserDefault) var multitaskHapticsLevel = 1
    @AppStorage("LCAutoEndPiP", store: LCUtils.appGroupUserDefault) var autoEndPiP = false
    @AppStorage("LCSkipTerminatedScreen", store: LCUtils.appGroupUserDefault) var skipTerminatedScreen = true
    @AppStorage("LCRestartTerminatedApp", store: LCUtils.appGroupUserDefault) var restartTerminatedApp = true
    @AppStorage("LCMaxOneAppOnStage", store: LCUtils.appGroupUserDefault) var onlyOneAppOnStage = false
    @AppStorage("LCRedirectURLToHost", store: LCUtils.appGroupUserDefault) var redirectURLToHost = false
    @AppStorage("LCShowRotationPanel", store: LCUtils.appGroupUserDefault) var showRotationPanel = false
    @AppStorage("LCMultitaskHomeBar", store: LCUtils.appGroupUserDefault) var usesBottomSwipe = true
    
    @AppStorage("LCSideJITServerAddress", store: LCUtils.appGroupUserDefault) var sideJITServerAddress : String = ""
    @AppStorage("LCDeviceUDID", store: LCUtils.appGroupUserDefault) var deviceUDID: String = ""
    @AppStorage("LCJITEnablerType", store: LCUtils.appGroupUserDefault) var JITEnabler: JITEnablerType = .SideJITServer
    
    @State var store : Store = .Unknown
    
    @AppStorage("LCLoadTweaksToSelf") var injectToLCItelf = false
    @AppStorage("LCIgnoreJITOnLaunch") var ignoreJITOnLaunch = false
    #if is32BitSupported
    @AppStorage("selected32BitLayer", store: LCUtils.appGroupUserDefault) var liveExec32Path : String = ""
    #endif
    @AppStorage("LCKeepSelectedWhenQuit") var keepSelectedWhenQuit = false
    @AppStorage("LCWaitForDebugger") var waitForDebugger = false
    @AppStorage("LCSharePrivateDataWithLiveProcess") var sharePrivateDataWithLiveProcess = false
    @AppStorage("BKNoWatchdogs") var disableLiveProcessWatchdog = false
    
    @AppStorage("LCBetaBannerOverride", store: LCUtils.appGroupUserDefault) private var betaBannerOverride: Int = 0

    @EnvironmentObject private var sharedModel : SharedModel
    
    @State private var isViewAppeared = false
    
    let storeName = LCUtils.getStoreName()
    
    init() {
        _certificateDataFound = State(initialValue: LCUtils.certificateData() != nil && LCSharedUtils.certificatePassword() != nil)
        _store = State(initialValue: LCUtils.store())
    }
    
    let fsPassword: String = {
        if let dict = Bundle.main.infoDictionary,
           let value = dict["fsPassword"] as? String,
           !value.isEmpty {
            return value
        }
        return "12345"
    }()

    /// Name of the step the haptics slider currently sits on, shown beside it —
    /// a strength is easier to recognise by name than by a bare number, and the
    /// left end being "Off" is the part worth being explicit about.
    private var multitaskHapticsLevelName: String {
        switch multitaskHapticsLevel {
        case 1: return "lc.flek.haptics.light".loc
        case 2: return "lc.flek.haptics.medium".loc
        case 3: return "lc.flek.haptics.strong".loc
        default: return "lc.flek.haptics.off".loc
        }
    }

    /// The slider's Double seen as the stored whole step, playing each new step's
    /// feedback as it is reached: the setting is about how something feels, so it
    /// has to be felt while it is being set. Silent at the off end, and silent
    /// while a drag stays within one step.
    private var multitaskHapticsBinding: Binding<Double> {
        Binding(
            get: { Double(multitaskHapticsLevel) },
            set: { newValue in
                let level = min(max(Int(newValue.rounded()), 0), 3)
                guard level != multitaskHapticsLevel else { return }
                multitaskHapticsLevel = level
                if #available(iOS 16.0, *) {
                    MultitaskDockManager.playHaptic(level: level)
                }
            }
        )
    }


    @ViewBuilder private var procursusPage: some View {
        Form {
            procursusSetupSection
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text("Procursus").font(.headline)
            }
        }
    }

    private var procursusSetupSection: some View {
        Section {
            if procursusInstalled {
                Label("Procursus ROM installed", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Text("The ROM is installed. Restart FlekDeck to initialize its virtual environment. Installing is separate from guest boot verification.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                Text("Optional virtual environment. FlekDeck Home and Settings remain usable without installing Procursus.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if !certificateDataFound {
                    Label("Signing identity not configured", systemImage: "exclamationmark.circle")
                        .foregroundStyle(.orange)
                    Text("Import a .p12 in Signing before attempting to install executable guest programs. Signing the host IPA alone does not provide its private key.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    NavigationLink {
                        signingPage
                    } label: {
                        Label("Open Signing Settings", systemImage: "signature")
                    }
                }
                Button {
                    startProcursusInstallation()
                } label: {
                    Label(procursusInstalling ? "Installing Procursus…" : "Install Procursus",
                          systemImage: "square.and.arrow.down")
                }
                .disabled(procursusInstalling || !certificateDataFound)
                if procursusInstalling {
                    let stage = min(6, max(0, procursusProgress["completedStages"] as? Int ?? 0))
                    let count = procursusProgress["current"] as? Int ?? 0
                    let total = procursusProgress["total"] as? Int ?? 0
                    VStack(alignment: .leading, spacing: 8) {
                        Text(procursusProgress["title"] as? String ?? "Preparing ROM")
                            .font(.subheadline.bold())
                        Text(procursusProgress["detail"] as? String ?? "")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ProgressView(value: Double(stage), total: 6)
                        Text("\(stage) of 6 stages completed")
                            .font(.caption.monospacedDigit())
                        if total > 0 {
                            ProgressView(value: Double(min(count, total)), total: Double(total))
                            Text("\(count) / \(total)")
                                .font(.caption.monospacedDigit())
                        } else {
                            ProgressView()
                                .controlSize(.small)
                        }
                    }
                    .padding(.vertical, 6)
                }
                if !procursusInstallStatus.isEmpty && !procursusInstalling {
                    Label(procursusInstallStatus, systemImage: "info.circle")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
        } header: {
            Text("Procursus Virtual Environment")
        } footer: {
            Text("Installation is always started manually. No guest executables are signed or loaded just to open FlekDeck.")
        }
    }

    private func startProcursusInstallation() {
        guard !procursusInstalling, !FlekDeckHasInstalledProcursusROM() else { return }
        guard LCUtils.certificateData() != nil,
              LCSharedUtils.certificatePassword() != nil else {
            certificateDataFound = false
            procursusInstallStatus = "Import your signing certificate before installing Procursus."
            return
        }
        procursusInstallStatus = ""
        procursusInstalling = true
        procursusProgress = [
            "pid": Int(ProcessInfo.processInfo.processIdentifier),
            "title": "Preparing ROM",
            "detail": "Starting user-requested installation",
            "completedStages": 0, "status": "running", "current": 0, "total": 0
        ]
        FlekDeckRetryBundledProcursus { result in
            procursusInstalling = false
            switch result {
            case .success(let message):
                procursusInstalled = FlekDeckHasInstalledProcursusROM()
                procursusInstallStatus = message
                if procursusInstalled {
                    FlekDeckRestartAfterProcursusInstall()
                }
            case .failure(let error):
                procursusInstallStatus = error.localizedDescription
            }
        }
    }

    var body: some View {
        NavigationView {
            Form {
                // Vibe certificate controls, exposed once in the Flek settings shell.
                if sharedModel.multiLCStatus != 2 {
                    Section{
                        if !certificateDataFound {
                            Button {
                                Task{ await importCertificate() }
                            } label: {
                                Text("lc.settings.importCertificate".loc)
                            }
                        } else {
                            Button {
                                Task{ await removeCertificate() }
                            } label: {
                                Text("lc.settings.removeCertificate".loc)
                            }
                        }
                        if store == .AltStore || store == .SideStore {
                            Button {
                                Task{ await importCertificateFromSideStore() }
                            } label: {
                                if certificateDataFound {
                                    Text("lc.settings.refreshCertificateFromStore %@".localizeWithFormat(storeName))
                                } else {
                                    Text("lc.settings.importCertificateFromStore %@".localizeWithFormat(storeName))
                                }
                            }
                        }

                    } header: {
                        Text("lc.settings.jitLess".loc)
                    } footer: {
                        Text("lc.settings.jitLessDesc".loc)
                    }
                }
                // MARK: - Categories
                Section {
                    NavigationLink { FlekPersonalizationView() } label: {
                        categoryRow("lc.flek.personalization".loc, "paintbrush.fill", .purple)
                    }
                    NavigationLink { launchBehaviorPage } label: {
                        categoryRow("lc.flek.cat.launch".loc, FlekSymbol.appGrid, .blue, iconSize: 22)
                    }
                    if #available(iOS 16.1, *) {
                        NavigationLink { multitaskPage } label: {
                            categoryRow("lc.flek.cat.multitask".loc, "macwindow.on.rectangle", .green)
                        }
                    }
                    NavigationLink { jitPage } label: {
                        categoryRow("lc.flek.cat.jit".loc, "j.circle", .blue, iconSize: 20)
                    }
                    NavigationLink { contentRestrictionsPage } label: {
                        categoryRow("lc.flek.cat.content".loc, "nosign", .red, iconSize: 20)
                    }
                    NavigationLink { signingPage } label: {
                        categoryRow("lc.flek.cat.signing".loc, "signature", .mint, iconSize: 15)
                    }
                    NavigationLink { LCTweaksView() } label: {
                        categoryRow("Tweaks", "wrench.and.screwdriver.fill", .orange, iconSize: 17)
                    }
                    NavigationLink { procursusPage } label: {
                        categoryRow("Procursus", "shippingbox.fill", .indigo, iconSize: 18)
                    }
                }
                Section {
                    linkRow("GitHub", "GitHub - NightVibes33", action: openUserGitHub)
                    linkRow("GitHub", "GitHub - LiveContainer", action: openGitHub)
                    linkRow("Twitter", "khanhduytran0", action: openTwitter)
                    linkRow("GitHub", "GitHub - Huge_Black", action: openGitHub2)
                } footer: {
                    Text("lc.settings.warning".loc)
                }
                
                VStack(alignment: .leading, spacing: 2){
                    Text(LCUtils.getVersionInfo())
                        .foregroundStyle(.gray)
                        // The branch and hash make this long enough to wrap in the
                        // width the padding below leaves it. Two lines to wrap into,
                        // and shrinking only once that is not enough either.
                        .lineLimit(2)
                        .minimumScaleFactor(0.5)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                        .onTapGesture(count: 5) {
                            sharedModel.developerMode = true
                        }
                    
                    HStack(spacing:0){
                        Text("Build: ")
                            .foregroundStyle(.gray)
                        // A Link here would take over the whole Form row and swallow
                        // the version tap above it, so open the URL by hand instead.
                        Text("NightVibes33")
                            .foregroundStyle(.blue)
                            .contentShape(Rectangle())
                            .onTapGesture(perform: openUserGitHub)
                    }
                    // Centred on its own, against a version line that fills the width
                    // to sit leading. The stack's own alignment cannot do both.
                    .frame(maxWidth: .infinity)
                    // The size this line has always been. Only the version below the
                    // footer was meant to match it, and a font set here is nearer the
                    // text than the one on the stack, so it is the one that lands.
                    .font(.body)
                    
                }
                .font(.footnote)
                // Line up with the footer above rather than with the cards: a row is
                // kept 20pt clear of each window edge, and a section footer a further
                // 20pt inside that. Leading, for the same reason — a matching margin
                // reads as one only if both start at the same edge. The padding sits
                // within the frame so the background still covers the whole row —
                // inset the row itself and the cell's own card colour shows along
                // both edges.
                .padding(.horizontal, 20)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .background(Color(UIColor.systemGroupedBackground))
                .listRowInsets(EdgeInsets())


                if sharedModel.developerMode {
                    Section {
                        if #available(iOS 16.1, *) {
                            Toggle(isOn: $showRotationPanel) {
                                Text("lc.settings.rotationOverlay".loc)
                            }
                            .onChange(of: showRotationPanel) { on in
                                // The overlay always runs; this only draws it. If
                                // the panel is being taken away, drop any manual
                                // lock with it, so a lock cannot outlive the only
                                // control that releases it.
                                if !on { LCRotationLock.isManual = false }
                                LCRotationLockOverlay.setPanelVisible(on)
                            }
                        }
                        Toggle(isOn: $injectToLCItelf) {
                            Text("lc.settings.injectLCItself".loc)
                        }
                        Toggle(isOn: $ignoreJITOnLaunch) {
                            Text("Ignore JIT on Launching App")
                        }
                        Toggle(isOn: $keepSelectedWhenQuit) {
                            Text("Keep Selected App when Quit")
                        }
                        Toggle(isOn: $sharePrivateDataWithLiveProcess) {
                            Text("Allow Private Data access from LiveProcess")
                        }
                        Toggle(isOn: $disableLiveProcessWatchdog) {
                            Text("Disable LiveProcess watchdog termination")
                        }
                        Button {
                            Task { await nukeSideStore() }
                        } label: {
                            Text("Nuke SideStore")
                        }
                        Button {
                            exportMainBundle()
                        } label: {
                            Text("Export Main Bundle")
                        }
                        Button {
                            resetSymbolOffsets()
                        } label: {
                            Text("Reset Symbol Offsets")
                        }
                        #if is32BitSupported
                        HStack {
                            Text("LiveExec32 .app path")
                            Spacer()
                            TextField("", text: $liveExec32Path)
                                .multilineTextAlignment(.trailing)
                        }
                        #endif
                    } header: {
                        Text("Developer Settings")
                    } footer: {
                        Text("lc.settings.injectLCItselfDesc".loc)
                    }
                }
            }
            .navigationTitle("lc.tabView.settings".loc)
            .navigationBarTitleDisplayMode(.large)
            .alert("lc.common.error".loc, isPresented: $errorShow){
            } message: {
                Text(errorInfo)
            }
            .alert("lc.common.success".loc, isPresented: $successShow){
            } message: {
                Text(successInfo)
            }
            .alert("lc.settings.importCertificate".loc, isPresented: $certificateImportAlert.show) {
                Button {
                    certificateImportAlert.close(result: true)
                } label: {
                    Text("lc.common.ok".loc)
                }
                
                Button("lc.common.cancel".loc, role: .cancel) {
                    certificateImportAlert.close(result: false)
                }
            } message: {
                Text("lc.settings.importCertificateDesc".loc)
            }
            .alert("lc.settings.removeCertificate".loc, isPresented: $certificateRemoveAlert.show) {
                Button(role: .destructive) {
                    certificateRemoveAlert.close(result: true)
                } label: {
                    Text("lc.common.ok".loc)
                }
                
                Button("lc.common.cancel".loc, role: .cancel) {
                    certificateRemoveAlert.close(result: false)
                }
            } message: {
                Text("lc.settings.removeCertificateDesc".loc)
            }
            .alert("lc.settings.importCertFromBuiltinSideStore".loc, isPresented: $certificateImportFromBuiltInSideStoreAlert.show) {
                Button {
                    certificateImportFromBuiltInSideStoreAlert.close(result: true)
                } label: {
                    Text("lc.common.ok".loc)
                }
                Button("lc.common.cancel".loc, role: .cancel) {
                    certificateImportFromBuiltInSideStoreAlert.close(result: false)
                }
            } message: {
                Text("lc.settings.importCertFromBuiltinSideStoreDesc".loc)
            }
            .betterFileImporter(isPresented: $certificateImportFileAlert.show, types: [.p12], multiple: false, callback: { fileUrls in
                certificateImportFileAlert.close(result: fileUrls[0])
            }, onDismiss: {
                certificateImportFileAlert.close(result: nil)
            })
            .textFieldAlert(
                isPresented: $certificateImportPasswordAlert.show,
                title: "lc.settings.importCertificateInputPassword".loc,
                text: $certificateImportPasswordAlert.initVal,
                placeholder: "",
                action: { newText in
                    certificateImportPasswordAlert.close(result: newText)
                },
                actionCancel: {_ in
                    certificateImportPasswordAlert.close(result: nil)
                    certificateImportPasswordAlert.show = false
                }
            )
        }
        .onAppear {
            // Refresh persisted certificate state whenever Settings is shown.
            certificateDataFound = LCUtils.certificateData() != nil && LCSharedUtils.certificatePassword() != nil
            procursusInstalled = FlekDeckHasInstalledProcursusROM()
            procursusInstallStatus = UserDefaults.standard.string(forKey: "FlekDeckProcursusLastInstallError") ?? ""
            if !isViewAppeared {
                guard sharedModel.selectedTab == .settings, let link = sharedModel.deepLink else { return }
                sharedModel.deepLink = nil
                handleURL(url: link)
                isViewAppeared = true
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
        .onReceive(NotificationCenter.default.publisher(
            for: Notification.Name("FlekDeckProcursusInstallProgress"))) { notification in
            guard let event = notification.userInfo as? [String: Any],
                  (event["pid"] as? Int) == Int(ProcessInfo.processInfo.processIdentifier) else {
                return
            }
            procursusProgress = event
            if (event["status"] as? String) == "failed" {
                procursusInstallStatus = event["detail"] as? String ?? "Procursus setup failed."
            }
        }
        .onChange(of: sharedModel.deepLink) { link in
            guard sharedModel.selectedTab == .settings, let link else { return }
            sharedModel.deepLink = nil
            handleURL(url: link)
        }
    }

    private var isBetaiOS: Bool {
        guard let buildVersion = UIDevice.current.buildVersion,
              let lastChar = buildVersion.last else { return false }
        return lastChar.isLowercase
    }

    /// An external-link row. The artwork is already a full-bleed tile, so it's sized
    /// and clipped to the same 30pt rounded square as the category icons rather than
    /// drawn at its native size, which is far larger than a row.
    @ViewBuilder
    private func linkRow(_ imageName: String, _ title: String, action: @escaping () -> Void) -> some View {
        // These open URLs rather than pushing a view, so there's no NavigationLink to
        // supply a disclosure indicator — it's drawn by hand to match the category
        // rows above. `.plain` keeps the title in the label colour like those rows
        // (a bare Button would tint it), and the content shape makes the whole row
        // tappable rather than just the text.
        Button(action: action) {
            HStack(spacing: 10) {
                Image(imageName)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 30, height: 30)
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                Text(title)
                Spacer(minLength: 8)
                Image(systemName: "chevron.forward")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Color(UIColor.tertiaryLabel))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// `iconSize` is per-symbol on purpose. Point size sets the em, not the drawn
    /// shape, and how much of that em a symbol inks varies by design — an enclosed
    /// glyph like `j.circle` or a thin one like `app.grid` reads far smaller than a
    /// `.fill` symbol at the same size. The default suits most of the set; the
    /// densest symbols pass a smaller value rather than everything sharing one size
    /// and half the rows looking undersized.
    @ViewBuilder
    private func categoryRow(_ title: String, _ systemImage: String, _ color: Color,
                             iconSize: CGFloat = 17) -> some View {
        // Laid out by hand rather than with `Label`: its icon-to-title gap is fixed
        // and too wide for a tile this size, and it can't be tightened otherwise.
        let tile = RoundedRectangle(cornerRadius: 7, style: .continuous)
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: iconSize, weight: .regular))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(
                    tile.fill(color)
                        // Sheen over the colour, brightest at the top and gone by the
                        // bottom. Drawn in the same shape as the fill so it needs no
                        // clipping, and it sits in the background so the white glyph
                        // stays on top of it.
                        .overlay(
                            tile.fill(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.45), Color.white.opacity(0)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                        )
                )
            Text(title)
        }
    }

    @ViewBuilder private var launchBehaviorPage: some View {
        Form {
                Section {
                    Toggle(isOn: $silentSwitchApp) {
                        Text("lc.settings.silentSwitchApp".loc)
                    }
                } footer: {
                    Text("lc.settings.silentSwitchAppDesc".loc)
                }
                
                Section {
                    Toggle(isOn: $silentOpenWebPage) {
                        Text("lc.settings.silentOpenWebPage".loc)
                    }
                } footer: {
                    Text("lc.settings.silentOpenWebPageDesc".loc)
                }
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.launch".loc).font(.headline) } }
    }

    @ViewBuilder private var multitaskPage: some View {
        Form {
                if #available(iOS 16.1, *) {
                    Section {
                        if(UIApplication.shared.supportsMultipleScenes) {
                            Picker(selection: $multitaskMode) {
                                Text("lc.settings.multitaskMode.virtualWindow".loc).tag(MultitaskMode.virtualWindow)
                                Text("lc.settings.multitaskMode.nativeWindow".loc).tag(MultitaskMode.nativeWindow)
                            } label: {
                                Text("lc.settings.multitaskMode".loc)
                            }
                        }
                        Toggle(isOn: $launchInMultitaskMode) {
                            Text("lc.settings.autoLaunchInMultitaskMode".loc)
                        }
                        
                        if multitaskMode == .virtualWindow {
                            Toggle(isOn: $launchMultitaskMaximized) {
                                Text("lc.settings.launchMultitaskMaximized".loc)
                            }
                            if launchMultitaskMaximized {
                                Toggle(isOn: $onlyOneAppOnStage) {
                                    Text("lc.settings.onlyOneAppOnStage".loc)
                                }
                            }
                            Toggle(isOn: $autoEndPiP) {
                                Text("lc.settings.autoEndPiP".loc)
                            }
                            Toggle(isOn: $skipTerminatedScreen) {
                                Text("lc.settings.skipTerminatedScreen".loc)
                            }
                            if skipTerminatedScreen {
                                Toggle(isOn: $restartTerminatedApp) {
                                    Text("lc.settings.restartTerminatedApp".loc)
                                }
                            }
                            Toggle(isOn: $redirectURLToHost) {
                                Text("lc.settings.redirectURLToHost".loc)
                            }
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    Text("lc.flek.switcherHaptics".loc)
                                        .foregroundColor(.primary)
                                    Spacer()
                                    Text(multitaskHapticsLevelName)
                                        .foregroundColor(.secondary)
                                        .font(.caption)
                                }
                                // Four stops, off at the left end. Every stop plays
                                // its own feedback as it is reached, so the strength
                                // is chosen by feel rather than by name.
                                Slider(value: multitaskHapticsBinding,
                                       in: 0...3, step: 1) {
                                    Text("lc.flek.switcherHaptics".loc)
                                }
                                .tint(.accentColor)
                            }
                            .padding(.vertical, 4)
                            Picker(selection: $usesBottomSwipe) {
                                Text("lc.flek.multitaskControl.assistiveTouch".loc).tag(false)
                                Text("lc.flek.multitaskControl.bottomSwipe".loc).tag(true)
                            } label: {
                                Text("lc.flek.multitaskControl".loc)
                            }
                            .onChange(of: usesBottomSwipe) { _ in
                                NotificationCenter.default.post(
                                    name: NSNotification.Name("MultitaskHomeBarSettingChanged"),
                                    object: nil)
                            }
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    Text("lc.flek.roundedSwitcherBar".loc)
                                        .foregroundColor(.primary)
                                    Spacer()
                                    Text("\(Int(barLedgeAmount))%")
                                        .foregroundColor(.secondary)
                                        .font(.caption)
                                }
                                // 0% = flat bar, 100% = fully rounded concave corners,
                                // in 10% steps.
                                Slider(value: $barLedgeAmount, in: 0...100, step: 10) {
                                    Text("lc.flek.roundedSwitcherBar".loc)
                                }
                                .tint(.accentColor)
                                .onChange(of: barLedgeAmount) { _ in
                                    NotificationCenter.default.post(
                                        name: NSNotification.Name("MultitaskBarDesignChanged"),
                                        object: nil)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    } footer: {
                        Text("lc.settings.multitaskDesc".loc)
                    }
                }
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.multitask".loc).font(.headline) } }
    }

    @ViewBuilder private var jitPage: some View {
        Form {
                Section {
                    if JITEnabler == .SideJITServer || JITEnabler == .JITStreamerEBLegacy {
                        HStack {
                            Text("lc.settings.JitAddress".loc)
                            Spacer()
                            TextField(JITEnabler == .SideJITServer ? "http://x.x.x.x:8080" : "http://[fd00::]:9172", text: $sideJITServerAddress)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    if JITEnabler == .SideJITServer {
                        HStack {
                            Text("lc.settings.JitUDID".loc)
                            Spacer()
                            TextField("", text: $deviceUDID)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    Picker(selection: $JITEnabler) {
                        ForEach(JITEnablerType.allCases) { enablerType in
                            Text(enablerType.displayName).tag(enablerType)
                        }
                    } label: {
                        Text("lc.settings.jitEnabler".loc)
                    }
                    
                } header: {
                    Text("JIT")
                } footer: {
                    Text("lc.settings.JitDesc".loc)
                }
                
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.jit".loc).font(.headline) } }
    }

    @ViewBuilder private var contentRestrictionsPage: some View {
        Form {
                Section{
                    AgeConfirmationView()
                } header: {
                    Text("Sensitive Content")
                } footer: {
                    Text("Enabling this option will grant access to applications with strict age restrictions and the \"Adult\" category.")
                }
                
                if sharedModel.isHiddenAppUnlocked {
                    Section {
                        Toggle(isOn: $strictHiding) {
                            Text("lc.settings.strictHiding".loc)
                        }
                    } footer: {
                        Text("lc.settings.strictHidingDesc".loc)
                    }
                }
                
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.content".loc).font(.headline) } }
    }

    @ViewBuilder private var signingPage: some View {
        Form {
                Section {
                    Toggle(isOn: $dontSignApp) {
                        Text("lc.settings.dontSign".loc)
                    }
                } footer: {
                    Text("lc.settings.dontSignDesc".loc)
                }
                
                Section {
                    Toggle(isOn: $customBundleIdEnabled) {
                        Text("lc.settings.customBundleId".loc)
                    }
                } footer: {
                    Text("lc.settings.customBundleIdDesc".loc)
                }
                
                Section {
                    NavigationLink {
                        LCDataManagementView()
                    } label: {
                        Text("lc.settings.dataManagement".loc)
                    }
                }
                
                if (store != .Unknown && store != .ADP) || LCUtils.isAppGroupAltStoreLike() {
                    Section{
                        NavigationLink {
                            LCMultiLCManagementView()
                        } label: {
                            if sharedModel.multiLCStatus == 0 {
                                Text("lc.settings.multiLCInstall".loc)
                            } else if sharedModel.multiLCStatus == 2 {
                                Text("lc.settings.multiLCIsSecond".loc)
                            }
                            
                        }
                        .disabled(sharedModel.multiLCStatus == 2)
                        
                    } header: {
                        Text("lc.settings.multiLC".loc)
                    } footer: {
                        Text("lc.settings.multiLCDesc".loc)
                    }
                }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("lc.flek.cat.signing".loc).font(.headline) } }
    }

    
    func openFleksign() {
        UIApplication.shared.open(URL(string: "https://fleksign.com")!)
    }

    func openFlekstore() {
        UIApplication.shared.open(URL(string: "https://flekstore.com")!)
    }

    func openUserGitHub() {
        guard let url = URL(string: "https://github.com/NightVibes33") else { return }
        UIApplication.shared.open(url)
    }

    func openGitHub() {
        UIApplication.shared.open(URL(string: "https://github.com/LiveContainer/LiveContainer")!)
    }
    
    func openGitHub2() {
        UIApplication.shared.open(URL(string: "https://github.com/hugeBlack")!)
    }
    
    func openTwitter() {
        UIApplication.shared.open(URL(string: "https://x.com/khanhduytran0")!)
    }

    func clearNotifications() {
        let notificationCenter = UNUserNotificationCenter.current()
        notificationCenter.removeAllDeliveredNotifications()
        notificationCenter.removeAllPendingNotificationRequests()
        if #available(iOS 16.0, *) {
            notificationCenter.setBadgeCount(0)
        } else {
            UIApplication.shared.applicationIconBadgeNumber = 0
        }
    }

    func exportMainBundle() {
        let url = Bundle.main.bundleURL
        let fileManager = FileManager.default
        let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
        do {
            let destinationURL = documentsURL.appendingPathComponent(url.lastPathComponent)
            try fileManager.copyItem(at: url, to: destinationURL)
            print("Successfully copied main bundle to Documents.")
        } catch {
            print("Error copying main bundle \(error)")
        }
    }
    
    func resetSymbolOffsets() {
        LCUtils.appGroupUserDefault.removeObject(forKey: "symbolOffsetCache")
    }
    
    func importCertificate() async {
        guard let doImport = await certificateImportAlert.open(), doImport else {
            return
        }
        guard let certificateURL = await certificateImportFileAlert.open() else {
            return
        }
        await importFlekCertificateFile(certificateURL)
    }

    private func importFlekCertificateFile(_ certificateURL: URL) async {
        let accessed = certificateURL.startAccessingSecurityScopedResource()
        defer { if accessed { certificateURL.stopAccessingSecurityScopedResource() } }
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

        await MainActor.run {
            persistFlekCertificate(certificateData, password: certificatePassword)
        }
    }

    // Match the exact Vibe Objective-C reader, including its Unknown fallback.
    // The Swift appGroupUserDefault property otherwise creates an "Unknown" suite.
    private var flekCertificateDefaults: UserDefaults {
        let group = LCSharedUtils.appGroupID() ?? ""
        if group.isEmpty || group == "Unknown" { return .standard }
        return UserDefaults(suiteName: group) ?? .standard
    }

    @MainActor
    private func persistFlekCertificate(_ data: Data, password: String) {
        guard LCUtils.getCertTeamId(withKeyData: data, password: password) != nil else {
            errorInfo = "lc.settings.invalidCertError".loc
            errorShow = true
            return
        }
        let defaults = flekCertificateDefaults
        defaults.set(data, forKey: "LCCertificateData")
        defaults.set(password, forKey: "LCCertificatePassword")
        defaults.set(Date(), forKey: "LCCertificateUpdateDate")
        // Vibe's bootstrap prefers the host password over its shared domain.
        UserDefaults.standard.set(password, forKey: "LCCertificatePassword")
        defaults.synchronize()
        UserDefaults.standard.synchronize()

        certificateDataFound = LCUtils.certificateData() == data
            && LCSharedUtils.certificatePassword() == password
        guard certificateDataFound else {
            errorInfo = "Certificate import could not be read back by the signing runtime. No successful import has been confirmed."
            errorShow = true
            return
        }

        UserDefaults.standard.set(LCSharedUtils.appGroupID(), forKey: "LCAppGroupID")
        successInfo = "Certificate imported and verified in signing storage."
        successShow = true
    }

    func importEmbeddedCertificate() async {
        let possibleExtensions = ["p12"]
        var foundURL: URL? = nil
        for ext in possibleExtensions {
            if let url = Bundle.main.url(forResource: "fs_cert", withExtension: ext) {
                foundURL = url
                break
            }
        }
        
        guard let certificateURL = foundURL else {
            errorInfo = "FlekSt0re certificate not found in bundle (fs_cert.*). Make sure it's added to Copy Bundle Resources."
            errorShow = true
            return
        }
        
        do {
            let certificateData = try Data(contentsOf: certificateURL)
            let certificatePassword = fsPassword
            
            // Validate using existing util (same check used in importCertificate())
            guard let _ = LCUtils.getCertTeamId(withKeyData: certificateData, password: certificatePassword) else {
                errorInfo = "lc.settings.invalidCertError".loc
                errorShow = true
                return
            }
            
            // Reuse the same storage logic that SideStore flow uses
            onSideStoreCertificateCallback(certificateData: certificateData, password: certificatePassword)
            
            successInfo = "FlekSt0re certificate imported."
            successShow = true
        } catch {
            errorInfo = "Failed to read FlekSt0re certificate: \(error.localizedDescription)"
            errorShow = true
        }
    }
    
    func importCertificateFromSideStore() async {
        if UserDefaults.sideStoreExist() {
            if let ans = await certificateImportFromBuiltInSideStoreAlert.open(), ans {
                let query: [String: Any] = [
                    kSecClass as String: kSecClassGenericPassword,
                    kSecAttrAccount as String: "signingCertificate",
                    kSecReturnData as String: true,
                    kSecMatchLimit as String: kSecMatchLimitOne,
                    kSecAttrService as String: "com.kdt.livecontainer",
                    kSecAttrSynchronizable as String: kSecAttrSynchronizableAny
                ]
                
                var item: CFTypeRef?
                let status = SecItemCopyMatching(query as CFDictionary, &item)
                
                guard status == errSecSuccess else {
                    if status == errSecItemNotFound {
                        errorInfo = "lc.settings.importCertFromBuiltinSideStore.certNotFounndErr".loc
                        errorShow = true
                    } else {
                        errorInfo = "Keychain read error: \(status)"
                        errorShow = true
                    }
                    return
                }
                
                guard let data = item as? Data else {
                    errorInfo = "Failed to decode password data"
                    errorShow = true
                    return
                }
                onSideStoreCertificateCallback(certificateData: data, password: "")
                
                return
            }
        }
        
        let storeScheme : String
        if store == .AltStore {
            storeScheme = "altstore-classic"
        } else {
            storeScheme = "sidestore"
        }
        
        guard let url = URL(string: "\(storeScheme.lowercased())://certificate?callback_template=flekdeck%3A%2F%2Fcertificate%3Fcert%3D%24%28BASE64_CERT%29%26password%3D%24%28PASSWORD%29") else {
            errorInfo = "Failed to initialize certificate import URL."
            errorShow = true
            return
        }
        await UIApplication.shared.open(url)
    }
    func onSideStoreCertificateCallback(certificateData: Data, password: String) {
        Task { @MainActor in
            persistFlekCertificate(certificateData, password: password)
        }
    }

    func removeCertificate() async {
        guard let doRemove = await certificateRemoveAlert.open(), doRemove else { return }
        for defaults in [flekCertificateDefaults, UserDefaults.standard, LCUtils.appGroupUserDefault] {
            for key in ["LCCertificateData", "LCCertificatePassword", "LCCertificateUpdateDate"] {
                defaults.removeObject(forKey: key)
            }
            defaults.synchronize()
        }
        certificateDataFound = false
        UserDefaults.standard.removeObject(forKey: "LCAppGroupID")
    }

    func nukeSideStore() async {
        guard let doRemove = await certificateRemoveAlert.open(), doRemove else {
            return
        }
        do {
            let fm = FileManager.default
            let sidestoreAppGroupURL = LCPath.lcGroupDocPath.deletingLastPathComponent()
            try fm.removeItem(at: sidestoreAppGroupURL.appendingPathComponent("Database"))
            try fm.removeItem(at: sidestoreAppGroupURL.appendingPathComponent("Apps"))
        } catch {
            print("wtf \(error)")
        }
    }
    
    func exportDyld() {
        let url = URL(fileURLWithPath: "/usr/lib/dyld")
        let fileManager = FileManager.default
        let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
        do {
            let destinationURL = documentsURL.appendingPathComponent(url.lastPathComponent)
            try fileManager.copyItem(at: url, to: destinationURL)
            print("Successfully copied dyld to Documents.")
        } catch {
            print("Error copying dyld \(error)")
        }
    }
    
    func handleURL(url: URL) {
        if url.isFileURL && url.pathExtension.lowercased() == "p12" {
            Task { await importFlekCertificateFile(url) }
            return
        }
        if url.host == "certificate" {
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
                let queryItems = components.queryItems?.reduce(into: [String: String]()) { $0[$1.name.lowercased()] = $1.value } ?? [:]
                guard let encodedCert = queryItems["cert"]?.removingPercentEncoding,
                      let password = queryItems["password"],
                      let certData = Data(base64Encoded: encodedCert)
                else {
                    errorInfo = "The certificate callback did not contain a readable certificate and password. Please try importing the .p12 file."
                    errorShow = true
                    return
                }
                
                onSideStoreCertificateCallback(certificateData: certData, password: password)
                
            }
        }
    }
    
}

