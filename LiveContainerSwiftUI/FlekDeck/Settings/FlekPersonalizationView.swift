//
//  FlekPersonalizationView.swift
//  LiveContainerSwiftUI
//
//  New "Personalization" settings page (not present in LiveContainer). Lets the
//  user pick a home screen wallpaper (built-in collection or a photo) and choose
//  the home screen layout (grid of cards or a list).
//

import SwiftUI
import PhotosUI

struct FlekPersonalizationView: View {
    @AppStorage("LCBetaBannerOverride", store: LCUtils.appGroupUserDefault) private var betaBannerOverride: Int = 0
    // 0 = auto (show on beta), 1 = force on, 2 = force off

    @AppStorage(FlekDeckKeys.wallpaperName, store: LCUtils.appGroupUserDefault)
    private var wallpaperDescriptor: String = FlekWallpaper.defaultDescriptor
    @AppStorage(FlekDeckKeys.wallpaperPhoto, store: LCUtils.appGroupUserDefault)
    private var wallpaperPhoto: String = ""
    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault)
    private var homeLayout: String = FlekHomeLayout.grid.rawValue

    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault) private var dynamicColors = true
    @AppStorage("darkModeIcon", store: LCUtils.appGroupUserDefault) private var darkModeIcon = false
    @AppStorage("LCFrameShortcutIcons", store: LCUtils.appGroupUserDefault) private var frameShortIcon = false
    @AppStorage(FlekDeckKeys.showAppCardBackgrounds, store: LCUtils.appGroupUserDefault) private var showAppCardBackgrounds = true
    @AppStorage("FlekDeckUseRealSpringBoard", store: LCUtils.appGroupUserDefault) private var procursusRuntimeEnabled = true

    @State private var showCollection = false
    @State private var showPhotoPicker = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // MARK: Wallpapers
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("lc.flek.wallpapers".loc)

                    HStack(alignment: .top, spacing: 8) {
                        currentPreview
                        VStack(spacing: 8) {
                            actionTile(title: "lc.flek.chooseFromCollection".loc, systemImage: "rectangle.grid.3x2.fill") {
                                showCollection = true
                            }
                            actionTile(title: "lc.flek.chooseFromPhotos".loc, systemImage: FlekSymbol.addPhoto) {
                                showPhotoPicker = true
                            }
                        }
                        .frame(height: 226)
                    }
                    .padding(16)
                    .background(card)
                }

                // MARK: Home Screen Layout
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("lc.flek.homeScreenLayout".loc)

                    HStack(spacing: 8) {
                        layoutOption(.grid, title: "lc.flek.layoutGrid".loc)
                        layoutOption(.list, title: "lc.flek.layoutList".loc)
                    }
                    .padding(16)
                    .background(card)
                }

                // MARK: Procursus virtual jailbreak (backend only)
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("Procursus Virtual Jailbreak")
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Enable Procursus Runtime", isOn: $procursusRuntimeEnabled)
                        Text("Starts the installed ROM's actual virtual SpringBoard and userspace services behind FlekDeck. Your Home Screen, dock, Installer and app layout stay unchanged. Restart FlekDeck to apply.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(16)
                    .background(card)
                }
                .onChange(of: procursusRuntimeEnabled) { enabled in
                    if enabled {
                        // An explicit retry is required after a ROM startup crash.
                        UserDefaults.standard.set(false, forKey: "FlekDeckGuestSpringBoardCrashGuard")
                    }
                }

                // MARK: App Icons
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("lc.flek.appIcons".loc)
                    VStack(spacing: 0) {
                        Toggle("lc.settings.dynamicColors".loc, isOn: $dynamicColors)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                        if #available(iOS 18.0, *) {
                            Divider().padding(.leading, 16)
                            Toggle("lc.settings.darkModeIcon".loc, isOn: $darkModeIcon)
                                .padding(.horizontal, 16).padding(.vertical, 12)
                        }
                        Divider().padding(.leading, 16)
                        Toggle("lc.settings.FrameIcon".loc, isOn: $frameShortIcon)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                        Divider().padding(.leading, 16)
                        Toggle("Show App Card Backgrounds", isOn: $showAppCardBackgrounds)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    .background(card)
                }

            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text("lc.flek.personalization".loc)
                    .font(.headline)
                    .onTapGesture(count: 10) {
                        betaBannerOverride = (betaBannerOverride + 1) % 3
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    }
            }
        }
        .sheet(isPresented: $showCollection) {
            FlekWallpaperCollectionView(selectedDescriptor: $wallpaperDescriptor, photoWallpaper: $wallpaperPhoto)
        }
        .sheet(isPresented: $showPhotoPicker) {
            FlekPhotoPicker { image in
                if let name = FlekWallpaperStore.savePhoto(image) {
                    wallpaperPhoto = name
                }
            }
        }
    }

    // MARK: Pieces

    /// The phone's screen corner radius (private UIScreen value), clamped into the
    /// slider's range, used as the default so the bar starts matching the device.
    private static var deviceCornerRadiusDefault: Double {
        let r = (UIScreen.main.value(forKey: "_displayCornerRadius") as? CGFloat) ?? 0
        let v = r > 0 ? Double(r) : 39
        return min(max(v, 10), 60)
    }

    private static let flekBlue = Color(red: 0/255, green: 117/255, blue: 255/255) // #0075ff
    private static let tileFill = Color(red: 136/255, green: 136/255, blue: 136/255).opacity(0.15)

    private var currentPreview: some View {
        ZStack(alignment: .top) {
            Group {
                if !wallpaperPhoto.isEmpty,
                   let img = FlekWallpaperStore.loadPhoto(named: wallpaperPhoto,
                                                          maxPixel: FlekWallpaperImages.thumbnailMaxPixel) {
                    Image(uiImage: img).resizable().scaledToFill()
                } else {
                    FlekWallpaper.from(descriptor: wallpaperDescriptor).thumbnail()
                }
            }
            .frame(width: 110, height: 226)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))

            Text("lc.flek.current".loc)
                .font(.system(size: 14))
                .foregroundStyle(.white.opacity(0.8))
                .padding(.horizontal, 16).frame(height: 21)
                .background(Capsule().fill(Color.black.opacity(0.2)))
                .padding(.top, 8)
        }
    }

    private func actionTile(title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 16) {
                Image(systemName: systemImage).font(.system(size: 28))
                Text(title).font(.system(size: 14)).multilineTextAlignment(.center)
            }
            .foregroundStyle(Self.flekBlue)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.horizontal, 24)
            .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Self.tileFill))
        }
        .buttonStyle(.plain)
    }

    private func layoutOption(_ layout: FlekHomeLayout, title: String) -> some View {
        let selected = homeLayout == layout.rawValue
        return Button {
            homeLayout = layout.rawValue
        } label: {
            VStack(spacing: 16) {
                LayoutGlyph(layout: layout, selected: selected)
                    .frame(width: 59, height: 100)
                if selected {
                    Text(title)
                        .font(.system(size: 14))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16).padding(.vertical, 6)
                        .background(Capsule().fill(Self.flekBlue))
                } else {
                    Text(title)
                        .font(.system(size: 14))
                        .foregroundStyle(.primary)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 32).padding(.vertical, 16)
            .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Self.tileFill))
        }
        .buttonStyle(.plain)
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text).font(.system(size: 20, weight: .bold)).foregroundStyle(.primary)
    }

    private var card: some View {
        RoundedRectangle(cornerRadius: 26, style: .continuous).fill(Color(.secondarySystemGroupedBackground))
    }
}

/// Small phone illustration showing a grid or list arrangement using SF Symbols.
private struct LayoutGlyph: View {
    let layout: FlekHomeLayout
    let selected: Bool

    var body: some View {
        let tint = selected ? Color.accentColor : Color.secondary
        ZStack {
            Image(systemName: FlekSymbol.device)
                .font(.system(size: 80, weight: .thin))
                .foregroundStyle(tint)

            Group {
                if layout == .grid {
                    Image(systemName: "square.grid.4x3.fill")
                        .font(.system(size: 24))
                        .rotationEffect(.degrees(90))
                } else {
                    Image(systemName: "line.3.horizontal")
                        .font(.system(size: 24, weight: .bold))
                }
            }
            .foregroundStyle(tint)
            .offset(y: -2)
        }
    }
}

/// PHPicker wrapper that returns a single chosen image.
struct FlekPhotoPicker: UIViewControllerRepresentable {
    var onPick: (UIImage) -> Void

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration()
        config.filter = .images
        config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let parent: FlekPhotoPicker
        init(_ parent: FlekPhotoPicker) { self.parent = parent }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            guard let provider = results.first?.itemProvider, provider.canLoadObject(ofClass: UIImage.self) else { return }
            provider.loadObject(ofClass: UIImage.self) { [weak self] obj, _ in
                guard let img = obj as? UIImage else { return }
                DispatchQueue.main.async { self?.parent.onPick(img) }
            }
        }
    }
}


// The original Home Screen stays unchanged; this is a genuine guest-application
// inventory inside FlekDeck's existing Settings navigation. Sileo, NewTerm and
// TweakSettings appear only if the ROM actually installed/registered them.
private struct FlekProcursusGuestEntry: Identifiable {
    let id: String
    let title: String
    let icon: UIImage?
}

struct FlekProcursusGuestAppsView: View {
    @State private var apps: [FlekProcursusGuestEntry] = []
    @State private var loading = false
    @State private var launchError: String?
    @State private var hasLoaded = false

    var body: some View {
        List {
            Section {
                Label("Procursus Jailed is bundled with FlekDeck", systemImage: "shippingbox.fill")
                Text("On first launch the included ROM is installed automatically. No Files import, bootloader flash, or runtime download is needed. ROM code signing still uses the P12 configured in FlekDeck.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section {
                if loading && !hasLoaded {
                    ProgressView("Checking virtual application registry")
                } else if apps.isEmpty {
                    Text("No registered Procursus apps. The ROM must finish bootstrapping, and Sileo must install successfully before it can appear here.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(apps) { app in
                        Button {
                            launch(app)
                        } label: {
                            HStack(spacing: 12) {
                                if let icon = app.icon {
                                    Image(uiImage: icon)
                                        .resizable()
                                        .scaledToFit()
                                        .frame(width: 42, height: 42)
                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                } else {
                                    Image(systemName: "app")
                                        .frame(width: 42, height: 42)
                                }
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(app.title).foregroundStyle(.primary)
                                    Text(app.id).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "arrow.up.forward.app")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            } header: {
                Text("Installed virtual applications")
            } footer: {
                Text("Entries come directly from Nyxian's LDEApplicationWorkspace. This does not list iOS apps or invent uninstalled jailbreak packages.")
            }
        }
        .navigationTitle("Procursus Apps")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    refresh()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(loading)
            }
        }
        .onAppear { refresh() }
        .alert("Virtual app launch failed",
               isPresented: Binding(
                    get: { launchError != nil },
                    set: { if !$0 { launchError = nil } }
               )) {
            Button("OK", role: .cancel) { launchError = nil }
        } message: {
            Text(launchError ?? "")
        }
    }

    private func refresh() {
        guard !loading else { return }
        loading = true
        DispatchQueue.global(qos: .userInitiated).async {
            let entries = FlekDeckListProcursusApps().compactMap { record -> FlekProcursusGuestEntry? in
                guard let id = record["bundleID"] as? String,
                      let title = record["title"] as? String else { return nil }
                return FlekProcursusGuestEntry(id: id, title: title,
                                               icon: record["icon"] as? UIImage)
            }
            DispatchQueue.main.async {
                apps = entries
                loading = false
                hasLoaded = true
            }
        }
    }

    private func launch(_ app: FlekProcursusGuestEntry) {
        DispatchQueue.global(qos: .userInitiated).async {
            let didLaunch = FlekDeckLaunchProcursusApp(app.id)
            DispatchQueue.main.async {
                if didLaunch {
                    NotificationCenter.default.post(
                        name: Notification.Name("FlekDeckProcursusGuestDidLaunch"),
                        object: nil)
                } else {
                    launchError = "Nyxian's bootstrapd did not accept the launch of \(app.title). Verify the ROM is booted and the app is installed."
                }
            }
        }
    }
}
