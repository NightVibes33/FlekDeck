import SwiftUI
import UIKit

/// VibeContainers appearance controls expressed as FlekDeck app-group state.
/// Existing FlekDeck wallpaper/icon state remains authoritative; these are the
/// additional controls Vibe exposes and the FlekDeck renderers now consume.
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

    static var moteCount: Int {
        showMotes ? Int(6 + moteDensity * 30) : 0
    }

    static func postChanged() {
        NotificationCenter.default.post(name: .flekAppearanceChanged, object: nil)
    }
}

extension Notification.Name {
    static let flekAppearanceChanged = Notification.Name("FlekAppearanceChanged")
}
