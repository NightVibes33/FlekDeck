#!/usr/bin/env python3
"""Create an isolated, disposable Nyxian source tree for the Xcode build."""

from pathlib import Path
import hashlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DONOR = ROOT / "Vendor" / "Nyxian"
OUTPUT = ROOT / "build" / "NyxianGenerated"
EXPECTED = "6db6de99271bd12499b68711da1e92edf169b431"


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, dirs_exist_ok=True)


def main() -> None:
    actual = subprocess.check_output(
        ["git", "-C", str(DONOR), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != EXPECTED:
        raise SystemExit(f"Nyxian donor mismatch: expected {EXPECTED}, got {actual}")

    shutil.rmtree(OUTPUT, ignore_errors=True)
    (OUTPUT / "Nyxian").mkdir(parents=True)
    copy_tree(DONOR / "Nyxian" / "LindChain", OUTPUT / "Nyxian" / "LindChain")
    copy_tree(DONOR / "LiveProcess", OUTPUT / "LiveProcess")
    copy_tree(DONOR / "Frameworks" / "LiveShim", OUTPUT / "Frameworks" / "LiveShim")
    live_shim = OUTPUT / "Frameworks" / "LiveShim"
    for header in live_shim.rglob("*.h"):
        flat_header = live_shim / header.name
        if header != flat_header and not flat_header.exists():
            shutil.copy2(header, flat_header)
    copy_tree(DONOR / "Frameworks" / "HWHook", OUTPUT / "Frameworks" / "HWHook")
    copy_tree(DONOR / "Frameworks" / "MobileDevelopmentKit", OUTPUT / "Frameworks" / "MobileDevelopmentKit")
    mdk = OUTPUT / "Frameworks" / "MobileDevelopmentKit"
    for header in mdk.rglob("*.h"):
        flat_header = mdk / header.name
        if header != flat_header and not flat_header.exists():
            shutil.copy2(header, flat_header)
    copy_tree(DONOR / "Shared", OUTPUT / "Shared")
    copy_tree(DONOR / "KEXTs", OUTPUT / "KEXTs")
    shutil.copy2(DONOR / "ksurface_config.h", OUTPUT / "ksurface_config.h")
    shutil.copy2(DONOR / "ksurface_abi.h", OUTPUT / "ksurface_abi.h")

    for source in OUTPUT.rglob("*"):
        if source.suffix not in {".h", ".m", ".mm", ".c", ".cpp", ".swift"}:
            continue
        data = source.read_text(errors="surrogateescape")
        data = data.replace("LiveProcess.appex", "NyxianProcess.appex")
        data = data.replace("<Nyxian-Swift.h>", '"FDNyxianUIAdapters.h"')
        data = data.replace("<UI/XCodeButton.h>", '"FDNyxianUIAdapters.h"')
        source.write_text(data, errors="surrogateescape")

    digest = hashlib.sha256()
    for source in sorted(p for p in OUTPUT.rglob("*") if p.is_file()):
        digest.update(str(source.relative_to(OUTPUT)).encode())
        digest.update(source.read_bytes())
    (OUTPUT / "SOURCE_SHA256").write_text(digest.hexdigest() + "\n")
    print(f"Prepared pinned Nyxian runtime: {digest.hexdigest()}")


if __name__ == "__main__":
    main()
