//
//  FlekSearchView.swift
//  LiveContainerSwiftUI
//
//  Springboard search. Presented as an overlay over the (dimmed, blurred) home
//  screen: results fill from the top and the search field sits in a bottom bar
//  just above the keyboard, matching the FlekSign design. Searches installed
//  apps; per-source (Installer) results are added with the Installer rework.
//

import SwiftUI
import Kingfisher
import QuartzCore

struct FlekSearchView: View {
    @Binding var isPresented: Bool
    let apps: [LCAppModel]
    let darkModeIcon: Bool
    var onSelect: (LCAppModel) -> Void
    /// Long-press menu for an installed result — the springboard's own app menu, so
    /// a result offers the same actions as an icon on the home screen.
    var contextMenu: (LCAppModel) -> AnyView = { _ in AnyView(EmptyView()) }
    var onInstallStoreApp: (FSAppModel) -> Void = { _ in }
    /// Opens a result's page in the installer, on the source it came from.
    var onOpenStoreApp: (FlekInstallerView.DetailRequest) -> Void = { _ in }
    var onOpenRepo: (String) -> Void = { _ in }

    @State private var query = ""
    @State private var debouncedQuery = ""
    @State private var debounceTask: Task<Void, Never>?
    @FocusState private var fieldFocused: Bool
    @State private var bottomBarHeight: CGFloat = 66   // measured at runtime; sensible fallback
    @StateObject private var repoSearch = MultiRepoSearchModel()
    @Environment(\.colorScheme) private var colorScheme

    private var results: [LCAppModel] {
        guard !debouncedQuery.isEmpty else { return [] }
        return apps.filter { app in
            (app.appInfo.displayName()?.localizedCaseInsensitiveContains(debouncedQuery) ?? false) ||
            (app.appInfo.bundleIdentifier()?.localizedCaseInsensitiveContains(debouncedQuery) ?? false)
        }
    }

    var body: some View {
        ZStack {
            ZStack(alignment: .bottom) {
                resultsArea
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                bottomBar
                    .padding(.horizontal, 14)
                    .padding(.bottom, 8)
                    .contentShape(Rectangle())
                    .background(
                        GeometryReader { proxy in
                            Color.clear.preference(key: BottomBarHeightKey.self,
                                                   value: proxy.size.height)
                        }
                    )
            }
            .onPreferenceChange(BottomBarHeightKey.self) { bottomBarHeight = $0 }
        }
        .onAppear {
            fieldFocused = true
            repoSearch.setup()
            Task { await MultiRepoSearchModel.prefetchAllRepos() }
        }
        .onChange(of: query) { q in
            debounceTask?.cancel()
            let trimmed = q.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                debouncedQuery = ""
                repoSearch.cancelSearch()
                return
            }
            debounceTask = Task {
                try? await Task.sleep(nanoseconds: 350_000_000)
                guard !Task.isCancelled else { return }
                debouncedQuery = trimmed
                repoSearch.search(trimmed)
            }
        }
    }

    @ViewBuilder
    private var resultsArea: some View {
        if debouncedQuery.isEmpty {
            Spacer()
        } else if results.isEmpty && repoSearch.sections.isEmpty && !repoSearch.isLoading {
            Spacer()
            VStack(spacing: 16) {
                Image(systemName: FlekSymbol.appGrid)
                    .font(.system(size: 75, weight: .thin))
                    .foregroundStyle(Color.white.opacity(0.6))
                Text("Nothing found")
                    .font(.system(size: 20))
                    .foregroundStyle(Color.white)
            }
            Spacer()
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if !results.isEmpty {
                        section(title: "lc.flek.installed".loc) {
                            ForEach(results, id: \.self) { app in
                                FlekSearchResultRow(app: app,
                                                    darkModeIcon: darkModeIcon,
                                                    onSelect: { onSelect(app); close() },
                                                    menu: { contextMenu(app) })
                            }
                        }
                    }
                    ForEach(repoSearch.sections) { repoSection in
                        section(title: repoSection.name, iconUrl: repoSection.iconUrl, onOpen: {
                            onOpenRepo(repoSection.id)
                            close()
                        }) {
                            if repoSection.apps.isEmpty && repoSection.isLoading {
                                HStack { Spacer(); ProgressView(); Spacer() }
                                    .frame(height: 74)
                            } else {
                                ForEach(repoSection.apps) { app in
                                    FlekStoreSearchResultRow(
                                        app: app,
                                        onOpen: {
                                            onOpenStoreApp(.init(repoURL: repoSection.id,
                                                                 app: app,
                                                                 isFlekstore: repoSection.isFlekstore))
                                            close()
                                        },
                                        onInstall: {
                                            if repoSection.isFlekstore {
                                                FlekstoreAppsListViewModel.recordDownload(appId: app.app_id)
                                            }
                                            onInstallStoreApp(app)
                                            close()
                                        }
                                    )
                                }
                            }
                        }
                    }
                    if repoSearch.isLoading {
                        ProgressView().frame(maxWidth: .infinity).padding()
                    }
                }
                .padding(.horizontal, 16)
                // No top bar/blur here (unlike the installer), so the list only
                // needs a small gap below the safe area rather than a large inset.
                .padding(.top, 8)
                // Clear the bottom search bar (measured at runtime) plus a
                // small gap, so the last result can scroll fully above it.
                .padding(.bottom, bottomBarHeight + 16)
            }
        }
    }

    @ViewBuilder
    private func section<Content: View>(title: String, iconUrl: String? = nil, onOpen: (() -> Void)? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                if let iconUrl, let url = URL(string: iconUrl) {
                    KFImage(url)
                        .placeholder { FlekImagePlaceholder(cornerRadius: 4) }
                        .setProcessor(DownsamplingImageProcessor(size: CGSize(width: 18, height: 18)))
                        .scaleFactor(UIScreen.main.scale)
                        .cacheOriginalImage()
                        .cancelOnDisappear(true)
                        .fade(duration: 0.15)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 18, height: 18)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                }
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color.white.opacity(0.7))
                if let onOpen {
                    Spacer()
                    Button(action: onOpen) {
                        HStack(spacing: 4) {
                            Text("lc.flek.openRepo".loc)
                                .font(.system(size: 13, weight: .medium))
                            Image(systemName: "arrow.up.forward.app.fill")
                                .font(.system(size: 11, weight: .semibold))
                        }
                        .foregroundStyle(Color.white.opacity(0.6))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.leading, 6)
            content()
        }
    }

    private var bottomBar: some View {
        HStack(spacing: 16) {
            // Search field pill
            HStack(spacing: 12) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 23))
                    .foregroundStyle(Color.primary.opacity(0.6))
                TextField("lc.flek.search".loc, text: $query)
                    .font(.system(size: 18))
                    .foregroundStyle(Color.primary)
                    .tint(Color.primary)                   // caret color
                    .focused($fieldFocused)
                    .submitLabel(.search)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                if !query.isEmpty {
                    Button {
                        query = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 18))
                            .foregroundStyle(Color.primary.opacity(0.4))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .searchPillBackground()

            // Clear + close button (returns to the home screen)
            Button {
                close()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 22))
                    .foregroundStyle(Color.primary.opacity(0.7))
                    .frame(width: 50, height: 50)
                    .searchCircleBackground()
            }
            .buttonStyle(.plain)
            .shadow(color: .black.opacity(0.25), radius: 20, x: 0, y: 4)  // single shadow, on the button
        }
    }

    private func close() {
        debounceTask?.cancel()
        query = ""
        debouncedQuery = ""
        fieldFocused = false
        isPresented = false
    }
}

// MARK: - Layout preference

private struct BottomBarHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 66
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

// MARK: - Multi-repo search model

@MainActor
class MultiRepoSearchModel: ObservableObject {
    struct RepoSection: Identifiable, Sendable {
        let id: String          // repo sourceURL
        let name: String
        let iconUrl: String
        let isFlekstore: Bool
        let apps: [FSAppModel]
        /// True while this section's results are still being fetched. Used to keep
        /// the FlekStore slot pinned at the top with a spinner instead of popping in
        /// (and reshuffling the list) once its server results arrive.
        var isLoading: Bool = false
    }

    @Published var sections: [RepoSection] = [] {
        didSet {
            sectionsStamp = CACurrentMediaTime()
            batch &+= 1
        }
    }
    @Published var isLoading = false

    /// When the current batch of results was published. Result rows animate in
    /// only when they belong to a fresh batch, so rows the lazy stack rebuilds
    /// while the user scrolls just appear instead of re-animating.
    private(set) var sectionsStamp: TimeInterval = 0

    /// Bumped with every published batch. The results list keys its layout
    /// animation off this, so a section filling in (or dropping out) slides the
    /// rows below it instead of teleporting them.
    @Published private(set) var batch = 0

    /// Cap on matches kept per repo section — bounds both the filtering work and
    /// the rendered rows for very broad (short) queries so results stay responsive.
    static let maxResultsPerRepo = 50
    /// Minimum characters before a repo search runs. 1 = no gate (the per-repo cap
    /// already bounds broad queries); raise to 2–3 to suppress 1‑character searches.
    static let minQueryLength = 1

    private var repos: [AppRepository] = []
    private var cachedApps: [String: [FSAppModel]] = [:] // keyed by sourceURL
    private var flekstoreVM = FlekstoreAppsListViewModel()
    private var searchTask: Task<Void, Never>?
    private var debounceTask: Task<Void, Never>?

    /// How long typing settles before a query is sent.
    private static let debounceDelay: UInt64 = 300_000_000

    func setup() {
        repos = FlekInstallerView.loadRepos()
        cachedApps = RepoCatalogCache.shared.loadAllCached(repos: repos)
        flekstoreVM.repository = .flekstore
    }

    func search(_ query: String) {
        searchTask?.cancel()

        guard query.count >= Self.minQueryLength else {
            sections = []
            isLoading = false
            return
        }

        isLoading = true

        searchTask = Task {
            await performSearch(query)
        }
    }

    /// Call on every keystroke. Debounces the query *and* marks the model busy
    /// straight away, so a view can show a loading state for the whole keystroke →
    /// results gap. Deciding "empty" from `sections` alone flashes "Nothing found"
    /// during the debounce, before the search has even started.
    func queryChanged(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        debounceTask?.cancel()
        guard !trimmed.isEmpty else {
            cancelSearch()
            return
        }
        isLoading = true
        debounceTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: Self.debounceDelay)
            guard !Task.isCancelled else { return }
            self?.search(trimmed)
        }
    }

    /// Run the query now, skipping the debounce (the keyboard's Search key).
    func searchNow(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        debounceTask?.cancel()
        guard !trimmed.isEmpty else {
            cancelSearch()
            return
        }
        search(trimmed)
    }

    func cancelSearch() {
        debounceTask?.cancel()
        searchTask?.cancel()
        sections = []
        isLoading = false
    }

    /// Fetches all custom-repo catalogs and writes them to disk cache.
    /// Skips if called again within the cooldown interval (5 minutes).
    private static var lastPrefetchDate: Date?
    private static let prefetchCooldown: TimeInterval = 300 // 5 minutes

    static func prefetchAllRepos() async {
        if let last = lastPrefetchDate, Date().timeIntervalSince(last) < prefetchCooldown {
            return
        }
        lastPrefetchDate = Date()

        let repos = FlekInstallerView.loadRepos()
        let cache = RepoCatalogCache.shared
        await withTaskGroup(of: Void.self) { group in
            for repo in repos where !FlekInstallerView.isFlekstore(repo) {
                let url = repo.sourceURL
                group.addTask { @MainActor in
                    let vm = FlekstoreAppsListViewModel()
                    vm.repository = .custom(url: url)
                    await vm.fetchApps()
                    if !vm.apps.isEmpty {
                        cache.store(apps: vm.apps, for: url)
                    }
                }
            }
        }
    }

    private func performSearch(_ query: String) async {
        // Reload disk cache (may have been updated by background pre-fetch)
        let cache = RepoCatalogCache.shared
        for repo in repos where !FlekInstallerView.isFlekstore(repo) {
            if cachedApps[repo.sourceURL] == nil,
               let apps = cache.cachedApps(for: repo.sourceURL) {
                cachedApps[repo.sourceURL] = apps
            }
        }

        // Fetch any custom repos that still aren't cached
        let uncachedRepos = repos.filter { !FlekInstallerView.isFlekstore($0) && cachedApps[$0.sourceURL] == nil }
        if !uncachedRepos.isEmpty {
            await withTaskGroup(of: (String, [FSAppModel]).self) { group in
                for repo in uncachedRepos {
                    let url = repo.sourceURL
                    group.addTask { @MainActor in
                        let vm = FlekstoreAppsListViewModel()
                        vm.repository = .custom(url: url)
                        await vm.fetchApps()
                        return (url, vm.apps)
                    }
                }
                for await (url, apps) in group {
                    if !apps.isEmpty {
                        cachedApps[url] = apps
                        cache.store(apps: apps, for: url)
                    }
                }
            }
        }

        guard !Task.isCancelled else { return }

        // Filter + rank + cap OFF the main thread. A broad/short query otherwise
        // scans the entire catalog of every repo on the main actor and stalls the UI.
        let inputs = repos
            .filter { !FlekInstallerView.isFlekstore($0) }
            .map { RepoFilterInput(id: $0.sourceURL, name: $0.name, iconUrl: $0.iconUrl,
                                   apps: cachedApps[$0.sourceURL] ?? []) }
        let customSections = await Task.detached(priority: .userInitiated) {
            Self.filterRepos(inputs, query: query)
        }.value

        guard !Task.isCancelled else { return }

        // Reserve FlekStore's slot at the top with a loading placeholder so its
        // late-arriving server results fill in place instead of pushing the custom
        // sections down (which reshuffles the list mid-scroll).
        let flekRepo = repos.first(where: { FlekInstallerView.isFlekstore($0) })
        if let flekRepo {
            let placeholder = RepoSection(id: flekRepo.sourceURL, name: "FlekSt0re",
                                          iconUrl: flekRepo.iconUrl, isFlekstore: true,
                                          apps: [], isLoading: true)
            sections = [placeholder] + customSections
        } else {
            sections = customSections
        }

        // FlekStore: server-side search (requires API call)
        flekstoreVM.searchQuery = query
        await flekstoreVM.resetAndFetchApps()

        guard !Task.isCancelled else { return }

        var finalSections = customSections
        if let flekRepo, !flekstoreVM.apps.isEmpty {
            let capped = Array(flekstoreVM.apps.prefix(Self.maxResultsPerRepo))
            finalSections.insert(RepoSection(id: flekRepo.sourceURL, name: "FlekSt0re",
                                             iconUrl: flekRepo.iconUrl, isFlekstore: true, apps: capped), at: 0)
        }

        if !Task.isCancelled {
            sections = finalSections
            isLoading = false
        }
    }

    /// Sendable snapshot handed to the off-main filter (no actor-isolated state).
    private struct RepoFilterInput: Sendable {
        let id: String
        let name: String
        let iconUrl: String
        let apps: [FSAppModel]
    }

    /// Pure, main-actor-independent filter. Ranks prefix matches ahead of substring
    /// matches and caps each repo to `maxResultsPerRepo`, so even a 1‑character query
    /// returns a bounded, relevant set instead of the whole catalog.
    nonisolated private static func filterRepos(_ inputs: [RepoFilterInput], query: String) -> [RepoSection] {
        let q = query.lowercased()
        guard !q.isEmpty else { return [] }

        var out: [RepoSection] = []
        for input in inputs {
            var prefixMatches: [FSAppModel] = []
            var containsMatches: [FSAppModel] = []
            for app in input.apps {
                if prefixMatches.count >= maxResultsPerRepo { break }
                let name = app.app_name.lowercased()
                if name.hasPrefix(q) {
                    prefixMatches.append(app)
                } else if containsMatches.count < maxResultsPerRepo, name.contains(q) {
                    containsMatches.append(app)
                }
            }
            var matched = prefixMatches
            if matched.count < maxResultsPerRepo {
                matched.append(contentsOf: containsMatches.prefix(maxResultsPerRepo - matched.count))
            }
            if !matched.isEmpty {
                out.append(RepoSection(id: input.id, name: input.name, iconUrl: input.iconUrl,
                                       isFlekstore: false, apps: matched))
            }
        }
        return out
    }
}

// MARK: - Row views

/// An installed-app result. Observes the model so hiding state changes — an unhide
/// from the menu — redraw the row instead of leaving a stale lock badge.
private struct FlekSearchResultRow: View {
    @ObservedObject var app: LCAppModel
    let darkModeIcon: Bool
    var onSelect: () -> Void
    var menu: () -> AnyView

    var body: some View {
        Button(action: onSelect) {
            FlekSearchRow(app: app, darkModeIcon: darkModeIcon, isLocked: app.uiIsLocked)
        }
        .buttonStyle(.plain)
        .contextMenu { menu() }
    }
}

private struct FlekSearchRow: View {
    let app: LCAppModel
    let darkModeIcon: Bool
    let isLocked: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(uiImage: app.appInfo.iconIsDarkIcon(darkModeIcon))
                .resizable().scaledToFill()
                .frame(width: 64, height: 64)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(app.appInfo.displayName() ?? "?")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                    // Hidden apps are reachable from search only, so say so here:
                    // tapping one asks for Face ID before it launches.
                    if isLocked {
                        Image(systemName: "lock.fill")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(Color.white.opacity(0.6))
                    }
                }
                Text("\(app.appInfo.version() ?? "?") - \(app.appInfo.bundleIdentifier() ?? "?")")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.7))
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Color.white.opacity(0.6))
                .padding(.trailing, 10)
        }
        .padding(.horizontal, 6)
        .frame(height: 74)
        .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct FlekSearchRowPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.72 : 1)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.16), value: configuration.isPressed)
    }
}

/// A result from a source. The row opens the app's page in the installer; the
/// download button on its right, which sits over the row rather than inside it,
/// installs without the detour.
private struct FlekStoreSearchResultRow: View {
    let app: FSAppModel
    var onOpen: () -> Void
    var onInstall: () -> Void

    var body: some View {
        Button(action: onOpen) {
            FlekStoreSearchRow(app: app)
        }
        // The row leads somewhere, so it answers a press — otherwise the only
        // part of it that visibly reacts is the download button beside it.
        .buttonStyle(FlekSearchRowPressStyle())
        .overlay(alignment: .trailing) {
            Button(action: onInstall) {
                Image(systemName: "arrow.down.circle")
                    .font(.system(size: 24))
                    .foregroundStyle(Color.white)
                    // A full-size target around a 24pt glyph, so the button can
                    // be hit without opening the page instead.
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.trailing, 6)
        }
    }
}

private struct FlekStoreSearchRow: View {
    let app: FSAppModel

    var body: some View {
        HStack(spacing: 12) {
            FlekRemoteIcon(url: app.app_icon, size: 64, corner: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(app.app_name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Color.white)
                    .lineLimit(1)
                Text("\(app.app_version)")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.7))
                    .lineLimit(1)

            }
            Spacer(minLength: 4)
            // Room for the download button, which is overlaid on top of the row.
            Color.clear.frame(width: 44, height: 44)
        }
        .padding(.horizontal, 6)
        .frame(height: 74)
        .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

// MARK: - Glass background

/// Stable Liquid Glass, independent of theme AND of the wallpaper behind it.
///
/// Keeps the real translucent/refractive glass (Telegram's approach) instead of
/// hiding it behind an opaque plate. `StableLiquidGlass` pins the glass tone via
/// a swizzled luma clamp (see LiquidGlassStable.swift), so it never re-tints to
/// match the content behind it. Fixed dark look to match the white UI.
private struct GlassBackground<S: InsettableShape>: ViewModifier {
    let shape: S
    @Environment(\.colorScheme) private var colorScheme

    private var isDark: Bool { colorScheme == .dark }

    // Pinned per theme. Subtle sheen on dark glass; a stronger white tint in
    // light theme so the pill reads as bright frosted glass, not thin/see-through.
    private var glassTint: UIColor {
        isDark ? UIColor(white: 1.0, alpha: 0.03)
               : UIColor(white: 1.0, alpha: 0.06)   // pale white sheen in light theme
    }

    func body(content: Content) -> some View {
        if #available(iOS 26, *) {
            content
                .background {
                    StableLiquidGlass(isDark: isDark, tint: glassTint)
                        .clipShape(shape)
                }
        } else {
            content
                .background {
                    ZStack {
                        shape.fill(.ultraThinMaterial)
                        shape.fill((isDark ? Color.black : Color.white).opacity(isDark ? 0.35 : 0.06))
                        shape.strokeBorder(Color.white.opacity(0.18), lineWidth: 0.5)
                    }
                }
                .compositingGroup()
        }
    }
}

private extension View {
    func searchPillBackground()   -> some View { modifier(GlassBackground(shape: Capsule())) }
    func searchCircleBackground() -> some View { modifier(GlassBackground(shape: Circle())) }
}
