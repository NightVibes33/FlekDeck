#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
source = path.read_text()

old_init = '''    bool is32bit = false;
    if (needPatch) {'''
new_init = '''#if is32BitSupported
    // Once an ARM32 guest has been identified, keep that fact on later launches.
    // The legacy FlekDeck path reset this local to false whenever no repatch was
    // required and then overwrote the saved property, silently turning ARM32 off.
    bool is32bit = self.is32bit;
#else
    bool is32bit = false;
#endif
    if (needPatch) {'''
if new_init not in source:
    if old_init not in source:
        raise SystemExit("LCAppInfo.m: ARM32 detection initializer anchor missing")
    source = source.replace(old_init, new_init, 1)

old_detect = '''        is32bit = !has64bitSlice;
        LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
        if (isEncrypted) {'''
new_detect = '''        is32bit = !has64bitSlice;
#if is32BitSupported
        self.is32bit = is32bit;
#endif
        if (!is32bit) {
            LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
        } else {
#if is32BitSupported
            // LiveExec32 requires JIT and its iOS 11 compatibility flow. Persist
            // both at import time so subsequent launches take the emulator path.
            self.isJITNeeded = YES;
            self.spoofSDKVersion = YES;
#endif
        }
        if (isEncrypted) {'''
if new_detect not in source:
    if old_detect not in source:
        raise SystemExit("LCAppInfo.m: ARM32 Mach-O detection anchor missing")
    source = source.replace(old_detect, new_detect, 1)

old_post = '''#if !is32BitSupported
    if(is32bit) {
        completetionHandler(NO, @"32-bit app is NOT supported!");
        return;
    }
#else
    self.is32Bit = is32bit;
#endif

    if (!LCSharedUtils.certificatePassword || is32bit || self.dontSign) {'''
new_post = '''#if !is32BitSupported
    if(is32bit) {
        completetionHandler(NO, @"32-bit app is NOT supported!");
        return;
    }
#endif

    if (!LCSharedUtils.certificatePassword || is32bit || self.dontSign) {'''
if new_post not in source:
    if old_post not in source:
        raise SystemExit("LCAppInfo.m: legacy ARM32 property-reset block missing")
    source = source.replace(old_post, new_post, 1)

path.write_text(source)

required = [
    "bool is32bit = self.is32bit;",
    "self.is32bit = is32bit;",
    "self.isJITNeeded = YES;",
    "self.spoofSDKVersion = YES;",
]
text = path.read_text()
for marker in required:
    if marker not in text:
        raise SystemExit(f"LCAppInfo.m: missing ARM32 persistence marker: {marker}")
if "self.is32Bit = is32bit;" in text:
    raise SystemExit("LCAppInfo.m: stale mis-cased ARM32 property assignment remains")

print("FlekDeck ARM32 guest detection persistence applied")
