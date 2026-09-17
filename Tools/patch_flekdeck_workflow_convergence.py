#!/usr/bin/env python3
from pathlib import Path

canonical = Path(".github/workflows/build-flekdeck-sidestore-parity-temp.yml")
text = canonical.read_text()
if "  workflow_call:\n" not in text:
    anchor = "on:\n  workflow_dispatch:\n"
    if anchor not in text:
        raise SystemExit("SideStore parity workflow trigger anchor missing")
    text = text.replace(anchor, "on:\n  workflow_call:\n  workflow_dispatch:\n", 1)
canonical.write_text(text)

wrappers = {
    ".github/workflows/build-flekdeck-full-parity-temp.yml": "FlekDeck Full Parity Temp IPA",
    ".github/workflows/build-flekdeck-32bit-temp.yml": "FlekDeck 32-bit Temp IPA",
    ".github/workflows/build-flekdeck-32bit-parity-temp.yml": "FlekDeck ARM32 + Parity Temp IPA",
}

for path_str, name in wrappers.items():
    path = Path(path_str)
    path.write_text(f'''name: {name}\n\non:\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\njobs:\n  canonical-sidestore-build:\n    uses: ./.github/workflows/build-flekdeck-sidestore-parity-temp.yml\n    secrets: inherit\n''')

# Final On-Device Audit remains an audit/debug workflow. It is intentionally not
# the canonical install artifact because its raw unsigned packaging omits the
# SideStore metadata/signature contract used by main.
if "workflow_call:" not in canonical.read_text():
    raise SystemExit("canonical SideStore builder is not reusable")

for path_str in wrappers:
    value = Path(path_str).read_text()
    if "build-flekdeck-sidestore-parity-temp.yml" not in value:
        raise SystemExit(f"{path_str}: does not delegate to SideStore-compatible builder")
    for stale in (
        "flekdeck-final-ondevice-audit.yml",
        "patch_direct_multitask_host_bridge.py",
        "patch_flekdeck_classic_mode.py",
        "patch_flekdeck_classic_mode_parity.py",
        "patch_flekdeck_livecontainer_parity.py",
    ):
        if stale in value:
            raise SystemExit(f"{path_str}: stale divergent install-build logic remains: {stale}")

print("All legacy temp install builders now delegate to the canonical SideStore-compatible build")
