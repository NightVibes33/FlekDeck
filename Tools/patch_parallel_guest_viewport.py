#!/usr/bin/env python3
"""Seed TikTok's Parallel viewport before the guest creates its first UIWindow.

TikTok is an outlier in LiveContainer multitasking: it can commit the For You
feed viewport from very early UIScreen metrics and does not reliably recompute
that viewport when the hosted scene becomes shorter later.

Keep FlekDeck's normal Parallel/window/switcher/PiP lifecycle untouched. For
TikTok only, the host sends the final Parallel point-size with the LiveProcess
request. LiveProcess places that size in process-local environment variables
before LiveContainerMain loads the guest. TweakLoader's UIScreen bridge can then
answer the hosted size even before the guest has a UIWindow; once a real hosted
window exists, its bounds remain authoritative.

Other guests receive no seed and retain the generic existing behavior.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) LiveProcess UIScreen bridge: use the host-provided seed before UIWindow.
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
// panel. Usually the first guest UIWindow is enough to tell us the hosted size.
// TikTok is different: it reads screen geometry before that UIWindow exists and
// caches the feed viewport. The host therefore seeds TikTok's final Parallel
// point-size in process-local environment variables before guest bootstrap.
//
// The seed is only present for TikTok. Once a real guest window has a hosted
// (non-physical) size, the real window wins.
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
                // A genuinely hosted key window is authoritative. A key window
                // that still reports the physical panel is the early TikTok case:
                // keep returning the seed until UIKit catches up.
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
    if(LCParallelSizeMatches(bestSize, physicalBounds.size)) {
        return seededBounds;
    }
    return CGRectMake(0, 0, bestSize.width, bestSize.height);
}

@implementation UIScreen (LCParallelGuestViewportBridge)
- (CGRect)lc_parallelGuest_bounds {
    // After method exchange this selector reaches UIKit's original -bounds.
    CGRect physicalBounds = [self lc_parallelGuest_bounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) {
        return physicalBounds;
    }

    CGRect hostedBounds = LCParallelHostedViewportBounds(physicalBounds);
    return CGRectIsNull(hostedBounds) ? physicalBounds : hostedBounds;
}

- (CGRect)lc_parallelGuest_nativeBounds {
    // Keep pixel geometry consistent with the point geometry above. This catches
    // code that snapshots nativeBounds at process startup instead of -bounds.
    CGRect physicalNativeBounds = [self lc_parallelGuest_nativeBounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) {
        return physicalNativeBounds;
    }

    // The exchanged selector reaches UIKit's original -bounds, so this is the
    // physical point-space denominator rather than our overridden answer.
    CGRect physicalPointBounds = [self lc_parallelGuest_bounds];
    CGRect hostedPointBounds = LCParallelHostedViewportBounds(physicalPointBounds);
    if(CGRectIsNull(hostedPointBounds) ||
       physicalPointBounds.size.width <= 0 ||
       physicalPointBounds.size.height <= 0) {
        return physicalNativeBounds;
    }

    CGFloat xScale = physicalNativeBounds.size.width / physicalPointBounds.size.width;
    CGFloat yScale = physicalNativeBounds.size.height / physicalPointBounds.size.height;
    return CGRectMake(0, 0,
                      hostedPointBounds.size.width * xScale,
                      hostedPointBounds.size.height * yScale);
}
@end

'''
    source = source.replace(insert_anchor, insert_anchor + bridge, 1)

    init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
    if init_anchor not in source:
        raise SystemExit("UIKit+GuestHooks.m: UIKitGuestHooksInit anchor not found")

    init_replacement = (
        init_anchor
        + "    if(NSUserDefaults.isLiveProcess) {\n"
        + "        swizzle(UIScreen.class, @selector(bounds), @selector(lc_parallelGuest_bounds));\n"
        + "        swizzle(UIScreen.class, @selector(nativeBounds), @selector(lc_parallelGuest_nativeBounds));\n"
        + "    }\n"
    )
    source = source.replace(init_anchor, init_replacement, 1)
    path.write_text(source)
    print("Applied early LiveProcess UIScreen viewport bridge")
else:
    print("LiveProcess UIScreen viewport bridge already present")

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
    //
    // TikTok can snapshot UIScreen before its first UIWindow exists. Give only
    // TikTok the final Parallel point-size up front; every other guest keeps the
    // standard LiveContainer path.
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
            if(dock.barVisible &&
               UIEdgeInsetsEqualToEdgeInsets(barInsets, UIEdgeInsetsZero)) {
                CGFloat thickness = dock.barReservedThickness;
                if(thickness > 0) {
                    if(UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad) {
                        barInsets.bottom = thickness;
                    } else {
                        UIInterfaceOrientation orientation =
                            hostWindow.windowScene.interfaceOrientation;
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
    // Process-local and cleared on every request: a TikTok viewport can never
    // leak into another guest if the extension process is reused.
    unsetenv("LC_PARALLEL_VIEWPORT_WIDTH");
    unsetenv("LC_PARALLEL_VIEWPORT_HEIGHT");

    NSNumber *parallelViewportWidth = appInfo[@"parallelInitialViewportWidth"];
    NSNumber *parallelViewportHeight = appInfo[@"parallelInitialViewportHeight"];
    if(parallelViewportWidth.doubleValue > 1 &&
       parallelViewportHeight.doubleValue > 1) {
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
