from pathlib import Path

# Keep FlekDeck's SideStore integration rebrand-aware without changing the
# LiveContainer/VibeContainers JIT-less execution semantics.
p = Path("SideStoreSupport/SideStoreHooks.m")
s = p.read_text()
s = s.replace(
    '+ (NSString*)hook_appbundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_appbundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    'https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json',
    'https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json'
)
if 'com.fs.flekdeck' not in s or 'flekdeck-side-source.json' not in s:
    raise SystemExit("SideStore rebrand patch did not apply")
p.write_text(s)

# Upstream exposes get-task-allow as diagnostic information, but a successful
# signed-library JIT-less test proves that the current signer actually works.
# FlekDeck must not surface the old fatal-sounding startup alert for an ESign /
# distribution-signed host after the real JIT-less path is usable. Keep the
# entitlement visible in the diagnostics screen; only remove the misleading
# lifecycle alert.
tab_path = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
tab = tab_path.read_text()
old_check = '''    func checkGetTaskAllow() {\n        let task = SecTaskCreateFromSelf(nil)\n        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil), (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {\n            errorInfo = "lc.settings.notDevCert".loc\n            errorShow = true\n            return\n        }\n    }\n'''
new_check = '''    func checkGetTaskAllow() {\n        // Informational only. `get-task-allow` is not an authoritative JIT-less\n        // capability test for every third-party signer. The signed-library\n        // diagnostic and real guest launch are the source of truth.\n        let task = SecTaskCreateFromSelf(nil)\n        let allowed = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil)\n            .map { ($0.takeRetainedValue() as? NSNumber)?.boolValue ?? false } ?? false\n        if !allowed {\n            print("FlekDeck: get-task-allow is false; continuing with signer-based JIT-less validation")\n        }\n    }\n'''
if old_check in tab:
    tab = tab.replace(old_check, new_check, 1)
elif 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Unexpected get-task-allow alert shape in LCTabView")

if 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Fatal development-certificate alert still present in LCTabView")
tab_path.write_text(tab)

# Preserve the actual Vibe/LiveContainer JIT-less signer and guest-launch path.
model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift").read_text()
diag = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift").read_text()

for forbidden in (
    "FlekHostHasDevelopmentSigning",
    "FlekHostDevelopmentSigningError",
):
    if forbidden in model:
        raise SystemExit(f"Unexpected FlekDeck JIT-less hard gate in LCAppModel: {forbidden}")

if "FlekDeck host does not have get-task-allow" in diag:
    raise SystemExit("Unexpected FlekDeck get-task-allow hard gate in JIT-less diagnostics")

if "LCUtils.validateJITLessSetup" not in diag:
    raise SystemExit("JIT-less diagnostic no longer performs the real signed-library validation")
if "LCSharedUtils.launchToGuestApp" not in model:
    raise SystemExit("LCAppModel no longer contains the upstream JIT-less guest launch path")

# Temp-branch-only probe. Main does not contain this file, so the production
# compatibility layer remains unchanged there. The experiment script runs after
# the pinned Vibe core has been copied, which is the only point where its signer
# and Library Validation code can be instrumented meaningfully.
experiment = Path("Tools/patch_multitask_jit_diagnosis.py")
if experiment.exists():
    exec(compile(experiment.read_text(), str(experiment), "exec"), {})

print("Applied signer-compatible SideStore integration and removed the false development-certificate launch alert")
