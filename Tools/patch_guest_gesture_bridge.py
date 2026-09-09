from pathlib import Path

p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text(encoding="utf-8")

def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f"{label} anchor not found")
    s = s.replace(old, new, 1)

def insert_after_in_func(func_sig: str, needle: str, insertion: str, label: str) -> None:
    global s
    start = s.find(func_sig)
    if start < 0:
        raise SystemExit(f"{label} function not found")
    end = min(len(s), start + 14000)
    pos = s.find(needle, start, end)
    if pos < 0:
        raise SystemExit(f"{label} state anchor not found")
    pos += len(needle)
    s = s[:pos] + insertion + s[pos:]

replace_once(
    "    private var swipeZone: MultitaskSwipeZone?\n",
    """    private var swipeZone: MultitaskSwipeZone?
    /// LCPersistentSwitcherSwipeInvariant: real overlay touch target armed from
    /// logical app/page launch state, never guest-render readiness.
    private var persistentSwitcherSwipeZone: MultitaskSwipeZone?
""",
    "persistent property",
)

replace_once(
    """    // MARK: - Multitask swipe zone

    /// Whether the bottom swipe is the chosen control rather than the floating button.
""",
    """    // MARK: - Multitask swipe zone

    private func syncPersistentSwitcherSwipeZone() {
        guard isDockEnabled() else {
            persistentSwitcherSwipeZone?.isHidden = true
            persistentSwitcherSwipeZone?.isUserInteractionEnabled = false
            return
        }

        let host = overlayHostView()
        if persistentSwitcherSwipeZone == nil, let host {
            let zone = MultitaskSwipeZone()
            zone.onActivate = { [weak self] in
                guard let self,
                      !self.isHomeState,
                      !self.apps.isEmpty,
                      !self.isAppSwitcherOpen,
                      !self.isOpeningAppSwitcher else { return }
                self.showAppSwitcher()
            }
            host.addSubview(zone)
            persistentSwitcherSwipeZone = zone
        } else if let host, let zone = persistentSwitcherSwipeZone,
                  zone.superview !== host {
            host.addSubview(zone)
        }

        guard let zone = persistentSwitcherSwipeZone else { return }
        let armed = !isHomeState && !apps.isEmpty
            && !isAppSwitcherOpen && !isOpeningAppSwitcher

        zone.layer.removeAllAnimations()
        zone.isHidden = !armed
        zone.isUserInteractionEnabled = armed
        zone.alpha = armed ? 1 : 0
        if armed {
            placePersistentSwitcherSwipeZone()
            zone.superview?.bringSubviewToFront(zone)
        }
    }

    private func placePersistentSwitcherSwipeZone(in bounds: CGRect? = nil) {
        guard let zone = persistentSwitcherSwipeZone,
              let host = zone.superview else { return }
        let area = bounds ?? host.bounds
        guard area.width > 0, area.height > 0 else { return }

        let inset = max(host.safeAreaInsets.bottom, safeAreaInsets.bottom)
        var size = MultitaskSwipeZone.preferredSize(
            forShortSide: min(area.width, area.height)
        )
        size.width = min(area.width, max(size.width, area.width * 0.72))
        let intrusion = min(MultitaskSwipeZone.bandIntrusion, inset)
        zone.frame = CGRect(
            x: ((area.width - size.width) / 2).rounded(),
            y: area.height - inset + intrusion - size.height,
            width: size.width,
            height: size.height
        )
    }

    /// Whether the bottom swipe is the chosen control rather than the floating button.
""",
    "persistent methods",
)

replace_once(
    """    private func installSwipeZone(in host: UIView, animated: Bool) {
        tearDownSwipeZone()
        guard isSwipeZoneEnabled else { return }
        let bar = MultitaskSwipeZone()
        bar.onActivate = { [weak self] in
            self?.showAppSwitcher()
        }
        host.addSubview(bar)
        swipeZone = bar
        placeSwipeZone(in: host.bounds)

        guard animated else { return }
        bar.alpha = 0
        UIView.animate(withDuration: Constants.standardAnimationDuration,
                       delay: 0.03,
                       options: [.curveEaseOut, .allowUserInteraction]) {
            bar.alpha = 1
        }
    }
""",
    """    private func installSwipeZone(in host: UIView, animated: Bool) {
        syncPersistentSwitcherSwipeZone()
    }
""",
    "legacy swipe installer",
)

replace_once(
    """    override init() {
        super.init()
""",
    """    override init() {
        super.init()
        // LCPersistentSwitcherSwipeStartup
        DispatchQueue.main.async { [weak self] in
            self?.syncPersistentSwitcherSwipeZone()
        }
""",
    "manager init",
)

replace_once(
    """            self.placeSwipeZone(in: bounds)
            guard let button = self.navAssistButton, !self.isNavAssistDragging else { return }
""",
    """            self.placeSwipeZone(in: bounds)
            self.placePersistentSwitcherSwipeZone(in: bounds)
            guard let button = self.navAssistButton, !self.isNavAssistDragging else { return }
""",
    "overlay geometry",
)

replace_once(
    """    @objc private func appDidBecomeActive() {
        ensureControlAccessible()
""",
    """    @objc private func appDidBecomeActive() {
        syncPersistentSwitcherSwipeZone()
        ensureControlAccessible()
""",
    "didBecomeActive",
)

insert_after_in_func(
    "    @objc public func addRunningAppWithInfo(",
    "            self.isHomeState = false\n",
    "            self.syncPersistentSwitcherSwipeZone()\n",
    "guest launch",
)
insert_after_in_func(
    "    public func openInternalPage<Content: View>(",
    "            self.isHomeState = false\n",
    "            self.syncPersistentSwitcherSwipeZone()\n",
    "internal page launch",
)

insert_after_in_func(
    "    private func windowTookStage(uuid: String)",
    "        frontmostAppUUID = uuid\n",
    "        syncPersistentSwitcherSwipeZone()\n",
    "window took stage",
)

showdock_start = s.find("    @objc public func showDock()")
showdock_end = s.find("    @objc public func hideDock()", showdock_start)
if showdock_start < 0 or showdock_end < 0:
    raise SystemExit("showDock scope not found")
showdock = s[showdock_start:showdock_end]
if "            self.updateDockFrame(animated: false)\n" not in showdock:
    raise SystemExit("showDock layout anchor not found")
showdock = showdock.replace(
    "            self.updateDockFrame(animated: false)\n",
    "            self.updateDockFrame(animated: false)\n            self.syncPersistentSwitcherSwipeZone()\n",
    1,
)
if """                NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
                return
""" not in showdock:
    raise SystemExit("showDock floating return anchor not found")
showdock = showdock.replace(
    """                NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
                return
""",
    """                NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
                self.syncPersistentSwitcherSwipeZone()
                return
""",
    1,
)
s = s[:showdock_start] + showdock + s[showdock_end:]

showbar_start = s.find("    @objc public func showSwitcherBar()")
showbar_end = s.find("    // MARK: - Multitask swipe zone", showbar_start)
if showbar_start < 0 or showbar_end < 0:
    raise SystemExit("showSwitcherBar scope not found")
showbar = s[showbar_start:showbar_end]
target = """            self.updateDockFrame(animated: false)
            NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
"""
if target not in showbar:
    raise SystemExit("showSwitcherBar layout anchor not found")
showbar = showbar.replace(
    target,
    """            self.updateDockFrame(animated: false)
            self.syncPersistentSwitcherSwipeZone()
            NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
""",
    1,
)
s = s[:showbar_start] + showbar + s[showbar_end:]

replace_once(
    """        updateFrontmostApp()
        isHomeState = true
        hideDock()
""",
    """        updateFrontmostApp()
        isHomeState = true
        syncPersistentSwitcherSwipeZone()
        hideDock()
""",
    "fly home",
)

replace_once(
    """            withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                self.apps.removeAll { $0.appUUID == appUUID }
            }
            self.appSnapshotViews.removeValue(forKey: appUUID)
""",
    """            withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                self.apps.removeAll { $0.appUUID == appUUID }
            }
            self.syncPersistentSwitcherSwipeZone()
            self.appSnapshotViews.removeValue(forKey: appUUID)
""",
    "remove app",
)

replace_once(
    """            self.apps.removeAll()
            self.appSnapshotViews.removeAll()
""",
    """            self.apps.removeAll()
            self.syncPersistentSwitcherSwipeZone()
            self.appSnapshotViews.removeAll()
""",
    "close all",
)

replace_once(
    """        isOpeningAppSwitcher = true
        AppDelegate.orientationLock = .portrait
""",
    """        isOpeningAppSwitcher = true
        syncPersistentSwitcherSwipeZone()
        AppDelegate.orientationLock = .portrait
""",
    "switcher opening",
)

replace_once(
    """        isAppSwitcherOpen = true
        isOpeningAppSwitcher = false
""",
    """        isAppSwitcherOpen = true
        isOpeningAppSwitcher = false
        syncPersistentSwitcherSwipeZone()
""",
    "switcher presented",
)

dismiss_start = s.find("    func dismissAppSwitcher()")
dismiss_end = s.find("    /// Puts the multitask control into its final state", dismiss_start)
if dismiss_start < 0 or dismiss_end < 0:
    raise SystemExit("dismissAppSwitcher scope not found")
dismiss = s[dismiss_start:dismiss_end]
completion_anchor = """            overlay.view.removeFromSuperview()
            overlay.view.transform = .identity
            self.springboardSnapshot = nil
            self.ensureControlAccessible()
"""
if completion_anchor not in dismiss:
    raise SystemExit("dismissAppSwitcher completion anchor not found")
dismiss = dismiss.replace(
    completion_anchor,
    """            overlay.view.removeFromSuperview()
            overlay.view.transform = .identity
            self.springboardSnapshot = nil
            self.syncPersistentSwitcherSwipeZone()
            self.ensureControlAccessible()
""",
    1,
)
s = s[:dismiss_start] + dismiss + s[dismiss_end:]

switch_home_start = s.find("    func goToSpringboardFromSwitcher()")
switch_home_end = s.find("    /// Puts the interface back", switch_home_start)
if switch_home_start < 0 or switch_home_end < 0:
    raise SystemExit("switcher home scope not found")
switch_home = s[switch_home_start:switch_home_end]
if "        isHomeState = true\n" not in switch_home:
    raise SystemExit("switcher home state anchor not found")
switch_home = switch_home.replace(
    "        isHomeState = true\n",
    "        isHomeState = true\n        syncPersistentSwitcherSwipeZone()\n",
    1,
)
s = s[:switch_home_start] + switch_home + s[switch_home_end:]

replace_once(
    """        DispatchQueue.main.async {
            self.isVisible = false

            // Remove the bar reservation from internal pages
""",
    """        DispatchQueue.main.async {
            self.isVisible = false
            self.syncPersistentSwitcherSwipeZone()

            // Remove the bar reservation from internal pages
""",
    "hideDock",
)

replace_once(
    """        let navShown = navAssistButton != nil || swipeZone != nil
        return barShown || navShown
""",
    """        let navShown = navAssistButton != nil || swipeZone != nil
        let persistentSwipeShown = persistentSwitcherSwipeZone?.window != nil
            && persistentSwitcherSwipeZone?.isHidden == false
            && persistentSwitcherSwipeZone?.isUserInteractionEnabled == true
        return barShown || navShown || persistentSwipeShown
""",
    "isAnyControlVisible",
)

replace_once(
    """            let navShown = self.navAssistButton?.window != nil || self.swipeZone?.window != nil

            guard !barShown && !navShown else { return }
""",
    """            let persistentSwipeShown = self.persistentSwitcherSwipeZone?.window != nil
                && self.persistentSwitcherSwipeZone?.isHidden == false
                && self.persistentSwitcherSwipeZone?.isUserInteractionEnabled == true
            let navShown = self.navAssistButton?.window != nil
                || self.swipeZone?.window != nil
                || persistentSwipeShown

            guard !barShown && !navShown else { return }
""",
    "control self-heal",
)

for required in [
    "LCPersistentSwitcherSwipeInvariant",
    "LCPersistentSwitcherSwipeStartup",
    "persistentSwitcherSwipeZone",
    "syncPersistentSwitcherSwipeZone",
    "placePersistentSwitcherSwipeZone",
]:
    if required not in s:
        raise SystemExit(f"persistent switcher swipe marker missing: {required}")

start = s.find("    private func syncPersistentSwitcherSwipeZone()")
end = s.find("    private func placePersistentSwitcherSwipeZone", start)
block = s[start:end]
for forbidden in ["hasForegroundAppWindow()", ".alpha > 0.1", "asyncAfter"]:
    if forbidden in block:
        raise SystemExit(f"persistent swipe waits on readiness: {forbidden}")

if "FlekImmediateSwitcherSwipeBridge" in s:
    raise SystemExit("obsolete lower-window immediate swipe bridge still present")

p.write_text(s, encoding="utf-8")
print("Persistent overlay switcher swipe armed directly by launch state; no readiness wait.")
