#!/usr/bin/env python3
from pathlib import Path

p = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m")
s = p.read_text()

old_decl = 'void bypass_os_variant_has_internal_content(void (^block)(void));\n'
local_helper = '''static void LCFlekClassicProbeBypass(void (^block)(void)) {
    if (block) block();
}
'''

if old_decl in s:
    s = s.replace(old_decl, local_helper, 1)
elif "static void LCFlekClassicProbeBypass" not in s:
    raise SystemExit(f"{p}: Compatibility bypass declaration anchor missing")

s = s.replace('bypass_os_variant_has_internal_content(^{', 'LCFlekClassicProbeBypass(^{')

# iOS 27 private SpringBoard application objects can terminate the host by
# signal, which Objective-C @try cannot catch. Keep LiveContainer's guarded
# probe on older releases, but on iOS 27 derive the stable launch-mode hint from
# the guest device-family metadata before any SpringBoard private class is used.
needle = '''        NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;
        NSURL *executableURL = bundle.executableURL;
        if (!bundle || !executableURL) return @0;

        static Class SBApplicationClass = Nil;'''
replacement = '''        NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;
        NSURL *executableURL = bundle.executableURL;
        if (!bundle || !executableURL) return @0;

        if (@available(iOS 27.0, *)) {
            NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];
            BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] && [families containsObject:@2];
            NSUInteger safeClassicMode =
                (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad && guestSupportsPad)
                    ? 12u : 1u;
            NSLog(@"[FlekDeck/ClassicMode] iOS 27 safe mode=%lu; private SpringBoard probe skipped",
                  (unsigned long)safeClassicMode);
            return @(safeClassicMode);
        }

        static Class SBApplicationClass = Nil;'''
if replacement not in s:
    if needle not in s:
        raise SystemExit(f"{p}: Compatibility function anchor missing")
    s = s.replace(needle, replacement, 1)

if "bypass_os_variant_has_internal_content" in s:
    raise SystemExit(f"{p}: unresolved Compatibility bypass symbol remains")
if "static void LCFlekClassicProbeBypass" not in s:
    raise SystemExit(f"{p}: local Compatibility bypass helper missing")
if "LCFlekClassicProbeBypass(^{" not in s:
    raise SystemExit(f"{p}: SpringBoard load is not using the local bypass")
if "iOS 27 safe mode=" not in s:
    raise SystemExit(f"{p}: iOS 27 safe Compatibility fallback missing")

p.write_text(s)
print("FlekDeck Compatibility probe uses local bypass and skips crash-prone SpringBoard objects on iOS 27")
