from pathlib import Path


def replace_between(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    p = Path(path)
    s = p.read_text()
    start = s.index(start_marker)
    end = s.index(end_marker, start)
    p.write_text(s[:start] + replacement + s[end:])


# 1) Share-sheet IPA handoff: use Duy LiveContainer's bookmark/original-file flow.
# Only the app URL scheme stays FlekDeck-specific.
p = Path("ShareExtension/ShareExtensionViewModel.swift")
s = p.read_text()
start = s.index("    func installSharedFileInLiveContainer(context: NSExtensionContext?) async {")
end = s.index("\n    /// Copies the shared file into the app group", start)
replacement = '''    func installSharedFileInLiveContainer(context: NSExtensionContext?) async {
        if isLaunching {
            return
        }
        guard case .file(let fileURL) = payload.kind else {
            return
        }
        isLaunching = true
        defer { isLaunching = false }

        do {
            try storeBookmark(for: fileURL)
            guard var components = URLComponents(string: "flekdeck://install") else {
                throw ShareExtensionError("Unable to build install URL.")
            }
            components.queryItems = [
                URLQueryItem(name: "url", value: fileURL.absoluteString)
            ]
            guard let installURL = components.url else {
                throw ShareExtensionError("Unable to build install URL.")
            }

            LCShareExtensionLauncher.openURL(fromShareExtension: installURL)
            (context ?? currentContext)?.completeRequest(returningItems: nil, completionHandler: nil)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
'''
s = s[:start] + replacement + s[end:]
p.write_text(s)


# 2) Upstream no longer stages shared IPAs into a fork-only app-group inbox.
# Keep the launch-time hook callable, but it has nothing to clean.
p = Path("LiveContainerSwiftUI/Utilities/Shared.swift")
s = p.read_text()
start = s.index("    public static func clearStaleShareInbox() {")
end = s.index("\n    /// Appended to the folder of an app that is being replaced", start)
s = s[:start] + '''    public static func clearStaleShareInbox() {
        // Duy upstream hands shared IPA URLs over by security-scoped bookmark.
        // There is no separate staged app-group inbox in this parity build.
    }
''' + s[end:]
p.write_text(s)


# 3) The Flek download queue stays as UI/progress plumbing, but the final install
# path must feed Duy's exact LCAppInfo.patchExecAndSignIfNeed implementation.
p = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = p.read_text()
# Remove cleanup for the retired staged-share-inbox flow.
staged_cleanup = '''                        // A copy the share extension staged in the app group is
                        // ours to remove, and exists for no other reason than to
                        // have reached us. It sits in a folder of its own.
                        if let shareInbox = LCSharedUtils.shareInboxPath(),
                           fileURL.path.hasPrefix(shareInbox.path + "/") {
                            try? fm.removeItem(at: fileURL.deletingLastPathComponent())
                        }
'''
s = s.replace(staged_cleanup, "")

# Duy's pinned upstream install/signing path does not carry the fork-only custom
# bundle-ID rewrite. Drop it here rather than altering upstream LCAppInfo.
custom_id_start = "        // A bundle ID chosen on the app's page. Goes through LCAppInfo rather"
if custom_id_start in s:
    start = s.index(custom_id_start)
    end = s.index("\n        var appRelativePath", start)
    s = s[:start] + s[end:]
p.write_text(s)


# 4) Flek's conversion UI had a resumable move classifier that Duy upstream does
# not expose. Localize only the classifier; the actual atomic mover remains the
# exact upstream LCUtils.moveFilesAtomicallyAfterPreflight implementation.
p = Path("LiveContainerSwiftUI/Models/LCAppModel+Conversion.swift")
s = p.read_text()
s = s.replace("LCUtils.MoveStep", "FlekMoveStep")
s = s.replace("LCUtils.planMove(from: source, to: destination)", "flekPlanMove(from: source, to: destination)")

classifier_anchor = "    /// Whether the bundle still has to be moved, has already been moved by an\n"
if "private enum FlekMoveStep" not in s:
    classifier = '''    private enum FlekMoveStep {
        case pending
        case alreadyDone
        case missing
        case blocked
    }

    private func flekPlanMove(from source: URL, to destination: URL) -> FlekMoveStep {
        let fm = FileManager.default
        let sourceExists = fm.fileExists(atPath: source.standardizedFileURL.path)
        let destinationExists = fm.fileExists(atPath: destination.standardizedFileURL.path)
        switch (sourceExists, destinationExists) {
        case (true, false): return .pending
        case (true, true): return .blocked
        case (false, true): return .alreadyDone
        case (false, false): return .missing
        }
    }

'''
    idx = s.index(classifier_anchor)
    s = s[:idx] + classifier + s[idx:]

# Flek's home/banner uninstall UX uses helpers removed from Duy's current model.
# Keep them in this fork-only extension instead of modifying upstream LCAppModel.
if "private enum FlekUninstallRefused" not in s:
    s += '''

private enum FlekUninstallRefused: LocalizedError {
    case sharedBundle

    var errorDescription: String? {
        switch self {
        case .sharedBundle:
            return "This app is stored in the shared folder, so every FlekDeck on this device uses the same copy — deleting it here would remove it for all of them.\\n\\nTo delete it, open the app's settings and tap \\"Convert to Private App\\" first."
        }
    }
}

extension LCAppModel {
    var isBundleMissing: Bool {
        guard let bundlePath = appInfo.bundlePath(), !bundlePath.isEmpty else {
            return true
        }
        return !FileManager.default.fileExists(atPath: bundlePath)
    }

    var isUninstallable: Bool {
        !uiIsShared || isBundleMissing
    }

    func uninstall(removingContainers: Bool) throws {
        guard isUninstallable else {
            throw FlekUninstallRefused.sharedBundle
        }

        let fm = FileManager.default
        if let bundlePath = appInfo.bundlePath(), !isBundleMissing {
            try fm.removeItem(atPath: bundlePath)
        }

        guard removingContainers else { return }
        for container in uiContainers {
            let folderName = container.folderName
            if container.storageBookMark == nil {
                try? fm.removeItem(at: container.containerURL)
            }
            LCUtils.removeAppKeychain(dataUUID: folderName)
            DispatchQueue.main.async {
                DataManager.shared.model.appDataFolderNames.removeAll { $0 == folderName }
            }
        }
    }
}
'''

p.write_text(s)

print("Applied FlekDeck shell compatibility without modifying Duy signing/JIT core.")
