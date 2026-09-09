# Parallel guest layout diagnosis — TikTok bottom UI clipped

Temporary experiment only. Do not merge to `main` until on-device validation is complete.

## Base

- Repository: `NightVibes33/FlekDeck`
- Branch base: `b452a1569fc99de8d85a44219adefe60fc14d1d3`
- Experiment branch: `experiment/parallel-guest-layout-safearea`

## Symptom

TikTok is laid out correctly in normal/single mode, but in Parallel the FYP can be sized from the wrong initial viewport and the bottom navigation is partially or completely below the visible hosted scene. Other apps with fixed bottom chrome can be affected by the same host/guest geometry mismatch.

This matches a known LiveContainer multitasking failure pattern. Upstream issue #1139 describes TikTok's video layout being determined by the multitask window size at startup and not correcting after the window is maximized. Upstream issue #792 reports the same class of TikTok fullscreen failure.

## FlekDeck-specific hole

FlekDeck already has the correct primitive for a maximized guest:

`applyMaximizedGeometryToSettings:`

It intentionally performs geometry in this order:

1. resize the FlekDeck host/decorated window;
2. recompute the guest scene drawable (`settings.frame`) from the new host bounds;
3. apply safe-area/periphery settings.

However, `updateVerticalConstraints` still installs this pending block:

```objc
self.appSceneVC.nextUpdateSettingsBlock = ^(UIMutableApplicationSceneSettings *settings) {
    [weakSelf updateMaximizedFrameWithSettings:settings];
};
```

That path only resizes the outer window.

`AppSceneViewController.updateFrameWithSettingsBlock:` computes `settings.frame` *before* invoking `nextUpdateSettingsBlock`. If the pending block then shrinks the maximized window to reserve the FlekDeck control strip or resolved safe area, the guest retains the old, taller drawable size. On the iOS 18+/27 `_UISceneHostingController` path that stale `settings.frame` becomes `contentView.frame`, while the decorated view is clipped to its newer, smaller bounds.

The resulting state is effectively:

- host visible bounds: shorter;
- guest logical/render frame: still taller;
- `masksToBounds = YES` on the decorated host;
- fixed bottom UI is rendered below the visible host and gets clipped.

TikTok exposes this very clearly because its FYP/bottom tab layout is heavily tied to the initial scene size. Many apps are more tolerant and recalculate later, so the bug can appear app-specific even though the underlying fault is generic Parallel geometry.

## Why normal mode is correct

Normal/single mode does not embed the guest through the Parallel `LiveProcess` hosted-scene path. UIKit owns the app's real fullscreen `UIWindow` geometry and safe area directly, so there is no FlekDeck outer-window/guest-scene size split to drift out of sync.

## Experimental correction

Change the pending maximized-layout block to use the complete geometry transaction:

```objc
self.appSceneVC.nextUpdateSettingsBlock = ^(UIMutableApplicationSceneSettings *settings) {
    [weakSelf applyMaximizedGeometryToSettings:settings];
};
```

That forces the guest drawable to be recalculated *after* the outer window has reached its final bounds, matching the invariant already documented and used by `applyMaximizedLayout`, `willPresentSceneWithSettings`, and the host-diff update path.

`Tools/patch_parallel_guest_layout.py` contains the guarded one-shot patch for this experiment.

## Validation matrix before merge

- TikTok FYP: bottom tabs fully visible on first launch.
- TikTok: hide/show FlekDeck switcher bar after launch; no jump or crop.
- TikTok: floating-button and bottom-swipe control modes.
- Portrait and both landscape directions.
- Phone flat / rotation lock transitions.
- PiP enter/exit path, because it calls `updateVerticalConstraints` again.
- At least one other fixed-bottom app (YouTube/Instagram/etc.).
- iPad windowing, to confirm the corrected pending block does not regress native-window geometry.

If the initial-frame mismatch disappears but a ~34pt bottom-only crop remains, the next isolated suspect is iOS 27's hosted-scene `peripheryInsets`/`safeAreaInsetsPortrait` behavior. That should be tested separately rather than mixed into this first fix.
