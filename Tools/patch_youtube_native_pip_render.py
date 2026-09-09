from pathlib import Path

# Temp-branch-only correction for current YouTube's MLPIPControllerImpl pipeline.
# The generic guest PiP bridge discovers AVPictureInPictureController instances,
# but YouTube's wrapper owns creation/refresh of the real AVKit content source and
# its playback delegate. Starting the raw controller before that source settles can
# produce a live PiP session with audio/metadata but a blank video surface.

p = Path("LiveContainer/LCBootstrap.m")
s = p.read_text(encoding="utf-8")

start = s.find("static void LCPrimeYouTubePiP(void) {")
end = s.find("static void LCMonitorPiPStop", start)
if start < 0 or end < 0:
    raise SystemExit("YouTube PiP priming block not found")

replacement = r'''static BOOL LCYouTubePiPRefreshSource(id pip, id avpip) {
    if(!pip || !avpip) return NO;

    id source = LCMsgId(avpip, sel_registerName("contentSource"));
    BOOL hasMediaSource = LCSourceIsMedia(source);
    BOOL needsRefresh = !hasMediaSource;
    if([pip respondsToSelector:sel_registerName("contentSourceNeedsRefresh")])
        needsRefresh = needsRefresh || LCMsgBool(pip, sel_registerName("contentSourceNeedsRefresh"));

    // Current YouTube's MLPIPControllerImpl owns source construction. Let it build
    // the source because that also preserves the sample-buffer playback delegate
    // used by AVKit for transport controls and frame delivery.
    if(needsRefresh && [pip respondsToSelector:sel_registerName("newContentSource")]) {
        id fresh = LCMsgId(pip, sel_registerName("newContentSource"));
        if(fresh && LCSourceIsMedia(fresh) &&
           [avpip respondsToSelector:sel_registerName("setContentSource:")]) {
            ((void(*)(id,SEL,id))objc_msgSend)(avpip, sel_registerName("setContentSource:"), fresh);
            source = fresh;
            hasMediaSource = YES;
        }
    }

    if(hasMediaSource) LCRegisterPiP(avpip, YES);
    return hasMediaSource;
}

static BOOL LCPrimeYouTubePiP(void) {
    if(!NSClassFromString(@"YTPlayerViewController")) return NO;
    NSMutableArray *players = [NSMutableArray new];
    NSMutableSet *seen = [NSMutableSet new];
    UIApplication *app = UIApplication.sharedApplication;
    for(UIScene *scene in app.connectedScenes) if([scene isKindOfClass:UIWindowScene.class])
        for(UIWindow *w in ((UIWindowScene *)scene).windows) LCWalkVC(w.rootViewController, seen, players);
    for(UIWindow *w in app.windows) LCWalkVC(w.rootViewController, seen, players);

    BOOL primed = NO;
    for(UIViewController *pvc in players.reverseObjectEnumerator) {
        id local = LCSafeKVC(pvc, @"_playbackController");
        id playerPiP = LCSafeKVC(local, @"_playerPIPController");
        if(!playerPiP) continue;

        // Preserve YouTube's own policy/eligibility path first. Do not override
        // account/premium policy here.
        if([playerPiP respondsToSelector:sel_registerName("maybeEnablePictureInPicture")])
            LCMsgVoid(playerPiP, sel_registerName("maybeEnablePictureInPicture"));
        else if([playerPiP respondsToSelector:sel_registerName("maybeInvokePictureInPicture")])
            LCMsgVoid(playerPiP, sel_registerName("maybeInvokePictureInPicture"));
        else {
            BOOL can = LCMsgBool(playerPiP, sel_registerName("canEnablePictureInPicture")) ||
                       LCMsgBool(playerPiP, sel_registerName("canInvokePictureInPicture"));
            id fallbackPiP = LCSafeKVC(playerPiP, @"_pipController");
            if(can) {
                if([fallbackPiP respondsToSelector:sel_registerName("activatePiPController")])
                    LCMsgVoid(fallbackPiP, sel_registerName("activatePiPController"));
                else
                    LCMsgVoid(fallbackPiP, sel_registerName("startPictureInPicture"));
            }
        }

        // Re-read after maybeEnable/maybeInvoke: current YouTube may create or swap
        // MLPIPControllerImpl during that call.
        id pip = LCSafeKVC(playerPiP, @"_pipController");
        if(!pip) continue;

        // The wrapper owns the renderer and delegate. Activate it before touching
        // AVPictureInPictureController so AVKit never starts on an unbound surface.
        if([pip respondsToSelector:sel_registerName("activatePiPController")])
            LCMsgVoid(pip, sel_registerName("activatePiPController"));

        id avpip = LCSafeKVC(pip, @"_pictureInPictureController");
        if(!avpip) continue;

        BOOL bound = LCYouTubePiPRefreshSource(pip, avpip);
        NSLog(@"[FlekDeck PiP] YouTube source bound=%d wrapper=%@ controller=%@",
              bound, NSStringFromClass([pip class]), NSStringFromClass([avpip class]));
        if(bound) {
            LCRegisterPiP(avpip, YES);
            primed = YES;
        }
    }
    return primed;
}
'''

s = s[:start] + replacement + s[end:]

old = "    if(attempt == 0 || attempt == 5 || attempt == 15) LCPrimeYouTubePiP();\n"
new = '''    BOOL ytPrimed = NO;
    if(attempt == 0 || attempt == 5 || attempt == 15) ytPrimed = LCPrimeYouTubePiP();
    // Do not immediately raw-start the AVKit controller in the same turn that
    // YouTube created/refreshed its renderer. Give MLPIPControllerImpl one main-run
    // loop to attach the player/sample-buffer source and playback delegate first.
    if(ytPrimed) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 150 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            LCAttemptPiPStart(gen, attempt + 1);
        });
        return;
    }
'''
if old not in s:
    raise SystemExit("PiP start sequencing anchor not found")
s = s.replace(old, new, 1)

for marker in [
    "LCYouTubePiPRefreshSource",
    "newContentSource",
    "contentSourceNeedsRefresh",
    "activatePiPController",
    "YouTube source bound=",
]:
    if marker not in s:
        raise SystemExit(f"YouTube render marker missing: {marker}")

p.write_text(s, encoding="utf-8")
print("Bound YouTube native PiP through MLPIPControllerImpl content-source ownership.")
