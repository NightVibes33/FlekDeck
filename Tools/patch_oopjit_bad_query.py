from pathlib import Path

# This script runs AFTER patch_free_sidestore_support.py on the experimental
# branch. It deliberately ignores the missing Apple-private OOPJIT entitlement
# and measures whether a bad_query-acquired filesystem sandbox extension changes
# access to /private/var/OOPJit or executable mmap behavior.

bad_query_core = r'''
#include <xpc/xpc.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>

typedef void *(*FlekContainerQueryCreateFn)(void);
typedef void (*FlekContainerQuerySetClassFn)(void *, uint64_t);
typedef void (*FlekContainerQuerySetIdentifiersFn)(void *, xpc_object_t);
typedef void (*FlekContainerQuerySetFlagsFn)(void *, uint64_t);
typedef void (*FlekContainerQuerySetPartFn)(void *, uint64_t);
typedef void (*FlekContainerQuerySetPartDomainFn)(void *, const char *);
typedef void *(*FlekContainerQueryGetSingleResultFn)(void *);
typedef void (*FlekContainerQueryFreeFn)(void *);
typedef char *(*FlekContainerCopySandboxTokenFn)(void *);
typedef int64_t (*FlekSandboxExtensionConsumeFn)(const char *);
typedef int (*FlekSandboxExtensionReleaseFn)(int64_t);

static int64_t FlekBadQueryAcquirePath(const char *path) {
    if (!path || path[0] != '/') return -255;

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

    querySetClass(query, 13);
    xpc_object_t identifier = xpc_string_create("systemgroup.com.apple.mobilegestaltcache");
    querySetIdentifiers(query, identifier);
    querySetPart(query, 3);

    char *part = NULL;
    if (asprintf(&part, "../../../../../../../..%s", path) == -1 || !part) {
        queryFree(query);
        dlclose(mgr);
        return -5;
    }
    querySetPartDomain(query, part);
    querySetFlags(query, 0x0000008000000000ULL);

    void *result = queryGetSingleResult(query);
    if (!result) {
        free(part);
        queryFree(query);
        dlclose(mgr);
        return -3;
    }

    char *token = copySandboxToken(result);
    if (!token) {
        free(part);
        queryFree(query);
        dlclose(mgr);
        return -4;
    }

    int64_t handle = consumeExtension(token);
    free(token);
    free(part);
    queryFree(query);
    dlclose(mgr);
    return handle;
}

static void FlekBadQueryReleasePath(int64_t handle) {
    if (handle < 0) return;
    FlekSandboxExtensionReleaseFn releaseExtension =
        (FlekSandboxExtensionReleaseFn)dlsym(RTLD_DEFAULT, "sandbox_extension_release");
    if (releaseExtension) releaseExtension(handle);
}
'''

# ---------------- Host diagnostic ----------------
utils_path = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
utils = utils_path.read_text()
security_marker = "@import Security;\n"
if security_marker not in utils:
    raise SystemExit("LCUtils Security import marker missing")

host_helpers = bad_query_core + r'''
static NSString *FlekErrnoString(int value) {
    if (value == 0) return @"0";
    return [NSString stringWithFormat:@"%d (%s)", value, strerror(value)];
}

static NSString *FlekProbePath(const char *label, const char *path) {
    struct stat st;
    errno = 0;
    int statResult = lstat(path, &st);
    int statErrno = statResult == 0 ? 0 : errno;

    errno = 0;
    int existsResult = access(path, F_OK);
    int existsErrno = existsResult == 0 ? 0 : errno;

    errno = 0;
    int readResult = access(path, R_OK);
    int readErrno = readResult == 0 ? 0 : errno;

    errno = 0;
    int writeResult = access(path, W_OK);
    int writeErrno = writeResult == 0 ? 0 : errno;

    errno = 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    int openErrno = fd >= 0 ? 0 : errno;
    if (fd >= 0) close(fd);

    return [NSString stringWithFormat:@"%s: stat=%d/%@ exists=%d/%@ read=%d/%@ write=%d/%@ open=%d/%@",
            label,
            statResult, FlekErrnoString(statErrno),
            existsResult, FlekErrnoString(existsErrno),
            readResult, FlekErrnoString(readErrno),
            writeResult, FlekErrnoString(writeErrno),
            fd >= 0 ? 0 : -1, FlekErrnoString(openErrno)];
}

static NSString *FlekRawExecMapProbe(NSString *path, BOOL *successOut) {
    if (successOut) *successOut = NO;
    errno = 0;
    int fd = open(path.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
    int openErrno = fd >= 0 ? 0 : errno;
    if (fd < 0) {
        return [NSString stringWithFormat:@"mmap %@: open failed %@",
                path.lastPathComponent, FlekErrnoString(openErrno)];
    }

    struct stat st;
    errno = 0;
    int statResult = fstat(fd, &st);
    int statErrno = statResult == 0 ? 0 : errno;
    if (statResult != 0 || st.st_size <= 0) {
        close(fd);
        return [NSString stringWithFormat:@"mmap %@: fstat failed %@",
                path.lastPathComponent, FlekErrnoString(statErrno)];
    }

    size_t mapLength = (size_t)MIN((off_t)0x4000, st.st_size);
    errno = 0;
    void *mapped = mmap(NULL, mapLength, PROT_READ | PROT_EXEC, MAP_PRIVATE, fd, 0);
    int mapErrno = mapped == MAP_FAILED ? errno : 0;
    close(fd);

    if (mapped != MAP_FAILED) {
        munmap(mapped, mapLength);
        if (successOut) *successOut = YES;
        return [NSString stringWithFormat:@"mmap %@: PASS len=%zu",
                path.lastPathComponent, mapLength];
    }
    return [NSString stringWithFormat:@"mmap %@: FAIL %@",
            path.lastPathComponent, FlekErrnoString(mapErrno)];
}
'''
utils = utils.replace(security_marker, security_marker + host_helpers + "\n", 1)

method_start = '+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {'
method_end = '+ (NSURL *)archiveIPAWithBundleName:'
start = utils.find(method_start)
end = utils.find(method_end, start)
if start == -1 or end == -1:
    raise SystemExit("Unable to locate JIT-less diagnostic method")

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

    dispatch_async(dispatch_get_main_queue(), ^{
        NSMutableArray<NSString *> *report = [NSMutableArray array];

        if (!signSuccess) {
            completionHandler(NO, signError);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }
        if (!checkCodeSignature(tmpLibPath.UTF8String)) {
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1200
                                                   userInfo:@{NSLocalizedDescriptionKey:
                                                                  @"OOPJIT/bad_query probe: signed test dylib failed signature validation."}]);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            return;
        }

        void *task = SecTaskCreateFromSelf(NULL);
        CFErrorRef entitlementError = NULL;
        CFTypeRef loaderValue = task ? SecTaskCopyValueForEntitlement(
            task, CFSTR("com.apple.private.oop-jit.loader"), &entitlementError) : NULL;
        NSString *loader = nil;
        if (loaderValue && CFGetTypeID(loaderValue) == CFStringGetTypeID()) {
            loader = [(__bridge NSString *)loaderValue copy];
        }
        if (loaderValue) CFRelease(loaderValue);
        if (entitlementError) CFRelease(entitlementError);
        if (task) CFRelease((CFTypeRef)task);
        [report addObject:[NSString stringWithFormat:@"effective oop-jit.loader=%@",
                           loader ?: @"<missing>"]];

        BOOL baselineMap = NO;
        [report addObject:FlekRawExecMapProbe(tmpLibPath, &baselineMap)];

        const char *oopRoot = "/private/var/OOPJit";
        const char *oopDir = "/private/var/OOPJit/previews";
        [report addObject:FlekProbePath("before root", oopRoot)];
        [report addObject:FlekProbePath("before previews", oopDir)];

        errno = 0;
        int preRootMkdir = mkdir(oopRoot, 0755);
        int preRootErrno = preRootMkdir == 0 ? 0 : errno;
        errno = 0;
        int preDirMkdir = mkdir(oopDir, 0700);
        int preDirErrno = preDirMkdir == 0 ? 0 : errno;
        [report addObject:[NSString stringWithFormat:
            @"before bad_query mkdir root=%d/%@ previews=%d/%@",
            preRootMkdir, FlekErrnoString(preRootErrno),
            preDirMkdir, FlekErrnoString(preDirErrno)]];

        int64_t rootExtension = FlekBadQueryAcquirePath(oopRoot);
        int64_t previewExtension = FlekBadQueryAcquirePath(oopDir);
        [report addObject:[NSString stringWithFormat:
            @"bad_query rootHandle=%lld previewsHandle=%lld",
            (long long)rootExtension, (long long)previewExtension]];

        errno = 0;
        int postRootMkdir = mkdir(oopRoot, 0755);
        int postRootErrno = postRootMkdir == 0 ? 0 : errno;
        errno = 0;
        int postDirMkdir = mkdir(oopDir, 0700);
        int postDirErrno = postDirMkdir == 0 ? 0 : errno;
        [report addObject:[NSString stringWithFormat:
            @"after bad_query mkdir root=%d/%@ previews=%d/%@",
            postRootMkdir, FlekErrnoString(postRootErrno),
            postDirMkdir, FlekErrnoString(postDirErrno)]];
        [report addObject:FlekProbePath("after root", oopRoot)];
        [report addObject:FlekProbePath("after previews", oopDir)];

        NSString *oopPath = [NSString stringWithFormat:
            @"/private/var/OOPJit/previews/FlekDeck-TestJITLess-%d.dylib", getpid()];
        [NSFileManager.defaultManager removeItemAtPath:oopPath error:nil];

        NSError *oopCopyError = nil;
        BOOL copied = [NSFileManager.defaultManager copyItemAtPath:tmpLibPath
                                                            toPath:oopPath
                                                             error:&oopCopyError];
        [report addObject:[NSString stringWithFormat:@"stage copy=%@ error=%@",
                           copied ? @"PASS" : @"FAIL",
                           oopCopyError.localizedDescription ?: @"<none>"]];

        if (!copied) {
            NSString *reportText = [report componentsJoinedByString:@"\n"];
            [NSUserDefaults.standardUserDefaults setObject:reportText
                                                    forKey:@"FlekOOPJITLastProbeReport"];
            NSLog(@"[FlekDeck OOPJIT] %@", reportText);
            FlekBadQueryReleasePath(previewExtension);
            FlekBadQueryReleasePath(rootExtension);
            [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1201
                                                   userInfo:@{NSLocalizedDescriptionKey:
                [@"OOPJIT + bad_query staging failed.\n" stringByAppendingString:reportText]}]);
            return;
        }

        BOOL oopMap = NO;
        [report addObject:FlekRawExecMapProbe(oopPath, &oopMap)];

        unsetenv("LC_JITLESS_TEST_LOADED");
        dlerror();
        void *handle = dlopen(oopPath.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        const char *rawDlError = dlerror();
        NSString *dlError = rawDlError ? [NSString stringWithUTF8String:rawDlError] : nil;
        BOOL constructorRan = getenv("LC_JITLESS_TEST_LOADED") &&
                              strcmp(getenv("LC_JITLESS_TEST_LOADED"), "1") == 0;
        [report addObject:[NSString stringWithFormat:
            @"dlopen handle=%p constructor=%@ error=%@",
            handle, constructorRan ? @"YES" : @"NO", dlError ?: @"<none>"]];

        if (handle) dlclose(handle);
        [NSFileManager.defaultManager removeItemAtPath:oopPath error:nil];
        [NSFileManager.defaultManager removeItemAtPath:tmpLibPath error:nil];
        FlekBadQueryReleasePath(previewExtension);
        FlekBadQueryReleasePath(rootExtension);

        NSString *reportText = [report componentsJoinedByString:@"\n"];
        [NSUserDefaults.standardUserDefaults setObject:reportText
                                                forKey:@"FlekOOPJITLastProbeReport"];
        NSLog(@"[FlekDeck OOPJIT] %@", reportText);

        if (!handle || !constructorRan) {
            completionHandler(NO, [NSError errorWithDomain:NSBundle.mainBundle.bundleIdentifier
                                                       code:1202
                                                   userInfo:@{NSLocalizedDescriptionKey:
                [@"OOPJIT + bad_query reached executable loading but did not execute the test library.\n"
                    stringByAppendingString:reportText]}]);
            return;
        }

        NSLog(@"[FlekDeck OOPJIT] PASS: test library executed from /private/var/OOPJit/previews");
        completionHandler(YES, nil);
    });
}

'''
utils = utils[:start] + new_validate + utils[end:]
if "bad_query rootHandle" not in utils or "FlekRawExecMapProbe" not in utils:
    raise SystemExit("Host OOPJIT/bad_query probe patch did not apply")
utils_path.write_text(utils)

# ---------------- Real guest mmap path ----------------
dyld_path = Path("LiveContainer/Tweaks/Dyld.m")
dyld = dyld_path.read_text()
foundation_marker = "@import Foundation;\n"
if foundation_marker not in dyld:
    raise SystemExit("Dyld Foundation import marker missing")

guest_helpers = bad_query_core + r'''
static int64_t gFlekOOPJITRootExtension = -999;
static int64_t gFlekOOPJITPreviewsExtension = -999;

static void FlekEnsureOOPJITBadQueryAccess(void) {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        gFlekOOPJITRootExtension = FlekBadQueryAcquirePath("/private/var/OOPJit");
        gFlekOOPJITPreviewsExtension = FlekBadQueryAcquirePath("/private/var/OOPJit/previews");
        NSLog(@"[FlekDeck OOPJIT] bad_query guest access root=%lld previews=%lld",
              (long long)gFlekOOPJITRootExtension,
              (long long)gFlekOOPJITPreviewsExtension);
    });
}
'''
dyld = dyld.replace(foundation_marker, foundation_marker + guest_helpers + "\n", 1)

init_marker = "void DyldHooksInit(bool hideLiveContainer, bool hookDlopen, uint32_t spoofSDKVersion) {\n"
if init_marker not in dyld:
    raise SystemExit("DyldHooksInit marker missing")
dyld = dyld.replace(
    init_marker,
    init_marker + '''    if (@available(iOS 27.0, *)) {
        // Acquire the filesystem extension before dyld's mmap interception starts.
        FlekEnsureOOPJITBadQueryAccess();
        (void)mkdir("/private/var/OOPJit", 0755);
        (void)mkdir("/private/var/OOPJit/previews", 0700);
    }
''',
    1
)

mmap_start_marker = "void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {"
mmap_end_marker = "static void *machOChainedFixupsValidLinkedit;"
mmap_start = dyld.find(mmap_start_marker)
mmap_end = dyld.find(mmap_end_marker, mmap_start)
if mmap_start == -1 or mmap_end == -1:
    raise SystemExit("Unable to locate jitless_hook_mmap")

new_mmap = r'''void* jitless_hook_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset) {
    void *map = __mmap(addr, len, prot, flags, fd, offset);
    if (map != MAP_FAILED || !(prot & PROT_EXEC) || fd < 0) return map;

    char filePath[PATH_MAX];
    if (fcntl(fd, F_GETPATH, filePath) != 0) return map;

    if (@available(iOS 27.0, *)) {
        char oopTmpPath[PATH_MAX];
        snprintf(oopTmpPath, sizeof(oopTmpPath),
                 "/private/var/OOPJit/previews/flekdeck-%d-%p.dylib",
                 getpid(), addr);

        errno = 0;
        if (rename(filePath, oopTmpPath) == 0) {
            void *oopMap = __mmap(addr, len, prot, flags, fd, offset);
            int oopMapErrno = oopMap == MAP_FAILED ? errno : 0;
            (void)rename(oopTmpPath, filePath);

            if (oopMap != MAP_FAILED) {
                NSLog(@"[FlekDeck OOPJIT] guest executable mmap PASS via OOPJit/bad_query");
                return oopMap;
            }

            NSLog(@"[FlekDeck OOPJIT] guest OOPJit mmap failed errno=%d (%s)",
                  oopMapErrno, strerror(oopMapErrno));
            errno = oopMapErrno;
        } else {
            int renameErrno = errno;
            NSLog(@"[FlekDeck OOPJIT] guest OOPJit rename failed errno=%d (%s)",
                  renameErrno, strerror(renameErrno));
        }
    }

    // Preserve the exact upstream LiveContainer fallback.
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
if "guest executable mmap PASS via OOPJit/bad_query" not in dyld:
    raise SystemExit("Guest OOPJIT/bad_query mmap patch did not apply")
dyld_path.write_text(dyld)

print("Applied second-stage OOPJIT + bad_query probe and guest mapper")
