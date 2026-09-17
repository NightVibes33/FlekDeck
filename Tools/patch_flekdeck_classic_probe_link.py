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

if "bypass_os_variant_has_internal_content" in s:
    raise SystemExit(f"{p}: unresolved Compatibility bypass symbol remains")
if "static void LCFlekClassicProbeBypass" not in s:
    raise SystemExit(f"{p}: local Compatibility bypass helper missing")
if "LCFlekClassicProbeBypass(^{" not in s:
    raise SystemExit(f"{p}: SpringBoard load is not using the local bypass")

p.write_text(s)
print("FlekDeck Compatibility probe uses the proven local bypass boundary")
