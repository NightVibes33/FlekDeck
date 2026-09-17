#!/usr/bin/env python3
from pathlib import Path

path = Path("SideStoreSupport/SideStoreHooks.m")
s = path.read_text()

# SideStore's internal store/app identity must stay byte-for-byte compatible
# with main.  It is intentionally NOT the host IPA's CFBundleIdentifier.
main_app = '''+ (NSString*)hook_appbundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
dynamic_app = '''+ (NSString*)hook_appbundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if dynamic_app in s:
    s = s.replace(dynamic_app, main_app, 1)
elif main_app not in s:
    raise SystemExit(f"{path}: main app identity hook anchor missing")

main_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    return @"com.kdt.livecontainer";
}'''
dynamic_store = '''+ (NSString*)hook_storeAppBundleIdentifier {
    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;
    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";
}'''
if dynamic_store in s:
    s = s.replace(dynamic_store, main_store, 1)
elif main_store not in s:
    raise SystemExit(f"{path}: main store identity hook anchor missing")

# Keep the FlekDeck source metadata while preserving main's SideStore identity
# contract above.  The actual host IPA remains com.fs.flekdeck / FlekDeck.
upstream_source = "https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json"
flek_source = "https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json"
s = s.replace(upstream_source, flek_source)
path.write_text(s)

final = path.read_text()
if final.count('return @"com.kdt.livecontainer";') != 2:
    raise SystemExit(f"{path}: SideStore internal identity no longer matches main")
if 'NSUserDefaults.lcMainBundle.bundleIdentifier' in final:
    raise SystemExit(f"{path}: temp host-derived SideStore identity rewrite remains")
if 'flekdeck-side-source.json' not in final:
    raise SystemExit(f"{path}: FlekDeck SideStore source missing")

print("FlekDeck SideStore internal App ID identity preserved exactly as main")
