//
//  TabView.swift
//  LiveContainerSwiftUI
//
//  Created by s s on 2024/8/21.
//

import Foundation
import SwiftUI
import ObjectiveC

struct LCTabView: View {
    @State var errorShow = false
    @State var crashReportShow = false
    @State var errorInfo = ""
    @State private var isiOSBeta = false
    @AppStorage("LCBetaBannerOverride", store: LCUtils.appGroupUserDefault) private var betaBannerOverride: Int = 0
    
    @State var previousSelectedTab : LCTabIdentifier = .apps
    @State private var didRunStartup = false
    
    @EnvironmentObject var sharedModel : SharedModel
    @EnvironmentObject var sceneDelegate: SceneDelegate
    @State var shouldToggleMainWindowOpen = false

    
    @StateObject var searchContextAppList = SearchContext()
    @StateObject var searchContextSource = SearchContext()
    
    let pub = NotificationCenter.default.publisher(for: UIScene.didDisconnectNotification)
    
    var body: some View {
        // FlekDeck: the springboard home screen replaces the old tab bar.
        // Startup is local; there is no FlekSt0re device/access gate.
        LCAppListView(searchContext: searchContextAppList)
        .modifier(DeferBottomHomeGestureModifier())
        .alert("lc.common.error".loc, isPresented: $errorShow) {
            Button("lc.common.ok".loc) {}
            Button("lc.common.copy".loc) { copyError() }
        } message: {
            Text(errorInfo)
        }
        .sheet(isPresented: $crashReportShow) {
            NavigationView {
                ScrollView {
                    Text(errorInfo)
                        .font(.system(size: 12).monospaced())
                        .fixedSize(horizontal: false, vertical: false)
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("lc.common.copy".loc, action: {
                            copyError()
                        })
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("lc.common.ok".loc, action: {
                            crashReportShow = false
                        })
                    }
                }
                .navigationTitle("lc.common.error".loc)
                .navigationBarTitleDisplayMode(.inline)
            }
        }
        .task {
            setupInitialRepositoriesIfNeeded()
            Task { await MultiRepoSearchModel.prefetchAllRepos() }
            await runStartupIfNeeded()
        }
        .onReceive(pub) { out in
            if let scene1 = sceneDelegate.window?.windowScene, let scene2 = out.object as? UIWindowScene, scene1 == scene2 {
                if shouldToggleMainWindowOpen {
                    DataManager.shared.model.mainWindowOpened = false
                }
            }
        }
        .onChange(of: sharedModel.selectedTab) { newValue in
            if newValue != LCTabIdentifier.search {
                previousSelectedTab = newValue
            }
        }
        .onChange(of: betaBannerOverride) { _ in
            updateBetaOverlay()
        }
        .onOpenURL { url in
            dispatchURL(url: url)
        }
        .onChange(of: sharedModel.pendingOpenURL) { _ in
            processPendingURLIfNeeded()
        }
    }
    
    func dispatchURL(url: URL) {
        repeat {
            if url.isFileURL {
                sharedModel.selectedTab = .apps
                break
            }
            if url.scheme?.lowercased() == "sidestore" {
                sharedModel.selectedTab = .apps
                break
            }
            
            guard let host = url.host?.lowercased() else {
                return
            }
            
            switch host {
            case "livecontainer-launch", "install", "open-web-page", "open-url":
                sharedModel.selectedTab = .apps
            case "certificate":
                sharedModel.selectedTab = .settings
            case "source":
                sharedModel.selectedTab = .sources
            default:
                return
            }
            
        } while(false)
        
        sharedModel.deepLink = url
    }

    /// Takes whatever URL is waiting, if this window is in a state to act on it.
    /// Every window runs this, and the first one through clears the URL, so a
    /// window that is about to be closed as a duplicate can park a document and
    /// have the window that stays open install it.
    func processPendingURLIfNeeded() {
        guard let url = sharedModel.pendingOpenURL else {
            return
        }
        sharedModel.pendingOpenURL = nil
        dispatchURL(url: url)
    }
    
    // MARK: - Existing helper functions
    func closeDuplicatedWindow() {
        if let session = sceneDelegate.window?.windowScene?.session, DataManager.shared.model.mainWindowOpened {
            UIApplication.shared.requestSceneSessionDestruction(session, options: nil) { e in
                print(e)
            }
        } else {
            shouldToggleMainWindowOpen = true
        }
        DataManager.shared.model.mainWindowOpened = true
    }
    
    func checkLastLaunchError() {
        var errorStr = UserDefaults.standard.string(forKey: "error")
        if errorStr == nil && UserDefaults.standard.bool(forKey: "SigningInProgress") {
            errorStr = "lc.signer.crashDuringSignErr".loc
            UserDefaults.standard.removeObject(forKey: "SigningInProgress")
        }
        guard let errorStr else { return }
        UserDefaults.standard.removeObject(forKey: "error")
        errorInfo = errorStr
        crashReportShow = true
    }
    
    func copyError() { UIPasteboard.general.string = errorInfo }
    
    
    func checkTeamId() {
        if let certificateTeamId = UserDefaults.standard.string(forKey: "LCCertificateTeamId") {
            if DataManager.shared.model.multiLCStatus != 2 {
                return
            }
            
            guard let primaryLCTeamId = Bundle.main.infoDictionary?["PrimaryLiveContainerTeamId"] as? String else {
                print("Unable to find PrimaryLiveContainerTeamId")
                return
            }
            if certificateTeamId != primaryLCTeamId {
                errorInfo = "lc.settings.multiLC.teamIdMismatch".loc
                errorShow = true
                return
            }
            return
        }
        
        guard let currentTeamId = LCSharedUtils.teamIdentifier() else {
            print("Failed to determine team id.")
            return
        }
        
        if DataManager.shared.model.multiLCStatus == 2 {
            guard let primaryLCTeamId = Bundle.main.infoDictionary?["PrimaryLiveContainerTeamId"] as? String else {
                print("Unable to find PrimaryLiveContainerTeamId")
                return
            }
            if currentTeamId != primaryLCTeamId {
                errorInfo = "lc.settings.multiLC.teamIdMismatch".loc
                errorShow = true
                return
            }
        }
        UserDefaults.standard.set(currentTeamId, forKey: "LCCertificateTeamId")
    }
    
    func checkAndSaveBundleId() {
        if DataManager.shared.model.multiLCStatus == 2 {
            let scheme = UserDefaults.lcAppUrlScheme() ?? ""
            LCUtils.appGroupUserDefault.set(Bundle.main.bundleIdentifier, forKey: "LCBundleID.\(scheme)")
        }
        
        if UserDefaults.standard.bool(forKey: "LCBundleIdChecked") {
            return
        }
        
        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "application-identifier" as CFString, nil), let appIdentifier = value.takeRetainedValue() as? String else {
            errorInfo = "Unable to determine application-identifier"
            errorShow = true
            return
        }
        
        guard let bundleId = Bundle.main.bundleIdentifier else {
            return
        }
        
        var correctBundleId = ""
        if appIdentifier.count > 11 {
            let startIndex = appIdentifier.index(appIdentifier.startIndex, offsetBy: 11)
            correctBundleId = String(appIdentifier[startIndex...])
        }
        
        if(bundleId != correctBundleId) {
            errorInfo = "lc.settings.bundleIdMismatch %@ %@".localizeWithFormat(bundleId, correctBundleId)
            //errorShow = true
        }
        UserDefaults.standard.set(true, forKey: "LCBundleIdChecked")
    }
    
    func checkGetTaskAllow() {
        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil), (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {
            errorInfo = "lc.settings.notDevCert".loc
            errorShow = true
            return
        }
    }
    
    private func setupInitialRepositoriesIfNeeded() {
        let didSetupKey = "DidSetupDefaultRepositories"
        
        guard !UserDefaults.standard.bool(forKey: didSetupKey) else {
            return
        }
        
        let defaultApps: [AppRepository] = [
            AppRepository(
                name: "FlekSt0re Lib",
                iconUrl: "https://flekstore.com/pro_app/icons/apple-touch-icon.png",
                sourceURL: "Default app catalog",
                isSelected: true
            ),
            AppRepository(
                name: "Nabzclan - App Store",
                iconUrl: "https://cdn.nabzclan.vip/popupv3/imgs/logo-tras.png",
                sourceURL: "https://appstore.nabzclan.vip/repos/altstore.php",
                isSelected: false
            ),
            AppRepository(
                name: "AppTesters IPA Repo",
                iconUrl: "https://apptesters.org/apptesters-512x512.png",
                sourceURL: "https://repository.apptesters.org/",
                isSelected: false
            ),
            AppRepository(
                name: "Quantum Source",
                iconUrl: "https://quarksources.github.io/assets/ElementQ-Circled.png",
                sourceURL: "https://quarksources.github.io/dist/quantumsource.min.json",
                isSelected: false
            )
        ]
        
        if let data = try? JSONEncoder().encode(defaultApps) {
            UserDefaults.standard.set(data, forKey: "savedRepositories")
        }
        UserDefaults.standard.set(true, forKey: didSetupKey)
        
    }
    @MainActor
    private func runStartupIfNeeded() {
        guard !didRunStartup else { return }
        didRunStartup = true

        sharedModel.selectedTab = .apps
        closeDuplicatedWindow()
        checkLastLaunchError()
        checkTeamId()
        checkAndSaveBundleId()
        checkGetTaskAllow()
        checkPrivateContainerBookmark()
        checkiOSBeta()
        processPendingURLIfNeeded()
    }

    func checkiOSBeta() {
        // Beta iOS builds have a build version ending with a lowercase letter (e.g. 22A5307f)
        if let buildVersion = UIDevice.current.buildVersion,
           let lastChar = buildVersion.last,
           lastChar.isLowercase {
            isiOSBeta = true
        }
        updateBetaOverlay()
    }

    private func updateBetaOverlay() {
        let shouldShow: Bool
        switch betaBannerOverride {
        case 1: shouldShow = true
        case 2: shouldShow = false
        default: shouldShow = isiOSBeta
        }

        if let scene = sceneDelegate.window?.windowScene {
            if shouldShow {
                BetaOverlayManager.shared.show(on: scene)
            } else {
                BetaOverlayManager.shared.hide()
            }
        }
    }

    func checkPrivateContainerBookmark() {
        if sharedModel.multiLCStatus == 2 {
            return
        }
        if LCUtils.appGroupUserDefault.object(forKey: "LCLaunchExtensionPrivateDocBookmark") != nil {
            return
        }
        
        guard let bookmark = LCUtils.bookmark(for: LCPath.docPath) else {
            errorInfo = "Failed to create bookmark for Documents folder?"
            errorShow = true
            return
        }
        LCUtils.appGroupUserDefault.set(bookmark, forKey: "LCLaunchExtensionPrivateDocBookmark")
    }
}
/// Requires a double-swipe to trigger the bottom system edge gesture
/// (swipe-up-to-home), preventing accidental exits.
///
/// The home indicator is intentionally left VISIBLE. iOS treats hiding the
/// indicator and deferring the home gesture as mutually exclusive: the deferral
/// works by revealing the indicator on the first swipe and only performing the
/// gesture on the second, so if the indicator is already hidden a single swipe
/// exits and the deferral has no effect. Showing the indicator is therefore a
/// hard requirement for the two-swipe behaviour — do not re-add
/// `.persistentSystemOverlays(.hidden)` here.
private struct DeferBottomHomeGestureModifier: ViewModifier {
    // Erased to AnyView: `defersSystemGestures` is iOS 16+, and an opaque return
    // type would bake its modifier type into Body. The runtime resolves Body
    // before the availability check ever runs, so iOS 15 would trap here.
    func body(content: Content) -> AnyView {
        if #available(iOS 16.0, *) {
            return AnyView(
                content
                    .defersSystemGestures(on: .bottom)
                    // SwiftUI's `.defersSystemGestures(on:)` frequently fails to
                    // propagate `preferredScreenEdgesDeferringSystemGestures` to the
                    // window's view controllers, so also install it directly on the
                    // hosting controller at runtime as a reliable backstop.
                    .background(BottomEdgeGestureDeferralInstaller())
            )
        }
        return AnyView(content)
    }
}

/// Zero-size helper that, once attached to a window, forces iOS to defer the
/// bottom screen-edge system gesture (swipe-up-to-home) by installing
/// `preferredScreenEdgesDeferringSystemGestures` directly on SwiftUI's
/// UIHostingController base class. This is the reliable path when the SwiftUI
/// `.defersSystemGestures` modifier is ignored.
///
/// Caveat: this preference is advisory. iOS still overrides it whenever it
/// decides the user clearly intends to go home, so a firm, deliberate swipe may
/// still leave in a single gesture on some devices / iOS versions — Apple
/// intentionally protects the home gesture and this cannot be fully defeated.
private struct BottomEdgeGestureDeferralInstaller: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = InstallerView()
        view.isUserInteractionEnabled = false
        view.backgroundColor = .clear
        return view
    }
    func updateUIView(_ uiView: UIView, context: Context) {}

    private final class InstallerView: UIView {
        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard let root = window?.rootViewController else { return }
            ScreenEdgeGestureDeferrer.install(fromRoot: root)
        }
    }
}

/// Runtime swizzler that makes every SwiftUI `UIHostingController` report the
/// bottom edge as deferring system gestures.
private enum ScreenEdgeGestureDeferrer {
    /// Hosting classes already swizzled, so repeated installs are no-ops.
    private static var swizzledClasses = Set<ObjectIdentifier>()

    static func install(fromRoot root: UIViewController) {
        let base = hostingControllerBaseClass(of: root) ?? object_getClass(root)
        swizzle(hostingBase: base)
        refresh(from: root)
    }

    /// Walks up the class hierarchy of `vc` and returns the highest-level class
    /// whose name identifies it as a SwiftUI `UIHostingController` — the base
    /// that every specialised `UIHostingController<Content>` inherits from, so
    /// swizzling it covers the root screen and every full-screen cover alike.
    private static func hostingControllerBaseClass(of vc: UIViewController) -> AnyClass? {
        var result: AnyClass? = nil
        var cls: AnyClass? = object_getClass(vc)
        while let c = cls {
            if String(cString: class_getName(c)).contains("UIHostingController") {
                result = c
            }
            cls = class_getSuperclass(c)
        }
        return result
    }

    private static func swizzle(hostingBase cls: AnyClass?) {
        guard let cls else { return }
        let id = ObjectIdentifier(cls)
        guard !swizzledClasses.contains(id) else { return }
        swizzledClasses.insert(id)

        // preferredScreenEdgesDeferringSystemGestures → previous value ∪ .bottom
        let preferredSel = #selector(getter: UIViewController.preferredScreenEdgesDeferringSystemGestures)
        if let method = class_getInstanceMethod(cls, preferredSel) {
            let previousIMP = method_getImplementation(method)
            let typeEnc = method_getTypeEncoding(method)
            let block: @convention(block) (UIViewController) -> UIRectEdge = { obj in
                typealias Getter = @convention(c) (UIViewController, Selector) -> UIRectEdge
                let previous = unsafeBitCast(previousIMP, to: Getter.self)(obj, preferredSel)
                return previous.union(.bottom)
            }
            class_replaceMethod(cls, preferredSel, imp_implementationWithBlock(block), typeEnc)
        }

        // childForScreenEdgesDeferringSystemGestures → nil, so the system reads
        // each hosting controller's own (now-deferred) preference instead of
        // forwarding to a child SwiftUI never wired up. This is a distinct path
        // from the home-indicator-hidden forwarding, which is left untouched.
        let childSel = #selector(getter: UIViewController.childForScreenEdgesDeferringSystemGestures)
        if let method = class_getInstanceMethod(cls, childSel) {
            let typeEnc = method_getTypeEncoding(method)
            let block: @convention(block) (UIViewController) -> UIViewController? = { _ in nil }
            class_replaceMethod(cls, childSel, imp_implementationWithBlock(block), typeEnc)
        }
    }

    /// Asks the current controller stack to re-query the now-swizzled prefs.
    private static func refresh(from root: UIViewController) {
        var vc: UIViewController? = root
        while let current = vc {
            current.setNeedsUpdateOfScreenEdgesDeferringSystemGestures()
            vc = current.presentedViewController
        }
    }
}
