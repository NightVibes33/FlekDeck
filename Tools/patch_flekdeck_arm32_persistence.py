#!/usr/bin/env python3
from pathlib import Path

app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
text = app_info.read_text()
old = '''- (void)setSelected32BitEmulator:(NSString *)selected32BitEmulator {
    if(selected32BitEmulator.length > 0) {
        _info[@"selected32BitEmulator"] = selected32BitEmulator;
    } else {
        [_info removeObjectForKey:@"selected32BitEmulator"];
    }
    [self save];
}'''
new = '''- (void)setSelected32BitEmulator:(NSString *)selected32BitEmulator {
    if(selected32BitEmulator.length > 0) {
        _info[@"selected32BitEmulator"] = selected32BitEmulator;
    } else {
        [_info removeObjectForKey:@"selected32BitEmulator"];
    }
    if (!_autoSaveDisabled) [self save];
}'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_info}: selected32BitEmulator setter anchor missing")
    text = text.replace(old, new, 1)
app_info.write_text(text)

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
anchor = '''            finalNewApp.jitLaunchScriptJs = appToReplace.appInfo.jitLaunchScriptJs
            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified
            finalNewApp.classicMode = appToReplace.appInfo.classicMode
'''
replacement = '''            finalNewApp.jitLaunchScriptJs = appToReplace.appInfo.jitLaunchScriptJs
            finalNewApp.multitaskSpecified = appToReplace.appInfo.multitaskSpecified
#if is32BitSupported
            // Preserve an app-specific translation runtime across IPA updates.
            // The new executable is reclassified during patch/sign; only the
            // user's runtime override belongs to the old app configuration.
            finalNewApp.selected32BitEmulator = appToReplace.appInfo.selected32BitEmulator
#endif
            finalNewApp.classicMode = appToReplace.appInfo.classicMode
'''
if replacement not in text:
    if anchor not in text:
        raise SystemExit(f"{app_list}: app replacement preference-copy anchor missing")
    text = text.replace(anchor, replacement, 1)
app_list.write_text(text)

if "if (!_autoSaveDisabled) [self save];" not in app_info.read_text():
    raise SystemExit("selected32BitEmulator still ignores bulk-save mode")
if "finalNewApp.selected32BitEmulator = appToReplace.appInfo.selected32BitEmulator" not in app_list.read_text():
    raise SystemExit("per-app ARM32 runtime override is not preserved across replacement")

print("FlekDeck preserves per-app ARM32 runtime overrides across app replacement")
