import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct FlekTweakEntry: Identifiable, Hashable {
    enum Kind: String {
        case dylib = "Dylib"
        case framework = "Framework"
        case folder = "Folder"
        case file = "File"
    }

    static let disabledSuffix = ".disabled"

    let url: URL
    let name: String
    let kind: Kind
    let enabled: Bool
    let bytes: Int64

    var id: String { url.path }
    var displayName: String {
        enabled ? name : String(name.dropLast(Self.disabledSuffix.count))
    }
    var isTweak: Bool { kind == .dylib || kind == .framework }
}

struct FlekTweakFolder: Identifiable, Hashable {
    let name: String
    let url: URL
    let entries: [FlekTweakEntry]

    var id: String { name }
    var enabledTweaks: Int { entries.filter { $0.isTweak && $0.enabled }.count }
    var totalTweaks: Int { entries.filter(\.isTweak).count }
    var bytes: Int64 { entries.reduce(0) { $0 + $1.bytes } }
}

/// VibeContainers-style tweak library/management model backed by FlekDeck's
/// existing Documents/Tweaks + LCTweakFolder + TweakLoader contract.
@MainActor
final class FlekTweakLibrary: ObservableObject {
    static let shared = FlekTweakLibrary()

    @Published private(set) var folders: [FlekTweakFolder] = []
    @Published private(set) var looseEntries: [FlekTweakEntry] = []
    @Published var isSigning = false
    @Published var lastError: String?
    @Published var lastNotice: String?

    private let fm = FileManager.default
    var root: URL { LCPath.tweakPath }

    private init() {
        refresh()
    }

    func refresh(sharedModel: SharedModel? = nil) {
        do {
            try fm.createDirectory(at: root, withIntermediateDirectories: true)
            let urls = try fm.contentsOfDirectory(
                at: root,
                includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
                options: [.skipsHiddenFiles]
            )

            var newFolders: [FlekTweakFolder] = []
            var newLoose: [FlekTweakEntry] = []

            for url in urls {
                let isDirectory = (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
                if isDirectory && url.pathExtension.lowercased() != "framework" {
                    newFolders.append(FlekTweakFolder(
                        name: url.lastPathComponent,
                        url: url,
                        entries: entries(in: url)
                    ))
                } else if let entry = describe(url) {
                    newLoose.append(entry)
                }
            }

            folders = newFolders.sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
            looseEntries = newLoose.sorted {
                $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
            }

            if let sharedModel { syncFolderNames(sharedModel) }
        } catch {
            lastError = error.localizedDescription
        }
    }

    func folder(named name: String?) -> FlekTweakFolder? {
        guard let name else { return nil }
        return folders.first { $0.name == name }
    }

    private func entries(in folder: URL) -> [FlekTweakEntry] {
        let urls = (try? fm.contentsOfDirectory(
            at: folder,
            includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        return urls.compactMap(describe).sorted {
            $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
    }

    private func describe(_ url: URL) -> FlekTweakEntry? {
        let rawName = url.lastPathComponent
        let enabled = !rawName.hasSuffix(FlekTweakEntry.disabledSuffix)
        let baseName = enabled
            ? rawName
            : String(rawName.dropLast(FlekTweakEntry.disabledSuffix.count))
        let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
        let isDirectory = values?.isDirectory == true

        let kind: FlekTweakEntry.Kind
        if isDirectory && baseName.lowercased().hasSuffix(".framework") {
            kind = .framework
        } else if !isDirectory && baseName.lowercased().hasSuffix(".dylib") {
            kind = .dylib
        } else if isDirectory {
            kind = .folder
        } else {
            kind = .file
        }

        let size = values?.fileSize.map(Int64.init) ?? recursiveSize(url)
        return FlekTweakEntry(
            url: url,
            name: rawName,
            kind: kind,
            enabled: enabled,
            bytes: size
        )
    }

    private func recursiveSize(_ url: URL) -> Int64 {
        guard let enumerator = fm.enumerator(
            at: url,
            includingPropertiesForKeys: [.fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { return 0 }

        var total: Int64 = 0
        while let file = enumerator.nextObject() as? URL {
            total += Int64((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
        }
        return total
    }

    func allApps(_ sharedModel: SharedModel) -> [LCAppModel] {
        var seen = Set<ObjectIdentifier>()
        return (sharedModel.apps + sharedModel.hiddenApps).filter {
            seen.insert(ObjectIdentifier($0)).inserted
        }
    }

    func appsUsing(_ folder: FlekTweakFolder, sharedModel: SharedModel) -> [LCAppModel] {
        allApps(sharedModel).filter { $0.uiTweakFolder == folder.name }
    }

    func setEnabled(_ enabled: Bool, entry: FlekTweakEntry, sharedModel: SharedModel) {
        guard entry.enabled != enabled, entry.displayName != "TweakLoader.dylib" else { return }
        let parent = entry.url.deletingLastPathComponent()
        let newName = enabled
            ? entry.displayName
            : entry.displayName + FlekTweakEntry.disabledSuffix

        do {
            try fm.moveItem(at: entry.url, to: parent.appendingPathComponent(newName))
            refresh(sharedModel: sharedModel)
        } catch {
            lastError = error.localizedDescription
        }
    }

    func createFolder(_ rawName: String, sharedModel: SharedModel) {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name != ".", name != "..", !name.contains("/") else {
            lastError = "Choose a valid folder name."
            return
        }

        let destination = root.appendingPathComponent(name, isDirectory: true)
        guard !fm.fileExists(atPath: destination.path) else {
            lastError = "A tweak folder named \(name) already exists."
            return
        }

        do {
            try fm.createDirectory(at: destination, withIntermediateDirectories: false)
            refresh(sharedModel: sharedModel)
            lastNotice = "Created \(name)."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func renameFolder(_ folder: FlekTweakFolder, to rawName: String, sharedModel: SharedModel) {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name != folder.name, !name.contains("/") else { return }

        let destination = root.appendingPathComponent(name, isDirectory: true)
        guard !fm.fileExists(atPath: destination.path) else {
            lastError = "A tweak folder named \(name) already exists."
            return
        }

        do {
            try fm.moveItem(at: folder.url, to: destination)
            for app in allApps(sharedModel) where app.uiTweakFolder == folder.name {
                app.uiTweakFolder = name
            }
            refresh(sharedModel: sharedModel)
            lastNotice = "Renamed \(folder.name) to \(name)."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func deleteFolder(_ folder: FlekTweakFolder, sharedModel: SharedModel) {
        do {
            for app in allApps(sharedModel) where app.uiTweakFolder == folder.name {
                app.uiTweakFolder = nil
            }
            try fm.removeItem(at: folder.url)
            refresh(sharedModel: sharedModel)
            lastNotice = "Deleted \(folder.name). Apps that used it now have tweaks disabled."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func delete(_ entry: FlekTweakEntry, sharedModel: SharedModel) {
        guard entry.displayName != "TweakLoader.dylib" else { return }
        do {
            try fm.removeItem(at: entry.url)
            refresh(sharedModel: sharedModel)
            lastNotice = "Deleted \(entry.displayName)."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func importItems(_ urls: [URL], into folderName: String, sharedModel: SharedModel) {
        guard let folder = folder(named: folderName) else {
            lastError = "Create or select a tweak folder first."
            return
        }

        var imported: [String] = []
        do {
            for source in urls {
                let ext = source.pathExtension.lowercased()
                guard ext == "dylib" || ext == "framework" else { continue }

                let scoped = source.startAccessingSecurityScopedResource()
                defer { if scoped { source.stopAccessingSecurityScopedResource() } }

                let destination = folder.url.appendingPathComponent(source.lastPathComponent)
                if fm.fileExists(atPath: destination.path) {
                    try fm.removeItem(at: destination)
                }

                do {
                    try fm.copyItem(at: source, to: destination)
                } catch {
                    try fm.moveItem(at: source, to: destination)
                }

                if ext == "dylib" {
                    LCParseMachO((destination.path as NSString).utf8String, false) { path, header, _, _ in
                        LCPatchAddRPath(path, header)
                    }
                }
                imported.append(source.lastPathComponent)
            }

            refresh(sharedModel: sharedModel)
            if !imported.isEmpty {
                lastNotice = "Imported \(imported.joined(separator: ", "))."
            }
        } catch {
            lastError = error.localizedDescription
        }
    }

    func adoptLooseEntries(into folderName: String, sharedModel: SharedModel) {
        guard let folder = folder(named: folderName) else {
            lastError = "Select a destination folder."
            return
        }

        var moved: [String] = []
        do {
            for entry in looseEntries where entry.isTweak {
                let destination = folder.url.appendingPathComponent(entry.url.lastPathComponent)
                if fm.fileExists(atPath: destination.path) {
                    try fm.removeItem(at: destination)
                }
                try fm.moveItem(at: entry.url, to: destination)
                moved.append(entry.displayName)
            }

            refresh(sharedModel: sharedModel)
            lastNotice = moved.isEmpty
                ? "No loose tweaks were found."
                : "Moved \(moved.joined(separator: ", ")) into \(folderName)."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func sign(folder: FlekTweakFolder, sharedModel: SharedModel) async {
        guard LCSharedUtils.certificatePassword() != nil else {
            lastError = "Import a signing certificate before signing tweaks."
            return
        }

        isSigning = true
        defer { isSigning = false }
        do {
            try await LCUtils.signTweaks(tweakFolderUrl: folder.url, force: true) { _ in }
            refresh(sharedModel: sharedModel)
            lastNotice = "Signed \(folder.name)."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func signAll(sharedModel: SharedModel) async {
        guard LCSharedUtils.certificatePassword() != nil else {
            lastError = "Import a signing certificate before signing tweaks."
            return
        }

        isSigning = true
        defer { isSigning = false }
        do {
            for folder in folders {
                try await LCUtils.signTweaks(tweakFolderUrl: folder.url, force: true) { _ in }
            }
            refresh(sharedModel: sharedModel)
            lastNotice = "Signed all tweak folders."
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func syncFolderNames(_ sharedModel: SharedModel) {
        let names = folders.map(\.name)
        if sharedModel.tweakFolderNames != names {
            sharedModel.tweakFolderNames = names
        }
    }
}

struct LCTweaksView: View {
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var library = FlekTweakLibrary.shared

    @State private var tab = 0
    @State private var importing = false
    @State private var destination = ""
    @State private var newFolderName = ""
    @State private var creatingFolder = false

    private var apps: [LCAppModel] {
        library.allApps(sharedModel)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                hero

                Picker("Tweaks", selection: $tab) {
                    Text("Library").tag(0)
                    Text("Manage").tag(1)
                    Text("Apps").tag(2)
                }
                .pickerStyle(.segmented)

                if tab == 0 {
                    libraryTab
                } else if tab == 1 {
                    manageTab
                } else {
                    appsTab
                }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text("Tweaks").font(.headline)
            }
        }
        .onAppear {
            library.refresh(sharedModel: sharedModel)
            if destination.isEmpty {
                destination = library.folders.first?.name ?? ""
            }
        }
        .fileImporter(
            isPresented: $importing,
            allowedContentTypes: [.dylib, .lcFramework],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                library.importItems(urls, into: destination, sharedModel: sharedModel)
            case .failure(let error):
                library.lastError = error.localizedDescription
            }
        }
        .alert("New Tweak Folder", isPresented: $creatingFolder) {
            TextField("Folder name", text: $newFolderName)
            Button("Cancel", role: .cancel) {
                newFolderName = ""
            }
            Button("Create") {
                let requested = newFolderName.trimmingCharacters(in: .whitespacesAndNewlines)
                library.createFolder(requested, sharedModel: sharedModel)
                if library.folder(named: requested) != nil {
                    destination = requested
                }
                newFolderName = ""
            }
        }
        .alert(
            "Tweaks",
            isPresented: Binding(
                get: { library.lastError != nil },
                set: { if !$0 { library.lastError = nil } }
            )
        ) {
            Button("OK", role: .cancel) {
                library.lastError = nil
            }
        } message: {
            Text(library.lastError ?? "")
        }
        .overlay(alignment: .top) {
            if let notice = library.lastNotice {
                HStack(spacing: 9) {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    Text(notice).font(.subheadline).lineLimit(2)
                    Spacer()
                    Button {
                        library.lastNotice = nil
                    } label: {
                        Image(systemName: "xmark")
                    }
                }
                .padding(14)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
                .padding(.horizontal, 16)
                .padding(.top, 4)
            }
        }
    }

    private var hero: some View {
        HStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color.orange.opacity(0.14))
                Image(systemName: "wrench.and.screwdriver.fill")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(.orange)
            }
            .frame(width: 66, height: 66)

            VStack(alignment: .leading, spacing: 4) {
                Text("Tweak Library").font(.title2.bold())
                Text("VibeContainers' Library / Manage / Apps workflow, adapted to FlekDeck's named tweak folders and TweakLoader runtime.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 25, tint: 0.10)
    }

    @ViewBuilder
    private var libraryTab: some View {
        if library.folders.isEmpty {
            emptyCard(
                title: "No tweak folders",
                detail: "Create a folder in Manage, then import .dylib or .framework tweaks into it.",
                symbol: "folder.badge.plus"
            )
        } else {
            VStack(spacing: 12) {
                ForEach(library.folders) { folder in
                    NavigationLink {
                        FlekTweakFolderDetailView(folderName: folder.name)
                    } label: {
                        HStack(spacing: 14) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(Color.orange.opacity(0.12))
                                Image(systemName: "folder.fill.badge.gearshape")
                                    .foregroundStyle(.orange)
                            }
                            .frame(width: 50, height: 50)

                            VStack(alignment: .leading, spacing: 3) {
                                Text(folder.name)
                                    .font(.headline)
                                    .foregroundStyle(.primary)
                                Text("\(folder.enabledTweaks) enabled · \(folder.totalTweaks) tweaks · \(ByteCountFormatter.string(fromByteCount: folder.bytes, countStyle: .file))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                let count = library.appsUsing(folder, sharedModel: sharedModel).count
                                Text(count == 0
                                     ? "Not assigned to an app"
                                     : "Used by \(count) app\(count == 1 ? "" : "s")")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.forward")
                                .font(.caption.bold())
                                .foregroundStyle(.tertiary)
                        }
                        .padding(16)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .flekGlassCard(cornerRadius: 22, tint: 0.08)
                }
            }
        }
    }

    private var manageTab: some View {
        VStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 12) {
                featureHeader(
                    title: "Add Tweaks",
                    detail: "Import dylibs/frameworks into a real FlekDeck tweak folder.",
                    symbol: "square.and.arrow.down.fill",
                    tint: .blue
                )
                if !library.folders.isEmpty {
                    Picker("Destination", selection: $destination) {
                        ForEach(library.folders) { folder in
                            Text(folder.name).tag(folder.name)
                        }
                    }
                    .pickerStyle(.menu)
                }
                Button("Import Tweaks…") {
                    if library.folders.isEmpty {
                        creatingFolder = true
                    } else {
                        importing = true
                    }
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(16)
            .flekGlassCard(cornerRadius: 22, tint: 0.08)

            actionCard(
                title: "New Folder",
                detail: "Creates a folder selectable by each app's LCTweakFolder setting.",
                symbol: "folder.badge.plus",
                tint: .orange
            ) {
                creatingFolder = true
            }

            actionCard(
                title: "Scan Loose Tweaks",
                detail: "Moves root-level dylibs/frameworks into the selected destination folder.",
                symbol: "folder.badge.gearshape",
                tint: .purple
            ) {
                library.adoptLooseEntries(into: destination, sharedModel: sharedModel)
            }

            actionCard(
                title: library.isSigning ? "Signing…" : "Sign All Tweaks",
                detail: "Uses FlekDeck's existing tweak signing path.",
                symbol: "signature",
                tint: .green
            ) {
                Task { await library.signAll(sharedModel: sharedModel) }
            }
            .disabled(library.isSigning)

            actionCard(
                title: "Refresh Library",
                detail: "Re-read Documents/Tweaks and synchronize folder choices.",
                symbol: "arrow.clockwise",
                tint: .blue
            ) {
                library.refresh(sharedModel: sharedModel)
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Storage").font(.headline)
                info("Root", value: "Documents/Tweaks")
                info("Folders", value: "\(library.folders.count)")
                info("Loose items", value: "\(library.looseEntries.count)")
                info("Apps", value: "\(apps.count)")
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .flekGlassCard(cornerRadius: 22, tint: 0.08)
        }
    }

    @ViewBuilder
    private var appsTab: some View {
        if apps.isEmpty {
            emptyCard(
                title: "No installed apps",
                detail: "Install an app and it will appear here for tweak-folder assignment.",
                symbol: "square.stack.3d.up.slash"
            )
        } else {
            VStack(spacing: 12) {
                ForEach(apps.indices, id: \.self) { index in
                    NavigationLink {
                        FlekAppTweakAssignmentView(app: apps[index])
                    } label: {
                        HStack(spacing: 14) {
                            Image(uiImage: apps[index].appInfo.iconIsDarkIcon(false))
                                .resizable()
                                .scaledToFill()
                                .frame(width: 50, height: 50)
                                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                            VStack(alignment: .leading, spacing: 3) {
                                Text(apps[index].displayName)
                                    .font(.headline)
                                    .foregroundStyle(.primary)
                                    .lineLimit(1)
                                Text(apps[index].bundleIdentifier)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                Text(apps[index].uiTweakFolder.map { "Tweaks: \($0)" } ?? "Tweaks disabled")
                                    .font(.caption2)
                                    .foregroundStyle(apps[index].uiTweakFolder == nil ? Color(UIColor.secondaryLabel) : Color.orange)
                            }
                            Spacer()
                            Image(systemName: "chevron.forward")
                                .font(.caption.bold())
                                .foregroundStyle(.tertiary)
                        }
                        .padding(16)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .flekGlassCard(cornerRadius: 22, tint: 0.08)
                }
            }
        }
    }

    private func emptyCard(title: String, detail: String, symbol: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text(title).font(.headline)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(30)
        .frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 24, tint: 0.08)
    }

    private func featureHeader(title: String, detail: String, symbol: String, tint: Color) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(tint.opacity(0.13))
                Image(systemName: symbol)
                    .foregroundStyle(tint)
                    .font(.system(size: 21, weight: .semibold))
            }
            .frame(width: 46, height: 46)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private func actionCard(
        title: String,
        detail: String,
        symbol: String,
        tint: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            featureHeader(title: title, detail: detail, symbol: symbol, tint: tint)
                .padding(16)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private func info(_ title: String, value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer()
            Text(value)
        }
        .font(.subheadline)
    }
}

struct FlekTweakFolderDetailView: View {
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var library = FlekTweakLibrary.shared

    let folderName: String
    @State private var importing = false
    @State private var renameText = ""
    @State private var renaming = false
    @State private var confirmDeleteFolder = false

    private var folder: FlekTweakFolder? {
        library.folder(named: folderName)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                if let folder {
                    header(folder)

                    if folder.entries.isEmpty {
                        VStack(spacing: 10) {
                            Image(systemName: "tray")
                                .font(.system(size: 32))
                                .foregroundStyle(.secondary)
                            Text("This folder is empty").font(.headline)
                        }
                        .padding(30)
                        .frame(maxWidth: .infinity)
                        .flekGlassCard(cornerRadius: 22, tint: 0.08)
                    } else {
                        ForEach(folder.entries) { entry in
                            entryCard(entry)
                        }
                    }

                    management(folder)
                }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle(folderName)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            library.refresh(sharedModel: sharedModel)
        }
        .fileImporter(
            isPresented: $importing,
            allowedContentTypes: [.dylib, .lcFramework],
            allowsMultipleSelection: true
        ) { result in
            if case .success(let urls) = result {
                library.importItems(urls, into: folderName, sharedModel: sharedModel)
            }
        }
        .alert("Rename Folder", isPresented: $renaming) {
            TextField("Folder name", text: $renameText)
            Button("Cancel", role: .cancel) {}
            Button("Rename") {
                if let folder {
                    library.renameFolder(folder, to: renameText, sharedModel: sharedModel)
                }
            }
        }
        .alert("Delete \(folderName)?", isPresented: $confirmDeleteFolder) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                if let folder {
                    library.deleteFolder(folder, sharedModel: sharedModel)
                }
            }
        } message: {
            Text("Apps using this folder will have tweaks disabled before the folder is deleted.")
        }
    }

    private func header(_ folder: FlekTweakFolder) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "folder.fill.badge.gearshape")
                .font(.system(size: 38))
                .foregroundStyle(.orange)
            Text(folder.name).font(.title2.bold())
            Text("\(folder.enabledTweaks) enabled of \(folder.totalTweaks) tweak\(folder.totalTweaks == 1 ? "" : "s")")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            let users = library.appsUsing(folder, sharedModel: sharedModel)
            if !users.isEmpty {
                Text("Used by \(users.map(\.displayName).joined(separator: ", "))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(22)
        .frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 24, tint: 0.08)
    }

    private func entryCard(_ entry: FlekTweakEntry) -> some View {
        HStack(spacing: 13) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(entry.isTweak ? Color.orange.opacity(0.12) : Color.secondary.opacity(0.10))
                Image(systemName: entrySymbol(entry))
                    .foregroundStyle(entry.isTweak ? .orange : .secondary)
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 3) {
                Text(entry.displayName)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .opacity(entry.enabled ? 1 : 0.55)
                Text("\(entry.kind.rawValue) · \(ByteCountFormatter.string(fromByteCount: entry.bytes, countStyle: .file))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()

            if entry.displayName != "TweakLoader.dylib" && entry.isTweak {
                Toggle(
                    "",
                    isOn: Binding(
                        get: { entry.enabled },
                        set: { library.setEnabled($0, entry: entry, sharedModel: sharedModel) }
                    )
                )
                .labelsHidden()
                .tint(.green)
            }
        }
        .padding(15)
        .flekGlassCard(cornerRadius: 20, tint: 0.07)
        .contextMenu {
            if entry.displayName != "TweakLoader.dylib" {
                Button(role: .destructive) {
                    library.delete(entry, sharedModel: sharedModel)
                } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
    }

    private func entrySymbol(_ entry: FlekTweakEntry) -> String {
        switch entry.kind {
        case .framework: return "shippingbox.fill"
        case .dylib: return "puzzlepiece.extension.fill"
        case .folder: return "folder.fill"
        case .file: return "doc.fill"
        }
    }

    private func management(_ folder: FlekTweakFolder) -> some View {
        VStack(spacing: 10) {
            Button {
                importing = true
            } label: {
                Label("Import Tweaks…", systemImage: "square.and.arrow.down")
            }
            .buttonStyle(.borderedProminent)

            Button {
                Task { await library.sign(folder: folder, sharedModel: sharedModel) }
            } label: {
                Label(library.isSigning ? "Signing…" : "Sign Folder", systemImage: "signature")
            }
            .buttonStyle(.bordered)
            .disabled(library.isSigning)

            Button {
                renameText = folder.name
                renaming = true
            } label: {
                Label("Rename Folder", systemImage: "pencil")
            }
            .buttonStyle(.bordered)

            Button(role: .destructive) {
                confirmDeleteFolder = true
            } label: {
                Label("Delete Folder", systemImage: "trash")
            }
            .buttonStyle(.bordered)
        }
        .padding(18)
        .frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }
}

struct FlekAppTweakAssignmentView: View {
    @ObservedObject var app: LCAppModel
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var library = FlekTweakLibrary.shared

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                VStack(spacing: 10) {
                    Image(uiImage: app.appInfo.iconIsDarkIcon(false))
                        .resizable()
                        .scaledToFill()
                        .frame(width: 72, height: 72)
                        .clipShape(RoundedRectangle(cornerRadius: 17, style: .continuous))
                    Text(app.displayName).font(.title2.bold())
                    Text(app.bundleIdentifier)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(22)
                .frame(maxWidth: .infinity)
                .flekGlassCard(cornerRadius: 24, tint: 0.08)

                choice(
                    nil,
                    title: "No Tweaks",
                    detail: "Do not load a selected tweak folder for this app."
                )

                ForEach(library.folders) { folder in
                    choice(
                        folder.name,
                        title: folder.name,
                        detail: "\(folder.enabledTweaks) enabled tweak\(folder.enabledTweaks == 1 ? "" : "s")"
                    )
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Runtime").font(.headline)
                    Text("FlekDeck continues to load the selected folder recursively through its existing TweakLoader/bootstrap path. This screen changes LCTweakFolder only; it does not add a competing executable-patching injection engine.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .flekGlassCard(cornerRadius: 20, tint: 0.07)
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle("Tweaks")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            library.refresh(sharedModel: sharedModel)
        }
    }

    private func choice(_ name: String?, title: String, detail: String) -> some View {
        let selected = app.uiTweakFolder == name
        return Button {
            app.uiTweakFolder = name
            UISelectionFeedbackGenerator().selectionChanged()
        } label: {
            HStack(spacing: 13) {
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundStyle(selected ? .green : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.headline).foregroundStyle(.primary)
                    Text(detail).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(15)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .flekGlassCard(cornerRadius: 20, tint: 0.07)
    }
}
