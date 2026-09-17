#!/usr/bin/env python3
from pathlib import Path

# Keep guest crash/error state scoped to exactly one launch attempt. A stale
# UserDefaults["error"] or ARM32 log URL must never bleed into the next app.
app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
s = app_model.read_text()

anchor = '''        try await signApp(force: false)\n        \n        if let bundleIdOverride {'''
replacement = '''        try await signApp(force: false)\n\n        // Start every guest attempt with a clean diagnostic slot. The bootstrap\n        // is the sole owner of the next guest error, so an app which dies before\n        // writing one cannot inherit the previous app's crash text or ARM32 log.\n        UserDefaults.standard.removeObject(forKey: "error")\n        UserDefaults.lcShared().removeObject(forKey: "LC32BitTranslationLayerLogFile")\n        \n        if let bundleIdOverride {'''
if replacement not in s:
    if anchor not in s:
        raise SystemExit(f"{app_model}: launch diagnostic reset anchor missing")
    s = s.replace(anchor, replacement, 1)

old = '''            guard LCSharedUtils.launchToGuestApp(withClassicMode: classicMode) else {\n                throw "FlekDeck could not relaunch the selected app. The host launch URL or Compatibility Mode relaunch surface is unavailable."\n            }'''
new = '''            guard LCSharedUtils.launchToGuestApp(withClassicMode: classicMode) else {\n                // This is a host relaunch failure: the guest never started, so do\n                // not fabricate or reuse a guest crash report. Keep it explicit.\n                throw "Host relaunch was rejected before \\(appInfo.displayName()) started. No guest crash report was produced."\n            }'''
if new not in s:
    if old not in s:
        raise SystemExit(f"{app_model}: synthetic relaunch error anchor missing")
    s = s.replace(old, new, 1)

app_model.write_text(s)

# The startup surface must consume only backend-provided guest text. It should
# never turn an absent value into a generic crash message.
tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
t = tab.read_text()
if 'guard let raw = defaults.string(forKey: "error") else {' not in t:
    raise SystemExit(f"{tab}: raw backend guest error reader missing")
if 'defaults.removeObject(forKey: "error")' not in t:
    raise SystemExit(f"{tab}: consumed guest error is not cleared")
if "No diagnostic text was provided" in t:
    raise SystemExit(f"{tab}: synthetic generic guest error remains")

# Final invariants.
final = app_model.read_text()
for marker in (
    'UserDefaults.standard.removeObject(forKey: "error")',
    'UserDefaults.lcShared().removeObject(forKey: "LC32BitTranslationLayerLogFile")',
    'No guest crash report was produced.',
):
    if marker not in final:
        raise SystemExit(f"{app_model}: per-launch error isolation missing: {marker}")
if "FlekDeck could not relaunch the selected app" in final:
    raise SystemExit(f"{app_model}: old generic relaunch error survived")

print("FlekDeck guest errors isolated per launch; stale/fake cross-app diagnostics removed")
