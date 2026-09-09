from pathlib import Path


path = Path("TweakLoader/UIKit+GuestHooks.m")
source = path.read_text(encoding="utf-8")

constructor_anchor = """    if(!NSUserDefaults.lcGuestAppId) return;
    swizzle(UIApplication.class, @selector(_applicationOpenURLAction:payload:origin:), @selector(hook__applicationOpenURLAction:payload:origin:));
"""
constructor_replacement = """    if(!NSUserDefaults.lcGuestAppId) return;

    // TikTok caches UIScreen.mainScreen.bounds while constructing its feed. In a
    // LiveProcess hosted scene that is the physical host screen, not the smaller
    // Parallel guest viewport above FlekDeck's switcher. The feed then remains
    // screen-height even though its UIWindow is shorter, clipping the bottom tabs.
    // YouTube asks its UIWindow/scene for geometry and therefore never exposes it.
    NSString *guestId = NSUserDefaults.lcGuestAppId.lowercaseString;
    BOOL isTikTok = [guestId containsString:@"musically"] ||
                    [guestId containsString:@"tiktok"] ||
                    [guestId containsString:@"aweme"];
    if(NSUserDefaults.isLiveProcess && isTikTok) {
        swizzle(UIScreen.class, @selector(bounds), @selector(lcParallelTikTok_bounds));
    }

    swizzle(UIApplication.class, @selector(_applicationOpenURLAction:payload:origin:), @selector(hook__applicationOpenURLAction:payload:origin:));
"""

if constructor_anchor not in source:
    if "lcParallelTikTok_bounds" in source:
        print("TikTok Parallel viewport hook already present")
        raise SystemExit(0)
    raise SystemExit("UIKit guest hook constructor anchor not found")

implementation_anchor = """NSString* findDefaultContainerWithBundleId(NSString* bundleId) {
"""
implementation = """@implementation UIScreen (LCParallelTikTokViewport)

- (CGRect)lcParallelTikTok_bounds {
    // After swizzling this calls UIScreen's original -bounds implementation.
    CGRect physicalBounds = [self lcParallelTikTok_bounds];

    // Prefer the foreground guest window. It is already sized by the hosted
    // scene and excludes the switcher strip. Avoid UIApplication.keyWindow: an
    // alert or keyboard window can temporarily become key and report nonsense.
    for(UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if(![scene isKindOfClass:UIWindowScene.class] ||
           scene.activationState == UISceneActivationStateUnattached) continue;
        UIWindowScene *windowScene = (UIWindowScene *)scene;
        for(UIWindow *window in windowScene.windows) {
            CGRect bounds = window.bounds;
            if(!window.hidden && bounds.size.width > 0 && bounds.size.height > 0 &&
               window.windowLevel == UIWindowLevelNormal) {
                return CGRectMake(0, 0, bounds.size.width, bounds.size.height);
            }
        }
        CGRect sceneBounds = windowScene.coordinateSpace.bounds;
        if(sceneBounds.size.width > 0 && sceneBounds.size.height > 0) {
            return CGRectMake(0, 0, sceneBounds.size.width, sceneBounds.size.height);
        }
    }
    return physicalBounds;
}

@end

NSString* findDefaultContainerWithBundleId(NSString* bundleId) {
"""

source = source.replace(constructor_anchor, constructor_replacement, 1)
if implementation_anchor not in source:
    raise SystemExit("UIKit guest hook implementation anchor not found")
source = source.replace(implementation_anchor, implementation, 1)

for marker in (
    "LCParallelTikTokViewport",
    "lcParallelTikTok_bounds",
    "NSUserDefaults.isLiveProcess && isTikTok",
    "window.windowLevel == UIWindowLevelNormal",
):
    if marker not in source:
        raise SystemExit(f"missing TikTok viewport marker: {marker}")

path.write_text(source, encoding="utf-8")
print("Added TikTok-only LiveProcess viewport correction")
