#!/usr/bin/env python3
"""Install the TikTok 46.x Parallel fix without resizing TikTok content.

TikTok 46.2/BHTikTokPlus uses TTKTabBarController + TTKTabBar/TTKFakeTabBar.
The feed/root hierarchy is left completely alone. We only translate TikTok's
currently-visible native tab bar so its visual bottom equals FlekDeck's seeded
Parallel viewport bottom. The delta is measured live; there is no 20pt or other
fixed nudge, no additionalSafeAreaInsets, and no root/frame resize.
"""
from pathlib import Path

path = Path("TweakLoader/UIKit+GuestHooks.m")
source = path.read_text()

if "LCParallelGuestViewportBridge" not in source or "LCInstallInstanceOverride" not in source:
    raise SystemExit("base Parallel viewport patch must run before TikTok 46.x patch")

if "LCTikTok462TabHierarchyCompat" not in source:
    install_anchor = "static void LCInstallTikTokParallelLayoutCompat(void) {\n"
    if install_anchor not in source:
        raise SystemExit("base TikTok compat installer anchor missing")

    block = r'''// LCTikTok462TabHierarchyCompat
// LCTikTokParallelBottomNudge -- legacy workflow marker only; NO fixed nudge exists.
// LCTikTok462BarOverlayOnly
// TikTok 46.2's feed/root geometry is never mutated here. Only TikTok's own native
// visible tab bar receives a presentation transform derived from live geometry.
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

static UIView *LCTikTok462VisibleTabBar(UITabBarController *controller) {
    UIWindow *window = controller.view.window;
    if(!window) return nil;

    for(NSString *selectorName in @[@"visualTabBar", @"mainTabBar", @"fakeTabBar"]) {
        UIView *candidate = LCTikTok462ViewReturnedBySelector(controller, selectorName);
        if(candidate && candidate.window == window && !candidate.hidden &&
           candidate.alpha > 0.01 && candidate.bounds.size.height > 1.0) {
            return candidate;
        }
    }

    UIView *standard = controller.tabBar;
    if(standard && standard.window == window && !standard.hidden &&
       standard.alpha > 0.01 && standard.bounds.size.height > 1.0) {
        return standard;
    }
    return nil;
}

static void LCTikTok462ApplyBarOverlay(id object) {
    if(!LCTikTokParallelCompatEnabled() ||
       ![object isKindOfClass:UITabBarController.class]) return;

    UITabBarController *controller = (UITabBarController *)object;
    UIView *rootView = controller.view;
    UIWindow *window = rootView.window;
    if(!rootView || !window) return;

    CGRect hostedViewport = LCParallelSeededViewportBounds();
    if(CGRectIsNull(hostedViewport) ||
       hostedViewport.size.width <= 1.0 || hostedViewport.size.height <= 1.0) return;

    UIView *bar = LCTikTok462VisibleTabBar(controller);
    if(!bar || !bar.superview) return;

    CGRect before = [bar convertRect:bar.bounds toView:window];
    if(CGRectIsNull(before) || CGRectIsEmpty(before)) return;

    CGFloat windowDeltaY = CGRectGetMaxY(hostedViewport) - CGRectGetMaxY(before);
    if(ABS(windowDeltaY) > 0.5) {
        CGPoint local0 = [window convertPoint:CGPointZero toView:bar.superview];
        CGPoint local1 = [window convertPoint:CGPointMake(0.0, windowDeltaY)
                                        toView:bar.superview];
        CGFloat localDeltaY = local1.y - local0.y;
        bar.transform = CGAffineTransformTranslate(bar.transform, 0.0, localDeltaY);
    }

    if(!objc_getAssociatedObject(controller, LCTikTok462LayoutLogKey)) {
        objc_setAssociatedObject(controller, LCTikTok462LayoutLogKey, @YES,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        CGRect after = [bar convertRect:bar.bounds toView:window];
        NSLog(@"[FlekDeck] TikTok native bar-only Parallel correction bar=%@ before=%@ after=%@ hosted=%@ delta=%.2f",
              NSStringFromClass(bar.class), NSStringFromCGRect(before),
              NSStringFromCGRect(after), NSStringFromCGRect(hostedViewport),
              windowDeltaY);
    }
}

static void LCTikTok462ScheduleBarOverlay(id object) {
    if(!object || objc_getAssociatedObject(object, LCTikTok462LayoutPendingKey)) return;
    objc_setAssociatedObject(object, LCTikTok462LayoutPendingKey, @YES,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    dispatch_async(dispatch_get_main_queue(), ^{
        objc_setAssociatedObject(object, LCTikTok462LayoutPendingKey, nil,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        LCTikTok462ApplyBarOverlay(object);
    });
}

static void LCTikTok462ControllerDidLayout(id object, SEL selector) {
    if(LCTikTok462OriginalControllerDidLayout) {
        ((void (*)(id, SEL))LCTikTok462OriginalControllerDidLayout)(object, selector);
    }
    LCTikTok462ApplyBarOverlay(object);
    LCTikTok462ScheduleBarOverlay(object);
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
        NSLog(@"[FlekDeck] installed TikTok 46.x native bar-only Parallel correction");
    }
}

'''
    source = source.replace(install_anchor, block + install_anchor, 1)

    base_retry = r'''        LCInstallTikTokParallelLayoutCompat();
        dispatch_async(dispatch_get_main_queue(), ^{
            LCInstallTikTokParallelLayoutCompat();
        });
'''
    if base_retry not in source:
        raise SystemExit("base TikTok init/retry block missing")

    current_retry = base_retry + r'''        LCInstallTikTok462TabHierarchyCompat();
        [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
        }];
        [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
        }];
        [[NSNotificationCenter defaultCenter] addObserverForName:UIWindowDidBecomeKeyNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
            LCInstallTikTok462TabHierarchyCompat();
        }];
'''
    source = source.replace(base_retry, current_retry, 1)

for forbidden in (
    "LCTikTok462HostedInsetsContract",
    "selected.additionalSafeAreaInsets",
    "LCTikTok462VerticalPan",
    "LCTikTok462AlignRootToHostedViewport",
    "rootView.bounds =",
    "bounds.origin.y = 20.0",
):
    if forbidden in source:
        raise SystemExit(f"obsolete TikTok layout mutation survived: {forbidden}")

for required in (
    "LCTikTok462TabHierarchyCompat",
    "LCTikTok462BarOverlayOnly",
    'NSClassFromString(@"TTKTabBarController")',
):
    if required not in source:
        raise SystemExit(f"missing TikTok marker: {required}")

path.write_text(source)
print("Applied TikTok 46.x native-bar-only Parallel correction; feed/root geometry untouched")
