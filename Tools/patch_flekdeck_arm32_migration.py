#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = path.read_text()
old = '''    if (needPatch) {
        bool has64bitSlice = false;
        bool has32bitSlice = false;
        bool isEncrypted = false;
        NSString *error = LCInspectMachOArchitectures(execPath.UTF8String, &has64bitSlice, &has32bitSlice, &isEncrypted);
        if(!error && !has64bitSlice && !has32bitSlice) {
            error = @"The app executable has no supported ARM slice.";
        }
        if(!error && has64bitSlice) {
            error = LCParseMachO(execPath.UTF8String, false, ^(const char *path, struct mach_header_64 *header, int fd, void* filePtr) {
                int patchResult = LCPatchExecSlice(path, header, ![self dontInjectTweakLoader]);
                if(patchResult & PATCH_EXEC_RESULT_NO_SPACE_FOR_TWEAKLOADER) {
                    info[@"LCTweakLoaderCantInject"] = @YES;
                    info[@"dontInjectTweakLoader"] = @YES;
                }
                if(patchResult & PATCH_EXEC_RESULT_SEG_COUNT_MISMATCH) {
                    info[@"segCountMismatch"] = @YES;
                }
            });
        }
        is32bit = !has64bitSlice && has32bitSlice;
#if is32BitSupported
        self.is32bit = is32bit;
#endif
        if (!is32bit) {
            LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
        } else {
#if is32BitSupported
            // LiveExec32 owns ARM32 execution. It requires JIT and SDK spoofing.
            self.isJITNeeded = YES;
            self.classicMode = YES;
            self.spoofSDKVersion = YES;
#endif
        }
        if (isEncrypted) {
            error = @"The app you tried to install is encrypted. Please provide decrypted app.";
        }
        if (error) {
            [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];
            completetionHandler(NO, error);
            return;
        }
        info[@"LCPatchRevision"] = @(currentPatchRev);
        forceSign = true;
        
        [self save];
    }'''
new = '''#if is32BitSupported
    bool needsArchitectureClassification = (info[@"is32bit"] == nil);
#else
    bool needsArchitectureClassification = false;
#endif
    if (needPatch || needsArchitectureClassification) {
        bool has64bitSlice = false;
        bool has32bitSlice = false;
        bool isEncrypted = false;
        NSString *error = LCInspectMachOArchitectures(execPath.UTF8String, &has64bitSlice, &has32bitSlice, &isEncrypted);
        if(!error && !has64bitSlice && !has32bitSlice) {
            error = @"The app executable has no supported ARM slice.";
        }

        is32bit = !has64bitSlice && has32bitSlice;
#if is32BitSupported
        self.is32bit = is32bit;
#endif

        // Only a genuinely outdated ARM64 executable goes through FlekDeck's
        // 64-bit mutation pipeline. Classification-only migration must never
        // rewrite an app whose patch revision is already current.
        if(!error && needPatch && has64bitSlice) {
            error = LCParseMachO(execPath.UTF8String, false, ^(const char *path, struct mach_header_64 *header, int fd, void* filePtr) {
                int patchResult = LCPatchExecSlice(path, header, ![self dontInjectTweakLoader]);
                if(patchResult & PATCH_EXEC_RESULT_NO_SPACE_FOR_TWEAKLOADER) {
                    info[@"LCTweakLoaderCantInject"] = @YES;
                    info[@"dontInjectTweakLoader"] = @YES;
                }
                if(patchResult & PATCH_EXEC_RESULT_SEG_COUNT_MISMATCH) {
                    info[@"segCountMismatch"] = @YES;
                }
            });
            if(!error) {
                LCPatchAppBundleFixupARM64eSlice([NSURL fileURLWithPath:appPath]);
            }
        }

#if is32BitSupported
        if(is32bit) {
            // Existing ARM32 imports get the same runtime contract as fresh ones.
            self.isJITNeeded = YES;
            self.classicMode = YES;
            self.spoofSDKVersion = YES;
        }
#endif
        if (isEncrypted) {
            error = @"The app you tried to install is encrypted. Please provide decrypted app.";
        }
        if (error) {
            [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];
            completetionHandler(NO, error);
            return;
        }
        if(needPatch) {
            info[@"LCPatchRevision"] = @(currentPatchRev);
            forceSign = true;
        }
        [self save];
    }'''

if new not in text:
    if old not in text:
        raise SystemExit(f"{path}: post-Mach-O ARM32 migration anchor missing")
    text = text.replace(old, new, 1)
path.write_text(text)

value = path.read_text()
for needle in (
    'needsArchitectureClassification = (info[@"is32bit"] == nil)',
    'if (needPatch || needsArchitectureClassification)',
    'if(!error && needPatch && has64bitSlice)',
    'if(is32bit)',
):
    if needle not in value:
        raise SystemExit(f"{path}: missing ARM32 migration marker: {needle}")

print("FlekDeck existing app architecture state migrates without re-patching current ARM64 apps")
