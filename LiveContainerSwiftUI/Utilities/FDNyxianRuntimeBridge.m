#import "FDNyxianRuntimeBridge.h"

#import <dlfcn.h>
#import <objc/message.h>
#import <objc/runtime.h>

static NSString *const FDNyxianErrorDomain = @"com.fs.flekdeck.nyxian-runtime";

typedef BOOL (*FDNyxianEntitlementCheck)(void);

@implementation FDNyxianRuntimeBridge

+ (instancetype)shared {
    static FDNyxianRuntimeBridge *bridge;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ bridge = [FDNyxianRuntimeBridge new]; });
    return bridge;
}

- (NSBundle *)processExtensionBundle {
    NSString *plugins = NSBundle.mainBundle.builtInPlugInsPath;
    return plugins.length == 0 ? nil : [NSBundle bundleWithPath:[plugins stringByAppendingPathComponent:@"NyxianProcess.appex"]];
}

- (FDNyxianRuntimeState)state {
    if (NSClassFromString(@"PEUserspaceManager") == Nil ||
        NSClassFromString(@"LDEApplicationWorkspace") == Nil ||
        NSClassFromString(@"PEProcessManager") == Nil) {
        return FDNyxianRuntimeStateUnavailable;
    }
    if ([self processExtensionBundle] == nil) {
        return FDNyxianRuntimeStateMissingExtension;
    }
    FDNyxianEntitlementCheck check = (FDNyxianEntitlementCheck)dlsym(RTLD_DEFAULT, "PEExtensionHasGetTaskAllowed");
    if (check == NULL || !check()) {
        return FDNyxianRuntimeStateMissingEntitlement;
    }
    return FDNyxianRuntimeStateReady;
}

- (NSString *)diagnosticMessage {
    switch (self.state) {
        case FDNyxianRuntimeStateUnavailable:
            return @"The Nyxian host runtime is not embedded in this build.";
        case FDNyxianRuntimeStateMissingExtension:
            return @"NyxianProcess.appex is not embedded in the host application.";
        case FDNyxianRuntimeStateMissingEntitlement:
            return @"NyxianProcess is missing the development get-task-allow entitlement required by the userspace runtime.";
        case FDNyxianRuntimeStateReady:
            return @"Nyxian userspace runtime and process extension are available.";
    }
}

- (NSError *)errorWithCode:(NSInteger)code message:(NSString *)message {
    return [NSError errorWithDomain:FDNyxianErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: message}];
}

- (void)launchApplicationAtBundlePath:(NSString *)bundlePath
                     bundleIdentifier:(NSString *)bundleIdentifier
                           completion:(void (^)(NSError * _Nullable))completion {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        FDNyxianRuntimeState state = self.state;
        if (state != FDNyxianRuntimeStateReady) {
            dispatch_async(dispatch_get_main_queue(), ^{ completion([self errorWithCode:state message:self.diagnosticMessage]); });
            return;
        }

        Class userspaceClass = NSClassFromString(@"PEUserspaceManager");
        id userspace = ((id (*)(id, SEL))objc_msgSend)(userspaceClass, sel_registerName("shared"));
        BOOL booted = ((BOOL (*)(id, SEL))objc_msgSend)(userspace, sel_registerName("isBooted"));
        if (!booted) {
            ((void (*)(id, SEL, BOOL))objc_msgSend)(userspace, sel_registerName("bootWithKextLoadingEnabled:"), YES);
            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:120.0];
            do {
                booted = ((BOOL (*)(id, SEL))objc_msgSend)(userspace, sel_registerName("isBooted"));
                if (!booted) [NSThread sleepForTimeInterval:0.1];
            } while (!booted && deadline.timeIntervalSinceNow > 0);
        }
        if (!booted) {
            dispatch_async(dispatch_get_main_queue(), ^{ completion([self errorWithCode:10 message:@"Nyxian userspace did not become ready within 120 seconds."]); });
            return;
        }

        Class workspaceClass = NSClassFromString(@"LDEApplicationWorkspace");
        id workspace = ((id (*)(id, SEL))objc_msgSend)(workspaceClass, sel_registerName("shared"));
        BOOL installed = ((BOOL (*)(id, SEL, id))objc_msgSend)(workspace, sel_registerName("installApplicationAtBundlePath:"), bundlePath);
        if (!installed) {
            dispatch_async(dispatch_get_main_queue(), ^{ completion([self errorWithCode:11 message:@"Nyxian could not install the selected application into its application workspace."]); });
            return;
        }

        Class processClass = NSClassFromString(@"PEProcessManager");
        id processManager = ((id (*)(id, SEL))objc_msgSend)(processClass, sel_registerName("shared"));
        SEL spawn = sel_registerName("spawnProcessWithBundleIdentifier:withItems:withKernelSurfaceProcess:doRestartIfRunning:");
        pid_t pid = ((pid_t (*)(id, SEL, id, id, id, BOOL))objc_msgSend)(processManager, spawn, bundleIdentifier, @{}, nil, YES);
        NSError *error = pid > 0 ? nil : [self errorWithCode:12 message:@"Nyxian failed to spawn the selected application."];
        dispatch_async(dispatch_get_main_queue(), ^{ completion(error); });
    });
}

@end
