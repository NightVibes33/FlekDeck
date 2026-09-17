#!/usr/bin/env python3
from pathlib import Path

branch = "temp/32bit-liveexec-data-folder"
canonical = Path(".github/workflows/flekdeck-final-ondevice-audit.yml")
text = canonical.read_text()
if "  workflow_call:\n" not in text:
    anchor = "on:\n  workflow_dispatch:\n"
    if anchor not in text:
        raise SystemExit("final audit workflow trigger anchor missing")
    text = text.replace(anchor, "on:\n  workflow_call:\n  workflow_dispatch:\n", 1)
canonical.write_text(text)

wrappers = {
    ".github/workflows/build-flekdeck-full-parity-temp.yml": "FlekDeck Full Parity Temp IPA",
    ".github/workflows/build-flekdeck-32bit-temp.yml": "FlekDeck 32-bit Temp IPA",
    ".github/workflows/build-flekdeck-32bit-parity-temp.yml": "FlekDeck ARM32 + Parity Temp IPA",
}

for path_str, name in wrappers.items():
    path = Path(path_str)
    path.write_text(f'''name: {name}\n\non:\n  workflow_dispatch:\n\npermissions:\n  contents: write\n\njobs:\n  canonical-audited-build:\n    uses: ./.github/workflows/flekdeck-final-ondevice-audit.yml\n    secrets: inherit\n''')

# Invariants: there must now be exactly one implementation of the temp build.
if "workflow_call:" not in canonical.read_text():
    raise SystemExit("canonical final audit is not reusable")
for path_str in wrappers:
    value = Path(path_str).read_text()
    if "flekdeck-final-ondevice-audit.yml" not in value:
        raise SystemExit(f"{path_str}: does not delegate to final audit")
    for stale in (
        "patch_direct_multitask_host_bridge.py",
        "patch_flekdeck_classic_mode.py",
        "patch_flekdeck_classic_mode_parity.py",
        "patch_flekdeck_livecontainer_parity.py",
    ):
        if stale in value:
            raise SystemExit(f"{path_str}: stale divergent build logic remains: {stale}")

print("All legacy temp builders now delegate to the canonical Final On-Device Audit")
