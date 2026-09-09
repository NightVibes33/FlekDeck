import SwiftUI
import UIKit

// MARK: - XMB menu model

enum FlekXMBCategory: String, CaseIterable, Identifiable {
    case users, settings, photo, music, video, game, network

    var id: String { rawValue }

    var title: String {
        switch self {
        case .users: return "Users"
        case .settings: return "Settings"
        case .photo: return "Photo"
        case .music: return "Music"
        case .video: return "Video"
        case .game: return "Game"
        case .network: return "Network"
        }
    }

    var symbol: String {
        switch self {
        case .users: return "person.fill"
        case .settings: return "wrench.and.screwdriver.fill"
        case .photo: return "camera.fill"
        case .music: return "music.note"
        case .video: return "film.fill"
        case .game: return "gamecontroller.fill"
        case .network: return "globe"
        }
    }

    var tint: Color {
        switch self {
        case .users: return Color(red: 0.88, green: 0.76, blue: 0.50)
        case .settings: return Color(red: 0.62, green: 0.66, blue: 0.72)
        case .photo: return Color(red: 0.78, green: 0.52, blue: 0.78)
        case .music: return Color(red: 0.48, green: 0.74, blue: 0.58)
        case .video: return Color(red: 0.79, green: 0.49, blue: 0.37)
        case .game: return Color(red: 0.40, green: 0.82, blue: 1.00)
        case .network: return Color(red: 0.36, green: 0.56, blue: 0.90)
        }
    }
}

enum FlekXMBColumnID: Hashable {
    case category(FlekXMBCategory)
    case applications
    case app(String)
    case httpServer
    case tweaks
    case appearance
    case controllers
    case about
    case connection
    case wallpapers

    var isPage: Bool {
        switch self {
        case .app, .httpServer, .tweaks, .appearance, .controllers, .about, .connection:
            return true
        default:
            return false
        }
    }
}

enum FlekXMBIcon {
    case symbol(String, Color)
    case app(LCAppModel)
    case wallpaper(FlekWallpaper)
}

struct FlekXMBInfoLine: Identifiable {
    let label: String
    let value: String
    var id: String { label + value }
}

struct FlekXMBInfo {
    var title: String
    var subtitle: String?
    var icon: FlekXMBIcon?
    var lines: [FlekXMBInfoLine] = []
    var body: String?
    var footnote: String?
    var accent: Color = .blue
}

struct FlekXMBItem: Identifiable {
    let id: String
    let title: String
    var subtitle: String?
    var icon: FlekXMBIcon
    var badge: String?
    var badgeTint: Color = .blue
    var info: FlekXMBInfo?
    var activate: (() -> Void)?
    var secondary: (() -> Void)?
    var secondaryTitle: String?
    var adjust: ((Int) -> Void)?
    var progress: Double?
    var dimmed = false
}

// MARK: - Navigator

@MainActor
final class FlekXMBNavigator: ObservableObject {
    @Published var categoryIndex: Int = 5
    @Published var stack: [FlekXMBColumnID] = []
    @Published var selections: [FlekXMBColumnID: Int] = [:]
    @Published var hoverPinned = false
    @Published var hovering = false
    @Published var toast: String?
    @Published var wantsExit = false

    var appsProvider: () -> [LCAppModel] = { [] }
    private var hoverTask: Task<Void, Never>?
    private var toastTask: Task<Void, Never>?

    var category: FlekXMBCategory {
        let all = FlekXMBCategory.allCases
        return all[min(max(categoryIndex, 0), all.count - 1)]
    }

    var column: FlekXMBColumnID {
        stack.last ?? .category(category)
    }

    var atRoot: Bool { stack.isEmpty }

    var selection: Int {
        selections[column] ?? 0
    }

    var itemCount: Int { items(for: column).count }

    var focused: FlekXMBItem? { item(at: selection) }

    var path: [String] {
        var result = [category.title]
        for value in stack { result.append(title(of: value)) }
        return result
    }

    func begin() {
        wantsExit = false
        clampSelection()
        armHover()
    }

    func clearExit() { wantsExit = false }

    func requestExit() { wantsExit = true }

    func handle(_ input: FlekControllerInput) {
        switch input {
        case .up:
            moveVertical(-1)
        case .down:
            moveVertical(1)
        case .left:
            if atRoot {
                moveCategory(-1)
            } else if focused?.adjust != nil {
                adjust(-1)
            } else {
                pop()
            }
        case .right:
            if atRoot {
                moveCategory(1)
            } else if focused?.adjust != nil {
                adjust(1)
            } else {
                activate()
            }
        case .cross:
            activate()
        case .circle:
            if atRoot { requestExit() } else { pop() }
        case .triangle:
            toggleInfo()
        case .square:
            secondary()
        case .l1:
            if atRoot { moveCategory(-1) } else { pop() }
        case .r1:
            if atRoot { moveCategory(1) } else { activate() }
        case .options:
            refreshCurrent()
        case .share:
            say("FlekDeck Controller Mode")
        case .home:
            requestExit()
        }
    }

    func push(_ id: FlekXMBColumnID) {
        stack.append(id)
        clampSelection()
        pulse()
        armHover()
    }

    func pop() {
        guard !stack.isEmpty else { return }
        stack.removeLast()
        hoverPinned = false
        hovering = false
        pulse()
        armHover()
    }

    func item(at index: Int) -> FlekXMBItem? {
        let rows = items(for: column)
        guard rows.indices.contains(index) else { return nil }
        return rows[index]
    }

    func title(of id: FlekXMBColumnID) -> String {
        switch id {
        case .category(let category): return category.title
        case .applications: return "Installed Applications"
        case .app(let key): return app(for: key)?.displayName ?? "Application"
        case .httpServer: return "HTTP Server"
        case .tweaks: return "Tweaks"
        case .appearance: return "Theme & Wave"
        case .controllers: return "Controller"
        case .about: return "System Information"
        case .connection: return "Connection Information"
        case .wallpapers: return "Wallpapers"
        }
    }

    private func moveVertical(_ delta: Int) {
        guard itemCount > 0 else { return }
        let next = min(max(selection + delta, 0), itemCount - 1)
        guard next != selection else { return }
        selections[column] = next
        hoverPinned = false
        hovering = false
        pulse()
        armHover()
    }

    private func moveCategory(_ delta: Int) {
        let count = FlekXMBCategory.allCases.count
        let next = min(max(categoryIndex + delta, 0), count - 1)
        guard next != categoryIndex else { return }
        categoryIndex = next
        stack.removeAll()
        hoverPinned = false
        hovering = false
        clampSelection()
        FlekControllerHub.shared.paintAll(UIColor(category.tint))
        pulse()
        armHover()
    }

    private func activate() {
        guard let item = focused, !item.dimmed else { return }
        if let action = item.activate {
            action()
            pulse(strong: true)
        }
    }

    private func secondary() {
        guard let action = focused?.secondary else { return }
        action()
        pulse(strong: true)
    }

    private func adjust(_ direction: Int) {
        guard let action = focused?.adjust else { return }
        action(direction)
        objectWillChange.send()
        pulse()
        armHover()
    }

    private func toggleInfo() {
        guard focused?.info != nil else { return }
        hoverPinned.toggle()
        hovering = hoverPinned
        if !hoverPinned { armHover() }
        pulse()
    }

    private func refreshCurrent() {
        switch column {
        case .httpServer:
            if FlekHTTPServer.shared.status.isRunning { FlekHTTPServer.shared.restart() }
            say("HTTP server refreshed")
        case .tweaks:
            FlekTweakStore.shared.refresh()
            say("Tweak library refreshed")
        default:
            say("Refreshed")
        }
        objectWillChange.send()
        pulse()
    }

    private func clampSelection() {
        let count = itemCount
        selections[column] = count == 0 ? 0 : min(max(selection, 0), count - 1)
    }

    private func armHover() {
        hoverTask?.cancel()
        guard !hoverPinned, focused?.info != nil else { return }
        hoverTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 650_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.hovering = true }
        }
    }

    func say(_ message: String) {
        toastTask?.cancel()
        toast = message
        toastTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_650_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.toast = nil }
        }
    }

    private func pulse(strong: Bool = false) {
        UISelectionFeedbackGenerator().selectionChanged()
        FlekControllerHub.shared.rumble(
            intensity: strong ? 0.55 : 0.28,
            sharpness: strong ? 0.62 : 0.48,
            duration: strong ? 0.065 : 0.035
        )
    }

    // MARK: Items

    private func items(for id: FlekXMBColumnID) -> [FlekXMBItem] {
        switch id {
        case .category(let category): return categoryItems(category)
        case .applications: return applicationItems()
        case .app(let key): return appItems(key)
        case .httpServer: return httpItems()
        case .tweaks: return tweakItems()
        case .appearance: return appearanceItems()
        case .controllers: return controllerItems()
        case .about: return aboutItems()
        case .connection: return connectionItems()
        case .wallpapers: return wallpaperItems()
        }
    }

    private func categoryItems(_ category: FlekXMBCategory) -> [FlekXMBItem] {
        switch category {
        case .users:
            return [
                FlekXMBItem(
                    id: "user.device",
                    title: "Device",
                    subtitle: UIDevice.current.model,
                    icon: .symbol("person.crop.circle.fill", category.tint),
                    info: FlekXMBInfo(
                        title: "Device",
                        subtitle: "FlekDeck on this device",
                        icon: .symbol("iphone", category.tint),
                        lines: [
                            .init(label: "System", value: "\(UIDevice.current.systemName) \(UIDevice.current.systemVersion)"),
                            .init(label: "Applications", value: "\(appsProvider().count)")
                        ], accent: category.tint
                    ),
                    activate: { [weak self] in self?.push(.about) }
                ),
                FlekXMBItem(
                    id: "user.exit",
                    title: "Return to FlekDeck",
                    subtitle: "Leave Controller Mode",
                    icon: .symbol("iphone", .secondary),
                    activate: { [weak self] in self?.requestExit() }
                )
            ]

        case .settings:
            let server = FlekHTTPServer.shared
            let tweaks = FlekTweakStore.shared
            return [
                FlekXMBItem(
                    id: "settings.http",
                    title: "HTTP Server",
                    subtitle: server.status.isRunning ? (server.addresses.first ?? "Running") : "Serve a folder over the local network",
                    icon: .symbol("network", .green),
                    badge: server.status.title,
                    badgeTint: server.status.isRunning ? .green : .secondary,
                    activate: { [weak self] in self?.push(.httpServer) }
                ),
                FlekXMBItem(
                    id: "settings.tweaks",
                    title: "Tweaks",
                    subtitle: "Library, global scope and per-app loading",
                    icon: .symbol("puzzlepiece.extension.fill", .purple),
                    badge: tweaks.library.isEmpty ? nil : "\(tweaks.library.count)",
                    activate: { [weak self] in self?.push(.tweaks) }
                ),
                FlekXMBItem(
                    id: "settings.theme",
                    title: "Theme & Wave",
                    subtitle: "Accent, motes, scanlines, motion and grid",
                    icon: .symbol("paintpalette.fill", .pink),
                    activate: { [weak self] in self?.push(.appearance) }
                ),
                FlekXMBItem(
                    id: "settings.controller",
                    title: "Controller",
                    subtitle: controllerSubtitle,
                    icon: .symbol("gamecontroller.fill", .cyan),
                    badge: FlekControllerHub.shared.pads.isEmpty ? nil : "\(FlekControllerHub.shared.pads.count)",
                    activate: { [weak self] in self?.push(.controllers) }
                ),
                FlekXMBItem(
                    id: "settings.about",
                    title: "System Information",
                    subtitle: "FlekDeck runtime information",
                    icon: .symbol("info.circle.fill", .secondary),
                    activate: { [weak self] in self?.push(.about) }
                )
            ]

        case .photo:
            return [
                FlekXMBItem(
                    id: "photo.wallpapers",
                    title: "Wallpapers",
                    subtitle: "Choose from FlekDeck and Vibe presets",
                    icon: .symbol("photo.on.rectangle.angled", category.tint),
                    badge: "\(FlekWallpaper.collection.count)",
                    activate: { [weak self] in self?.push(.wallpapers) }
                )
            ]

        case .music:
            return [FlekXMBItem(id: "music.empty", title: "There are no titles.", subtitle: "FlekDeck has no host music library", icon: .symbol("music.note", category.tint), dimmed: true)]

        case .video:
            return [FlekXMBItem(id: "video.empty", title: "There are no titles.", subtitle: "Video stays inside guest applications", icon: .symbol("film", category.tint), dimmed: true)]

        case .game:
            let apps = appsProvider()
            return [
                FlekXMBItem(
                    id: "game.installed",
                    title: "Installed Applications",
                    subtitle: apps.isEmpty ? "No applications installed" : "\(apps.count) available in FlekDeck",
                    icon: .symbol("square.stack.3d.up.fill", category.tint),
                    badge: apps.isEmpty ? nil : "\(apps.count)",
                    activate: { [weak self] in self?.push(.applications) }
                )
            ]

        case .network:
            return [
                FlekXMBItem(
                    id: "network.connection",
                    title: "Connection Information",
                    subtitle: FlekHTTPServer.localIPv4Addresses().first ?? "Not connected",
                    icon: .symbol("wifi", category.tint),
                    activate: { [weak self] in self?.push(.connection) }
                ),
                FlekXMBItem(
                    id: "network.server",
                    title: "HTTP Server",
                    subtitle: FlekHTTPServer.shared.status.title,
                    icon: .symbol("network", .green),
                    activate: { [weak self] in self?.push(.httpServer) }
                )
            ]
        }
    }

    private func applicationItems() -> [FlekXMBItem] {
        let apps = appsProvider().sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
        if apps.isEmpty {
            return [FlekXMBItem(id: "apps.empty", title: "There are no titles.", subtitle: "Install an IPA from FlekDeck first", icon: .symbol("square.stack.3d.up.slash", .secondary), dimmed: true)]
        }
        return apps.map { app in
            let key = appKey(app)
            return FlekXMBItem(
                id: "app.\(key)",
                title: app.displayName,
                subtitle: app.bundleIdentifier,
                icon: .app(app),
                badge: app.version,
                info: appInfo(app),
                activate: { [weak self] in self?.launch(app, parallel: false) },
                secondary: { [weak self] in self?.launch(app, parallel: true) },
                secondaryTitle: "Parallel"
            )
        }
    }

    private func appItems(_ key: String) -> [FlekXMBItem] {
        guard let app = app(for: key) else {
            return [FlekXMBItem(id: "app.missing", title: "Application unavailable", icon: .symbol("exclamationmark.triangle", .orange), dimmed: true)]
        }
        return [
            FlekXMBItem(id: "app.launch", title: "Launch", subtitle: "Run in FlekDeck's normal single-app path", icon: .symbol("play.fill", .green), activate: { [weak self] in self?.launch(app, parallel: false) }),
            FlekXMBItem(id: "app.parallel", title: "Run Parallel", subtitle: "Use FlekDeck multitasking when available", icon: .symbol("rectangle.on.rectangle", .blue), activate: { [weak self] in self?.launch(app, parallel: true) }),
            FlekXMBItem(id: "app.tweaks", title: "Tweak Profile", subtitle: app.uiTweakFolder ?? "No named profile selected", icon: .symbol("puzzlepiece.extension", .purple), info: FlekTweakStore.shared.appInfo(app), dimmed: true),
            FlekXMBItem(id: "app.version", title: "Version", subtitle: app.version, icon: .symbol("number", .secondary), dimmed: true),
            FlekXMBItem(id: "app.bundle", title: "Bundle Identifier", subtitle: app.bundleIdentifier, icon: .symbol("shippingbox", .secondary), dimmed: true)
        ]
    }

    private func appInfo(_ app: LCAppModel) -> FlekXMBInfo {
        FlekXMBInfo(
            title: app.displayName,
            subtitle: app.bundleIdentifier,
            icon: .app(app),
            lines: [
                .init(label: "Version", value: app.version),
                .init(label: "Tweaks", value: app.uiTweakFolder ?? "None"),
                .init(label: "Launch", value: app.shouldLaunchInMultitaskMode ? "Parallel" : "Single")
            ],
            body: "Cross launches normally. Square launches through FlekDeck's parallel runtime when the device/runtime supports it.",
            accent: .cyan
        )
    }

    private func httpItems() -> [FlekXMBItem] {
        let server = FlekHTTPServer.shared
        var rows: [FlekXMBItem] = [
            FlekXMBItem(
                id: "http.power",
                title: server.status.isRunning ? "Stop Server" : "Start Server",
                subtitle: server.status.isRunning ? (server.addresses.first ?? "Listening") : "Serve \(server.root.lastPathComponent)",
                icon: .symbol(server.status.isRunning ? "stop.fill" : "play.fill", server.status.isRunning ? .red : .green),
                badge: server.status.title,
                activate: { [weak self] in
                    if server.status.isRunning { server.stop() } else { server.start() }
                    self?.objectWillChange.send()
                }
            ),
            FlekXMBItem(
                id: "http.port",
                title: "Port",
                subtitle: "Left / right changes the listening port",
                icon: .symbol("number", .blue),
                badge: "\(server.port)",
                adjust: { [weak self] direction in
                    let next = min(max(Int(server.port) + direction, 1024), 65535)
                    server.setPort(next)
                    self?.objectWillChange.send()
                }
            ),
            FlekXMBItem(
                id: "http.root",
                title: "www Path",
                subtitle: server.root.path,
                icon: .symbol("folder.fill", .orange),
                info: FlekXMBInfo(title: server.root.lastPathComponent, subtitle: "Served root", lines: [.init(label: "Path", value: server.root.path)], accent: .orange),
                dimmed: true
            )
        ]
        rows += server.addresses.enumerated().map { index, address in
            FlekXMBItem(
                id: "http.address.\(index)",
                title: address,
                subtitle: "Cross copies this LAN address",
                icon: .symbol("wifi", .green),
                activate: { [weak self] in UIPasteboard.general.string = address; self?.say("Address copied") }
            )
        }
        rows.append(FlekXMBItem(id: "http.traffic", title: "Traffic", subtitle: "\(server.requestCount) requests · \(ByteCountFormatter.string(fromByteCount: Int64(server.bytesServed), countStyle: .file))", icon: .symbol("arrow.left.arrow.right", .secondary), dimmed: true))
        return rows
    }

    private func tweakItems() -> [FlekXMBItem] {
        let store = FlekTweakStore.shared
        if store.library.isEmpty {
            return [FlekXMBItem(id: "tweaks.empty", title: "No tweaks yet", subtitle: "Import tweaks from Settings → Tweaks", icon: .symbol("wrench.and.screwdriver", .secondary), dimmed: true)]
        }
        return store.library.map { tweak in
            FlekXMBItem(
                id: "tweak.\(tweak.id)",
                title: tweak.name,
                subtitle: tweak.detail,
                icon: .symbol(tweak.isFramework ? "shippingbox.fill" : "puzzlepiece.extension.fill", tweak.isLoadable ? .purple : .orange),
                badge: store.isGlobal(tweak) ? "GLOBAL" : store.scopeBadge(tweak),
                badgeTint: store.isGlobal(tweak) ? .green : .secondary,
                info: store.xmbInfo(tweak),
                dimmed: !tweak.isLoadable
            )
        }
    }

    private func appearanceItems() -> [FlekXMBItem] {
        let defaults = FlekAppearanceStore.defaults
        let accent = FlekAppearanceStore.accent
        let transition = FlekAppearanceStore.pageTransition
        let density = FlekAppearanceStore.moteDensity
        return [
            FlekXMBItem(
                id: "theme.accent", title: "Accent", subtitle: "Tint used by FlekDeck controls", icon: .symbol("paintpalette.fill", accent.color), badge: accent.title,
                adjust: { [weak self] direction in
                    let choices = FlekAccentChoice.allCases
                    let current = accent.rawValue
                    let next = min(max(current + direction, 0), choices.count - 1)
                    defaults.set(next, forKey: FlekDeckKeys.accentChoice)
                    FlekAppearanceStore.postChanged(); self?.objectWillChange.send()
                }
            ),
            FlekXMBItem(
                id: "theme.motes", title: "Motes", subtitle: "Ambient particles over the wallpaper", icon: .symbol("sparkles", .cyan), badge: FlekAppearanceStore.showMotes ? "On" : "Off",
                activate: { [weak self] in defaults.set(!FlekAppearanceStore.showMotes, forKey: FlekDeckKeys.showMotes); FlekAppearanceStore.postChanged(); self?.objectWillChange.send() }
            ),
            FlekXMBItem(
                id: "theme.density", title: "Mote Density", subtitle: "Ambient particle count", icon: .symbol("circle.grid.3x3.fill", .cyan), badge: "\(Int(density * 100))%", progress: density,
                adjust: { [weak self] direction in
                    let next = min(max(FlekAppearanceStore.moteDensity + Double(direction) * 0.1, 0), 1)
                    defaults.set(next, forKey: FlekDeckKeys.moteDensity); FlekAppearanceStore.postChanged(); self?.objectWillChange.send()
                }
            ),
            FlekXMBItem(
                id: "theme.scanlines", title: "Scanlines", subtitle: "Fine display texture over the wallpaper", icon: .symbol("line.3.horizontal", .purple), badge: FlekAppearanceStore.scanlines ? "On" : "Off",
                activate: { [weak self] in defaults.set(!FlekAppearanceStore.scanlines, forKey: FlekDeckKeys.scanlines); FlekAppearanceStore.postChanged(); self?.objectWillChange.send() }
            ),
            FlekXMBItem(
                id: "theme.motion", title: "Reduce Motion", subtitle: "Stops wallpaper drift and simplifies page effects", icon: .symbol("figure.walk.motion", .orange), badge: FlekAppearanceStore.reduceMotion ? "On" : "Off",
                activate: { [weak self] in defaults.set(!FlekAppearanceStore.reduceMotion, forKey: FlekDeckKeys.reduceMotion); FlekAppearanceStore.postChanged(); self?.objectWillChange.send() }
            ),
            FlekXMBItem(
                id: "theme.columns", title: "Home Screen Columns", subtitle: "Real UIKit Springboard column count", icon: .symbol("square.grid.3x3", .blue), badge: "\(FlekAppearanceStore.gridColumns)",
                adjust: { [weak self] direction in
                    let next = min(max(FlekAppearanceStore.gridColumns + direction, 2), 6)
                    defaults.set(next, forKey: FlekDeckKeys.gridColumns); FlekAppearanceStore.postChanged(); self?.objectWillChange.send()
                }
            ),
            FlekXMBItem(
                id: "theme.labels", title: "App Labels", subtitle: "Names beneath Springboard icons", icon: .symbol("textformat", .green), badge: FlekAppearanceStore.showLabels ? "Shown" : "Hidden",
                activate: { [weak self] in defaults.set(!FlekAppearanceStore.showLabels, forKey: FlekDeckKeys.showAppLabels); FlekAppearanceStore.postChanged(); self?.objectWillChange.send() }
            ),
            FlekXMBItem(
                id: "theme.dock", title: "Dock Background", subtitle: "Glass/material behind the bottom home controls", icon: .symbol("dock.rectangle", .indigo), badge: FlekAppearanceStore.hideDockBackground ? "Hidden" : "Shown",
                activate: { [weak self] in defaults.set(!FlekAppearanceStore.hideDockBackground, forKey: FlekDeckKeys.hideDockBackground); FlekAppearanceStore.postChanged(); self?.objectWillChange.send() }
            ),
            FlekXMBItem(
                id: "theme.transition", title: "Page Transition", subtitle: "Springboard page animation", icon: .symbol("rectangle.2.swap", .pink), badge: transition.title,
                adjust: { [weak self] direction in
                    let values = FlekPageTransition.allCases
                    let index = values.firstIndex(of: FlekAppearanceStore.pageTransition) ?? 0
                    let next = min(max(index + direction, 0), values.count - 1)
                    defaults.set(values[next].rawValue, forKey: FlekDeckKeys.pageTransition); FlekAppearanceStore.postChanged(); self?.objectWillChange.send()
                }
            )
        ]
    }

    private func controllerItems() -> [FlekXMBItem] {
        let hub = FlekControllerHub.shared
        var rows = hub.pads.map { pad in
            FlekXMBItem(
                id: "controller.\(pad.id)",
                title: pad.kind.title,
                subtitle: "\(pad.vendorName) · \(pad.batteryText)",
                icon: .symbol(pad.kind.symbol, .cyan),
                info: FlekXMBInfo(
                    title: pad.kind.title,
                    subtitle: pad.vendorName,
                    lines: [
                        .init(label: "Battery", value: pad.batteryText),
                        .init(label: "Haptics", value: pad.hasHaptics ? "Available" : "Unavailable"),
                        .init(label: "Light Bar", value: pad.hasLightBar ? "Available" : "Unavailable"),
                        .init(label: "Adaptive Triggers", value: pad.hasAdaptiveTriggers ? "Detected" : "Unavailable")
                    ], accent: .cyan
                ),
                activate: { [weak self] in hub.rumble(intensity: 0.8, sharpness: 0.6, duration: 0.15); self?.say("Rumble test") },
                secondary: { [weak self] in hub.paintAll(FlekAppearanceStore.accent.uiColor); self?.say("Light bar updated") },
                secondaryTitle: "Light"
            )
        }
        if rows.isEmpty {
            rows.append(FlekXMBItem(id: "controller.none", title: "No physical controller", subtitle: "Touch Test Controls can drive the same navigator", icon: .symbol("gamecontroller", .secondary), dimmed: true))
        }
        return rows
    }

    private func aboutItems() -> [FlekXMBItem] {
        [
            FlekXMBItem(id: "about.version", title: "FlekDeck", subtitle: LCUtils.getVersionInfo(), icon: .symbol("app.badge", .blue), dimmed: true),
            FlekXMBItem(id: "about.system", title: UIDevice.current.systemName, subtitle: UIDevice.current.systemVersion, icon: .symbol("iphone", .secondary), dimmed: true),
            FlekXMBItem(id: "about.apps", title: "Applications", subtitle: "\(appsProvider().count) installed", icon: .symbol("square.stack.3d.up", .green), dimmed: true),
            FlekXMBItem(id: "about.runtime", title: "Controller Runtime", subtitle: "Vibe XMB adapted to FlekDeck launch/settings state", icon: .symbol("gamecontroller.fill", .cyan), dimmed: true)
        ]
    }

    private func connectionItems() -> [FlekXMBItem] {
        let addresses = FlekHTTPServer.localIPv4Addresses()
        if addresses.isEmpty {
            return [FlekXMBItem(id: "connection.none", title: "Not connected", subtitle: "No active IPv4 network interface", icon: .symbol("wifi.slash", .secondary), dimmed: true)]
        }
        return addresses.enumerated().map { index, address in
            FlekXMBItem(id: "connection.\(index)", title: address, subtitle: index == 0 ? "Preferred LAN address" : "Additional interface", icon: .symbol(index == 0 ? "wifi" : "network", .blue), activate: { [weak self] in UIPasteboard.general.string = address; self?.say("Address copied") })
        }
    }

    private func wallpaperItems() -> [FlekXMBItem] {
        let current = FlekAppearanceStore.defaults.string(forKey: FlekDeckKeys.wallpaperName) ?? FlekWallpaper.defaultDescriptor
        return FlekWallpaper.collection.map { wallpaper in
            FlekXMBItem(
                id: "wallpaper.\(wallpaper.id)",
                title: wallpaper.displayName,
                subtitle: wallpaper.id == current ? "Current wallpaper" : "Cross to apply",
                icon: .wallpaper(wallpaper),
                badge: wallpaper.id == current ? "CURRENT" : nil,
                activate: { [weak self] in
                    FlekAppearanceStore.defaults.set(wallpaper.id, forKey: FlekDeckKeys.wallpaperName)
                    FlekAppearanceStore.defaults.set("", forKey: FlekDeckKeys.wallpaperPhoto)
                    FlekAppearanceStore.postChanged()
                    self?.objectWillChange.send()
                    self?.say("Wallpaper applied")
                }
            )
        }
    }

    private var controllerSubtitle: String {
        guard let first = FlekControllerHub.shared.pads.first else { return "No controller connected" }
        let count = FlekControllerHub.shared.pads.count
        return count > 1 ? "\(first.kind.shortTitle) and \(count - 1) more" : first.kind.title
    }

    private func appKey(_ app: LCAppModel) -> String {
        app.appInfo.relativeBundlePath ?? app.bundleIdentifier
    }

    private func app(for key: String) -> LCAppModel? {
        appsProvider().first { appKey($0) == key }
    }

    private func launch(_ app: LCAppModel, parallel: Bool) {
        Task { @MainActor [weak self] in
            do {
                if #available(iOS 16.0, *), parallel {
                    try await app.runApp(multitask: true)
                } else {
                    try await app.runApp(multitask: false)
                }
            } catch {
                self?.say(error.localizedDescription)
            }
        }
    }
}

// MARK: - Root view

struct FlekXMBRootView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var hub = FlekControllerHub.shared
    @StateObject private var nav = FlekXMBNavigator()
    @State private var appeared = false
    @State private var previousOrientation: UIInterfaceOrientationMask = .portrait

    private static let anchorXFraction: CGFloat = 0.27
    private static let categoryYFraction: CGFloat = 0.25
    private static let itemYFraction: CGFloat = 0.46
    private static let pushedItemYFraction: CGFloat = 0.28
    private static let rowHeight: CGFloat = 61
    private static let categorySpacing: CGFloat = 82
    private static let iconInset: CGFloat = 34

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            ZStack {
                background(size)

                Group {
                    if nav.column.isPage {
                        page(size)
                    } else {
                        crossbar(size)
                    }
                }
                .opacity(appeared ? 1 : 0)
                .blur(radius: appeared ? 0 : 7)

                topBar(size)
                hoverPanel(size)
                footer(size)

                if hub.controllerUITestMode || hub.pads.isEmpty {
                    FlekXMBTestControls { nav.handle($0) }
                }

                if let toast = nav.toast {
                    Text(toast)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 15)
                        .padding(.vertical, 9)
                        .background(.ultraThinMaterial, in: Capsule())
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .padding(.top, 92)
                        .transition(.opacity.combined(with: .scale(scale: 0.94)))
                }
            }
            .frame(width: size.width, height: size.height)
        }
        .ignoresSafeArea()
        .preferredColorScheme(.dark)
        .onAppear(perform: activate)
        .onDisappear(perform: deactivate)
        .onChange(of: nav.wantsExit) { wants in
            guard wants else { return }
            nav.clearExit()
            dismiss()
        }
    }

    private func activate() {
        previousOrientation = AppDelegate.orientationLock
        AppDelegate.orientationLock = .landscape
        _ = AppDelegate.applyOrientationLock()

        nav.appsProvider = { sharedModel.apps.filter { !$0.uiIsHidden } }
        FlekTweakStore.shared.refresh()
        nav.begin()
        hub.paintAll(UIColor(nav.category.tint))
        hub.sink = { input in nav.handle(input) }
        hub.onHome = { nav.handle(.home) }
        withAnimation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .easeOut(duration: 0.45)) {
            appeared = true
        }
    }

    private func deactivate() {
        hub.sink = nil
        hub.onHome = nil
        AppDelegate.orientationLock = previousOrientation
        _ = AppDelegate.applyOrientationLock()
    }

    private func background(_ size: CGSize) -> some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.018, green: 0.028, blue: 0.055), Color(red: 0.035, green: 0.075, blue: 0.12), .black],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            FlekXMBWave(tint: nav.category.tint, reduceMotion: FlekAppearanceStore.reduceMotion)
                .opacity(0.86)

            RadialGradient(
                colors: [nav.category.tint.opacity(0.24), .clear],
                center: UnitPoint(x: Self.anchorXFraction, y: Self.categoryYFraction),
                startRadius: 0,
                endRadius: max(size.width, size.height) * 0.76
            )
            .blendMode(.plusLighter)

            if FlekAppearanceStore.showMotes {
                FlekXMBDust(count: FlekAppearanceStore.moteCount, reduceMotion: FlekAppearanceStore.reduceMotion)
            }

            if FlekAppearanceStore.scanlines {
                FlekXMBScanlines()
            }
        }
        .ignoresSafeArea()
        .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .easeOut(duration: 0.45), value: nav.categoryIndex)
    }

    private func crossbar(_ size: CGSize) -> some View {
        let pushed = !nav.atRoot
        let anchorX = size.width * Self.anchorXFraction
        let categoryY = size.height * Self.categoryYFraction
        let itemY = size.height * (pushed ? Self.pushedItemYFraction : Self.itemYFraction)
        let ceiling = pushed ? size.height * 0.15 : categoryY + 50
        let rowLeading = anchorX - Self.iconInset
        let rowWidth = max(220, size.width - rowLeading - 24)

        return ZStack(alignment: .topLeading) {
            LinearGradient(colors: [.clear, .white.opacity(0.18), .white.opacity(0.04), .clear], startPoint: .leading, endPoint: .trailing)
                .frame(height: 1)
                .offset(y: categoryY)
                .blendMode(.plusLighter)
                .opacity(pushed ? 0 : 1)

            categories(anchorX: anchorX, y: categoryY, width: size.width)
                .opacity(pushed ? 0 : 1)
                .offset(x: pushed ? -72 : 0)

            column(leading: rowLeading, width: rowWidth, itemY: itemY, ceiling: ceiling, height: size.height)
        }
        .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .spring(response: 0.36, dampingFraction: 0.88), value: pushed)
    }

    private func categories(anchorX: CGFloat, y: CGFloat, width: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            ForEach(Array(FlekXMBCategory.allCases.enumerated()), id: \.element.id) { index, category in
                let offset = CGFloat(index - nav.categoryIndex)
                let x = anchorX + offset * Self.categorySpacing
                let selected = index == nav.categoryIndex
                VStack(spacing: 6) {
                    Image(systemName: category.symbol)
                        .font(.system(size: selected ? 28 : 20, weight: .light))
                        .foregroundStyle(selected ? .white : .white.opacity(0.52))
                        .frame(height: 34)
                        .shadow(color: category.tint.opacity(selected ? 0.9 : 0), radius: 13)
                    Text(category.title)
                        .font(.system(size: selected ? 12 : 10, weight: selected ? .semibold : .regular))
                        .foregroundStyle(selected ? .white : .white.opacity(0.45))
                        .fixedSize()
                }
                .frame(width: Self.categorySpacing)
                .opacity(x > -70 && x < width + 70 ? 1 : 0)
                .position(x: x, y: y)
            }
        }
        .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .spring(response: 0.34, dampingFraction: 0.86), value: nav.categoryIndex)
    }

    @ViewBuilder
    private func column(leading: CGFloat, width: CGFloat, itemY: CGFloat, ceiling: CGFloat, height: CGFloat) -> some View {
        let count = nav.itemCount
        if count == 0 {
            Text("There are no titles.")
                .font(.system(size: 14))
                .foregroundStyle(.white.opacity(0.48))
                .frame(width: width, alignment: .leading)
                .offset(x: leading + Self.iconInset, y: itemY - 10)
        } else {
            let lower = max(0, nav.selection - 4)
            let upper = min(count - 1, nav.selection + 8)
            ForEach(lower...upper, id: \.self) { index in
                if let item = nav.item(at: index) {
                    let y = itemY + CGFloat(index - nav.selection) * Self.rowHeight
                    FlekXMBRow(item: item, focused: index == nav.selection)
                        .frame(width: width, height: Self.rowHeight, alignment: .leading)
                        .opacity(rowOpacity(y: y, ceiling: ceiling, height: height))
                        .offset(x: leading, y: y - Self.rowHeight / 2)
                }
            }
            .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .spring(response: 0.30, dampingFraction: 0.86), value: nav.selection)
        }
    }

    private func rowOpacity(y: CGFloat, ceiling: CGFloat, height: CGFloat) -> Double {
        if y < ceiling { return Double(max(0, 1 + (y - ceiling) / 28)) }
        let floorY = nav.hovering ? height * 0.54 : height - 104
        if y > floorY { return Double(max(0, 1 - (y - floorY) / 58)) }
        return 1
    }

    private func page(_ size: CGSize) -> some View {
        let count = nav.itemCount
        let visible = max(3, Int((size.height * 0.52) / 56))
        let start = min(max(0, nav.selection - visible / 2), max(0, count - visible))
        let shown = start..<min(count, start + visible)

        return VStack(alignment: .leading, spacing: 14) {
            Text(nav.title(of: nav.column))
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(.white)
            Text(pageSubtitle)
                .font(.system(size: 13))
                .foregroundStyle(.white.opacity(0.52))

            VStack(spacing: 2) {
                ForEach(shown, id: \.self) { index in
                    if let item = nav.item(at: index) {
                        FlekXMBRow(item: item, focused: index == nav.selection, compact: true)
                    }
                }
                if count > visible {
                    Text("\(nav.selection + 1) of \(count)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.45))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                        .padding(.top, 4)
                }
            }
            .padding(10)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(.white.opacity(0.10), lineWidth: 0.7))
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 26)
        .padding(.top, size.height * 0.16)
        .padding(.bottom, 100)
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    private var pageSubtitle: String {
        switch nav.column {
        case .httpServer: return "Vibe's local HTTP server, backed by FlekDeck Documents/www."
        case .tweaks: return "Vibe-style tweak state resolved through FlekDeck TweakLoader."
        case .appearance: return "The same Vibe appearance controls used by the FlekDeck home renderer."
        case .controllers: return "Connected controller capabilities and hardware tests."
        case .about: return "Host and runtime information."
        case .connection: return "Reachable local network interfaces."
        case .app: return "Application actions and current runtime state."
        default: return ""
        }
    }

    private func topBar(_ size: CGSize) -> some View {
        VStack {
            HStack(alignment: .firstTextBaseline) {
                HStack(spacing: 6) {
                    ForEach(Array(nav.path.enumerated()), id: \.offset) { index, component in
                        if index > 0 {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.35))
                        }
                        Text(component)
                            .font(.system(size: 11, weight: index == nav.path.count - 1 ? .semibold : .regular))
                            .foregroundStyle(index == nav.path.count - 1 ? .white : .white.opacity(0.48))
                            .lineLimit(1)
                    }
                }
                Spacer()
                if let pad = hub.pads.first {
                    HStack(spacing: 7) {
                        Image(systemName: pad.kind.symbol)
                        Text(pad.kind.shortTitle)
                        Text(pad.batteryText).foregroundStyle(.white.opacity(0.45))
                    }
                    .font(.system(size: 11, weight: .medium))
                }
                Text(Date(), style: .time)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .monospacedDigit()
                    .padding(.leading, 14)
            }
            .padding(.horizontal, 22)
            .padding(.top, 48)
            Spacer()
        }
        .frame(width: size.width, height: size.height)
    }

    @ViewBuilder
    private func hoverPanel(_ size: CGSize) -> some View {
        if nav.hovering, let info = nav.focused?.info {
            VStack {
                Spacer()
                FlekXMBInfoPanel(info: info, pinned: nav.hoverPinned)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 82)
            }
            .frame(width: size.width, height: size.height)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    private func footer(_ size: CGSize) -> some View {
        VStack {
            Spacer()
            HStack(spacing: 16) {
                legend("✕", "Enter")
                legend("○", nav.atRoot ? "Exit" : "Back")
                if nav.focused?.info != nil { legend("△", nav.hoverPinned ? "Close Info" : "Info") }
                if let title = nav.focused?.secondaryTitle { legend("□", title) }
                legend("L1/R1", nav.atRoot ? "Category" : "Back / Enter")
                legend("OPTIONS", "Refresh")
                Spacer()
                Text("FlekDeck XMB")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(nav.category.tint)
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 24)
        }
        .frame(width: size.width, height: size.height)
    }

    private func legend(_ button: String, _ action: String) -> some View {
        HStack(spacing: 5) {
            Text(button).font(.system(size: 10, weight: .bold)).foregroundStyle(.white)
            Text(action).font(.system(size: 10)).foregroundStyle(.white.opacity(0.48))
        }
    }
}

// MARK: - XMB rendering

private struct FlekXMBRow: View {
    let item: FlekXMBItem
    let focused: Bool
    var compact = false

    var body: some View {
        HStack(spacing: 12) {
            FlekXMBIconView(icon: item.icon, size: compact ? 34 : 42)
                .frame(width: compact ? 42 : 48)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: compact ? 15 : 17, weight: focused ? .semibold : .regular))
                    .foregroundStyle(item.dimmed ? .white.opacity(0.35) : (focused ? .white : .white.opacity(0.70)))
                    .lineLimit(1)
                if let subtitle = item.subtitle {
                    Text(subtitle)
                        .font(.system(size: compact ? 10 : 11))
                        .foregroundStyle(.white.opacity(focused ? 0.52 : 0.34))
                        .lineLimit(1)
                }
                if let progress = item.progress {
                    GeometryReader { geo in
                        Capsule().fill(.white.opacity(0.10))
                            .overlay(alignment: .leading) {
                                Capsule().fill(item.badgeTint).frame(width: geo.size.width * CGFloat(min(max(progress, 0), 1)))
                            }
                    }
                    .frame(height: 3)
                    .frame(maxWidth: 150)
                }
            }
            Spacer(minLength: 8)
            if let badge = item.badge {
                Text(badge)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(item.badgeTint)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(item.badgeTint.opacity(0.12), in: Capsule())
            }
            if focused && item.adjust != nil {
                Text("‹  ›").font(.system(size: 13, weight: .bold)).foregroundStyle(.white.opacity(0.52))
            }
        }
        .padding(.horizontal, compact ? 10 : 4)
        .background(focused && compact ? Color.white.opacity(0.07) : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .scaleEffect(focused && !compact ? 1.035 : 1, anchor: .leading)
        .shadow(color: focused ? .black.opacity(0.35) : .clear, radius: 8, y: 2)
    }
}

private struct FlekXMBIconView: View {
    let icon: FlekXMBIcon
    let size: CGFloat

    var body: some View {
        Group {
            switch icon {
            case .symbol(let name, let tint):
                ZStack {
                    RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
                        .fill(tint.opacity(0.15))
                    Image(systemName: name)
                        .font(.system(size: size * 0.48, weight: .medium))
                        .foregroundStyle(tint)
                }
            case .app(let app):
                Image(uiImage: app.appInfo.iconIsDarkIcon(false))
                    .resizable().scaledToFill()
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.22, style: .continuous))
            case .wallpaper(let wallpaper):
                wallpaper.thumbnail()
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.22, style: .continuous))
            }
        }
        .frame(width: size, height: size)
    }
}

private struct FlekXMBInfoPanel: View {
    let info: FlekXMBInfo
    let pinned: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            if let icon = info.icon {
                FlekXMBIconView(icon: icon, size: 58)
            }
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(info.title).font(.system(size: 17, weight: .semibold))
                    if pinned {
                        Image(systemName: "pin.fill").font(.system(size: 9)).foregroundStyle(info.accent)
                    }
                }
                if let subtitle = info.subtitle {
                    Text(subtitle).font(.system(size: 11)).foregroundStyle(.white.opacity(0.48))
                }
                ForEach(info.lines) { line in
                    HStack(spacing: 8) {
                        Text(line.label).foregroundStyle(.white.opacity(0.42)).frame(width: 105, alignment: .leading)
                        Text(line.value).foregroundStyle(.white.opacity(0.82)).lineLimit(1)
                    }
                    .font(.system(size: 11))
                }
                if let body = info.body {
                    Text(body).font(.system(size: 11)).foregroundStyle(.white.opacity(0.60)).lineLimit(3)
                }
                if let footnote = info.footnote {
                    Text(footnote).font(.system(size: 9, design: .monospaced)).foregroundStyle(.white.opacity(0.35)).lineLimit(1)
                }
            }
            Spacer()
        }
        .padding(16)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(info.accent.opacity(0.25), lineWidth: 0.8))
    }
}

private struct FlekXMBTestControls: View {
    let emit: (FlekControllerInput) -> Void

    var body: some View {
        VStack {
            Spacer()
            HStack(alignment: .bottom) {
                VStack(spacing: 6) {
                    testButton("↑", .up)
                    HStack(spacing: 6) {
                        testButton("←", .left)
                        testButton("↓", .down)
                        testButton("→", .right)
                    }
                }
                Spacer()
                HStack(spacing: 7) {
                    testButton("□", .square)
                    testButton("△", .triangle)
                    testButton("○", .circle)
                    testButton("✕", .cross, prominent: true)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 54)
        }
    }

    private func testButton(_ title: String, _ input: FlekControllerInput, prominent: Bool = false) -> some View {
        Button { emit(input) } label: {
            Text(title)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 40, height: 38)
                .background(prominent ? Color.cyan.opacity(0.30) : Color.white.opacity(0.09), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(.white.opacity(0.10), lineWidth: 0.6))
        }
        .buttonStyle(.plain)
    }
}

private struct FlekXMBWave: View {
    let tint: Color
    let reduceMotion: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30.0)) { timeline in
            let t = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                for band in 0..<3 {
                    var path = Path()
                    let base = size.height * (0.42 + CGFloat(band) * 0.08)
                    for x in stride(from: CGFloat(0), through: size.width, by: 8) {
                        let phase = Double(x / max(size.width, 1)) * 6.2 + t * (0.34 + Double(band) * 0.06)
                        let y = base + CGFloat(sin(phase)) * (22 + CGFloat(band) * 9)
                        if x == 0 { path.move(to: CGPoint(x: x, y: y)) }
                        else { path.addLine(to: CGPoint(x: x, y: y)) }
                    }
                    context.stroke(path, with: .color(tint.opacity(0.16 - Double(band) * 0.035)), lineWidth: 20 + CGFloat(band) * 8)
                }
            }
        }
        .blendMode(.plusLighter)
    }
}

private struct FlekXMBDust: View {
    let count: Int
    let reduceMotion: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 20.0)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                guard count > 0 else { return }
                for index in 0..<count {
                    let seed = Double(index + 1)
                    let xBase = (sin(seed * 12.9898) * 43758.5453).truncatingRemainder(dividingBy: 1)
                    let yBase = (sin(seed * 78.233) * 12345.6789).truncatingRemainder(dividingBy: 1)
                    let xNorm = abs(xBase)
                    let yNorm = abs(yBase)
                    let drift = reduceMotion ? 0 : sin(time * (0.08 + seed.truncatingRemainder(dividingBy: 4) * 0.01) + seed) * 0.04
                    let point = CGPoint(x: size.width * CGFloat(min(max(xNorm + drift, 0), 1)), y: size.height * CGFloat(yNorm))
                    let radius = CGFloat(0.8 + seed.truncatingRemainder(dividingBy: 2.2))
                    context.fill(Path(ellipseIn: CGRect(x: point.x, y: point.y, width: radius, height: radius)), with: .color(.white.opacity(0.17)))
                }
            }
        }
    }
}

private struct FlekXMBScanlines: View {
    var body: some View {
        Canvas { context, size in
            var y: CGFloat = 0
            while y < size.height {
                context.fill(Path(CGRect(x: 0, y: y, width: size.width, height: 0.55)), with: .color(.black.opacity(0.12)))
                y += 4
            }
        }
        .allowsHitTesting(false)
    }
}

private extension FlekWallpaper {
    var displayName: String {
        switch self {
        case .asset(let name): return name.replacingOccurrences(of: "FlekWallpaper", with: "Flek ").capitalized
        case .gradient(let name, _): return name.capitalized
        }
    }
}
