#!/usr/bin/env python3
from pathlib import Path
import runpy

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()

# UIKit Springboard context-menu container picker.
old = '''                ) { _ in
                    app.uiSelectedContainer = container
                    LCSpringboardPageCell.refreshActiveContextMenu()
                }'''
new = '''                ) { _ in
                    app.uiSelectedContainer = container
                    app.uiDefaultDataFolder = container.folderName
                    app.appInfo.dataUUID = container.folderName
                    LCSpringboardPageCell.refreshActiveContextMenu()
                }'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: UIKit quick-container action anchor missing")
    text = text.replace(old, new, 1)

# SwiftUI/list context-menu container picker.
old = '''                    Button {
                        app.uiSelectedContainer = container
                    } label: {'''
new = '''                    Button {
                        app.uiSelectedContainer = container
                        app.uiDefaultDataFolder = container.folderName
                        app.appInfo.dataUUID = container.folderName
                    } label: {'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: SwiftUI quick-container action anchor missing")
    text = text.replace(old, new, 1)

app_list.write_text(text)

final = app_list.read_text()
if final.count("app.appInfo.dataUUID = container.folderName") < 2:
    raise SystemExit("Quick-container selection is not persisted in both menu implementations")
if final.count("app.uiDefaultDataFolder = container.folderName") < 2:
    raise SystemExit("Quick-container UI default is not synchronized in both menu implementations")

# Keep app-specific ARM32 runtime choices across IPA replacement too. Running
# this from the final context/runtime adapter ensures older parity generators
# cannot silently drop that preference after this script has normalized menus.
runpy.run_path("Tools/patch_flekdeck_arm32_persistence.py", run_name="__main__")

# Compatibility Mode deep-link launches used to consume only the cached classic
# mode. The crash-safe toggle intentionally no longer probes private SpringBoard
# state, so a freshly enabled setting had no cache and silently launched as mode
# 0. Resolve the same generic safe mode here when the cache is absent.
shared = Path("LiveContainer/LCSharedUtils.m")
s = shared.read_text()
old_classic_lookup = '''        NSUInteger classicMode = [appInfo[@"classicMode"] boolValue]
            ? [appInfo[@"LCClassicModeCache"][@"defaultClassicMode"] unsignedIntegerValue]
            : 0;'''
new_classic_lookup = '''        NSUInteger classicMode = 0;
        if([appInfo[@"classicMode"] boolValue]) {
            NSNumber *cachedClassicMode = appInfo[@"LCClassicModeCache"][@"defaultClassicMode"];
            if([cachedClassicMode isKindOfClass:NSNumber.class] && cachedClassicMode.unsignedIntegerValue > 0) {
                classicMode = cachedClassicMode.unsignedIntegerValue;
            } else {
                NSArray *families = appBundle.infoDictionary[@"UIDeviceFamily"];
                BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] && [families containsObject:@2];
                classicMode = (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad && guestSupportsPad) ? 12 : 1;
            }
        }'''
if new_classic_lookup not in s:
    if old_classic_lookup not in s:
        raise SystemExit(f"{shared}: Compatibility deep-link cache lookup anchor missing")
    s = s.replace(old_classic_lookup, new_classic_lookup, 1)

# Guard private relaunch selectors before sending them. A renamed/removed private
# selector must fall back to the normal relaunch path, never terminate FlekDeck.
old_surface_guard = '''    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];
    NSString *bundleIdentifier = lcMainBundle.bundleIdentifier ?: NSBundle.mainBundle.bundleIdentifier;
    if(!configuration || !workspace || bundleIdentifier.length == 0) {
        NSLog(@"[FlekDeck/ClassicMode] private launch surface unavailable; falling back to normal launch");
        return [self launchToGuestApp];
    }

    configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };'''
new_surface_guard = '''    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];
    NSString *bundleIdentifier = lcMainBundle.bundleIdentifier ?: NSBundle.mainBundle.bundleIdentifier;
    SEL openSelector = @selector(openApplicationWithBundleIdentifier:configuration:completionHandler:);
    SEL optionsSelector = @selector(setFrontBoardOptions:);
    if(!configuration || !workspace || bundleIdentifier.length == 0 ||
       ![workspace respondsToSelector:openSelector] || ![configuration respondsToSelector:optionsSelector]) {
        NSLog(@"[FlekDeck/ClassicMode] private launch surface unavailable; falling back to normal launch");
        return [self launchToGuestApp];
    }

    configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };'''
if new_surface_guard not in s:
    if old_surface_guard not in s:
        raise SystemExit(f"{shared}: Compatibility private-surface guard anchor missing")
    s = s.replace(old_surface_guard, new_surface_guard, 1)

shared.write_text(s)
shared_final = shared.read_text()
if "cachedClassicMode" not in shared_final or "guestSupportsPad" not in shared_final:
    raise SystemExit("Compatibility deep-link launch still depends on a precomputed cache")
if "respondsToSelector:openSelector" not in shared_final or "respondsToSelector:optionsSelector" not in shared_final:
    raise SystemExit("Compatibility private launch selectors are not guarded")

print("FlekDeck Home container/runtime state and Compatibility deep-link launch are synchronized and guarded")