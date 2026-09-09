import CoreHaptics
import Foundation
import GameController
import SwiftUI
import UIKit

enum FlekControllerInput: Equatable, Hashable {
    case up, down, left, right
    case cross, circle, triangle, square
    case l1, r1, options, share, home
}

struct FlekGamePad: Identifiable, Equatable {
    enum Kind: Equatable {
        case dualSense, dualSenseEdge, dualShock4, extended

        var title: String {
            switch self {
            case .dualSense: return "DualSense Wireless Controller"
            case .dualSenseEdge: return "DualSense Edge Wireless Controller"
            case .dualShock4: return "DualShock 4 Wireless Controller"
            case .extended: return "Extended Gamepad"
            }
        }

        var shortTitle: String {
            switch self {
            case .dualSense: return "DualSense"
            case .dualSenseEdge: return "DualSense Edge"
            case .dualShock4: return "DualShock 4"
            case .extended: return "Gamepad"
            }
        }

        var isPlayStation: Bool { self != .extended }
        var symbol: String { isPlayStation ? "playstation.logo" : "gamecontroller.fill" }
    }

    let id: Int
    let kind: Kind
    let vendorName: String
    let battery: Float?
    let charging: Bool
    let hasLightBar: Bool
    let hasHaptics: Bool
    let hasAdaptiveTriggers: Bool

    var batteryText: String {
        guard let battery else { return charging ? "Charging" : "—" }
        let percent = Int((battery * 100).rounded())
        return charging ? "\(percent)% · charging" : "\(percent)%"
    }
}

/// FlekDeck-native port of VibeContainers' ControllerHub.
/// Hardware discovery/input stays independent from the app/runtime model so the
/// dashboard can drive FlekDeck's existing launch path rather than introducing
/// a second package or guest runtime.
@MainActor
final class FlekControllerHub: ObservableObject {
    static let shared = FlekControllerHub()

    @Published private(set) var pads: [FlekGamePad] = []

    var isConnected: Bool { !pads.isEmpty }
    var hasPlayStationPad: Bool { pads.contains { $0.kind.isPlayStation } }

    var sink: ((FlekControllerInput) -> Void)?
    var onHome: (() -> Void)?

    private var observers: [NSObjectProtocol] = []
    private var repeaters: [FlekControllerInput: Task<Void, Never>] = [:]
    private var stickDirection: [Int: FlekControllerInput?] = [:]
    private var haptics: [Int: CHHapticEngine] = [:]

    private init() {
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: .GCControllerDidConnect,
                                            object: nil, queue: .main) { [weak self] note in
            guard let controller = note.object as? GCController else { return }
            Task { @MainActor in self?.adopt(controller) }
        })
        observers.append(center.addObserver(forName: .GCControllerDidDisconnect,
                                            object: nil, queue: .main) { [weak self] note in
            guard let controller = note.object as? GCController else { return }
            Task { @MainActor in self?.drop(controller) }
        })

        GCController.controllers().forEach(adopt)
        GCController.startWirelessControllerDiscovery()
    }

    deinit {
        observers.forEach(NotificationCenter.default.removeObserver)
        cancelAllRepeats()
    }

    private static func key(_ controller: GCController) -> Int {
        ObjectIdentifier(controller).hashValue
    }

    private func adopt(_ controller: GCController) {
        guard controller.extendedGamepad != nil else { return }
        bind(controller)
        paint(controller)
        prepareHaptics(controller)
        refreshPads()
    }

    private func drop(_ controller: GCController) {
        let key = Self.key(controller)
        stickDirection[key] = nil
        haptics[key]?.stop()
        haptics[key] = nil
        cancelAllRepeats()
        refreshPads()
    }

    private func refreshPads() {
        pads = GCController.controllers().compactMap(Self.describe)
    }

    private static func describe(_ controller: GCController) -> FlekGamePad? {
        guard controller.extendedGamepad != nil else { return nil }
        let battery = controller.battery
        return FlekGamePad(
            id: key(controller),
            kind: kind(of: controller),
            vendorName: controller.vendorName ?? "Controller",
            battery: battery?.batteryLevel,
            charging: battery?.batteryState == .charging,
            hasLightBar: controller.light != nil,
            hasHaptics: controller.haptics != nil,
            hasAdaptiveTriggers: controller.physicalInputProfile is GCDualSenseGamepad
        )
    }

    private static func kind(of controller: GCController) -> FlekGamePad.Kind {
        let category = controller.productCategory
        if controller.physicalInputProfile is GCDualSenseGamepad {
            return category.localizedCaseInsensitiveContains("edge") ? .dualSenseEdge : .dualSense
        }
        if controller.physicalInputProfile is GCDualShockGamepad { return .dualShock4 }
        if category == GCProductCategoryDualSense { return .dualSense }
        if category == GCProductCategoryDualShock4 { return .dualShock4 }
        return .extended
    }

    private func bind(_ controller: GCController) {
        guard let pad = controller.extendedGamepad else { return }
        controller.handlerQueue = .main

        pad.dpad.up.pressedChangedHandler = repeatHandler(.up)
        pad.dpad.down.pressedChangedHandler = repeatHandler(.down)
        pad.dpad.left.pressedChangedHandler = repeatHandler(.left)
        pad.dpad.right.pressedChangedHandler = repeatHandler(.right)

        pad.buttonA.pressedChangedHandler = tapHandler(.cross)
        pad.buttonB.pressedChangedHandler = tapHandler(.circle)
        pad.buttonX.pressedChangedHandler = tapHandler(.square)
        pad.buttonY.pressedChangedHandler = tapHandler(.triangle)
        pad.leftShoulder.pressedChangedHandler = repeatHandler(.l1)
        pad.rightShoulder.pressedChangedHandler = repeatHandler(.r1)
        pad.buttonMenu.pressedChangedHandler = tapHandler(.options)
        pad.buttonOptions?.pressedChangedHandler = tapHandler(.share)
        pad.buttonHome?.pressedChangedHandler = { [weak self] _, _, pressed in
            guard pressed else { return }
            Task { @MainActor in self?.onHome?() }
        }

        let key = Self.key(controller)
        pad.leftThumbstick.valueChangedHandler = { [weak self] _, x, y in
            Task { @MainActor in self?.stickMoved(key: key, x: x, y: y) }
        }
    }

    private func repeatHandler(_ input: FlekControllerInput) -> GCControllerButtonValueChangedHandler {
        { [weak self] _, _, pressed in
            Task { @MainActor in
                guard let self else { return }
                if pressed { self.beginRepeating(input) }
                else { self.endRepeating(input) }
            }
        }
    }

    private func tapHandler(_ input: FlekControllerInput) -> GCControllerButtonValueChangedHandler {
        { [weak self] _, _, pressed in
            guard pressed else { return }
            Task { @MainActor in self?.sink?(input) }
        }
    }

    private func stickMoved(key: Int, x: Float, y: Float) {
        let armed: FlekControllerInput?
        if abs(x) > abs(y) {
            armed = abs(x) > 0.60 ? (x > 0 ? .right : .left) : nil
        } else {
            armed = abs(y) > 0.60 ? (y > 0 ? .up : .down) : nil
        }

        let current = stickDirection[key] ?? nil
        if armed == nil && max(abs(x), abs(y)) > 0.35 { return }
        guard armed != current else { return }
        if let current { endRepeating(current) }
        stickDirection[key] = armed
        if let armed { beginRepeating(armed) }
    }

    private func beginRepeating(_ input: FlekControllerInput) {
        repeaters[input]?.cancel()
        sink?(input)
        guard [.up, .down, .left, .right].contains(input) else { return }
        repeaters[input] = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 380_000_000)
            while !Task.isCancelled {
                guard let self else { return }
                await MainActor.run { self.sink?(input) }
                try? await Task.sleep(nanoseconds: 105_000_000)
            }
        }
    }

    private func endRepeating(_ input: FlekControllerInput) {
        repeaters[input]?.cancel()
        repeaters[input] = nil
    }

    private func cancelAllRepeats() {
        repeaters.values.forEach { $0.cancel() }
        repeaters.removeAll()
    }

    private func prepareHaptics(_ controller: GCController) {
        guard let engine = controller.haptics?.createEngine(withLocality: .default) else { return }
        engine.isAutoShutdownEnabled = true
        try? engine.start()
        haptics[Self.key(controller)] = engine
    }

    func rumble(intensity: Float = 0.60, sharpness: Float = 0.55, duration: TimeInterval = 0.07) {
        for engine in haptics.values {
            let event = CHHapticEvent(
                eventType: .hapticContinuous,
                parameters: [
                    CHHapticEventParameter(parameterID: .hapticIntensity, value: intensity),
                    CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness)
                ],
                relativeTime: 0,
                duration: duration
            )
            guard let pattern = try? CHHapticPattern(events: [event], parameters: []),
                  let player = try? engine.makePlayer(with: pattern) else { continue }
            try? engine.start()
            try? player.start(atTime: CHHapticTimeImmediate)
        }
    }

    func paintAll(_ color: UIColor = UIColor(red: 0.10, green: 0.74, blue: 1.0, alpha: 1)) {
        GCController.controllers().forEach { paint($0, color: color) }
    }

    private func paint(_ controller: GCController,
                       color: UIColor = UIColor(red: 0.10, green: 0.74, blue: 1.0, alpha: 1)) {
        guard let light = controller.light else { return }
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        light.color = GCColor(red: Float(r), green: Float(g), blue: Float(b))
    }
}

struct FlekControllerSettingsView: View {
    @StateObject private var hub = FlekControllerHub.shared
    @State private var dashboardPresented = false

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                hero
                controllerCard
                capabilityCard
                launchCard
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("Controller Mode").font(.headline) } }
        .fullScreenCover(isPresented: $dashboardPresented) {
            FlekControllerDashboardView()
        }
    }

    private var hero: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle().fill(Color.blue.opacity(0.14)).frame(width: 86, height: 86)
                Image(systemName: "gamecontroller.fill")
                    .font(.system(size: 36, weight: .semibold))
                    .foregroundStyle(.blue)
            }
            Text(hub.isConnected ? "Controller connected" : "Controller ready")
                .font(.title2.bold())
            Text("The VibeContainers controller dashboard is adapted to FlekDeck's installed apps and launch runtime. D-pad/thumbstick navigation, PlayStation face buttons, shoulders, battery, light bar and rumble are handled here without replacing FlekDeck's normal home screen.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(22)
        .frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 26, tint: 0.12)
    }

    private var controllerCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Controllers").font(.headline).padding(.bottom, 12)
            if hub.pads.isEmpty {
                HStack(spacing: 12) {
                    Image(systemName: "dot.radiowaves.left.and.right").foregroundStyle(.blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("No physical controller")
                        Text("Touch controls remain available in the dashboard.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.vertical, 10)
            } else {
                ForEach(Array(hub.pads.enumerated()), id: \.element.id) { index, pad in
                    HStack(spacing: 12) {
                        Image(systemName: pad.kind.symbol)
                            .font(.system(size: 22, weight: .semibold))
                            .frame(width: 34)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(pad.kind.title).font(.body.weight(.medium))
                            Text("\(pad.vendorName) · \(pad.batteryText)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding(.vertical, 10)
                    if index != hub.pads.count - 1 { Divider() }
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var capabilityCard: some View {
        let pad = hub.pads.first
        return VStack(alignment: .leading, spacing: 12) {
            Text("Capabilities").font(.headline)
            capability("Navigation", value: "D-pad + left stick")
            capability("Face buttons", value: "✕ ○ □ △")
            capability("Shoulders", value: "L1 / R1 category jump")
            capability("Rumble", value: pad?.hasHaptics == true ? "Available" : "Controller dependent")
            capability("Light bar", value: pad?.hasLightBar == true ? "Available" : "Controller dependent")
            capability("Adaptive triggers", value: pad?.hasAdaptiveTriggers == true ? "Detected" : "Controller dependent")
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var launchCard: some View {
        Button {
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            dashboardPresented = true
        } label: {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color.blue.opacity(0.13))
                    Image(systemName: "rectangle.landscape.rotate")
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundStyle(.blue)
                }
                .frame(width: 54, height: 54)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Open Controller Mode").font(.headline)
                    Text("Landscape dashboard with controller and touch navigation")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.forward").foregroundStyle(.secondary)
            }
            .padding(18)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private func capability(_ title: String, value: String) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(value).foregroundStyle(.secondary)
        }
        .font(.subheadline)
    }
}

struct FlekControllerDashboardView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var hub = FlekControllerHub.shared
    @State private var selected = 0
    @State private var launchError: String?
    @State private var showInfo = false

    private var apps: [LCAppModel] {
        sharedModel.apps.filter { !$0.uiIsHidden }
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                LinearGradient(colors: [
                    Color(red: 0.025, green: 0.055, blue: 0.11),
                    Color(red: 0.035, green: 0.16, blue: 0.24),
                    Color(red: 0.02, green: 0.03, blue: 0.07)
                ], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()

                Circle()
                    .fill(Color.cyan.opacity(0.12))
                    .frame(width: geo.size.width * 0.55)
                    .blur(radius: 60)
                    .offset(x: geo.size.width * 0.25, y: -geo.size.height * 0.18)

                VStack(spacing: 0) {
                    topBar
                    Spacer(minLength: 18)
                    dashboardContent
                    Spacer(minLength: 18)
                    touchControls
                }
                .padding(.horizontal, max(24, geo.safeAreaInsets.left + 16))
                .padding(.vertical, 18)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear(perform: enter)
        .onDisappear(perform: leave)
        .alert("Launch failed", isPresented: Binding(get: { launchError != nil }, set: { if !$0 { launchError = nil } })) {
            Button("OK", role: .cancel) { launchError = nil }
        } message: { Text(launchError ?? "") }
        .sheet(isPresented: $showInfo) {
            if let app = selectedApp {
                NavigationView {
                    Form {
                        Section("Application") {
                            LabeledContent("Name", value: app.displayName)
                            LabeledContent("Bundle ID", value: app.bundleIdentifier)
                            LabeledContent("Version", value: app.version)
                            LabeledContent("Tweaks", value: app.uiTweakFolder ?? "None")
                            LabeledContent("Launch", value: app.shouldLaunchInMultitaskMode ? "Parallel" : "Single")
                        }
                    }
                    .navigationTitle(app.displayName)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { showInfo = false } } }
                }
            }
        }
    }

    private var selectedApp: LCAppModel? {
        guard apps.indices.contains(selected) else { return nil }
        return apps[selected]
    }

    private var topBar: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text("FlekDeck").font(.title2.bold())
                Text("CONTROLLER MODE").font(.caption.bold()).tracking(1.5).foregroundStyle(.cyan)
            }
            Spacer()
            if let pad = hub.pads.first {
                HStack(spacing: 8) {
                    Image(systemName: pad.kind.symbol)
                    Text(pad.kind.shortTitle)
                    Text(pad.batteryText).foregroundStyle(.secondary)
                }
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(.thinMaterial, in: Capsule())
            }
            Button { dismiss() } label: {
                Label("Exit", systemImage: "xmark.circle.fill")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(.thinMaterial, in: Capsule())
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private var dashboardContent: some View {
        if apps.isEmpty {
            VStack(spacing: 14) {
                Image(systemName: "square.stack.3d.up.slash").font(.system(size: 46))
                Text("No apps installed").font(.title3.bold())
                Text("Install an app in FlekDeck and it will appear here automatically.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            VStack(spacing: 22) {
                Text("APPS").font(.caption.bold()).tracking(1.4).foregroundStyle(.secondary)
                HStack(spacing: 24) {
                    controllerButton("chevron.left", input: .left)
                    if let app = selectedApp {
                        VStack(spacing: 14) {
                            Image(uiImage: app.appInfo.iconIsDarkIcon(false))
                                .resizable().scaledToFill()
                                .frame(width: 112, height: 112)
                                .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
                                .shadow(color: .cyan.opacity(0.25), radius: 24)
                            Text(app.displayName).font(.title.bold()).lineLimit(1)
                            Text(app.bundleIdentifier)
                                .font(.caption.monospaced()).foregroundStyle(.secondary).lineLimit(1)
                            HStack(spacing: 10) {
                                Label("✕ Launch", systemImage: "play.fill")
                                Label("△ Info", systemImage: "info.circle")
                                Label("○ Exit", systemImage: "xmark")
                            }
                            .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: 420)
                        .padding(.vertical, 26).padding(.horizontal, 36)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 32, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 32, style: .continuous).stroke(Color.cyan.opacity(0.28), lineWidth: 1))
                    }
                    controllerButton("chevron.right", input: .right)
                }
                Text("\(selected + 1) / \(apps.count)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
    }

    private var touchControls: some View {
        HStack(spacing: 12) {
            touchButton("L1", .l1)
            touchButton("◀", .left)
            touchButton("▶", .right)
            touchButton("R1", .r1)
            Spacer()
            touchButton("△", .triangle)
            touchButton("□", .square)
            touchButton("○", .circle)
            touchButton("✕", .cross, prominent: true)
        }
    }

    private func controllerButton(_ symbol: String, input: FlekControllerInput) -> some View {
        Button { handle(input) } label: {
            Image(systemName: symbol)
                .font(.system(size: 22, weight: .bold))
                .frame(width: 52, height: 52)
                .background(.thinMaterial, in: Circle())
        }
        .buttonStyle(.plain)
    }

    private func touchButton(_ title: String, _ input: FlekControllerInput, prominent: Bool = false) -> some View {
        Button { handle(input) } label: {
            Text(title).font(.headline)
                .frame(minWidth: 44, minHeight: 42)
                .padding(.horizontal, title.count > 1 ? 7 : 0)
                .background(prominent ? Color.cyan.opacity(0.28) : Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(Color.white.opacity(0.10), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private func enter() {
        AppDelegate.orientationLock = .landscape
        _ = AppDelegate.applyOrientationLock()
        hub.paintAll()
        hub.sink = { input in handle(input) }
        hub.onHome = { dismiss() }
    }

    private func leave() {
        hub.sink = nil
        hub.onHome = nil
        AppDelegate.orientationLock = .portrait
        _ = AppDelegate.applyOrientationLock()
    }

    private func handle(_ input: FlekControllerInput) {
        UISelectionFeedbackGenerator().selectionChanged()
        hub.rumble(intensity: 0.35, sharpness: 0.6, duration: 0.045)
        guard !apps.isEmpty else {
            if input == .circle || input == .home { dismiss() }
            return
        }
        switch input {
        case .left, .up:
            selected = (selected - 1 + apps.count) % apps.count
        case .right, .down:
            selected = (selected + 1) % apps.count
        case .l1:
            selected = max(0, selected - 5)
        case .r1:
            selected = min(apps.count - 1, selected + 5)
        case .cross:
            launchSelected()
        case .triangle:
            showInfo = true
        case .circle, .home:
            dismiss()
        case .square:
            showInfo = true
        case .options, .share:
            break
        }
    }

    private func launchSelected() {
        guard let app = selectedApp else { return }
        Task {
            do { try await app.runApp() }
            catch { launchError = error.localizedDescription }
        }
    }
}
