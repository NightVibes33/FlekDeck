#!/usr/bin/env python3
# Run the proven compatibility base, then add the current TikTok 46.x tab-hierarchy
# fix plus the separate Single-mode switcher gesture bridge.
from pathlib import Path
import runpy

runpy.run_path("Tools/patch_parallel_guest_viewport_base.py", run_name="__main__")

# TikTok 46.x Parallel: the uploaded BHTikTokPlus IPA uses TTKTabBarController /
# TTKTabBar, not the legacy AWETabBarController / AWETabBar classes. Do not use a
# guessed pixel offset. Measure where TikTok actually placed its visible tab bar
# relative to the seeded Parallel viewport and shift the root coordinate space by
# exactly that measured overflow. Width, height, scale and host scene geometry stay
# untouched.
tweak_path = Path("TweakLoader/UIKit+GuestHooks.m")
tweak = tweak_path.read_text()

if "LCTikTok462TabHierarchyCompat" not in tweak:
    install_function_anchor = "static void LCInstallTikTokParallelLayoutCompat(void) {\n"
    if install_function_anchor not in tweak:
        raise SystemExit("TikTok base compat installer anchor missing after base patch")

    ttk_compat = r'''// LCTikTok462TabHierarchyCompat
// LCTikTokParallelBottomNudge -- legacy workflow marker only. The current fix has
// no fixed nudge: it derives the correction from TTKTabBarController's live layout.
// Verified against the uploaded TikTok 46.2.0 / BHTikTokPlus build. That build's
// live tab hierarchy is TTKTabBarController + TTKTabBar/TTKFakeTabBar.
static IMP LCTikTok462OriginalControllerDidLayout = NULL;
static const void *LCTikTok462AlignmentLogKey = &LCTikTok462AlignmentLogKey;
static const void *LCTikTok462AlignmentPendingKey = &LCTikTok462AlignmentPendingKey;

static UIView *LCTikTok462ViewReturnedBySelector(id object, NSString *selectorName) {
    SEL selector = NSSelectorFromString(selectorName);
    if(!object || ![object respondsToSelector:selector]) return nil;
    IMP implementation = [object methodForSelector:selector];
    if(!implementation) return nil;
    id (*getter)(id, SEL) = (void *)implementation;
    id value = getter(object, selector);
    return [value isKindOfClass:UIView.class] ? value : nil;
}

static UIView *LCTikTok462VisibleTabBar(UITabBarController *controller) {
    UIWindow *window = controller.view.window;
    if(!window) return nil;

    // Current TikTok exposes these on TTKTabBarController. Prefer the visual/main
    // bars when present, then fall back to UITabBarController.tabBar.
    NSArray<NSString *> *selectors = @[@"visualTabBar", @"mainTabBar", @"fakeTabBar"];
    for(NSString *selectorName in selectors) {
        UIView *candidate = LCTikTok462ViewReturnedBySelector(controller, selectorName);
        if(candidate && candidate.window == window && !candidate.hidden &&
           candidate.alpha > 0.01 && candidate.bounds.size.height > 1.0) {
            return candidate;
        }
    }

    UIView *tabBar = controller.tabBar;
    if(tabBar && tabBar.window == window && !tabBar.hidden &&
       tabBar.alpha > 0.01 && tabBar.bounds.size.height > 1.0) {
        return tabBar;
    }
    return nil;
}

// LCTikTok462MeasuredAlignment
// TikTok declares itself full-screen-only and can lay the tab hierarchy out against
// the physical display even though FlekDeck's hosted Parallel viewport is shorter.
// Correct only the resulting coordinate-space mismatch: measure the actual bottom
// of TikTok's visible tab bar in window coordinates and align it to the exact bottom
// of LCParallelSeededViewportBounds(). No guessed points are involved.
static void LCTikTok462AlignRootToHostedViewport(id object) {
    if(!LCTikTokParallelCompatEnabled() ||
       ![object isKindOfClass:UITabBarController.class]) return;

    UITabBarController *controller = (UITabBarController *)object;
    UIView *rootView = controller.view;
    UIWindow *window = rootView.window;
    if(!rootView || !window) return;

    CGRect hostedViewport = LCParallelSeededViewportBounds();
    if(CGRectIsNull(hostedViewport) ||
       hostedViewport.size.width <= 1.0 || hostedViewport.size.height <= 1.0) return;

    UIView *tabBar = LCTikTok462VisibleTabBar(controller);
    if(!tabBar) return;

    CGRect tabBarInWindow = [tabBar convertRect:tabBar.bounds toView:window];
    if(CGRectIsNull(tabBarInWindow) || CGRectIsEmpty(tabBarInWindow)) return;

    CGFloat hostedBottom = CGRectGetMaxY(hostedViewport);
    CGFloat tabBarBottom = CGRectGetMaxY(tabBarInWindow);
    CGFloat measuredOverflow = tabBarBottom - hostedBottom;

    // Already aligned. This also prevents a bounds change from creating a layout loop.
    if(ABS(measuredOverflow) <= 0.5) return;

    CGRect bounds = rootView.bounds;
    bounds.origin.y += measuredOverflow;
    rootView.bounds = bounds;

    if(!objc_getAssociatedObject(controller, LCTikTok462AlignmentLogKey)) {
        objc_setAssociatedObject(controller, LCTikTok462AlignmentLogKey, @YES,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        NSLog(@"[FlekDeck] TikTok measured Parallel alignment delta=%.2f tabBar=%@ tabFrame=%@ hosted=%@ rootBounds=%@",
              measuredOverflow, NSStringFromClass(tabBar.class),
              NSStringFromCGRect(tabBarInWindow), NSStringFromCGRect(hostedViewport),
              NSStringFromCGRect(rootView.bounds));
    }
}

static void LCTikTok462ScheduleAlignment(id object) {
    if(!object || objc_getAssociatedObject(object, LCTikTok462AlignmentPendingKey)) return;
    objc_setAssociatedObject(object, LCTikTok462AlignmentPendingKey, @YES,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    dispatch_async(dispatch_get_main_queue(), ^{
        objc_setAssociatedObject(object, LCTikTok462AlignmentPendingKey, nil,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        LCTikTok462AlignRootToHostedViewport(object);
    });
}

static void LCTikTok462ControllerDidLayout(id object, SEL selector) {
    if(LCTikTok462OriginalControllerDidLayout) {
        ((void (*)(id, SEL))LCTikTok462OriginalControllerDidLayout)(object, selector);
    }

    // First pass catches normal UIKit ordering; the coalesced next-main-turn pass
    // catches TikTok's own late tab-bar adjustment without hard-coding any distance.
    LCTikTok462AlignRootToHostedViewport(object);
    LCTikTok462ScheduleAlignment(object);
}

static void LCInstallTikTok462TabHierarchyCompat(void) {
    if(!LCTikTokParallelCompatEnabled() || LCTikTok462OriginalControllerDidLayout) return;
    Class tabController = NSClassFromString(@"TTKTabBarController");
    if(!tabController || ![tabController isSubclassOfClass:UITabBarController.class]) return;

    LCTikTok462OriginalControllerDidLayout =
        LCInstallInstanceOverride(tabController,
                                  @selector(viewDidLayoutSubviews),
                                  (IMP)LCTikTok462ControllerDidLayout);
    if(LCTikTok462OriginalControllerDidLayout) {
        NSLog(@"[FlekDeck] installed measured TikTok 46.x Parallel alignment on TTKTabBarController");
    }
}

'''
    tweak = tweak.replace(install_function_anchor, ttk_compat + install_function_anchor, 1)

    base_retry = r'''        LCInstallTikTokParallelLayoutCompat();
        dispatch_async(dispatch_get_main_queue(), ^{
            LCInstallTikTokParallelLayoutCompat();
        });
'''
    if base_retry not in tweak:
        raise SystemExit("TikTok base compat init/retry block missing")

    current_retry = base_retry + r'''        LCInstallTikTok462TabHierarchyCompat();
        [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
        }];
        [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
        }];
        [[NSNotificationCenter defaultCenter] addObserverForName:UIWindowDidBecomeKeyNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
            dispatch_async(dispatch_get_main_queue(), ^{
                for(UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
                    if(![scene isKindOfClass:UIWindowScene.class]) continue;
                    for(UIWindow *window in ((UIWindowScene *)scene).windows) {
                        [window setNeedsLayout];
                        [window layoutIfNeeded];
                    }
                }
            });
        }];
'''
    tweak = tweak.replace(base_retry, current_retry, 1)

if "LCSingleGuestSwitcherGestureBridge" not in tweak:
    constructor_anchor = "__attribute__((constructor))\nstatic void UIKitGuestHooksInit() {\n"
    if constructor_anchor not in tweak:
        raise SystemExit("UIKit guest constructor anchor missing")
    single_bridge = r'''// LCSingleGuestSwitcherGestureBridge
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

'''
    tweak = tweak.replace(constructor_anchor, single_bridge + constructor_anchor, 1)
    init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
    if init_anchor not in tweak:
        raise SystemExit("UIKit guest init anchor missing")
    tweak = tweak.replace(init_anchor, init_anchor + r'''    if(!NSUserDefaults.isLiveProcess) {
        [[LCSingleGuestSwitcherPanBridge shared] start];
    }
''', 1)

tweak_path.write_text(tweak)

dock_path = Path("MultitaskSupport/MultitaskDockView.swift")
dock = dock_path.read_text()
if "FlekSingleGuestSwitcherGestureRequested" not in dock:
    observer_anchor = r'''        NotificationCenter.default.addObserver(
            self,
            selector: #selector(homeSingleKeyWindowChanged(_:)),
            name: UIWindow.didBecomeKeyNotification,
            object: nil
        )
'''
    if observer_anchor not in dock:
        raise SystemExit("Home/Single key-window observer missing after base patch")
    dock = dock.replace(observer_anchor, observer_anchor + r'''        NotificationCenter.default.addObserver(
            self,
            selector: #selector(singleGuestSwitcherGestureRequested),
            name: Notification.Name("FlekSingleGuestSwitcherGestureRequested"),
            object: nil
        )
''', 1)

    handler_anchor = "    @objc private func homeSingleKeyWindowChanged(_ notification: Notification) {\n"
    if handler_anchor not in dock:
        raise SystemExit("Home/Single key-window handler missing after base patch")
    handler = r'''    @objc private func singleGuestSwitcherGestureRequested() {
        guard isSwipeZoneEnabled,
              !isAppSwitcherOpen,
              !isOpeningAppSwitcher,
              !hasForegroundAppWindow() else { return }
        Self.buttonHaptic()
        showAppSwitcher()
    }

'''
    dock = dock.replace(handler_anchor, handler + handler_anchor, 1)

dock_path.write_text(dock)

final_tweak = tweak_path.read_text()
final_dock = dock_path.read_text()
for required in (
    "LCParallelGuestViewportBridge",
    "LCTikTokParallelLayoutCompat",
    "LCTikTok462TabHierarchyCompat",
    "LCTikTok462MeasuredAlignment",
    'NSClassFromString(@"TTKTabBarController")',
    "LCSingleGuestSwitcherGestureBridge",
):
    if required not in final_tweak:
        raise SystemExit(f"missing marker: {required}")

for forbidden in (
    "seed.size.height -= bottomNudge",
    "seed.origin.y -= verticalShift",
    "LCTikTokAdjustedParallelViewportBounds",
    "LCTikTokParallelBoundsPan",
    "LCTikTok462VerticalPan",
    "bounds.origin.y = 20.0",
):
    if forbidden in final_tweak:
        raise SystemExit(f"forbidden obsolete TikTok layout logic survived: {forbidden}")

for required in (
    "FlekHomeSingleSwitcherGestureBridge",
    "FlekSingleGuestSwitcherGestureRequested",
    "!hasForegroundAppWindow()",
):
    if required not in final_dock:
        raise SystemExit(f"missing marker: {required}")

print("Applied: measured TTKTabBarController Parallel alignment + Single guest switcher bridge")
