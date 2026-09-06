#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def load(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def save(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex(text: str, pattern: str, replacement: str, label: str) -> str:
    out, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return out


# ---------------------------------------------------------------------------
# New FlekDeck installer: remove every premium branch instead of spoofing a
# subscription response. External sources become ordinary install sources.
# ---------------------------------------------------------------------------
installer_path = "LiveContainerSwiftUI/FlekDeck/Install/FlekInstallerView.swift"
s = load(installer_path)
s = exact(s, "    @State private var showPremium = false\n", "", "installer showPremium state")
s = exact(s, "            await viewModel.refreshSubscriptionStatus()\n", "", "installer subscription refresh")
s = exact(
    s,
    "        .sheet(isPresented: $showPremium) {\n            PremiumRequiredView()\n        }\n",
    "",
    "installer premium sheet",
)
s = exact(
    s,
    "                requiresPremium: requiresPremium(fromFlekstore: target.isFlekstore),\n",
    "",
    "installer detail premium argument",
)
s = regex(
    s,
    r"    private func install\(_ app: FSAppModel\) \{.*?    /// Queues the download \+ install and counts the FlekSt0re download\.",
    """    private func install(_ app: FSAppModel) {\n        enqueueInstall(app, fromFlekstore: viewModel.repository == .flekstore)\n    }\n\n    private func installSearchResult(_ app: FSAppModel, fromFlekstore: Bool) {\n        enqueueInstall(app, fromFlekstore: fromFlekstore)\n    }\n\n    /// Queues the download + install and counts the FlekSt0re download.""",
    "installer premium install guards",
)
save(installer_path, s)


# ---------------------------------------------------------------------------
# App detail sheet: install/cancel directly; no premium state or modal.
# ---------------------------------------------------------------------------
detail_path = "LiveContainerSwiftUI/FlekDeck/Install/FlekAppDetailSheet.swift"
s = load(detail_path)
s = regex(
    s,
    r"    /// True when this source is behind the subscription\..*?    let requiresPremium: Bool\n",
    "",
    "detail premium property",
)
s = s.replace("    /// The premium gate is applied before this is called.\n", "")
s = exact(s, "    @State private var showPremium = false\n", "", "detail showPremium state")
s = exact(
    s,
    "        .sheet(isPresented: $showPremium) {\n            PremiumRequiredView()\n        }\n",
    "",
    "detail premium sheet",
)
s = exact(
    s,
    """        Button {\n            if requiresPremium {\n                showPremium = true\n            } else if installItem != nil {\n""",
    """        Button {\n            if installItem != nil {\n""",
    "detail premium button gate",
)
save(detail_path, s)


# ---------------------------------------------------------------------------
# Root view: remove the FlekSt0re UDID/device-status gate completely. Startup is
# local and deterministic; no access-verification/ban/payment screen exists.
# ---------------------------------------------------------------------------
tab_path = "LiveContainerSwiftUI/Views/LCTabView.swift"
s = load(tab_path)
s = exact(
    s,
    """    @State var previousSelectedTab : LCTabIdentifier = .apps\n    @State private var isBlocked = false\n    @State private var hasCheckedBlockedStatus = false\n    @State private var didFailBlockedStatusCheck = false\n    @State private var didRunPostGateStartup = false\n    @State private var isVerifyingAccess = false\n    @State private var accessVerificationFailureMessage = \"Please check your internet connection and try again.\"\n    @State private var blockedReason = \"Unavailable\"\n    @State private var blockedMessage = \"Your access has been limited by the service.\"\n    @AppStorage(\"FSEncryptedUDID\") private var encryptedUDID: String = \"\"\n""",
    """    @State var previousSelectedTab : LCTabIdentifier = .apps\n    @State private var didRunStartup = false\n""",
    "root access state",
)
s = s.replace("    @Environment(\\.scenePhase) var scenePhase\n", "")
s = exact(
    s,
    """    var body: some View {\n        Group {\n            if !hasCheckedBlockedStatus {\n                ZStack {\n                    Color.black.ignoresSafeArea()\n                    ProgressView()\n                        .tint(.white)\n                }\n            } else if didFailBlockedStatusCheck {\n                AccessVerificationFailedView(message: accessVerificationFailureMessage) {\n                    Task {\n                        await verifyAccess(forceNetworkCheck: true)\n                    }\n                }\n            } else if isBlocked {\n                AccessBlockedView(reason: blockedReason, message: blockedMessage)\n            } else {\n                // FlekDeck: the springboard home screen replaces the old tab bar.\n                // Settings and the Installer are now opened as full-screen pages from\n                // the home screen instead of being separate tabs.\n                LCAppListView(searchContext: searchContextAppList)\n            }\n        }\n        .modifier(DeferBottomHomeGestureModifier())\n""",
    """    var body: some View {\n        // FlekDeck: the springboard home screen replaces the old tab bar.\n        // Startup is local; there is no FlekSt0re device/access gate.\n        LCAppListView(searchContext: searchContextAppList)\n        .modifier(DeferBottomHomeGestureModifier())\n""",
    "root gated body",
)
s = exact(
    s,
    """        .task {\n            setupInitialRepositoriesIfNeeded()\n            Task { await MultiRepoSearchModel.prefetchAllRepos() }\n            await verifyAccess()\n        }\n""",
    """        .task {\n            setupInitialRepositoriesIfNeeded()\n            Task { await MultiRepoSearchModel.prefetchAllRepos() }\n            await runStartupIfNeeded()\n        }\n""",
    "root startup task",
)
s = regex(
    s,
    r"        \.onChange\(of: scenePhase\) \{ newPhase in.*?        \}\n        \.onOpenURL",
    "        .onOpenURL",
    "root foreground access refresh",
)
s = exact(
    s,
    """        if isBlocked || didFailBlockedStatusCheck || !hasCheckedBlockedStatus {\n            sharedModel.pendingOpenURL = url\n            return\n        }\n""",
    "",
    "root dispatch access guard",
)
s = exact(
    s,
    """        guard hasCheckedBlockedStatus, !isBlocked, !didFailBlockedStatusCheck,\n              let url = sharedModel.pendingOpenURL else {\n            return\n        }\n""",
    """        guard let url = sharedModel.pendingOpenURL else {\n            return\n        }\n""",
    "root pending URL access guard",
)
s = regex(
    s,
    r"    /// Single entry point for the access gate\..*?    func checkiOSBeta\(\) \{",
    """    @MainActor\n    private func runStartupIfNeeded() {\n        guard !didRunStartup else { return }\n        didRunStartup = true\n\n        sharedModel.selectedTab = .apps\n        closeDuplicatedWindow()\n        checkLastLaunchError()\n        checkTeamId()\n        checkAndSaveBundleId()\n        checkGetTaskAllow()\n        checkPrivateContainerBookmark()\n        checkiOSBeta()\n        processPendingURLIfNeeded()\n    }\n\n    func checkiOSBeta() {""",
    "root access service implementation",
)
s = regex(
    s,
    r"private struct AccessVerificationFailedView: View \{.*?\n\}\n\n/// Requires a double-swipe",
    "/// Requires a double-swipe",
    "root access failure screen",
)
save(tab_path, s)


# The shared model no longer needs to synthesize an access-service UDID.
shared_path = "LiveContainerSwiftUI/FlekStore/Models/FlekstoreSharedModel.swift"
save(
    shared_path,
    """//\n//  SharedModel.swift\n//  LiveContainer\n//\n//  Created by Alexander Grigoryev on 30.09.2025.\n//\nimport SwiftUI\n\nclass FlekstoreSharedModel: ObservableObject {\n    @Published var appInstallURL: String = \"\"\n}\n""",
)


# These types existed only to enforce/display FlekSt0re access and premium state.
for rel in [
    "LiveContainerSwiftUI/FlekStore/Models/AccessVerification.swift",
    "LiveContainerSwiftUI/FlekStore/Models/DeviceStatusResponse.swift",
    "LiveContainerSwiftUI/FlekStore/Views/AccessBlockedView.swift",
    "LiveContainerSwiftUI/FlekStore/Screens/Premium/PremiumRequiredView.swift",
]:
    p = ROOT / rel
    if p.exists():
        p.unlink()


# Fail loudly if an entitlement/payment path remains in the app source. Public
# FlekSt0re catalog APIs are intentionally allowed; this audit targets access,
# UDID, ban, subscription and premium-gate behavior only.
forbidden = [
    "PremiumRequiredView",
    "showPremium",
    "requiresPremium",
    "hasSubscription",
    "refreshSubscriptionStatus",
    "FSEncryptedUDID",
    "AccessVerificationService",
    "AccessVerdictStore",
    "AccessBlockedView",
    "device-service/get-status",
    "Unable to verify access",
    "User UDID is empty",
    "chargeback",
]
scan_roots = [
    ROOT / "LiveContainerSwiftUI/FlekStore",
    ROOT / "LiveContainerSwiftUI/FlekDeck",
    ROOT / "LiveContainerSwiftUI/Views/LCTabView.swift",
]
violations = []
for root in scan_roots:
    files = [root] if root.is_file() else list(root.rglob("*.swift"))
    for f in files:
        text = f.read_text(encoding="utf-8")
        for token in forbidden:
            if token.lower() in text.lower():
                violations.append(f"{f.relative_to(ROOT)}: {token}")

if violations:
    raise RuntimeError("FlekSt0re access/payment remnants remain:\n" + "\n".join(violations))

print("FlekDeck standalone cleanup complete: no UDID/access/premium gates remain.")
