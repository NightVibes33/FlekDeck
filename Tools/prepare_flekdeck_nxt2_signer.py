#!/usr/bin/env python3
"""Prepare complete host-usable Nyxian NXT2 trust modules from pinned source.

Full signing/read/verify, RootCA, CDHash, persistent EC keychain, and vendor
key matching are retained. Only references to the *guest kernel instance*
are adapted for pre-boot host execution. The guest's process/kernel trust.m
remains in the genuine System/Rom/init, rather than running before boot.

Nyxian AGPL-3.0-or-later (c) 2025-2026 emexlab.
"""
from pathlib import Path
import argparse
import subprocess

PINNED = "350dd8dbeb796bc0ff5bc91ef770f1a2994432e7"

SIGN_HASH_OLD = """    LCMachO *machO = LCMapMachOFromFDRO(dup(fd));
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
SIGN_HASH_NEW = """    // Use Nyxian's original CDHashOfFD rather than loading guest dyld hooks.
    uint8_t cdhash[USER_FSIGNATURES_CDHASH_LEN];
    if(!CDHashOfFD(fd, cdhash))
    {
        return KERN_FAILURE;
    }"""
READ_HASH_OLD = """    LCMachO *machO = LCMapMachOFromFDRO(dup(fd));
    if(machO != NULL)
    {
        uint8_t cdhash[USER_FSIGNATURES_CDHASH_LEN];
        if(CDHashOfMachO(machO->map, machO->size, (uint8_t*)&cdhash))
        {
            if(memcmp(cdhash, result->cdhash, USER_FSIGNATURES_CDHASH_LEN) == 0)
            {
                result->isCdHashValid = true;
            }
        }
        LCUnmapMachO(machO);
    }"""
READ_HASH_NEW = """    uint8_t cdhash[USER_FSIGNATURES_CDHASH_LEN];
    if(CDHashOfFD(fd, cdhash) &&
       memcmp(cdhash, result->cdhash, USER_FSIGNATURES_CDHASH_LEN) == 0)
    {
        result->isCdHashValid = true;
    }"""
SURFACE_PUBLIC_OLD = """        const uint8_t *p = ksurface->pub_key;
        EVP_PKEY *pub = d2i_PUBKEY(NULL, &p, ksurface->pub_key_len);"""
SURFACE_PUBLIC_NEW = """        // The guest's ksurface global is not initialized until ROM boot.
        // Get the SAME persistent Nyxian EC public key directly from Keychain.
        uint8_t *hostPublicKey = NULL;
        size_t hostPublicKeyLength = 0;
        if(!get_static_kernel_key(NULL, NULL, &hostPublicKey, &hostPublicKeyLength))
        {
            goto signature_invalid;
        }
        const uint8_t *p = hostPublicKey;
        EVP_PKEY *pub = d2i_PUBKEY(NULL, &p, (long)hostPublicKeyLength);
        free(hostPublicKey);"""
READY = """
// Confirms usable Nyxian signing and RootCA state without leaking key data.
int FlekDeckNXT2SignerReady(void) {
    uint8_t *priv = NULL, *pub = NULL;
    size_t plen = 0, ulen = 0;
    if (!get_static_kernel_key(&priv, &plen, &pub, &ulen)) return 0;
    int valid = (priv && plen > 0 && pub && ulen > 0);
    if (priv) { OPENSSL_cleanse(priv, plen); free(priv); }
    if (pub) free(pub);
    if (!valid) return 0;
    return ksurface_keychain_update() == KERN_SUCCESS ? 1 : 0;
}

// Do not report a signed guest file until Nyxian's own read, CDHash and
// EC signature verification all succeed with the shared device key.
int FlekDeckNXT2VerifySignedPath(const char *path) {
    if (!path) return 0;
    ksurface_nxt2_t result;
    kern_return_t code = trust_nxt2_read(path, &result);
    if (code != KERN_SUCCESS) return 0;
    int valid = result.isValid && result.isSigned && result.isCdHashValid;
    if (result.entitlements) CFRelease(result.entitlements);
    return valid ? 1 : 0;
}
"""

def once(source, old, new, desc):
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"Pinned Nyxian {desc} changed: {count} matches")
    return source.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nyxian", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    root = args.nyxian.resolve()
    rev = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PINNED:
        raise SystemExit("Wrong Nyxian source revision: " + rev)
    directory = root / "Nyxian/LindChain/ProcEnvironment/Surface"
    signer = (directory / "trust/signing.c").read_text()
    signer = once(signer, SIGN_HASH_OLD, SIGN_HASH_NEW, "sign CDHash")
    signer = once(signer, READ_HASH_OLD, READ_HASH_NEW, "verify CDHash")
    signer = once(signer, SURFACE_PUBLIC_OLD, SURFACE_PUBLIC_NEW, "public key")
    signer = once(
        signer,
        "#include <LindChain/ProcEnvironment/Surface/surface.h>\n"
        "#include <LindChain/ProcEnvironment/LiveContainer/LCMachOUtils.h>\n",
        "#include <LindChain/ProcEnvironment/Surface/key.h>\n"
        "#include <sys/param.h>\n#include <unistd.h>\n#include <fcntl.h>\n",
        "guest-only Mach-O imports"
    ) + READY
    if ("trust_nxt2_public_key_read" not in signer or
            "trust_nxt2_generate_rootca_keypair" not in signer or
            "trust_nxt2_read_fd" not in signer):
        raise SystemExit("Full Nyxian NXT2 verifier/RootCA APIs missing")

    keychain = (directory / "trust/keychain.m").read_text()
    keychain = once(
        keychain, "#import <LindChain/IDEFoundation/NXBootstrap.h>\n",
        "#import <LindChain/ProcEnvironment/Surface/key.h>\n",
        "host keychain header"
    )
    keychain = once(
        keychain, "#include <LindChain/ProcEnvironment/Surface/surface.h>\n",
        "", "guest surface header"
    )
    keychain = once(
        keychain,
        "    nxt2_vendor_key_t ksurface_vendor;",
        """    // Same device-local Nyxian key; the guest's ksurface is not booted.
    uint8_t *hostPublicKey = NULL;
    size_t hostPublicKeyLength = 0;
    if (!get_static_kernel_key(NULL, NULL,
                               &hostPublicKey, &hostPublicKeyLength)) {
        os_unfair_lock_unlock(&g_keychain_lock);
        return KERN_FAILURE;
    }
    nxt2_vendor_key_t ksurface_vendor;""",
        "guest public key initialization"
    )
    keychain = once(
        keychain,
        "        os_unfair_lock_unlock(&g_keychain_lock);\n"
        "        return KERN_RESOURCE_SHORTAGE;\n"
        "    }\n"
        "    ksurface_vendor.public_key = malloc(ksurface->pub_key_len);",
        "        free(hostPublicKey);\n"
        "        os_unfair_lock_unlock(&g_keychain_lock);\n"
        "        return KERN_RESOURCE_SHORTAGE;\n"
        "    }\n"
        "    ksurface_vendor.public_key = malloc(hostPublicKeyLength);",
        "vendor allocation"
    )
    keychain = once(
        keychain,
        "    if(ksurface_vendor.public_key == NULL)\n"
        "    {\n"
        "        os_unfair_lock_unlock(&g_keychain_lock);\n",
        "    if(ksurface_vendor.public_key == NULL)\n"
        "    {\n"
        "        free(ksurface_vendor.vendor_name);\n"
        "        free(hostPublicKey);\n"
        "        os_unfair_lock_unlock(&g_keychain_lock);\n",
        "vendor allocation failure"
    )
    keychain = once(
        keychain,
        "    ksurface_vendor.public_key_len = ksurface->pub_key_len;\n"
        "    memcpy(ksurface_vendor.public_key, ksurface->pub_key, ksurface->pub_key_len);",
        "    ksurface_vendor.public_key_len = hostPublicKeyLength;\n"
        "    memcpy(ksurface_vendor.public_key, hostPublicKey, hostPublicKeyLength);\n"
        "    free(hostPublicKey);",
        "public key copy"
    )
    keychain = once(
        keychain,
        '    NSArray<NSURL*> *rootCAs = [[NSFileManager defaultManager] '
        'contentsOfDirectoryAtURL:[NXBootstrap.shared.rootURL '
        'URLByAppendingPathComponent:@"RootCAs"] '
        'includingPropertiesForKeys:@[] options:0 error:nil];',
        '    NSURL *userSupport = [[NSFileManager defaultManager] '
        'URLsForDirectory:NSApplicationSupportDirectory '
        'inDomains:NSUserDomainMask].firstObject;\n'
        '    NSURL *rootCAFolder = [userSupport '
        'URLByAppendingPathComponent:@"FlekDeck/Boot/RootCAs" isDirectory:YES];\n'
        '    NSArray<NSURL*> *rootCAs = [[NSFileManager defaultManager] '
        'contentsOfDirectoryAtURL:rootCAFolder '
        'includingPropertiesForKeys:@[] options:0 error:nil];',
        "host RootCA location"
    )
    if "NXBootstrap" in keychain or "ksurface->" in keychain:
        raise SystemExit("Unsafe guest-only keychain dependencies remain")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "FlekDeckNXT2Signer.c").write_text(signer)
    (args.out / "FlekDeckNXT2Keychain.m").write_text(keychain)
    (args.out / "PINNED-NYXIAN-AGPL.txt").write_text(
        "Full Nyxian host-relevant trust modules: signing, signature reading,"
        " CDHash, EC keychain, RootCA generation/reading, and vendor matching.\n"
        "Original source: emexlab/Nyxian@" + PINNED + "\n"
        "License: AGPL-3.0-or-later (c) 2025-2026 emexlab.\n"
        "Source files: Surface/trust/{signing.c,cdhash.c,keychain.m};"
        " Surface/key.c.\n"
        "Host-only adaptation: resolve persistent public key without guest"
        " kernel startup; use Nyxian CDHashOfFD; load RootCAs in"
        " Application Support/FlekDeck/Boot/RootCAs.\n")
    print("Prepared complete Nyxian host NXT2 trust signer and verifier")


if __name__ == "__main__":
    main()
