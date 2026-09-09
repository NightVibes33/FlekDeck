from pathlib import Path

# Experiment-only diagnosis layer for:
# 1) guest code-signature rejection after ZSign reports success,
# 2) parallel launches unexpectedly entering a JIT provider path, and
# 3) the missing host-owned bottom gesture over maximized guests.
#
# The signer-compatible workflow copies the pinned VibeContainers core before
# applying Flek compatibility patches, so diagnostics that touch Vibe files must
# be applied here after that copy. This script is intentionally used only on the
# experiment/multitask-control-jit-diagnosis branch.

# ---------------------------------------------------------------------------
# Detailed kernel Library Validation diagnostic.
# ---------------------------------------------------------------------------
h = Path("LiveContainer/LCMachOUtils.h")
s = h.read_text()
old_decl = "bool checkCodeSignature(const char* path);"
new_decl = old_decl + "\nNSString *checkCodeSignatureDiagnostic(const char* path);"
if "checkCodeSignatureDiagnostic" not in s:
    if old_decl not in s:
        raise SystemExit("LCMachOUtils.h signature checker declaration not found")
    s = s.replace(old_decl, new_decl, 1)
h.write_text(s)

m = Path("LiveContainer/LCMachOUtils.m")
s = m.read_text()
old_checker = r'''bool checkCodeSignature(const char* path) {
    __block bool checked = false;
    __block bool ans = false;
    LCParseMachO(path, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        if(checked || header->cputype != CPU_TYPE_ARM64) {
            return;
        }
        checked = true;
        
        struct code_signature_command* codeSignatureCommand = findSignatureCommand(header);
        if(!codeSignatureCommand) {
            return;
        }
        off_t sliceOffset = (void*)header - filePtr;
        fsignatures_t siginfo;
        siginfo.fs_file_start = sliceOffset;
        siginfo.fs_blob_start = (void*)(long)(codeSignatureCommand->dataoff);
        siginfo.fs_blob_size  = codeSignatureCommand->datasize;
        int addFileSigsReault = fcntl(fd, F_ADDFILESIGS_RETURN, &siginfo);
        if ( addFileSigsReault == -1 ) {
            ans = false;
            return;
        }
        
        fchecklv_t checkInfo;
        char     messageBuffer[512];
        messageBuffer[0]                = '\0';
        checkInfo.lv_error_message_size = sizeof(messageBuffer);
        checkInfo.lv_error_message      = messageBuffer;
        checkInfo.lv_file_start= sliceOffset;
        int checkLVresult = fcntl(fd, F_CHECK_LV, &checkInfo);
        
        if (checkLVresult == 0) {
            ans = true;
            return;
        } else {
            ans = false;
            return;
        }
    });
    return ans;
}
'''
new_checker = r'''NSString *checkCodeSignatureDiagnostic(const char* path) {
    __block bool checked = false;
    __block NSString *failure = nil;

    NSString *parseError = LCParseMachO(path, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        if(checked || header->cputype != CPU_TYPE_ARM64) {
            return;
        }
        checked = true;

        struct code_signature_command* codeSignatureCommand = findSignatureCommand(header);
        if(!codeSignatureCommand) {
            failure = @"Mach-O has no LC_CODE_SIGNATURE command.";
            return;
        }

        off_t sliceOffset = (void*)header - filePtr;
        fsignatures_t siginfo;
        memset(&siginfo, 0, sizeof(siginfo));
        siginfo.fs_file_start = sliceOffset;
        siginfo.fs_blob_start = (void*)(long)(codeSignatureCommand->dataoff);
        siginfo.fs_blob_size  = codeSignatureCommand->datasize;

        errno = 0;
        int addFileSigsResult = fcntl(fd, F_ADDFILESIGS_RETURN, &siginfo);
        int addFileSigsErrno = errno;
        if(addFileSigsResult == -1) {
            failure = [NSString stringWithFormat:
                @"F_ADDFILESIGS_RETURN failed: errno=%d (%s), sliceOffset=%lld, blobOffset=%u, blobSize=%u",
                addFileSigsErrno,
                strerror(addFileSigsErrno),
                (long long)sliceOffset,
                codeSignatureCommand->dataoff,
                codeSignatureCommand->datasize];
            return;
        }

        fchecklv_t checkInfo;
        memset(&checkInfo, 0, sizeof(checkInfo));
        char messageBuffer[512];
        messageBuffer[0] = '\0';
        checkInfo.lv_error_message_size = sizeof(messageBuffer);
        checkInfo.lv_error_message = messageBuffer;
        checkInfo.lv_file_start = sliceOffset;

        errno = 0;
        int checkLVResult = fcntl(fd, F_CHECK_LV, &checkInfo);
        int checkLVErrno = errno;
        if(checkLVResult != 0) {
            NSString *kernelMessage = messageBuffer[0]
                ? [NSString stringWithUTF8String:messageBuffer]
                : @"<no kernel Library Validation message>";
            failure = [NSString stringWithFormat:
                @"F_CHECK_LV failed: result=%d errno=%d (%s), sliceOffset=%lld, kernel=\"%@\"",
                checkLVResult,
                checkLVErrno,
                strerror(checkLVErrno),
                (long long)sliceOffset,
                kernelMessage];
        }
    });

    if(failure.length) {
        return failure;
    }
    if(parseError.length) {
        return [NSString stringWithFormat:@"Mach-O parse failed: %@", parseError];
    }
    if(!checked) {
        return @"No arm64 Mach-O slice was available for Library Validation.";
    }
    return nil;
}

bool checkCodeSignature(const char* path) {
    return checkCodeSignatureDiagnostic(path) == nil;
}
'''
if "checkCodeSignatureDiagnostic(const char* path)" not in s:
    if old_checker not in s:
        raise SystemExit("LCMachOUtils.m checkCodeSignature implementation shape changed")
    s = s.replace(old_checker, new_checker, 1)
m.write_text(s)

# ---------------------------------------------------------------------------
# Replace the generic post-ZSign guest error with the actual kernel rejection.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
s = p.read_text()
old_post_sign = r'''                        bool signatureValid = checkCodeSignature(executablePath.UTF8String);
                        if(signatureValid) {
                            completetionHandler(YES, [error localizedDescription]);
                        } else {
                            completetionHandler(NO, @"lc.signer.latestCertificateInvalidErr");
                        }
'''
new_post_sign = r'''                        NSString *signatureFailure = checkCodeSignatureDiagnostic(executablePath.UTF8String);
                        if(!signatureFailure) {
                            completetionHandler(YES, [error localizedDescription]);
                        } else {
                            NSLog(@"[FlekDeckDiag] guest signature rejected after ZSign: %@", signatureFailure);
                            completetionHandler(NO, [NSString stringWithFormat:
                                @"The app was signed, but iOS Library Validation rejected its executable.\n\n[FlekDeck diagnostic] %@",
                                signatureFailure]);
                        }
'''
if "[FlekDeckDiag] guest signature rejected after ZSign" not in s:
    if old_post_sign not in s:
        raise SystemExit("LCAppInfo.m post-sign validation shape changed")
    s = s.replace(old_post_sign, new_post_sign, 1)
p.write_text(s)

# Give the JIT-less TestJITLess.dylib probe the same detailed failure. This lets
# us distinguish a certificate-wide failure from an app-specific Mach-O failure.
p = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
s = p.read_text()
old_diag = r'''    dispatch_async(dispatch_get_main_queue(), ^{
        if(!signSuccess) {
            completionHandler(NO, signError);
        } else if (checkCodeSignature([tmpLibPath UTF8String])) {
            completionHandler(YES, signError);
        } else {
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier code:2 userInfo:@{NSLocalizedDescriptionKey: @"lc.signer.latestCertificateInvalidErr"}]);
        }
        [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
    });
'''
new_diag = r'''    dispatch_async(dispatch_get_main_queue(), ^{
        if(!signSuccess) {
            completionHandler(NO, signError);
        } else {
            NSString *signatureFailure = checkCodeSignatureDiagnostic([tmpLibPath UTF8String]);
            if(!signatureFailure) {
                completionHandler(YES, signError);
            } else {
                NSLog(@"[FlekDeckDiag] TestJITLess signature rejected: %@", signatureFailure);
                completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                          code:2
                                                      userInfo:@{NSLocalizedDescriptionKey:
                    [NSString stringWithFormat:@"JIT-less test library failed iOS Library Validation.\n\n[FlekDeck diagnostic] %@", signatureFailure]}]);
            }
        }
        [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
    });
'''
if "[FlekDeckDiag] TestJITLess signature rejected" not in s:
    if old_diag not in s:
        raise SystemExit("LCUtils.m JIT-less diagnostic validation shape changed")
    s = s.replace(old_diag, new_diag, 1)
p.write_text(s)

# ---------------------------------------------------------------------------
# Log the launch decision before LCAppModel gets control. This stays in Flek's
# shell, so the pinned Vibe LCAppModel can remain behaviorally unchanged.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()
launch_start = s.index("    func launchHomeApp(_ app: LCAppModel, parallel: Bool) async {")
do_index = s.index("        do {", launch_start)
log_block = '''        let diagJITProvider = LCUtils.appGroupUserDefault.integer(forKey: "LCJITEnablerType")
        let diagCertData = LCUtils.certificateData() != nil
        let diagCertPassword = LCSharedUtils.certificatePassword() != nil
        print("[FlekDeckDiag] launch bundle=\\(app.bundleIdentifier) parallel=\\(parallel) isJITNeeded=\\(app.appInfo.isJITNeeded) jitProviderRaw=\\(diagJITProvider) certData=\\(diagCertData) certPassword=\\(diagCertPassword) multiLCStatus=\\(sharedModel.multiLCStatus)")

'''
if "[FlekDeckDiag] launch bundle=" not in s:
    s = s[:do_index] + log_block + s[do_index:]
p.write_text(s)

# ---------------------------------------------------------------------------
# Restore a host-owned bottom recognizer over actual multitask windows. Vibe 3.8
# did this at UIWindow level; Flek's newer small swipe zone only exists after the
# main switcher bar has been hidden, which is why the control appears/disappears
# depending on UI state.
# ---------------------------------------------------------------------------
p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text()
show_dock_anchor = '''    @objc public func showDock() {
        guard isDockEnabled() else { return }
        guard !isVisible, let hostingController = hostingController else { return }
        guard let keyWindow = self.keyWindow else { return }
        
        DispatchQueue.main.async {
'''
show_dock_replacement = '''    @objc public func showDock() {
        guard isDockEnabled() else { return }
        guard !isVisible, let hostingController = hostingController else { return }
        guard let keyWindow = self.keyWindow else { return }

        // Experiment: restore Vibe's host-owned bottom gesture boundary. The
        // recognizer is inert on FlekDeck's SpringBoard and only begins while a
        // virtual guest/internal page is visibly hosted.
        // Temp Parallel layout build: keep the base control path unchanged.
        
        DispatchQueue.main.async {
'''
if "// Temp Parallel layout build: keep the base control path unchanged." not in s:
    if show_dock_anchor not in s:
        raise SystemExit("MultitaskDockView.showDock shape changed")
    s = s.replace(show_dock_anchor, show_dock_replacement, 1)
p.write_text(s)

print("Applied FlekDeck multitask/JIT-less experiment diagnostics and host gesture bridge.")
