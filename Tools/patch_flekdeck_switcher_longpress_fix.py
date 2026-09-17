#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one {label} block, found {count}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. Restore FlekDeck's App Switcher / Parallel routing.
# Classic Mode is a single-process launch option. It must never silently force
# an ARM64 app out of FlekDeck's existing App Switcher / Parallel path.
# ARM32 still remains single-process because LiveExec32 is not a LiveProcess
# runtime.
# ---------------------------------------------------------------------------
app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
replace_once(
    app_model,
    '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // LiveExec32 and Classic Mode both require the single-process host path.
        let multitask = (appInfo.is32bit || classicMode != 0) ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = classicMode == 0 ? (multitask ?? shouldLaunchInMultitaskMode) : false
#endif''',
    '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // Preserve FlekDeck's App Switcher / Parallel routing for every native
        // ARM64 guest. Only ARM32 is forced onto the single-process LiveExec32
        // path; Classic Mode is consumed only if that single-process path wins.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif''',
    "App Switcher routing",
)

# ---------------------------------------------------------------------------
# 2. Make the Springboard hold menu win the recognizer race.
# Previously the root drag long-press reached .began first and then toggled
# itself off/on for installed apps. By then UIKit's collection-view context menu
# could already have been cancelled. Fail the drag recognizer before it begins
# whenever a non-editing hold lands on an installed app.
# ---------------------------------------------------------------------------
drag = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardDragManager.swift")
replace_once(
    drag,
    "final class LCSpringboardDragManager {",
    "final class LCSpringboardDragManager: NSObject, UIGestureRecognizerDelegate {",
    "drag manager recognizer delegate conformance",
)

text = drag.read_text()
delegate_method = '''    /// Installed app holds belong to UICollectionView's context-menu recognizer.
    /// Reject the root drag recognizer before it enters `.began`; cancelling it
    /// after `.began` is too late and can suppress the menu entirely.
    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let gesture = gestureRecognizer as? UILongPressGestureRecognizer,
              let vc = viewController,
              !vc.isInEditMode else {
            return true
        }

        let touchInView = gesture.location(in: vc.view)
        guard let (_, pageCell) = vc.pageCellAtPoint(touchInView) else {
            return true
        }

        let touchInPage = gesture.location(in: pageCell.collectionView)
        guard let indexPath = pageCell.collectionView.indexPathForItem(at: touchInPage),
              indexPath.item < pageCell.items.count else {
            // Empty-space holds still belong to FlekDeck's edit-mode gesture.
            return true
        }

        let item = pageCell.items[indexPath.item]
        if item.isInstalledApp {
            return false
        }
        return true
    }

'''
if delegate_method not in text:
    anchor = "    // MARK: - Gesture handler\n\n"
    if anchor not in text:
        raise SystemExit(f"{drag}: gesture handler anchor missing")
    text = text.replace(anchor, anchor + delegate_method, 1)

# The delegate now prevents this branch from being reached for an installed app.
# Keep it as a harmless fallback, but never disable/re-enable the recognizer at
# .began because doing so can cancel UIKit's context-menu interaction.
text = text.replace(
    '''            } else {
                // Installed app → let context menu handle it
                gesture.isEnabled = false
                gesture.isEnabled = true
                return
            }''',
    '''            } else {
                // Installed app → the recognizer delegate should already have
                // rejected this drag so UIKit can present the context menu.
                return
            }''',
    1,
)
drag.write_text(text)

vc = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift")
replace_once(
    vc,
    '''        longPressGesture = UILongPressGestureRecognizer(target: self, action: #selector(handleLongPress(_:)))
        longPressGesture.minimumPressDuration = 0.3
        view.addGestureRecognizer(longPressGesture)''',
    '''        longPressGesture = UILongPressGestureRecognizer(target: self, action: #selector(handleLongPress(_:)))
        longPressGesture.minimumPressDuration = 0.3
        // Installed-app holds must be rejected by the drag recognizer before
        // recognition so the inner UICollectionView context menu can own them.
        longPressGesture.delegate = dragManager
        view.addGestureRecognizer(longPressGesture)''',
    "Springboard long-press delegate wiring",
)

# ---------------------------------------------------------------------------
# 3. Assert the active Home menu really contains Open Data Folder.
# Do not fall back to the legacy LCAppBanner menu; FlekDeck's Springboard menu is
# the UI the user actually holds on.
# ---------------------------------------------------------------------------
app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
app_list_text = app_list.read_text()
for marker in [
    "func homeOpenDataFolder(_ app: LCAppModel)",
    'title: "lc.appBanner.openDataFolder".loc,',
    'image: UIImage(systemName: "folder")',
    "homeOpenDataFolder(app)",
    "let dataGroup = UIMenu(",
]:
    if marker not in app_list_text:
        raise SystemExit(f"{app_list}: active Springboard Open Data Folder marker missing: {marker}")

# Page cells must still expose UIKit's context-menu configuration.
page = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardPageCell.swift")
page_text = page.read_text()
if "contextMenuConfigurationForItemAt" not in page_text or "contextMenuFor: item" not in page_text:
    raise SystemExit(f"{page}: UIKit context menu delegate path is missing")

# Final invariants.
model_text = app_model.read_text()
if "appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)" not in model_text:
    raise SystemExit(f"{app_model}: ARM64 FlekDeck App Switcher routing was not restored")
if "classicMode != 0) ? false" in model_text or "classicMode == 0 ?" in model_text:
    raise SystemExit(f"{app_model}: Classic Mode can still override App Switcher routing")
if "longPressGesture.delegate = dragManager" not in vc.read_text():
    raise SystemExit(f"{vc}: drag recognizer does not yield to context menus")
if "func gestureRecognizerShouldBegin" not in drag.read_text():
    raise SystemExit(f"{drag}: early recognizer rejection is missing")

print("Restored FlekDeck App Switcher routing and reliable installed-app hold menus")
