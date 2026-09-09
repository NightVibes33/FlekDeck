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

/// FlekDeck adaptation of VibeContainers' controller hardware layer. It owns
/// GameController discovery/input only; navigation and guest launch remain on
/// FlekDeck's XMB adapter and LCAppModel runtime.
@MainActor
final class FlekControllerHub: ObservableObject {
    static let shared = FlekControllerHub()

    @Published private(set) var pads: [FlekGamePad] = []
    @Published private(set) var controllerUITestMode = false

    var isConnected: Bool { !pads.isEmpty }
    var hasPlayStationPad: Bool { pads.contains { $0.kind.isPlayStation } }

    /// The active controller surface installs these while it is on-screen.
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
        haptics.values.forEach { $0.stop() }
    }

    func enterControllerUITestMode() {
        controllerUITestMode = true
    }

    func leaveControllerUITestMode() {
        controllerUITestMode = false
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

        // Apple's generic A/B/X/Y profile maps exactly to Vibe's face-button
        // vocabulary: Cross/Circle/Square/Triangle.
        pad.buttonA.pressedChangedHandler = tapHandler(.cross)
        pad.buttonB.pressedChangedHandler = tapHandler(.circle)
        pad.buttonX.pressedChangedHandler = tapHandler(.square)
        pad.buttonY.pressedChangedHandler = tapHandler(.triangle)
        pad.leftShoulder.pressedChangedHandler = tapHandler(.l1)
        pad.rightShoulder.pressedChangedHandler = tapHandler(.r1)
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
        // Hysteresis: do not disarm until the stick is well inside its deadzone.
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

    func rumble(intensity: Float = 0.60,
                sharpness: Float = 0.55,
                duration: TimeInterval = 0.07) {
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

/// Settings front-end for Vibe's controller feature. Entry is always explicit:
/// discovering a controller never changes FlekDeck's startup UI.
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
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text("Controller Mode").font(.headline)
            }
        }
        .fullScreenCover(isPresented: $dashboardPresented, onDismiss: {
            hub.leaveControllerUITestMode()
        }) {
            // This is the actual Vibe XMB state machine adapted to FlekDeck's
            // app/runtime stores. The old one-card carousel was intentionally
            // removed; it never represented Controller Mode correctly.
            FlekXMBRootView()
        }
    }

    private var hero: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(FlekAppearanceStore.accent.color.opacity(0.14))
                    .frame(width: 86, height: 86)
                Image(systemName: "gamecontroller.fill")
                    .font(.system(size: 36, weight: .semibold))
                    .foregroundStyle(FlekAppearanceStore.accent.color)
            }
            Text(hub.isConnected ? "Controller connected" : "Controller ready")
                .font(.title2.bold())
            Text("Open FlekDeck's Vibe-style XMB dashboard. D-pad and left-stick navigation, face buttons, L1/R1, PS/Home exit, battery state, light bar and controller haptics are routed through the existing FlekDeck app runtime.")
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
                    Image(systemName: "dot.radiowaves.left.and.right")
                        .foregroundStyle(FlekAppearanceStore.accent.color)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("No physical controller")
                        Text("Touch test controls are available in Controller Mode.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                                .font(.caption)
                                .foregroundStyle(.secondary)
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
            capability("Shoulders", value: "L1 / R1")
            capability("Options / Share", value: "Mapped")
            capability("PS / Home", value: "Exit dashboard")
            capability("Rumble", value: pad?.hasHaptics == true ? "Available" : "Controller dependent")
            capability("Light bar", value: pad?.hasLightBar == true ? "Available" : "Controller dependent")
            capability("Adaptive triggers", value: pad?.hasAdaptiveTriggers == true ? "Detected" : "Controller dependent")
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var launchCard: some View {
        VStack(spacing: 10) {
            Button {
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                // Vibe's test mode is intentionally session-only. It gives a
                // complete touch control layer while testing without a pad.
                hub.enterControllerUITestMode()
                dashboardPresented = true
            } label: {
                HStack(spacing: 14) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(FlekAppearanceStore.accent.color.opacity(0.13))
                        Image(systemName: "rectangle.landscape.rotate")
                            .font(.system(size: 24, weight: .semibold))
                            .foregroundStyle(FlekAppearanceStore.accent.color)
                    }
                    .frame(width: 54, height: 54)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Open Controller Mode").font(.headline)
                        Text("Full XMB dashboard · landscape · touch test controls")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.forward").foregroundStyle(.secondary)
                }
                .padding(18)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if hub.isConnected {
                Divider().padding(.horizontal, 18)
                Button {
                    hub.leaveControllerUITestMode()
                    dashboardPresented = true
                } label: {
                    Label("Open with physical controls only", systemImage: "gamecontroller")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 18)
                        .padding(.bottom, 16)
                }
                .buttonStyle(.plain)
            }
        }
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
