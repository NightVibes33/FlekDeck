//
//  main.m
//  LiveProcess
//
//  Created by Duy Tran on 3/5/25.
//

#import <dlfcn.h>
#import <UIKit/UIKit.h>
#import <mach-o/dyld.h>
#import <objc/message.h>
#import <sys/types.h>
#import <unistd.h>
#import <stdlib.h>
#import <string.h>
#import <errno.h>
#import "../LiveContainer/LCSharedUtils.h"
#import "../LiveContainer/utils.h"
#import "../LiveContainer/Tweaks/Tweaks.h"
#import "../SideStore/XPCServer.h"

@interface LiveProcessHandler : NSObject<NSExtensionRequestHandling>
@end
@implementation LiveProcessHandler
static NSExtensionContext *extensionContext;
static NSDictionary *retrievedAppInfo;
static NSMutableArray<NSURL *> *activeResourceURLs;
+ (NSExtensionContext *)extensionContext {
    return extensionContext;
}

+ (NSDictionary *)retrievedAppInfo {
    return retrievedAppInfo;
}

// Upstream Nyxian drops its NSExtensionContext after decoding the ROM
// launch request, before handing XPC endpoints to its PE runtime. Keeping
// FlekDeck's separate static references alive retains the XPC request and
// its Mach send rights even after the payload has been unpacked.
+ (void)releaseROMRequestPayload {
    retrievedAppInfo = nil;
    extensionContext = nil;
}

- (void)beginRequestWithExtensionContext:(NSExtensionContext *)context {
    extensionContext = context;
    retrievedAppInfo = [context.inputItems.firstObject userInfo];
    // Return control to LiveContainerMain
    CFRunLoopStop(CFRunLoopGetMain());
}
@end

extern int LiveContainerMain(int argc, char *argv[]);
static char **_envp, **_apple = NULL;

static void *flekDeckROMRuntimeHandle;
static NSString *flekDeckROMRuntimeError;

static NSError *FlekDeckPEError(NSInteger code, NSString *description) {
    return [NSError errorWithDomain:@"FlekDeck.PEBridge"
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description ?: @"FlekDeck could not start the ROM process."}];
}

/*
 * The PE client library is rebuilt from pinned upstream source for FlekDeck.
 * Load its secure-coding classes before NSExtension decodes a ROM request.
 * Normal LiveContainer requests never initialize the PE execution environment.
 */
static BOOL FlekDeckPrepareROMRuntime(void) {
    if (flekDeckROMRuntimeHandle) return YES;
    flekDeckROMRuntimeError = nil;
    // Register PE secure-coding classes before decoding the launch request.
    // Loading these classes does not initialize the PE execution environment.
    // Private host storage is handed off later through PEFilePermissions, so
    // the extension cannot use a shared boot-session file to choose this path.
    if (@available(iOS 18.0, *)) {
        NSURL *clientLibrary = [NSBundle.mainBundle.privateFrameworksURL
            URLByAppendingPathComponent:@"FlekDeckPERuntime.dylib"];
        if (![NSFileManager.defaultManager fileExistsAtPath:clientLibrary.path]) {
            flekDeckROMRuntimeError = @"The FlekDeck PE client library is missing from this build.";
            return NO;
        }
        dlerror();
        void *handle = dlopen(clientLibrary.fileSystemRepresentation,
                             RTLD_NOW | RTLD_GLOBAL | RTLD_NODELETE);
        if (!handle) {
            const char *detail = dlerror();
            flekDeckROMRuntimeError = [NSString stringWithFormat:@"Could not load the FlekDeck PE client: %s", detail ?: "unknown dyld error"];
            return NO;
        }
        for (NSString *className in @[@"PEFileTable", @"PEFileHandle", @"PEMachPort"]) {
            if (NSClassFromString(className) == Nil) {
                flekDeckROMRuntimeError = [NSString stringWithFormat:@"The PE client did not register %@.", className];
                return NO;
            }
        }
        flekDeckROMRuntimeHandle = handle;
        return YES;
    }
    flekDeckROMRuntimeError = @"The Nyxian 0.11.5 PE client requires iOS 18 or newer.";
    return NO;
}

static int FlekDeckRejectPERequest(NSString *detail) {
    NSError *error = FlekDeckPEError(ENOTSUP, detail);
    [LiveProcessHandler.extensionContext cancelRequestWithError:error];
    NSLog(@"LiveProcess: %@", detail);
    return ENOTSUP;
}

typedef void (*FlekDeckPEConnectHostFunction)(NSXPCListenerEndpoint *endpoint);
typedef void (*FlekDeckPEConnectSyscallFunction)(id syscallPort);
typedef int (*FlekDeckPEEnvironmentInitFunction)(NSInteger mode, NSString *executablePath, int argc, char *argv[]);

static int FlekDeckRunPERequest(NSDictionary *appInfo) {
    if (!FlekDeckPrepareROMRuntime()) {
        return FlekDeckRejectPERequest(flekDeckROMRuntimeError ?: @"The imported ROM runtime could not be loaded.");
    }

    FlekDeckPEConnectHostFunction connectHost =
        (FlekDeckPEConnectHostFunction)dlsym(flekDeckROMRuntimeHandle, "environment_client_connect_to_host");
    FlekDeckPEConnectSyscallFunction connectSyscall =
        (FlekDeckPEConnectSyscallFunction)dlsym(flekDeckROMRuntimeHandle, "environment_client_connect_to_syscall_proxy");
    FlekDeckPEEnvironmentInitFunction environmentInit =
        (FlekDeckPEEnvironmentInitFunction)dlsym(flekDeckROMRuntimeHandle, "environment_init");
    if (!connectHost || !connectSyscall || !environmentInit) {
        return FlekDeckRejectPERequest(
            @"The packaged PE client is missing a required environment entry point.");
    }

    NSString *executablePath = appInfo[@"PEExecutablePath"];
    NSXPCListenerEndpoint *endpoint = appInfo[@"PEEndpoint"];
    id syscallPort = appInfo[@"PESyscallPort"];
    NSDictionary *environment = appInfo[@"PEEnvironment"];
    NSArray *arguments = appInfo[@"PEArguments"];
    NSString *workingDirectory = appInfo[@"PEWorkingDirectory"];
    id fileTable = appInfo[@"PEFileTable"];
    NSArray *permissions = appInfo[@"PEFilePermissions"];

    if (![executablePath isKindOfClass:NSString.class] || executablePath.length == 0 ||
        ![endpoint isKindOfClass:NSXPCListenerEndpoint.class] ||
        ![syscallPort isKindOfClass:NSClassFromString(@"PEMachPort")] ||
        (environment && ![environment isKindOfClass:NSDictionary.class]) ||
        (arguments && ![arguments isKindOfClass:NSArray.class]) ||
        (permissions && ![permissions isKindOfClass:NSArray.class])) {
        return FlekDeckRejectPERequest(@"The PE launch request is missing required endpoint, executable, argument, or environment data.");
    }

    typedef int64_t (*FlekDeckSandboxConsumeFunction)(const char *token);
    FlekDeckSandboxConsumeFunction consume =
        (FlekDeckSandboxConsumeFunction)dlsym(RTLD_DEFAULT, "sandbox_extension_consume");
    if (permissions.count && !consume) {
        return FlekDeckRejectPERequest(@"LiveProcess cannot consume the ROM's sandbox file permissions.");
    }
    for (id permission in permissions) {
        if (![permission isKindOfClass:NSData.class] || ![permission length] ||
            [permission length] > 1048576) {
            return FlekDeckRejectPERequest(@"The ROM supplied an invalid sandbox file permission.");
        }
        NSMutableData *token = [permission mutableCopy];
        const char terminator = '\0';
        [token appendBytes:&terminator length:1];
        if (consume(token.bytes) < 0) {
            return FlekDeckRejectPERequest(@"LiveProcess could not consume a ROM sandbox file permission.");
        }
    }

    // Tokens must grant real filesystem access before the PE runtime starts.
    if (![NSFileManager.defaultManager isReadableFileAtPath:executablePath]) {
        return FlekDeckRejectPERequest(
            @"LiveProcess cannot read the ROM executable after consuming PEFilePermissions. Re-import the ROM and export the boot log.");
    }

    NSString *directory = [workingDirectory isKindOfClass:NSString.class] && workingDirectory.length
        ? workingDirectory
        : [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
    if (chdir(directory.fileSystemRepresentation) != 0) {
        return FlekDeckRejectPERequest([NSString stringWithFormat:@"Could not enter the ROM working directory %@: %s",
                                        directory, strerror(errno)]);
    }

    SEL applySelector = NSSelectorFromString(@"apply");
    if ([fileTable isKindOfClass:NSClassFromString(@"PEFileTable")] &&
        [fileTable respondsToSelector:applySelector]) {
        ((void (*)(id, SEL))objc_msgSend)(fileTable, applySelector);
        setvbuf(stdout, NULL, _IONBF, 0);
        setvbuf(stderr, NULL, _IONBF, 0);
    } else if (fileTable) {
        return FlekDeckRejectPERequest(@"The ROM file-descriptor table is not compatible with FlekDeck LiveProcess.");
    }

    // Mirror Nyxian's ROM-only XPC lifecycle. The endpoint, syscall port,
    // environment, and argv are now retained in local variables; detach the
    // original NSExtensionContext and userInfo dictionary before activating
    // the PE host/syscall connections. Do NOT affect regular guest requests.
    appInfo = nil;
    [LiveProcessHandler releaseROMRequestPayload];

    connectHost(endpoint);
    connectSyscall(syscallPort);

    for (NSString *key in NSProcessInfo.processInfo.environment.allKeys) {
        unsetenv(key.UTF8String);
    }
    for (id key in environment) {
        id value = environment[key];
        if ([key isKindOfClass:NSString.class] && [value isKindOfClass:NSString.class]) {
            setenv([key UTF8String], [value UTF8String], 1);
        }
    }

    NSArray *sourceArguments = arguments.count ? arguments : @[executablePath];
    char **guestArgv = calloc(sourceArguments.count + 1, sizeof(char *));
    if (!guestArgv) {
        return FlekDeckRejectPERequest(@"LiveProcess could not allocate the ROM argument vector.");
    }
    for (NSUInteger i = 0; i < sourceArguments.count; i++) {
        id argument = sourceArguments[i];
        if (![argument isKindOfClass:NSString.class]) {
            for (NSUInteger j = 0; j < i; j++) free(guestArgv[j]);
            free(guestArgv);
            return FlekDeckRejectPERequest(@"The ROM supplied a non-string process argument.");
        }
        guestArgv[i] = strdup([argument UTF8String]);
        if (!guestArgv[i]) {
            for (NSUInteger j = 0; j < i; j++) free(guestArgv[j]);
            free(guestArgv);
            return FlekDeckRejectPERequest(@"LiveProcess could not copy the ROM argument vector.");
        }
    }

    SEL argumentsSelector = NSSelectorFromString(@"setArguments:");
    if ([NSProcessInfo.processInfo respondsToSelector:argumentsSelector]) {
        ((void (*)(id, SEL, id))objc_msgSend)(NSProcessInfo.processInfo, argumentsSelector, sourceArguments);
    }
    int status = environmentInit(1, executablePath, (int)sourceArguments.count, guestArgv);
    for (NSUInteger i = 0; i < sourceArguments.count; i++) free(guestArgv[i]);
    free(guestArgv);
    return status;
}


static NSError *LiveProcessLaunchError(NSInteger code, NSString *description) {
    return [NSError errorWithDomain:@"LiveProcess"
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey:
        description.length ? description : @"LiveProcess could not access the guest files."}];
}

static BOOL ConfigureGuestResources(NSDictionary *appInfo, NSError **outError) {
    NSArray *resources = appInfo[@"resources"];
    if (![resources isKindOfClass:NSArray.class] || resources.count == 0) {
        return NO;
    }

    activeResourceURLs = [NSMutableArray arrayWithCapacity:resources.count];
    NSMutableSet<NSString *> *configuredRoles = [NSMutableSet set];
    NSDictionary<NSString *, NSString *> *environmentKeys = @{
        @"bundle": @"LC_LIVEPROCESS_BUNDLE_PATH",
        @"container": @"LC_LIVEPROCESS_DATA_PATH",
        @"tweaks": @"LC_LIVEPROCESS_TWEAKS_PATH",
        @"appGroups": @"LC_LIVEPROCESS_APP_GROUPS_PATH",
        @"containerLocks": @"LC_LIVEPROCESS_LOCKS_PATH",
        @"sideStoreContainer": @"LC_LIVEPROCESS_SIDESTORE_PATH",
    };

    for (id candidate in resources) {
        if (![candidate isKindOfClass:NSDictionary.class]) continue;
        NSDictionary *resource = candidate;
        NSString *role = resource[@"role"];
        NSData *bookmark = resource[@"bookmark"];
        if (![role isKindOfClass:NSString.class] ||
            ![bookmark isKindOfClass:NSData.class] || !bookmark.length) {
            if (outError) {
                *outError = LiveProcessLaunchError(EINVAL,
                    @"The host supplied an invalid guest resource bookmark.");
            }
            return NO;
        }

        BOOL isStale = NO;
        NSError *resolutionError = nil;
        NSURL *url = [NSURL URLByResolvingBookmarkData:bookmark
                                               options:0
                                         relativeToURL:nil
                                   bookmarkDataIsStale:&isStale
                                                 error:&resolutionError];
        if (!url.isFileURL || !url.path.length) {
            if (outError) {
                NSString *detail = resolutionError.localizedDescription ?: @"the bookmark did not resolve";
                *outError = LiveProcessLaunchError(resolutionError.code ?: EACCES,
                    [NSString stringWithFormat:@"The %@ resource is unavailable: %@", role, detail]);
            }
            return NO;
        }

        // Resolution installs an ephemeral extension on iOS. Explicitly hold
        // its security scope too, and retain every URL for the full guest
        // lifetime so Foundation cannot release the access grant early.
        BOOL scoped = [url startAccessingSecurityScopedResource];
        BOOL exists = [NSFileManager.defaultManager fileExistsAtPath:url.path];
        BOOL readOnly = [resource[@"readOnly"] boolValue];
        BOOL accessible = exists && access(url.fileSystemRepresentation, R_OK) == 0;
        if (!readOnly) accessible = accessible && access(url.fileSystemRepresentation, W_OK) == 0;
        if (!accessible) {
            if (scoped) [url stopAccessingSecurityScopedResource];
            if (outError) {
                *outError = LiveProcessLaunchError(EACCES,
                    [NSString stringWithFormat:@"LiveProcess cannot %@ the %@ resource at %@.",
                     readOnly ? @"read" : @"read or write", role, url.path]);
            }
            return NO;
        }
        if (isStale) {
            NSLog(@"LiveProcess: %@ resource bookmark is stale but remains accessible", role);
        }
        [activeResourceURLs addObject:url];
        [configuredRoles addObject:role];

        NSString *environmentKey = environmentKeys[role];
        if (environmentKey.length) {
            setenv(environmentKey.UTF8String, url.fileSystemRepresentation, 1);
        }
    }

    BOOL isSideStore = [appInfo[@"selected"] isEqualToString:@"builtinSideStore"];
    BOOL missingRequiredRole = isSideStore
        ? ![configuredRoles containsObject:@"sideStoreContainer"]
        : (![configuredRoles containsObject:@"bundle"] ||
           ![configuredRoles containsObject:@"container"] ||
           ![configuredRoles containsObject:@"tweaks"] ||
           ![configuredRoles containsObject:@"appGroups"]);
    if (missingRequiredRole) {
        if (outError) {
            *outError = LiveProcessLaunchError(EINVAL,
                @"The host did not provide all required guest resources.");
        }
        return NO;
    }
    return YES;
}

int LiveProcessMain(int argc, char *argv[]) {
    // Let NSExtensionContext initialize, once it's done it will call CFRunLoopStop
    CFRunLoopRun();
    // Ensure app info is delivered
    NSDictionary *appInfo = LiveProcessHandler.retrievedAppInfo;
    NSCAssert(appInfo, @"Failed to retrieve app info");

    // The Nyxian PE launch path is separate from ordinary LiveContainer app launches.
    if ([appInfo[@"PEExecutablePath"] isKindOfClass:NSString.class]) {
        exit(FlekDeckRunPERequest(appInfo));
    }
    
    // Check if we received a request to execute a custom payload
    NSString *customPayloadDylib = appInfo[@"customPayloadDylib"];
    if(customPayloadDylib) {
        void *handle = dlopen(customPayloadDylib.fileSystemRepresentation, RTLD_LAZY);
        NSCAssert(appInfo, @"Failed to load custom payload dylib at path: %@", customPayloadDylib);
        
        NSString *customPayloadEntry = appInfo[@"customPayloadEntry"];
        NSCAssert(customPayloadEntry, @"Missing customPayloadEntry");
        int (*payloadEntry)(int, char **, char **, char **) = dlsym(handle, customPayloadEntry.UTF8String);
        return payloadEntry(argc, argv, _envp, _apple);
    }
    
    NSLog(@"LiveProcess: received launch for %@ (%@)",
          appInfo[@"selected"], appInfo[@"selectedContainer"]);
    // Set LiveContainer's home path
    setenv("LP_HOME_PATH", getenv("HOME"), 1);
    const char *overrideHomePath = [appInfo[@"lcHomePath"] fileSystemRepresentation];
    if(overrideHomePath) setenv("LC_HOME_PATH", overrideHomePath, 1);
    // Pass selected app info to user defaults
    NSUserDefaults *lcUserDefaults = NSUserDefaults.standardUserDefaults;
    NSDictionary<NSString *, NSString *> *launchValues = @{
        @"hostUrlScheme": appInfo[@"hostUrlScheme"] ?: @"iossim",
        @"selected": appInfo[@"selected"] ?: @"",
        @"selectedContainer": appInfo[@"selectedContainer"] ?: @""
    };
    [launchValues enumerateKeysAndObjectsUsingBlock:^(NSString *key, NSString *value, BOOL *stop) {
        if (value.length) [lcUserDefaults setObject:value forKey:key];
        else [lcUserDefaults removeObjectForKey:key];
    }];
    NSString *launchURLScheme = appInfo[@"launchAppUrlScheme"];
    if (launchURLScheme.length) [lcUserDefaults setObject:launchURLScheme forKey:@"launchAppUrlScheme"];
    else [lcUserDefaults removeObjectForKey:@"launchAppUrlScheme"];
    if(appInfo[@"certificatePassword"]) {
        [lcUserDefaults setObject:appInfo[@"certificatePassword"] forKey:@"LCCertificatePassword"];
    } else {
        [lcUserDefaults removeObjectForKey:@"LCCertificatePassword"];
    }
    
    NSError *resourceError = nil;
    BOOL hasStructuredResources = ConfigureGuestResources(appInfo, &resourceError);
    if (resourceError) {
        [LiveProcessHandler.extensionContext cancelRequestWithError:resourceError];
        return EACCES;
    }

    // Compatibility for SideStore/older hosts which still send an unlabelled
    // bookmark array. New VibeContainers launches always use role-labelled
    // resources so bootstrap receives the bookmark-resolved canonical paths.
    BOOL legacyAccess = NO;
    NSMutableArray<NSURL *> *legacyURLs = [NSMutableArray array];
    if (!hasStructuredResources) {
        NSArray *bookmarks = appInfo[@"bookmarks"];
        for (NSData *bookmark in bookmarks) {
            if (![bookmark isKindOfClass:NSData.class]) continue;
            BOOL isStale = NO;
            NSError *error = nil;
            NSURL *url = [NSURL URLByResolvingBookmarkData:bookmark options:0
                                             relativeToURL:nil
                                       bookmarkDataIsStale:&isStale error:&error];
            if (!url) {
                NSLog(@"LiveProcess: failed to resolve legacy bookmark: %@", error.localizedDescription);
                continue;
            }
            [legacyURLs addObject:url];
            legacyAccess |= [url startAccessingSecurityScopedResource];
        }
        activeResourceURLs = legacyURLs;
    }
    
    if ([appInfo[@"selected"] isEqualToString:@"builtinSideStore"]) {
        const char *resolvedSideStorePath = getenv("LC_LIVEPROCESS_SIDESTORE_PATH");
        if (resolvedSideStorePath && resolvedSideStorePath[0]) {
            [lcUserDefaults setObject:[NSString stringWithUTF8String:resolvedSideStorePath]
                               forKey:@"specifiedSideStoreContainerPath"];
        } else if(legacyAccess && legacyURLs.count > 0) {
            [lcUserDefaults setObject:legacyURLs.firstObject.path forKey:@"specifiedSideStoreContainerPath"];
        }
        NSXPCListenerEndpoint* endpoint = appInfo[@"endpoint"];
        if (endpoint) {
            NSXPCConnection* connection = [[NSXPCConnection alloc] initWithListenerEndpoint:endpoint];
            connection.remoteObjectInterface = [NSXPCInterface interfaceWithProtocol:@protocol(RefreshServer)];
            connection.interruptionHandler = ^{
                NSLog(@"LiveProcess: SideStore refresh connection interrupted");
            };

            [connection activate];

            NSObject<RefreshServer>* proxy = [connection remoteObjectProxy];
            LiveProcessSideStoreHandler.shared.server = proxy;
            LiveProcessSideStoreHandler.shared.connection = connection;
        }
        
    }

    
    return LiveContainerMain(argc, argv);
}

// this is our fake UIApplicationMain called from _xpc_objc_uimain (xpc_main)
__attribute__((visibility("default")))
int UIApplicationMain(int argc, char * argv[], NSString * principalClassName, NSString * delegateClassName) {
    return LiveProcessMain(argc, argv);
}

// Match the iOS extension launch interception that Nyxian uses in
// LiveProcess/main.m. The old FlekDeck implementation returned RTLD_MAIN_ONLY
// when UIKit was loaded, which rewrote dyld's *library loading* state and
// interfered with the process bootstrap before a PE request was decoded.
//
// Nyxian instead intercepts exactly the UIApplicationMain symbol lookup and
// immediately restores the original dyld dlsym implementation. This works
// for both the ROM request and FlekDeck's ordinary LiveContainer guest path,
// since both enter through the shared LiveProcessMain dispatcher.
static void* (*orig_extension_dlsym)(void *dyldApiInstancePtr, void *handle, const char *symbol);
static void* hook_extension_dlsym(void *dyldApiInstancePtr, void *handle, const char *symbol) {
    if (symbol && strcmp(symbol, "UIApplicationMain") == 0) {
        // Once extension startup resolves the entry point, stop intercepting
        // subsequent symbol lookups (Nyxian's exact lifecycle).
        performHookDyldApi("dlsym", 2, (void **)&orig_extension_dlsym, orig_extension_dlsym);
        return (void *)&UIApplicationMain;
    }
    __attribute__((musttail)) return orig_extension_dlsym(dyldApiInstancePtr, handle, symbol);
}

// Extension entry point
int NSExtensionMain(int argc, char *argv[], char *envp[], char *apple[]) {
    // Decode both request types without relying on an App Group marker.
    BOOL hasPEClient = FlekDeckPrepareROMRuntime();
    void (*resecureDecoder)(void) = hasPEClient
        ? (void (*)(void))dlsym(flekDeckROMRuntimeHandle, "ResecureDecoder") : NULL;
    if (resecureDecoder) {
        resecureDecoder();
    } else {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wundeclared-selector"
    method_setImplementation(class_getInstanceMethod(NSClassFromString(@"NSXPCDecoder"), @selector(_validateAllowedClass:forKey:allowingInvocations:)), (IMP)hook_do_nothing);
#pragma clang diagnostic pop
    }
    // Register Nyxian's one-shot UIApplicationMain resolution hook.
    // Do not alter dlopen/RTLD_MAIN_ONLY or run ROM process setup yet.
    if (!performHookDyldApi("dlsym", 2,
                            (void **)&orig_extension_dlsym, hook_extension_dlsym)) {
        NSLog(@"FlekDeck LiveProcess: could not install upstream-style extension entry hook");
        return ENOTSUP;
    }
    // call the real one
    _envp = envp;
    _apple = apple;
    int (*orig_NSExtensionMain)(int argc, char * argv[]) = dlsym(RTLD_NEXT, "NSExtensionMain");
    return orig_NSExtensionMain(argc, argv);
}

