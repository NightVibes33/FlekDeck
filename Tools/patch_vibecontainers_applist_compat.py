from pathlib import Path

p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()

# VibeContainers 3.8.0's LCAppModelDelegate predates Classic Mode. Keep Flek's
# newer UI overloads, but also implement the exact Vibe delegate signatures and
# route them through classicMode=0. The underlying Vibe core remains untouched.
anchor = "    func jitLaunch(appName: String, classicMode: UInt) async {\n"
if "    func jitLaunch(appName: String) async {\n" not in s:
    wrappers = '''    func jitLaunch(appName: String) async {
        await jitLaunch(appName: appName, classicMode: 0)
    }

    func jitLaunch(withScript script: String, appName: String) async {
        await jitLaunch(withScript: script, appName: appName, classicMode: 0)
    }

'''
    if anchor not in s:
        raise SystemExit("Could not find Flek classic-mode JIT launch anchor")
    s = s.replace(anchor, wrappers + anchor, 1)

old_ask = "LCUtils.askForJIT(withScript: script, appName: appName, classicMode: classicMode)"
if old_ask in s:
    s = s.replace(old_ask, "LCUtils.askForJIT(withScript: script, appName: appName)")

old_launch = "LCSharedUtils.launchToGuestApp(withClassicMode: classicMode)"
if old_launch in s:
    s = s.replace(old_launch, "LCSharedUtils.launchToGuestApp()")

p.write_text(s)
print("Adapted Flek LCAppListView to exact VibeContainers delegate/JIT launch APIs.")
