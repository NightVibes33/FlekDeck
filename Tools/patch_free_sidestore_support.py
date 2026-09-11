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

# Temp-branch-only LiveContainer/StikDebug alignment. This keeps normal single
# launch untouched while restoring Duy LiveContainer's private-app bookmark
# handoff for LiveProcess and using StikDebug's current PID-targeted URL scheme.
livecontainer_alignment = Path("Tools/patch_livecontainer_multitask_stikdebug.py")
if livecontainer_alignment.exists():
    exec(compile(livecontainer_alignment.read_text(), str(livecontainer_alignment), "exec"), {})

# Temp-branch-only probes. Main does not contain these files, so the production
# compatibility layer remains unchanged there. They run after the pinned Vibe
# core has been copied, which is the only point where its signer/Library
# Validation code can be instrumented meaningfully.
experiment = Path("Tools/patch_multitask_jit_diagnosis.py")
if experiment.exists():
    exec(compile(experiment.read_text(), str(experiment), "exec"), {})

# The signer-compatible workflow copies the pinned Vibe LCBootstrap over the
# repository version before this adapter runs. PiP's native guest bridge and
# YouTube sample-buffer binding are build-time compatibility layers, so they must
# be re-applied here after that copy. Keep the same order as the known-good
# direct multitask build. These scripts do not rewrite the app-switcher gesture.
for pip_patch_name in (
    "patch_guest_native_pip_bridge.py",
    "patch_youtube_native_pip_render.py",
    "patch_pip_state_separation.py",
):
    pip_patch = Path("Tools") / pip_patch_name
    if not pip_patch.exists():
        raise SystemExit(f"Required PiP compatibility patch missing: {pip_patch}")
    exec(compile(pip_patch.read_text(), str(pip_patch), "exec"), {})

# Fail closed if the Vibe core copy ever drops the PiP layer again.
bootstrap = Path("LiveContainer/LCBootstrap.m").read_text()
pip_manager = Path("MultitaskSupport/PiPManager.m").read_text()
for marker in (
    "LCGuestNativePiPBridge",
    "sampleBufferDisplayLayer",
    "LCYouTubePiPRefreshSource",
    "newContentSource",
):
    if marker not in bootstrap:
        raise SystemExit(f"PiP bootstrap marker missing after compatibility patches: {marker}")
for marker in (
    "startWindowPiPWithVC",
    "LCNativePiPDoesNotOwnWindowLifecycle",
    "LCNativePiPAutoWindowFallback",
):
    if marker not in pip_manager:
        raise SystemExit(f"PiP manager marker missing after compatibility patches: {marker}")

# Preserve the exact main/pre-PiP bottom-swipe implementation. The temporary
# persistent swipe rewrite replaced that path and is the app-switcher regression.
# Keep the historical patch file in the branch, but do not compile it.
gesture_bridge = Path("Tools/patch_guest_gesture_bridge.py")
if gesture_bridge.exists():
    print("Skipping obsolete persistent switcher-swipe rewrite; preserving main gesture path.")

print("Applied signer-compatible SideStore integration, PiP compatibility stack, and removed the false development-certificate launch alert")
