from pathlib import Path

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
print("Patched ShareExtension install handoff to upstream behavior (FlekDeck URL scheme only).")
