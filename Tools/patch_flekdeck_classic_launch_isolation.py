#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
text = path.read_text()
old = '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // Preserve FlekDeck's App Switcher / Parallel routing for every native
        // ARM64 guest. Only ARM32 is forced onto the single-process LiveExec32
        // path; Classic Mode is consumed only if that single-process path wins.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif'''
new = '''#if is32BitSupported
        // Preserve FlekDeck's proven App Switcher / Parallel routing for every
        // native ARM64 guest. Only ARM32 is forced onto LiveExec32 single mode.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif
        // Compatibility Mode is a single-process launch option. Resolving it can
        // touch private SpringBoard APIs, so never probe it for Parallel launches
        // that cannot consume the result anyway.
        let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{path}: Classic/Parallel decision anchor missing")
    text = text.replace(old, new, 1)
path.write_text(text)

value = path.read_text()
if "let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode" not in value:
    raise SystemExit(f"{path}: Classic Mode is not isolated from Parallel")
if value.find("appInfo.defaultClassicMode") < value.find("let multitask"):
    raise SystemExit(f"{path}: private Classic probe still executes before launch-mode resolution")

print("FlekDeck Compatibility Mode isolated to final single-process launches")

# Audit trigger marker: regression-chain repair validated after main-switcher restore.
