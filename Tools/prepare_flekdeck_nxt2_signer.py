#!/usr/bin/env python3
"""Prepare FlekDeck NXT2 signing source from pinned Nyxian.

Nyxian (c) 2025-2026 emexlab, AGPL-3.0-or-later.
The real EC NXT2 signing, CDHash and keychain algorithms remain upstream.
"""
import argparse
import subprocess
from pathlib import Path

PINNED = "350dd8dbeb796bc0ff5bc91ef770f1a2994432e7"
OLD_HASH = """    LCMachO *machO = LCMapMachOFromFDRO(dup(fd));
    if(machO == NULL)
    {
        return KERN_FAILURE;
    }
    uint8_t cdhash[USER_FSIGNATURES_CDHASH_LEN];
    if(!CDHashOfMachO(machO->map, machO->size, (uint8_t*)&cdhash))
    {
        LCUnmapMachO(machO);
        return KERN_FAILURE;
    }
    LCUnmapMachO(machO);"""
NEW_HASH = """    // Nyxian's own CDHashOfFD, not a guest dyld-hook Mach-O mapper.
    uint8_t cdhash[USER_FSIGNATURES_CDHASH_LEN];
    if(!CDHashOfFD(fd, cdhash))
    {
        return KERN_FAILURE;
    }"""
READY = """
// Prove the same persisted EC key Nyxian ksurface uses can be read.
// Secret key bytes must never be exported or added to diagnostics.
int FlekDeckNXT2SignerReady(void) {
    uint8_t *priv = NULL, *pub = NULL;
    size_t plen = 0, ulen = 0;
    if (!get_static_kernel_key(&priv, &plen, &pub, &ulen)) return 0;
    int valid = (priv && plen > 0 && pub && ulen > 0);
    if (priv) { OPENSSL_cleanse(priv, plen); free(priv); }
    if (pub) free(pub);
    return valid;
}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nyxian", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    root = a.nyxian.resolve()
    rev = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PINNED:
        raise SystemExit("Wrong pinned Nyxian revision: " + rev)
    original = (root / "Nyxian/LindChain/ProcEnvironment/Surface/"
                "trust/signing.c").read_text()
    split = "\n#if !defined(BOOT)\n"
    if original.count(split) != 1 or original.count(OLD_HASH) != 1:
        raise SystemExit("Unexpected upstream signer source")
    source = original.split(split, 1)[0].replace(OLD_HASH, NEW_HASH)
    old_includes = (
        "#include <LindChain/ProcEnvironment/Surface/surface.h>\n"
        "#include <LindChain/ProcEnvironment/LiveContainer/LCMachOUtils.h>\n"
    )
    if source.count(old_includes) != 1:
        raise SystemExit("Unexpected upstream signer includes")
    source = source.replace(
        old_includes, "#include <LindChain/ProcEnvironment/Surface/key.h>\n"
        "#include <unistd.h>\n#include <fcntl.h>\n"
    ) + READY
    assert "EVP_DigestSign" in source and "trust_nxt2_sign_fd" in source
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "FlekDeckNXT2Signer.c").write_text(source)
    (a.out / "PINNED-NYXIAN-AGPL.txt").write_text(
        "Nyxian pinned SHA: " + PINNED + "\n"
        "AGPL-3.0-or-later (c) 2025-2026 emexlab\n"
        "Original source: Nyxian/LindChain/ProcEnvironment/Surface/"
        "trust/signing.c, trust/cdhash.c, Surface/key.c\n"
        "Adaptations: Nyxian CDHashOfFD replaces the guest Mach-O utility;"
        " unrelated guest-only read/verification/root-CA code is omitted.\n")
    print("Prepared Nyxian NXT2 signer with EC key and native code hash")

if __name__ == "__main__":
    main()
