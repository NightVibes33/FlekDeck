from pathlib import Path

# Temp-branch-only correction for current YouTube's MLPIPControllerImpl pipeline.
# Keep this isolated from MultitaskDockView.swift: the bottom app-switcher swipe is
# known-good and must remain byte-for-byte untouched by PiP experiments.
#
# The generic guest PiP bridge discovers AVPictureInPictureController instances,
# while YouTube's MLPIPControllerImpl owns the real AVKit content source, playback
# delegate, and HAM/AVPlayer rendering views. A controller can become active with
# controls/audio/Now Playing metadata while its sample-buffer renderer never gets
# an appearance/render-size transition inside LiveProcess. That produces a black
# PiP surface even though the transport session is otherwise healthy.

p = Path("LiveContainer/LCBootstrap.m")
s = p.read_text(encoding="utf-8")

start = s.find("static void LCPrimeYouTubePiP(void) {")
end = s.find("static void LCMonitorPiPStop", start)
if start < 0 or end < 0:
    raise SystemExit("YouTube PiP priming block not found")

replacement = r'''static id LCGuestYouTubePiPWrapper;
static id LCGuestYouTubeAVPiP;

static BOOL LCYouTubePiPRefreshSource(id pip, id avpip) {
    if(!pip || !avpip) return NO;

    id source = LCMsgId(avpip, sel_registerName("contentSource"));
    BOOL hasMediaSource = LCSourceIsMedia(source);
    BOOL needsRefresh = !hasMediaSource;
    if([pip respondsToSelector:sel_registerName("contentSourceNeedsRefresh")])
        needsRefresh = needsRefresh || LCMsgBool(pip, sel_registerName("contentSourceNeedsRefresh"));

    // Current YouTube's MLPIPControllerImpl owns source construction. Let it build
    // the source because that preserves its sample-buffer playback delegate and
    // the exact AVPlayerLayer / AVSampleBufferDisplayLayer selected by YouTube.
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

// LiveProcess-specific renderer wake-up. YouTube can have a completely healthy
// PiP transport session (native controls, audio and Now Playing metadata) while
// the HAM sample-buffer surface never gets told that it appeared. PoomSmart's
// YouPiP uses these AVKit renderer notifications for YouTube's HAM renderer on
// older pipelines; sending them here is harmless when unsupported and gives the
// out-of-process LiveProcess renderer the missing lifecycle edge.
static BOOL LCYouTubePiPWakeRenderer(id pip, id avpip) {
    if(!pip || !avpip) return NO;
    BOOL woke = NO;

    id ham = LCSafeKVC(pip, @"_HAMPlayerView");
    if(!ham) ham = LCSafeKVC(pip, @"HAMPlayerView");
    id displayLayer = LCMsgId(ham, sel_registerName("displayLayer"));

    if(ham && [ham isKindOfClass:UIView.class]) {
        UIView *view = (UIView *)ham;
        [view setNeedsLayout];
        [view layoutIfNeeded];

        CGSize size = view.bounds.size;
        SEL renderSel = sel_registerName("renderSizeForView:");
        if([pip respondsToSelector:renderSel]) {
            CGSize rendered = ((CGSize(*)(id,SEL,id))objc_msgSend)(pip, renderSel, ham);
            if(rendered.width > 0 && rendered.height > 0) size = rendered;
        }

        SEL sizeSel = sel_registerName("sampleBufferDisplayLayerRenderSizeDidChangeToSize:");
        if(size.width > 0 && size.height > 0 && [avpip respondsToSelector:sizeSel]) {
            ((void(*)(id,SEL,CGSize))objc_msgSend)(avpip, sizeSel, size);
            woke = YES;
        }

        // Some YouTube generations expose their own forwarding callback. Let the
        // wrapper observe the same size so its internal state cannot remain stale.
        SEL wrapperSizeSel = sel_registerName("renderingViewSampleBufferFrameSizeDidChange:");
        if(size.width > 0 && size.height > 0 && [pip respondsToSelector:wrapperSizeSel]) {
            ((void(*)(id,SEL,CGSize))objc_msgSend)(pip, wrapperSizeSel, size);
            woke = YES;
        }
    }

    SEL appearSel = sel_registerName("sampleBufferDisplayLayerDidAppear");
    if(displayLayer && [avpip respondsToSelector:appearSel]) {
        LCMsgVoid(avpip, appearSel);
        woke = YES;
    }

    // AVPlayer-backed YouTube builds don't need the HAM appearance signal, but
    // forcing the owning view through layout before start prevents a zero-sized
    // playerLayer from being handed to AVKit.
    id avView = LCSafeKVC(pip, @"_AVPlayerView");
    if(!avView) avView = LCSafeKVC(pip, @"AVPlayerView");
    if(avView && [avView isKindOfClass:UIView.class]) {
        UIView *view = (UIView *)avView;
        [view setNeedsLayout];
        [view layoutIfNeeded];
        id playerLayer = LCMsgId(avView, sel_registerName("playerLayer"));
        if(playerLayer) woke = YES;
    }

    NSLog(@"[FlekDeck PiP] YouTube renderer wake=%d ham=%d displayLayer=%d",
          woke, ham != nil, displayLayer != nil);
    return woke;
}

static void LCYouTubePiPWakeRendererBurst(id pip, id avpip) {
    if(!pip || !avpip) return;
    LCYouTubePiPWakeRenderer(pip, avpip);
    for(NSNumber *delay in @[@0.08, @0.20, @0.45, @0.90]) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,
                    (int64_t)(delay.doubleValue * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            if(LCGuestYouTubePiPWrapper == pip && LCGuestYouTubeAVPiP == avpip)
                LCYouTubePiPWakeRenderer(pip, avpip);
        });
    }
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
        BOOL woke = bound ? LCYouTubePiPWakeRenderer(pip, avpip) : NO;
        NSLog(@"[FlekDeck PiP] YouTube source bound=%d renderer=%d wrapper=%@ controller=%@",
              bound, woke, NSStringFromClass([pip class]), NSStringFromClass([avpip class]));
        if(bound) {
            LCGuestYouTubePiPWrapper = pip;
            LCGuestYouTubeAVPiP = avpip;
            LCYouTubePiPWakeRendererBurst(pip, avpip);
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
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 180 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            if(LCGuestYouTubePiPWrapper && LCGuestYouTubeAVPiP)
                LCYouTubePiPWakeRenderer(LCGuestYouTubePiPWrapper, LCGuestYouTubeAVPiP);
            LCAttemptPiPStart(gen, attempt + 1);
        });
        return;
    }
'''
if old not in s:
    raise SystemExit("PiP start sequencing anchor not found")
s = s.replace(old, new, 1)

# Once AVKit reports the PiP window active, wake the media surface again. This is
# intentionally renderer-only; it does not touch FlekDeck window/switcher state.
active_old = '''    if(LCMsgBool(controller, sel_registerName("isPictureInPictureActive"))) {
        LCGuestPiPCurrent = controller; LCGuestPiPPost(@"active"); LCMonitorPiPStop(controller, gen); return;
    }
'''
active_new = '''    if(LCMsgBool(controller, sel_registerName("isPictureInPictureActive"))) {
        if(controller == LCGuestYouTubeAVPiP && LCGuestYouTubePiPWrapper)
            LCYouTubePiPWakeRendererBurst(LCGuestYouTubePiPWrapper, controller);
        LCGuestPiPCurrent = controller; LCGuestPiPPost(@"active"); LCMonitorPiPStop(controller, gen); return;
    }
'''
if active_old not in s:
    raise SystemExit("PiP active renderer-wake anchor not found")
s = s.replace(active_old, active_new, 1)

for marker in [
    "LCYouTubePiPRefreshSource",
    "LCYouTubePiPWakeRenderer",
    "LCYouTubePiPWakeRendererBurst",
    "sampleBufferDisplayLayerDidAppear",
    "sampleBufferDisplayLayerRenderSizeDidChangeToSize:",
    "renderingViewSampleBufferFrameSizeDidChange:",
    "newContentSource",
    "contentSourceNeedsRefresh",
    "YouTube renderer wake=",
]:
    if marker not in s:
        raise SystemExit(f"YouTube render marker missing: {marker}")

p.write_text(s, encoding="utf-8")
print("Bound and explicitly woke YouTube native PiP renderer without touching switcher code.")
