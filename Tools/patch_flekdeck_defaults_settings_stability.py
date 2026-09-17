#!/usr/bin/env python3
from pathlib import Path

# Canonical, idempotent replacement for the non-Compatibility pieces of the
# legacy runtime_stability pass. Compatibility and Mach-O now have dedicated
# safer passes and must not be reconstructed here.

# 1) Swift/UI and ObjC/bootstrap must read the same defaults domain when there
# is no usable app-group entitlement.
utils = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
text = utils.read_text()
old = '    public static let appGroupUserDefault = UserDefaults.init(suiteName: LCSharedUtils.appGroupID()) ?? UserDefaults.standard'
new = '''    public static let appGroupUserDefault: UserDefaults = {
        guard let groupID = LCSharedUtils.appGroupID(),
              !groupID.isEmpty,
              groupID != "Unknown",
              let defaults = UserDefaults(suiteName: groupID) else {
            return .standard
        }
        return defaults
    }()'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{utils}: app-group defaults anchor missing")
    text = text.replace(old, new, 1)

old_jit = '''        guard let groupUserDefaults = UserDefaults(suiteName: LCSharedUtils.appGroupID()),
              let jitEnabler = JITEnablerType(rawValue: groupUserDefaults.integer(forKey: "LCJITEnablerType")) else {
            return false
        }'''
new_jit = '''        let groupUserDefaults = LCUtils.appGroupUserDefault
        guard let jitEnabler = JITEnablerType(rawValue: groupUserDefaults.integer(forKey: "LCJITEnablerType")) else {
            return false
        }'''
if new_jit not in text:
    if old_jit in text:
        text = text.replace(old_jit, new_jit, 1)
    elif "let groupUserDefaults = LCUtils.appGroupUserDefault" not in text:
        raise SystemExit(f"{utils}: JIT defaults anchor missing")
utils.write_text(text)

# 2) Only the validated ARM32 picker may write LCSelected32BitEmulator.
settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
text = settings.read_text()
raw_runtime = '''                        #if is32BitSupported
                        HStack {
                            Text("32-bit Runtime")
                            Spacer()
                            TextField("", text: $liveExec32Path)
                                .multilineTextAlignment(.trailing)
                        }
                        #endif
'''
text = text.replace(raw_runtime, "", 1)

old_flex = '''                        Button {
                            presentFLEXOverlay()
                        } label: {
                            Text("Show FLEX Overlay")
                        }
                        .disabled(NSClassFromString("FLEXManager") == nil)
'''
new_flex = '''                        if NSClassFromString("FLEXManager") != nil {
                            Button {
                                presentFLEXOverlay()
                            } label: {
                                Text("Show FLEX Overlay")
                            }
                        }
'''
text = text.replace(old_flex, new_flex, 1)
settings.write_text(text)

# Keep the shell parity generator from recreating the disabled FLEX row.
shell_gen = Path("Tools/patch_flekdeck_shell_parity.py")
if shell_gen.exists():
    gen = shell_gen.read_text()
    gen = gen.replace(old_flex, new_flex)
    shell_gen.write_text(gen)

# Invariants.
uv = utils.read_text()
sv = settings.read_text()
if 'groupID != "Unknown"' not in uv or "let groupUserDefaults = LCUtils.appGroupUserDefault" not in uv:
    raise SystemExit("shared-default stability contract is incomplete")
if 'TextField("", text: $liveExec32Path)' in sv:
    raise SystemExit("unsafe raw ARM32 runtime field survived")
if "Default 32-bit Runtime" not in sv:
    raise SystemExit("validated ARM32 runtime picker is missing")

print("FlekDeck defaults/settings stability applied without reconstructing private Compatibility code")
