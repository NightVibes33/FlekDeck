#!/usr/bin/env python3
from pathlib import Path
import runpy

# This legacy entry point used to install a root long-press recognizer delegate.
# That changed Home gesture arbitration and regressed the already-proven app
# switcher. Keep the filename for old workflows, but route it through the
# canonical user-regression repair instead.
runpy.run_path("Tools/patch_flekdeck_user_regressions.py", run_name="__main__")

# Open Data Folder remains a context-menu action; it does not own root gestures.
app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift").read_text()
for marker in (
    "func homeOpenDataFolder(_ app: LCAppModel)",
    'title: "lc.appBanner.openDataFolder".loc,',
    "homeOpenDataFolder(app)",
):
    if marker not in app_list:
        raise SystemExit(f"Springboard Open Data Folder marker missing: {marker}")

page = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardPageCell.swift").read_text()
if "contextMenuConfigurationForItemAt" not in page or "contextMenuFor: item" not in page:
    raise SystemExit("UIKit Springboard context-menu path is missing")

drag = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardDragManager.swift").read_text()
vc = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift").read_text()
if "gestureRecognizerShouldBegin" in drag or "longPressGesture.delegate = dragManager" in vc:
    raise SystemExit("legacy temp root gesture arbitration survived")

print("Legacy switcher patch now preserves main Home gestures and context-menu Open Data Folder")
