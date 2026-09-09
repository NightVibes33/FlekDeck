from pathlib import Path


def replace_once(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1))


def insert_before(path: str, marker: str, text_to_insert: str):
    p = Path(path)
    text = p.read_text()
    if marker not in text:
        raise SystemExit(f"Marker not found in {path}: {marker!r}")
    p.write_text(text.replace(marker, text_to_insert + marker, 1))


# ---------------------------------------------------------------------------
# FlekDeck app-group appearance keys
# ---------------------------------------------------------------------------
replace_once(
    "LiveContainerSwiftUI/FlekDeck/Home/FlekDeckModel.swift",
    '    static let cardStyleGlass = "FlekCardStyleGlass" // true = liquid glass, false = thin material\n',
    '''    static let cardStyleGlass = "FlekCardStyleGlass" // true = liquid glass, false = thin material
    // VibeContainers appearance controls, stored in the same app-group domain
    // as the rest of FlekDeck so Settings, Springboard and controller mode agree.
    static let accentChoice = "FlekAccentChoice"
    static let showMotes = "FlekShowMotes"
    static let moteDensity = "FlekMoteDensity"
    static let scanlines = "FlekScanlines"
    static let reduceMotion = "FlekReduceMotion"
    static let gridColumns = "FlekGridColumns"
    static let showAppLabels = "FlekShowAppLabels"
    static let hideDockBackground = "FlekHideDockBackground"
    static let pageTransition = "FlekPageTransition"
'''
)

# ---------------------------------------------------------------------------
# Merge Vibe customization into the real Personalization page
# ---------------------------------------------------------------------------
personalization = "LiveContainerSwiftUI/FlekDeck/Settings/FlekPersonalizationView.swift"
replace_once(
    personalization,
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault)
    private var homeLayout: String = FlekHomeLayout.grid.rawValue

    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault) private var dynamicColors = true
''',
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault)
    private var homeLayout: String = FlekHomeLayout.grid.rawValue

    @AppStorage(FlekDeckKeys.accentChoice, store: LCUtils.appGroupUserDefault) private var accentChoice = 0
    @AppStorage(FlekDeckKeys.showMotes, store: LCUtils.appGroupUserDefault) private var showMotes = true
    @AppStorage(FlekDeckKeys.moteDensity, store: LCUtils.appGroupUserDefault) private var moteDensity = 0.5
    @AppStorage(FlekDeckKeys.scanlines, store: LCUtils.appGroupUserDefault) private var scanlines = true
    @AppStorage(FlekDeckKeys.reduceMotion, store: LCUtils.appGroupUserDefault) private var reduceMotion = false
    @AppStorage(FlekDeckKeys.gridColumns, store: LCUtils.appGroupUserDefault) private var gridColumns = 3
    @AppStorage(FlekDeckKeys.showAppLabels, store: LCUtils.appGroupUserDefault) private var showAppLabels = true
    @AppStorage(FlekDeckKeys.hideDockBackground, store: LCUtils.appGroupUserDefault) private var hideDockBackground = false
    @AppStorage(FlekDeckKeys.pageTransition, store: LCUtils.appGroupUserDefault) private var pageTransition = FlekPageTransition.slide.rawValue

    @AppStorage("dynamicColors", store: LCUtils.appGroupUserDefault) private var dynamicColors = true
'''
)

insert_before(
    personalization,
    "                // MARK: App Icons\n",
    '''                // MARK: Appearance — VibeContainers port
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("Appearance")
                    VStack(spacing: 0) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Accent").font(.subheadline.weight(.semibold))
                            HStack(spacing: 12) {
                                ForEach(FlekAccentChoice.allCases) { choice in
                                    Button {
                                        accentChoice = choice.rawValue
                                        UISelectionFeedbackGenerator().selectionChanged()
                                    } label: {
                                        Circle()
                                            .fill(choice.color)
                                            .frame(width: 30, height: 30)
                                            .overlay {
                                                if accentChoice == choice.rawValue {
                                                    Image(systemName: "checkmark")
                                                        .font(.system(size: 12, weight: .bold))
                                                        .foregroundStyle(.white)
                                                }
                                            }
                                            .overlay(Circle().stroke(Color.primary.opacity(accentChoice == choice.rawValue ? 0.28 : 0.08), lineWidth: 1))
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)

                        Divider().padding(.leading, 16)
                        Toggle("Motes", isOn: $showMotes)
                            .padding(.horizontal, 16).padding(.vertical, 12)

                        if showMotes {
                            Divider().padding(.leading, 16)
                            VStack(alignment: .leading, spacing: 7) {
                                HStack {
                                    Text("Mote Density")
                                    Spacer()
                                    Text("\\(Int(moteDensity * 100))%")
                                        .foregroundStyle(.secondary)
                                        .monospacedDigit()
                                }
                                Slider(value: $moteDensity, in: 0...1, step: 0.05)
                                    .tint(accentColor)
                            }
                            .padding(.horizontal, 16).padding(.vertical, 12)
                        }

                        Divider().padding(.leading, 16)
                        Toggle("Scanlines", isOn: $scanlines)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                        Divider().padding(.leading, 16)
                        Toggle("Reduce Motion", isOn: $reduceMotion)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    .background(card)
                }

                // MARK: Home Screen — VibeContainers port
                VStack(alignment: .leading, spacing: 10) {
                    sectionHeader("Home Screen")
                    VStack(spacing: 0) {
                        HStack {
                            Text("Grid Columns")
                            Spacer()
                            Stepper("\\(gridColumns)", value: $gridColumns, in: 2...6)
                                .labelsHidden()
                            Text("\\(gridColumns)")
                                .foregroundStyle(.secondary)
                                .monospacedDigit()
                                .frame(width: 18)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .opacity(homeLayout == FlekHomeLayout.grid.rawValue ? 1 : 0.45)
                        .disabled(homeLayout != FlekHomeLayout.grid.rawValue)

                        Divider().padding(.leading, 16)
                        Toggle("Show App Labels", isOn: $showAppLabels)
                            .padding(.horizontal, 16).padding(.vertical, 12)

                        Divider().padding(.leading, 16)
                        Toggle("Hide Dock Background", isOn: $hideDockBackground)
                            .padding(.horizontal, 16).padding(.vertical, 12)

                        Divider().padding(.leading, 16)
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Page Transition").font(.subheadline.weight(.semibold))
                            Picker("Page Transition", selection: $pageTransition) {
                                ForEach(FlekPageTransition.allCases) { transition in
                                    Text(transition.title).tag(transition.rawValue)
                                }
                            }
                            .pickerStyle(.segmented)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    .background(card)
                }

'''
)

replace_once(personalization, "Self.flekBlue", "accentColor")
replace_once(personalization, "Self.flekBlue", "accentColor")
insert_before(
    personalization,
    "    private var currentPreview: some View {\n",
    '''    private var accentColor: Color {
        FlekAccentChoice.resolved(accentChoice).color
    }

'''
)

replace_once(
    personalization,
    '''        .sheet(isPresented: $showCollection) {
''',
    '''        .onChange(of: accentChoice) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: showMotes) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: moteDensity) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: scanlines) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: reduceMotion) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: gridColumns) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: showAppLabels) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: hideDockBackground) { _ in FlekAppearanceStore.postChanged() }
        .onChange(of: pageTransition) { _ in FlekAppearanceStore.postChanged() }
        .sheet(isPresented: $showCollection) {
'''
)

# ---------------------------------------------------------------------------
# Vibe wallpaper presets + real motes/scanlines render over Flek wallpaper
# ---------------------------------------------------------------------------
wallpaper = "LiveContainerSwiftUI/FlekDeck/Home/FlekWallpaperView.swift"
replace_once(
    wallpaper,
    '''        .asset("wallpaper14"),
        .gradient("sunset", [Color(red: 1.0, green: 0.45, blue: 0.45), Color(red: 0.6, green: 0.2, blue: 0.6)]),
''',
    '''        .asset("wallpaper14"),
        // VibeContainers wallpaper styles adapted into FlekDeck's existing
        // descriptor collection rather than a competing wallpaper store.
        .gradient("vibe", [Color(red: 0.035, green: 0.08, blue: 0.16), Color(red: 0.08, green: 0.32, blue: 0.46), Color(red: 0.01, green: 0.02, blue: 0.06)]),
        .gradient("aurora", [Color(red: 0.15, green: 0.10, blue: 0.34), Color(red: 0.09, green: 0.52, blue: 0.48), Color(red: 0.03, green: 0.08, blue: 0.16)]),
        .gradient("sunset", [Color(red: 1.0, green: 0.45, blue: 0.45), Color(red: 0.6, green: 0.2, blue: 0.6)]),
'''
)

old_wallpaper_view = '''struct FlekWallpaperView: View {
    @AppStorage(FlekDeckKeys.wallpaperName, store: LCUtils.appGroupUserDefault)
    private var wallpaperDescriptor: String = FlekWallpaper.defaultDescriptor
    @AppStorage(FlekDeckKeys.wallpaperPhoto, store: LCUtils.appGroupUserDefault)
    private var wallpaperPhoto: String = ""

    var body: some View {
        GeometryReader { geo in
            Group {
                if !wallpaperPhoto.isEmpty, let img = FlekWallpaperStore.loadPhoto(named: wallpaperPhoto) {
                    Image(uiImage: img).resizable().scaledToFill()
                } else {
                    FlekWallpaper.from(descriptor: wallpaperDescriptor).fullSize()
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .ignoresSafeArea()
    }
}
'''
new_wallpaper_view = '''struct FlekWallpaperView: View {
    @AppStorage(FlekDeckKeys.wallpaperName, store: LCUtils.appGroupUserDefault)
    private var wallpaperDescriptor: String = FlekWallpaper.defaultDescriptor
    @AppStorage(FlekDeckKeys.wallpaperPhoto, store: LCUtils.appGroupUserDefault)
    private var wallpaperPhoto: String = ""
    @AppStorage(FlekDeckKeys.showMotes, store: LCUtils.appGroupUserDefault)
    private var showMotes = true
    @AppStorage(FlekDeckKeys.moteDensity, store: LCUtils.appGroupUserDefault)
    private var moteDensity = 0.5
    @AppStorage(FlekDeckKeys.scanlines, store: LCUtils.appGroupUserDefault)
    private var scanlines = true
    @AppStorage(FlekDeckKeys.reduceMotion, store: LCUtils.appGroupUserDefault)
    private var reduceMotion = false

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Group {
                    if !wallpaperPhoto.isEmpty, let img = FlekWallpaperStore.loadPhoto(named: wallpaperPhoto) {
                        Image(uiImage: img).resizable().scaledToFill()
                    } else {
                        FlekWallpaper.from(descriptor: wallpaperDescriptor).fullSize()
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
                .clipped()

                if showMotes {
                    FlekWallpaperMotes(density: moteDensity, reduceMotion: reduceMotion)
                        .allowsHitTesting(false)
                }
                if scanlines {
                    FlekWallpaperScanlines().allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .ignoresSafeArea()
    }
}

private struct FlekWallpaperMotes: View {
    let density: Double
    let reduceMotion: Bool

    var body: some View {
        let count = Int(6 + min(max(density, 0), 1) * 30)
        TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 20.0)) { timeline in
            let t = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                for index in 0..<count {
                    let seed = Double(index + 1)
                    let bx = abs((sin(seed * 12.9898) * 43758.5453).truncatingRemainder(dividingBy: 1))
                    let by = abs((sin(seed * 78.233) * 12345.6789).truncatingRemainder(dividingBy: 1))
                    let drift = reduceMotion ? 0 : sin(t * (0.075 + seed.truncatingRemainder(dividingBy: 5) * 0.01) + seed) * 0.045
                    let x = size.width * CGFloat(min(max(bx + drift, 0), 1))
                    let y = size.height * CGFloat(by)
                    let r = CGFloat(0.9 + seed.truncatingRemainder(dividingBy: 2.0))
                    context.fill(Path(ellipseIn: CGRect(x: x, y: y, width: r, height: r)), with: .color(.white.opacity(0.20)))
                }
            }
        }
    }
}

private struct FlekWallpaperScanlines: View {
    var body: some View {
        Canvas { context, size in
            var y: CGFloat = 0
            while y < size.height {
                context.fill(Path(CGRect(x: 0, y: y, width: size.width, height: 0.5)), with: .color(.black.opacity(0.10)))
                y += 4
            }
        }
    }
}
'''
replace_once(wallpaper, old_wallpaper_view, new_wallpaper_view)

# ---------------------------------------------------------------------------
# Real UIKit Springboard columns/capacity and labels
# ---------------------------------------------------------------------------
page_cell = "LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardPageCell.swift"
replace_once(page_cell, "    static let phoneColumns: Int = 3\n", "    static var phoneColumns: Int { FlekAppearanceStore.gridColumns }\n")
replace_once(
    page_cell,
    '''    static func columns(forPageSize size: CGSize) -> Int {
        usesPadGrid(pageSize: size) ? padGrid(forPageSize: size).columns : phoneColumns
    }
''',
    '''    static func columns(forPageSize size: CGSize) -> Int {
        // Until the user touches the Vibe column control, preserve FlekDeck's
        // existing iPad 4/6-column geometry. Once chosen, the same preference
        // drives every Springboard page and all drag/page-capacity math.
        if FlekAppearanceStore.defaults.object(forKey: FlekDeckKeys.gridColumns) != nil {
            return FlekAppearanceStore.gridColumns
        }
        return usesPadGrid(pageSize: size) ? padGrid(forPageSize: size).columns : phoneColumns
    }
'''
)
replace_once(
    page_cell,
    "        size.width * padGridWidthFraction / CGFloat(padGrid(forPageSize: size).columns)\n",
    "        size.width * padGridWidthFraction / CGFloat(columns(forPageSize: size))\n"
)

icon_cell = "LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardIconCell.swift"
replace_once(
    icon_cell,
    '''        let iconS = Self.iconSize
        let labelS = Self.labelSize
        let labelGap = Self.labelTopSpacing
        let contentHeight = iconS + labelGap + labelS.height
        let contentY = ((bounds.height - contentHeight) / 2).rounded()
''',
    '''        let iconS = Self.iconSize
        let labelS = Self.labelSize
        let showLabel = FlekAppearanceStore.showLabels
        nameLabel.isHidden = !showLabel
        let labelGap = showLabel ? Self.labelTopSpacing : 0
        let contentHeight = iconS + labelGap + (showLabel ? labelS.height : 0)
        let contentY = ((bounds.height - contentHeight) / 2).rounded()
'''
)

# ---------------------------------------------------------------------------
# Page transition and live appearance refresh in active UIKit Springboard
# ---------------------------------------------------------------------------
controller = "LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift"
replace_once(
    controller,
    '''        setupOuterCollectionView()
        setupPageControl()
        setupDragManager()
    }
''',
    '''        setupOuterCollectionView()
        setupPageControl()
        setupDragManager()
        NotificationCenter.default.addObserver(self, selector: #selector(flekAppearanceChanged), name: .flekAppearanceChanged, object: nil)
    }
'''
)
insert_before(
    controller,
    "    // MARK: - Data update\n",
    '''    @objc private func flekAppearanceChanged() {
        outerCollectionView.collectionViewLayout.invalidateLayout()
        outerCollectionView.visibleCells.forEach { cell in
            cell.setNeedsLayout()
            (cell as? LCSpringboardPageCell)?.collectionView.collectionViewLayout.invalidateLayout()
        }
        view.setNeedsLayout()
        refreshVisibleItems()
    }

'''
)
replace_once(
    controller,
    '''    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        guard scrollView.frame.width > 0 else { return }
        let page = Int(round(scrollView.contentOffset.x / scrollView.frame.width))
        if page != currentPage && page >= 0 && page < pages.count {
            currentPage = page
            pageControl.currentPage = page
        }
    }
''',
    '''    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        guard scrollView.frame.width > 0 else { return }
        let fractionalPage = scrollView.contentOffset.x / scrollView.frame.width
        let page = Int(round(fractionalPage))
        if page != currentPage && page >= 0 && page < pages.count {
            currentPage = page
            pageControl.currentPage = page
        }

        let transition = FlekAppearanceStore.reduceMotion ? FlekPageTransition.slide : FlekAppearanceStore.pageTransition
        for cell in outerCollectionView.visibleCells {
            guard let indexPath = outerCollectionView.indexPath(for: cell) else { continue }
            let distance = min(abs(CGFloat(indexPath.item) - fractionalPage), 1)
            switch transition {
            case .slide:
                cell.alpha = 1
                cell.transform = .identity
            case .fade:
                cell.alpha = 1 - distance * 0.72
                cell.transform = .identity
            case .scale:
                cell.alpha = 1 - distance * 0.25
                let scale = 1 - distance * 0.10
                cell.transform = CGAffineTransform(scaleX: scale, y: scale)
            }
        }
    }
'''
)

# ---------------------------------------------------------------------------
# Home accent + actual hidden bottom-control background
# ---------------------------------------------------------------------------
app_list = "LiveContainerSwiftUI/Views/AppList/LCAppListView.swift"
replace_once(
    app_list,
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault) var homeLayout: String = FlekHomeLayout.grid.rawValue


    @State private var homeSaveIconExporterShow = false
''',
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault) var homeLayout: String = FlekHomeLayout.grid.rawValue
    @AppStorage(FlekDeckKeys.accentChoice, store: LCUtils.appGroupUserDefault) private var flekAccentChoice = 0
    @AppStorage(FlekDeckKeys.hideDockBackground, store: LCUtils.appGroupUserDefault) private var hideHomeDockBackground = false


    @State private var homeSaveIconExporterShow = false
'''
)
replace_once(
    app_list,
    '''    private var homeBottomBar: AnyView {
        if #available(iOS 26.0, *) {
''',
    '''    private var homeBottomBar: AnyView {
        if hideHomeDockBackground {
            return AnyView(
                HStack(spacing: 18) {
                    if #available(iOS 16.0, *), showMultitaskDock {
                        Button {
                            MultitaskDockManager.shared.showAppSwitcher()
                        } label: {
                            Image(systemName: "rectangle.stack.fill")
                                .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))
                                .foregroundStyle(Color.primary.opacity(0.72))
                                .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)
                                .contentShape(Circle())
                        }
                        .buttonStyle(.plain)
                    }
                    Button {
                        showSearch = true
                    } label: {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))
                            .foregroundStyle(Color.primary.opacity(0.72))
                            .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
                .animation(dockEntranceAnimation, value: showMultitaskDock)
            )
        }
        if #available(iOS 26.0, *) {
'''
)
replace_once(
    app_list,
    '''        .animation(.easeOut(duration: 0.25), value: showSearch)
        .onAppear {
''',
    '''        .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .easeOut(duration: 0.25), value: showSearch)
        .tint(FlekAccentChoice.resolved(flekAccentChoice).color)
        .onReceive(NotificationCenter.default.publisher(for: .flekAppearanceChanged)) { _ in
            homeRefreshToggle.toggle()
        }
        .onAppear {
'''
)

# ---------------------------------------------------------------------------
# Controller settings now enter the real XMB and expose Vibe test controls
# ---------------------------------------------------------------------------
controller_mode = "LiveContainerSwiftUI/FlekDeck/Controller/FlekControllerMode.swift"
replace_once(
    controller_mode,
    '''    @Published private(set) var pads: [FlekGamePad] = []
    var isConnected: Bool { !pads.isEmpty }
''',
    '''    @Published private(set) var pads: [FlekGamePad] = []
    @Published var controllerUITestMode = false
    var isConnected: Bool { !pads.isEmpty }
'''
)
replace_once(controller_mode, "            FlekControllerDashboardView()\n", "            FlekXMBRootView()\n")
replace_once(
    controller_mode,
    '''                controllerCard
                capabilityCard
                launchCard
''',
    '''                controllerCard
                capabilityCard
                touchTestCard
                launchCard
'''
)
insert_before(
    controller_mode,
    "    private var launchCard: some View {\n",
    '''    private var touchTestCard: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.cyan.opacity(0.13))
                Image(systemName: "hand.tap.fill")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(.cyan)
            }
            .frame(width: 50, height: 50)
            VStack(alignment: .leading, spacing: 3) {
                Text("Touch Test Controls").font(.headline)
                Text("Session-only controls feed the exact same XMB navigator as a physical controller.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Toggle("", isOn: $hub.controllerUITestMode).labelsHidden().tint(.cyan)
        }
        .padding(16)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

'''
)

# ---------------------------------------------------------------------------
# Settings integration: Personalization is authoritative; new tweak view is real
# ---------------------------------------------------------------------------
settings = "LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift"
replace_once(
    settings,
    '''                    NavigationLink { FlekCustomizationView() } label: {
                        categoryRow("Customization", "paintbrush.pointed.fill", .purple)
                    }
''',
    '''                    NavigationLink { FlekPersonalizationView() } label: {
                        categoryRow("Personalization", "paintbrush.pointed.fill", .purple)
                    }
'''
)
replace_once(settings, "                    NavigationLink { LCTweaksView() } label:\n", "                    NavigationLink { FlekVibeTweaksView() } label:\n")

# ---------------------------------------------------------------------------
# HTTP parity refinements from Vibe
# ---------------------------------------------------------------------------
http = "LiveContainerSwiftUI/FlekDeck/HTTP/FlekHTTPServer.swift"
replace_once(http, "        guard (1...65535).contains(value) else { return }\n", "        guard (1024...65535).contains(value) else { return }\n")
replace_once(
    http,
    '''                    .frame(width: 90)
                    .onSubmit(applyPort)
''',
    '''                    .frame(width: 90)
                    .onSubmit(applyPort)
                    .onChange(of: portText) { _ in applyPort() }
'''
)

print("Corrected Vibe port source patches applied")
