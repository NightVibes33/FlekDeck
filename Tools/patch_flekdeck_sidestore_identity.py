#!/usr/bin/env python3
from pathlib import Path

path = Path("SideStoreSupport/SideStoreHooks.m")
s = path.read_text()

old_app = '''+ (NSString*)hook_appbundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
new_app = '''+ (NSString*)hook_appbundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if old_app in s:
    s = s.replace(old_app, new_app, 1)
elif new_app not in s:
    raise SystemExit(f"{path}: app bundle identity hook anchor missing")

old_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
new_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if old_store in s:
    s = s.replace(old_store, new_store, 1)
elif new_store not in s:
    raise SystemExit(f"{path}: store bundle identity hook anchor missing")

upstream_source = "https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json"
flek_source = "https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json"
s = s.replace(upstream_source, flek_source)
path.write_text(s)

final = path.read_text()
if 'return @"com.kdt.livecontainer";' in final:
    raise SystemExit(f"{path}: stale LiveContainer SideStore identity remains")
if 'com.fs.flekdeck' not in final:
    raise SystemExit(f"{path}: fixed FlekDeck identity missing")
if 'flekdeck-side-source.json' not in final:
    raise SystemExit(f"{path}: FlekDeck SideStore source missing")
if final.count('NSUserDefaults.lcMainBundle.bundleIdentifier') < 2:
    raise SystemExit(f"{path}: SideStore identity is not derived from the actual host bundle")

print("FlekDeck SideStore hooks now resolve the installed host as com.fs.flekdeck")
