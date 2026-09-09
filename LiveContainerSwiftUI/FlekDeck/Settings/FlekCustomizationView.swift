import SwiftUI

/// FlekDeck adaptation of VibeContainers' Customization page.
/// It intentionally writes the state FlekDeck already renders instead of
/// creating a second Appearance singleton whose values would fight the existing
/// wallpaper, icon and springboard preferences.
struct FlekCustomizationView: View {
    @AppStorage(FlekDeckKeys.wallpaperName, store: LCUtils.appGroupUserDefault)
    private var wallpaperDescriptor: String = FlekWallpaper.defaultDescriptor
    @AppStorage(FlekDeckKeys.wallpaperPhoto, store: LCUtils.appGroupUserDefault)
    private var wallpaperPhoto: String = ""
    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault)
    private var homeLayout: String = FlekHomeLayout.grid.rawValue
    @AppStorage(FlekDeckKeys.cardStyleGlass, store: LCUtils.appGroupUserDefault)
    private var glassCards = true
    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault)
    private var dynamicColors = true
    @AppStorage("darkModeIcon", store: LCUtils.appGroupUserDefault)
    private var darkModeIcon = false
    @AppStorage("LCFrameShortcutIcons", store: LCUtils.appGroupUserDefault)
    private var frameShortcutIcons = false
    @AppStorage("LCMultitaskHapticsLevel", store: LCUtils.appGroupUserDefault)
    private var multitaskHapticsLevel = 1

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                hero
                wallpaperCard
                homeCard
                appearanceCard
                feedbackCard
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("Customization").font(.headline) } }
    }

    private var hero: some View {
        HStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.purple.opacity(0.14))
                Image(systemName: "paintbrush.pointed.fill")
                    .font(.system(size: 28, weight: .semibold)).foregroundStyle(.purple)
            }
            .frame(width: 66, height: 66)
            VStack(alignment: .leading, spacing: 4) {
                Text("Make FlekDeck yours").font(.title2.bold())
                Text("VibeContainers' customization concept, wired into FlekDeck's real wallpaper, home-layout, icon and glass state instead of a duplicate theme engine.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(18).flekGlassCard(cornerRadius: 25, tint: 0.10)
    }

    private var wallpaperCard: some View {
        NavigationLink {
            FlekPersonalizationView()
        } label: {
            HStack(spacing: 16) {
                Group {
                    if !wallpaperPhoto.isEmpty,
                       let image = FlekWallpaperStore.loadPhoto(named: wallpaperPhoto,
                                                                maxPixel: FlekWallpaperImages.thumbnailMaxPixel) {
                        Image(uiImage: image).resizable().scaledToFill()
                    } else {
                        FlekWallpaper.from(descriptor: wallpaperDescriptor).thumbnail()
                    }
                }
                .frame(width: 62, height: 96)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("Wallpaper & Home Screen").font(.headline).foregroundStyle(.primary)
                    Text("Wallpaper collection, Photos wallpaper and Grid/List layout")
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.leading)
                }
                Spacer()
                Image(systemName: "chevron.forward").font(.caption.bold()).foregroundStyle(.tertiary)
            }
            .padding(16).contentShape(Rectangle())
        }
        .buttonStyle(.plain).flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var homeCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Home Screen").font(.headline)
            HStack(spacing: 10) {
                layoutPill(.grid, title: "Grid", symbol: "square.grid.3x3.fill")
                layoutPill(.list, title: "List", symbol: "list.bullet")
            }
            Divider()
            Toggle("Liquid Glass app cards", isOn: $glassCards)
            Text("On iOS 26+ this uses the system glass effect. Earlier systems keep FlekDeck's frosted fallback.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(18).flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var appearanceCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("App Icons").font(.headline).padding(.bottom, 12)
            toggleRow("Dynamic colors", detail: "Follow FlekDeck's dynamic icon treatment.", binding: $dynamicColors)
            Divider()
            if #available(iOS 18.0, *) {
                toggleRow("Dark mode icons", detail: "Use dark variants when an app provides them.", binding: $darkModeIcon)
                Divider()
            }
            toggleRow("Frame shortcut icons", detail: "Keep shortcut artwork visually consistent with installed apps.", binding: $frameShortcutIcons)
        }
        .padding(18).flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var feedbackCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Switcher haptics").font(.headline)
                Spacer()
                Text(hapticName).font(.caption).foregroundStyle(.secondary)
            }
            Slider(value: Binding(
                get: { Double(multitaskHapticsLevel) },
                set: { value in
                    let level = min(max(Int(value.rounded()), 0), 3)
                    guard level != multitaskHapticsLevel else { return }
                    multitaskHapticsLevel = level
                    if #available(iOS 16.0, *) { MultitaskDockManager.playHaptic(level: level) }
                }
            ), in: 0...3, step: 1)
            Text("This is the same persisted setting used by FlekDeck's multitask controls, exposed here because feedback is part of the app's feel.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(18).flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private func layoutPill(_ layout: FlekHomeLayout, title: String, symbol: String) -> some View {
        let selected = homeLayout == layout.rawValue
        return Button {
            homeLayout = layout.rawValue
            UISelectionFeedbackGenerator().selectionChanged()
        } label: {
            HStack(spacing: 8) {
                Image(systemName: symbol)
                Text(title).font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(selected ? Color.white : Color.primary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(selected ? Color.blue : Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func toggleRow(_ title: String, detail: String, binding: Binding<Bool>) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Toggle("", isOn: binding).labelsHidden()
        }
        .padding(.vertical, 10)
    }

    private var hapticName: String {
        switch multitaskHapticsLevel {
        case 1: return "Light"
        case 2: return "Medium"
        case 3: return "Strong"
        default: return "Off"
        }
    }
}
