from pathlib import Path

# Temp-branch-only verification for PID-specific StikDebug JIT.
# This runs after patch_direct_multitask_host_bridge.py, which already rewrites
# the old stikjit:// scheme to current stikdebug:// routing.

# ---------------------------------------------------------------------------
# 1) Export small process-signing helpers to Swift.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Utilities/LCUtils.h")
s = p.read_text(encoding="utf-8")
anchor = "uint32_t dyld_get_sdk_version(const struct mach_header* mh);\n"
exports = """uint32_t dyld_get_sdk_version(const struct mach_header* mh);\nBOOL LCFlekProcessHasGetTaskAllow(int pid);\nBOOL LCFlekProcessIsDebugged(int pid);\nvoid LCFlekTerminateProcess(int pid);\n"""
if "LCFlekProcessIsDebugged" not in s:
    if anchor not in s:
        raise SystemExit("LCUtils.h dyld declaration anchor not found")
    s = s.replace(anchor, exports, 1)
p.write_text(s, encoding="utf-8")

p = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
s = p.read_text(encoding="utf-8")
if "LCFlekProcessIsDebugged" not in s:
    impl_anchor = "@implementation LCUtils\n"
    support = r'''#include <sys/types.h>
#include <signal.h>

extern int csops(pid_t pid, unsigned int ops, void *useraddr, size_t usersize);

#ifndef CS_GET_TASK_ALLOW
#define CS_GET_TASK_ALLOW 0x00000004
#endif
#ifndef CS_DEBUGGED
#define CS_DEBUGGED 0x10000000
#endif

static BOOL LCFlekReadCSFlags(int pid, uint32_t *flagsOut) {
    if (pid <= 0 || !flagsOut) return NO;
    uint32_t flags = 0;
    if (csops((pid_t)pid, 0, &flags, sizeof(flags)) != 0) {
        return NO;
    }
    *flagsOut = flags;
    return YES;
}

BOOL LCFlekProcessHasGetTaskAllow(int pid) {
    uint32_t flags = 0;
    return LCFlekReadCSFlags(pid, &flags) && (flags & CS_GET_TASK_ALLOW) != 0;
}

BOOL LCFlekProcessIsDebugged(int pid) {
    uint32_t flags = 0;
    return LCFlekReadCSFlags(pid, &flags) && (flags & CS_DEBUGGED) != 0;
}

void LCFlekTerminateProcess(int pid) {
    if (pid > 0) {
        kill((pid_t)pid, SIGTERM);
    }
}

'''
    if impl_anchor not in s:
        raise SystemExit("LCUtils.m implementation anchor not found")
    s = s.replace(impl_anchor, support + impl_anchor, 1)
p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------------------
# 2) Replace only the PID-specific JIT delegate with a verified StikDebug path.
# Normal JIT-less Parallel launch is not touched.
# ---------------------------------------------------------------------------
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text(encoding="utf-8")
start = s.find("    func jitLaunch(withPID pid: Int,")
end = s.find("    func showRunWhenMultitaskAlert()", start)
if start < 0 or end < 0:
    raise SystemExit("LCAppListView PID JIT function anchors not found")

replacement = r'''    func jitLaunch(withPID pid: Int, withScript script: String? = nil, appName: String) async {
        guard let jitEnabler = JITEnablerType(rawValue: LCUtils.appGroupUserDefault.integer(forKey: "LCJITEnablerType")) else {
            await MainActor.run {
                errorInfo = "No JIT provider is selected."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        // Keep StosDebug behavior separate. This change is intentionally scoped
        // to the StikDebug provider selected in Settings.
        if jitEnabler == .StosDebug || jitEnabler == .StosDebugLC {
            await MainActor.run {
                let encodedData = script?.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)
                let encoded = encodedData.map { "&script=\($0)" } ?? ""
                if jitEnabler == .StosDebugLC {
                    if let _ = sharedModel.apps.first(where: { app in
                        app.appInfo.urlSchemes().contains("stosdebug") &&
                        (sharedModel.multiLCStatus != 2 || app.appInfo.isShared)
                    }) {
                        if let url = URL(string: "stosdebug://enableJIT?bundleId=\(Bundle.main.bundleIdentifier!)&appName=\(appName)&pid=\(pid)&relaunchApp=false&forcePID=true\(encoded)") {
                            Task { await openWebView(urlString: url.absoluteString) }
                        }
                    } else {
                        errorInfo = "StosDebug is not found. Please install it first and switch it to shared app."
                        errorShow = true
                    }
                } else if let url = URL(string: "stosdebug://enableJIT?bundleId=\(Bundle.main.bundleIdentifier!)&appName=\(appName)&pid=\(pid)&forcePID=true\(encoded)") {
                    UIApplication.shared.open(url)
                }
            }
            return
        }

        guard jitEnabler == .StikJIT || jitEnabler == .StikJITLC else {
            await MainActor.run {
                errorInfo = "The selected JIT provider does not support PID attachment required by Run Parallel. Select StikDebug."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        // StikDebug can only debug a target signed with get-task-allow. Check the
        // exact LiveProcess PID rather than assuming the host app entitlement
        // propagated to the extension during signing.
        guard LCFlekProcessHasGetTaskAllow(Int32(pid)) else {
            await MainActor.run {
                errorInfo = "LiveProcess PID \(pid) does not have get-task-allow. Re-sign FlekDeck with a development/SideStore-style signer that preserves the LiveProcess extension, then try again."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        guard let bundleID = Bundle.main.bundleIdentifier else {
            await MainActor.run {
                errorInfo = "Unable to determine FlekDeck's bundle identifier for StikDebug."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        var components = URLComponents()
        components.scheme = "stikdebug"
        components.host = "enable-jit"
        components.queryItems = [
            URLQueryItem(name: "bundle-id", value: bundleID),
            URLQueryItem(name: "pid", value: String(pid))
        ]
        if let script, !script.isEmpty {
            // App settings store the selected iOS 26/27 script as Base64 file
            // contents, which is exactly what current StikDebug expects here.
            components.queryItems?.append(URLQueryItem(name: "script-data", value: script))
        }

        guard let url = components.url else {
            await MainActor.run {
                errorInfo = "Unable to build the StikDebug PID request."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        let opened: Bool
        if jitEnabler == .StikJITLC {
            opened = await MainActor.run {
                guard sharedModel.apps.contains(where: { app in
                    app.appInfo.urlSchemes().contains("stikdebug") &&
                    (sharedModel.multiLCStatus != 2 || app.appInfo.isShared)
                }) else {
                    errorInfo = "StikDebug is not found inside FlekDeck. Install it and make it shared first."
                    errorShow = true
                    return false
                }
                Task { await openWebView(urlString: url.absoluteString) }
                return true
            }
        } else {
            opened = await withCheckedContinuation { continuation in
                DispatchQueue.main.async {
                    UIApplication.shared.open(url, options: [:]) { accepted in
                        continuation.resume(returning: accepted)
                    }
                }
            }
        }

        guard opened else {
            await MainActor.run {
                errorInfo = "FlekDeck could not open StikDebug. Install or update StikDebug, then try again."
                errorShow = true
            }
            LCFlekTerminateProcess(Int32(pid))
            return
        }

        // Opening the URL only proves that iOS accepted it. Do not report success
        // until the exact LiveProcess PID has CS_DEBUGGED set by StikDebug.
        let deadline = Date().addingTimeInterval(60)
        while Date() < deadline {
            if LCFlekProcessIsDebugged(Int32(pid)) {
                return
            }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }

        LCFlekTerminateProcess(Int32(pid))
        await MainActor.run {
            var detail = "StikDebug opened, but JIT was not attached to LiveProcess PID \(pid) within 60 seconds. Check LocalDevVPN, the pairing file, and Developer Disk Image state."
            if #available(iOS 26.0, *), script?.isEmpty != false {
                detail += " On iOS 26+, TXM/SPTM guests also need the matching JIT script configured in the app's settings."
            }
            errorInfo = detail
            errorShow = true
        }
    }

'''

s = s[:start] + replacement + s[end:]
if 'stikjit://enable-jit' in s:
    raise SystemExit("Obsolete stikjit PID URL remains after verification patch")
for marker in [
    'components.scheme = "stikdebug"',
    'URLQueryItem(name: "pid", value: String(pid))',
    'URLQueryItem(name: "script-data", value: script)',
    'LCFlekProcessHasGetTaskAllow(Int32(pid))',
    'LCFlekProcessIsDebugged(Int32(pid))',
]:
    if marker not in s:
        raise SystemExit(f"Missing StikDebug verification marker: {marker}")
p.write_text(s, encoding="utf-8")

print("Added verified StikDebug PID JIT handoff for Run Parallel")
