#!/usr/bin/env python3
# Run the proven #65 compatibility, then add Single swipe + TikTok bounds pan.
from pathlib import Path
import runpy

runpy.run_path("Tools/patch_parallel_guest_viewport_base.py", run_name="__main__")

# TikTok Parallel: keep the #65 hosted viewport exactly as-is. Do NOT change the
# seed origin or size. TikTok is already very close there; the residual problem is
# that its own hierarchy sits slightly too low. Pan the root coordinate space after
# TikTok has completed layout. A bounds-origin pan moves every child (including the
# bottom tab bar) without changing width, height, scale, aspect ratio, or host scene
# geometry.
tweak_path = Path("TweakLoader/UIKit+GuestHooks.m")
tweak = tweak_path.read_text()

if "LCTikTokParallelBoundsPan" not in tweak:
    static_anchor = (
        "static IMP LCTikTokOriginalTabControllerWillLayout = NULL;\n"
        "static IMP LCTikTokOriginalTabBarLayout = NULL;\n"
    )
    if static_anchor not in tweak:
        raise SystemExit("TikTok compat IMP anchor missing after base patch")
    tweak = tweak.replace(
        static_anchor,
        (
            "static IMP LCTikTokOriginalTabControllerWillLayout = NULL;\n"
            "static IMP LCTikTokOriginalTabControllerDidLayout = NULL;\n"
            "static IMP LCTikTokOriginalTabBarLayout = NULL;\n"
        ),
        1,
    )

    function_anchor = "static void LCTikTokTabControllerWillLayout(id object, SEL selector) {\n"
    if function_anchor not in tweak:
        raise SystemExit("TikTok will-layout hook missing after base patch")

    bounds_pan = r"""// LCTikTokParallelBoundsPan
// LCTikTokParallelBottomNudge -- legacy CI marker; this no longer resizes anything.
static const CGFloat LCTikTokParallelVerticalPan = 20.0;

static void LCTikTokApplyParallelBoundsPan(id object) {
    if(!LCTikTokParallelCompatEnabled() || ![object isKindOfClass:UIViewController.class]) return;
    UIViewController *controller = (UIViewController *)object;
    UIView *view = controller.view;
    if(!view || !view.window) return;

    CGRect bounds = view.bounds;
    if(ABS(bounds.origin.y - LCTikTokParallelVerticalPan) <= 0.5) return;
    bounds.origin.y = LCTikTokParallelVerticalPan;
    view.bounds = bounds;
}

static void LCTikTokTabControllerDidLayout(id object, SEL selector) {
    if(LCTikTokOriginalTabControllerDidLayout) {
        ((void (*)(id, SEL))LCTikTokOriginalTabControllerDidLayout)(object, selector);
    }
    // Apply after TikTok/Auto Layout is finished so the app cannot immediately
    // re-frame itself back down. Size stays untouched; only bounds.origin moves.
    LCTikTokApplyParallelBoundsPan(object);
}

"""
    tweak = tweak.replace(function_anchor, bounds_pan + function_anchor, 1)

    install_anchor = r"""    if(!LCTikTokOriginalTabBarLayout) {
        Class tabBar = NSClassFromString(@"AWETabBar");
"""
    if install_anchor not in tweak:
        raise SystemExit("TikTok tab-bar install anchor missing after base patch")

    did_layout_install = r"""    if(!LCTikTokOriginalTabControllerDidLayout) {
        Class tabController = NSClassFromString(@"AWETabBarController");
        if(tabController) {
            LCTikTokOriginalTabControllerDidLayout =
                LCInstallInstanceOverride(tabController,
                                          @selector(viewDidLayoutSubviews),
                                          (IMP)LCTikTokTabControllerDidLayout);
        }
    }

"""
    tweak = tweak.replace(install_anchor, did_layout_install + install_anchor, 1)

# Single mode: install the gesture inside the actual in-process guest window and
# post back to FlekDeck's existing switcher manager. Parallel never installs this.
if "LCSingleGuestSwitcherGestureBridge" not in tweak:
    constructor_anchor = "__attribute__((constructor))\nstatic void UIKitGuestHooksInit() {\n"
    if constructor_anchor not in tweak:
        raise SystemExit("UIKit guest constructor anchor missing")
    single_bridge = r"""// LCSingleGuestSwitcherGestureBridge
@interface LCSingleGuestSwitcherPanBridge : NSObject <UIGestureRecognizerDelegate>
@property(nonatomic, strong) NSMapTable<UIWindow *, UIPanGestureRecognizer *> *recognizers;
@end

@implementation LCSingleGuestSwitcherPanBridge
+ (instancetype)shared {
    static LCSingleGuestSwitcherPanBridge *bridge;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        bridge = [LCSingleGuestSwitcherPanBridge new];
        bridge.recognizers = [NSMapTable weakToStrongObjectsMapTable];
    });
    return bridge;
}
- (void)attachToWindow:(UIWindow *)window {
    if(!window || NSUserDefaults.isLiveProcess || [self.recognizers objectForKey:window]) return;
    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(handlePan:)];
    pan.maximumNumberOfTouches = 1;
    pan.cancelsTouchesInView = NO;
    pan.delaysTouchesBegan = NO;
    pan.delaysTouchesEnded = NO;
    pan.delegate = self;
    [window addGestureRecognizer:pan];
    [self.recognizers setObject:pan forKey:window];
}
- (void)start {
    if(NSUserDefaults.isLiveProcess) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:UIWindowDidBecomeKeyNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        UIWindow *window = [note.object isKindOfClass:UIWindow.class] ? note.object : nil;
        [[LCSingleGuestSwitcherPanBridge shared] attachToWindow:window];
    }];
    UIApplication *application = UIApplication.sharedApplication;
    for(UIScene *scene in application.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class]) continue;
        for(UIWindow *window in ((UIWindowScene *)scene).windows) [self attachToWindow:window];
    }
}
- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer *)gestureRecognizer {
    if(NSUserDefaults.isLiveProcess || ![gestureRecognizer isKindOfClass:UIPanGestureRecognizer.class]) return NO;
    UIPanGestureRecognizer *pan = (UIPanGestureRecognizer *)gestureRecognizer;
    UIWindow *window = (UIWindow *)pan.view;
    if(![window isKindOfClass:UIWindow.class]) return NO;
    CGPoint point = [pan locationInView:window];
    CGFloat bottomBand = MAX(window.safeAreaInsets.bottom + 30.0, 64.0);
    if(point.y < CGRectGetMaxY(window.bounds) - bottomBand) return NO;
    CGPoint velocity = [pan velocityInView:window];
    return velocity.y < -80.0 && fabs(velocity.y) > fabs(velocity.x);
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)otherGestureRecognizer { return YES; }
- (void)handlePan:(UIPanGestureRecognizer *)pan {
    if(NSUserDefaults.isLiveProcess || pan.state != UIGestureRecognizerStateEnded) return;
    UIWindow *window = (UIWindow *)pan.view;
    if(![window isKindOfClass:UIWindow.class]) return;
    CGFloat translation = [pan translationInView:window].y;
    CGFloat velocity = [pan velocityInView:window].y;
    if(-translation < 16.0 && velocity > -300.0) return;
    [[NSNotificationCenter defaultCenter] postNotificationName:@"FlekSingleGuestSwitcherGestureRequested" object:nil];
}
@end

"""
    tweak = tweak.replace(constructor_anchor, single_bridge + constructor_anchor, 1)
    init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
    if init_anchor not in tweak:
        raise SystemExit("UIKit guest init anchor missing")
    tweak = tweak.replace(init_anchor, init_anchor + r"""    if(!NSUserDefaults.isLiveProcess) {
        [[LCSingleGuestSwitcherPanBridge shared] start];
    }
""", 1)

tweak_path.write_text(tweak)

# Host receiver for the Single guest gesture. Parallel is still excluded by the
# existing hosted-window check, so its proven swipe zone remains untouched.
dock_path = Path("MultitaskSupport/MultitaskDockView.swift")
dock = dock_path.read_text()
if "FlekSingleGuestSwitcherGestureRequested" not in dock:
    observer_anchor = r"""        NotificationCenter.default.addObserver(
            self,
            selector: #selector(homeSingleKeyWindowChanged(_:)),
            name: UIWindow.didBecomeKeyNotification,
            object: nil
        )
"""
    if observer_anchor not in dock:
        raise SystemExit("Home/Single key-window observer missing after base patch")
    dock = dock.replace(observer_anchor, observer_anchor + r"""        NotificationCenter.default.addObserver(
            self,
            selector: #selector(singleGuestSwitcherGestureRequested),
            name: Notification.Name("FlekSingleGuestSwitcherGestureRequested"),
            object: nil
        )
""", 1)

    handler_anchor = "    @objc private func homeSingleKeyWindowChanged(_ notification: Notification) {\n"
    if handler_anchor not in dock:
        raise SystemExit("Home/Single key-window handler missing after base patch")
    handler = r"""    @objc private func singleGuestSwitcherGestureRequested() {
        guard isSwipeZoneEnabled,
              !isAppSwitcherOpen,
              !isOpeningAppSwitcher,
              !hasForegroundAppWindow() else { return }
        Self.buttonHaptic()
        showAppSwitcher()
    }

"""
    dock = dock.replace(handler_anchor, handler + handler_anchor, 1)

dock_path.write_text(dock)

final_tweak = tweak_path.read_text()
final_dock = dock_path.read_text()
for required in (
    "LCParallelGuestViewportBridge",
    "LCTikTokParallelLayoutCompat",
    "LCTikTokParallelBoundsPan",
    "LCTikTokParallelBottomNudge",
    "LCSingleGuestSwitcherGestureBridge",
):
    if required not in final_tweak:
        raise SystemExit(f"missing marker: {required}")

# Fail closed against accidentally reintroducing the two broken attempts.
for forbidden in (
    "seed.size.height -= bottomNudge",
    "seed.origin.y -= verticalShift",
    "LCTikTokAdjustedParallelViewportBounds",
):
    if forbidden in final_tweak:
        raise SystemExit(f"forbidden TikTok resize/frame-shift logic survived: {forbidden}")

for required in (
    "FlekHomeSingleSwitcherGestureBridge",
    "FlekSingleGuestSwitcherGestureRequested",
    "!hasForegroundAppWindow()",
):
    if required not in final_dock:
        raise SystemExit(f"missing marker: {required}")

print("Applied: Single guest switcher bridge + TikTok Parallel post-layout bounds pan (no resize)")
