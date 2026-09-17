#!/usr/bin/env python3
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Home/App Switcher: preserve main's proven Springboard gesture ownership.
# Open Data Folder belongs in the app context menu; it must not require a new
# root long-press delegate that can interfere with the bottom-swipe switcher.
# ---------------------------------------------------------------------------
drag = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardDragManager.swift")
s = drag.read_text()
method_start = s.find("    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {")
if method_start >= 0:
    method_end = s.find("    func handleLongPress(_ gesture: UILongPressGestureRecognizer) {", method_start)
    if method_end < 0:
        raise SystemExit(f"{drag}: gesture arbitration block has no handleLongPress boundary")
    s = s[:method_start] + s[method_end:]
s = s.replace(
    "final class LCSpringboardDragManager: NSObject, UIGestureRecognizerDelegate {",
    "final class LCSpringboardDragManager {",
    1,
)
start = s.find("    /// Installed app holds belong to UICollectionView's context-menu recognizer.")
if start >= 0:
    end = s.find("    func handleLongPress(_ gesture: UILongPressGestureRecognizer) {", start)
    if end < 0:
        raise SystemExit(f"{drag}: context-menu delegate block has no end anchor")
    s = s[:start] + s[end:]
s = s.replace(
    '''            } else {
                // Installed app → the recognizer delegate should already have
                // rejected this drag so UIKit can present the context menu.
                return
            }''',
    '''            } else {
                // Installed app → let context menu handle it. This is main's
                // proven behavior and does not install another root delegate.
                gesture.isEnabled = false
                gesture.isEnabled = true
                return
            }''',
    1,
)
drag.write_text(s)

vc = Path("LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift")
s = vc.read_text()
s = s.replace("        longPressGesture.delegate = dragManager\n", "", 1)
s = s.replace(
    '''        // Installed-app holds must be rejected by the drag recognizer before
        // recognition so the inner UICollectionView context menu can own them.
        longPressGesture.delegate = dragManager
''',
    "",
    1,
)
vc.write_text(s)

# ---------------------------------------------------------------------------
# 2. Compatibility Mode: toggling it must be side-effect free, Parallel must
# never probe it, and the mode detector must not instantiate private SpringBoard
# objects that can abort the host on iOS 27. Generic classic modes are stable:
# phone=1; iPad-capable guest on iPad=12.
# ---------------------------------------------------------------------------
app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
s = app_info.read_text()
classic_start = s.find("- (bool)classicMode {")
classic_end = s.find("- (bool)isLocked {", classic_start)
if classic_start < 0 or classic_end < 0:
    raise SystemExit(f"{app_info}: Classic Mode model block markers missing")
classic_block = '''- (bool)classicMode {
    return [_info[@"classicMode"] boolValue];
}

- (void)setClassicMode:(bool)classicMode {
    // Flipping the UI setting must be side-effect free.
    _info[@"classicMode"] = @(classicMode);
    if(!classicMode) {
        [_info removeObjectForKey:@"LCClassicModeCache"];
    }
    [self save];
}

- (NSUInteger)defaultClassicMode {
    if(!self.classicMode) return 0;

    NSInteger systemMajorVersion = NSProcessInfo.processInfo.operatingSystemVersion.majorVersion;
    NSDictionary *cache = _info[@"LCClassicModeCache"];
    NSNumber *cachedMode = cache[@"defaultClassicMode"];
    NSNumber *cachedSystemMajorVersion = cache[@"systemMajorVersion"];
    if([cachedMode isKindOfClass:NSNumber.class] &&
       [cachedSystemMajorVersion isKindOfClass:NSNumber.class] &&
       cachedSystemMajorVersion.integerValue == systemMajorVersion) {
        return cachedMode.unsignedIntegerValue;
    }

    NSNumber *mode = LCGetDefaultClassicMode([NSURL fileURLWithPath:self.bundlePath]);
    if(![mode isKindOfClass:NSNumber.class]) mode = @0;
    _info[@"LCClassicModeCache"] = @{
        @"defaultClassicMode": mode,
        @"systemMajorVersion": @(systemMajorVersion),
    };
    [self save];
    return mode.unsignedIntegerValue;
}

'''
s = s[:classic_start] + classic_block + s[classic_end:]
app_info.write_text(s)

probe = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m")
probe.write_text('''#import <Foundation/Foundation.h>\n#import <UIKit/UIKit.h>\n#import "LCUtils.h"\n\n// Do not construct private SpringBoard application objects in the host process.\n// Those objects change between iOS releases and failure can abort below\n// Objective-C exception handling. Compatibility Mode is an optional launch\n// hint, so use stable generic modes instead: 1 = phone, 12 = iPad.\nNSNumber *LCGetDefaultClassicMode(NSURL *appURL) {\n    NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;\n    if(!bundle || !bundle.executableURL) {\n        return @0;\n    }\n\n    NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];\n    BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] && [families containsObject:@2];\n    if(UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad && guestSupportsPad) {\n        return @12;\n    }\n    return @1;\n}\n''')

app_model = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
s = app_model.read_text()
unsafe = '''        let classicMode = appInfo.defaultClassicMode
#if is32BitSupported
        // Preserve FlekDeck's App Switcher / Parallel routing for every native
        // ARM64 guest. Only ARM32 is forced onto the single-process LiveExec32
        // path; Classic Mode is consumed only if that single-process path wins.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif'''
safe = '''#if is32BitSupported
        // Main owns the App Switcher / Parallel decision. Compatibility Mode is
        // consumed only after that decision and can never force ARM64 out of it.
        let multitask = appInfo.is32bit ? false : (multitask ?? shouldLaunchInMultitaskMode)
#else
        let multitask = multitask ?? shouldLaunchInMultitaskMode
#endif
        let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode'''
if unsafe in s:
    s = s.replace(unsafe, safe, 1)
elif safe not in s and "let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode" not in s:
    raise SystemExit(f"{app_model}: launch-mode ordering anchor missing")
app_model.write_text(s)

shared = Path("LiveContainer/LCSharedUtils.m")
s = shared.read_text()
start = s.find("+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {")
end = s.find("+ (BOOL)launchToGuestAppWithURL:(NSURL *)url {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{shared}: Classic relaunch method markers missing")
classic_launch = '''+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {
    if(classicMode == 0) {
        return [self launchToGuestApp];
    }

    _LSOpenConfiguration *configuration = [[PrivClass(_LSOpenConfiguration) alloc] init];
    LSApplicationWorkspace *workspace = [PrivClass(LSApplicationWorkspace) defaultWorkspace];
    NSString *bundleIdentifier = lcMainBundle.bundleIdentifier ?: NSBundle.mainBundle.bundleIdentifier;
    if(!configuration || !workspace || bundleIdentifier.length == 0) {
        NSLog(@"[FlekDeck/ClassicMode] private launch surface unavailable; falling back to normal launch");
        return [self launchToGuestApp];
    }

    configuration.frontBoardOptions = @{ @"__ActivateAsClassic": @(classicMode) };
    @try {
        [workspace openApplicationWithBundleIdentifier:bundleIdentifier
                                         configuration:configuration
                                     completionHandler:^(BOOL success, NSError *error) {
            NSLog(@"[FlekDeck/ClassicMode] success=%d mode=%lu error=%@", success, (unsigned long)classicMode, error);
            if(success) {
                __asm__ __volatile__ (
                    "mov x0, #31\\n"
                    "mov x16, #26\\n"
                    "svc #0x80\\n"
                );
                raise(SIGKILL);
                return;
            }
            // Rejected Classic launch is not a host crash. Fall back to the
            // exact normal relaunch path and keep the real private error in log.
            dispatch_async(dispatch_get_main_queue(), ^{
                [self launchToGuestApp];
            });
        }];
        return YES;
    } @catch (NSException *exception) {
        NSLog(@"[FlekDeck/ClassicMode] launch exception %@: %@; falling back", exception.name, exception.reason);
        return [self launchToGuestApp];
    }
}

'''
s = s[:start] + classic_launch + s[end:]
shared.write_text(s)

# ---------------------------------------------------------------------------
# 3. Error authenticity: keep the earlier Bool contract that gives a REAL guest
# crash priority over host diagnostics, but never synthesize an error from a
# stale SigningInProgress flag or an empty backend value.
# ---------------------------------------------------------------------------
tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
s = tab.read_text()
start = s.find("    @discardableResult\n    func checkLastLaunchError() -> Bool {")
if start < 0:
    start = s.find("    func checkLastLaunchError() {")
end = s.find("    func checkTeamId() {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{tab}: startup error helper markers missing")
error_helpers = '''    @discardableResult
    func checkLastLaunchError() -> Bool {
        let defaults = UserDefaults.standard
        let signingWasInterrupted = defaults.bool(forKey: "SigningInProgress")
        defaults.removeObject(forKey: "SigningInProgress")

        guard let raw = defaults.string(forKey: "error") else {
            if signingWasInterrupted {
                print("[FlekDeck/Error] stale SigningInProgress with no backend diagnostic; not showing a synthetic app error")
            }
            return false
        }
        defaults.removeObject(forKey: "error")

        guard !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            print("[FlekDeck/Error] backend recorded an empty error; not showing a synthetic app error")
            return false
        }
        errorInfo = raw
        crashReportShow = true
        return true
    }

    func copyError() { UIPasteboard.general.string = errorInfo }


'''
s = s[:start] + error_helpers + s[end:]
s = s.replace("Text(displayErrorInfo(errorInfo))", "Text(errorInfo)")
s = s.replace("ShareLink(item: displayErrorInfo(errorInfo))", "ShareLink(item: errorInfo)")
tab.write_text(s)

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = app_list.read_text()
s = s.replace("Text(displayErrorInfo(errorInfo))", "Text(errorInfo)")
s = s.replace("UIPasteboard.general.string = displayErrorInfo(errorInfo)", "UIPasteboard.general.string = errorInfo")
helper_start = s.find("    func displayErrorInfo(_ value: String) -> String {")
if helper_start >= 0:
    helper_end = s.find("    func copyError()", helper_start)
    if helper_end < 0:
        raise SystemExit(f"{app_list}: displayErrorInfo has no copyError end anchor")
    s = s[:helper_start] + s[helper_end:]
app_list.write_text(s)

bootstrap = Path("LiveContainer/LCBootstrap.m")
s = bootstrap.read_text()
bookmark_start = s.find("                    bookmarkURL = [NSURL URLByResolvingBookmarkData:bookmarkData")
bookmark_end = s.find("                    [lcUserDefaults removeObjectForKey:@\"error\"];", bookmark_start)
if bookmark_start < 0 or bookmark_end < 0:
    raise SystemExit(f"{bootstrap}: bookmark resolution block missing")
bookmark_end += len('                    [lcUserDefaults removeObjectForKey:@"error"];')
bookmark = '''                    bookmarkURL = [NSURL URLByResolvingBookmarkData:bookmarkData options:0 relativeToURL:nil bookmarkDataIsStale:&isStale error:&err];
                    if(!bookmarkURL) {
                        NSString *detail = err.localizedDescription;
                        return detail.length > 0
                            ? [NSString stringWithFormat:@"Bookmark resolution failed: %@", detail]
                            : @"Bookmark resolution failed without an NSError.";
                    }
                    bool access = [bookmarkURL startAccessingSecurityScopedResource];
                    if(!access) {
                        return [NSString stringWithFormat:@"Security-scoped access denied for data container: %@",
                                bookmarkURL.path ?: @"(unknown path)"];
                    }
                    [lcUserDefaults removeObjectForKey:@"error"];'''
s = s[:bookmark_start] + bookmark + s[bookmark_end:]
bootstrap.write_text(s)

# Final invariants for the reported regressions.
if "longPressGesture.delegate = dragManager" in vc.read_text():
    raise SystemExit("Home root long-press delegate regression remains")
if "gestureRecognizerShouldBegin" in drag.read_text():
    raise SystemExit("Springboard drag manager still owns root recognizer arbitration")
if "No diagnostic text was provided" in tab.read_text() or "No diagnostic text was provided" in app_list.read_text():
    raise SystemExit("Synthetic generic error UI remains")
if 'errorStr = "lc.signer.crashDuringSignErr"' in tab.read_text():
    raise SystemExit("Stale signing marker still fabricates an app error")
if "let presentedGuestCrash = checkLastLaunchError()" not in tab.read_text():
    raise SystemExit("Real guest errors no longer suppress host diagnostics during startup")
probe_value = probe.read_text()
if "NSCAssert(" in probe_value or "assert(" in probe_value:
    raise SystemExit("Compatibility probe still contains process-fatal assertions")
if "PrivClass(SBApplication" in probe_value or 'NSClassFromString(@"SBApplication' in probe_value or "SpringBoard.framework" in probe_value:
    raise SystemExit("Compatibility probe still constructs private SpringBoard objects")
if "let classicMode: UInt = multitask ? 0 : appInfo.defaultClassicMode" not in app_model.read_text():
    raise SystemExit("Compatibility Mode still probes before final launch routing")
classic_text = shared.read_text()
classic_region = classic_text[classic_text.find("+ (BOOL)launchToGuestAppWithClassicMode"):classic_text.find("+ (BOOL)launchToGuestAppWithURL")]
if "if(success)" not in classic_region or "falling back" not in classic_region:
    raise SystemExit("Classic relaunch is not fail-safe")
if "The security-scoped resource denied access." in bootstrap.read_text():
    raise SystemExit("Generic external-container error fallback remains")

print("FlekDeck user regressions repaired: main Home gestures, crash-safe Compatibility Mode, real backend errors")
