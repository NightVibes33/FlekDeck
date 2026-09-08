from pathlib import Path

# Temp-branch-only PiP correctness layer.
# Media PiP is fail-closed: the normal PiP action asks the LiveProcess guest to
# start its real AVPictureInPictureController (AVPlayerLayer/sample-buffer source).
# The existing remote-window PiP is retained only as an explicit fallback.

bootstrap = Path("LiveContainer/LCBootstrap.m")
s = bootstrap.read_text(encoding="utf-8")
if "#include <objc/message.h>" not in s:
    s = s.replace("#include <objc/runtime.h>\n", "#include <objc/runtime.h>\n#include <objc/message.h>\n#include <notify.h>\n#include <unistd.h>\n", 1)

marker = "LCGuestNativePiPBridge"
anchor = "@implementation NSUserDefaults(LiveContainer)\n"
if marker not in s:
    bridge = r'''// LCGuestNativePiPBridge -----------------------------------------------------
// Capture the AVKit controllers created inside the real guest process. The host
// only owns a remote scene surface, so it cannot derive a media aspect ratio.
static NSHashTable *LCGuestPiPControllers;
static id LCGuestPiPCurrent;
static NSUInteger LCGuestPiPGeneration;
static IMP LCOrigInitPlayerLayer;
static IMP LCOrigInitContentSource;
static IMP LCOrigSetContentSource;
static IMP LCOrigStartPiP;
static BOOL LCGuestPiPHooked;
static int LCGuestPiPStartToken = -1, LCGuestPiPStopToken = -1;
static char LCGuestPiPMediaKey, LCGuestPiPStampKey;

static NSString *LCGuestPiPName(NSString *event) {
    return [NSString stringWithFormat:@"com.flekdeck.nativepip.%@.%d", event, getpid()];
}
static void LCGuestPiPPost(NSString *event) { notify_post(LCGuestPiPName(event).UTF8String); }
static id LCMsgId(id o, SEL s) { return o && [o respondsToSelector:s] ? ((id(*)(id,SEL))objc_msgSend)(o,s) : nil; }
static BOOL LCMsgBool(id o, SEL s) { return o && [o respondsToSelector:s] ? ((BOOL(*)(id,SEL))objc_msgSend)(o,s) : NO; }
static void LCMsgVoid(id o, SEL s) { if(o && [o respondsToSelector:s]) ((void(*)(id,SEL))objc_msgSend)(o,s); }
static id LCSafeKVC(id o, NSString *key) {
    @try { return o ? [o valueForKey:key] : nil; } @catch(__unused NSException *e) { return nil; }
}
static BOOL LCSourceIsMedia(id source) {
    return LCMsgId(source, sel_registerName("playerLayer")) != nil ||
           LCMsgId(source, sel_registerName("sampleBufferDisplayLayer")) != nil;
}
static BOOL LCControllerIsMedia(id controller) {
    if([objc_getAssociatedObject(controller, &LCGuestPiPMediaKey) boolValue]) return YES;
    return LCSourceIsMedia(LCMsgId(controller, sel_registerName("contentSource")));
}
static void LCRegisterPiP(id controller, BOOL media) {
    if(!controller) return;
    if(!LCGuestPiPControllers) LCGuestPiPControllers = [NSHashTable weakObjectsHashTable];
    if(media || LCControllerIsMedia(controller))
        objc_setAssociatedObject(controller, &LCGuestPiPMediaKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(controller, &LCGuestPiPStampKey, @([NSDate.date timeIntervalSince1970]), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    @synchronized(LCGuestPiPControllers) { [LCGuestPiPControllers addObject:controller]; }
}
static id LCHookInitPlayer(id self, SEL cmd, id layer) {
    id obj = ((id(*)(id,SEL,id))LCOrigInitPlayerLayer)(self, cmd, layer);
    LCRegisterPiP(obj, YES); return obj;
}
static id LCHookInitSource(id self, SEL cmd, id source) {
    id obj = ((id(*)(id,SEL,id))LCOrigInitContentSource)(self, cmd, source);
    LCRegisterPiP(obj, LCSourceIsMedia(source)); return obj;
}
static void LCHookSetSource(id self, SEL cmd, id source) {
    ((void(*)(id,SEL,id))LCOrigSetContentSource)(self, cmd, source);
    LCRegisterPiP(self, LCSourceIsMedia(source));
}
static void LCHookStartPiP(id self, SEL cmd) {
    LCRegisterPiP(self, LCControllerIsMedia(self));
    ((void(*)(id,SEL))LCOrigStartPiP)(self, cmd);
}
static void LCHookMethod(Class cls, SEL sel, IMP replacement, IMP *original) {
    Method m = class_getInstanceMethod(cls, sel); if(!m || *original) return;
    *original = method_getImplementation(m); method_setImplementation(m, replacement);
}
static void LCInstallAVKitPiPHooks(void) {
    if(LCGuestPiPHooked) return;
    Class cls = NSClassFromString(@"AVPictureInPictureController"); if(!cls) return;
    LCHookMethod(cls, sel_registerName("initWithPlayerLayer:"), (IMP)LCHookInitPlayer, &LCOrigInitPlayerLayer);
    LCHookMethod(cls, sel_registerName("initWithContentSource:"), (IMP)LCHookInitSource, &LCOrigInitContentSource);
    LCHookMethod(cls, sel_registerName("setContentSource:"), (IMP)LCHookSetSource, &LCOrigSetContentSource);
    LCHookMethod(cls, sel_registerName("startPictureInPicture"), (IMP)LCHookStartPiP, &LCOrigStartPiP);
    LCGuestPiPHooked = LCOrigStartPiP != NULL;
    NSLog(@"[FlekDeck PiP] AVKit guest media hook=%d pid=%d", LCGuestPiPHooked, getpid());
}
static NSArray *LCSortedPiPControllers(void) {
    NSArray *a; @synchronized(LCGuestPiPControllers) { a = LCGuestPiPControllers.allObjects ?: @[]; }
    return [a sortedArrayUsingComparator:^NSComparisonResult(id x, id y) {
        NSNumber *a = objc_getAssociatedObject(x, &LCGuestPiPStampKey) ?: @0;
        NSNumber *b = objc_getAssociatedObject(y, &LCGuestPiPStampKey) ?: @0;
        return [a compare:b];
    }];
}
static id LCBestPiP(BOOL possible, BOOL active) {
    for(id c in LCSortedPiPControllers().reverseObjectEnumerator) {
        if(!LCControllerIsMedia(c)) continue;
        if(possible && !LCMsgBool(c, sel_registerName("isPictureInPicturePossible"))) continue;
        if(active && !LCMsgBool(c, sel_registerName("isPictureInPictureActive"))) continue;
        return c;
    }
    return nil;
}
static void LCWalkVC(UIViewController *vc, NSMutableSet *seen, NSMutableArray *ytPlayers) {
    if(!vc) return; NSValue *key = [NSValue valueWithNonretainedObject:vc];
    if([seen containsObject:key]) return; [seen addObject:key];
    if([NSStringFromClass(vc.class) isEqualToString:@"YTPlayerViewController"]) [ytPlayers addObject:vc];
    LCWalkVC(vc.presentedViewController, seen, ytPlayers);
    for(UIViewController *child in vc.childViewControllers) LCWalkVC(child, seen, ytPlayers);
}
// Ask YouTube to prepare its own controller without changing any premium/account
// policy. This mirrors its native enable/invoke path and only proceeds if its own
// canEnable/canInvoke decision allows it.
static void LCPrimeYouTubePiP(void) {
    if(!NSClassFromString(@"YTPlayerViewController")) return;
    NSMutableArray *players = [NSMutableArray new]; NSMutableSet *seen = [NSMutableSet new];
    UIApplication *app = UIApplication.sharedApplication;
    for(UIScene *scene in app.connectedScenes) if([scene isKindOfClass:UIWindowScene.class])
        for(UIWindow *w in ((UIWindowScene *)scene).windows) LCWalkVC(w.rootViewController, seen, players);
    for(UIWindow *w in app.windows) LCWalkVC(w.rootViewController, seen, players);
    for(UIViewController *pvc in players.reverseObjectEnumerator) {
        id local = LCSafeKVC(pvc, @"_playbackController");
        id playerPiP = LCSafeKVC(local, @"_playerPIPController"); if(!playerPiP) continue;
        if([playerPiP respondsToSelector:sel_registerName("maybeEnablePictureInPicture")])
            LCMsgVoid(playerPiP, sel_registerName("maybeEnablePictureInPicture"));
        else if([playerPiP respondsToSelector:sel_registerName("maybeInvokePictureInPicture")])
            LCMsgVoid(playerPiP, sel_registerName("maybeInvokePictureInPicture"));
        else {
            BOOL can = LCMsgBool(playerPiP, sel_registerName("canEnablePictureInPicture")) ||
                       LCMsgBool(playerPiP, sel_registerName("canInvokePictureInPicture"));
            id pip = LCSafeKVC(playerPiP, @"_pipController");
            if(can) {
                if([pip respondsToSelector:sel_registerName("activatePiPController")]) LCMsgVoid(pip, sel_registerName("activatePiPController"));
                else LCMsgVoid(pip, sel_registerName("startPictureInPicture"));
            }
        }
        id avpip = LCSafeKVC(LCSafeKVC(playerPiP, @"_pipController"), @"_pictureInPictureController");
        if(avpip) LCRegisterPiP(avpip, LCControllerIsMedia(avpip));
    }
}
static void LCMonitorPiPStop(id controller, NSUInteger gen) {
    if(gen != LCGuestPiPGeneration || controller != LCGuestPiPCurrent) return;
    if(LCMsgBool(controller, sel_registerName("isPictureInPictureActive"))) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 150 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{ LCMonitorPiPStop(controller, gen); });
    } else { LCGuestPiPCurrent = nil; LCGuestPiPPost(@"stopped"); }
}
static void LCWaitPiPActive(id controller, NSUInteger gen, NSInteger attempt) {
    if(gen != LCGuestPiPGeneration) return;
    if(LCMsgBool(controller, sel_registerName("isPictureInPictureActive"))) {
        LCGuestPiPCurrent = controller; LCGuestPiPPost(@"active"); LCMonitorPiPStop(controller, gen); return;
    }
    if(attempt >= 30) { LCGuestPiPCurrent = nil; LCGuestPiPPost(@"failed"); return; }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{ LCWaitPiPActive(controller, gen, attempt + 1); });
}
static void LCAttemptPiPStart(NSUInteger gen, NSInteger attempt) {
    if(gen != LCGuestPiPGeneration) return;
    LCInstallAVKitPiPHooks();
    if(attempt == 0 || attempt == 5 || attempt == 15) LCPrimeYouTubePiP();
    id active = LCBestPiP(NO, YES);
    if(active) { LCGuestPiPCurrent = active; LCGuestPiPPost(@"active"); LCMonitorPiPStop(active, gen); return; }
    id controller = LCBestPiP(YES, NO);
    if(controller) { LCGuestPiPCurrent = controller; LCMsgVoid(controller, sel_registerName("startPictureInPicture")); LCWaitPiPActive(controller, gen, 0); return; }
    if(attempt >= 30) { LCGuestPiPPost(@"unavailable"); return; }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{ LCAttemptPiPStart(gen, attempt + 1); });
}
static void LCHandlePiPStart(void) { NSUInteger gen = ++LCGuestPiPGeneration; LCAttemptPiPStart(gen, 0); }
static void LCHandlePiPStop(void) {
    ++LCGuestPiPGeneration; id c = LCGuestPiPCurrent ?: LCBestPiP(NO, YES);
    if(c) LCMsgVoid(c, sel_registerName("stopPictureInPicture")); LCGuestPiPCurrent = nil; LCGuestPiPPost(@"stopped");
}
static void LCInstallGuestNativePiPBridge(void) {
    static dispatch_once_t once; dispatch_once(&once, ^{
        dlopen("/System/Library/Frameworks/AVKit.framework/AVKit", RTLD_LAZY | RTLD_LOCAL);
        LCGuestPiPControllers = [NSHashTable weakObjectsHashTable]; LCInstallAVKitPiPHooks();
        notify_register_dispatch(LCGuestPiPName(@"start").UTF8String, &LCGuestPiPStartToken, dispatch_get_main_queue(), ^(__unused int t){ LCHandlePiPStart(); });
        notify_register_dispatch(LCGuestPiPName(@"stop").UTF8String, &LCGuestPiPStopToken, dispatch_get_main_queue(), ^(__unused int t){ LCHandlePiPStop(); });
        NSLog(@"[FlekDeck PiP] LCGuestNativePiPBridge ready pid=%d", getpid());
    });
}
// ---------------------------------------------------------------------------

'''
    if anchor not in s: raise SystemExit("LCBootstrap PiP bridge anchor not found")
    s = s.replace(anchor, bridge + anchor, 1)

live_anchor = '    isLiveProcess = [lcAppUrlScheme isEqualToString:@"liveprocess"];\n'
if "LCInstallGuestNativePiPBridge();" not in s:
    if live_anchor not in s: raise SystemExit("LiveProcess assignment anchor not found")
    s = s.replace(live_anchor, live_anchor + '    if(isLiveProcess) LCInstallGuestNativePiPBridge();\n', 1)
for needle in [marker, "sampleBufferDisplayLayer", "LCInstallGuestNativePiPBridge();", "com.flekdeck.nativepip.%@.%d"]:
    if needle not in s: raise SystemExit(f"Guest PiP marker missing: {needle}")
bootstrap.write_text(s, encoding="utf-8")

# Host PiPManager: the existing implementation becomes explicit Window PiP.
p = Path("MultitaskSupport/PiPManager.m")
s = p.read_text(encoding="utf-8")
if "#include <notify.h>" not in s:
    s = s.replace('#include "../LiveContainer/utils.h"\n', '#include "../LiveContainer/utils.h"\n#include <notify.h>\n', 1)

prop_anchor = '@property(nonatomic, strong) CALayer *observedLayer;\n'
props = '''@property(nonatomic) BOOL nativePiPActive;
@property(nonatomic) BOOL nativePiPRequestPending;
@property(nonatomic) NSUInteger nativePiPGeneration;
@property(nonatomic) int nativeActiveToken;
@property(nonatomic) int nativeStoppedToken;
@property(nonatomic) int nativeUnavailableToken;
@property(nonatomic) int nativeFailedToken;
'''
if "nativePiPActive" not in s:
    if prop_anchor not in s: raise SystemExit("PiPManager property anchor not found")
    s = s.replace(prop_anchor, prop_anchor + props, 1)

s = s.replace('''- (BOOL)isPiP {\n    return self.pipController.isPictureInPictureActive;\n}\n''',
'''- (BOOL)isPiP {\n    return self.nativePiPActive || self.pipController.isPictureInPictureActive;\n}\n''', 1)
s = s.replace('''- (BOOL)isPiPWithVC:(AppSceneViewController*)vc {\n    return self.pipController.isPictureInPictureActive && self.displayingVC == vc;\n}\n''',
'''- (BOOL)isPiPWithVC:(AppSceneViewController*)vc {\n    return (self.nativePiPActive || self.pipController.isPictureInPictureActive) && self.displayingVC == vc;\n}\n''', 1)
s = s.replace('''- (BOOL)isPiPWithDecoratedVC:(UIViewController*)vc {\n    return self.pipController.isPictureInPictureActive && self.displayingDecoratedVC == vc;\n}\n''',
'''- (BOOL)isPiPWithDecoratedVC:(UIViewController*)vc {\n    return (self.nativePiPActive || self.pipController.isPictureInPictureActive) && self.displayingDecoratedVC == vc;\n}\n''', 1)

old_start = '- (void)startPiPWithVC:(AppSceneViewController*)vc {\n'
if "startWindowPiPWithVC" not in s:
    if old_start not in s: raise SystemExit("PiPManager startPiP anchor not found")
    s = s.replace(old_start, '- (void)startWindowPiPWithVC:(AppSceneViewController*)vc {\n', 1)

native_methods = r'''- (NSString *)nativePiPName:(NSString *)event pid:(int)pid {
    return [NSString stringWithFormat:@"com.flekdeck.nativepip.%@.%d", event, pid];
}
- (void)cancelNativePiPToken:(int *)token {
    if(*token >= 0) { notify_cancel(*token); *token = -1; }
}
- (void)cancelNativePiPTokensKeepingStopped:(BOOL)keepStopped {
    [self cancelNativePiPToken:&_nativeActiveToken];
    [self cancelNativePiPToken:&_nativeUnavailableToken];
    [self cancelNativePiPToken:&_nativeFailedToken];
    if(!keepStopped) [self cancelNativePiPToken:&_nativeStoppedToken];
}
- (void)finishNativePiP {
    self.nativePiPRequestPending = NO; self.nativePiPActive = NO;
    if(self.displayingVC) {
        self.displayingVC.shouldIgnoreSceneUpdates = NO;
        [self.displayingVC setBackgroundNotificationEnabled:true];
        [self.displayingDecoratedVC unminimizeWindowPiP];
    }
}
- (void)showNativePiPUnavailable:(NSString *)message {
    AppSceneViewController *vc = self.displayingVC;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 150 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        DecoratedAppSceneViewController *presenter = (id)vc.delegate;
        if(!presenter || presenter.presentedViewController) { NSLog(@"[FlekDeck PiP] %@", message); return; }
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Native Media PiP unavailable" message:message preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
        [alert addAction:[UIAlertAction actionWithTitle:@"Window PiP" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){ [self startWindowPiPWithVC:vc]; }]];
        [presenter presentViewController:alert animated:YES completion:nil];
    });
}
- (void)startPiPWithVC:(AppSceneViewController*)vc {
    if(!vc) return;
    self.displayingVC = vc;
    int pid = vc.pid;
    if(pid <= 0) { [self showNativePiPUnavailable:@"The guest PID is not available yet. Wait for launch to finish and try again."]; return; }
    [self cancelNativePiPTokensKeepingStopped:NO];
    self.nativePiPRequestPending = YES; self.nativePiPActive = NO;
    NSUInteger generation = ++self.nativePiPGeneration;
    self.nativeActiveToken = self.nativeStoppedToken = self.nativeUnavailableToken = self.nativeFailedToken = -1;
    notify_register_dispatch([self nativePiPName:@"active" pid:pid].UTF8String, &_nativeActiveToken, dispatch_get_main_queue(), ^(__unused int t){
        if(generation != self.nativePiPGeneration || !self.nativePiPRequestPending) return;
        self.nativePiPRequestPending = NO; self.nativePiPActive = YES;
        [self cancelNativePiPTokensKeepingStopped:YES];
        [self.displayingDecoratedVC minimizeWindowPiP];
        [self.displayingVC setBackgroundNotificationEnabled:false]; self.displayingVC.shouldIgnoreSceneUpdates = YES;
    });
    notify_register_dispatch([self nativePiPName:@"stopped" pid:pid].UTF8String, &_nativeStoppedToken, dispatch_get_main_queue(), ^(__unused int t){
        if(generation != self.nativePiPGeneration) return;
        [self cancelNativePiPTokensKeepingStopped:NO]; [self finishNativePiP];
    });
    notify_register_dispatch([self nativePiPName:@"unavailable" pid:pid].UTF8String, &_nativeUnavailableToken, dispatch_get_main_queue(), ^(__unused int t){
        if(generation != self.nativePiPGeneration || !self.nativePiPRequestPending) return;
        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        [self showNativePiPUnavailable:@"This guest has no active native AVKit player/sample-buffer PiP source. FlekDeck will not guess or crop the app window. Window PiP is available separately."];
    });
    notify_register_dispatch([self nativePiPName:@"failed" pid:pid].UTF8String, &_nativeFailedToken, dispatch_get_main_queue(), ^(__unused int t){
        if(generation != self.nativePiPGeneration || !self.nativePiPRequestPending) return;
        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        [self showNativePiPUnavailable:@"The guest exposed a real media PiP controller, but iOS did not activate it. No cropped fallback was started."];
    });
    if(notify_post([self nativePiPName:@"start" pid:pid].UTF8String) != NOTIFY_STATUS_OK) {
        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        [self showNativePiPUnavailable:@"FlekDeck could not send the native media PiP request to LiveProcess."]; return;
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        if(generation != self.nativePiPGeneration || !self.nativePiPRequestPending) return;
        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        [self showNativePiPUnavailable:@"Timed out waiting for the guest's real AVKit media source. No guessed/cropped PiP was started."];
    });
}

'''
insert_anchor = '- (void)startWindowPiPWithVC:(AppSceneViewController*)vc {\n'
if "nativePiPName:" not in s:
    if insert_anchor not in s: raise SystemExit("Window PiP insertion anchor not found")
    s = s.replace(insert_anchor, native_methods + insert_anchor, 1)

old_stop = '''- (void)stopPiP {\n    [self.pipController stopPictureInPicture];\n}\n'''
new_stop = '''- (void)stopPiP {\n    if(self.nativePiPActive || self.nativePiPRequestPending) {\n        int pid = self.displayingVC.pid;\n        ++self.nativePiPGeneration;\n        if(pid > 0) notify_post([self nativePiPName:@"stop" pid:pid].UTF8String);\n        [self cancelNativePiPTokensKeepingStopped:NO];\n        [self finishNativePiP];\n        return;\n    }\n    [self.pipController stopPictureInPicture];\n}\n'''
if old_stop in s: s = s.replace(old_stop, new_stop, 1)
elif "self.nativePiPActive || self.nativePiPRequestPending" not in s: raise SystemExit("PiPManager stopPiP anchor not found")

for needle in ["startWindowPiPWithVC", "nativePiPActive", "com.flekdeck.nativepip.%@.%d", "No cropped fallback"]:
    if needle not in s: raise SystemExit(f"Host native PiP marker missing: {needle}")
p.write_text(s, encoding="utf-8")
print("Installed fail-closed native media PiP bridge; Window PiP remains explicit fallback.")
