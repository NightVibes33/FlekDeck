#!/usr/bin/env python3
"""Run #65 compatibility, then refine Single switcher + TikTok Parallel vertical fit."""
from pathlib import Path
import runpy

runpy.run_path("Tools/patch_parallel_guest_viewport_base.py", run_name="__main__")

# TikTok Parallel: preserve the exact hosted viewport size and aspect ratio. The
# residual bug is positional, not dimensional: TikTok's own hierarchy sits a little
# too low. Translate it upward 20pt without changing width/height/scale.
tweak_path = Path("TweakLoader/UIKit+GuestHooks.m")
tweak = tweak_path.read_text()
compat_anchor = r'''static BOOL LCTikTokParallelCompatEnabled(void) {
    return !CGRectIsNull(LCParallelSeededViewportBounds());
}
'''
if "LCTikTokParallelBottomNudge" not in tweak:
    if compat_anchor not in tweak:
        raise SystemExit("TikTok compat enable anchor missing after base patch")
    tweak = tweak.replace(compat_anchor, compat_anchor + r'''
// LCTikTokParallelBottomNudge
static CGRect LCTikTokAdjustedParallelViewportBounds(void) {
    CGRect seed = LCParallelSeededViewportBounds();
    if(CGRectIsNull(seed)) return seed;
    const CGFloat verticalShift = 20.0;
    seed.origin.y -= verticalShift;
    return seed;
}
''', 1)

    old = "    CGRect seed = LCParallelSeededViewportBounds();\n"
    new = "    CGRect seed = LCTikTokAdjustedParallelViewportBounds();\n"
    for function_name in ("static void LCTikTokClampRootController", "static void LCTikTokAnchorTabBar"):
        start = tweak.index(function_name)
        end = tweak.index("\n}\n", start) + 3
        block = tweak[start:end]
        if old not in block:
            raise SystemExit(f"TikTok layout seed missing in {function_name}")
        block = block.replace(old, new, 1)

        if function_name == "static void LCTikTokClampRootController":
            old_logic = '''    if(ABS(frame.size.width - seed.size.width) <= 0.5 &&
       ABS(frame.size.height - seed.size.height) <= 0.5) return;

    frame.size = seed.size;
    view.frame = frame;
'''
            new_logic = '''    BOOL sizeMatches = ABS(frame.size.width - seed.size.width) <= 0.5 &&
                       ABS(frame.size.height - seed.size.height) <= 0.5;
    BOOL originMatches = ABS(frame.origin.y - seed.origin.y) <= 0.5;
    if(sizeMatches && originMatches) return;

    frame.origin.y = seed.origin.y;
    frame.size = seed.size;
    view.frame = frame;
'''
            if old_logic not in block:
                raise SystemExit("TikTok root clamp logic missing")
            block = block.replace(old_logic, new_logic, 1)

        tweak = tweak[:start] + block + tweak[end:]

# Single mode: install the gesture inside the actual in-process guest window and
# post back to FlekDeck's existing switcher manager. Parallel never installs this.
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

# Host receiver for the Single guest gesture. Parallel is still excluded by the
# existing hosted-window check, so its proven swipe zone remains untouched.
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
for required in ("LCParallelGuestViewportBridge", "LCTikTokParallelLayoutCompat", "LCTikTokParallelBottomNudge", "LCSingleGuestSwitcherGestureBridge"):
    if required not in final_tweak: raise SystemExit(f"missing marker: {required}")
for required in ("FlekHomeSingleSwitcherGestureBridge", "FlekSingleGuestSwitcherGestureRequested", "!hasForegroundAppWindow()"):
    if required not in final_dock: raise SystemExit(f"missing marker: {required}")
print("Applied: Single guest switcher bridge + TikTok Parallel 20pt pure upward translation")
