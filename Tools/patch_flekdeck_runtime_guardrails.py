#!/usr/bin/env python3
from pathlib import Path
import runpy

# Keep the established defaults/settings/runtime passes, then apply the final
# post-scan hardening after every older parity generator has finished.
runpy.run_path("Tools/patch_flekdeck_defaults_settings_stability.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_liveexec32_txm.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_ondevice_regressions.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_signing_stability.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_liveexec32_loader_guard.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_error_transport.py", run_name="__main__")

app_info_path = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
macho_path = Path("LiveContainer/LCMachOUtils.m")
app_info_before_macho = app_info_path.read_text()
macho_before = macho_path.read_text()
migrated_macho_contract = all(marker in app_info_before_macho for marker in (
    'needsArchitectureClassification = (info[@"is32bit"] == nil)',
    'LCInspectMachOArchitectures(execPath.UTF8String, &has64bitSlice, &has32bitSlice, &isEncrypted)',
    'is32bit = !has64bitSlice && has32bitSlice',
    'if(!error && needPatch && has64bitSlice)',
)) and all(marker in macho_before for marker in (
    'NSString *LCInspectMachOArchitectures(',
    'cpu != CPU_TYPE_ARM64) continue',
    'ARM32 is intentionally inspection-only',
))
if migrated_macho_contract:
    print("FlekDeck Mach-O contract already migration-aware; preserving canonical form")
else:
    runpy.run_path("Tools/patch_flekdeck_macho_contract.py", run_name="__main__")

runpy.run_path("Tools/patch_flekdeck_macho_sdk_reader.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_arm32_migration.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_runtime_selection.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_classic_launch_isolation.py", run_name="__main__")

# Canonicalize the model block after older parity generators.
app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = app_info.read_text()
start = text.find("- (bool)classicMode {")
end = text.find("- (bool)isLocked {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{app_info}: Classic model block markers missing")
canonical = '''- (bool)classicMode {
    return [_info[@"classicMode"] boolValue];
}

- (void)setClassicMode:(bool)classicMode {
    _info[@"classicMode"] = @(classicMode);
    if(!classicMode) {
        [_info removeObjectForKey:@"LCClassicModeCache"];
    }
    [self save];
}

- (NSUInteger)defaultClassicMode {
    if(!self.classicMode) return 0;

    NSInteger systemMajorVersion = NSProcessInfo.processInfo.operatingSystemVersion.majorVersion;
    NSDictionary *cache = _info[@"LCClassicModeCache"];
    NSNumber *cachedMode = cache[@"defaultClassicMode"];
    NSNumber *cachedSystemMajorVersion = cache[@"systemMajorVersion"];
    if([cachedMode isKindOfClass:NSNumber.class] &&
       [cachedSystemMajorVersion isKindOfClass:NSNumber.class] &&
       cachedSystemMajorVersion.integerValue == systemMajorVersion) {
        return cachedMode.unsignedIntegerValue;
    }

    NSNumber *mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    if (![mode isKindOfClass:NSNumber.class]) mode = @0;
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": mode,
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return mode.unsignedIntegerValue;
}

'''
text = text[:start] + canonical + text[end:]
app_info.write_text(text)

# These layers own the earlier user-reported regressions and must run after old
# parity transforms. Post-scan behavior and its target-link adapter are last.
runpy.run_path("Tools/patch_flekdeck_user_regressions.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_relaunch_safety.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_context_runtime.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_postscan_runtime.py", run_name="__main__")
runpy.run_path("Tools/patch_flekdeck_classic_probe_link.py", run_name="__main__")
# The parent edit/drag long press and the inner UIKit context menu are separate
# recognizers. Reject only the parent recognizer for installed-app holds, before
# it begins, so the menu is reliable without touching the switcher pan gesture.
runpy.run_path("Tools/patch_flekdeck_context_menu_arbitration.py", run_name="__main__")


def add_trigger_path(text: str, anchor: str) -> str:
    marker = "      - 'Tools/patch_flekdeck_runtime_guardrails.py'\n"
    if marker in text:
        return text
    if anchor not in text:
        return text
    return text.replace(anchor, anchor + marker, 1)


full = Path(".github/workflows/build-flekdeck-full-parity-temp.yml")
if full.exists():
    value = full.read_text()
    value = add_trigger_path(value, "      - 'Tools/patch_flekdeck_shell_parity.py'\n")
    needle = "            Tools/patch_flekdeck_shell_parity.py\n"
    replacement = needle + "            Tools/patch_flekdeck_runtime_guardrails.py\n"
    if "Tools/patch_flekdeck_runtime_guardrails.py\n          )" not in value:
        value = value.replace(needle, replacement)
    full.write_text(value)

arm32 = Path(".github/workflows/build-flekdeck-32bit-temp.yml")
if arm32.exists():
    value = arm32.read_text()
    value = add_trigger_path(value, "      - 'Tools/patch_flekdeck_classic_mode_parity.py'\n")
    needle = "          python3 Tools/patch_flekdeck_classic_mode_parity.py\n"
    replacement = needle + "          python3 Tools/patch_flekdeck_runtime_guardrails.py\n"
    if "python3 Tools/patch_flekdeck_runtime_guardrails.py" not in value:
        value = value.replace(needle, replacement)
    arm32.write_text(value)

parity = Path(".github/workflows/build-flekdeck-32bit-parity-temp.yml")
if parity.exists():
    value = parity.read_text()
    value = add_trigger_path(value, "      - 'Tools/patch_flekdeck_classic_mode.py'\n")
    needle = "          python3 Tools/patch_flekdeck_classic_mode.py\n"
    replacement = needle + "          python3 Tools/patch_flekdeck_runtime_guardrails.py\n"
    if "python3 Tools/patch_flekdeck_runtime_guardrails.py" not in value:
        value = value.replace(needle, replacement)
    value = value.replace(
        "          grep -q 'classicMode != 0' LiveContainerSwiftUI/Models/LCAppModel.swift\n          grep -q 'appInfo.is32bit || classicMode != 0' LiveContainerSwiftUI/Models/LCAppModel.swift\n",
        "          grep -q 'appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)' LiveContainerSwiftUI/Models/LCAppModel.swift\n"
    )
    value = value.replace(
        "          grep -q 'FBSOpenApplicationOptionKeyActivateAsClassic' LiveContainer/LCSharedUtils.m\n",
        "          grep -q '__ActivateAsClassic' LiveContainer/LCSharedUtils.m\n"
    )
    parity.write_text(value)

# Final end-to-end invariants.
final = app_info.read_text()
if final.count("- (NSUInteger)defaultClassicMode {") != 1:
    raise SystemExit(f"{app_info}: duplicate defaultClassicMode implementations remain")
if final.count("- (bool)classicMode {") != 1:
    raise SystemExit(f"{app_info}: duplicate classicMode implementations remain")
if "(void)[self defaultClassicMode]" in final[final.find("- (void)setClassicMode:"):final.find("- (NSUInteger)defaultClassicMode")]:
    raise SystemExit(f"{app_info}: Compatibility Mode toggle still executes the probe")
if "LCInspectMachOArchitectures" not in final:
    raise SystemExit(f"{app_info}: safe ARM32 inspection contract missing")
if "LCReadMachOSDKVersion(execPath.UTF8String, self.is32bit, &sdkVersion)" not in final:
    raise SystemExit(f"{app_info}: architecture-aware linked SDK reader missing")
if "self.is32bit && LCUtils.isTXMScriptRequired" not in final:
    raise SystemExit(f"{app_info}: ARM32 TXM automatic JIT script selection missing")
if 'needsArchitectureClassification = (info[@"is32bit"] == nil)' not in final:
    raise SystemExit(f"{app_info}: existing-app ARM32 migration missing")
if "if (!_autoSaveDisabled) [self save];" not in final[final.find("- (void)setSelected32BitEmulator:"):final.find("- (bool)is32bitEmulator", final.find("- (void)setSelected32BitEmulator:"))]:
    raise SystemExit(f"{app_info}: ARM32 runtime override setter ignores bulk-save mode")

bootstrap = Path("LiveContainer/LCBootstrap.m").read_text()
for marker in (
    "guestExecutablePath.length == 0",
    "hasLoadPath != hasEntrySymbol",
    "runtime launcher executable is missing or not executable",
    "Bookmark resolution failed without an NSError.",
    "Security-scoped access denied for data container:",
    "if(!lcSharedDefaults)",
):
    if marker not in bootstrap:
        raise SystemExit(f"LiveExec32/error/defaults hardening missing: {marker}")
if "The security-scoped resource denied access." in bootstrap:
    raise SystemExit("generic external-container failure survived")
if "stringByAppendingString:err.localizedDescription" in bootstrap:
    raise SystemExit("nil-unsafe external-container error transport survived")

app_entry = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift").read_text()
if "Repaired stale default runtime" not in app_entry or "Cleared stale per-app runtime" not in app_entry:
    raise SystemExit("ARM32 runtime-selection normalization missing")

app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift").read_text()
if "let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode" not in app_model:
    raise SystemExit("Compatibility Mode is not isolated from Parallel launch routing")
if "guard LCSharedUtils.launchToGuestApp(withClassicMode: classicMode) else" not in app_model:
    raise SystemExit("Immediate single-process relaunch failure is still ignored")

probe = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m").read_text()
if "NSCAssert(" in probe or "assert(" in probe:
    raise SystemExit("process-fatal Compatibility probe survived")
for marker in (
    "_defaultClassicMode",
    "instancesRespondToSelector:modernInit",
    "LCInspectMachOArchitectures",
    "LCReadMachOSDKVersion",
    "probe failed safely",
    "static void LCFlekClassicProbeBypass",
    "LCFlekClassicProbeBypass(^{",
):
    if marker not in probe:
        raise SystemExit(f"real crash-safe Compatibility probe missing: {marker}")
if "bypass_os_variant_has_internal_content" in probe:
    raise SystemExit("unlinked Compatibility bypass symbol survived")
if "return @12;" in probe or "return @1;" in probe:
    raise SystemExit("hard-coded Compatibility Mode heuristic survived")

spring_drag = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardDragManager.swift").read_text()
spring_vc = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift").read_text()
for marker in (
    "UIGestureRecognizerDelegate",
    "gestureRecognizerShouldBegin",
    "if case .installed = pageCell.items[indexPath.item]",
):
    if marker not in spring_drag:
        raise SystemExit(f"installed-app context-menu arbitration missing: {marker}")
if "longPressGesture.delegate = dragManager" not in spring_vc:
    raise SystemExit("Springboard parent long press is not yielding to installed-app context menus")

for error_ui in (
    Path("LiveContainerSwiftUI/Views/LCTabView.swift").read_text(),
    Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift").read_text(),
):
    if "No diagnostic text was provided" in error_ui:
        raise SystemExit("synthetic generic app error survived")

app_list_text = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift").read_text()
if app_list_text.count("app.appInfo.dataUUID = container.folderName") < 2:
    raise SystemExit("Home quick-container selection is not persisted in both menu paths")
if "finalNewApp.selected32BitEmulator = appToReplace.appInfo.selected32BitEmulator" not in app_list_text:
    raise SystemExit("per-app ARM32 runtime override is not preserved across app replacement")

shared = Path("LiveContainer/LCSharedUtils.m").read_text()
classic_region = shared[shared.find("+ (BOOL)launchToGuestAppWithClassicMode"):shared.find("+ (BOOL)launchToGuestAppWithURL")]
if classic_region.count("+ (BOOL)launchToGuestAppWithClassicMode") != 1:
    raise SystemExit("Duplicate Classic relaunch methods remain")
if "if(success)" not in classic_region or "falling back" not in classic_region:
    raise SystemExit("Classic relaunch is not fail-safe")
if "guestSupportsPad" in shared:
    raise SystemExit("deep-link Compatibility path still invents a generic classic mode")
normal_region = shared[shared.find("+ (BOOL)launchToGuestApp {"):shared.find("+ (BOOL)launchToGuestAppWithClassicMode")]
if "if(!success)" not in normal_region or "keeping host alive" not in normal_region:
    raise SystemExit("Normal relaunch still terminates on a rejected openURL")
if "exit(0);" in normal_region:
    raise SystemExit("Normal relaunch still exits when no relaunch URL can be opened")

settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift").read_text()
if 'TextField("", text: $liveExec32Path)' in settings:
    raise SystemExit("unsafe raw ARM32 runtime field survived")
if "Default 32-bit Runtime" not in settings:
    raise SystemExit("validated ARM32 runtime picker is missing")

utils_impl = Path("LiveContainerSwiftUI/Utilities/LCUtils.m").read_text()
if "NSError *error;" in utils_impl:
    raise SystemExit("uninitialized NSError local remains in signer utilities")
if "if (error) *error = nil;" not in utils_impl:
    raise SystemExit("ZSign loader does not initialize its NSError out-parameter")

print("FlekDeck runtime guardrails applied with full post-scan protections")
