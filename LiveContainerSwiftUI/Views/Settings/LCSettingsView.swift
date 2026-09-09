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
    @State private var showIdentityReport = false
    @State var errorShow = false
    @State var errorInfo = ""
    @State var successShow = false
    @State var successInfo = ""
    @StateObject private var installLC2Alert = AlertHelper<Int>()
    @State private var certificateDataFound = false
    
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
    
    // Written from inside LiveProcess by LCHostIdentityInit. The extension has no
    // UI of its own and cannot be attached to on someone else's device, so the app
    // group is the only way to see whether the identifier reached a parallel guest.
    @AppStorage("LCHostIdentityStatus", store: LCUtils.appGroupUserDefault)
    private var hostIdentityStatus: String = ""

    @AppStorage("LCHostIdentityUdid", store: LCUtils.appGroupUserDefault)
    private var hostIdentityUdid: String = ""

    @AppStorage("LCHostIdentityDetail", store: LCUtils.appGroupUserDefault)
    private var hostIdentityDetail: String = ""

    // Published by this app at launch for the extension to pick up.
    @AppStorage("LCHostEncryptedUdid", store: LCUtils.appGroupUserDefault)
    private var publishedEncryptedUdid: String = ""

    // How many times guest code actually asked the extension for the identifier,
    // and who asked first. Installing the hook and being read are different facts.
    @AppStorage("LCHostIdentityReads", store: LCUtils.appGroupUserDefault)
    private var hostIdentityReads: Int = -1

    @AppStorage("LCHostIdentityReader", store: LCUtils.appGroupUserDefault)
    private var hostIdentityReader: String = ""

    // Size and build date of the dylib that read the identifier, so two devices can
    // be compared from screenshots when the files themselves cannot be moved.
    @AppStorage("LCHostIdentityReaderFingerprint", store: LCUtils.appGroupUserDefault)
    private var hostIdentityReaderFingerprint: String = ""

    // The guest names itself. The image name above can only ever say which
    // library made the call, and resolves to nothing when the caller sits in a
    // hook trampoline — which is why this row used to say only "guest code".
    @AppStorage("LCHostIdentityReaderApp", store: LCUtils.appGroupUserDefault)
    private var hostIdentityReaderApp: String = ""
    
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

    // Kept as separate lines on purpose. "What this app published" and "what a
    // parallel guest actually resolved" are different facts, and collapsing them
    // into one value hides the case worth catching: a guest that read an
    // identifier belonging to some other install.
    private var multitaskIdentityValue: String {
        hostIdentityUdid.isEmpty ? "" : hostIdentityUdid
    }

    // These live in app group defaults, which outlive the app itself — reinstalling
    // does not clear them. So a status with no timestamp beside it may well be from
    // a previous install, which is exactly how a diagnostic starts lying.
    private var multitaskIdentityDate: Date? {
        LCUtils.appGroupUserDefault.object(forKey: "LCHostIdentityDate") as? Date
    }

    // One line for the row. Everything else moved behind a tap once this grew past
    // what a Settings row can show — a truncated diagnostic is worse than a short
    // one, because the ellipsis hides exactly the part being looked for.
    private var multitaskIdentitySummary: String {
        guard !hostIdentityStatus.isEmpty else {
            return publishedEncryptedUdid.isEmpty
                ? "This app has no identifier to publish"
                : "Launch an app in parallel to confirm it arrives"
        }
        let carried = hostIdentityUdid.isEmpty ? "Not carried" : "Carried"
        switch hostIdentityReads {
        case ..<0: return "\(carried) · read count pending · tap for detail"
        case 0: return "\(carried) · never read · tap for detail"
        default:
            let reader = hostIdentityReader.isEmpty ? "guest code" : hostIdentityReader
            return "\(carried) · read \(hostIdentityReads)× by \(reader) · tap for detail"
        }
    }

    // The full picture, for the alert and the clipboard. Copyable matters more than
    // readable here: comparing two devices means sending this to someone else.
    private var multitaskIdentityReport: String {
        var lines: [String] = []
        lines.append("App: \(publishedEncryptedUdid.isEmpty ? "—" : publishedEncryptedUdid)")
        lines.append("Guest: \(hostIdentityUdid.isEmpty ? "—" : hostIdentityUdid)")
        if hostIdentityStatus.isEmpty {
            lines.append("No app has been launched in parallel yet.")
        } else {
            lines.append(hostIdentityDetail.isEmpty ? hostIdentityStatus : "\(hostIdentityStatus) (\(hostIdentityDetail))")
            if let date = multitaskIdentityDate {
                lines.append("Recorded \(date.formatted(.relative(presentation: .numeric)))")
            }
            switch hostIdentityReads {
            case ..<0: lines.append("Read count not reported yet")
            case 0: lines.append("Never read by the guest")
            default:
                let app = hostIdentityReaderApp.isEmpty ? "guest code" : hostIdentityReaderApp
                lines.append("Read \(hostIdentityReads)× by \(app)")
                if !hostIdentityReader.isEmpty {
                    lines.append("via \(hostIdentityReader)")
                }
                if !hostIdentityReaderFingerprint.isEmpty {
                    lines.append(hostIdentityReaderFingerprint)
                }
            }
        }
        return lines.joined(separator: "\n")
    }

    // Orange only when something is genuinely wrong: a parallel launch that produced
    // no identifier, or one that produced an identifier this app never published.
    private var multitaskIdentityIsProblem: Bool {
        if hostIdentityStatus.isEmpty {
            return publishedEncryptedUdid.isEmpty
        }
        if hostIdentityUdid.isEmpty {
            return true
        }
        if hostIdentityReads == 0 {
            return true
        }
        return !publishedEncryptedUdid.isEmpty && hostIdentityUdid != publishedEncryptedUdid
    }

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

    var body: some View {
        NavigationView {
            Form {
                Section {
                    // Developer-only. This is a diagnostic — it exists to compare what the
                    // guest's identity check actually saw against what the app holds — and it
                    // means nothing to anyone not chasing that particular mismatch.
                    if sharedModel.developerMode {
                        HStack(spacing: 12) {
                            Image(systemName: "square.on.square")
                                .font(.system(size: 20))
                                .foregroundColor(.white)
                                .frame(width: 36, height: 36)
                                .background(Color.indigo)
                                .cornerRadius(8)

                            VStack(alignment: .leading, spacing: 2) {
                                Text("Multitask UDID")
                                    .font(.body)

                                Text("App: \(publishedEncryptedUdid.isEmpty ? "—" : publishedEncryptedUdid)")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.3)

                                Text("Guest: \(multitaskIdentityValue.isEmpty ? "—" : multitaskIdentityValue)")
                                    .font(.subheadline)
                                    .foregroundColor(multitaskIdentityIsProblem ? .orange : .secondary)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.3)

                                Text(multitaskIdentitySummary)
                                    .font(.caption)
                                    .foregroundColor(multitaskIdentityIsProblem ? .orange : .secondary)
                                    .lineLimit(2)
                                    .minimumScaleFactor(0.8)
                            }
                            Spacer()

                            if !multitaskIdentityValue.isEmpty {
                                Button(action: {
                                    UIPasteboard.general.string = multitaskIdentityValue
                                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                }) {
                                    Image(systemName: "doc.on.doc")
                                        .font(.system(size: 18))
                                        .foregroundColor(.blue)
                                }
                            }
                        }
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            UIPasteboard.general.string = multitaskIdentityReport
                            UIImpactFeedbackGenerator(style: .light).impactOccurred()
                            showIdentityReport = true
                        }
                        .alert("Multitask UDID", isPresented: $showIdentityReport) {
                            Button("OK", role: .cancel) {}
                        } message: {
                            Text("\(multitaskIdentityReport)\n\nCopied to clipboard.")
                        }
                    }
                }
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

                        NavigationLink {
                            LCJITLessDiagnoseView()
                        } label: {
                            Text("lc.settings.jitlessDiagnose".loc)
                        }

                    } header: {
                        Text("lc.settings.jitLess".loc)
                    } footer: {
                        Text("lc.settings.jitLessDesc".loc)
                    }
                }
                // MARK: - Categories
                Section {
                    NavigationLink { FlekCustomizationView() } label: {
                        categoryRow("Customization", "paintbrush.pointed.fill", .purple)
                    }
                    NavigationLink { FlekControllerSettingsView() } label: {
                        categoryRow("Controller Mode", "gamecontroller.fill", .indigo, iconSize: 16)
                    }
                    NavigationLink { FlekHTTPServerView() } label: {
                        categoryRow("HTTP Server", "network", .green, iconSize: 16)
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
                    NavigationLink { FlekVibeTweaksView() } label: {
                        categoryRow("Tweaks", "wrench.and.screwdriver.fill", .orange, iconSize: 17)
                    }
                }
                Section {
                    linkRow("FlekIconFlekStore", "FlekSt0re.com", action: openFlekstore)
                    linkRow("GitHub", "GitHub - LiveContainer", action: openGitHub)
                    linkRow("Twitter", "khanhduytran0", action: openTwitter)
                    linkRow("GitHub", "GitHub - Huge_Black", action: openGitHub2)
                } footer: {
                    Text("lc.settings.warning".loc)
                }
                
                VStack(alignment: .leading, spacing: 2){
                    Text(LCUtils.getVersionInfo())
                        .foregroundStyle(.gray)
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
                        Text("FlekSt0re")
                            .foregroundStyle(.blue)
                            .contentShape(Rectangle())
                            .onTapGesture(perform: openFlekstore)
                    }
                    .frame(maxWidth: .infinity)
                    .font(.body)
                    
                }
                .font(.footnote)
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
                        Toggle(isOn: $waitForDebugger) {
                            Text("Wait For Debugger")
                        }
                        Toggle(isOn: $sharePrivateDataWithLiveProcess) {
                            Text("Allow Private Data access from LiveProcess")
                        }
                        Toggle(isOn: $disableLiveProcessWatchdog) {
                            Text("Disable LiveProcess watchdog termination")
                        }
                        Button {
                            exportDyld()
                        } label: {
                            Text("Export Dyld")
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
            certificateDataFound = LCUtils.certificateData() != nil && LCSharedUtils.certificatePassword() != nil
            if !isViewAppeared {
                guard sharedModel.selectedTab == .settings, let link = sharedModel.deepLink else { return }
                sharedModel.deepLink = nil
                handleURL(url: link)
                isViewAppeared = true
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
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

    @ViewBuilder
    private func linkRow(_ imageName: String, _ title: String, action: @escaping () -> Void) -> some View {
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

    @ViewBuilder
    private func categoryRow(_ title: String, _ systemImage: String, _ color: Color,
                             iconSize: CGFloat = 17) -> some View {
        let tile = RoundedRectangle(cornerRadius: 7, style: .continuous)
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: iconSize, weight: .regular))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(
                    tile.fill(color)
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
                        
                        if(sharedModel.multiLCStatus == 2) {
                            NavigationLink {
                                LCJITLessDiagnoseView()
                            } label: {
                                Text("lc.settings.jitlessDiagnose".loc)
                            }
                        }
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
            guard let _ = LCUtils.getCertTeamId(withKeyData: certificateData, password: certificatePassword) else {
                errorInfo = "lc.settings.invalidCertError".loc
                errorShow = true
                return
            }
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
