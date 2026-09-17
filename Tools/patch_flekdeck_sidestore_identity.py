#!/usr/bin/env python3
from pathlib import Path

path = Path("SideStoreSupport/SideStoreHooks.m")
s = path.read_text()

fixed_app = '''+ (NSString*)hook_appbundleIdentifier {
    return @"com.fs.flekdeck";
}'''
legacy_app = '''+ (NSString*)hook_appbundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
dynamic_app = '''+ (NSString*)hook_appbundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if fixed_app in s:
    pass
elif legacy_app in s:
    s = s.replace(legacy_app, fixed_app, 1)
elif dynamic_app in s:
    s = s.replace(dynamic_app, fixed_app, 1)
else:
    raise SystemExit(f"{path}: app bundle identity hook anchor missing")

fixed_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    return @"com.fs.flekdeck";
}'''
legacy_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
dynamic_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if fixed_store in s:
    pass
elif legacy_store in s:
    s = s.replace(legacy_store, fixed_store, 1)
elif dynamic_store in s:
    s = s.replace(dynamic_store, fixed_store, 1)
else:
    raise SystemExit(f"{path}: store bundle identity hook anchor missing")

upstream_source = "https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json"
flek_source = "https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json"
s = s.replace(upstream_source, flek_source)
path.write_text(s)

final = path.read_text()
if final.count('return @"com.fs.flekdeck";') != 2:
    raise SystemExit(f"{path}: SideStore app/store identity is not exactly com.fs.flekdeck")
if 'com.kdt.livecontainer' in final:
    raise SystemExit(f"{path}: stale LiveContainer SideStore identity remains")
if 'NSUserDefaults.lcMainBundle.bundleIdentifier' in final:
    raise SystemExit(f"{path}: dynamic SideStore identity rewrite remains")
if 'flekdeck-side-source.json' not in final:
    raise SystemExit(f"{path}: FlekDeck SideStore source missing")

print("FlekDeck SideStore app/store identity fixed to com.fs.flekdeck")
