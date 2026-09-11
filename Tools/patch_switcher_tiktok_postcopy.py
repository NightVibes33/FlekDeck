#!/usr/bin/env python3
"""Post-copy FlekDeck compatibility that must survive the Vibe runtime overlay.

The signer-compatible workflow deliberately overlays a pinned VibeContainers runtime
before building. Anything that belongs to FlekDeck's guest/UI behavior therefore has
to be applied *after* that overlay or it can silently disappear from the produced IPA.

This patch deliberately leaves the already-working Home and Parallel switcher paths
alone. It only:

1. gives in-process (Single mode) guest windows their own bottom-up switcher gesture
   and signals the host switcher in the same process, and
2. trims TikTok's already-nearly-correct Parallel layout by a small portrait-only
   residual amount so its own tab/feed hierarchy lands above the host control strip.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) Guest side: Single-mode bottom pan + TikTok residual Parallel lift.
# ---------------------------------------------------------------------------
path = Path("TweakLoader/UIKit+GuestHooks.m")
source = path.read_text()

# TikTok #65 is now using the hosted Parallel rectangle, but its own tab hierarchy
# still lands a few points too low. Do not move the host window/bar and do not alter
# screen metrics again: shorten only TikTok's internal portrait layout rectangle.
residual_marker = "LCTikTokParallelResidualLift"
if residual_marker not in source:
    compat_anchor = '''static BOOL LCTikTokParallelCompatEnabled(void) {
    return !CGRectIsNull(LCParallelSeededViewportBounds());
}
'''
    if compat_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: TikTok Parallel compatibility anchor not found")

    compat_replacement = compat_anchor + r'''
// LCTikTokParallelResidualLift
// #65 established the correct hosted viewport but TikTok's tab/feed stack still
// resolves slightly below the visible Parallel bottom edge. Keep the screen/scene
// geometry truthful and compensate only inside TikTok's non-resizable root layout.
// Portrait only: landscape already has different edge semantics and is not part of
// the reported failure.
static CGRect LCTikTokParallelEffectiveLayoutBounds(void) {
    CGRect bounds = LCParallelSeededViewportBounds();
    if(CGRectIsNull(bounds)) return bounds;
    if(bounds.size.height > bounds.size.width && bounds.size.height > 40.0) {
        const CGFloat residualLift = 18.0;
        bounds.size.height = MAX(bounds.size.height - residualLift, 1.0);
    }
    return bounds;
}
'''
    source = source.replace(compat_anchor, compat_replacement, 1)

    def replace_inside(signature: str, old: str, new: str) -> None:
        nonlocal_source = None

    # Scope the replacements to the two TikTok layout functions so the public/private
    # UIScreen bridges continue returning the actual hosted rectangle.
    root_start = source.find("static void LCTikTokClampRootController(id object) {")
    root_end = source.find("\n}\n\nstatic void LCTikTokTabControllerWillLayout", root_start)
    if root_start < 0 or root_end < 0:
        raise SystemExit("UIKit+GuestHooks.m: TikTok root clamp block not found")
    root_block = source[root_start:root_end]
    old_seed = "    CGRect seed = LCParallelSeededViewportBounds();\n"
    if old_seed not in root_block:
        raise SystemExit("UIKit+GuestHooks.m: TikTok root seed assignment not found")
    root_block = root_block.replace(
        old_seed,
        "    CGRect seed = LCTikTokParallelEffectiveLayoutBounds();\n",
        1,
    )
    source = source[:root_start] + root_block + source[root_end:]

    bar_start = source.find("static void LCTikTokAnchorTabBar(id object) {")
    bar_end = source.find("\n}\n\nstatic void LCTikTokTabBarLayout", bar_start)
    if bar_start < 0 or bar_end < 0:
        raise SystemExit("UIKit+GuestHooks.m: TikTok tab bar block not found")
    bar_block = source[bar_start:bar_end]
    if old_seed not in bar_block:
        raise SystemExit("UIKit+GuestHooks.m: TikTok tab bar seed assignment not found")
    bar_block = bar_block.replace(
        old_seed,
        "    CGRect seed = LCTikTokParallelEffectiveLayoutBounds();\n",
        1,
    )
    source = source[:bar_start] + bar_block + source[bar_end:]
    print("Applied TikTok portrait residual Parallel lift (18pt)")
else:
    print("TikTok residual Parallel lift already present")

single_marker = "FlekSingleGuestSwitcherGestureBridge"
if single_marker not in source:
    category_anchor = "@implementation UIScreen (LCParallelGuestViewportBridge)\n"
    if category_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: UIScreen bridge implementation anchor not found")

    single_bridge = r'''// FlekSingleGuestSwitcherGestureBridge
//
// Single mode is the in-process launch path. It does not live in the hosted
// Parallel window hierarchy, so Parallel's proven MultitaskSwipeZone cannot see
// the guest's bottom-edge pan. Install the recognizer directly on the in-process
// guest key window and signal FlekDeck's existing switcher through NotificationCenter.
// LiveProcess/Parallel is explicitly excluded and keeps its existing gesture path.
@interface FlekSingleGuestSwitcherGestureBridge : NSObject <UIGestureRecognizerDelegate>
@property(nonatomic, weak) UIWindow *window;
@property(nonatomic, weak) UIPanGestureRecognizer *pan;
@end

@implementation FlekSingleGuestSwitcherGestureBridge

+ (instancetype)shared {
    static FlekSingleGuestSwitcherGestureBridge *bridge;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        bridge = [FlekSingleGuestSwitcherGestureBridge new];
    });
    return bridge;
}

- (void)installOnWindow:(UIWindow *)window {
    if(!window || NSUserDefaults.isLiveProcess) return;
    if(self.window == window && self.pan.view == window) return;

    if(self.pan) {
        [self.pan.view removeGestureRecognizer:self.pan];
    }

    UIPanGestureRecognizer *pan =
        [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(handlePan:)];
    pan.maximumNumberOfTouches = 1;
    pan.cancelsTouchesInView = NO;
    pan.delaysTouchesBegan = NO;
    pan.delaysTouchesEnded = NO;
    pan.delegate = self;
    [window addGestureRecognizer:pan];

    self.window = window;
    self.pan = pan;
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer *)gestureRecognizer {
    if(NSUserDefaults.isLiveProcess || !self.window ||
       ![gestureRecognizer isKindOfClass:UIPanGestureRecognizer.class]) return NO;

    UIPanGestureRecognizer *pan = (UIPanGestureRecognizer *)gestureRecognizer;
    CGPoint point = [pan locationInView:self.window];
    CGFloat bottomBand = MAX(self.window.safeAreaInsets.bottom + 30.0, 64.0);
    if(point.y < CGRectGetMaxY(self.window.bounds) - bottomBand) return NO;

    CGPoint velocity = [pan velocityInView:self.window];
    return velocity.y < -80.0 && fabs(velocity.y) > fabs(velocity.x);
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer
        shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)other {
    return YES;
}

- (void)handlePan:(UIPanGestureRecognizer *)pan {
    if(NSUserDefaults.isLiveProcess || pan.state != UIGestureRecognizerStateEnded || !self.window) return;

    CGFloat translation = [pan translationInView:self.window].y;
    CGFloat velocity = [pan velocityInView:self.window].y;
    if(-translation < 16.0 && velocity > -300.0) return;

    [NSNotificationCenter.defaultCenter
        postNotificationName:@"FlekSingleSwitcherGestureRequested"
                      object:self.window];
}

@end

static UIWindow *LCFlekSingleKeyWindow(void) {
    UIApplication *application = UIApplication.sharedApplication;
    if(!application) return nil;

    for(UIScene *scene in application.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class]) continue;
        if(scene.activationState != UISceneActivationStateForegroundActive &&
           scene.activationState != UISceneActivationStateForegroundInactive) continue;
        for(UIWindow *window in ((UIWindowScene *)scene).windows) {
            if(window.isKeyWindow) return window;
        }
    }
    return nil;
}

static void LCInstallFlekSingleGuestSwitcherGesture(void) {
    if(NSUserDefaults.isLiveProcess) return;

    static dispatch_once_t observerOnce;
    dispatch_once(&observerOnce, ^{
        [NSNotificationCenter.defaultCenter
            addObserverForName:UIWindowDidBecomeKeyNotification
                        object:nil
                         queue:NSOperationQueue.mainQueue
                    usingBlock:^(NSNotification *note) {
            UIWindow *window = [note.object isKindOfClass:UIWindow.class] ? note.object : nil;
            [[FlekSingleGuestSwitcherGestureBridge shared] installOnWindow:window];
        }];
    });

    dispatch_async(dispatch_get_main_queue(), ^{
        [[FlekSingleGuestSwitcherGestureBridge shared] installOnWindow:LCFlekSingleKeyWindow()];
    });
}

'''
    source = source.replace(category_anchor, single_bridge + category_anchor, 1)

    init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
    if init_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: UIKitGuestHooksInit anchor not found")
    source = source.replace(
        init_anchor,
        init_anchor + "    LCInstallFlekSingleGuestSwitcherGesture();\n",
        1,
    )
    print("Installed in-process Single-mode guest switcher gesture")
else:
    print("Single-mode guest switcher gesture already present")

path.write_text(source)

# ---------------------------------------------------------------------------
# 2) Host side: consume only the Single-mode guest signal.
# ---------------------------------------------------------------------------
path = Path("MultitaskSupport/MultitaskDockView.swift")
source = path.read_text()
host_marker = "FlekSingleSwitcherGestureRequested"

if host_marker not in source:
    observer_anchor = '''        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appDidBecomeActive),
            name: UIApplication.didBecomeActiveNotification,
            object: nil
        )
'''
    if observer_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: app foreground observer anchor not found")

    observer = observer_anchor + '''        // Single mode runs the guest in-process, outside Parallel's hosted-window
        // gesture hierarchy. The guest-side bottom pan posts this notification;
        // Home and Parallel never use it.
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(singleGuestSwitcherGestureRequested),
            name: Notification.Name("FlekSingleSwitcherGestureRequested"),
            object: nil
        )
'''
    source = source.replace(observer_anchor, observer, 1)

    method_anchor = "    @objc private func appDidBecomeActive() {\n"
    if method_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: appDidBecomeActive method anchor not found")

    method = '''    @objc private func singleGuestSwitcherGestureRequested() {
        // Fail closed if a Parallel hosted window owns the stage. That keeps the
        // already-perfect Parallel MultitaskSwipeZone as the only gesture there.
        guard isDockEnabled(), isSwipeZoneEnabled,
              !isAppSwitcherOpen, !isOpeningAppSwitcher,
              !hasForegroundAppWindow() else { return }
        Self.buttonHaptic()
        showAppSwitcher()
    }

'''
    source = source.replace(method_anchor, method + method_anchor, 1)
    path.write_text(source)
    print("Connected Single-mode guest gesture to existing FlekDeck switcher")
else:
    print("Single-mode host switcher signal already present")

# Fail closed: these are the exact post-copy guarantees this script exists to keep.
tweak = Path("TweakLoader/UIKit+GuestHooks.m").read_text()
dock = Path("MultitaskSupport/MultitaskDockView.swift").read_text()
for required in (
    "LCTikTokParallelResidualLift",
    "LCTikTokParallelEffectiveLayoutBounds",
    "FlekSingleGuestSwitcherGestureBridge",
    "FlekSingleSwitcherGestureRequested",
):
    if required not in tweak:
        raise SystemExit(f"post-copy guest compatibility marker missing: {required}")
for required in (
    "FlekHomeSingleSwitcherGestureBridge",  # #65 Home fallback remains intact
    "FlekSingleSwitcherGestureRequested",
    "singleGuestSwitcherGestureRequested",
    "MultitaskSwipeZone",                   # proven Parallel path remains present
):
    if required not in dock:
        raise SystemExit(f"post-copy switcher marker missing: {required}")

print("Post-copy switcher/TikTok compatibility verified; Home and Parallel paths preserved")
