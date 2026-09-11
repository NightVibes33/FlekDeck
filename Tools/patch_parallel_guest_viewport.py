#!/usr/bin/env python3
# Run the proven compatibility base, then add the current TikTok 46.x tab-hierarchy
# fix plus the separate Single-mode switcher gesture bridge.
from pathlib import Path
import runpy

runpy.run_path("Tools/patch_parallel_guest_viewport_base.py", run_name="__main__")

# TikTok 46.x Parallel: the uploaded BHTikTokPlus IPA uses TTKTabBarController /
# TTKTabBar, not the legacy AWETabBarController / AWETabBar classes. Do not move
# the controller root view: that is what created the large black top band and made
# TikTok's feed overlays disagree with its navigation bar. Keep the feed surface in
# place, align TikTok's own tab-bar views to the hosted viewport, then propagate the
# resulting bottom exclusion into the selected child controller's safe area.
tweak_path = Path("TweakLoader/UIKit+GuestHooks.m")
tweak = tweak_path.read_text()

if "LCTikTok462TabHierarchyCompat" not in tweak:
    install_function_anchor = "static void LCInstallTikTokParallelLayoutCompat(void) {\n"
    if install_function_anchor not in tweak:
        raise SystemExit("TikTok base compat installer anchor missing after base patch")

    ttk_compat = r'''// LCTikTok462TabHierarchyCompat
// LCTikTokParallelBottomNudge -- legacy workflow marker only. There is no fixed
// nudge and the root view is never translated by this compatibility layer.
// LCTikTok462HostedInsetsContract
// Verified against the uploaded TikTok 46.2.0 / BHTikTokPlus build. That build's
// live tab hierarchy is TTKTabBarController + TTKTabBar/TTKFakeTabBar.
static IMP LCTikTok462OriginalControllerDidLayout = NULL;
static const void *LCTikTok462LayoutLogKey = &LCTikTok462LayoutLogKey;
static const void *LCTikTok462LayoutPendingKey = &LCTikTok462LayoutPendingKey;

static UIView *LCTikTok462ViewReturnedBySelector(id object, NSString *selectorName) {
    SEL selector = NSSelectorFromString(selectorName);
    if(!object || ![object respondsToSelector:selector]) return nil;
    IMP implementation = [object methodForSelector:selector];
    if(!implementation) return nil;
    id (*getter)(id, SEL) = (void *)implementation;
    id value = getter(object, selector);
    return [value isKindOfClass:UIView.class] ? value : nil;
}

static NSArray<UIView *> *LCTikTok462AttachedTabBars(UITabBarController *controller) {
    UIWindow *window = controller.view.window;
    if(!window) return @[];

    NSMutableArray<UIView *> *bars = [NSMutableArray array];
    for(NSString *selectorName in @[@"visualTabBar", @"mainTabBar", @"fakeTabBar"]) {
        UIView *candidate = LCTikTok462ViewReturnedBySelector(controller, selectorName);
        if(candidate && candidate.window == window && ![bars containsObject:candidate]) {
            [bars addObject:candidate];
        }
    }

    UIView *standardTabBar = controller.tabBar;
    if(standardTabBar && standardTabBar.window == window && ![bars containsObject:standardTabBar]) {
        [bars addObject:standardTabBar];
    }
    return bars;
}

static UIView *LCTikTok462VisibleTabBar(UITabBarController *controller) {
    for(UIView *candidate in LCTikTok462AttachedTabBars(controller)) {
        if(!candidate.hidden && candidate.alpha > 0.01 && candidate.bounds.size.height > 1.0) {
            return candidate;
        }
    }
    return nil;
}

static void LCTikTok462MoveViewByWindowDeltaY(UIView *view, UIWindow *window, CGFloat deltaY) {
    if(!view.superview || ABS(deltaY) <= 0.5) return;
    CGPoint p0 = [window convertPoint:CGPointZero toView:view.superview];
    CGPoint p1 = [window convertPoint:CGPointMake(0.0, deltaY) toView:view.superview];
    CGRect frame = view.frame;
    frame.origin.y += (p1.y - p0.y);
    view.frame = frame;
}

// Keep TikTok's root surface exactly where TikTok put it. The only direct frame
// correction is applied to TikTok's own tab-bar views. The selected content
// controller then receives the exact bottom exclusion implied by that native bar,
// so captions/search/profile content reflow instead of being dragged with the bar.
static void LCTikTok462ApplyHostedInsetsContract(id object) {
    if(!LCTikTokParallelCompatEnabled() ||
       ![object isKindOfClass:UITabBarController.class]) return;

    UITabBarController *controller = (UITabBarController *)object;
    UIView *rootView = controller.view;
    UIWindow *window = rootView.window;
    if(!rootView || !window) return;

    CGRect hostedViewport = LCParallelSeededViewportBounds();
    if(CGRectIsNull(hostedViewport) ||
       hostedViewport.size.width <= 1.0 || hostedViewport.size.height <= 1.0) return;

    UIView *visibleTabBar = LCTikTok462VisibleTabBar(controller);
    if(!visibleTabBar) return;

    CGRect beforeFrame = [visibleTabBar convertRect:visibleTabBar.bounds toView:window];
    if(CGRectIsNull(beforeFrame) || CGRectIsEmpty(beforeFrame)) return;

    CGFloat hostedBottom = CGRectGetMaxY(hostedViewport);
    CGFloat tabBarBottom = CGRectGetMaxY(beforeFrame);
    CGFloat barDeltaY = hostedBottom - tabBarBottom;

    if(ABS(barDeltaY) > 0.5) {
        for(UIView *bar in LCTikTok462AttachedTabBars(controller)) {
            LCTikTok462MoveViewByWindowDeltaY(bar, window, barDeltaY);
        }
    }

    // Re-read the visible bar after moving TikTok's bar hierarchy. Do not alter the
    // video/feed root frame. Instead tell only the selected child how much bottom
    // space is actually occupied by the now-visible TikTok navigation bar.
    visibleTabBar = LCTikTok462VisibleTabBar(controller) ?: visibleTabBar;
    UIViewController *selected = controller.selectedViewController;
    if(selected && selected.view.window == window) {
        UIView *childView = selected.view;
        CGRect barInChild = [visibleTabBar convertRect:visibleTabBar.bounds toView:childView];
        if(!CGRectIsNull(barInChild) && !CGRectIsEmpty(barInChild)) {
            CGFloat childBottom = CGRectGetMaxY(childView.bounds);
            CGFloat desiredTotalBottomInset = MAX(0.0, childBottom - CGRectGetMinY(barInChild));
            desiredTotalBottomInset = MIN(desiredTotalBottomInset, childView.bounds.size.height * 0.5);

            UIEdgeInsets additional = selected.additionalSafeAreaInsets;
            CGFloat systemBottom = MAX(0.0, childView.safeAreaInsets.bottom - additional.bottom);
            CGFloat desiredAdditionalBottom = MAX(0.0, desiredTotalBottomInset - systemBottom);
            if(ABS(additional.bottom - desiredAdditionalBottom) > 0.5) {
                additional.bottom = desiredAdditionalBottom;
                selected.additionalSafeAreaInsets = additional;
            }
        }
    }

    if(!objc_getAssociatedObject(controller, LCTikTok462LayoutLogKey)) {
        objc_setAssociatedObject(controller, LCTikTok462LayoutLogKey, @YES,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        CGRect afterFrame = [visibleTabBar convertRect:visibleTabBar.bounds toView:window];
        NSLog(@"[FlekDeck] TikTok hosted insets contract bar=%@ before=%@ after=%@ hosted=%@ child=%@",
              NSStringFromClass(visibleTabBar.class), NSStringFromCGRect(beforeFrame),
              NSStringFromCGRect(afterFrame), NSStringFromCGRect(hostedViewport),
              NSStringFromClass(controller.selectedViewController.class));
    }
}

static void LCTikTok462ScheduleLayoutContract(id object) {
    if(!object || objc_getAssociatedObject(object, LCTikTok462LayoutPendingKey)) return;
    objc_setAssociatedObject(object, LCTikTok462LayoutPendingKey, @YES,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    dispatch_async(dispatch_get_main_queue(), ^{
        objc_setAssociatedObject(object, LCTikTok462LayoutPendingKey, nil,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        LCTikTok462ApplyHostedInsetsContract(object);
    });
}

static void LCTikTok462ControllerDidLayout(id object, SEL selector) {
    if(LCTikTok462OriginalControllerDidLayout) {
        ((void (*)(id, SEL))LCTikTok462OriginalControllerDidLayout)(object, selector);
    }

    LCTikTok462ApplyHostedInsetsContract(object);
    LCTikTok462ScheduleLayoutContract(object);
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
        NSLog(@"[FlekDeck] installed TikTok 46.x hosted-insets contract on TTKTabBarController");
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
    "LCTikTok462HostedInsetsContract",
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
    "LCTikTok462AlignRootToHostedViewport",
    "rootView.bounds = bounds",
):
    if forbidden in final_tweak:
        raise SystemExit(f"forbidden obsolete TikTok root/layout logic survived: {forbidden}")

for required in (
    "FlekHomeSingleSwitcherGestureBridge",
    "FlekSingleGuestSwitcherGestureRequested",
    "!hasForegroundAppWindow()",
):
    if required not in final_dock:
        raise SystemExit(f"missing marker: {required}")

print("Applied: TTKTabBarController hosted-insets contract + Single guest switcher bridge")
