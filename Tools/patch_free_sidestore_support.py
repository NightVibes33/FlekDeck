from pathlib import Path
import plistlib

# Keep FlekDeck's SideStore integration rebrand-aware without changing the
# LiveContainer/VibeContainers JIT-less execution semantics.
p = Path("SideStoreSupport/SideStoreHooks.m")
s = p.read_text()
s = s.replace(
    '+ (NSString*)hook_appbundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_appbundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    'https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json',
    'https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json'
)
if 'com.fs.flekdeck' not in s or 'flekdeck-side-source.json' not in s:
    raise SystemExit("SideStore rebrand patch did not apply")
p.write_text(s)

# Keep get-task-allow informational. The real signed-library probe and guest
# launch are the source of truth for this experiment.
tab_path = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
tab = tab_path.read_text()
old_check = '''    func checkGetTaskAllow() {\n        let task = SecTaskCreateFromSelf(nil)\n        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil), (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {\n            errorInfo = "lc.settings.notDevCert".loc\n            errorShow = true\n            return\n        }\n    }\n'''
new_check = '''    func checkGetTaskAllow() {\n        // Informational only. `get-task-allow` is not an authoritative JIT-less\n        // capability test for every third-party signer. The signed-library\n        // diagnostic and real guest launch are the source of truth.\n        let task = SecTaskCreateFromSelf(nil)\n        let allowed = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil)\n            .map { ($0.takeRetainedValue() as? NSNumber)?.boolValue ?? false } ?? false\n        if !allowed {\n            print("FlekDeck: get-task-allow is false; continuing with signer-based JIT-less validation")\n        }\n    }\n'''
if old_check in tab:
    tab = tab.replace(old_check, new_check, 1)
elif 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Unexpected get-task-allow alert shape in LCTabView")
if 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Fatal development-certificate alert still present in LCTabView")
tab_path.write_text(tab)

# Preserve the actual Vibe/LiveContainer JIT-less signer and guest-launch path.
model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift").read_text()
diag = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift").read_text()
for forbidden in ("FlekHostHasDevelopmentSigning", "FlekHostDevelopmentSigningError"):
    if forbidden in model:
        raise SystemExit(f"Unexpected FlekDeck JIT-less hard gate in LCAppModel: {forbidden}")
if "FlekDeck host does not have get-task-allow" in diag:
    raise SystemExit("Unexpected FlekDeck get-task-allow hard gate in JIT-less diagnostics")
if "LCUtils.validateJITLessSetup" not in diag:
    raise SystemExit("JIT-less diagnostic no longer performs the real signed-library validation")
if "LCSharedUtils.launchToGuestApp" not in model:
    raise SystemExit("LCAppModel no longer contains the upstream JIT-less guest launch path")

# ---------------------------------------------------------------------------
# TEMP EXPERIMENT: PreviewShell-style OOPJIT executable mapping.
# ---------------------------------------------------------------------------
OOPJIT_ENTITLEMENT = "com.apple.private.oop-jit.loader"
OOPJIT_LOADER = "previews"

def add_oopjit_loader(path_string: str) -> None:
    path = Path(path_string)
    if not path.exists():
        raise SystemExit(f"OOPJIT entitlement target missing: {path}")
    with path.open("rb") as f:
        data = plistlib.load(f)
    data[OOPJIT_ENTITLEMENT] = OOPJIT_LOADER
    with path.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_XML, sort_keys=False)

for entitlement_path in (
    "entitlements.xml",
    "LiveProcess/LiveProcess.entitlements",
    "LiveProcess/LiveProcessRelease.entitlements",
):
    add_oopjit_loader(entitlement_path)

utils_path = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
utils = utils_path.read_text()
start_marker = '+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {'
end_marker = '+ (NSURL *)archiveIPAWithBundleName:'
start = utils.find(start_marker)
end = utils.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("Unable to locate validateJITLessSetup for OOPJIT experiment")

experimental_validate = r'''+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {
    // Security.framework does not publicly expose SecTask's concrete typedef,
    // while LiveContainer already uses these private entry points as void*.
    extern void *SecTaskCreateFromSelf(CFAllocatorRef allocator);
    extern CFTypeRef SecTaskCopyValueForEntitlement(void *task, CFStringRef key, CFErrorRef *error);

    // EXPERIMENT: prove the effective PreviewShell-style entitlement and then
    // perform a real executable load from /private/var/OOPJit/previews.
    NSString *path = NSTemporaryDirectory();
    [NSFileManager.defaultManager createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *tmpLibPath = [path stringByAppendingPathComponent:@"TestJITLess.dylib"];
    [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
    NSError *copySourceError = nil;
    [NSFileManager.defaultManager copyItemAtPath:[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Frameworks/TestJITLess.dylib"]
                                           toPath:tmpLibPath
                                            error:&copySourceError];
    if (copySourceError) {
        completionHandler(NO, copySourceError);
        return;
    }

    dispatch_semaphore_t sema = dispatch_semaphore_create(0);
    __block bool signSuccess = false;
    __block NSError *signError = nil;
    [LCUtils signFilesWithZSignWithURLs:@[[NSURL fileURLWithPath:tmpLibPath]]
                      completionHandler:^(BOOL success, NSError *_Nullable error) {
        signSuccess = success;
        signError = error;
        dispatch_semaphore_signal(sema);
    }];
    dispatch_semaphore_wait(sema, DISPATCH_TIME_FOREVER);

    dispatch_async(dispatch_get_main_queue(), ^{
        if (!signSuccess) {
            completionHandler(NO, signError);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }
        if (!checkCodeSignature([tmpLibPath UTF8String])) {
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:2
                                                   userInfo:@{NSLocalizedDescriptionKey: @"OOPJIT probe: signed TestJITLess.dylib failed code-signature validation."}]);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }

        void *task = SecTaskCreateFromSelf(NULL);
        CFErrorRef entitlementError = NULL;
        CFTypeRef loaderValue = task ? SecTaskCopyValueForEntitlement(task, CFSTR("com.apple.private.oop-jit.loader"), &entitlementError) : NULL;
        NSString *loader = nil;
        if (loaderValue && CFGetTypeID(loaderValue) == CFStringGetTypeID()) {
            loader = [(__bridge NSString *)loaderValue copy];
        }
        if (loaderValue) CFRelease(loaderValue);
        if (entitlementError) CFRelease(entitlementError);
        if (task) CFRelease((CFTypeRef)task);

        if (![loader isEqualToString:@"previews"]) {
            NSString *message = [NSString stringWithFormat:@"OOPJIT probe stopped: effective com.apple.private.oop-jit.loader is %@, expected previews. The signing/provisioning path stripped or did not grant the private entitlement.", loader ?: @"<missing>"];
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1001
                                                   userInfo:@{NSLocalizedDescriptionKey: message}]);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }

        const char *oopRoot = "/private/var/OOPJit";
        const char *oopDir = "/private/var/OOPJit/previews";
        errno = 0;
        int rootResult = mkdir(oopRoot, 0755);
        int rootErrno = errno;
        errno = 0;
        int dirResult = mkdir(oopDir, 0700);
        int dirErrno = errno;

        NSString *oopPath = [NSString stringWithFormat:@"/private/var/OOPJit/previews/FlekDeck-TestJITLess-%d.dylib", getpid()];
        [NSFileManager.defaultManager removeItemAtPath:oopPath error:nil];
        NSError *oopCopyError = nil;
        BOOL copied = [NSFileManager.defaultManager copyItemAtPath:tmpLibPath toPath:oopPath error:&oopCopyError];
        if (!copied) {
            NSString *message = [NSString stringWithFormat:@"OOPJIT entitlement is effective, but staging failed. mkdir root=%d errno=%d, mkdir previews=%d errno=%d, copy=%@", rootResult, rootErrno, dirResult, dirErrno, oopCopyError.localizedDescription ?: @"unknown error"];
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1002
                                                   userInfo:@{NSLocalizedDescriptionKey: message}]);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }

        unsetenv("LC_JITLESS_TEST_LOADED");
        dlerror();
        void *handle = dlopen(oopPath.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        const char *rawDlError = dlerror();
        NSString *dlError = rawDlError ? [NSString stringWithUTF8String:rawDlError] : nil;
        BOOL constructorRan = getenv("LC_JITLESS_TEST_LOADED") && strcmp(getenv("LC_JITLESS_TEST_LOADED"), "1") == 0;

        if (handle) dlclose(handle);
        [NSFileManager.defaultManager removeItemAtPath:oopPath error:nil];
        [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];

        if (!handle || !constructorRan) {
            NSString *message = [NSString stringWithFormat:@"OOPJIT staging succeeded and loader entitlement is effective, but executable dlopen failed. handle=%p constructor=%@ error=%@", handle, constructorRan ? @"YES" : @"NO", dlError ?: @"<none>"];
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1003
                                                   userInfo:@{NSLocalizedDescriptionKey: message}]);
            return;
        }

        NSLog(@"[FlekDeck OOPJIT] PASS: effective loader=previews and TestJITLess executed from /private/var/OOPJit/previews");
        completionHandler(YES, nil);
    });
}

'''
utils = utils[:start] + experimental_validate + utils[end:]
if "OOPJIT probe stopped" not in utils or "/private/var/OOPJit/previews" not in utils:
    raise SystemExit("OOPJIT LCUtils runtime probe patch did not apply")
utils_path.write_text(utils)

dyld_path = Path("LiveContainer/Tweaks/Dyld.m")
dyld = dyld_path.read_text()
old_mmap = r'''void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {
    void *map = __mmap(addr, len, prot, flags, fd, offset);
    // only handle mapping __TEXT segment from fd outside of permitted path
    if (map != MAP_FAILED || !(prot & PROT_EXEC) || fd < 0) return map;
    
    // to get around `file system sandbox blocked mmap()` we temporarily move it to permitted path
    char filePath[PATH_MAX];
    if (fcntl(fd, F_GETPATH, filePath) != 0) return map;
    char newTmpPath[PATH_MAX];
    sprintf(newTmpPath, "%s/Documents/%p.dylib", getenv("LP_HOME_PATH"), addr);
    rename(filePath, newTmpPath);
    map = __mmap(addr, len, prot, flags, fd, offset);
    rename(newTmpPath, filePath);
    
    return map;
}
'''
new_mmap = r'''void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {
    void *map = __mmap(addr, len, prot, flags, fd, offset);
    if (map != MAP_FAILED || !(prot & PROT_EXEC) || fd < 0) return map;

    char filePath[PATH_MAX];
    if (fcntl(fd, F_GETPATH, filePath) != 0) return map;

    // TEMP EXPERIMENT: try the PreviewShell OOPJIT executable-map area first.
    (void)mkdir("/private/var/OOPJit", 0755);
    (void)mkdir("/private/var/OOPJit/previews", 0700);
    char oopTmpPath[PATH_MAX];
    snprintf(oopTmpPath, sizeof(oopTmpPath), "/private/var/OOPJit/previews/flekdeck-%d-%p.dylib", getpid(), addr);
    if (rename(filePath, oopTmpPath) == 0) {
        void *oopMap = __mmap(addr, len, prot, flags, fd, offset);
        int oopMapErrno = errno;
        (void)rename(oopTmpPath, filePath);
        if (oopMap != MAP_FAILED) {
            NSLog(@"[FlekDeck OOPJIT] executable mmap succeeded via /private/var/OOPJit/previews");
            return oopMap;
        }
        errno = oopMapErrno;
    }

    // Preserve upstream LiveContainer's private-container workaround.
    const char *lpHome = getenv("LP_HOME_PATH");
    if (!lpHome) return map;
    char newTmpPath[PATH_MAX];
    snprintf(newTmpPath, sizeof(newTmpPath), "%s/Documents/%p.dylib", lpHome, addr);
    if (rename(filePath, newTmpPath) == 0) {
        map = __mmap(addr, len, prot, flags, fd, offset);
        (void)rename(newTmpPath, filePath);
    }
    return map;
}
'''
if old_mmap not in dyld:
    raise SystemExit("Unable to locate upstream jitless_hook_mmap for OOPJIT experiment")
dyld = dyld.replace(old_mmap, new_mmap, 1)
if "[FlekDeck OOPJIT] executable mmap succeeded" not in dyld:
    raise SystemExit("OOPJIT dyld mmap fallback patch did not apply")
dyld_path.write_text(dyld)

print("Applied signer-compatible SideStore integration plus TEMP PreviewShell OOPJIT runtime experiment")