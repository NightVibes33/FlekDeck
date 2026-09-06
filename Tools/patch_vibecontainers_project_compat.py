from pathlib import Path

p = Path("LiveContainer.xcodeproj/project.pbxproj")
s = p.read_text()

# VibeContainers' TweakLoader target includes utils.m. FlekDeck's newer project
# dropped it when its newer guest-hook implementation no longer needed swizzle().
# The Vibe runtime still calls swizzle/swizzleClassMethod from DocumentPicker.m,
# so restore the exact target membership without editing Vibe source.
needle = '''\t\t174140F52D9C1C9B00F3F928 /* PBXFileSystemSynchronizedBuildFileExceptionSet */ = {
\t\t\tisa = PBXFileSystemSynchronizedBuildFileExceptionSet;
\t\t\tmembershipExceptions = (
'''
start = s.index(needle)
end = s.index("\n\t\t\t);", start)
block = s[start:end]
if "\t\t\t\tutils.m," not in block:
    insert_after = '\t\t\t\t"UIKit+GuestHooks.m",'
    if insert_after not in block:
        raise SystemExit("Could not find TweakLoader UIKit membership anchor")
    block = block.replace(insert_after, insert_after + "\n\t\t\t\tutils.m,")
    s = s[:start] + block + s[end:]

p.write_text(s)
print("Restored VibeContainers TweakLoader utils.m target membership.")
