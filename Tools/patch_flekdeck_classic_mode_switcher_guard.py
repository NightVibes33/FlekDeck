#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/patch_flekdeck_classic_mode_parity.py")
text = path.read_text()

old = '''new_multitask = \'\'\'        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // LiveExec32 and Classic Mode both require the single-process host path.
        let multitask = (appInfo.is32bit || classicMode != 0) ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = classicMode == 0 ? (multitask ?? shouldLaunchInMultitaskMode) : false
#endif\'\'\''''

new = '''new_multitask = \'\'\'        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // Preserve FlekDeck's App Switcher / Parallel routing for native ARM64.
        // Only ARM32 is forced to the single-process LiveExec32 path; Classic
        // Mode is consumed if the single-process path is actually selected.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif\'\'\''''

if new not in text:
    if old not in text:
        raise SystemExit(f"{path}: Classic Mode multitask generator block not found")
    text = text.replace(old, new, 1)

path.write_text(text)

if "classicMode != 0) ? false" in text or "classicMode == 0 ?" in text:
    raise SystemExit(f"{path}: Classic Mode still contains an App Switcher override")
if "appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)" not in text:
    raise SystemExit(f"{path}: ARM32-only routing guard missing")

print("Classic Mode parity generator now preserves FlekDeck App Switcher routing")
