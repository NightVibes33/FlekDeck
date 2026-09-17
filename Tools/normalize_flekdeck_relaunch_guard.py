#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
s = path.read_text()

canonical = '''            guard LCSharedUtils.launchToGuestApp(withClassicMode: classicMode) else {
                throw "FlekDeck could not relaunch the selected app. The host launch URL or Compatibility Mode relaunch surface is unavailable."
            }
        }
        
        // Record the launch time'''

if canonical not in s:
    marker = "            guard LCSharedUtils.launchToGuestApp(withClassicMode: classicMode) else {"
    start = s.find(marker)
    record = s.find("        // Record the launch time", start)
    if start >= 0 and record >= 0:
        # Replace the entire already-hardened guard + enclosing single-process
        # branch tail with the canonical form expected by postscan_runtime.
        s = s[:start] + canonical + "\n" + s[record + len("        // Record the launch time"):]
    else:
        legacy = '''            LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)
        }
        
        // Record the launch time'''
        if legacy in s:
            s = s.replace(legacy, canonical, 1)
        else:
            raise SystemExit(f"{path}: no recognized single-process relaunch block")

path.write_text(s)

final = path.read_text()
if canonical not in final:
    raise SystemExit(f"{path}: canonical relaunch guard was not installed")
print("FlekDeck single-process relaunch guard normalized")
