#!/usr/bin/env python3
from pathlib import Path

# Compatibility Mode uses private SpringBoard launch metadata. Current upstream
# still asserts inside its offline probe. On iOS 27+ that is too risky: an ABI
# drift can terminate the whole FlekDeck process before Objective-C exceptions
# can be caught. Keep the upstream-style probe on older systems, but use the
# stable Classic launch values directly on iOS 27+.
probe = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m")
s = probe.read_text()
anchor = '''        NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;\n        NSURL *executableURL = bundle.executableURL;\n        if (!bundle || !executableURL) return @0;\n'''
insert = '''        NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;\n        NSURL *executableURL = bundle.executableURL;\n        if (!bundle || !executableURL) return @0;\n\n        if (@available(iOS 27.0, *)) {\n            // Avoid instantiating private SBApplication/SBApplicationInfo on iOS\n            // 27+. The private object graph can abort the host on ABI drift. The\n            // launch option itself remains supported by the guarded LS workspace\n            // path: 1 is the phone Classic mode, 12 is the iPad Classic mode.\n            NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];\n            BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] &&\n                                    [families containsObject:@2];\n            NSUInteger mode = (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad &&\n                               guestSupportsPad) ? 12 : 1;\n            NSLog(@"[FlekDeck/ClassicMode] iOS 27+ safe mode=%lu for %@",\n                  (unsigned long)mode, bundle.bundleIdentifier ?: bundle.bundleURL.lastPathComponent);\n            return @(mode);\n        }\n'''
if insert not in s:
    if anchor not in s:
        raise SystemExit(f"{probe}: Classic probe bundle anchor missing")
    s = s.replace(anchor, insert, 1)
probe.write_text(s)

shared = Path("LiveContainer/LCSharedUtils.m")
s = shared.read_text()
old = '''    configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };\n    @try {\n        [workspace openApplicationWithBundleIdentifier:bundleIdentifier'''
new = '''    @try {\n        configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };\n        [workspace openApplicationWithBundleIdentifier:bundleIdentifier'''
if new not in s:
    if old not in s:
        raise SystemExit(f"{shared}: Classic launch configuration anchor missing")
    s = s.replace(old, new, 1)
shared.write_text(s)

# Invariants.
probe_text = probe.read_text()
if 'if (@available(iOS 27.0, *)) {' not in probe_text:
    raise SystemExit("iOS 27 Compatibility safe path missing")
if 'return @(mode);' not in probe_text:
    raise SystemExit("iOS 27 Compatibility safe mode result missing")
shared_text = shared.read_text()
region = shared_text[shared_text.find("+ (BOOL)launchToGuestAppWithClassicMode"):shared_text.find("+ (BOOL)launchToGuestAppWithURL")]
if region.find("@try {") > region.find("configuration.frontBoardOptions"):
    raise SystemExit("Classic frontBoardOptions assignment is still outside exception guard")

print("FlekDeck Compatibility Mode hardened for iOS 27+ without touching App Switcher routing")
