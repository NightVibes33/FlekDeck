#!/usr/bin/env python3
from pathlib import Path

# Final on-device regression containment for the LiveContainer parity branch.
# This runs AFTER the older parity/stability generators. It must never invent
# guest errors and it must keep host-signing diagnostics from masking a real
# guest crash report.

# 1) Swift and ObjC must agree on the defaults domain. LCSharedUtils.appGroupID()
# is nullable in Swift; unwrap it before testing isEmpty.
utils = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
text = utils.read_text()
text = text.replace(
'''    public static let appGroupUserDefault: UserDefaults = {
        let groupID = LCSharedUtils.appGroupID()
        guard !groupID.isEmpty,
              groupID != "Unknown",
              let defaults = UserDefaults(suiteName: groupID) else {
            return .standard
        }
        return defaults
    }()''',
'''    public static let appGroupUserDefault: UserDefaults = {
        guard let groupID = LCSharedUtils.appGroupID(),
              !groupID.isEmpty,
              groupID != "Unknown",
              let defaults = UserDefaults(suiteName: groupID) else {
            return .standard
        }
        return defaults
    }()''',
1,
)
utils.write_text(text)

# 2) Root crash/error presentation: use LiveContainer's REAL diagnostic string.
# The previous parity patch synthesized the same fallback text for unrelated
# failures. Remove that fallback entirely while retaining readable layout.
tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
text = tab.read_text()
text = text.replace("Text(displayErrorInfo(errorInfo))", "Text(errorInfo)")
text = text.replace("ShareLink(item: displayErrorInfo(errorInfo))", "ShareLink(item: errorInfo)")
text = text.replace(
'''    func displayErrorInfo(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "An unknown error occurred. No diagnostic text was provided."
        }
        return value
    }

    func copyError() { UIPasteboard.general.string = displayErrorInfo(errorInfo) }''',
'''    func copyError() { UIPasteboard.general.string = errorInfo }''',
1,
)

# Real launch errors have priority over host diagnostics. Do not replace a guest
# crash with a team-id/get-task-allow/bookmark message during the same startup.
old_last_error = '''    func checkLastLaunchError() {
        var errorStr = UserDefaults.standard.string(forKey: "error")
        if errorStr == nil && UserDefaults.standard.bool(forKey: "SigningInProgress") {
            errorStr = "lc.signer.crashDuringSignErr".loc
            UserDefaults.standard.removeObject(forKey: "SigningInProgress")
        }
        guard let errorStr else { return }
        UserDefaults.standard.removeObject(forKey: "error")
        errorInfo = errorStr
        crashReportShow = true
    }'''
new_last_error = '''    @discardableResult
    func checkLastLaunchError() -> Bool {
        var errorStr = UserDefaults.standard.string(forKey: "error")
        if errorStr == nil && UserDefaults.standard.bool(forKey: "SigningInProgress") {
            errorStr = "lc.signer.crashDuringSignErr".loc
            UserDefaults.standard.removeObject(forKey: "SigningInProgress")
        }
        guard let errorStr, !errorStr.isEmpty else { return false }
        UserDefaults.standard.removeObject(forKey: "error")
        errorInfo = errorStr
        crashReportShow = true
        return true
    }'''
if old_last_error in text:
    text = text.replace(old_last_error, new_last_error, 1)
elif new_last_error not in text:
    raise SystemExit(f"{tab}: checkLastLaunchError anchor missing")

old_startup = '''        sharedModel.selectedTab = .apps
        closeDuplicatedWindow()
        checkLastLaunchError()
        checkTeamId()
        checkAndSaveBundleId()
        checkGetTaskAllow()
        checkPrivateContainerBookmark()
        checkiOSBeta()
        processPendingURLIfNeeded()'''
new_startup = '''        sharedModel.selectedTab = .apps
        closeDuplicatedWindow()
        let presentedGuestCrash = checkLastLaunchError()
        if !presentedGuestCrash {
            checkTeamId()
            checkAndSaveBundleId()
            checkGetTaskAllow()
            checkPrivateContainerBookmark()
        }
        checkiOSBeta()
        processPendingURLIfNeeded()'''
if old_startup in text:
    text = text.replace(old_startup, new_startup, 1)
elif new_startup not in text:
    raise SystemExit(f"{tab}: startup diagnostic sequence anchor missing")

# FlekDeck intentionally supports distribution/JIT-less installs where
# get-task-allow=false. That is a diagnostic fact, not a launch error, so never
# surface it as the same modal error on every failed guest launch.
old_gta = '''    func checkGetTaskAllow() {
        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil), (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false else {
            errorInfo = "lc.settings.notDevCert".loc
            errorShow = true
            return
        }
    }'''
new_gta = '''    func checkGetTaskAllow() {
        let task = SecTaskCreateFromSelf(nil)
        guard let value = SecTaskCopyValueForEntitlement(task, "get-task-allow" as CFString, nil) else {
            NSLog("[FlekDeck] get-task-allow entitlement is absent; valid for distribution/JIT-less installs")
            return
        }
        let allowed = (value.takeRetainedValue() as? NSNumber)?.boolValue ?? false
        if !allowed {
            NSLog("[FlekDeck] get-task-allow=false; keeping this as a diagnostic instead of a launch error")
        }
    }'''
if old_gta in text:
    text = text.replace(old_gta, new_gta, 1)
elif new_gta not in text:
    raise SystemExit(f"{tab}: get-task-allow anchor missing")

tab.write_text(text)

# 3) Home/app-list errors: same rule. Never synthesize a fake fallback string.
app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
text = text.replace("Text(displayErrorInfo(errorInfo))", "Text(errorInfo)")
text = text.replace(
'''    func displayErrorInfo(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "An unknown error occurred. No diagnostic text was provided."
        }
        return value
    }

    func copyError() {
        UIPasteboard.general.string = displayErrorInfo(errorInfo)
    }''',
'''    func copyError() {
        UIPasteboard.general.string = errorInfo
    }''',
1,
)
app_list.write_text(text)

# 4) Runtime seeding must never take normal app discovery down with it. Also do
# not force-unwrap arbitrary .app directories: one malformed import should be
# skipped and logged rather than crashing FlekDeck at startup.
app_entry = Path("LiveContainerSwiftUI/App/LiveContainerSwiftUIApp.swift")
text = app_entry.read_text()
old_seed = '''        do {
            try Self.seedBundled32BitRuntime(using: fm)

            // load apps
            try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)'''
new_seed = '''        do {
            try Self.seedBundled32BitRuntime(using: fm)
        } catch {
            NSLog("[FlekDeck/LC32] Runtime seed failed without blocking app discovery: \\(error)")
        }

        do {
            // load apps
            try fm.createDirectory(at: LCPath.bundlePath, withIntermediateDirectories: true)'''
if old_seed in text:
    text = text.replace(old_seed, new_seed, 1)
elif new_seed not in text:
    raise SystemExit(f"{app_entry}: runtime seed/app discovery anchor missing")

old_private = '''                let newApp = LCAppInfo(bundlePath: "\\(LCPath.bundlePath.path)/\\(appDir)")!
                newApp.relativeBundlePath = appDir
                newApp.isShared = false
                if newApp.isHidden {
                    tempHiddenApps.append(LCAppModel(appInfo: newApp))
                } else {
                    tempApps.append(LCAppModel(appInfo: newApp))
                    tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
                }
#if is32BitSupported
                if newApp.is32bitEmulator {
                    tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                }
#endif'''
new_private = '''                guard let newApp = LCAppInfo(bundlePath: "\\(LCPath.bundlePath.path)/\\(appDir)") else {
                    NSLog("[FlekDeck] Skipping malformed app bundle: %@", appDir)
                    continue
                }
                newApp.relativeBundlePath = appDir
                newApp.isShared = false
#if is32BitSupported
                if newApp.is32bitEmulator {
                    tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                    continue
                }
#endif
                if newApp.isHidden {
                    tempHiddenApps.append(LCAppModel(appInfo: newApp))
                } else {
                    tempApps.append(LCAppModel(appInfo: newApp))
                    tempURLSchemes?.formUnion((newApp.urlSchemes() as? [String]) ?? [])
                }'''
if old_private in text:
    text = text.replace(old_private, new_private, 1)
elif new_private not in text:
    raise SystemExit(f"{app_entry}: private app discovery anchor missing")

old_shared = '''                    let newApp = LCAppInfo(bundlePath: "\\(LCPath.lcGroupBundlePath.path)/\\(appDir)")!
                    newApp.relativeBundlePath = appDir
                    newApp.isShared = true
                    if newApp.isHidden {
                        tempHiddenApps.append(LCAppModel(appInfo: newApp))
                    } else {
                        tempApps.append(LCAppModel(appInfo: newApp))
                        tempURLSchemes?.formUnion(newApp.urlSchemes() as! [String])
                    }
#if is32BitSupported
                    if newApp.is32bitEmulator {
                        tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                    }
#endif'''
new_shared = '''                    guard let newApp = LCAppInfo(bundlePath: "\\(LCPath.lcGroupBundlePath.path)/\\(appDir)") else {
                        NSLog("[FlekDeck] Skipping malformed shared app bundle: %@", appDir)
                        continue
                    }
                    newApp.relativeBundlePath = appDir
                    newApp.isShared = true
#if is32BitSupported
                    if newApp.is32bitEmulator {
                        tempArm32EmuApps.append(LCAppModel(appInfo: newApp))
                        continue
                    }
#endif
                    if newApp.isHidden {
                        tempHiddenApps.append(LCAppModel(appInfo: newApp))
                    } else {
                        tempApps.append(LCAppModel(appInfo: newApp))
                        tempURLSchemes?.formUnion((newApp.urlSchemes() as? [String]) ?? [])
                    }'''
if old_shared in text:
    text = text.replace(old_shared, new_shared, 1)
elif new_shared not in text:
    raise SystemExit(f"{app_entry}: shared app discovery anchor missing")
app_entry.write_text(text)

# 5) Keep the old error-ui generator from putting the synthetic fallback back
# the next time the full parity workflow runs.
error_gen = Path("Tools/patch_flekdeck_error_ui_parity.py")
if error_gen.exists():
    gen = error_gen.read_text()
    gen = gen.replace("Text(displayErrorInfo(errorInfo))", "Text(errorInfo)")
    gen = gen.replace("ShareLink(item: displayErrorInfo(errorInfo))", "ShareLink(item: errorInfo)")
    gen = gen.replace("UIPasteboard.general.string = displayErrorInfo(errorInfo)", "UIPasteboard.general.string = errorInfo")
    # Make the generator idempotent on a branch where raw LiveContainer errors
    # are already restored: do not require the synthetic helper markers.
    gen = gen.replace('            "No diagnostic text was provided",\n', '')
    error_gen.write_text(gen)

# Invariants.
for path in (tab, app_list):
    value = path.read_text()
    if "No diagnostic text was provided" in value or "displayErrorInfo(errorInfo)" in value:
        raise SystemExit(f"{path}: synthetic/fake error fallback still present")
if "let presentedGuestCrash = checkLastLaunchError()" not in tab.read_text():
    raise SystemExit(f"{tab}: guest crash priority guard missing")
if "get-task-allow=false; keeping this as a diagnostic" not in tab.read_text():
    raise SystemExit(f"{tab}: distribution-signing diagnostic guard missing")
if "guard let groupID = LCSharedUtils.appGroupID()" not in utils.read_text():
    raise SystemExit(f"{utils}: nullable app-group identifier is still unsafe")
entry_value = app_entry.read_text()
if "Runtime seed failed without blocking app discovery" not in entry_value:
    raise SystemExit(f"{app_entry}: runtime seeding is still coupled to app discovery")
if 'LCAppInfo(bundlePath: "\\(LCPath.bundlePath.path)/\\(appDir)")!' in entry_value:
    raise SystemExit(f"{app_entry}: private app discovery still force-unwraps LCAppInfo")
if 'LCAppInfo(bundlePath: "\\(LCPath.lcGroupBundlePath.path)/\\(appDir)")!' in entry_value:
    raise SystemExit(f"{app_entry}: shared app discovery still force-unwraps LCAppInfo")

print("FlekDeck on-device regression fixes applied: real errors preserved, startup/runtime discovery hardened")
