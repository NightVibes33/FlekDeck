from pathlib import Path

# Follow-up correctness patch for the temp native-media-PiP experiment.
# Native media PiP is VIDEO state. FlekDeck Window PiP is WINDOW/SWITCHER state.
# They must never share minimize/unminimize lifecycle calls.

p = Path("MultitaskSupport/PiPManager.m")
s = p.read_text(encoding="utf-8")

# 1) A successful native media PiP start must not tell the dock that the whole
# guest window entered Window PiP. Doing so hides the guest, changes frontmost-app
# bookkeeping, and can leave the app switcher stale when AVKit stops independently.
old_active = '''        self.nativePiPRequestPending = NO; self.nativePiPActive = YES;
        [self cancelNativePiPTokensKeepingStopped:YES];
        [self.displayingDecoratedVC minimizeWindowPiP];
        [self.displayingVC setBackgroundNotificationEnabled:false]; self.displayingVC.shouldIgnoreSceneUpdates = YES;
'''
new_active = '''        self.nativePiPRequestPending = NO; self.nativePiPActive = YES;
        [self cancelNativePiPTokensKeepingStopped:YES];
        // LCNativePiPDoesNotOwnWindowLifecycle: native media PiP keeps the guest
        // scene/window alive. Do not call minimizeWindowPiP, alter dock state, or
        // freeze scene updates here; AVKit owns only the media presentation.
'''
if old_active not in s:
    raise SystemExit("Native PiP active/window-lifecycle anchor not found")
s = s.replace(old_active, new_active, 1)

# 2) Same rule on teardown. Calling unminimizeWindowPiP for a window that never
# entered Window PiP emits a false windowDidExitPiP transition into the switcher.
old_finish = '''- (void)finishNativePiP {
    self.nativePiPRequestPending = NO; self.nativePiPActive = NO;
    if(self.displayingVC) {
        self.displayingVC.shouldIgnoreSceneUpdates = NO;
        [self.displayingVC setBackgroundNotificationEnabled:true];
        [self.displayingDecoratedVC unminimizeWindowPiP];
    }
}
'''
new_finish = '''- (void)finishNativePiP {
    // Native media PiP never took ownership of the FlekDeck guest window, so
    // finishing it must not generate Window-PiP exit/switcher transitions either.
    self.nativePiPRequestPending = NO;
    self.nativePiPActive = NO;
}
'''
if old_finish not in s:
    raise SystemExit("Native PiP finish/window-lifecycle anchor not found")
s = s.replace(old_finish, new_finish, 1)

# 3) If the guest reports that it has no native AVKit media source, this is a
# normal non-media app. Preserve LiveContainer/FlekDeck behavior automatically by
# using Window PiP rather than making the user choose a fallback alert.
old_unavailable = '''        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        [self showNativePiPUnavailable:@"This guest has no active native AVKit player/sample-buffer PiP source. FlekDeck will not guess or crop the app window. Window PiP is available separately."];
'''
new_unavailable = '''        self.nativePiPRequestPending = NO; [self cancelNativePiPTokensKeepingStopped:NO];
        // LCNativePiPAutoWindowFallback: no media controller means this is the
        // ordinary app-window PiP case. Keep legacy behavior automatic.
        [self startWindowPiPWithVC:vc];
'''
if old_unavailable not in s:
    raise SystemExit("Native PiP unavailable fallback anchor not found")
s = s.replace(old_unavailable, new_unavailable, 1)

# 4) Window PiP is the whole guest window again. The earlier 16:9 media crop was
# only a workaround before a real native-media path existed; keeping it here would
# distort ordinary app PiP and would blur the separation between the two modes.
crop_assignment = 'self.usesMediaCrop = [self shouldUseMediaCropForSourceSize:self.sourceContentSize];'
if s.count(crop_assignment) != 2:
    raise SystemExit(f"Expected exactly two Window PiP media-crop assignments, found {s.count(crop_assignment)}")
s = s.replace(crop_assignment, 'self.usesMediaCrop = NO;')

preferred = 'self.pipVideoCallViewController.preferredContentSize = [self preferredPiPContentSizeForSourceSize:self.sourceContentSize];'
if s.count(preferred) != 2:
    raise SystemExit(f"Expected exactly two cropped preferredContentSize assignments, found {s.count(preferred)}")
s = s.replace(preferred, 'self.pipVideoCallViewController.preferredContentSize = self.sourceContentSize;')

# Prove the native-media block itself cannot mutate Window-PiP/switcher state.
# Match executable Objective-C calls/state assignments, not explanatory comments.
finish_start = s.find('- (void)finishNativePiP')
window_start = s.find('- (void)startWindowPiPWithVC:')
if finish_start < 0 or window_start < 0 or finish_start >= window_start:
    raise SystemExit("Unable to isolate native media PiP host block")
native_block = s[finish_start:window_start]
for forbidden in [
    '[self.displayingDecoratedVC minimizeWindowPiP];',
    '[self.displayingDecoratedVC unminimizeWindowPiP];',
    '[self.displayingVC setBackgroundNotificationEnabled:false];',
    'self.displayingVC.shouldIgnoreSceneUpdates = YES;',
]:
    if forbidden in native_block:
        raise SystemExit(f"Native media PiP still mutates Window-PiP state: {forbidden}")

for required in [
    'LCNativePiPDoesNotOwnWindowLifecycle',
    'LCNativePiPAutoWindowFallback',
    'self.usesMediaCrop = NO;',
    'preferredContentSize = self.sourceContentSize',
]:
    if required not in s:
        raise SystemExit(f"PiP separation marker missing: {required}")

p.write_text(s, encoding="utf-8")
print("Separated native media PiP from FlekDeck window/switcher lifecycle and restored normal Window PiP fallback.")
