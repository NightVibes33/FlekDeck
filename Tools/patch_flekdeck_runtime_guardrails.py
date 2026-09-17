#!/usr/bin/env python3
from pathlib import Path
import runpy

# Always run the primary stability hardening last.
runpy.run_path("Tools/patch_flekdeck_runtime_stability.py", run_name="__main__")
# Then apply the on-device regression fixes that preserve real guest errors,
# keep distribution-signing diagnostics non-modal, and repair the nullable
# app-group defaults path produced by the stability generator.
runpy.run_path("Tools/patch_flekdeck_ondevice_regressions.py", run_name="__main__")

# Old parity generators can append another Classic implementation because their
# template no longer byte-matches the hardened one. Canonicalize the entire
# model block after every parity pass so duplicate ObjC selectors can never ship.
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
    if(classicMode) {
        (void)[self defaultClassicMode];
    } else {
        [_info removeObjectForKey:@"LCClassicModeCache"];
        [self save];
    }
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

    NSNumber *mode = nil;
    @try {
        mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    } @catch (NSException *exception) {
        NSLog(@"[FlekDeck/ClassicMode] default-mode probe exception: %@ %@", exception.name, exception.reason);
    }
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

# Make every legacy temp workflow run this guardrail last, both for validation
# and for any source bake. This prevents a later parity rebuild from restoring
# the unsafe Compatibility Mode / defaults / Mach-O behavior.
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

# Final duplicate/unsafe checks.
final = app_info.read_text()
if final.count("- (NSUInteger)defaultClassicMode {") != 1:
    raise SystemExit(f"{app_info}: duplicate defaultClassicMode implementations remain")
if final.count("- (bool)classicMode {") != 1:
    raise SystemExit(f"{app_info}: duplicate classicMode implementations remain")

shared = Path("LiveContainer/LCSharedUtils.m").read_text()
classic_region = shared[shared.find("+ (BOOL)launchToGuestAppWithClassicMode"):shared.find("+ (BOOL)launchToGuestAppWithURL")]
if classic_region.count("+ (BOOL)launchToGuestAppWithClassicMode") != 1:
    raise SystemExit("Duplicate Classic relaunch methods remain")
if "completionHandler(success);" in classic_region:
    raise SystemExit("Unsafe unconditional Classic completion handler remains")

print("FlekDeck runtime guardrails applied")
