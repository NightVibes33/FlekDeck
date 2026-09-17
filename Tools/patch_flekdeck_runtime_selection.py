#!/usr/bin/env python3
from pathlib import Path

app = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift")
text = app.read_text()
old = '''        DataManager.shared.model.apps = tempApps
#if is32BitSupported
        DataManager.shared.model.arm32EmuApps = tempArm32EmuApps
#endif
        DataManager.shared.model.hiddenApps = tempHiddenApps'''
new = '''        DataManager.shared.model.apps = tempApps
#if is32BitSupported
        DataManager.shared.model.arm32EmuApps = tempArm32EmuApps

        // Runtime choices are persisted across updates/removals. Normalize them
        // against the runtimes that actually exist now so a stale path cannot
        // make every ARM32 app fail forever. Per-app stale overrides fall back to
        // the global selection; the global selection prefers bundled LiveExec32.
        let available32BitRuntimeNames = Set(tempArm32EmuApps.compactMap { model in
            model.appInfo.relativeBundlePath.map { ($0 as NSString).lastPathComponent }
        })
        let runtimeDefaults = LCUtils.appGroupUserDefault
        let persistedDefault = runtimeDefaults.string(forKey: "LCSelected32BitEmulator") ?? ""
        let persistedDefaultName = (persistedDefault as NSString).lastPathComponent
        if !persistedDefaultName.isEmpty && !available32BitRuntimeNames.contains(persistedDefaultName) {
            if available32BitRuntimeNames.contains(Self.bundled32BitRuntimeName) {
                runtimeDefaults.set(Self.bundled32BitRuntimeName, forKey: "LCSelected32BitEmulator")
                NSLog("[FlekDeck/LC32] Repaired stale default runtime %@ -> %@", persistedDefaultName, Self.bundled32BitRuntimeName)
            } else if let firstRuntime = available32BitRuntimeNames.sorted().first {
                runtimeDefaults.set(firstRuntime, forKey: "LCSelected32BitEmulator")
                NSLog("[FlekDeck/LC32] Repaired stale default runtime %@ -> %@", persistedDefaultName, firstRuntime)
            } else {
                runtimeDefaults.removeObject(forKey: "LCSelected32BitEmulator")
            }
        }

        for model in tempApps + tempHiddenApps where model.appInfo.is32bit {
            guard let selected = model.appInfo.selected32BitEmulator, !selected.isEmpty else { continue }
            let selectedName = (selected as NSString).lastPathComponent
            if !available32BitRuntimeNames.contains(selectedName) {
                model.appInfo.selected32BitEmulator = ""
                model.uiSelected32BitEmulator = ""
                NSLog("[FlekDeck/LC32] Cleared stale per-app runtime %@ for %@", selectedName, model.appInfo.displayName())
            }
        }
#endif
        DataManager.shared.model.hiddenApps = tempHiddenApps'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app}: ARM32 runtime publication anchor missing")
    text = text.replace(old, new, 1)
app.write_text(text)

value = app.read_text()
for needle in (
    "available32BitRuntimeNames",
    "Repaired stale default runtime",
    "Cleared stale per-app runtime",
    'removeObject(forKey: "LCSelected32BitEmulator")',
):
    if needle not in value:
        raise SystemExit(f"{app}: missing runtime-selection normalization marker: {needle}")

print("FlekDeck ARM32 runtime selections normalized against discovered runtimes")
