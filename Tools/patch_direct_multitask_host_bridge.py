from pathlib import Path

# Direct-build compatibility for the temp multitask branch. Keep these changes
# narrowly scoped to source surfaces that the legacy build.yml compiles directly.

# 1) LCUtils.m expects this ObjC selector on MultitaskDockManager. Inject it into
# the existing compiled Swift file so it is emitted into LiveContainerSwiftUI-Swift.h.
p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text(encoding="utf-8")
selector = "@objc(prepareHostWindowForGuestLaunch)"

if selector not in s:
    anchor = '''        return nil
    }

    /// Ranks scenes so the foreground-active one wins over restored/background
'''
    replacement = '''        return nil
    }

    /// Compatibility surface used by LCUtils.m when Run Parallel launches a
    /// guest through FlekDeck's virtual-window host. This lives on the existing
    /// compiled MultitaskDockManager source so it is exported in the generated
    /// LiveContainerSwiftUI-Swift.h header for Objective-C callers.
    @objc(prepareHostWindowForGuestLaunch)
    public func prepareHostWindowForGuestLaunch() -> UIWindow? {
        dispatchPrecondition(condition: .onQueue(.main))
        guard let window = keyWindow,
              window.rootViewController != nil,
              window.windowScene != nil else {
            return nil
        }
        windowHostingView.frame = window.bounds
        return window
    }

    /// Ranks scenes so the foreground-active one wins over restored/background
'''
    if anchor not in s:
        raise SystemExit("Could not find MultitaskDockManager keyWindow anchor")
    s = s.replace(anchor, replacement, 1)
    p.write_text(s, encoding="utf-8")

if s.count(selector) != 1:
    raise SystemExit("Unexpected multitask host bridge count after patch")
print("Injected Objective-C-visible multitask host window bridge into compiled source")

# 2) FlekDeck's newer OfflineClassicModeProbe references a helper that the legacy
# direct-build target does not link. Use the same local compatibility fallback as
# the signer-compatible build boundary: execute the probe block directly rather
# than leaving an unresolved external symbol.
p = Path("LiveContainerSwiftUI/Utilities/OfflineClassicModeProbe.m")
s = p.read_text(encoding="utf-8")
old_decl = 'void bypass_os_variant_has_internal_content(void (^block)(void));\n'
local_helper = '''static void LCFlekClassicProbeBypass(void (^block)(void)) {
    if (block) block();
}
'''

if old_decl in s:
    s = s.replace(old_decl, local_helper, 1)
elif "static void LCFlekClassicProbeBypass" not in s:
    raise SystemExit("OfflineClassicModeProbe bypass declaration anchor not found")

s = s.replace('bypass_os_variant_has_internal_content(^{', 'LCFlekClassicProbeBypass(^{')

if 'bypass_os_variant_has_internal_content(^{ ' in s or 'bypass_os_variant_has_internal_content(^{\n' in s:
    raise SystemExit("Unresolved classic-mode bypass call remains")
if "static void LCFlekClassicProbeBypass" not in s:
    raise SystemExit("Local classic-mode bypass helper missing")

p.write_text(s, encoding="utf-8")
print("Replaced unresolved classic-mode probe bypass with local compatibility helper")

# 3) Restore Duy's private-app multitask sandbox-extension contract. FlekDeck's
# current source stages private guests into the app group but does not hand
# LiveProcess the bundle/data/tweaks access grants that bootstrap expects. The
# result is that LiveProcess reaches LiveContainerMain but LCAppInfo.plist cannot
# be read from the guest bundle. Use the upstream bookmark handoff for this temp
# experiment and start the extension directly. Do not keep staging enabled at the
# same time: cleanup would otherwise copy an untouched staged container back over
# the live bookmarked container and could discard guest writes.
p = Path("MultitaskSupport/AppSceneViewController.m")
s = p.read_text(encoding="utf-8")
start_anchor = '''    NSURL *docURL = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].lastObject;
'''
end_anchor = '''
    return self;
}

// The delegate is passed in rather than read from self:'''

init_start = s.find('- (instancetype)initWithBundleId:')
if init_start < 0:
    raise SystemExit("AppSceneViewController initializer anchor not found")
start = s.find(start_anchor, init_start)
if start < 0:
    raise SystemExit("AppSceneViewController Documents handoff anchor not found inside initializer")
end = s.find(end_anchor, start)
if end < 0:
    raise SystemExit("AppSceneViewController init tail anchor not found")

bookmark_handoff = '''    NSURL *docURL = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].lastObject;
    if ([NSUserDefaults.standardUserDefaults boolForKey:@"LCSharePrivateDataWithLiveProcess"]) {
        NSData *bookmarkData = [docURL bookmarkDataWithOptions:(1<<11)
                              includingResourceValuesForKeys:0
                                               relativeToURL:0
                                                       error:0];
        if (bookmarkData) {
            [bookmarks addObject:bookmarkData];
        }
    } else {
        bool isSharedApp = false;
        NSBundle *bundle = [LCSharedUtils findBundleWithBundleId:bundleId isSharedAppOut:&isSharedApp];
        if (!isSharedApp) {
            NSURL *dataURL = [docURL URLByAppendingPathComponent:[NSString stringWithFormat:@"Data/Application/%@", dataUUID]];
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
            if (!bundleBookmark || !containerBookmark || !tweaksBookmark) {
                NSError *bookmarkError = [NSError errorWithDomain:@"LiveProcess"
                                                              code:13
                                                          userInfo:@{NSLocalizedDescriptionKey:
                    @"Run Parallel could not grant LiveProcess access to the guest bundle, data container, and tweaks."}];
                [delegate appSceneVC:self didInitializeWithError:bookmarkError];
                return nil;
            }
            [bookmarks addObject:bundleBookmark];
            [bookmarks addObject:containerBookmark];
            [bookmarks addObject:tweaksBookmark];
        }
    }

    item.userInfo = userInfo;

    __weak typeof(self) weakSelf = self;
    [_extension setRequestCancellationBlock:^(NSUUID *uuid, NSError *error) {
        [weakSelf appTerminationCleanUp];
        [weakSelf.delegate appSceneVC:weakSelf didInitializeWithError:error];
    }];
    [_extension setRequestInterruptionBlock:^(NSUUID *uuid) {
        [weakSelf appTerminationCleanUp];
    }];

    _isNativeWindow = [NSUserDefaults.lcSharedDefaults integerForKey:@"LCMultitaskMode" ] == 1;
    self.stagedToAppGroup = false;
    [self beginExtensionRequestWithItem:item delegate:delegate];
'''

s = s[:start] + bookmark_handoff + s[end:]

required = [
    '[bookmarks addObject:bundleBookmark];',
    '[bookmarks addObject:containerBookmark];',
    '[bookmarks addObject:tweaksBookmark];',
    '[self beginExtensionRequestWithItem:item delegate:delegate];',
]
for needle in required:
    if needle not in s:
        raise SystemExit(f"Missing upstream bookmark handoff marker: {needle}")

# The build-time source must no longer enter the app-group staging launch path.
init_end = s.find('// The delegate is passed in rather than read from self:', init_start)
init_body = s[init_start:init_end]
if 'LCStageAppToAppGroup(' in init_body:
    raise SystemExit("Private app-group staging still active in patched initializer")

p.write_text(s, encoding="utf-8")
print("Restored upstream private-app bookmark handoff for Run Parallel")

# 4) Current StikDebug uses the `stikdebug` URL scheme. The inherited LiveContainer
# code still emits the old `stikjit` scheme even though the Settings UI labels that
# enum value as StikDebug. Modern StikDebug ignores that request, and the PID path
# also discarded UIApplication.open's success result, producing a silent failure.
# Keep custom iOS 26/27 script data exactly as stored (already Base64), but send it
# through URLComponents so +, / and = are safely encoded.
p = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
s = p.read_text(encoding="utf-8")
branch_start = s.find('        } else if jitEnabler == .StikJIT || jitEnabler == .StikJITLC {')
branch_end = s.find('        } else if jitEnabler == .SideStore {', branch_start)
if branch_start < 0 or branch_end < 0:
    raise SystemExit("StikDebug askForJIT branch anchors not found")

stikdebug_branch = '''        } else if jitEnabler == .StikJIT || jitEnabler == .StikJITLC {
            guard let bundleID = Bundle.main.bundleIdentifier else {
                onServerMessage?("Unable to determine FlekDeck's bundle identifier for StikDebug.")
                return false
            }

            var components = URLComponents()
            components.scheme = "stikdebug"
            components.host = "enable-jit"
            components.queryItems = [
                URLQueryItem(name: "bundle-id", value: bundleID),
                URLQueryItem(name: "pid", value: String(ProcessInfo.processInfo.processIdentifier))
            ]
            if let script = script, !script.isEmpty {
                components.queryItems?.append(URLQueryItem(name: "script-data", value: script))
            }
            guard let directStikDebugURL = components.url else {
                onServerMessage?("Unable to create the StikDebug JIT request URL.")
                return false
            }

            let launchURL: URL
            if jitEnabler == .StikJITLC {
                let encodedStr = Data(directStikDebugURL.absoluteString.utf8).base64EncodedString()

                var appToLaunch: LCAppModel? = nil
                appLoop:
                for app in DataManager.shared.model.apps {
                    if let schemes = app.appInfo.urlSchemes() {
                        for scheme in schemes {
                            if let scheme = scheme as? String, scheme == "stikdebug" {
                                appToLaunch = app
                                break appLoop
                            }
                        }
                    }
                }
                guard let appToLaunch else {
                    onServerMessage?("StikDebug is not installed in FlekDeck.")
                    return false
                }
                if !appToLaunch.uiIsShared {
                    onServerMessage?("StikDebug is installed in FlekDeck, but is not a shared app. Convert it to a shared app to continue.")
                    return false
                }

                var freeScheme = LCSharedUtils.getContainerUsingLCScheme(withFolderName: appToLaunch.uiDefaultDataFolder)
                if freeScheme == nil {
                    forEachInstalledLC(isFree: true) { scheme, shouldBreak in
                        freeScheme = scheme
                        shouldBreak = true
                    }
                }
                guard let freeScheme else {
                    onServerMessage?("No free FlekDeck instance is available to run StikDebug.")
                    return false
                }

                launchURL = URL(string: "\\(freeScheme)://open-url?url=\\(encodedStr)")!
                LCUtils.appGroupUserDefault.set(freeScheme, forKey: "LCLaunchExtensionScheme")
                LCUtils.appGroupUserDefault.set(appToLaunch.appInfo.relativeBundlePath, forKey: "LCLaunchExtensionBundleID")
                LCUtils.appGroupUserDefault.set(Date.now, forKey: "LCLaunchExtensionLaunchDate")
                onServerMessage?("JIT acquisition will continue in StikDebug running in another FlekDeck instance.")
            } else {
                launchURL = directStikDebugURL
                onServerMessage?("JIT acquisition will continue in StikDebug.")
            }

            let opened = await UIApplication.shared.open(launchURL)
            if !opened {
                onServerMessage?("Failed to open StikDebug. Install or update StikDebug, then try again.")
                return false
            }
'''
s = s[:branch_start] + stikdebug_branch + s[branch_end:]
if 'stikjit://enable-jit' in s:
    raise SystemExit("Obsolete stikjit URL remains in LCUtilsExtensions.swift")
p.write_text(s, encoding="utf-8")
print("Updated normal StikDebug JIT requests to current stikdebug:// contract")

# PID-specific Run Parallel request. Preserve StosDebug as its own provider, but
# target the exact LiveProcess PID with StikDebug and report URL-open failures.
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text(encoding="utf-8")
old_url = 'URL(string: "stikjit://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)&pid=\\(pid)\\(encoded)")'
new_url = 'URL(string: "stikdebug://enable-jit?bundle-id=\\(Bundle.main.bundleIdentifier!)&pid=\\(pid)\\(encoded)")'
if old_url not in s and 'stikdebug://enable-jit' not in s:
    raise SystemExit("PID StikDebug URL anchor not found")
s = s.replace(old_url, new_url, 1)
s = s.replace('app.appInfo.urlSchemes().contains("stikjit")', 'app.appInfo.urlSchemes().contains("stikdebug")', 1)

pid_func_start = s.find('    func jitLaunch(withPID pid: Int,')
pid_func_end = s.find('    func showRunWhenMultitaskAlert()', pid_func_start)
if pid_func_start < 0 or pid_func_end < 0:
    raise SystemExit("PID JIT launch function anchors not found")
pid_func = s[pid_func_start:pid_func_end]
final_open = '''                    } else {
                        UIApplication.shared.open(url)
                    }
                }
            }
        }
    }

'''
final_open_replacement = '''                    } else {
                        UIApplication.shared.open(url, options: [:]) { opened in
                            guard !opened else { return }
                            Task { @MainActor in
                                self.errorInfo = "FlekDeck could not open StikDebug. Install or update StikDebug, then try again."
                                self.errorShow = true
                            }
                        }
                    }
                }
            }
        }
    }

'''
if final_open not in pid_func:
    raise SystemExit("PID StikDebug open-result anchor not found")
pid_func = pid_func.replace(final_open, final_open_replacement, 1)
s = s[:pid_func_start] + pid_func + s[pid_func_end:]

if 'stikjit://enable-jit' in s:
    raise SystemExit("Obsolete stikjit URL remains in LCAppListView.swift")
if 'stikdebug://enable-jit' not in s or 'contains("stikdebug")' not in s:
    raise SystemExit("Current StikDebug PID routing markers missing")
p.write_text(s, encoding="utf-8")
print("Updated Run Parallel StikDebug routing to the exact LiveProcess PID")
