#!/usr/bin/env python3
"""Extract verified Procursus ZIP as regular IPA assets plus link metadata."""
import hashlib
import plistlib
import posixpath
import stat
import sys
import zipfile
from pathlib import Path

DIGEST = "8e213e8893cfc8a00f19783f9ae954a7ac6d3c36363df108dc9e6a8c75fcbf6c"

def main(zip_path: Path, destination: Path):
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != DIGEST:
        raise SystemExit("Procursus source ZIP digest mismatch")
    if destination.exists():
        raise SystemExit("Procursus output directory already exists")
    destination.mkdir(parents=True)
    symlinks, seen = {}, set()
    regular_files = 0
    total = 0
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None:
            raise SystemExit("Procursus ZIP has corrupt members")
        manifest = plistlib.loads(z.read("ROM/manifest.plist"))
        required = {"NXRomIdentifier": "org.emexlabs.procursus.jailed",
                    "NXRomExecutable": "System/Rom/init",
                    "NXRomVersion": "1.0"}
        if any(manifest.get(k) != v for k, v in required.items()):
            raise SystemExit("Unexpected Procursus ROM manifest")
        for required_file in ("ROM/System/Rom/init", "ROM/usr/libexec/bootstrapd",
                              "ROM/System/Library/CoreServices/SpringBoard.app/SpringBoard",
                              "ROM/bootstrap.tar.zst"):
            if required_file not in z.namelist():
                raise SystemExit("Missing ROM file: " + required_file)
        for member in z.infolist():
            if not member.filename.startswith("ROM/"):
                raise SystemExit("Unexpected ROM ZIP root")
            rel = member.filename[4:].rstrip("/")
            if not rel:
                continue
            if (rel in seen or rel.startswith("/") or "\\" in rel or
                any(p in ("", ".", "..") for p in rel.split("/"))):
                raise SystemExit("Unsafe ZIP path: " + rel)
            seen.add(rel)
            output = destination / "ROM" / rel
            if member.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = z.read(member).decode("utf-8")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
                if (not target or target.startswith("/") or "\\" in target or
                    resolved in (".", "..", "") or
                    resolved.startswith("../") or resolved.startswith("/")):
                    raise SystemExit("ROM symlink escapes root: " + rel)
                symlinks[rel] = target
            elif stat.S_ISREG(mode):
                total += member.file_size
                if total > 150_000_000:
                    raise SystemExit("ROM expanded file limit exceeded")
                output.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as source, output.open("wb") as sink:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        sink.write(chunk)
                output.chmod((mode & 0o777) or 0o644)
                regular_files += 1
            else:
                raise SystemExit("Unsupported ROM member type: " + rel)
    if len(symlinks) != 101 or regular_files != 40:
        raise SystemExit("Wrong Procursus ROM file/link count")
    (destination / "symlinks.plist").write_bytes(
        plistlib.dumps(symlinks, fmt=plistlib.FMT_XML))
    print("Expanded real Procursus ROM: 40 files, 101 symlink definitions, "
          + str(total) + " bytes. No nested ZIP.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_embedded_procursus.py ZIP OUTPUT")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
