#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#include <dlfcn.h>
#include <objc/runtime.h>
#include "utils.h"

static NSURL *FlekCanonicalScopedURL(NSURL *globalRoot, NSURL *candidate) {
    // Vibe-style global/per-app entries are symlink projections of the
    // canonical __FlekLibrary item. A parallel LiveProcess receives a cloned
    // Tweaks tree, and an absolute symlink copied from the host may still point
    // at the host Documents container. Resolve by *name* inside the staged root
    // instead, so the exact same scope tree works in single and parallel launch.
    NSNumber *isSymlink = nil;
    [candidate getResourceValue:&isSymlink forKey:NSURLIsSymbolicLinkKey error:nil];
    if (!isSymlink.boolValue) return candidate;

    NSURL *libraryItem = [[globalRoot URLByAppendingPathComponent:@"__FlekLibrary" isDirectory:YES]
                          URLByAppendingPathComponent:candidate.lastPathComponent];
    if ([NSFileManager.defaultManager fileExistsAtPath:libraryItem.path]) {
        return libraryItem;
    }
    return candidate;
}

static NSString *loadTweakAtURL(NSURL *url) {
    NSString *tweakPath = url.path;
    NSString *tweak = tweakPath.lastPathComponent;
    if (![tweakPath hasSuffix:@".dylib"] && ![tweakPath hasSuffix:@".framework"]) {
        return nil;
    }
    if ([tweakPath hasSuffix:@".framework"]) {
        NSURL* infoPlistURL = [url URLByAppendingPathComponent:@"Info.plist"];
        NSDictionary* infoDict = [NSDictionary dictionaryWithContentsOfURL:infoPlistURL];
        NSString* binary = infoDict[@"CFBundleExecutable"];
        if(!binary || ![binary isKindOfClass:NSString.class]) {
            return [NSString stringWithFormat:@"Unable to load %@: Unable to read Info.Plist", tweak];
        }
        tweakPath = [[url URLByAppendingPathComponent:binary] path];
    }

    dlerror();
    void *handle = dlopen(tweakPath.UTF8String, RTLD_LAZY | RTLD_GLOBAL);
    const char *error = dlerror();
    if (handle) {
        NSLog(@"Loaded tweak %@", tweak);
        return nil;
    } else if (error) {
        NSLog(@"Error: %s", error);
        return @(error);
    } else {
        NSLog(@"Error: dlopen(%@): Unknown error because dlerror() returns NULL", tweak);
        return [NSString stringWithFormat:@"dlopen(%@): unknown error, handle is NULL", tweakPath];
    }
}

static void loadTweaksRecursively(NSURL *folderURL, NSURL *globalRoot, NSMutableArray *errors, NSSet<NSString *> *blockedNames) {
    NSArray<NSURL *> *items = [NSFileManager.defaultManager contentsOfDirectoryAtURL:folderURL
        includingPropertiesForKeys:@[NSURLIsDirectoryKey, NSURLIsSymbolicLinkKey]
        options:0 error:nil] ?: @[];
    for (NSURL *rawURL in items) {
        NSString *name = rawURL.lastPathComponent;
        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled tweak %@", name);
            continue;
        }
        if ([blockedNames containsObject:name]) {
            NSLog(@"Skipping blocked tweak %@", name);
            continue;
        }

        NSURL *fileURL = FlekCanonicalScopedURL(globalRoot, rawURL);
        NSNumber *isDirectory = nil;
        [fileURL getResourceValue:&isDirectory forKey:NSURLIsDirectoryKey error:nil];
        // A .framework is a directory but loads as one tweak.
        if (isDirectory.boolValue && ![name hasSuffix:@".framework"] && ![fileURL.path hasSuffix:@".framework"]) {
            loadTweaksRecursively(fileURL, globalRoot, errors, blockedNames);
        } else {
            NSString *error = loadTweakAtURL(fileURL);
            if (error) [errors addObject:error];
        }
    }
}

static void showDlerrAlert(NSString *error) {
    UIWindow *window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Failed to load tweaks"
                                                                   message:error
                                                            preferredStyle:UIAlertControllerStyleAlert];
    UIAlertAction* okAction = [UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:^(UIAlertAction * action) {
        window.windowScene = nil;
    }];
    [alert addAction:okAction];
    UIAlertAction* copyAction = [UIAlertAction actionWithTitle:@"Copy" style:UIAlertActionStyleCancel handler:^(UIAlertAction * action) {
        UIPasteboard.generalPasteboard.string = error;
        window.windowScene = nil;
    }];
    [alert addAction:copyAction];
    window.rootViewController = [UIViewController new];
    window.windowLevel = 1000;
    window.windowScene = (id)UIApplication.sharedApplication.connectedScenes.anyObject;
    [window makeKeyAndVisible];
    [window.rootViewController presentViewController:alert animated:YES completion:nil];
    objc_setAssociatedObject(alert, @"window", window, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

static NSString *FlekGuestBundleIdentifier(void) {
    // This is the identifier LCBootstrap already resolved for the guest (and is
    // the same identifier FlekTweakStore uses as its per-app directory key).
    NSString *bundleIdentifier = NSUserDefaults.lcGuestAppId;
    if (![bundleIdentifier isKindOfClass:NSString.class] || bundleIdentifier.length == 0) {
        bundleIdentifier = NSUserDefaults.guestAppInfo[@"LCOrignalBundleIdentifier"];
    }
    if (![bundleIdentifier isKindOfClass:NSString.class] || bundleIdentifier.length == 0) {
        bundleIdentifier = NSBundle.mainBundle.bundleIdentifier;
    }
    if (![bundleIdentifier isKindOfClass:NSString.class] || bundleIdentifier.length == 0) {
        bundleIdentifier = @"unknown";
    }

    NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:
        @"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"];
    NSMutableString *safe = [NSMutableString new];
    for (NSUInteger i = 0; i < bundleIdentifier.length; i++) {
        unichar c = [bundleIdentifier characterAtIndex:i];
        if ([allowed characterIsMember:c]) [safe appendFormat:@"%C", c];
        else [safe appendString:@"_"];
    }
    return safe;
}

__attribute__((constructor))
static void TweakLoaderConstructor() {
    const char *tweakFolderC = getenv("LC_GLOBAL_TWEAKS_FOLDER");
    if (!tweakFolderC) return;
    NSString *globalTweakFolder = @(tweakFolderC);
    unsetenv("LC_GLOBAL_TWEAKS_FOLDER");

    if([NSUserDefaults.guestAppInfo[@"dontInjectTweakLoader"] boolValue]) {
        NSLog(@"Skip loading tweaks");
        return;
    }

    NSMutableArray *errors = [NSMutableArray new];
    NSURL *globalFolderURL = [NSURL fileURLWithPath:globalTweakFolder isDirectory:YES];
    NSArray<NSURL *> *globalTweaks = [NSFileManager.defaultManager contentsOfDirectoryAtURL:globalFolderURL
        includingPropertiesForKeys:@[NSURLIsSymbolicLinkKey] options:0 error:nil] ?: @[];
    NSString *tweakFolderName = NSUserDefaults.guestAppInfo[@"LCTweakFolder"];
    NSString *bundleIdentifier = FlekGuestBundleIdentifier();

    // Vibe-style per-app scope is additive. It never replaces the existing
    // LCTweakFolder profile selected in FlekDeck app settings.
    NSURL *perAppFolder = [[[globalFolderURL URLByAppendingPathComponent:@"__FlekPerApp" isDirectory:YES]
                            URLByAppendingPathComponent:bundleIdentifier isDirectory:YES] standardizedURL];
    NSURL *blockedFolder = [[[globalFolderURL URLByAppendingPathComponent:@"__FlekBlocked" isDirectory:YES]
                             URLByAppendingPathComponent:bundleIdentifier isDirectory:YES] standardizedURL];
    NSArray<NSURL *> *blockedURLs = [NSFileManager.defaultManager contentsOfDirectoryAtURL:blockedFolder
        includingPropertiesForKeys:@[] options:0 error:nil] ?: @[];
    NSMutableSet<NSString *> *blockedNames = [NSMutableSet new];
    for (NSURL *url in blockedURLs) [blockedNames addObject:url.lastPathComponent];

    // Load CydiaSubstrate exactly as FlekDeck did before this port.
    const char *lcMainBundlePath;
    if(NSUserDefaults.isLiveProcess) {
        lcMainBundlePath = NSUserDefaults.lcMainBundle.bundlePath.stringByDeletingLastPathComponent.stringByDeletingLastPathComponent.fileSystemRepresentation;
    } else {
        lcMainBundlePath = NSUserDefaults.lcMainBundle.bundlePath.fileSystemRepresentation;
    }
    char substratePath[PATH_MAX];
    snprintf(substratePath, sizeof(substratePath), "%s/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", lcMainBundlePath);
    dlerror();
    dlopen(substratePath, RTLD_LAZY | RTLD_GLOBAL);
    const char *substrateError = dlerror();
    if (substrateError) [errors addObject:@(substrateError)];

    // Root-level dylibs/frameworks are FlekDeck's existing global scope. The
    // three reserved management directories are state only, never global tweaks.
    NSLog(@"Loading tweaks from the global folder");
    NSSet<NSString *> *reserved = [NSSet setWithArray:@[
        @"__FlekLibrary", @"__FlekPerApp", @"__FlekBlocked"
    ]];
    for (NSURL *rawURL in globalTweaks) {
        NSString *name = rawURL.lastPathComponent;
        if ([name isEqualToString:@"TweakLoader.dylib"] || [reserved containsObject:name]) continue;
        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled global tweak %@", name);
            continue;
        }
        if ([blockedNames containsObject:name]) {
            NSLog(@"Skipping global tweak %@ for %@ (per-app opt-out)", name, bundleIdentifier);
            continue;
        }

        NSURL *fileURL = FlekCanonicalScopedURL(globalFolderURL, rawURL);
        NSString *error = loadTweakAtURL(fileURL);
        if (error) [errors addObject:error];
    }

    // Existing named tweak profile — unchanged and still recursive.
    if (tweakFolderName.length > 0) {
        NSLog(@"Loading tweaks from the selected folder");
        NSURL *profile = [globalFolderURL URLByAppendingPathComponent:tweakFolderName isDirectory:YES];
        NSString *rootPath = globalFolderURL.standardizedURL.path;
        NSString *profilePath = profile.standardizedURL.path;
        // Defensive containment check: app metadata cannot escape Tweaks.
        if ([profilePath isEqualToString:rootPath] || [profilePath hasPrefix:[rootPath stringByAppendingString:@"/"]]) {
            loadTweaksRecursively(profile, globalFolderURL, errors, blockedNames);
        }
    }

    // Vibe-style per-app selections. Each projection resolves back to the
    // canonical __FlekLibrary copy inside *this* staged Tweaks tree.
    BOOL perAppIsDirectory = NO;
    if ([NSFileManager.defaultManager fileExistsAtPath:perAppFolder.path isDirectory:&perAppIsDirectory] && perAppIsDirectory) {
        NSLog(@"Loading Vibe per-app tweak overlay for %@", bundleIdentifier);
        loadTweaksRecursively(perAppFolder, globalFolderURL, errors, blockedNames);
    }

    if (errors.count > 0) {
        dispatch_async(dispatch_get_main_queue(), ^{
            showDlerrAlert([errors componentsJoinedByString:@"\n"]);
        });
    }
}
