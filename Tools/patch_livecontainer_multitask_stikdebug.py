from pathlib import Path

# Temp-branch-only compatibility layer based on Duy Tran's current LiveContainer
# multitask boundary plus StikDebug's current URL contract. Normal single-app
# launch/signing is intentionally left untouched.

# ---------------------------------------------------------------------------
# 1) Run Parallel: use LiveContainer's security-scoped bookmark handoff for
# private guests instead of cloning the executable into the app group.
# ---------------------------------------------------------------------------
p = Path("MultitaskSupport/AppSceneViewController.m")
s = p.read_text()

resource_start_marker = '''    NSURL *docURL = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].lastObject;\n'''
resource_end_marker = '''    item.userInfo = userInfo;\n'''
start = s.index(resource_start_marker)
end = s.index(resource_end_marker, start)

resource_block = r'''    NSURL *docURL = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].lastObject;
    if ([NSUserDefaults.standardUserDefaults boolForKey:@"LCSharePrivateDataWithLiveProcess"]) {
        NSData *bookmarkData = [docURL bookmarkDataWithOptions:(1<<11)
                                   includingResourceValuesForKeys:0
                                                    relativeToURL:0
                                                            error:0];
        if (bookmarkData) {
            [bookmarks addObject:bookmarkData];
        }
    } else {
        // Match current upstream LiveContainer: private multitask guests stay at
        // their original signed path. LiveProcess receives narrowly-scoped
        // sandbox extensions for the bundle, selected data container and tweaks.
        bool isSharedApp = false;
        NSBundle *bundle = [LCSharedUtils findBundleWithBundleId:bundleId
                                                  isSharedAppOut:&isSharedApp];
        if (!isSharedApp) {
            NSURL *dataURL = [docURL URLByAppendingPathComponent:
                [NSString stringWithFormat:@"Data/Application/%@", dataUUID]];
            NSURL *tweaksURL = [docURL URLByAppendingPathComponent:@"Tweaks"];

            NSData *bundleBookmark = [bundle.bundleURL bookmarkDataWithOptions:(1<<11)
                                                    includingResourceValuesForKeys:0
                                                                     relativeToURL:0
                                                                             error:0];
            NSData *containerBookmark = [dataURL bookmarkDataWithOptions:(1<<11)
                                               includingResourceValuesForKeys:0
                                                                relativeToURL:0
                                                                        error:0];
            NSData *tweaksBookmark = [tweaksURL bookmarkDataWithOptions:(1<<11)
                                              includingResourceValuesForKeys:0
                                                               relativeToURL:0
                                                                       error:0];
            if (bundleBookmark) [bookmarks addObject:bundleBookmark];
            if (containerBookmark) [bookmarks addObject:containerBookmark];
            if (tweaksBookmark) [bookmarks addObject:tweaksBookmark];

            if (!bundleBookmark || !containerBookmark || !tweaksBookmark) {
                NSLog(@"[FlekDeck] LiveProcess bookmark creation incomplete: bundle=%d container=%d tweaks=%d",
                      bundleBookmark != nil, containerBookmark != nil, tweaksBookmark != nil);
            }
        }
    }
'''
s = s[:start] + resource_block + s[end:]

stage_marker = '''    // Local app files are staged into the app group so the extension can reach\n'''
stage_start = s.index(stage_marker)
return_marker = '''    return self;\n}\n'''
stage_end = s.index(return_marker, stage_start)
launch_block = r'''    // Follow upstream LiveContainer's multitask launch boundary. The security
    // scopes above are resolved by LiveProcess before LiveContainerMain enters
    // the guest. Do not move/copy the signed executable to a second path.
    [self beginExtensionRequestWithItem:item delegate:delegate];

'''
s = s[:stage_start] + launch_block + s[stage_end:]
p.write_text(s)

# ---------------------------------------------------------------------------
# 2) Current StikDebug contract for host JIT acquisition.
# StikDebug now targets the exact process PID via stikdebug://enable-jit.
# Keep the legacy internal-LC discovery path compatible with older installs.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
s = p.read_text()
old_host = '''            var launchURLStr = "stikjit://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)"\n'''
new_host = '''            var launchURLStr = "stikdebug://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)&pid=\\(ProcessInfo.processInfo.processIdentifier)"\n'''
if old_host not in s:
    raise SystemExit("LCUtilsExtensions StikDebug host URL anchor not found")
s = s.replace(old_host, new_host, 1)

# New StikDebug advertises stikdebug://. Keep accepting the old stikjit:// scheme
# when StikDebug itself is being hosted as a guest for the LC-to-LC mode.
s = s.replace('''                            if let scheme = scheme as? String, scheme == "stikjit" {\n''',
              '''                            if let scheme = scheme as? String, scheme == "stikdebug" || scheme == "stikjit" {\n''')
p.write_text(s)

# ---------------------------------------------------------------------------
# 3) Current StikDebug contract for multitask/LiveProcess PID attachment.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()
old_pid_url = '''                if let url = URL(string: "stikjit://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)&pid=\\(pid)\\(encoded)") {\n'''
new_pid_url = '''                if let url = URL(string: "stikdebug://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)&pid=\\(pid)\\(encoded)") {\n'''
if old_pid_url not in s:
    raise SystemExit("LCAppListView StikDebug PID URL anchor not found")
s = s.replace(old_pid_url, new_pid_url, 1)
s = s.replace('''                            return app.appInfo.urlSchemes().contains("stikjit") &&\n''',
              '''                            return (app.appInfo.urlSchemes().contains("stikdebug") || app.appInfo.urlSchemes().contains("stikjit")) &&\n''')
p.write_text(s)

# ---------------------------------------------------------------------------
# 4) Legacy relaunch helper: prefer the current external StikDebug scheme while
# retaining the old scheme as a fallback for older StikDebug builds.
# ---------------------------------------------------------------------------
p = Path("LiveContainer/LCSharedUtils.m")
s = p.read_text()
old_legacy = '''        } else if ([application canOpenURL:[NSURL URLWithString:@"stikjit://"]]) {\n            urlScheme = @"stikjit://enable-jit?bundle-id=%@";\n        } else if ([application canOpenURL:[NSURL URLWithString:@"sidestore://"]]) {\n'''
new_legacy = '''        } else if ([application canOpenURL:[NSURL URLWithString:@"stikdebug://"]]) {\n            urlScheme = @"stikdebug://enable-jit?bundle-id=%@";\n        } else if ([application canOpenURL:[NSURL URLWithString:@"stikjit://"]]) {\n            urlScheme = @"stikjit://enable-jit?bundle-id=%@";\n        } else if ([application canOpenURL:[NSURL URLWithString:@"sidestore://"]]) {\n'''
if old_legacy in s:
    s = s.replace(old_legacy, new_legacy, 1)
p.write_text(s)

print("Aligned FlekDeck Parallel launch with LiveContainer bookmarks and current StikDebug PID routing.")
