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
