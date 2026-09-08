from pathlib import Path

JITLESS_HOST_ERROR = (
    "JIT-less guest execution requires FlekDeck itself to be signed with a development profile "
    "that grants get-task-allow. The imported certificate can still pass the signing test while "
    "iOS blocks executable mmap from Documents. Re-sign FlekDeck with an Apple Development / "
    "Personal Team profile, or enable JIT for this app."
)

# Keep FlekDeck's SideStore integration rebrand-aware.
p = Path("SideStoreSupport/SideStoreHooks.m")
s = p.read_text()
s = s.replace(
    '+ (NSString*)hook_appbundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_appbundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    return @"com.kdt.livecontainer";\n}',
    '+ (NSString*)hook_storeAppBundleIdentifier {\n    NSString *bundleID = NSUserDefaults.lcMainBundle.bundleIdentifier;\n    return bundleID.length > 0 ? bundleID : @"com.fs.flekdeck";\n}'
)
s = s.replace(
    'https://github.com/LiveContainer/LiveContainer/releases/download/1.0/apps_ss_lc.json',
    'https://raw.githubusercontent.com/NightVibes33/FlekDeck/main/.github/flekdeck-side-source.json'
)
if 'com.fs.flekdeck' not in s or 'flekdeck-side-source.json' not in s:
    raise SystemExit("SideStore rebrand patch did not apply")
p.write_text(s)

# Keep the startup entitlement check informational only. The JIT-less diagnostic
# and launch path below provide the precise error only when the user actually
# tries to use JIT-less execution.
tab_path = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
tab = tab_path.read_text()
old_check = '''    func checkGetTaskAllow() {\n        let task = SecTaskCreateFromSelf(nil)\n        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil), (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {\n            errorInfo = "lc.settings.notDevCert".loc\n            errorShow = true\n            return\n        }\n    }\n'''
new_check = '''    func checkGetTaskAllow() {\n        // Informational only at startup. The JIT-less test and launch path do\n        // the authoritative capability check when JIT-less is actually used.\n        let task = SecTaskCreateFromSelf(nil)\n        let allowed = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil)\n            .map { ($0.takeRetainedValue() as? NSNumber)?.boolValue ?? false } ?? false\n        if !allowed {\n            print("FlekDeck: host get-task-allow is false; JIT-less guest execution is unavailable unless JIT is enabled")\n        }\n    }\n'''
if old_check in tab:
    tab = tab.replace(old_check, new_check, 1)
elif 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Unexpected get-task-allow alert shape in LCTabView")
if 'errorInfo = "lc.settings.notDevCert".loc' in tab:
    raise SystemExit("Old fatal development-certificate startup alert still present")
tab_path.write_text(tab)

# Add a single native capability helper. Upstream's validateJITLessSetup only
# verifies that the imported certificate can sign TestJITLess.dylib and that the
# resulting code signature validates; it does not dlopen the guest from
# Documents. A host without get-task-allow can therefore report a false pass and
# then fail with `file system sandbox blocked mmap()` on the real guest.
h_path = Path("LiveContainerSwiftUI/Utilities/LCUtils.h")
h = h_path.read_text()
method_decl = '+ (BOOL)hostAllowsJITLessExecution;\n'
if method_decl not in h:
    anchor = '@interface LCUtils : NSObject\n\n'
    if anchor not in h:
        raise SystemExit("LCUtils.h interface anchor not found")
    h = h.replace(anchor, anchor + method_decl, 1)
h_path.write_text(h)

m_path = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
m = m_path.read_text()
if '+ (BOOL)hostAllowsJITLessExecution {' not in m:
    anchor = '@implementation LCUtils\n'
    helper = '''@implementation LCUtils\n\n+ (BOOL)hostAllowsJITLessExecution {\n    SecTaskRef task = SecTaskCreateFromSelf(NULL);\n    if (!task) return NO;\n    CFTypeRef value = SecTaskCopyValueForEntitlement(task, CFSTR("get-task-allow"), NULL);\n    BOOL allowed = NO;\n    if (value && CFGetTypeID(value) == CFBooleanGetTypeID()) {\n        allowed = CFBooleanGetValue((CFBooleanRef)value);\n    } else if (value && CFGetTypeID(value) == CFNumberGetTypeID()) {\n        int intValue = 0;\n        if (CFNumberGetValue((CFNumberRef)value, kCFNumberIntType, &intValue)) {\n            allowed = intValue != 0;\n        }\n    }\n    if (value) CFRelease(value);\n    CFRelease(task);\n    return allowed;\n}\n'''
    if anchor not in m:
        raise SystemExit("LCUtils.m implementation anchor not found")
    m = m.replace(anchor, helper, 1)

validate_anchor = '+ (void)validateJITLessSetupWithCompletionHandler:(void (^)(BOOL success, NSError *error))completionHandler {\n'
if 'FlekDeckJITLessHostCapability' not in m:
    validate_prefix = validate_anchor + '''    if (![self hostAllowsJITLessExecution]) {\n        NSError *hostError = [NSError errorWithDomain:@"FlekDeckJITLessHostCapability"\n                                                  code:1\n                                              userInfo:@{NSLocalizedDescriptionKey: @"__ERROR__"}];\n        completionHandler(NO, hostError);\n        return;\n    }\n'''.replace('__ERROR__', JITLESS_HOST_ERROR.replace('"', '\\"'))
    if validate_anchor not in m:
        raise SystemExit("validateJITLessSetup anchor not found")
    m = m.replace(validate_anchor, validate_prefix, 1)
m_path.write_text(m)

# Gate only the non-JIT guest path. JIT-enabled apps, including 32-bit guests,
# keep using Vibe/LiveContainer's normal JIT flow.
model_path = Path("LiveContainerSwiftUI/Models/LCAppModel.swift")
model = model_path.read_text()
if 'FlekDeckJITLessHostCapability' not in model:
    anchor = '''    func runApp(multitask: Bool? = nil, containerFolderName : String? = nil, bundleIdOverride : String? = nil, urlStr : String? = nil, forceJIT: Bool? = nil) async throws{\n        if isAppRunning {\n            return\n        }\n'''
    replacement = anchor + '''\n#if !targetEnvironment(simulator)\n        let flekWillUseJIT = forceJIT ?? (appInfo.isJITNeeded || appInfo.is32bit)\n        if !flekWillUseJIT && !LCUtils.hostAllowsJITLessExecution() {\n            throw "__ERROR__"\n        }\n#endif\n'''.replace('__ERROR__', JITLESS_HOST_ERROR.replace('"', '\\"'))
    if anchor not in model:
        raise SystemExit("LCAppModel.runApp anchor not found")
    model = model.replace(anchor, replacement, 1)
model_path.write_text(model)

# Preserve the real upstream signer and guest launch beyond this capability gate.
diag = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift").read_text()
if "LCUtils.validateJITLessSetup" not in diag:
    raise SystemExit("JIT-less diagnostic no longer calls validateJITLessSetup")
if "LCSharedUtils.launchToGuestApp" not in model:
    raise SystemExit("LCAppModel no longer contains the upstream guest launch path")
if "hostAllowsJITLessExecution" not in model or "hostAllowsJITLessExecution" not in m:
    raise SystemExit("JIT-less host capability gate did not apply")

print("Applied accurate JIT-less host capability gating and signer-compatible SideStore integration")
