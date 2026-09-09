from pathlib import Path

# Temp-branch-only persistent app-switcher swipe invariant.
#
# FlekDeck's guest scene is hosted out of process. A clear UIWindow gesture target
# is not a reliable touch owner above that remote scene; MultitaskSwipeZone already
# solves this by using a tiny non-clear backing layer in the dedicated overlay
# window. Keep one such zone alive for the entire foreground-app lifetime instead
# of constructing it later through showNavAssist()/ensureControlAccessible().
#
# Invariant:
#   app/page launch is registered -> persistent overlay swipe is armed immediately
#   app/page on stage            -> swipe remains armed
#   switcher opening/open         -> swipe is disabled
#   springboard/no running apps   -> swipe is disabled
#
# This path intentionally does NOT wait for view alpha, view.window,
# hasForegroundAppWindow(), launch content, or any retry timer.

p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text(encoding="utf-8")

# 1) Dedicated persistent zone, separate from the legacy optional swipeZone that
# showNavAssist creates/tears down while switching between bar/button controls.
prop_anchor = '''    private var swipeZone: MultitaskSwipeZone?
'''
prop_replacement = '''    private var swipeZone: MultitaskSwipeZone?
    /// LCPersistentSwitcherSwipeInvariant: a real, hit-testable overlay target that
    /// is armed from app/page launch state itself. Unlike `swipeZone`, this is not
    /// owned by the bar/floating-button lifecycle and is never recreated just
    /// because those controls change.
    private var persistentSwitcherSwipeZone: MultitaskSwipeZone?
'''
if prop_anchor not in s:
    raise SystemExit("swipeZone property anchor not found")
s = s.replace(prop_anchor, prop_replacement, 1)

# 2) Add the persistent-zone synchronizer beside the existing swipe-zone code.
method_anchor = '''    // MARK: - Multitask swipe zone

    /// Whether the bottom swipe is the chosen control rather than the floating button.
'''
persistent_methods = '''    // MARK: - Multitask swipe zone

    /// Make the bottom app-switcher swipe follow logical launch state, not rendered
    /// view readiness. This is the only lifecycle owner of the persistent zone.
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
        let armed = !isHomeState
            && !apps.isEmpty
            && !isAppSwitcherOpen
            && !isOpeningAppSwitcher

        zone.layer.removeAllAnimations()
        zone.isHidden = !armed
        zone.isUserInteractionEnabled = armed
        zone.alpha = armed ? 1 : 0

        if armed {
            placePersistentSwitcherSwipeZone()
            zone.superview?.bringSubviewToFront(zone)
        }
    }

    /// Same safe-area placement as the proven MultitaskSwipeZone, but independent
    /// of the delayed nav-assist lifecycle.
    private func placePersistentSwitcherSwipeZone(in bounds: CGRect? = nil) {
        guard let zone = persistentSwitcherSwipeZone,
              let host = zone.superview else { return }
        let area = bounds ?? host.bounds
        guard area.width > 0, area.height > 0 else { return }

        let inset = max(host.safeAreaInsets.bottom, safeAreaInsets.bottom)
        let shortSide = min(area.width, area.height)
        var size = MultitaskSwipeZone.preferredSize(forShortSide: shortSide)
        // Keep the system-home-indicator-centered behavior, but give the target
        // enough horizontal room that a natural bottom swipe does not have to land
        // on one exact narrow strip.
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
'''
if method_anchor not in s:
    raise SystemExit("multitask swipe-zone section anchor not found")
s = s.replace(method_anchor, persistent_methods, 1)

# 3) The old optional install path must not create a competing second swipe target.
old_install = '''    private func installSwipeZone(in host: UIView, animated: Bool) {
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
'''
new_install = '''    private func installSwipeZone(in host: UIView, animated: Bool) {
        // Persistent launch invariant owns the bottom swipe. Keep this method as
        // the legacy call-site boundary so bar/button preference code needs no
        // behavioral fork, but do not create a second recognizer/view.
        syncPersistentSwitcherSwipeZone()
    }
'''
if old_install not in s:
    raise SystemExit("legacy installSwipeZone implementation anchor not found")
s = s.replace(old_install, new_install, 1)

# 4) Create the overlay/zone once at manager startup (hidden on springboard).
init_anchor = '''    override init() {
        super.init()
'''
init_replacement = '''    override init() {
        super.init()
        // LCPersistentSwitcherSwipeStartup: create the real overlay touch owner
        // before any guest/page launch can race its later control-reconciliation.
        DispatchQueue.main.async { [weak self] in
            self?.syncPersistentSwitcherSwipeZone()
        }
'''
if init_anchor not in s:
    raise SystemExit("manager init anchor not found")
s = s.replace(init_anchor, init_replacement, 1)

# 5) If the overlay window geometry changes, move BOTH legacy and persistent zones.
geometry_anchor = '''            self.placeSwipeZone(in: bounds)
            guard let button = self.navAssistButton, !self.isNavAssistDragging else { return }
'''
geometry_replacement = '''            self.placeSwipeZone(in: bounds)
            self.placePersistentSwitcherSwipeZone(in: bounds)
            guard let button = self.navAssistButton, !self.isNavAssistDragging else { return }
'''
if geometry_anchor not in s:
    raise SystemExit("overlay geometry swipe placement anchor not found")
s = s.replace(geometry_anchor, geometry_replacement, 1)

# 6) Foreground re-entry reattaches the zone if UIKit moved us to another scene.
active_anchor = '''    @objc private func appDidBecomeActive() {
        ensureControlAccessible()
'''
active_replacement = '''    @objc private func appDidBecomeActive() {
        syncPersistentSwitcherSwipeZone()
        ensureControlAccessible()
'''
if active_anchor not in s:
    raise SystemExit("appDidBecomeActive anchor not found")
s = s.replace(active_anchor, active_replacement, 1)

# 7) Exact guest launch state transition: arm before the expand/showDock animations.
guest_state = '''            self.apps.append(appModel)
            self.frontmostAppUUID = appUUID
            self.isHomeState = false

            // Opens at once, carrying the app's launch screen.
'''
guest_state_replacement = '''            self.apps.append(appModel)
            self.frontmostAppUUID = appUUID
            self.isHomeState = false
            self.syncPersistentSwitcherSwipeZone()

            // Opens at once, carrying the app's launch screen.
'''
if guest_state not in s:
    raise SystemExit("guest launch state anchor not found")
s = s.replace(guest_state, guest_state_replacement, 1)

# 8) Exact built-in Settings/Installer/FlekStore state transition.
internal_state = '''            self.apps.append(appModel)
            self.frontmostAppUUID = uuid
            self.isHomeState = false

            // Out of its own icon, the same as a guest app
'''
internal_state_replacement = '''            self.apps.append(appModel)
            self.frontmostAppUUID = uuid
            self.isHomeState = false
            self.syncPersistentSwitcherSwipeZone()

            // Out of its own icon, the same as a guest app
'''
if internal_state not in s:
    raise SystemExit("internal-page launch state anchor not found")
s = s.replace(internal_state, internal_state_replacement, 1)

# 9) Any app brought back to stage (switcher card, home dock, PiP return) re-arms.
stage_anchor = '''    private func windowTookStage(uuid: String) {
        let wasHomeState = isHomeState
        isHomeState = false
        frontmostAppUUID = uuid
'''
stage_replacement = '''    private func windowTookStage(uuid: String) {
        let wasHomeState = isHomeState
        isHomeState = false
        frontmostAppUUID = uuid
        syncPersistentSwitcherSwipeZone()
'''
if stage_anchor not in s:
    raise SystemExit("windowTookStage anchor not found")
s = s.replace(stage_anchor, stage_replacement, 1)

# 10) Keep the persistent target above whichever bar/button control is laid out.
floating_return_anchor = '''                self.refreshOrientationLock()
                NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
                return
'''
floating_return_replacement = '''                self.refreshOrientationLock()
                NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
                self.syncPersistentSwitcherSwipeZone()
                return
'''
if floating_return_anchor not in s:
    raise SystemExit("showDock floating path anchor not found")
s = s.replace(floating_return_anchor, floating_return_replacement, 1)

showdock_bar_anchor = '''            self.updateDockFrame(animated: false)

            hostingController.view.isHidden = false
'''
showdock_bar_replacement = '''            self.updateDockFrame(animated: false)
            self.syncPersistentSwitcherSwipeZone()

            hostingController.view.isHidden = false
'''
if showdock_bar_anchor not in s:
    raise SystemExit("showDock bar layout anchor not found")
s = s.replace(showdock_bar_anchor, showdock_bar_replacement, 1)

show_switcher_start = s.find('    @objc public func showSwitcherBar()')
if show_switcher_start < 0:
    raise SystemExit("showSwitcherBar start not found")
show_switcher_end = s.find('    // MARK: - Multitask swipe zone', show_switcher_start)
if show_switcher_end < 0:
    raise SystemExit("showSwitcherBar end not found")
chunk = s[show_switcher_start:show_switcher_end]
needle = '''            self.updateDockFrame(animated: false)
            NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
'''
replacement = '''            self.updateDockFrame(animated: false)
            self.syncPersistentSwitcherSwipeZone()
            NotificationCenter.default.post(name: .multitaskBarVisibilityChanged, object: nil)
'''
if needle not in chunk:
    raise SystemExit("showSwitcherBar layout anchor not found")
chunk = chunk.replace(needle, replacement, 1)
s = s[:show_switcher_start] + chunk + s[show_switcher_end:]

# 11) Going home disables it as soon as logical home state flips.
home_anchor = '''        updateFrontmostApp()
        isHomeState = true
        hideDock()
'''
home_replacement = '''        updateFrontmostApp()
        isHomeState = true
        syncPersistentSwitcherSwipeZone()
        hideDock()
'''
if home_anchor not in s:
    raise SystemExit("flyEverythingHome home-state anchor not found")
s = s.replace(home_anchor, home_replacement, 1)

# 12) App removal updates the invariant before any delayed control healing.
remove_anchor = '''            withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                self.apps.removeAll { $0.appUUID == appUUID }
            }
            self.appSnapshotViews.removeValue(forKey: appUUID)
'''
remove_replacement = '''            withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                self.apps.removeAll { $0.appUUID == appUUID }
            }
            self.syncPersistentSwitcherSwipeZone()
            self.appSnapshotViews.removeValue(forKey: appUUID)
'''
if remove_anchor not in s:
    raise SystemExit("removeRunningApp list mutation anchor not found")
s = s.replace(remove_anchor, remove_replacement, 1)

# 13) Opening the switcher disables the launch swipe immediately, before rotation.
open_switcher_anchor = '''        isOpeningAppSwitcher = true
        AppDelegate.orientationLock = .portrait
'''
open_switcher_replacement = '''        isOpeningAppSwitcher = true
        syncPersistentSwitcherSwipeZone()
        AppDelegate.orientationLock = .portrait
'''
if open_switcher_anchor not in s:
    raise SystemExit("showAppSwitcher opening-state anchor not found")
s = s.replace(open_switcher_anchor, open_switcher_replacement, 1)

# 14) Once the switcher is fully presented, keep it disabled explicitly.
present_anchor = '''        isAppSwitcherOpen = true
        isOpeningAppSwitcher = false
        // The portrait lock was applied
'''
present_replacement = '''        isAppSwitcherOpen = true
        isOpeningAppSwitcher = false
        syncPersistentSwitcherSwipeZone()
        // The portrait lock was applied
'''
if present_anchor not in s:
    raise SystemExit("presentAppSwitcher state anchor not found")
s = s.replace(present_anchor, present_replacement, 1)

# 15) Returning from the switcher: re-arm only after the overlay actually leaves.
dismiss_completion_anchor = '''            overlay.view.removeFromSuperview()
            overlay.view.transform = .identity
            self.springboardSnapshot = nil
            self.ensureControlAccessible()
        }
    }

    /// Puts the multitask control into its final state
'''
dismiss_completion_replacement = '''            overlay.view.removeFromSuperview()
            overlay.view.transform = .identity
            self.springboardSnapshot = nil
            self.syncPersistentSwitcherSwipeZone()
            self.ensureControlAccessible()
        }
    }

    /// Puts the multitask control into its final state
'''
if dismiss_completion_anchor not in s:
    raise SystemExit("dismissAppSwitcher completion anchor not found")
s = s.replace(dismiss_completion_anchor, dismiss_completion_replacement, 1)

# 16) The springboard exit path disables the target at the same logical transition.
switcher_home_anchor = '''        updateFrontmostApp()
        isHomeState = true
        hideDock()
        refreshOrientationLock()
'''
switcher_home_replacement = '''        updateFrontmostApp()
        isHomeState = true
        syncPersistentSwitcherSwipeZone()
        hideDock()
        refreshOrientationLock()
'''
if switcher_home_anchor not in s:
    raise SystemExit("switcher-to-springboard home-state anchor not found")
s = s.replace(switcher_home_anchor, switcher_home_replacement, 1)

# 17) Close-all empties the list before home is recorded; disable immediately.
closeall_anchor = '''            self.apps.removeAll()
            self.appSnapshotViews.removeAll()
'''
closeall_replacement = '''            self.apps.removeAll()
            self.syncPersistentSwitcherSwipeZone()
            self.appSnapshotViews.removeAll()
'''
if closeall_anchor not in s:
    raise SystemExit("closeAll apps.removeAll anchor not found")
s = s.replace(closeall_anchor, closeall_replacement, 1)

# 18) Control visibility/healing must recognize the persistent target.
any_control_anchor = '''        let navShown = navAssistButton != nil || swipeZone != nil
        return barShown || navShown
'''
any_control_replacement = '''        let navShown = navAssistButton != nil || swipeZone != nil
        let persistentSwipeShown = persistentSwitcherSwipeZone?.window != nil
            && persistentSwitcherSwipeZone?.isHidden == false
            && persistentSwitcherSwipeZone?.isUserInteractionEnabled == true
        return barShown || navShown || persistentSwipeShown
'''
if any_control_anchor not in s:
    raise SystemExit("isAnyControlVisible anchor not found")
s = s.replace(any_control_anchor, any_control_replacement, 1)

heal_anchor = '''            let navShown = self.navAssistButton?.window != nil || self.swipeZone?.window != nil

            guard !barShown && !navShown else { return }
'''
heal_replacement = '''            let persistentSwipeShown = self.persistentSwitcherSwipeZone?.window != nil
                && self.persistentSwitcherSwipeZone?.isHidden == false
                && self.persistentSwitcherSwipeZone?.isUserInteractionEnabled == true
            let navShown = self.navAssistButton?.window != nil
                || self.swipeZone?.window != nil
                || persistentSwipeShown

            guard !barShown && !navShown else { return }
'''
if heal_anchor not in s:
    raise SystemExit("ensureControlAccessible navShown anchor not found")
s = s.replace(heal_anchor, heal_replacement, 1)

# 19) When hideDock runs after home/PiP transitions, reconcile the persistent zone.
hide_dock_anchor = '''        DispatchQueue.main.async {
            self.isVisible = false

            // Remove the bar reservation from internal pages
'''
hide_dock_replacement = '''        DispatchQueue.main.async {
            self.isVisible = false
            self.syncPersistentSwitcherSwipeZone()

            // Remove the bar reservation from internal pages
'''
if hide_dock_anchor not in s:
    raise SystemExit("hideDock state anchor not found")
s = s.replace(hide_dock_anchor, hide_dock_replacement, 1)

for required in [
    "LCPersistentSwitcherSwipeInvariant",
    "LCPersistentSwitcherSwipeStartup",
    "persistentSwitcherSwipeZone",
    "syncPersistentSwitcherSwipeZone",
    "placePersistentSwitcherSwipeZone",
]:
    if required not in s:
        raise SystemExit(f"persistent switcher swipe marker missing: {required}")

method_start = s.find("    private func syncPersistentSwitcherSwipeZone()")
method_end = s.find("    private func placePersistentSwitcherSwipeZone", method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit("unable to isolate persistent switcher synchronizer")
sync_block = s[method_start:method_end]
for forbidden in [
    "hasForegroundAppWindow()",
    ".alpha > 0.1",
    ".window != nil",
    "asyncAfter",
]:
    if forbidden in sync_block:
        raise SystemExit(f"persistent swipe incorrectly waits on readiness: {forbidden}")

if "FlekImmediateSwitcherSwipeBridge" in s:
    raise SystemExit("obsolete lower-window immediate swipe bridge leaked into source")

p.write_text(s, encoding="utf-8")
print("Installed persistent overlay-owned app-switcher swipe invariant with no launch-readiness wait.")
