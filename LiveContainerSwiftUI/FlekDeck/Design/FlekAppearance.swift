import SwiftUI
import UIKit

/// VibeContainers appearance controls expressed as FlekDeck app-group state.
/// Existing wallpaper/icon settings remain authoritative; these are the extra
/// controls Vibe exposes and the active Flek renderers consume.
enum FlekAccentChoice: Int, CaseIterable, Identifiable {
    case blue = 0, indigo, green, orange, purple, pink

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .blue: return "Blue"
        case .indigo: return "Indigo"
        case .green: return "Green"
        case .orange: return "Orange"
        case .purple: return "Purple"
        case .pink: return "Pink"
        }
    }

    var color: Color {
        switch self {
        case .blue: return Color(red: 0.00, green: 0.46, blue: 1.00)
        case .indigo: return .indigo
        case .green: return .green
        case .orange: return .orange
        case .purple: return .purple
        case .pink: return .pink
        }
    }

    var uiColor: UIColor { UIColor(color) }

    static func resolved(_ raw: Int) -> FlekAccentChoice {
        FlekAccentChoice(rawValue: raw) ?? .blue
    }
}

enum FlekPageTransition: String, CaseIterable, Identifiable {
    case slide
    case fade
    case scale

    var id: String { rawValue }
    var title: String {
        switch self {
        case .slide: return "Slide"
        case .fade: return "Crossfade"
        case .scale: return "Scale"
        }
    }
}

enum FlekAppearanceStore {
    static let defaults = LCUtils.appGroupUserDefault

    static var accent: FlekAccentChoice {
        FlekAccentChoice.resolved(defaults.integer(forKey: FlekDeckKeys.accentChoice))
    }

    static var gridColumnsOverride: Int? {
        guard defaults.object(forKey: FlekDeckKeys.gridColumns) != nil else { return nil }
        return gridColumns
    }

    static var gridColumns: Int {
        let value = defaults.integer(forKey: FlekDeckKeys.gridColumns)
        return value == 0 ? 3 : min(max(value, 2), 6)
    }

    static var showLabels: Bool {
        guard defaults.object(forKey: FlekDeckKeys.showAppLabels) != nil else { return true }
        return defaults.bool(forKey: FlekDeckKeys.showAppLabels)
    }

    static var hideDockBackground: Bool {
        defaults.bool(forKey: FlekDeckKeys.hideDockBackground)
    }

    static var showMotes: Bool {
        guard defaults.object(forKey: FlekDeckKeys.showMotes) != nil else { return true }
        return defaults.bool(forKey: FlekDeckKeys.showMotes)
    }

    static var moteDensity: Double {
        guard defaults.object(forKey: FlekDeckKeys.moteDensity) != nil else { return 0.5 }
        return min(max(defaults.double(forKey: FlekDeckKeys.moteDensity), 0), 1)
    }

    static var scanlines: Bool {
        guard defaults.object(forKey: FlekDeckKeys.scanlines) != nil else { return true }
        return defaults.bool(forKey: FlekDeckKeys.scanlines)
    }

    static var reduceMotion: Bool {
        defaults.bool(forKey: FlekDeckKeys.reduceMotion)
    }

    static var pageTransition: FlekPageTransition {
        let raw = defaults.string(forKey: FlekDeckKeys.pageTransition) ?? FlekPageTransition.slide.rawValue
        return FlekPageTransition(rawValue: raw) ?? .slide
    }

    static var moteCount: Int { showMotes ? Int(6 + moteDensity * 30) : 0 }

    /// Broadcast and immediately update the active UIKit springboard. Column
    /// changes therefore repaginate through the same `itemsPerPage` math used by
    /// drag/reorder rather than waiting for a relaunch.
    @MainActor
    static func postChanged() {
        UIView.appearance().tintColor = accent.uiColor
        for case let scene as UIWindowScene in UIApplication.shared.connectedScenes {
            scene.windows.forEach { $0.tintColor = accent.uiColor }
        }

        if let springboard = LCSpringboardViewController.current {
            springboard.outerCollectionView.collectionViewLayout.invalidateLayout()
            for case let pageCell as LCSpringboardPageCell in springboard.outerCollectionView.visibleCells {
                pageCell.collectionView.collectionViewLayout.invalidateLayout()
                pageCell.setNeedsLayout()
            }
            springboard.view.setNeedsLayout()
            springboard.view.layoutIfNeeded()
            _ = springboard.refreshVisibleItems()
        }
        NotificationCenter.default.post(name: .flekAppearanceChanged, object: nil)
    }
}

extension Notification.Name {
    static let flekAppearanceChanged = Notification.Name("FlekAppearanceChanged")
}

/// Vibe's dust/motes + scanline treatment, adapted as a lightweight overlay
/// above FlekDeck's existing wallpaper. This is intentionally visual-only and
/// never replaces the selected wallpaper/photo.
struct FlekAtmosphereOverlay: View {
    @AppStorage(FlekDeckKeys.accentChoice, store: LCUtils.appGroupUserDefault)
    private var accentRaw = FlekAccentChoice.blue.rawValue
    @AppStorage(FlekDeckKeys.showMotes, store: LCUtils.appGroupUserDefault)
    private var showMotes = true
    @AppStorage(FlekDeckKeys.moteDensity, store: LCUtils.appGroupUserDefault)
    private var moteDensity = 0.5
    @AppStorage(FlekDeckKeys.scanlines, store: LCUtils.appGroupUserDefault)
    private var scanlines = true
    @AppStorage(FlekDeckKeys.reduceMotion, store: LCUtils.appGroupUserDefault)
    private var reduceMotion = false

    private var accent: Color { FlekAccentChoice.resolved(accentRaw).color }
    private var count: Int { showMotes ? Int(6 + min(max(moteDensity, 0), 1) * 30) : 0 }

    var body: some View {
        ZStack {
            if showMotes && count > 0 {
                TimelineView(.animation(minimumInterval: 1.0 / 20.0, paused: reduceMotion)) { timeline in
                    Canvas { context, size in
                        let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
                        for index in 0..<count {
                            let seed = Double(index + 1)
                            let baseX = fract(sin(seed * 12.9898) * 43758.5453)
                            let baseY = fract(sin(seed * 78.233) * 12345.6789)
                            let speed = 0.004 + fract(sin(seed * 19.31) * 991.7) * 0.010
                            let x = fract(baseX + time * speed) * size.width
                            let y = fract(baseY - time * speed * 0.55) * size.height
                            let radius = 0.7 + fract(sin(seed * 44.17) * 812.2) * 1.6
                            let opacity = 0.06 + fract(sin(seed * 9.71) * 388.4) * 0.12
                            let rect = CGRect(x: x - radius, y: y - radius,
                                              width: radius * 2, height: radius * 2)
                            context.fill(Path(ellipseIn: rect), with: .color(accent.opacity(opacity)))
                        }
                    }
                }
            }

            if scanlines {
                Canvas { context, size in
                    var path = Path()
                    var y: CGFloat = 1
                    while y < size.height {
                        path.move(to: CGPoint(x: 0, y: y))
                        path.addLine(to: CGPoint(x: size.width, y: y))
                        y += 4
                    }
                    context.stroke(path, with: .color(.black.opacity(0.055)), lineWidth: 0.5)
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func fract(_ value: Double) -> Double { value - floor(value) }
}
