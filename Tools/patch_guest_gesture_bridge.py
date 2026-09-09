from pathlib import Path

# Temp-branch-only immediate app-switcher gesture bridge.
#
# The normal MultitaskSwipeZone is created through showNavAssist(), which depends
# on FlekDeck first deciding a guest/internal page is fully foreground. On cold
# Settings/Installer launches that state can settle late, so the bottom swipe may
# appear to be broken and then start working later. Keep an independent recognizer
# on the host UIWindow from startup instead. It never owns app/window state; it
# only asks the existing MultitaskDockManager to open its switcher.

p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text(encoding="utf-8")

marker = "FlekImmediateSwitcherSwipeBridge"
if marker not in s:
    s += r'''

// MARK: - Experiment: immediate host-owned switcher swipe

/// A UIWindow-owned bottom-edge swipe that exists independently of the delayed
/// nav-assist/swipe-zone lifecycle. It covers guest windows AND built-in pages
/// (Settings/Installer), while leaving taps and the app's own gestures untouched.
@available(iOS 16.0, *)
final class FlekImmediateSwitcherSwipeBridge: NSObject, UIGestureRecognizerDelegate {
    static let shared = FlekImmediateSwitcherSwipeBridge()

    private weak var installedWindow: UIWindow?
    private weak var pan: UIPanGestureRecognizer?
    private var lastActivation: CFTimeInterval = 0

    private override init() {
        super.init()
    }

    func install(on window: UIWindow) {
        if installedWindow === window, pan?.view === window { return }

        if let oldPan = pan, let oldView = oldPan.view {
            oldView.removeGestureRecognizer(oldPan)
        }

        let recognizer = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        recognizer.delegate = self
        recognizer.maximumNumberOfTouches = 1
        recognizer.cancelsTouchesInView = false
        recognizer.delaysTouchesBegan = false
        recognizer.delaysTouchesEnded = false
        window.addGestureRecognizer(recognizer)

        installedWindow = window
        pan = recognizer
        NSLog("[FlekDeckDiag] immediate switcher swipe installed on %@", String(describing: window))
    }

    private func hasVisibleAppOrInternalPage(_ manager: MultitaskDockManager) -> Bool {
        manager.apps.contains { app in
            guard let view = app.view else { return false }
            return view.window != nil && !view.isHidden && view.alpha > 0.01
        }
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let pan = gestureRecognizer as? UIPanGestureRecognizer,
              let view = pan.view else { return false }

        let manager = MultitaskDockManager.shared
        guard !manager.isAppSwitcherOpen,
              hasVisibleAppOrInternalPage(manager) else { return false }

        // Respect the existing Home Bar setting. Missing means enabled, matching
        // MultitaskDockManager.isSwipeZoneEnabled.
        let swipeEnabled = LCUtils.appGroupUserDefault.object(forKey: "LCMultitaskHomeBar") as? Bool ?? true
        guard swipeEnabled else { return false }

        let start = pan.location(in: view)
        let bandHeight = max(88.0, view.safeAreaInsets.bottom + 54.0)
        guard start.y >= view.bounds.height - bandHeight else { return false }

        let velocity = pan.velocity(in: view)
        guard velocity.y < -20 else { return false }
        return abs(velocity.y) >= abs(velocity.x) * 0.55
    }

    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
    ) -> Bool {
        true
    }

    @objc private func handlePan(_ gesture: UIPanGestureRecognizer) {
        guard gesture.state == .ended, let view = gesture.view else { return }

        let translation = gesture.translation(in: view)
        let velocity = gesture.velocity(in: view)
        let upward = max(0, -translation.y)
        guard upward >= 22 || velocity.y <= -500 else { return }

        // Prevent a second recognizer finishing the same physical swipe from
        // opening the switcher twice while its first transition is beginning.
        let now = CACurrentMediaTime()
        guard now - lastActivation > 0.45 else { return }
        lastActivation = now

        let manager = MultitaskDockManager.shared
        guard !manager.isAppSwitcherOpen,
              hasVisibleAppOrInternalPage(manager) else { return }
        NSLog("[FlekDeckDiag] immediate bottom swipe -> switcher (up=%.1f vy=%.1f)", upward, velocity.y)
        manager.showAppSwitcher()
    }
}
'''

# Install as soon as the manager has been constructed. The async hop is deliberate:
# it runs after init finishes, when UIKit has established the app's key window.
manager_start = s.find("@objc public class MultitaskDockManager")
init_start = s.find("    override init() {", manager_start)
if manager_start < 0 or init_start < 0:
    raise SystemExit("MultitaskDockManager init anchor not found")
init_super = s.find("        super.init()\n", init_start)
if init_super < 0:
    raise SystemExit("MultitaskDockManager super.init anchor not found")
init_insert = init_super + len("        super.init()\n")
init_marker = "LCImmediateSwitcherSwipeInstall"
if init_marker not in s[init_start:init_start + 1800]:
    install = '''        // LCImmediateSwitcherSwipeInstall: do not wait for foreground-window\n        // reconciliation before the bottom app-switcher gesture exists.\n        DispatchQueue.main.async { [weak self] in\n            guard let self, let window = self.keyWindow else { return }\n            FlekImmediateSwitcherSwipeBridge.shared.install(on: window)\n        }\n'''
    s = s[:init_insert] + install + s[init_insert:]

# Reattach if UIKit changes the key window/scene while the app is running.
active_anchor = '''    @objc private func appDidBecomeActive() {\n'''
if active_anchor not in s:
    raise SystemExit("appDidBecomeActive anchor not found")
active_install = '''    @objc private func appDidBecomeActive() {\n        if let window = keyWindow {\n            FlekImmediateSwitcherSwipeBridge.shared.install(on: window)\n        }\n'''
if "FlekImmediateSwitcherSwipeBridge.shared.install(on: window)" not in s[s.find(active_anchor):s.find(active_anchor) + 500]:
    s = s.replace(active_anchor, active_install, 1)

# Built-in pages can be opened without a guest LiveProcess becoming foreground.
# Reinstall at the start of that path too, so Settings/Installer never depend on
# the guest-window readiness retry loop.
internal_anchor = '''    public func openInternalPage<Content: View>(kind: String, uuid: String, name: String, @ViewBuilder content: () -> Content) {\n'''
if internal_anchor not in s:
    raise SystemExit("openInternalPage anchor not found")
internal_install = internal_anchor + '''        if let window = keyWindow {\n            FlekImmediateSwitcherSwipeBridge.shared.install(on: window)\n        }\n'''
if "FlekImmediateSwitcherSwipeBridge.shared.install(on: window)" not in s[s.find(internal_anchor):s.find(internal_anchor) + 500]:
    s = s.replace(internal_anchor, internal_install, 1)

for required in [
    marker,
    init_marker,
    "hasVisibleAppOrInternalPage",
    "manager.showAppSwitcher()",
    'LCMultitaskHomeBar',
]:
    if required not in s:
        raise SystemExit(f"Immediate switcher gesture marker missing: {required}")

p.write_text(s, encoding="utf-8")
print("Installed immediate UIWindow app-switcher swipe for guest and internal pages")
