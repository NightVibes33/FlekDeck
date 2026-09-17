#!/usr/bin/env python3
from pathlib import Path

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()

# UIKit Springboard context-menu container picker.
old = '''                ) { _ in
                    app.uiSelectedContainer = container
                    LCSpringboardPageCell.refreshActiveContextMenu()
                }'''
new = '''                ) { _ in
                    app.uiSelectedContainer = container
                    app.uiDefaultDataFolder = container.folderName
                    app.appInfo.dataUUID = container.folderName
                    LCSpringboardPageCell.refreshActiveContextMenu()
                }'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: UIKit quick-container action anchor missing")
    text = text.replace(old, new, 1)

# SwiftUI/list context-menu container picker.
old = '''                    Button {
                        app.uiSelectedContainer = container
                    } label: {'''
new = '''                    Button {
                        app.uiSelectedContainer = container
                        app.uiDefaultDataFolder = container.folderName
                        app.appInfo.dataUUID = container.folderName
                    } label: {'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: SwiftUI quick-container action anchor missing")
    text = text.replace(old, new, 1)

app_list.write_text(text)

final = app_list.read_text()
if final.count("app.appInfo.dataUUID = container.folderName") < 2:
    raise SystemExit("Quick-container selection is not persisted in both menu implementations")
if final.count("app.uiDefaultDataFolder = container.folderName") < 2:
    raise SystemExit("Quick-container UI default is not synchronized in both menu implementations")

print("FlekDeck Home quick-container selection now persists LCDataUUID in UIKit and SwiftUI menus")
