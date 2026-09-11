#!/usr/bin/env python3
"""FlekDeck Parallel compatibility boundary.

This runs after the signer-compatible workflow restores the pinned VibeContainers
runtime. It keeps the working Parallel/app-switcher/PiP host path intact while:

1. seeding TikTok's hosted Parallel viewport into LiveProcess before guest bootstrap,
2. virtualizing the screen metrics TikTok is known to consult (including the private
   reference bounds),
3. clamping TikTok's own tab-root/tab-bar layout to that hosted viewport when its
   non-resizable UI ignores the scene resize, and
4. adding a separate bottom-pan bridge for FlekDeck Home + Single mode only.

The Home/Single recognizer explicitly disables itself whenever a hosted Parallel
window is foregrounded, so the existing Parallel MultitaskSwipeZone remains the
only gesture path there.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) LiveProcess: hosted screen geometry + TikTok non-resizable layout shim.
# ---------------------------------------------------------------------------
path = Path("TweakLoader/UIKit+GuestHooks.m")
source = path.read_text()
marker = "LCParallelGuestViewportBridge"

if marker not in source:
    insert_anchor = "BOOL launchURLProcessed = NO;\n\n"
    if insert_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: launchURLProcessed anchor not found")

    bridge = r'''// LCParallelGuestViewportBridge
//
// A LiveProcess guest is hosted inside FlekDeck, not directly on the physical
// panel. TikTok is an outlier that caches display geometry very early and then
// does not reliably relayout its feed when the hosted scene becomes shorter.
// The host therefore seeds TikTok's final Parallel point-size before bootstrap.
static CGRect LCParallelSeededViewportBounds(void) {
    NSDictionary<NSString *, NSString *> *environment = NSProcessInfo.processInfo.environment;
    CGFloat width = [environment[@"LC_PARALLEL_VIEWPORT_WIDTH"] doubleValue];
    CGFloat height = [environment[@"LC_PARALLEL_VIEWPORT_HEIGHT"] doubleValue];
    if(width <= 1 || height <= 1) return CGRectNull;
    return CGRectMake(0, 0, width, height);
}

static BOOL LCParallelSizeMatches(CGSize lhs, CGSize rhs) {
    return ABS(lhs.width - rhs.width) <= 0.5 &&
           ABS(lhs.height - rhs.height) <= 0.5;
}

static CGRect LCParallelHostedViewportBounds(CGRect physicalBounds) {
    if(!NSUserDefaults.isLiveProcess) return CGRectNull;

    CGRect seededBounds = LCParallelSeededViewportBounds();
    UIApplication *application = UIApplication.sharedApplication;
    if(!application) return seededBounds;

    CGSize bestSize = CGSizeZero;
    CGFloat bestArea = 0;

    for(UIScene *scene in application.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class]) continue;
        if(scene.activationState == UISceneActivationStateUnattached) continue;

        UIWindowScene *windowScene = (UIWindowScene *)scene;
        for(UIWindow *window in windowScene.windows) {
            CGSize size = window.bounds.size;
            if(size.width <= 1 || size.height <= 1) continue;

            if(window.isKeyWindow) {
                if(!LCParallelSizeMatches(size, physicalBounds.size)) {
                    return CGRectMake(0, 0, size.width, size.height);
                }
                return seededBounds;
            }

            CGFloat area = size.width * size.height;
            if(area > bestArea) {
                bestArea = area;
                bestSize = size;
            }
        }
    }

    if(bestArea <= 0) return seededBounds;
    if(LCParallelSizeMatches(bestSize, physicalBounds.size)) return seededBounds;
    return CGRectMake(0, 0, bestSize.width, bestSize.height);
}

// LCTikTokParallelLayoutCompat
//
// Upstream LiveContainer already supplies a valid hosted scene frame, but TikTok's
// own tab hierarchy is not resize-safe. If TikTok ignores the scene size, correct
// the two pieces that actually own the full-screen feed: the tab controller root
// and AWETabBar. This is enabled only when the host supplied the TikTok Parallel
// seed; normal TikTok/Single launches and every other guest bypass it completely.
static IMP LCTikTokOriginalTabControllerWillLayout = NULL;
static IMP LCTikTokOriginalTabBarLayout = NULL;

static BOOL LCTikTokParallelCompatEnabled(void) {
    return !CGRectIsNull(LCParallelSeededViewportBounds());
}

static void LCTikTokClampRootController(id object) {
    if(!LCTikTokParallelCompatEnabled() || ![object isKindOfClass:UIViewController.class]) return;
    UIViewController *controller = (UIViewController *)object;
    UIView *view = controller.view;
    if(!view || !view.window) return;

    CGRect seed = LCParallelSeededViewportBounds();
    CGRect frame = view.frame;
    if(ABS(frame.size.width - seed.size.width) <= 0.5 &&
       ABS(frame.size.height - seed.size.height) <= 0.5) return;

    frame.size = seed.size;
    view.frame = frame;
}

static void LCTikTokTabControllerWillLayout(id object, SEL selector) {
    // Set the hosted size before TikTok's own layout pass so its children are
    // computed from the Parallel viewport rather than corrected after the fact.
    LCTikTokClampRootController(object);
    if(LCTikTokOriginalTabControllerWillLayout) {
        ((void (*)(id, SEL))LCTikTokOriginalTabControllerWillLayout)(object, selector);
    }
}

static void LCTikTokAnchorTabBar(id object) {
    if(!LCTikTokParallelCompatEnabled() || ![object isKindOfClass:UIView.class]) return;
    UIView *bar = (UIView *)object;
    UIView *parent = bar.superview;
    UIWindow *window = bar.window;
    if(!parent || !window || bar.bounds.size.height <= 1) return;

    CGRect seed = LCParallelSeededViewportBounds();
    CGPoint seededBottom = [parent convertPoint:CGPointMake(0, CGRectGetMaxY(seed))
                                        fromView:window];
    CGRect frame = bar.frame;
    CGFloat targetY = seededBottom.y - frame.size.height;
    if(ABS(frame.origin.y - targetY) <= 0.5) return;
    frame.origin.y = targetY;
    bar.frame = frame;
}

static void LCTikTokTabBarLayout(id object, SEL selector) {
    if(LCTikTokOriginalTabBarLayout) {
        ((void (*)(id, SEL))LCTikTokOriginalTabBarLayout)(object, selector);
    }
    LCTikTokAnchorTabBar(object);
}

static IMP LCInstallInstanceOverride(Class cls, SEL selector, IMP replacement) {
    Method inheritedOrOwn = class_getInstanceMethod(cls, selector);
    if(!inheritedOrOwn) return NULL;

    IMP original = method_getImplementation(inheritedOrOwn);
    const char *types = method_getTypeEncoding(inheritedOrOwn);
    if(class_addMethod(cls, selector, replacement, types)) {
        // The class inherited the method; our new override calls the inherited IMP.
        return original;
    }

    Method own = class_getInstanceMethod(cls, selector);
    return method_setImplementation(own, replacement);
}

static void LCInstallTikTokParallelLayoutCompat(void) {
    if(!LCTikTokParallelCompatEnabled()) return;

    if(!LCTikTokOriginalTabControllerWillLayout) {
        Class tabController = NSClassFromString(@"AWETabBarController");
        if(tabController) {
            LCTikTokOriginalTabControllerWillLayout =
                LCInstallInstanceOverride(tabController,
                                          @selector(viewWillLayoutSubviews),
                                          (IMP)LCTikTokTabControllerWillLayout);
        }
    }

    if(!LCTikTokOriginalTabBarLayout) {
        Class tabBar = NSClassFromString(@"AWETabBar");
        if(tabBar) {
            LCTikTokOriginalTabBarLayout =
                LCInstallInstanceOverride(tabBar,
                                          @selector(layoutSubviews),
                                          (IMP)LCTikTokTabBarLayout);
        }
    }
}

@implementation UIScreen (LCParallelGuestViewportBridge)
- (CGRect)lc_parallelGuest_bounds {
    CGRect physicalBounds = [self lc_parallelGuest_bounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) return physicalBounds;
    CGRect hostedBounds = LCParallelHostedViewportBounds(physicalBounds);
    return CGRectIsNull(hostedBounds) ? physicalBounds : hostedBounds;
}

- (CGRect)lc_parallelGuest_nativeBounds {
    CGRect physicalNativeBounds = [self lc_parallelGuest_nativeBounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) return physicalNativeBounds;

    CGRect physicalPointBounds = [self lc_parallelGuest_bounds];
    CGRect hostedPointBounds = LCParallelHostedViewportBounds(physicalPointBounds);
    if(CGRectIsNull(hostedPointBounds) ||
       physicalPointBounds.size.width <= 0 || physicalPointBounds.size.height <= 0) {
        return physicalNativeBounds;
    }

    CGFloat xScale = physicalNativeBounds.size.width / physicalPointBounds.size.width;
    CGFloat yScale = physicalNativeBounds.size.height / physicalPointBounds.size.height;
    return CGRectMake(0, 0,
                      hostedPointBounds.size.width * xScale,
                      hostedPointBounds.size.height * yScale);
}

- (CGRect)lc_parallelGuest_referenceBounds {
    // TikTok can bypass public -bounds and use UIKit's display reference rectangle.
    // Keep that private metric in the same hosted coordinate space too.
    CGRect physicalReferenceBounds = [self lc_parallelGuest_referenceBounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) return physicalReferenceBounds;
    CGRect hostedBounds = LCParallelHostedViewportBounds(physicalReferenceBounds);
    return CGRectIsNull(hostedBounds) ? physicalReferenceBounds : hostedBounds;
}
@end

'''
    source = source.replace(insert_anchor, insert_anchor + bridge, 1)

    init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
    if init_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: UIKitGuestHooksInit anchor not found")

    init_replacement = init_anchor + r'''    if(NSUserDefaults.isLiveProcess) {
        swizzle(UIScreen.class, @selector(bounds), @selector(lc_parallelGuest_bounds));
        swizzle(UIScreen.class, @selector(nativeBounds), @selector(lc_parallelGuest_nativeBounds));

        SEL referenceBoundsSelector = NSSelectorFromString(@"_referenceBounds");
        if(class_getInstanceMethod(UIScreen.class, referenceBoundsSelector) &&
           class_getInstanceMethod(UIScreen.class, @selector(lc_parallelGuest_referenceBounds))) {
            swizzle(UIScreen.class,
                    referenceBoundsSelector,
                    @selector(lc_parallelGuest_referenceBounds));
        }

        // Guest classes are normally registered already. The main-queue retry covers
        // TikTok builds that register a UI framework immediately after constructors.
        LCInstallTikTokParallelLayoutCompat();
        dispatch_async(dispatch_get_main_queue(), ^{
            LCInstallTikTokParallelLayoutCompat();
        });
    }
'''
    source = source.replace(init_anchor, init_replacement, 1)
    path.write_text(source)
    print("Applied LiveProcess screen/reference viewport bridge and TikTok layout compatibility")
else:
    print("LiveProcess Parallel viewport bridge already present")

# ---------------------------------------------------------------------------
# 2) Host: seed only TikTok with the intended Parallel viewport.
# ---------------------------------------------------------------------------
path = Path("MultitaskSupport/AppSceneViewController.m")
source = path.read_text()
host_marker = "LCParallelTikTokInitialViewportSeed"

if host_marker not in source:
    item_anchor = "    item.userInfo = userInfo;\n"
    if item_anchor not in source:
        raise SystemExit("AppSceneViewController.m: item.userInfo anchor not found")

    host_seed = r'''    // LCParallelTikTokInitialViewportSeed
    // TikTok can snapshot display geometry before its first UIWindow exists. Resolve
    // the imported bundle metadata rather than relying on FlekDeck's relative path.
    bool viewportSharedApp = false;
    NSBundle *viewportBundle = [LCSharedUtils findBundleWithBundleId:_bundleId
                                                      isSharedAppOut:&viewportSharedApp];
    NSString *viewportBundleID = viewportBundle.bundleIdentifier ?: @"";
    NSString *viewportExecutable =
        [viewportBundle objectForInfoDictionaryKey:@"CFBundleExecutable"] ?: @"";

    BOOL isTikTokGuest =
        [viewportBundleID isEqualToString:@"com.zhiliaoapp.musically"] ||
        [viewportBundleID isEqualToString:@"com.ss.iphone.ugc.Ame"] ||
        [viewportBundleID isEqualToString:@"com.ss.iphone.ugc.trill"] ||
        [viewportExecutable caseInsensitiveCompare:@"TikTok"] == NSOrderedSame;

    if(isTikTokGuest) {
        MultitaskDockManager *dock = MultitaskDockManager.shared;
        UIWindow *hostWindow = dock.windowHostingView.window;

        if(!hostWindow) {
            for(UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
                if(![scene isKindOfClass:UIWindowScene.class]) continue;
                for(UIWindow *candidate in ((UIWindowScene *)scene).windows) {
                    if(candidate.isKeyWindow) {
                        hostWindow = candidate;
                        break;
                    }
                }
                if(hostWindow) break;
            }
        }

        if(hostWindow) {
            [hostWindow layoutIfNeeded];
            [dock.windowHostingView setNeedsLayout];
            [dock.windowHostingView layoutIfNeeded];

            UIEdgeInsets barInsets = dock.barReservedInsets;
            if(dock.barVisible && UIEdgeInsetsEqualToEdgeInsets(barInsets, UIEdgeInsetsZero)) {
                CGFloat thickness = dock.barReservedThickness;
                if(thickness > 0) {
                    if(UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad) {
                        barInsets.bottom = thickness;
                    } else {
                        UIInterfaceOrientation orientation = hostWindow.windowScene.interfaceOrientation;
                        switch(orientation) {
                            case UIInterfaceOrientationLandscapeLeft:
                                barInsets.left = thickness;
                                break;
                            case UIInterfaceOrientationLandscapeRight:
                                barInsets.right = thickness;
                                break;
                            default:
                                barInsets.bottom = thickness;
                                break;
                        }
                    }
                }
            }

            CGRect seededViewport = UIEdgeInsetsInsetRect(hostWindow.bounds, barInsets);
            if(seededViewport.size.width > 1 && seededViewport.size.height > 1) {
                userInfo[@"parallelInitialViewportWidth"] = @(seededViewport.size.width);
                userInfo[@"parallelInitialViewportHeight"] = @(seededViewport.size.height);
                NSLog(@"[FlekDeck] TikTok Parallel initial viewport seed %@",
                      NSStringFromCGSize(seededViewport.size));
            }
        }
    }

'''
    source = source.replace(item_anchor, host_seed + item_anchor, 1)
    path.write_text(source)
    print("Added TikTok Parallel initial viewport seed")
else:
    print("TikTok Parallel initial viewport seed already present")

# ---------------------------------------------------------------------------
# 3) LiveProcess: publish the seed before LiveContainerMain loads the guest.
# ---------------------------------------------------------------------------
path = Path("LiveProcess/main.m")
source = path.read_text()
live_marker = "LCParallelTikTokInitialViewportEnvironment"

if live_marker not in source:
    app_info_anchor = (
        '    NSDictionary *appInfo = LiveProcessHandler.retrievedAppInfo;\n'
        '    NSCAssert(appInfo, @"Failed to retrieve app info");\n'
    )
    if app_info_anchor not in source:
        raise SystemExit("LiveProcess/main.m: appInfo anchor not found")

    env_seed = r'''
    // LCParallelTikTokInitialViewportEnvironment
    // Process-local and cleared on every request: a TikTok viewport can never leak
    // into another guest if the extension process is reused.
    unsetenv("LC_PARALLEL_VIEWPORT_WIDTH");
    unsetenv("LC_PARALLEL_VIEWPORT_HEIGHT");

    NSNumber *parallelViewportWidth = appInfo[@"parallelInitialViewportWidth"];
    NSNumber *parallelViewportHeight = appInfo[@"parallelInitialViewportHeight"];
    if(parallelViewportWidth.doubleValue > 1 && parallelViewportHeight.doubleValue > 1) {
        setenv("LC_PARALLEL_VIEWPORT_WIDTH",
               parallelViewportWidth.stringValue.UTF8String, 1);
        setenv("LC_PARALLEL_VIEWPORT_HEIGHT",
               parallelViewportHeight.stringValue.UTF8String, 1);
        NSLog(@"LiveProcess: seeded early Parallel viewport %@x%@",
              parallelViewportWidth, parallelViewportHeight);
    }

'''
    source = source.replace(app_info_anchor, app_info_anchor + env_seed, 1)
    path.write_text(source)
    print("Propagated Parallel initial viewport seed into LiveProcess environment")
else:
    print("Parallel initial viewport environment already present")

# ---------------------------------------------------------------------------
# 4) Home + Single: separate key-window bottom pan. Parallel is explicitly excluded.
# ---------------------------------------------------------------------------
path = Path("MultitaskSupport/MultitaskDockView.swift")
source = path.read_text()
gesture_marker = "FlekHomeSingleSwitcherGestureBridge"

if gesture_marker not in source:
    helper_anchor = "    private func frontmostAppName() -> String {\n"
    if helper_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: frontmostAppName anchor not found")

    helper = r'''    // FlekHomeSingleSwitcherGestureBoundary
    // Home and Single do not live inside the hosted Parallel window hierarchy, so
    // Parallel's MultitaskSwipeZone cannot receive their bottom-edge gesture. Keep
    // this as a separate recognizer and turn it off whenever Parallel owns the stage.
    fileprivate var canUseHomeSingleSwitcherGesture: Bool {
        guard isDockEnabled(), isSwipeZoneEnabled else { return false }
        guard !isAppSwitcherOpen, !isOpeningAppSwitcher else { return false }
        return !hasForegroundAppWindow()
    }

    fileprivate func openSwitcherFromHomeSingleGesture() {
        guard canUseHomeSingleSwitcherGesture else { return }
        Self.buttonHaptic()
        showAppSwitcher()
    }

'''
    source = source.replace(helper_anchor, helper + helper_anchor, 1)

    sentinel_anchor = "        if let win = keyWindow { attachSafeAreaSentinel(to: win) }\n"
    if sentinel_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: startup key-window anchor not found")
    sentinel_replacement = r'''        if let win = keyWindow {
            attachSafeAreaSentinel(to: win)
            FlekHomeSingleSwitcherGestureBridge.shared.install(on: win)
        }
'''
    source = source.replace(sentinel_anchor, sentinel_replacement, 1)

    observer_anchor = r'''        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appDidBecomeActive),
            name: UIApplication.didBecomeActiveNotification,
            object: nil
        )
'''
    if observer_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: foreground observer anchor not found")
    observer_replacement = observer_anchor + r'''        // Single mode can make a guest-created UIWindow key without entering the
        // Parallel host hierarchy. Follow the key window so the same bottom swipe is
        // available there and on FlekDeck Home.
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(homeSingleKeyWindowChanged(_:)),
            name: UIWindow.didBecomeKeyNotification,
            object: nil
        )
'''
    source = source.replace(observer_anchor, observer_replacement, 1)

    active_anchor = "    @objc private func appDidBecomeActive() {\n"
    if active_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: appDidBecomeActive anchor not found")
    active_prefix = r'''    @objc private func homeSingleKeyWindowChanged(_ notification: Notification) {
        guard let window = notification.object as? UIWindow,
              !(window is MultitaskOverlayWindow) else { return }
        FlekHomeSingleSwitcherGestureBridge.shared.install(on: window)
    }

'''
    source = source.replace(active_anchor, active_prefix + active_anchor, 1)

    zone_anchor = "@available(iOS 16.0, *)\nfinal class MultitaskSwipeZone: UIView {\n"
    if zone_anchor not in source:
        raise SystemExit("MultitaskDockView.swift: MultitaskSwipeZone anchor not found")

    bridge_class = r'''@available(iOS 16.0, *)
final class FlekHomeSingleSwitcherGestureBridge: NSObject, UIGestureRecognizerDelegate {
    static let shared = FlekHomeSingleSwitcherGestureBridge()

    private weak var window: UIWindow?
    private weak var pan: UIPanGestureRecognizer?

    func install(on window: UIWindow) {
        guard !(window is MultitaskOverlayWindow) else { return }
        if self.window === window, pan?.view === window { return }

        if let oldPan = pan {
            oldPan.view?.removeGestureRecognizer(oldPan)
        }

        let recognizer = UIPanGestureRecognizer(target: self, action: #selector(handle(_:)))
        recognizer.maximumNumberOfTouches = 1
        recognizer.cancelsTouchesInView = false
        recognizer.delaysTouchesBegan = false
        recognizer.delaysTouchesEnded = false
        recognizer.delegate = self
        window.addGestureRecognizer(recognizer)

        self.window = window
        self.pan = recognizer
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard MultitaskDockManager.shared.canUseHomeSingleSwitcherGesture,
              let recognizer = gestureRecognizer as? UIPanGestureRecognizer,
              let window else { return false }

        let point = recognizer.location(in: window)
        let bottomBand = max(window.safeAreaInsets.bottom + 30, 64)
        guard point.y >= window.bounds.maxY - bottomBand else { return false }

        let velocity = recognizer.velocity(in: window)
        return velocity.y < -80 && abs(velocity.y) > abs(velocity.x)
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                           shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        true
    }

    @objc private func handle(_ recognizer: UIPanGestureRecognizer) {
        guard recognizer.state == .ended,
              MultitaskDockManager.shared.canUseHomeSingleSwitcherGesture,
              let window else { return }

        let translation = recognizer.translation(in: window).y
        let velocity = recognizer.velocity(in: window).y
        guard -translation >= 16 || velocity <= -300 else { return }
        MultitaskDockManager.shared.openSwitcherFromHomeSingleGesture()
    }
}

'''
    source = source.replace(zone_anchor, bridge_class + zone_anchor, 1)
    path.write_text(source)
    print("Added Home/Single switcher pan without modifying Parallel's swipe zone")
else:
    print("Home/Single switcher gesture bridge already present")

# Fail closed on the boundaries this experiment is supposed to preserve.
tweak = Path("TweakLoader/UIKit+GuestHooks.m").read_text()
dock = Path("MultitaskSupport/MultitaskDockView.swift").read_text()
for required in (
    "LCParallelGuestViewportBridge",
    "lc_parallelGuest_referenceBounds",
    "LCTikTokParallelLayoutCompat",
):
    if required not in tweak:
        raise SystemExit(f"TikTok Parallel compatibility marker missing: {required}")
for required in (
    "FlekHomeSingleSwitcherGestureBridge",
    "canUseHomeSingleSwitcherGesture",
    "return !hasForegroundAppWindow()",
):
    if required not in dock:
        raise SystemExit(f"Home/Single switcher marker missing: {required}")

print("Parallel gesture path preserved; Home/Single gesture and TikTok compatibility layers applied")
