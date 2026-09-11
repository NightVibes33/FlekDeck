#!/usr/bin/env python3
"""Replace the TikTok 46.x post-layout experiment with a bar-only visual correction.

The previous experiment moved TikTok's tab bar *and* injected a bottom
additionalSafeAreaInset into the selected child. On TikTok 46.2 that causes the
feed/video container to recompute against a shorter content area, which is what
produced the large black top/bottom bands seen on-device.

This patch deliberately does less:
  * never changes TTKTabBarController/root bounds or frame,
  * never changes any child safe-area inset,
  * never resizes the hosted scene,
  * never uses a fixed point offset,
  * only translates TikTok's currently visible native TTK tab-bar view so its
    visual bottom matches the host-provided Parallel viewport bottom.

The correction is derived from live geometry every layout pass. Because it is a
view transform, TikTok's Auto Layout/feed sizing does not receive a new content
rectangle and therefore cannot letterbox the video in response.
"""
from pathlib import Path
import re

path = Path("TweakLoader/UIKit+GuestHooks.m")
source = path.read_text()

if "LCTikTok462TabHierarchyCompat" not in source:
    raise SystemExit("TikTok 46.x compatibility block is missing")

start = "static void LCTikTok462ApplyHostedInsetsContract(id object) {"
end = "static void LCTikTok462ScheduleLayoutContract(id object) {"
if start not in source or end not in source:
    raise SystemExit("TikTok hosted-insets function anchors are missing")

replacement = r'''// LCTikTok462BarOverlayOnly
// Keep TikTok's feed/root hierarchy exactly as it laid itself out. The only
// compatibility operation here is a visual translation of TikTok's *own*
// currently-visible native tab bar. No safe-area, root-bounds, frame-size or
// fixed-point correction is applied.
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
    if(!visibleTabBar || !visibleTabBar.superview) return;

    CGRect beforeFrame = [visibleTabBar convertRect:visibleTabBar.bounds toView:window];
    if(CGRectIsNull(beforeFrame) || CGRectIsEmpty(beforeFrame)) return;

    CGFloat hostedBottom = CGRectGetMaxY(hostedViewport);
    CGFloat tabBarBottom = CGRectGetMaxY(beforeFrame);
    CGFloat windowDeltaY = hostedBottom - tabBarBottom;

    if(ABS(windowDeltaY) > 0.5) {
        // Convert the required window-space correction into the tab bar's
        // superview coordinate system, then compose it into the presentation
        // transform. This does not mutate frame/bounds and therefore does not
        // participate in TikTok's own layout calculations.
        CGPoint local0 = [window convertPoint:CGPointZero toView:visibleTabBar.superview];
        CGPoint local1 = [window convertPoint:CGPointMake(0.0, windowDeltaY)
                                        toView:visibleTabBar.superview];
        CGFloat localDeltaY = local1.y - local0.y;
        visibleTabBar.transform = CGAffineTransformTranslate(visibleTabBar.transform,
                                                             0.0,
                                                             localDeltaY);
    }

    if(!objc_getAssociatedObject(controller, LCTikTok462LayoutLogKey)) {
        objc_setAssociatedObject(controller, LCTikTok462LayoutLogKey, @YES,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        CGRect afterFrame = [visibleTabBar convertRect:visibleTabBar.bounds toView:window];
        NSLog(@"[FlekDeck] TikTok native bar-only Parallel correction bar=%@ before=%@ after=%@ hosted=%@ delta=%.2f",
              NSStringFromClass(visibleTabBar.class), NSStringFromCGRect(beforeFrame),
              NSStringFromCGRect(afterFrame), NSStringFromCGRect(hostedViewport),
              windowDeltaY);
    }
}

'''

pattern = re.compile(
    re.escape(start) + r".*?(?=" + re.escape(end) + r")",
    re.S,
)
source, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise SystemExit(f"expected to replace one TikTok hosted-insets function, got {count}")

# Rename the experiment marker so CI can prove the bad contract is no longer in
# the compiled source rather than merely assuming a later patch won.
source = source.replace("// LCTikTok462HostedInsetsContract\n", "")

if "LCTikTok462BarOverlayOnly" not in source:
    raise SystemExit("bar-only TikTok marker was not installed")
if "LCTikTok462HostedInsetsContract" in source:
    raise SystemExit("obsolete TikTok hosted-insets marker survived")
if "selected.additionalSafeAreaInsets" in source:
    raise SystemExit("obsolete TikTok selected-child safe-area mutation survived")
if "rootView.bounds =" in source:
    raise SystemExit("obsolete TikTok root-bounds mutation survived")
if "LCTikTok462VerticalPan" in source or "bounds.origin.y = 20.0" in source:
    raise SystemExit("obsolete fixed TikTok pan survived")

path.write_text(source)
print("Applied TikTok 46.x native-bar-only Parallel correction; feed/root geometry untouched")
