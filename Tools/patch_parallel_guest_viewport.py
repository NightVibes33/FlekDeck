#!/usr/bin/env python3
"""Keep LiveProcess guests from seeing the physical screen as their hosted viewport.

The signer-compatible workflow intentionally restores VibeContainers' TweakLoader
sources before building, so this patch is applied after that copy. It is generic:
all LiveProcess guests get the bounds of their actual hosted UIWindow when it is
different from UIScreen.mainScreen.bounds; normal in-process launches and
full-screen-equivalent guests keep UIKit's original answer.
"""
from pathlib import Path

PATH = Path("TweakLoader/UIKit+GuestHooks.m")
MARKER = "LCParallelGuestViewportBridge"

source = PATH.read_text()
if MARKER in source:
    print("Parallel guest viewport bridge already present")
    raise SystemExit(0)

insert_anchor = "BOOL launchURLProcessed = NO;\n\n"
if insert_anchor not in source:
    raise SystemExit("UIKit+GuestHooks.m: launchURLProcessed anchor not found")

bridge = r'''// LCParallelGuestViewportBridge
//
// A LiveProcess guest is not the physical display: its UIWindowScene is hosted in
// FlekDeck's Parallel rectangle. UIKit gives the remote scene the right frame,
// but UIScreen.mainScreen.bounds still describes the iPhone itself. Apps that
// later derive a page/feed viewport from UIScreen can therefore replace a correct
// first layout with a physical-screen-sized one and get clipped by the host.
//
// Use an actual guest UIWindow as the source of truth. We deliberately do not
// invent a size before a window exists, and we leave full-screen-equivalent
// windows alone. That keeps bootstrap behaviour identical and makes this a
// generic hosted-scene invariant rather than an app-specific workaround.
static CGRect LCParallelHostedViewportBounds(CGRect physicalBounds) {
    if(!NSUserDefaults.isLiveProcess) return CGRectNull;

    UIApplication *application = UIApplication.sharedApplication;
    if(!application) return CGRectNull;

    CGSize bestSize = CGSizeZero;
    CGFloat bestArea = 0;

    for(UIScene *scene in application.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class]) continue;
        if(scene.activationState == UISceneActivationStateUnattached) continue;

        UIWindowScene *windowScene = (UIWindowScene *)scene;
        for(UIWindow *window in windowScene.windows) {
            CGSize size = window.bounds.size;
            if(size.width <= 1 || size.height <= 1) continue;

            // The key window is the app's active viewport and is the strongest
            // answer. If UIKit has not chosen one yet, retain the largest valid
            // window; transient panels/alerts cannot then shrink the screen.
            if(window.isKeyWindow) {
                CGRect hosted = CGRectMake(0, 0, size.width, size.height);
                if(ABS(hosted.size.width - physicalBounds.size.width) > 0.5 ||
                   ABS(hosted.size.height - physicalBounds.size.height) > 0.5) {
                    return hosted;
                }
                return CGRectNull;
            }

            CGFloat area = size.width * size.height;
            if(area > bestArea) {
                bestArea = area;
                bestSize = size;
            }
        }
    }

    if(bestArea <= 0) return CGRectNull;
    if(ABS(bestSize.width - physicalBounds.size.width) <= 0.5 &&
       ABS(bestSize.height - physicalBounds.size.height) <= 0.5) {
        return CGRectNull;
    }
    return CGRectMake(0, 0, bestSize.width, bestSize.height);
}

@implementation UIScreen (LCParallelGuestViewportBridge)
- (CGRect)lc_parallelGuest_bounds {
    // After swizzling this selector reaches UIKit's original -bounds.
    CGRect physicalBounds = [self lc_parallelGuest_bounds];
    if(!NSUserDefaults.isLiveProcess || self != UIScreen.mainScreen) {
        return physicalBounds;
    }

    CGRect hostedBounds = LCParallelHostedViewportBounds(physicalBounds);
    return CGRectIsNull(hostedBounds) ? physicalBounds : hostedBounds;
}
@end

'''
source = source.replace(insert_anchor, insert_anchor + bridge, 1)

init_anchor = "static void UIKitGuestHooksInit() {\n    if(!NSUserDefaults.lcGuestAppId) return;\n"
if init_anchor not in source:
    raise SystemExit("UIKit+GuestHooks.m: UIKitGuestHooksInit anchor not found")

init_replacement = init_anchor + "    if(NSUserDefaults.isLiveProcess) {\n        swizzle(UIScreen.class, @selector(bounds), @selector(lc_parallelGuest_bounds));\n    }\n"
source = source.replace(init_anchor, init_replacement, 1)

PATH.write_text(source)
print("Applied generic LiveProcess UIScreen viewport bridge")
