from pathlib import Path

# Project boundary: make FlekDeck's newer Xcode project build VibeContainers'
# exact TweakLoader source without editing that Vibe source.
p = Path("LiveContainer.xcodeproj/project.pbxproj")
s = p.read_text()

# VibeContainers' TweakLoader target includes utils.m. FlekDeck's newer project
# dropped it when its newer guest-hook implementation no longer needed swizzle().
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

# Shell boundary: FlekDeck's newer SideStoreSupport calls APIs that were added
# after the VibeContainers 3.8.0 runtime. Keep the newer SideStore UI/hooks, but
# make those hooks use the exact equivalent operations Vibe 3.8.0 expects.
p = Path("SideStoreSupport/SideStoreHooks.m")
s = p.read_text()

s = s.replace("[LCSharedUtils launchToGuestAppWithClassicMode:0];", "[LCSharedUtils launchToGuestApp];")
s = s.replace("swizzleClassMethod(", "SSVibeSwizzleClassMethod(")
s = s.replace("swizzle(", "SSVibeSwizzle(")

helper_anchor = "@import UIKit;\n"
helpers = '''@import UIKit;\n\n// FlekDeck SideStoreSupport is newer than VibeContainers 3.8.0. Keep the\n// compatibility helpers local to this shell target so Vibe's core remains\n// byte-identical. Their implementation is the same method exchange used by\n// VibeContainers TweakLoader/utils.m.\nstatic void SSVibeSwizzle(Class cls, SEL originalAction, SEL swizzledAction) {\n    method_exchangeImplementations(class_getInstanceMethod(cls, originalAction),\n                                   class_getInstanceMethod(cls, swizzledAction));\n}\n\nstatic void SSVibeSwizzleClassMethod(Class cls, SEL originalAction, SEL swizzledAction) {\n    method_exchangeImplementations(class_getClassMethod(cls, originalAction),\n                                   class_getClassMethod(cls, swizzledAction));\n}\n'''
if "static void SSVibeSwizzle(" not in s:
    if helper_anchor not in s:
        raise SystemExit("Could not find SideStoreHooks UIKit import anchor")
    s = s.replace(helper_anchor, helpers, 1)

p.write_text(s)

# FlekDeck's LCAppListView also carries newer Classic Mode delegate/JIT APIs.
# Apply the separate UI-only adapter after the Vibe core has been copied.
exec(Path("Tools/patch_vibecontainers_applist_compat.py").read_text(), {})

print("Restored Vibe TweakLoader project membership and adapted Flek shell to Vibe runtime semantics.")
