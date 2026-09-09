from pathlib import Path

changed = []


def load(path: str) -> str:
    return Path(path).read_text()


def save(path: str, old: str, new: str):
    if old != new:
        Path(path).write_text(new)
        changed.append(path)


def replace_once(path: str, old: str, new: str, required: bool = True):
    text = load(path)
    if old not in text:
        if required and new not in text:
            raise SystemExit(f"Expected block not found in {path}: {old[:120]!r}")
        return
    save(path, text, text.replace(old, new, 1))


def replace_all(path: str, old: str, new: str):
    text = load(path)
    if old not in text:
        return
    save(path, text, text.replace(old, new))


def insert_before(path: str, marker: str, insertion: str, sentinel: str):
    text = load(path)
    if sentinel in text:
        return
    if marker not in text:
        raise SystemExit(f"Marker not found in {path}: {marker!r}")
    save(path, text, text.replace(marker, insertion + marker, 1))


# ---------------------------------------------------------------------------
# Settings: route Tweaks to the real Vibe Library / Manage / Apps UI.
# ---------------------------------------------------------------------------
settings = "LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift"
replace_once(
    settings,
    "                    NavigationLink { LCTweaksView() } label: {\n",
    "                    NavigationLink { FlekVibeTweaksView() } label: {\n",
)


# ---------------------------------------------------------------------------
# Home: consume the Vibe appearance state in the active renderer.
# ---------------------------------------------------------------------------
app_list = "LiveContainerSwiftUI/Views/AppList/LCAppListView.swift"
replace_once(
    app_list,
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault) var homeLayout: String = FlekHomeLayout.grid.rawValue\n\n\n    @State private var homeSaveIconExporterShow = false\n''',
    '''    @AppStorage(FlekDeckKeys.homeLayout, store: LCUtils.appGroupUserDefault) var homeLayout: String = FlekHomeLayout.grid.rawValue\n    @AppStorage(FlekDeckKeys.accentChoice, store: LCUtils.appGroupUserDefault) private var flekAccentChoice = FlekAccentChoice.blue.rawValue\n    @AppStorage(FlekDeckKeys.hideDockBackground, store: LCUtils.appGroupUserDefault) private var hideHomeDockBackground = false\n\n\n    @State private var homeSaveIconExporterShow = false\n''',
)
replace_once(
    app_list,
    '''                FlekWallpaperView()\n                FlekBlurredWallpaperOverlay(radius: 30)\n\n                homeContentView\n''',
    '''                FlekWallpaperView()\n                FlekBlurredWallpaperOverlay(radius: 30)\n                FlekAtmosphereOverlay()\n\n                homeContentView\n''',
)
replace_once(
    app_list,
    '''    private var homeBottomBar: AnyView {\n        if #available(iOS 26.0, *) {\n''',
    '''    private var homeBottomBar: AnyView {\n        if hideHomeDockBackground {\n            return AnyView(\n                HStack(spacing: 18) {\n                    if #available(iOS 16.0, *), showMultitaskDock {\n                        Button {\n                            MultitaskDockManager.shared.showAppSwitcher()\n                        } label: {\n                            Image(systemName: "rectangle.stack.fill")\n                                .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))\n                                .foregroundStyle(Color.primary.opacity(0.72))\n                                .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)\n                                .contentShape(Circle())\n                        }\n                        .buttonStyle(.plain)\n                    }\n                    Button {\n                        showSearch = true\n                    } label: {\n                        Image(systemName: "magnifyingglass")\n                            .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))\n                            .foregroundStyle(Color.primary.opacity(0.72))\n                            .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)\n                            .contentShape(Circle())\n                    }\n                    .buttonStyle(.plain)\n                }\n                .animation(dockEntranceAnimation, value: showMultitaskDock)\n            )\n        }\n        if #available(iOS 26.0, *) {\n''',
)
replace_once(
    app_list,
    '''        .animation(.easeOut(duration: 0.25), value: showSearch)\n        .onAppear {\n''',
    '''        .animation(FlekAppearanceStore.reduceMotion ? .linear(duration: 0.01) : .easeOut(duration: 0.25), value: showSearch)\n        .tint(FlekAccentChoice.resolved(flekAccentChoice).color)\n        .onReceive(NotificationCenter.default.publisher(for: .flekAppearanceChanged)) { _ in\n            homeRefreshToggle.toggle()\n        }\n        .onAppear {\n''',
)


# ---------------------------------------------------------------------------
# Add Vibe wallpaper presets to FlekDeck's existing wallpaper collection.
# ---------------------------------------------------------------------------
wallpaper = "LiveContainerSwiftUI/FlekDeck/Home/FlekWallpaperView.swift"
replace_once(
    wallpaper,
    '''        .asset("wallpaper14"),\n        .gradient("sunset", [Color(red: 1.0, green: 0.45, blue: 0.45), Color(red: 0.6, green: 0.2, blue: 0.6)]),\n''',
    '''        .asset("wallpaper14"),\n        .gradient("vibe", [Color(red: 0.035, green: 0.08, blue: 0.16), Color(red: 0.08, green: 0.32, blue: 0.46), Color(red: 0.01, green: 0.02, blue: 0.06)]),\n        .gradient("aurora", [Color(red: 0.15, green: 0.10, blue: 0.34), Color(red: 0.09, green: 0.52, blue: 0.48), Color(red: 0.03, green: 0.08, blue: 0.16)]),\n        .gradient("sunset", [Color(red: 1.0, green: 0.45, blue: 0.45), Color(red: 0.6, green: 0.2, blue: 0.6)]),\n''',
)


# ---------------------------------------------------------------------------
# Icon labels: hide in the active UIKit cells, not just model state.
# ---------------------------------------------------------------------------
icon_cell = "LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardIconCell.swift"
replace_once(
    icon_cell,
    '''        let iconS = Self.iconSize\n        let labelS = Self.labelSize\n        let labelGap = Self.labelTopSpacing\n        let contentHeight = iconS + labelGap + labelS.height\n        let contentY = ((bounds.height - contentHeight) / 2).rounded()\n''',
    '''        let iconS = Self.iconSize\n        let labelS = Self.labelSize\n        let showLabel = FlekAppearanceStore.showLabels\n        nameLabel.isHidden = !showLabel\n        let labelGap = showLabel ? Self.labelTopSpacing : 0\n        let contentHeight = iconS + labelGap + (showLabel ? labelS.height : 0)\n        let contentY = ((bounds.height - contentHeight) / 2).rounded()\n''',
)


# ---------------------------------------------------------------------------
# UIKit Springboard: live layout refresh + real Vibe page transitions.
# Column changes also reset stale persisted page capacities and repaginate.
# ---------------------------------------------------------------------------
controller = "LiveContainerSwiftUI/FlekDeck/Springboard/LCSpringboardViewController.swift"
replace_once(
    controller,
    '''    private(set) var itemsPerPage: Int = 15\n\n    // MARK: - Lifecycle\n''',
    '''    private(set) var itemsPerPage: Int = 15\n    private var lastAppearanceColumnToken = LCSpringboardViewController.appearanceColumnToken()\n\n    private static func appearanceColumnToken() -> String {\n        if FlekAppearanceStore.defaults.object(forKey: FlekDeckKeys.gridColumns) == nil { return "system" }\n        return "custom:\\(FlekAppearanceStore.gridColumns)"\n    }\n\n    // MARK: - Lifecycle\n''',
)
replace_once(
    controller,
    '''        setupOuterCollectionView()\n        setupPageControl()\n        setupDragManager()\n    }\n\n    deinit {\n        if Self.current === self { Self.current = nil }\n    }\n''',
    '''        setupOuterCollectionView()\n        setupPageControl()\n        setupDragManager()\n        NotificationCenter.default.addObserver(self, selector: #selector(flekAppearanceChanged), name: .flekAppearanceChanged, object: nil)\n    }\n\n    deinit {\n        NotificationCenter.default.removeObserver(self)\n        if Self.current === self { Self.current = nil }\n    }\n''',
)
insert_before(
    controller,
    "    // MARK: - Data update\n",
    '''    @objc private func flekAppearanceChanged() {\n        let token = Self.appearanceColumnToken()\n        let columnsChanged = token != lastAppearanceColumnToken\n        lastAppearanceColumnToken = token\n\n        if columnsChanged {\n            // Stored page sizes were calculated with the previous capacity.\n            // Rebuilding them is required so drag/reorder and paging stay in sync.\n            LCUtils.appGroupUserDefault.removeObject(forKey: FlekDeckKeys.homeScreenPageSizes)\n            recalculateItemsPerPage()\n            _ = paginateFromFlatItems()\n            currentPage = min(max(currentPage, 0), max(0, pages.count - 1))\n            outerCollectionView.reloadData()\n            pageControl.numberOfPages = pages.count\n            pageControl.currentPage = currentPage\n            DispatchQueue.main.async { [weak self] in self?.syncPagesToSwiftUI() }\n        } else {\n            outerCollectionView.collectionViewLayout.invalidateLayout()\n            for case let pageCell as LCSpringboardPageCell in outerCollectionView.visibleCells {\n                pageCell.collectionView.collectionViewLayout.invalidateLayout()\n                pageCell.setNeedsLayout()\n            }\n        }\n\n        view.setNeedsLayout()\n        refreshVisibleItems()\n    }\n\n''',
    "@objc private func flekAppearanceChanged()",
)
replace_once(
    controller,
    '''    func scrollViewDidScroll(_ scrollView: UIScrollView) {\n        guard scrollView.frame.width > 0 else { return }\n        let page = Int(round(scrollView.contentOffset.x / scrollView.frame.width))\n        if page != currentPage && page >= 0 && page < pages.count {\n            currentPage = page\n            pageControl.currentPage = page\n        }\n    }\n''',
    '''    func scrollViewDidScroll(_ scrollView: UIScrollView) {\n        guard scrollView.frame.width > 0 else { return }\n        let fractionalPage = scrollView.contentOffset.x / scrollView.frame.width\n        let page = Int(round(fractionalPage))\n        if page != currentPage && page >= 0 && page < pages.count {\n            currentPage = page\n            pageControl.currentPage = page\n        }\n\n        let transition = FlekAppearanceStore.reduceMotion ? FlekPageTransition.slide : FlekAppearanceStore.pageTransition\n        for cell in outerCollectionView.visibleCells {\n            guard let indexPath = outerCollectionView.indexPath(for: cell) else { continue }\n            let distance = min(abs(CGFloat(indexPath.item) - fractionalPage), 1)\n            switch transition {\n            case .slide:\n                cell.alpha = 1\n                cell.transform = .identity\n            case .fade:\n                cell.alpha = 1 - distance * 0.72\n                cell.transform = .identity\n            case .scale:\n                cell.alpha = 1 - distance * 0.25\n                let scale = 1 - distance * 0.10\n                cell.transform = CGAffineTransform(scaleX: scale, y: scale)\n            }\n        }\n    }\n''',
)


# ---------------------------------------------------------------------------
# Tweak scope semantics: one effective On/Off across global, per-app overlay,
# and legacy LCTweakFolder. Links are relative so parallel staging stays valid.
# ---------------------------------------------------------------------------
store = "LiveContainerSwiftUI/FlekDeck/Tweaks/FlekTweakStore.swift"
replace_once(
    store,
    '''    func isEffective(_ tweak: FlekManagedTweak, for app: LCAppModel) -> Bool {\n        if isGlobal(tweak) && !isBlocked(tweak, for: app) { return true }\n        if fm.fileExists(atPath: perAppURL(tweak, app: app).path) { return true }\n        return profileTweaks(for: app).contains { $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame }\n    }\n''',
    '''    func isEffective(_ tweak: FlekManagedTweak, for app: LCAppModel) -> Bool {\n        if isBlocked(tweak, for: app) { return false }\n        if isGlobal(tweak) { return true }\n        if fm.fileExists(atPath: perAppURL(tweak, app: app).path) { return true }\n        return profileTweaks(for: app).contains { $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame }\n    }\n''',
)
replace_once(
    store,
    '''    /// Mirrors Vibe's per-app toggle. For a global tweak this writes an opt-out\n    /// marker; for a non-global tweak it adds/removes a symlink in the app overlay.\n    func setEnabled(_ enabled: Bool, tweak: FlekManagedTweak, for app: LCAppModel) {\n        do {\n            try ensureDirectories()\n            if isGlobal(tweak) {\n                let marker = blockURL(tweak, app: app)\n                try fm.createDirectory(at: marker.deletingLastPathComponent(), withIntermediateDirectories: true)\n                if enabled {\n                    if fm.fileExists(atPath: marker.path) { try fm.removeItem(at: marker) }\n                } else if !fm.fileExists(atPath: marker.path) {\n                    fm.createFile(atPath: marker.path, contents: Data(), attributes: nil)\n                }\n            } else {\n                let overlay = perAppURL(tweak, app: app)\n                try fm.createDirectory(at: overlay.deletingLastPathComponent(), withIntermediateDirectories: true)\n                if enabled {\n                    if fm.fileExists(atPath: overlay.path) { try fm.removeItem(at: overlay) }\n                    try fm.createSymbolicLink(at: overlay, withDestinationURL: canonicalSource(for: tweak))\n                } else if fm.fileExists(atPath: overlay.path) {\n                    try fm.removeItem(at: overlay)\n                }\n            }\n            lastNotice = enabled ? "Enabled \\(tweak.name) for \\(app.displayName)." : "Disabled \\(tweak.name) for \\(app.displayName)."\n            objectWillChange.send()\n        } catch {\n            lastError = error.localizedDescription\n        }\n    }\n''',
    '''    /// Mirrors Vibe's per-app toggle, but makes the result authoritative\n    /// across global scope, the per-app overlay, and the existing profile.\n    func setEnabled(_ enabled: Bool, tweak: FlekManagedTweak, for app: LCAppModel) {\n        do {\n            try ensureDirectories()\n            let marker = blockURL(tweak, app: app)\n            let overlay = perAppURL(tweak, app: app)\n            try fm.createDirectory(at: marker.deletingLastPathComponent(), withIntermediateDirectories: true)\n            try fm.createDirectory(at: overlay.deletingLastPathComponent(), withIntermediateDirectories: true)\n\n            if enabled {\n                if fm.fileExists(atPath: marker.path) { try fm.removeItem(at: marker) }\n                let providedByProfile = profileTweaks(for: app).contains {\n                    $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame\n                }\n                if !isGlobal(tweak) && !providedByProfile && !fm.fileExists(atPath: overlay.path) {\n                    try createRelativeLink(at: overlay, to: canonicalSource(for: tweak))\n                }\n            } else {\n                if !fm.fileExists(atPath: marker.path) {\n                    fm.createFile(atPath: marker.path, contents: Data(), attributes: nil)\n                }\n                if fm.fileExists(atPath: overlay.path) || isSymlink(overlay) {\n                    try? fm.removeItem(at: overlay)\n                }\n            }\n            lastNotice = enabled ? "Enabled \\(tweak.name) for \\(app.displayName)." : "Disabled \\(tweak.name) for \\(app.displayName)."\n            objectWillChange.send()\n        } catch {\n            lastError = error.localizedDescription\n        }\n    }\n''',
)
replace_once(
    store,
    '''        for tweak in overlayTweaks(for: app) { map[tweak.id] = tweak }\n        for tweak in profileTweaks(for: app) { map[tweak.id] = tweak }\n''',
    '''        for tweak in overlayTweaks(for: app) where !isBlocked(tweak, for: app) { map[tweak.id] = tweak }\n        for tweak in profileTweaks(for: app) where !isBlocked(tweak, for: app) { map[tweak.id] = tweak }\n''',
)
replace_all(store, "try fm.createSymbolicLink(at: global, withDestinationURL: canonicalSource(for: tweak))", "try createRelativeLink(at: global, to: canonicalSource(for: tweak))")
replace_all(store, "try fm.createSymbolicLink(at: overlay, withDestinationURL: canonicalSource(for: tweak))", "try createRelativeLink(at: overlay, to: canonicalSource(for: tweak))")
replace_all(store, "try fm.createSymbolicLink(at: link, withDestinationURL: target)", "try createRelativeLink(at: link, to: target)")
replace_all(store, "try fm.createSymbolicLink(at: link, withDestinationURL: destination)", "try createRelativeLink(at: link, to: destination)")
insert_before(
    store,
    "    private func removeNamedItem(_ name: String, below root: URL) throws {\n",
    '''    private func createRelativeLink(at link: URL, to target: URL) throws {\n        let from = link.deletingLastPathComponent().standardizedFileURL.pathComponents\n        let to = target.standardizedFileURL.pathComponents\n        var common = 0\n        while common < from.count && common < to.count && from[common] == to[common] { common += 1 }\n        let components = Array(repeating: "..", count: from.count - common) + Array(to.dropFirst(common))\n        let relative = components.isEmpty ? "." : components.joined(separator: "/")\n        try fm.createSymbolicLink(atPath: link.path, withDestinationPath: relative)\n    }\n\n''',
    "private func createRelativeLink(at link:",
)


# ---------------------------------------------------------------------------
# TweakLoader: blacklist applies to recursive legacy profiles and per-app
# overlays too, so the UI's Off state cannot be bypassed by another source.
# ---------------------------------------------------------------------------
loader = "TweakLoader/TweakLoader.m"
replace_once(
    loader,
    "static void loadTweaksRecursively(NSURL *folderURL, NSMutableArray *errors) {\n",
    "static void loadTweaksRecursively(NSURL *folderURL, NSMutableArray *errors, NSSet<NSString *> *blockedNames) {\n",
)
replace_once(
    loader,
    '''        if ([name hasSuffix:@".disabled"]) {\n            NSLog(@"Skipping disabled tweak %@", name);\n            continue;\n        }\n''',
    '''        if ([name hasSuffix:@".disabled"]) {\n            NSLog(@"Skipping disabled tweak %@", name);\n            continue;\n        }\n        if ([blockedNames containsObject:name]) {\n            NSLog(@"Skipping blocked tweak %@", name);\n            continue;\n        }\n''',
)
replace_all(loader, "loadTweaksRecursively(fileURL, errors);", "loadTweaksRecursively(fileURL, errors, blockedNames);")
replace_all(loader, "loadTweaksRecursively([NSURL fileURLWithPath:tweakFolder], errors);", "loadTweaksRecursively([NSURL fileURLWithPath:tweakFolder], errors, blockedNames);")
replace_all(loader, "loadTweaksRecursively(perAppFolder, errors);", "loadTweaksRecursively(perAppFolder, errors, blockedNames);")


print("finish_vibe_settings_port changed:")
for path in sorted(set(changed)):
    print(" -", path)
