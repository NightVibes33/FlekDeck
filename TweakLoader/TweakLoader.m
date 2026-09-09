#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#include <dlfcn.h>
#include <objc/runtime.h>
#include "utils.h"

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

static void loadTweaksRecursively(NSURL *folderURL, NSMutableArray *errors) {
    NSArray<NSURL *> *items = [NSFileManager.defaultManager contentsOfDirectoryAtURL:folderURL includingPropertiesForKeys:@[NSURLIsDirectoryKey] options:0 error:nil];
    for (NSURL *fileURL in items) {
        NSString *name = fileURL.lastPathComponent;
        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled tweak %@", name);
            continue;
        }
        NSNumber *isDirectory = nil;
        [fileURL getResourceValue:&isDirectory forKey:NSURLIsDirectoryKey error:nil];
        // a .framework is a directory but loads as a single tweak
        if (isDirectory.boolValue && ![name hasSuffix:@".framework"]) {
            loadTweaksRecursively(fileURL, errors);
        } else {
            NSString *error = loadTweakAtURL(fileURL);
            if (error) {
                [errors addObject:error];
            }
        }
    }
}

static void showDlerrAlert(NSString *error) {
    UIWindow *window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Failed to load tweaks" message:error preferredStyle:UIAlertControllerStyleAlert];
    UIAlertAction* okAction = [UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:^(UIAlertAction * action) {
        window.windowScene = nil;
    }];
    [alert addAction:okAction];
    UIAlertAction* cancelAction = [UIAlertAction actionWithTitle:@"Copy" style:UIAlertActionStyleCancel handler:^(UIAlertAction * action) {
        UIPasteboard.generalPasteboard.string = error;
        window.windowScene = nil;
    }];
    [alert addAction:cancelAction];
    window.rootViewController = [UIViewController new];
    window.windowLevel = 1000;
    window.windowScene = (id)UIApplication.sharedApplication.connectedScenes.anyObject;
    [window makeKeyAndVisible];
    [window.rootViewController presentViewController:alert animated:YES completion:nil];
    objc_setAssociatedObject(alert, @"window", window, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

static NSString *FlekGuestBundleIdentifier(void) {
    NSString *bundleIdentifier = NSUserDefaults.guestAppInfo[@"CFBundleIdentifier"];
    if (![bundleIdentifier isKindOfClass:NSString.class] || bundleIdentifier.length == 0) {
        bundleIdentifier = NSBundle.mainBundle.bundleIdentifier;
    }
    if (![bundleIdentifier isKindOfClass:NSString.class] || bundleIdentifier.length == 0) {
        bundleIdentifier = @"unknown";
    }
    NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"];
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
        // don't load any tweak since tweakloader is loaded after all initializers
        NSLog(@"Skip loading tweaks");
        return;
    }
    
    NSMutableArray *errors = [NSMutableArray new];
    NSURL *globalFolderURL = [NSURL fileURLWithPath:globalTweakFolder];
    NSArray<NSURL *> *globalTweaks = [NSFileManager.defaultManager contentsOfDirectoryAtURL:globalFolderURL
    includingPropertiesForKeys:@[] options:0 error:nil] ?: @[];
    NSString *tweakFolderName = NSUserDefaults.guestAppInfo[@"LCTweakFolder"];
    NSString *bundleIdentifier = FlekGuestBundleIdentifier();

    // Vibe-style per-app scope is represented as an additive TweakLoader overlay.
    // It does not replace or rewrite the existing LCTweakFolder profile.
    NSURL *perAppFolder = [[[globalFolderURL URLByAppendingPathComponent:@"__FlekPerApp" isDirectory:YES]
                            URLByAppendingPathComponent:bundleIdentifier isDirectory:YES] standardizedURL];
    NSURL *blockedFolder = [[[globalFolderURL URLByAppendingPathComponent:@"__FlekBlocked" isDirectory:YES]
                             URLByAppendingPathComponent:bundleIdentifier isDirectory:YES] standardizedURL];
    NSArray<NSURL *> *blockedURLs = [NSFileManager.defaultManager contentsOfDirectoryAtURL:blockedFolder
        includingPropertiesForKeys:@[] options:0 error:nil] ?: @[];
    NSMutableSet<NSString *> *blockedNames = [NSMutableSet new];
    for (NSURL *url in blockedURLs) [blockedNames addObject:url.lastPathComponent];

    // Load CydiaSubstrate
    const char *lcMainBundlePath;
    if(NSUserDefaults.isLiveProcess) {
        lcMainBundlePath = NSUserDefaults.lcMainBundle.bundlePath.stringByDeletingLastPathComponent.stringByDeletingLastPathComponent.fileSystemRepresentation;
    } else {
        lcMainBundlePath = NSUserDefaults.lcMainBundle.bundlePath.fileSystemRepresentation;
    }
    char substratePath[PATH_MAX];
    snprintf(substratePath, sizeof(substratePath), "%s/Frameworks/CydiaSubstrate.framework/CydiaSubstrate", lcMainBundlePath);
    dlopen(substratePath, RTLD_LAZY | RTLD_GLOBAL);
    const char *substrateError = dlerror();
    if (substrateError) {
        [errors addObject:@(substrateError)];
    }

    // Root-level tweaks are FlekDeck's existing global scope. Reserved Vibe
    // management directories are data only and are never treated as tweaks.
    NSLog(@"Loading tweaks from the global folder");
    NSSet<NSString *> *reserved = [NSSet setWithArray:@[@"__FlekLibrary", @"__FlekPerApp", @"__FlekBlocked"]];
    for (NSURL *fileURL in globalTweaks) {
        NSString *name = fileURL.lastPathComponent;
        if ([name isEqualToString:@"TweakLoader.dylib"] || [reserved containsObject:name]) {
            continue;
        }
        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled global tweak %@", name);
            continue;
        }
        if ([blockedNames containsObject:name]) {
            NSLog(@"Skipping globally-scoped tweak %@ for %@ (Vibe per-app block)", name, bundleIdentifier);
            continue;
        }
        NSString *error = loadTweakAtURL(fileURL);
        if (error) {
            [errors addObject:error];
        }
    }

    // Load the user's existing named tweak folder recursively, unchanged.
    if (tweakFolderName.length > 0) {
        NSLog(@"Loading tweaks from the selected folder");
        NSString *tweakFolder = [globalTweakFolder stringByAppendingPathComponent:tweakFolderName];
        loadTweaksRecursively([NSURL fileURLWithPath:tweakFolder], errors);
    }

    // Then load Vibe-style per-app selections. These are symlink overlays into
    // __FlekLibrary and therefore use the exact same dlopen/TweakLoader path.
    BOOL perAppIsDirectory = NO;
    if ([NSFileManager.defaultManager fileExistsAtPath:perAppFolder.path isDirectory:&perAppIsDirectory] && perAppIsDirectory) {
        NSLog(@"Loading Vibe per-app tweak overlay for %@", bundleIdentifier);
        loadTweaksRecursively(perAppFolder, errors);
    }

    if (errors.count > 0) {
        dispatch_async(dispatch_get_main_queue(), ^{
            NSString *error = [errors componentsJoinedByString:@"\n"];
            showDlerrAlert(error);
        });
    }
}
