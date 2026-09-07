import Foundation

enum FDGuestRuntime: Int, CaseIterable, Identifiable {
    case vibe = 0
    case nyxian = 1

    var id: Int { rawValue }
}

final class FDRuntimeSelectionStore {
    static let shared = FDRuntimeSelectionStore()

    private let defaults = LCUtils.appGroupUserDefault
    private let key = "FDRuntimeSelections"

    private init() {}

    func runtime(for app: LCAppModel) -> FDGuestRuntime {
        guard let path = app.appInfo.relativeBundlePath,
              let raw = (defaults.dictionary(forKey: key)?[path] as? NSNumber)?.intValue,
              let runtime = FDGuestRuntime(rawValue: raw) else {
            return .vibe
        }
        return runtime
    }

    func set(_ runtime: FDGuestRuntime, for app: LCAppModel) {
        guard let path = app.appInfo.relativeBundlePath else { return }
        var selections = defaults.dictionary(forKey: key) ?? [:]
        if runtime == .vibe {
            selections.removeValue(forKey: path)
        } else {
            selections[path] = runtime.rawValue
        }
        defaults.set(selections, forKey: key)
    }
}

extension LCAppModel {
    func fdRunApp(
        multitask: Bool? = nil,
        containerFolderName: String? = nil,
        bundleIdOverride: String? = nil,
        urlStr: String? = nil,
        forceJIT: Bool? = nil
    ) async throws {
        guard FDRuntimeSelectionStore.shared.runtime(for: self) == .nyxian else {
            try await runApp(
                multitask: multitask,
                containerFolderName: containerFolderName,
                bundleIdOverride: bundleIdOverride,
                urlStr: urlStr,
                forceJIT: forceJIT
            )
            return
        }

        guard let bundlePath = appInfo.bundlePath() else {
            throw "Nyxian runtime could not resolve the application bundle."
        }
        try await FDNyxianRuntimeBridge.shared.launchApplication(
            atBundlePath: bundlePath,
            bundleIdentifier: bundleIdentifier
        )
        appInfo.lastLaunched = Date()
    }
}
