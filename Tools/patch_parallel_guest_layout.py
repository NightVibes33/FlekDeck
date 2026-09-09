#!/usr/bin/env python3
from pathlib import Path

path = Path("MultitaskSupport/DecoratedAppSceneViewController.m")
text = path.read_text()

old = '''        self.appSceneVC.nextUpdateSettingsBlock = ^(UIMutableApplicationSceneSettings *settings) {
            [weakSelf updateMaximizedFrameWithSettings:settings];
        };
'''

new = '''        self.appSceneVC.nextUpdateSettingsBlock = ^(UIMutableApplicationSceneSettings *settings) {
            // The pending resize runs after AppSceneViewController has already
            // sampled its current frame. Resizing only the outer window here can
            // therefore leave the guest drawable at the old, taller size and clip
            // fixed bottom UI (TikTok is a reliable reproducer). Re-run the full
            // geometry transaction so the drawable is measured from the final
            // maximized bounds.
            [weakSelf applyMaximizedGeometryToSettings:settings];
        };
'''

if old not in text:
    raise SystemExit("expected updateVerticalConstraints pending block not found; source drifted")

if text.count(old) != 1:
    raise SystemExit(f"expected one matching pending block, found {text.count(old)}")

path.write_text(text.replace(old, new, 1))
print(f"patched {path}")
