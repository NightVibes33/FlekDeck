from pathlib import Path

p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text(encoding="utf-8")

selector = "@objc(prepareHostWindowForGuestLaunch)"
if selector in s:
    print("Direct-build multitask host bridge already present")
    raise SystemExit(0)

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
