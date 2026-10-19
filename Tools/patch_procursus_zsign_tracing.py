#!/usr/bin/env python3
"""Instrument the pinned Vibe ZSigner worker ONLY for Procursus ROM crash diagnosis.

Run after the exact upstream Vibe parity check, before Xcode compiles ZSign.
No signing inputs, certificate material, algorithms or concurrency are modified.
Every diagnostic is appended and fsynced to Documents/BootLogs/current-boot.log.
"""
from pathlib import Path
import sys


def replace_one(content: str, before: str, after: str, label: str) -> str:
    matches = content.count(before)
    if matches != 1:
        raise SystemExit(f"ZSign diagnostic patch {label}: expected one anchor, got {matches}")
    return content.replace(before, after, 1)


def patch(path: Path) -> None:
    src = path.read_text()
    if "flekdeck_zsign_trace(" in src:
        raise SystemExit("ZSign diagnostics already patched; not reapplying")
    src = replace_one(src, '#include "zsigner.h"',
                       '#include "zsigner.h"\n'
                       '#include <fcntl.h>\n#include <unistd.h>\n'
                       '#include <time.h>\n#include <stdio.h>\n#include <limits.h>\n',
                       "includes")
    helper = r'''
// Logs are limited to the FlekDeck ROM staging slot. No user IPA signing
// or certificate material is logged. O_APPEND + fsync preserve breadcrumbs
// when a concurrent native C++ worker terminates the host process.
static void flekdeck_zsign_trace(const char *stage, NSString *path) {
    if (!stage || ![path isKindOfClass:NSString.class] ||
        [path rangeOfString:@"/FlekDeck/Boot/Slot/"].location == NSNotFound) return;
    const char *home = getenv("HOME");
    if (!home) return;
    char filename[PATH_MAX];
    if (snprintf(filename, sizeof(filename),
                 "%s/Documents/BootLogs/current-boot.log", home) >= sizeof(filename)) return;
    const char *raw = path.fileSystemRepresentation;
    const char *marker = strstr(raw, "/.A.installing/");
    const char *relative = marker ? marker + strlen("/.A.installing/") : path.lastPathComponent.UTF8String;
    struct timespec ts = {0};
    clock_gettime(CLOCK_REALTIME, &ts);
    char line[768];
    int count = snprintf(line, sizeof(line),
        "epoch=%lld.%03ld pid=%d zsign-worker-%s file=%.*s\n",
        (long long)ts.tv_sec, ts.tv_nsec / 1000000, getpid(),
        stage, 340, relative ?: "");
    if (count <= 0 || count >= sizeof(line)) return;
    int fd = open(filename, O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0) return;
    (void)write(fd, line, (size_t)count);
    (void)fsync(fd);
    close(fd);
}

'''
    src = replace_one(src,
                      '// copy, remove and rename back the file to prevent crash due to kernel signature cache',
                      helper + '// copy, remove and rename back the file to prevent crash due to kernel signature cache',
                      "logging helper")
    # Trace the destructive refresh operation separately: a crash while the
    # signer is refreshing a vnode must be distinguishable from Mach-O Sign().
    src = replace_one(src,
        'void refreshFile(NSString* path) {\n',
        'void refreshFile(NSString* path) {\n'
        '    flekdeck_zsign_trace("refresh-begin", path);\n',
        "refresh begin")
    src = replace_one(src,
        '    [NSFileManager.defaultManager moveItemAtPath:newPath toPath:path error:&error];\n}',
        '    [NSFileManager.defaultManager moveItemAtPath:newPath toPath:path error:&error];\n'
        '    flekdeck_zsign_trace(error ? "refresh-file-error" : "refresh-end", path);\n}',
        "refresh end")
    src = replace_one(src,
        '    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{\n'
        '        ZSignAsset* pSignAsset = new ZSignAsset();',
        '    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{\n'
        '        flekdeck_zsign_trace("worker-enter", machoPathArr.firstObject);\n'
        '        ZSignAsset* pSignAsset = new ZSignAsset();',
        "worker entry")
    src = replace_one(src,
        '        bool ret = pSignAsset->InitSimple(strPKeyFileData, (int)[key length],',
        '        flekdeck_zsign_trace("certificate-init-enter", machoPathArr.firstObject);\n'
        '        bool ret = pSignAsset->InitSimple(strPKeyFileData, (int)[key length],',
        "certificate enter")
    src = replace_one(src,
        '        if (!ret) {\n            delete pSignAsset;\n            NSError* initError',
        '        flekdeck_zsign_trace(ret ? "certificate-init-ok" : "certificate-init-failed",\n'
        '                              machoPathArr.firstObject);\n'
        '        if (!ret) {\n            delete pSignAsset;\n            NSError* initError',
        "certificate result")
    src = replace_one(src,
        '        for (NSString* machoPath in machoPathArr) {\n'
        '            dispatch_group_async(group, concurrentQueue, ^{\n'
        '                ZMachO* macho = new ZMachO();',
        '        for (NSString* machoPath in machoPathArr) {\n'
        '            dispatch_group_async(group, concurrentQueue, ^{\n'
        '                flekdeck_zsign_trace("file-dispatched", machoPath);\n'
        '                ZMachO* macho = new ZMachO();',
        "file dispatch")
    src = replace_one(src,
        '                refreshFile(machoPath);\n'
        '                if (!macho->Init(machoPath.UTF8String)) {',
        '                refreshFile(machoPath);\n'
        '                flekdeck_zsign_trace("macho-init-enter", machoPath);\n'
        '                if (!macho->Init(machoPath.UTF8String)) {\n'
        '                    flekdeck_zsign_trace("macho-init-failed", machoPath);',
        "Mach-O init")
    src = replace_one(src,
        '                } else {\n'
        '                    bool bRet = macho->Sign(pSignAsset, true, strBundleId,',
        '                } else {\n'
        '                    flekdeck_zsign_trace("macho-sign-enter", machoPath);\n'
        '                    bool bRet = macho->Sign(pSignAsset, true, strBundleId,',
        "Mach-O sign enter")
    src = replace_one(src,
        '                    if (!bRet) {\n'
        '                        errorMsg = [NSString stringWithFormat:@"Failed to Sign %@", machoPath];',
        '                    flekdeck_zsign_trace(bRet ? "macho-sign-ok" : "macho-sign-failed", machoPath);\n'
        '                    if (!bRet) {\n'
        '                        errorMsg = [NSString stringWithFormat:@"Failed to Sign %@", machoPath];',
        "Mach-O sign result")
    src = replace_one(src,
        '                delete macho;\n\n'
        '                // Serialize errorList mutation',
        '                delete macho;\n'
        '                flekdeck_zsign_trace("file-finished", machoPath);\n\n'
        '                // Serialize errorList mutation',
        "file finish")
    src = replace_one(src,
        '        dispatch_group_wait(group, DISPATCH_TIME_FOREVER);\n\n'
        '        delete pSignAsset;',
        '        flekdeck_zsign_trace("group-wait-enter", machoPathArr.firstObject);\n'
        '        dispatch_group_wait(group, DISPATCH_TIME_FOREVER);\n'
        '        flekdeck_zsign_trace("group-wait-done", machoPathArr.firstObject);\n\n'
        '        delete pSignAsset;',
        "group wait")
    path.write_text(src)
    print("Inserted fsync-backed Procursus-specific ZSign native-worker diagnostics")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_procursus_zsign_tracing.py ZSign/zsign.mm")
    patch(Path(sys.argv[1]))
