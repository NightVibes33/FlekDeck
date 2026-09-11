#!/usr/bin/env python3
"""Rebuild FlekDeck's post-Vibe Parallel/Single compatibility boundary.

Order matters:
1. restore the proven hosted viewport/screen bridge,
2. add the current TikTok 46.x bar-only compatibility layer,
3. restore the separate Single-mode switcher gesture bridge.

The TikTok layer intentionally never changes the feed/root frame, root bounds,
selected-child safe area, scene size, or any fixed point offset.
"""
from pathlib import Path
import runpy

runpy.run_path("Tools/patch_parallel_guest_viewport_base.py", run_name="__main__")
runpy.run_path("Tools/patch_tiktok_462_bar_overlay.py", run_name="__main__")
runpy.run_path("Tools/patch_single_switcher_bridge.py", run_name="__main__")

tweak = Path("TweakLoader/UIKit+GuestHooks.m").read_text()
dock = Path("MultitaskSupport/MultitaskDockView.swift").read_text()

for required in (
    "LCParallelGuestViewportBridge",
    "LCTikTokParallelLayoutCompat",
    "LCTikTok462TabHierarchyCompat",
    "LCTikTok462BarOverlayOnly",
    "LCTikTokParallelBottomNudge",  # legacy CI marker; not a fixed nudge
    'NSClassFromString(@"TTKTabBarController")',
    "LCSingleGuestSwitcherGestureBridge",
):
    if required not in tweak:
        raise SystemExit(f"missing compiled compatibility marker: {required}")

for forbidden in (
    "LCTikTok462HostedInsetsContract",
    "selected.additionalSafeAreaInsets",
    "LCTikTok462VerticalPan",
    "LCTikTok462AlignRootToHostedViewport",
    "rootView.bounds =",
    "bounds.origin.y = 20.0",
):
    if forbidden in tweak:
        raise SystemExit(f"obsolete TikTok geometry mutation survived: {forbidden}")

for required in (
    "FlekHomeSingleSwitcherGestureBridge",
    "FlekSingleGuestSwitcherGestureRequested",
    "!hasForegroundAppWindow()",
    "MultitaskSwipeZone",
):
    if required not in dock:
        raise SystemExit(f"missing switcher marker: {required}")

print("Parallel path preserved; TikTok feed/root untouched; native TikTok bar-only overlay + Single switcher restored")
