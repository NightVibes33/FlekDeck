#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainer/LCBootstrap.m")
text = path.read_text()

old_guest = '''    // Overwrite @executable_path
    const char *appExecPath = appBundle.executablePath.fileSystemRepresentation;
    NSString *emulatorLauncherPath = nil;
    NSString *emulatorEntrySymbol = nil;
    int (*emulatorMain)(int, char **, char **) = NULL;
    *path = appExecPath;
    overwriteExecPath(appExecPath);'''
new_guest = '''    // Overwrite @executable_path. Validate the guest executable before touching
    // dyld process state; a malformed bundle must become a real error, not a NULL
    // path passed into the private executable-path rewrite.
    NSString *guestExecutablePath = appBundle.executablePath;
    if(guestExecutablePath.length == 0) {
        return @"App's executable path was not found. The bundle is malformed or incomplete.";
    }
    const char *appExecPath = guestExecutablePath.fileSystemRepresentation;
    if(!appExecPath || !appExecPath[0]) {
        return @"App's executable path could not be represented for launch.";
    }
    NSString *emulatorLauncherPath = nil;
    NSString *emulatorEntrySymbol = nil;
    int (*emulatorMain)(int, char **, char **) = NULL;
    *path = appExecPath;
    overwriteExecPath(appExecPath);'''
if new_guest not in text:
    if old_guest not in text:
        raise SystemExit(f"{path}: guest executable rewrite anchor missing")
    text = text.replace(old_guest, new_guest, 1)

old_runtime = '''        emulatorLauncherPath = selected32bitLayerBundle.executablePath;
        NSString *emulatorLoadPath = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorLoadPath"];
        emulatorEntrySymbol = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorEntrySymbol"];
        if(emulatorLoadPath.length > 0 && emulatorEntrySymbol.length > 0) {
            NSString *resolvedLoadPath = [selected32bitLayerBundle.bundlePath stringByAppendingPathComponent:emulatorLoadPath];
            if(![fm fileExistsAtPath:resolvedLoadPath]) {
                appError = [NSString stringWithFormat:@"32-bit runtime load image is missing: %@", resolvedLoadPath];
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            appExecPath = strdup(resolvedLoadPath.fileSystemRepresentation);
            overwriteExecPath(emulatorLauncherPath.fileSystemRepresentation);
        } else {
            // Compatibility fallback for older LiveExec32 bundles.
            appExecPath = strdup(selected32bitLayerBundle.executablePath.fileSystemRepresentation);
            overwriteExecPath(appExecPath);
        }'''
new_runtime = '''        emulatorLauncherPath = selected32bitLayerBundle.executablePath;
        NSString *emulatorLoadPath = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorLoadPath"];
        emulatorEntrySymbol = selected32bitLayerBundle.infoDictionary[@"LC32BitEmulatorEntrySymbol"];

        BOOL hasLoadPath = emulatorLoadPath.length > 0;
        BOOL hasEntrySymbol = emulatorEntrySymbol.length > 0;
        if(hasLoadPath != hasEntrySymbol) {
            appError = @"The selected 32-bit runtime has incomplete loader metadata (load path and entry symbol must both be present).";
            NSLog(@"[LCBootstrap] %@", appError);
            *path = oldPath;
            return appError;
        }

        if(hasLoadPath && hasEntrySymbol) {
            if(emulatorLauncherPath.length == 0 || ![fm isExecutableFileAtPath:emulatorLauncherPath]) {
                appError = @"The selected 32-bit runtime launcher executable is missing or not executable.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            NSString *resolvedLoadPath = [selected32bitLayerBundle.bundlePath stringByAppendingPathComponent:emulatorLoadPath];
            BOOL loadImageIsDirectory = NO;
            if(![fm fileExistsAtPath:resolvedLoadPath isDirectory:&loadImageIsDirectory] || loadImageIsDirectory) {
                appError = [NSString stringWithFormat:@"32-bit runtime load image is missing or invalid: %@", resolvedLoadPath];
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            const char *loadImagePath = resolvedLoadPath.fileSystemRepresentation;
            const char *launcherPath = emulatorLauncherPath.fileSystemRepresentation;
            if(!loadImagePath || !launcherPath) {
                appError = @"The selected 32-bit runtime paths could not be represented for launch.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            char *ownedLoadImagePath = strdup(loadImagePath);
            if(!ownedLoadImagePath) {
                appError = @"Unable to allocate the 32-bit runtime load path.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            appExecPath = ownedLoadImagePath;
            overwriteExecPath(launcherPath);
        } else {
            // Compatibility fallback for older translation-layer bundles. A legacy
            // runtime still has to contain a real executable before it can be used.
            if(emulatorLauncherPath.length == 0 || ![fm isExecutableFileAtPath:emulatorLauncherPath]) {
                appError = @"The selected legacy 32-bit runtime executable is missing or not executable.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            const char *legacyPath = emulatorLauncherPath.fileSystemRepresentation;
            if(!legacyPath) {
                appError = @"The selected legacy 32-bit runtime path could not be represented for launch.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            char *ownedLegacyPath = strdup(legacyPath);
            if(!ownedLegacyPath) {
                appError = @"Unable to allocate the legacy 32-bit runtime path.";
                NSLog(@"[LCBootstrap] %@", appError);
                *path = oldPath;
                return appError;
            }
            appExecPath = ownedLegacyPath;
            overwriteExecPath(appExecPath);
        }'''
if new_runtime not in text:
    if old_runtime not in text:
        raise SystemExit(f"{path}: ARM32 runtime loader anchor missing")
    text = text.replace(old_runtime, new_runtime, 1)

path.write_text(text)

value = path.read_text()
for needle in (
    "guestExecutablePath.length == 0",
    "hasLoadPath != hasEntrySymbol",
    "runtime launcher executable is missing or not executable",
    "runtime load image is missing or invalid",
    "Unable to allocate the 32-bit runtime load path",
):
    if needle not in value:
        raise SystemExit(f"{path}: missing loader hardening marker: {needle}")

print("FlekDeck guest/LiveExec32 loader now fails closed with real diagnostics")
