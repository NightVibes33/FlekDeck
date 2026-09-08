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

# Upstream LiveContainer intentionally treats get-task-allow as a warning and
# lets the real signed-library validation / guest launch decide whether the
# current signer works. Do not reintroduce FlekDeck-only hard gates here.
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

print("Applied signer-compatible SideStore integration while preserving LiveContainer JIT-less behavior")
