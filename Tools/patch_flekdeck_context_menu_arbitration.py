#!/usr/bin/env python3
from pathlib import Path
import runpy

# The Home app context menu is owned by the inner icon UICollectionView. The
# Springboard's parent long-press recognizer is only for edit-mode dragging. If
# that parent recognizer reaches .began on an installed app it can cancel UIKit's
# context-menu recognizer before the menu appears. Reject ONLY that parent
# recognizer before recognition for installed apps. This has no relationship to
# FlekDeck's bottom-swipe App Switcher UIPanGestureRecognizer.

drag = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardDragManager.swift")
s = drag.read_text()
if "final class LCSpringboardDragManager: NSObject, UIGestureRecognizerDelegate {" not in s:
    s = s.replace(
        "final class LCSpringboardDragManager {",
        "final class LCSpringboardDragManager: NSObject, UIGestureRecognizerDelegate {",
        1,
    )

method = '''    /// Installed-app holds belong to the icon UICollectionView context menu.
    /// Fail the parent edit/drag long press BEFORE it begins so UIKit can own
    /// the hold. Empty space/default apps still use the normal edit-mode path.
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
            return true
        }

        if case .installed = pageCell.items[indexPath.item] {
            return false
        }
        return true
    }

'''
if "func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool" not in s:
    anchor = "    func handleLongPress(_ gesture: UILongPressGestureRecognizer) {\n"
    if anchor not in s:
        raise SystemExit(f"{drag}: handleLongPress anchor missing")
    s = s.replace(anchor, method + anchor, 1)
drag.write_text(s)

vc = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift")
s = vc.read_text()
if "longPressGesture.delegate = dragManager" not in s:
    # Comments around this setup have changed several times. Bind the delegate
    # structurally immediately before the recognizer is added to the root view.
    anchor = "        view.addGestureRecognizer(longPressGesture)\n"
    if anchor not in s:
        raise SystemExit(f"{vc}: long-press addGestureRecognizer anchor missing")
    s = s.replace(
        anchor,
        "        longPressGesture.delegate = dragManager\n" + anchor,
        1,
    )
vc.write_text(s)

# Invariants: context-menu arbitration must be present, and it must be scoped to
# UILongPressGestureRecognizer/installed apps rather than any pan recognizer.
drag_text = drag.read_text()
vc_text = vc.read_text()
for marker in (
    "UIGestureRecognizerDelegate",
    "gestureRecognizerShouldBegin",
    "UILongPressGestureRecognizer",
    "if case .installed = pageCell.items[indexPath.item]",
):
    if marker not in drag_text:
        raise SystemExit(f"{drag}: missing context-menu arbitration marker: {marker}")
if "longPressGesture.delegate = dragManager" not in vc_text:
    raise SystemExit(f"{vc}: parent long press is not delegated")
if "UIPanGestureRecognizer" in method:
    raise SystemExit("context-menu arbitration unexpectedly touches pan gestures")

print("FlekDeck Home hold menu arbitration restored without touching App Switcher pan gestures")

# This script is the last leaf of the canonical runtime guardrail. Keep the
# user's other reported UI regression adjacent to it: once gesture ownership is
# final, scope guest diagnostics to the current launch so old app errors/logs
# cannot bleed into the next app.
runpy.run_path("Tools/patch_flekdeck_error_session.py", run_name="__main__")
