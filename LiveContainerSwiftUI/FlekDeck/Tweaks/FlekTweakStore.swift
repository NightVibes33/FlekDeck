import Foundation
import SwiftUI

struct FlekMachODescription: Hashable {
    let architectures: [String]
    let platform: String
    let fileType: String
    let isDylib: Bool
    let hasArm64: Bool
    let error: String?

    var architectureText: String { architectures.isEmpty ? "Unknown" : architectures.joined(separator: ", ") }
    var isLoadable: Bool { error == nil && isDylib && hasArm64 }

    var detail: String {
        if let error { return error }
        return "\(architectureText) · \(platform) · \(fileType)"
    }
}

/// Small read-only Mach-O inspector used by the Vibe-style tweak manager.
/// It intentionally does not mutate load commands. FlekDeck's TweakLoader is
/// the only injection backend.
enum FlekMachOInspector {
    private static let cpuArm64: UInt32 = 0x0100000c
    private static let cpuX8664: UInt32 = 0x01000007
    private static let mhDylib: UInt32 = 6
    private static let lcBuildVersion: UInt32 = 0x32
    private static let lcVersionMinIPhoneOS: UInt32 = 0x25
    private static let lcVersionMinMacOSX: UInt32 = 0x24

    static func inspect(_ file: URL) -> FlekMachODescription {
        guard let data = try? Data(contentsOf: file, options: .mappedIfSafe), data.count >= 4 else {
            return .init(architectures: [], platform: "Unknown", fileType: "Unknown", isDylib: false, hasArm64: false, error: "Unreadable binary")
        }

        let firstBE = u32(data, 0, endian: .big)
        let firstLE = u32(data, 0, endian: .little)

        if firstBE == 0xcafebabe || firstBE == 0xcafebabf {
            return inspectFat(data, is64: firstBE == 0xcafebabf)
        }
        if firstLE == 0xcafebabe || firstLE == 0xcafebabf {
            return inspectFat(data, is64: firstLE == 0xcafebabf, swapped: true)
        }
        if firstLE == 0xfeedfacf {
            return inspectThin(data, offset: 0)
        }
        return .init(architectures: [], platform: "Unknown", fileType: "Unknown", isDylib: false, hasArm64: false, error: "Not a 64-bit Mach-O dylib")
    }

    private static func inspectFat(_ data: Data, is64: Bool, swapped: Bool = false) -> FlekMachODescription {
        guard data.count >= 8 else {
            return .init(architectures: [], platform: "Unknown", fileType: "Universal", isDylib: false, hasArm64: false, error: "Invalid universal Mach-O")
        }
        let endian: Endian = swapped ? .little : .big
        let count = Int(u32(data, 4, endian: endian))
        let stride = is64 ? 32 : 20
        var cursor = 8
        var descriptions: [FlekMachODescription] = []
        var archNames: [String] = []

        for _ in 0..<min(count, 32) {
            guard cursor + stride <= data.count else { break }
            let cpu = u32(data, cursor, endian: endian)
            let offset: UInt64 = is64 ? u64(data, cursor + 8, endian: endian) : UInt64(u32(data, cursor + 8, endian: endian))
            archNames.append(archName(cpu))
            if offset < UInt64(data.count), Int(offset) + 32 <= data.count {
                let thin = inspectThin(data, offset: Int(offset))
                descriptions.append(thin)
            }
            cursor += stride
        }

        guard !descriptions.isEmpty else {
            return .init(architectures: archNames, platform: "Unknown", fileType: "Universal", isDylib: false, hasArm64: archNames.contains("arm64"), error: "No readable Mach-O slice")
        }

        let arm = descriptions.first(where: { $0.hasArm64 }) ?? descriptions[0]
        return .init(
            architectures: Array(Set(archNames)).sorted(),
            platform: arm.platform,
            fileType: arm.fileType,
            isDylib: descriptions.contains(where: { $0.isDylib }),
            hasArm64: descriptions.contains(where: { $0.hasArm64 }),
            error: descriptions.contains(where: { $0.isLoadable }) ? nil : arm.error
        )
    }

    private static func inspectThin(_ data: Data, offset: Int) -> FlekMachODescription {
        guard offset + 32 <= data.count, u32(data, offset, endian: .little) == 0xfeedfacf else {
            return .init(architectures: [], platform: "Unknown", fileType: "Unknown", isDylib: false, hasArm64: false, error: "Invalid Mach-O slice")
        }
        let cpu = u32(data, offset + 4, endian: .little)
        let fileType = u32(data, offset + 12, endian: .little)
        let ncmds = Int(u32(data, offset + 16, endian: .little))
        let commandsSize = Int(u32(data, offset + 20, endian: .little))
        var platform = "Unknown"
        var command = offset + 32
        let end = min(data.count, command + commandsSize)

        for _ in 0..<min(ncmds, 8192) {
            guard command + 8 <= end else { break }
            let cmd = u32(data, command, endian: .little)
            let size = Int(u32(data, command + 4, endian: .little))
            guard size >= 8, command + size <= end else { break }
            if cmd == lcBuildVersion, command + 12 <= end {
                platform = platformName(u32(data, command + 8, endian: .little))
            } else if cmd == lcVersionMinIPhoneOS {
                platform = "iOS"
            } else if cmd == lcVersionMinMacOSX {
                platform = "macOS"
            }
            command += size
        }

        let typeName: String
        switch fileType {
        case mhDylib: typeName = "Dylib"
        case 8: typeName = "Bundle"
        case 2: typeName = "Executable"
        default: typeName = "Mach-O \(fileType)"
        }
        let arm64 = cpu == cpuArm64
        let dylib = fileType == mhDylib
        let error: String? = !arm64 ? "Missing arm64 slice" : (!dylib ? "Mach-O is not MH_DYLIB" : nil)
        return .init(architectures: [archName(cpu)], platform: platform, fileType: typeName, isDylib: dylib, hasArm64: arm64, error: error)
    }

    private enum Endian { case little, big }

    private static func u32(_ data: Data, _ offset: Int, endian: Endian) -> UInt32 {
        guard offset >= 0, offset + 4 <= data.count else { return 0 }
        let b0 = UInt32(data[offset]), b1 = UInt32(data[offset + 1]), b2 = UInt32(data[offset + 2]), b3 = UInt32(data[offset + 3])
        switch endian {
        case .little: return b0 | b1 << 8 | b2 << 16 | b3 << 24
        case .big: return b0 << 24 | b1 << 16 | b2 << 8 | b3
        }
    }

    private static func u64(_ data: Data, _ offset: Int, endian: Endian) -> UInt64 {
        guard offset >= 0, offset + 8 <= data.count else { return 0 }
        var result: UInt64 = 0
        switch endian {
        case .little:
            for i in 0..<8 { result |= UInt64(data[offset + i]) << UInt64(i * 8) }
        case .big:
            for i in 0..<8 { result = (result << 8) | UInt64(data[offset + i]) }
        }
        return result
    }

    private static func archName(_ cpu: UInt32) -> String {
        switch cpu {
        case cpuArm64: return "arm64"
        case cpuX8664: return "x86_64"
        case 12: return "arm"
        case 7: return "x86"
        default: return String(format: "cpu 0x%08x", cpu)
        }
    }

    private static func platformName(_ value: UInt32) -> String {
        switch value {
        case 1: return "macOS"
        case 2: return "iOS"
        case 3: return "tvOS"
        case 4: return "watchOS"
        case 6: return "Mac Catalyst"
        case 7: return "iOS Simulator"
        case 8: return "tvOS Simulator"
        case 9: return "watchOS Simulator"
        case 11: return "visionOS"
        case 12: return "visionOS Simulator"
        default: return "Platform \(value)"
        }
    }
}

struct FlekManagedTweak: Identifiable, Hashable {
    let name: String
    let sourceURL: URL
    let binaryURL: URL
    let bytes: Int64
    let machO: FlekMachODescription
    let isFramework: Bool

    var id: String { name.lowercased() }
    var isLoadable: Bool { machO.isLoadable }
    var detail: String { "\(machO.detail) · \(ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file))" }
    var loadPath: String { sourceURL.path }
}

/// VibeContainers' tweak-library/scope model implemented entirely through the
/// FlekDeck TweakLoader folder contract. No LC_LOAD_DYLIB mutation occurs here.
///
/// Layout under Documents/Tweaks:
///   root tweak                  -> global tweak (existing Flek behavior)
///   __FlekLibrary/<tweak>       -> imported library master, not global
///   __FlekPerApp/<bundle>/<...> -> per-app overlay loaded by TweakLoader
///   __FlekBlocked/<bundle>/<n>  -> global opt-out marker for that app
///   any normal named folder     -> existing LCTweakFolder profile, unchanged
@MainActor
final class FlekTweakStore: ObservableObject {
    static let shared = FlekTweakStore()

    @Published private(set) var library: [FlekManagedTweak] = []
    @Published var lastError: String?
    @Published var lastNotice: String?
    @Published var isSigning = false

    private let fm = FileManager.default
    let libraryFolderName = "__FlekLibrary"
    let perAppFolderName = "__FlekPerApp"
    let blockedFolderName = "__FlekBlocked"

    var root: URL { LCPath.tweakPath }
    var libraryRoot: URL { root.appendingPathComponent(libraryFolderName, isDirectory: true) }
    var perAppRoot: URL { root.appendingPathComponent(perAppFolderName, isDirectory: true) }
    var blockedRoot: URL { root.appendingPathComponent(blockedFolderName, isDirectory: true) }

    private init() { refresh() }

    func refresh() {
        do {
            try ensureDirectories()
            var byName: [String: FlekManagedTweak] = [:]

            for url in tweakItems(in: libraryRoot) {
                if let tweak = describe(url) { byName[tweak.id] = tweak }
            }
            for url in tweakItems(in: root) where !isReserved(url) && url.lastPathComponent != "TweakLoader.dylib" {
                guard let tweak = describe(url) else { continue }
                // A library master wins over its root-level global symlink.
                if byName[tweak.id] == nil { byName[tweak.id] = tweak }
            }

            library = byName.values.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        } catch {
            lastError = error.localizedDescription
        }
    }

    func isGlobal(_ tweak: FlekManagedTweak) -> Bool {
        fm.fileExists(atPath: root.appendingPathComponent(tweak.name).path)
    }

    func appsUsing(_ tweak: FlekManagedTweak, apps: [LCAppModel]) -> [LCAppModel] {
        apps.filter { isEffective(tweak, for: $0) }
    }

    func isEffective(_ tweak: FlekManagedTweak, for app: LCAppModel) -> Bool {
        if isBlocked(tweak, for: app) { return false }
        if isGlobal(tweak) { return true }
        if fm.fileExists(atPath: perAppURL(tweak, app: app).path) { return true }
        return profileTweaks(for: app).contains { $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame }
    }

    func isExplicitPerApp(_ tweak: FlekManagedTweak, for app: LCAppModel) -> Bool {
        fm.fileExists(atPath: perAppURL(tweak, app: app).path)
    }

    func isBlocked(_ tweak: FlekManagedTweak, for app: LCAppModel) -> Bool {
        fm.fileExists(atPath: blockURL(tweak, app: app).path)
    }

    func setGlobal(_ enabled: Bool, tweak: FlekManagedTweak) {
        do {
            try ensureDirectories()
            let global = root.appendingPathComponent(tweak.name)
            if enabled {
                if !fm.fileExists(atPath: global.path) {
                    try createRelativeLink(at: global, to: canonicalSource(for: tweak))
                }
            } else if fm.fileExists(atPath: global.path) {
                if isSymlink(global) {
                    try fm.removeItem(at: global)
                } else {
                    let destination = libraryRoot.appendingPathComponent(tweak.name)
                    if fm.fileExists(atPath: destination.path) { try fm.removeItem(at: destination) }
                    try fm.moveItem(at: global, to: destination)
                    try retargetPerAppLinks(named: tweak.name, to: destination)
                }
            }
            refresh()
            lastNotice = enabled ? "\(tweak.name) is now global." : "\(tweak.name) is no longer global."
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Mirrors Vibe's per-app toggle, but makes the result authoritative
    /// across global scope, the per-app overlay, and the existing profile.
    func setEnabled(_ enabled: Bool, tweak: FlekManagedTweak, for app: LCAppModel) {
        do {
            try ensureDirectories()
            let marker = blockURL(tweak, app: app)
            let overlay = perAppURL(tweak, app: app)
            try fm.createDirectory(at: marker.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fm.createDirectory(at: overlay.deletingLastPathComponent(), withIntermediateDirectories: true)

            if enabled {
                if fm.fileExists(atPath: marker.path) { try fm.removeItem(at: marker) }
                let providedByProfile = profileTweaks(for: app).contains {
                    $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame
                }
                if !isGlobal(tweak) && !providedByProfile && !fm.fileExists(atPath: overlay.path) {
                    try createRelativeLink(at: overlay, to: canonicalSource(for: tweak))
                }
            } else {
                if !fm.fileExists(atPath: marker.path) {
                    fm.createFile(atPath: marker.path, contents: Data(), attributes: nil)
                }
                if fm.fileExists(atPath: overlay.path) || isSymlink(overlay) {
                    try? fm.removeItem(at: overlay)
                }
            }
            lastNotice = enabled ? "Enabled \(tweak.name) for \(app.displayName)." : "Disabled \(tweak.name) for \(app.displayName)."
            objectWillChange.send()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func importItems(_ urls: [URL]) {
        do {
            try ensureDirectories()
            var imported = 0
            for source in urls {
                let ext = source.pathExtension.lowercased()
                guard ext == "dylib" || ext == "framework" else { continue }
                let scoped = source.startAccessingSecurityScopedResource()
                defer { if scoped { source.stopAccessingSecurityScopedResource() } }
                let destination = libraryRoot.appendingPathComponent(source.lastPathComponent)
                if fm.fileExists(atPath: destination.path) { try fm.removeItem(at: destination) }
                try fm.copyItem(at: source, to: destination)
                imported += 1
            }
            refresh()
            lastNotice = "Imported \(imported) tweak\(imported == 1 ? "" : "s") into the library."
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Vibe's "Scan Documents Folder": adopts loose dylibs/frameworks from the
    /// top level of Documents without touching IPAs or unrelated user files.
    func scanDocuments() {
        do {
            try ensureDirectories()
            let urls = try fm.contentsOfDirectory(at: LCPath.docPath, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles])
            var adopted = 0
            for source in urls {
                let ext = source.pathExtension.lowercased()
                guard ext == "dylib" || ext == "framework" else { continue }
                let destination = libraryRoot.appendingPathComponent(source.lastPathComponent)
                if fm.fileExists(atPath: destination.path) { continue }
                try fm.moveItem(at: source, to: destination)
                adopted += 1
            }
            refresh()
            lastNotice = adopted == 0 ? "No loose tweaks found in Documents." : "Adopted \(adopted) tweak\(adopted == 1 ? "" : "s")."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func delete(_ tweak: FlekManagedTweak) {
        do {
            let global = root.appendingPathComponent(tweak.name)
            if fm.fileExists(atPath: global.path) { try fm.removeItem(at: global) }
            let library = libraryRoot.appendingPathComponent(tweak.name)
            if fm.fileExists(atPath: library.path) { try fm.removeItem(at: library) }
            try removeNamedItem(tweak.name, below: perAppRoot)
            try removeNamedItem(tweak.name, below: blockedRoot)
            if tweak.sourceURL.path != global.path && tweak.sourceURL.path != library.path && fm.fileExists(atPath: tweak.sourceURL.path) {
                try fm.removeItem(at: tweak.sourceURL)
            }
            refresh()
            lastNotice = "Deleted \(tweak.name) and removed its scope links."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func repair() {
        do {
            try ensureDirectories()
            for appDirectory in childDirectories(perAppRoot) {
                for link in tweakItems(in: appDirectory) {
                    guard isSymlink(link) else { continue }
                    let name = link.lastPathComponent
                    guard let tweak = library.first(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame }) else {
                        try fm.removeItem(at: link)
                        continue
                    }
                    let target = canonicalSource(for: tweak)
                    if link.resolvingSymlinksInPath().standardizedFileURL != target.resolvingSymlinksInPath().standardizedFileURL {
                        try fm.removeItem(at: link)
                        try createRelativeLink(at: link, to: target)
                    }
                }
            }
            refresh()
            lastNotice = "Re-synced per-app tweak overlays."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func signAll() async {
        guard LCSharedUtils.certificatePassword() != nil else {
            lastError = "Import a signing certificate before signing tweaks."
            return
        }
        isSigning = true
        defer { isSigning = false }
        do {
            try await LCUtils.signTweaks(tweakFolderUrl: libraryRoot, force: true) { _ in }
            // Root-level originals and normal user folders keep using the existing signer.
            try await LCUtils.signTweaks(tweakFolderUrl: root, force: true) { _ in }
            refresh()
            lastNotice = "Signed the tweak library and FlekDeck tweak folders."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func profileTweaks(for app: LCAppModel) -> [FlekManagedTweak] {
        guard let folder = app.uiTweakFolder, !folder.isEmpty else { return [] }
        let folderURL = root.appendingPathComponent(folder, isDirectory: true)
        return recursiveTweakItems(in: folderURL).compactMap(describe)
    }

    func overlayTweaks(for app: LCAppModel) -> [FlekManagedTweak] {
        let folder = perAppRoot.appendingPathComponent(appKey(app), isDirectory: true)
        return tweakItems(in: folder).compactMap(describe)
    }

    func effectiveTweaks(for app: LCAppModel) -> [FlekManagedTweak] {
        var map: [String: FlekManagedTweak] = [:]
        for tweak in library where isGlobal(tweak) && !isBlocked(tweak, for: app) { map[tweak.id] = tweak }
        for tweak in overlayTweaks(for: app) where !isBlocked(tweak, for: app) { map[tweak.id] = tweak }
        for tweak in profileTweaks(for: app) where !isBlocked(tweak, for: app) { map[tweak.id] = tweak }
        return map.values.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    func scopeBadge(_ tweak: FlekManagedTweak) -> String? {
        let count = childDirectories(perAppRoot).filter { fm.fileExists(atPath: $0.appendingPathComponent(tweak.name).path) }.count
        return count == 0 ? nil : "\(count) APP\(count == 1 ? "" : "S")"
    }

    func scopeText(_ tweak: FlekManagedTweak, apps: [LCAppModel]) -> String {
        if isGlobal(tweak) {
            let blocked = apps.filter { isBlocked(tweak, for: $0) }.count
            return blocked == 0 ? "Global · every app" : "Global · blocked in \(blocked) app\(blocked == 1 ? "" : "s")"
        }
        let explicit = apps.filter { isExplicitPerApp(tweak, for: $0) }.count
        return explicit == 0 ? "Not loaded by the Vibe per-app layer" : "Loaded in \(explicit) app\(explicit == 1 ? "" : "s")"
    }

    func xmbInfo(_ tweak: FlekManagedTweak) -> FlekXMBInfo {
        FlekXMBInfo(
            title: tweak.name,
            subtitle: tweak.detail,
            icon: .symbol(tweak.isFramework ? "shippingbox.fill" : "puzzlepiece.extension.fill", tweak.isLoadable ? .purple : .orange),
            lines: [
                .init(label: "Architecture", value: tweak.machO.architectureText),
                .init(label: "Platform", value: tweak.machO.platform),
                .init(label: "Mach-O", value: tweak.machO.fileType),
                .init(label: "Scope", value: isGlobal(tweak) ? "Global" : (scopeBadge(tweak) ?? "Library"))
            ],
            body: tweak.isLoadable ? "Loaded by FlekDeck TweakLoader. No guest executable load commands are rewritten." : (tweak.machO.error ?? "Not loadable"),
            footnote: tweak.loadPath,
            accent: tweak.isLoadable ? .purple : .orange
        )
    }

    func appInfo(_ app: LCAppModel) -> FlekXMBInfo {
        let effective = effectiveTweaks(for: app)
        let invalid = effective.filter { !$0.isLoadable }.count
        return FlekXMBInfo(
            title: app.displayName,
            subtitle: app.bundleIdentifier,
            icon: .app(app),
            lines: [
                .init(label: "Effective", value: "\(effective.count) tweaks"),
                .init(label: "Named Profile", value: app.uiTweakFolder ?? "None"),
                .init(label: "Invalid", value: "\(invalid)")
            ],
            body: "Global tweaks, the per-app Vibe overlay, and the existing LCTweakFolder profile all resolve through the same TweakLoader constructor.",
            accent: invalid == 0 ? .green : .orange
        )
    }

    // MARK: internals

    private func ensureDirectories() throws {
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        try fm.createDirectory(at: libraryRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: perAppRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: blockedRoot, withIntermediateDirectories: true)
    }

    private func canonicalSource(for tweak: FlekManagedTweak) -> URL {
        let library = libraryRoot.appendingPathComponent(tweak.name)
        if fm.fileExists(atPath: library.path) { return library }
        return tweak.sourceURL.resolvingSymlinksInPath()
    }

    private func perAppURL(_ tweak: FlekManagedTweak, app: LCAppModel) -> URL {
        perAppRoot.appendingPathComponent(appKey(app), isDirectory: true).appendingPathComponent(tweak.name)
    }

    private func blockURL(_ tweak: FlekManagedTweak, app: LCAppModel) -> URL {
        blockedRoot.appendingPathComponent(appKey(app), isDirectory: true).appendingPathComponent(tweak.name)
    }

    func appKey(_ app: LCAppModel) -> String { sanitize(app.bundleIdentifier) }

    private func sanitize(_ string: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: ".-_"))
        return String(string.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : "_" })
    }

    private func isReserved(_ url: URL) -> Bool {
        [libraryFolderName, perAppFolderName, blockedFolderName].contains(url.lastPathComponent)
    }

    private func tweakItems(in directory: URL) -> [URL] {
        guard let urls = try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey], options: [.skipsHiddenFiles]) else { return [] }
        return urls.filter { url in
            let lower = url.lastPathComponent.lowercased()
            return lower.hasSuffix(".dylib") || lower.hasSuffix(".framework")
        }
    }

    private func recursiveTweakItems(in directory: URL) -> [URL] {
        guard let enumerator = fm.enumerator(at: directory, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return [] }
        var result: [URL] = []
        while let url = enumerator.nextObject() as? URL {
            let lower = url.lastPathComponent.lowercased()
            if lower.hasSuffix(".framework") {
                result.append(url)
                enumerator.skipDescendants()
            } else if lower.hasSuffix(".dylib") {
                result.append(url)
            }
        }
        return result
    }

    private func describe(_ url: URL) -> FlekManagedTweak? {
        let resolved = url.resolvingSymlinksInPath()
        let lower = resolved.lastPathComponent.lowercased()
        let framework = lower.hasSuffix(".framework")
        let dylib = lower.hasSuffix(".dylib")
        guard framework || dylib else { return nil }
        guard let binary = binaryURL(for: resolved, framework: framework) else {
            let invalid = FlekMachODescription(architectures: [], platform: "Unknown", fileType: "Framework", isDylib: false, hasArm64: false, error: "Framework executable missing")
            return FlekManagedTweak(name: url.lastPathComponent, sourceURL: resolved, binaryURL: resolved, bytes: recursiveSize(resolved), machO: invalid, isFramework: true)
        }
        return FlekManagedTweak(name: url.lastPathComponent, sourceURL: resolved, binaryURL: binary, bytes: recursiveSize(resolved), machO: FlekMachOInspector.inspect(binary), isFramework: framework)
    }

    private func binaryURL(for url: URL, framework: Bool) -> URL? {
        guard framework else { return url }
        let plist = url.appendingPathComponent("Info.plist")
        if let info = NSDictionary(contentsOf: plist), let executable = info["CFBundleExecutable"] as? String {
            let candidate = url.appendingPathComponent(executable)
            if fm.fileExists(atPath: candidate.path) { return candidate }
        }
        let fallback = url.appendingPathComponent(url.deletingPathExtension().lastPathComponent)
        return fm.fileExists(atPath: fallback.path) ? fallback : nil
    }

    private func recursiveSize(_ url: URL) -> Int64 {
        if let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey]), values.isDirectory != true {
            return Int64(values.fileSize ?? 0)
        }
        guard let enumerator = fm.enumerator(at: url, includingPropertiesForKeys: [.fileSizeKey], options: [.skipsHiddenFiles]) else { return 0 }
        var total: Int64 = 0
        while let file = enumerator.nextObject() as? URL {
            total += Int64((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
        }
        return total
    }

    private func childDirectories(_ url: URL) -> [URL] {
        let urls = (try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles])) ?? []
        return urls.filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
    }

    private func isSymlink(_ url: URL) -> Bool {
        (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
    }

    private func retargetPerAppLinks(named name: String, to destination: URL) throws {
        for appDirectory in childDirectories(perAppRoot) {
            let link = appDirectory.appendingPathComponent(name)
            guard fm.fileExists(atPath: link.path) || isSymlink(link) else { continue }
            try? fm.removeItem(at: link)
            try createRelativeLink(at: link, to: destination)
        }
    }

    private func createRelativeLink(at link: URL, to target: URL) throws {
        let from = link.deletingLastPathComponent().standardizedFileURL.pathComponents
        let to = target.standardizedFileURL.pathComponents
        var common = 0
        while common < from.count && common < to.count && from[common] == to[common] { common += 1 }
        let components = Array(repeating: "..", count: from.count - common) + Array(to.dropFirst(common))
        let relative = components.isEmpty ? "." : components.joined(separator: "/")
        try fm.createSymbolicLink(atPath: link.path, withDestinationPath: relative)
    }

    private func removeNamedItem(_ name: String, below root: URL) throws {
        for directory in childDirectories(root) {
            let candidate = directory.appendingPathComponent(name)
            if fm.fileExists(atPath: candidate.path) || isSymlink(candidate) { try? fm.removeItem(at: candidate) }
        }
    }
}
