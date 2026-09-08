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
