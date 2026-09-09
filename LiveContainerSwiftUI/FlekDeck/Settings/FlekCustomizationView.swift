import SwiftUI

/// VibeContainers' Customization feature adapted to FlekDeck's existing visual
/// system. Wallpaper/photo and icon settings remain FlekDeck-native; Vibe's
/// accent, columns, labels, dock, transition, motes, scanlines and motion
/// controls are stored in the app group and consumed by the live renderers.
struct FlekCustomizationView: View {
    @AppStorage(FlekDeckKeys.wallpaperName, store: LCUtils.appGroupUserDefault)
    private var wallpaperDescriptor: String = FlekWallpaper.defaultDescriptor
    @AppStorage(FlekDeckKeys.wallpaperPhoto, store: LCUtils.appGroupUserDefault)
    private var wallpaperPhoto: String = ""
    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault)
    private var homeLayout: String = FlekHomeLayout.grid.rawValue
    @AppStorage(FlekDeckKeys.cardStyleGlass, store: LCUtils.appGroupUserDefault)
    private var glassCards = true

    @AppStorage(FlekDeckKeys.accentChoice, store: LCUtils.appGroupUserDefault)
    private var accentRaw = FlekAccentChoice.blue.rawValue
    @AppStorage(FlekDeckKeys.gridColumns, store: LCUtils.appGroupUserDefault)
    private var gridColumns = 3
    @AppStorage(FlekDeckKeys.showAppLabels, store: LCUtils.appGroupUserDefault)
    private var showLabels = true
    @AppStorage(FlekDeckKeys.hideDockBackground, store: LCUtils.appGroupUserDefault)
    private var hideDockBackground = false
    @AppStorage(FlekDeckKeys.pageTransition, store: LCUtils.appGroupUserDefault)
    private var pageTransition = FlekPageTransition.slide.rawValue
    @AppStorage(FlekDeckKeys.reduceMotion, store: LCUtils.appGroupUserDefault)
    private var reduceMotion = false
    @AppStorage(FlekDeckKeys.showMotes, store: LCUtils.appGroupUserDefault)
    private var showMotes = true
    @AppStorage(FlekDeckKeys.moteDensity, store: LCUtils.appGroupUserDefault)
    private var moteDensity = 0.5
    @AppStorage(FlekDeckKeys.scanlines, store: LCUtils.appGroupUserDefault)
    private var scanlines = true

    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault)
    private var dynamicColors = true
    @AppStorage("darkModeIcon", store: LCUtils.appGroupUserDefault)
    private var darkModeIcon = false
    @AppStorage("LCFrameShortcutIcons", store: LCUtils.appGroupUserDefault)
    private var frameShortcutIcons = false

    private var accent: FlekAccentChoice { FlekAccentChoice.resolved(accentRaw) }

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                hero
                wallpaperCard
                accentCard
                homeCard
                effectsCard
                iconCard
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text("Customization").font(.headline)
            }
        }
        .tint(accent.color)
        .onAppear {
            // @AppStorage's defaults do not write until changed. Keep the
            // established Flek layout on older installs while still reflecting
            // the effective values in this page.
            if LCUtils.appGroupUserDefault.object(forKey: FlekDeckKeys.gridColumns) == nil {
                gridColumns = FlekAppearanceStore.gridColumns
            }
        }
        .onChange(of: accentRaw) { _ in changed() }
        .onChange(of: gridColumns) { _ in changed() }
        .onChange(of: showLabels) { _ in changed() }
        .onChange(of: hideDockBackground) { _ in changed() }
        .onChange(of: pageTransition) { _ in changed() }
        .onChange(of: reduceMotion) { _ in changed() }
        .onChange(of: showMotes) { _ in changed() }
        .onChange(of: moteDensity) { _ in changed() }
        .onChange(of: scanlines) { _ in changed() }
    }

    private var hero: some View {
        HStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(accent.color.opacity(0.14))
                Image(systemName: "paintbrush.pointed.fill")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(accent.color)
            }
            .frame(width: 66, height: 66)
            VStack(alignment: .leading, spacing: 4) {
                Text("Customize FlekDeck").font(.title2.bold())
                Text("Vibe's live appearance controls, adapted to FlekDeck's SpringBoard and wallpaper renderer rather than duplicated beside them.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 25, tint: 0.10)
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
                    Text("Wallpaper & Layout").font(.headline).foregroundStyle(.primary)
                    Text("FlekDeck wallpaper collection, Photos wallpaper, Grid/List layout and icon appearance")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
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

    private var accentCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Accent").font(.headline)
                Text("Used by Controller Mode and FlekDeck controls that follow the application tint.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            HStack(spacing: 0) {
                ForEach(FlekAccentChoice.allCases) { choice in
                    Button {
                        accentRaw = choice.rawValue
                        UISelectionFeedbackGenerator().selectionChanged()
                    } label: {
                        ZStack {
                            Circle().fill(choice.color).frame(width: 32, height: 32)
                            if accentRaw == choice.rawValue {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundStyle(.white)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .accessibilityLabel(choice.title)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var homeCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Home Screen").font(.headline).padding(.bottom, 12)

            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Grid Columns")
                    Text("Page capacity and drag targets update with the same layout math.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Stepper(value: $gridColumns, in: 2...6) {
                    Text("\(gridColumns)")
                        .font(.body.monospacedDigit())
                        .frame(minWidth: 20)
                }
                .labelsHidden()
                Text("\(gridColumns)").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
            }
            .padding(.vertical, 10)

            Divider()
            toggleRow("Show App Labels",
                      detail: "Hide names without changing icon positions or page capacity.",
                      binding: $showLabels)
            Divider()
            toggleRow("Hide Dock Background",
                      detail: "Remove FlekDeck's bottom wallpaper/dock blur treatment.",
                      binding: $hideDockBackground)
            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Text("Page Transition")
                Picker("Page Transition", selection: $pageTransition) {
                    ForEach(FlekPageTransition.allCases) { transition in
                        Text(transition.title).tag(transition.rawValue)
                    }
                }
                .pickerStyle(.segmented)
            }
            .padding(.vertical, 10)

            Divider()
            toggleRow("Reduce Motion",
                      detail: "Freezes motes and shortens FlekDeck/XMB motion effects.",
                      binding: $reduceMotion)
            Divider()
            toggleRow("Liquid Glass App Cards",
                      detail: "Keep FlekDeck's iOS 26 glass cards or its frosted fallback.",
                      binding: $glassCards)
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var effectsCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Wallpaper Effects").font(.headline).padding(.bottom, 12)
            toggleRow("Motes",
                      detail: "Vibe-style drifting particles layered over the selected Flek wallpaper.",
                      binding: $showMotes)
            if showMotes {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Mote Density")
                        Spacer()
                        Text("\(Int(moteDensity * 100))%")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    Slider(value: $moteDensity, in: 0...1)
                }
                .padding(.vertical, 10)
            }
            Divider()
            toggleRow("Scanlines",
                      detail: "Adds Vibe's subtle scanline texture above the wallpaper.",
                      binding: $scanlines)
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private var iconCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("App Icons").font(.headline).padding(.bottom, 12)
            toggleRow("Dynamic Colors",
                      detail: "Use FlekDeck's dynamic icon treatment.",
                      binding: $dynamicColors)
            if #available(iOS 18.0, *) {
                Divider()
                toggleRow("Dark Mode Icons",
                          detail: "Use dark variants when an app provides them.",
                          binding: $darkModeIcon)
            }
            Divider()
            toggleRow("Frame Shortcut Icons",
                      detail: "Frame generated shortcut artwork consistently with installed apps.",
                      binding: $frameShortcutIcons)
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
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

    @MainActor
    private func changed() {
        FlekAppearanceStore.postChanged()
        UISelectionFeedbackGenerator().selectionChanged()
    }
}
