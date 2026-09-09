from pathlib import Path

p = Path("Tools/finish_vibe_settings_port.py")
text = p.read_text()
marker = "# ---------------------------------------------------------------------------\n# TweakLoader: blacklist applies to recursive legacy profiles and per-app\n"
if marker not in text:
    raise SystemExit("TweakLoader finish-patch section not found")
head = text.split(marker, 1)[0]
tail = r'''# ---------------------------------------------------------------------------
# TweakLoader: blacklist applies to recursive legacy profiles and per-app
# overlays too, while preserving the rebuild's staging-safe globalRoot resolver.
# ---------------------------------------------------------------------------
loader = "TweakLoader/TweakLoader.m"
replace_once(
    loader,
    "static void loadTweaksRecursively(NSURL *folderURL, NSURL *globalRoot, NSMutableArray *errors) {\n",
    "static void loadTweaksRecursively(NSURL *folderURL, NSURL *globalRoot, NSMutableArray *errors, NSSet<NSString *> *blockedNames) {\n",
)
replace_once(
    loader,
    '''        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled tweak %@", name);
            continue;
        }

        NSURL *fileURL = FlekCanonicalScopedURL(globalRoot, rawURL);
''',
    '''        if ([name hasSuffix:@".disabled"]) {
            NSLog(@"Skipping disabled tweak %@", name);
            continue;
        }
        if ([blockedNames containsObject:name]) {
            NSLog(@"Skipping blocked tweak %@", name);
            continue;
        }

        NSURL *fileURL = FlekCanonicalScopedURL(globalRoot, rawURL);
''',
)
replace_all(loader, "loadTweaksRecursively(fileURL, globalRoot, errors);", "loadTweaksRecursively(fileURL, globalRoot, errors, blockedNames);")
replace_all(loader, "loadTweaksRecursively(profile, globalFolderURL, errors);", "loadTweaksRecursively(profile, globalFolderURL, errors, blockedNames);")
replace_all(loader, "loadTweaksRecursively(perAppFolder, globalFolderURL, errors);", "loadTweaksRecursively(perAppFolder, globalFolderURL, errors, blockedNames);")


print("finish_vibe_settings_port changed:")
for path in sorted(set(changed)):
    print(" -", path)
'''
p.write_text(head + tail)
print("Rebased finish patch onto staging-safe TweakLoader")
