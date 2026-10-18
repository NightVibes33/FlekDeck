//
//  FlekSpringboardView.swift
//  LiveContainerSwiftUI
//
//  iOS-style paged home screen grid. Uses Dragula's DraggableView for smooth
//  UIKit-backed drag interactions. Supports cross-page icon movement via
//  edge auto-scroll zones (0.7 s timer, mirroring real SpringBoard).
//

import SwiftUI
import UniformTypeIdentifiers

struct FlekSpringboardView<Menu: View>: View {
    @Binding var items: [FlekHomeItem]
    let darkModeIcon: Bool
    @Binding var isEditing: Bool
    var isNew: (LCAppModel) -> Bool
    var isSingleMode: (LCAppModel) -> Bool
    var onTap: (FlekHomeItem) -> Void
    var onDelete: (FlekHomeItem) -> Void
    var onDropCompleted: () -> Void = {}
    var onCancelInstall: (InstallItem) -> Void = { _ in }
    /// Set by the parent to request scrolling to a specific page.
    /// Resets to nil after the scroll is performed.
    var scrollToPage: Binding<Int?> = .constant(nil)
    @ViewBuilder var contextMenu: (FlekHomeItem) -> Menu

    @State private var currentPage = 0
    @State private var draggedItem: FlekHomeItem?
    @State private var edgeScrollTimer: Timer?
    /// Page-based item model used during edit mode. Each sub-array
    /// is one page, allowing items to live on pages independently
    /// of the flat array's chunk boundaries.
    @State private var editPages: [[FlekHomeItem]] = []
    /// Persisted per-page item counts so page boundaries survive
    /// exiting edit mode and app restarts.
    @State private var customPageSizes: [Int] = []

    private var columns: [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: FlekTheme.gridSpacing),
              count: FlekTheme.gridColumns)
    }

    var body: some View {
        GeometryReader { geo in
            let spacing = FlekTheme.gridSpacing
            let reserve: CGFloat = 34
            let available = max(FlekTheme.cardHeight, geo.size.height - reserve)
            let baseRow = FlekTheme.cardHeight + spacing
            let fitRows = max(1, Int((available + spacing) / baseRow))
            let rows = max(5, fitRows)
            let cardHeight = min(FlekTheme.cardHeight, (available - CGFloat(rows - 1) * spacing) / CGFloat(rows))
            let perPage = max(1, rows * FlekTheme.gridColumns)

            // IDs of real (non-placeholder) items, used to detect confirmed
            // deletions while in edit mode.
            let realItemIds = items.filter { !$0.isPlaceholder }.map(\.id)

            // During edit mode, use the page-based model so items
            // can live on any page independently of flat-array chunking.
            let displayPages: [[FlekHomeItem]] = {
                if isEditing && !editPages.isEmpty {
                    var p = editPages
                    // Always ensure a trailing empty page of placeholders
                    let lastHasReal = p.last?.contains(where: { !$0.isPlaceholder }) ?? false
                    if p.isEmpty || lastHasReal {
                        p.append(padPage([], toSize: perPage))
                    }
                    return p
                }
                return paginatedItems(perPage: perPage)
            }()

            VStack(spacing: 8) {
                TabView(selection: $currentPage) {
                    ForEach(Array(displayPages.enumerated()), id: \.offset) { index, pageItems in
                        ZStack {
                            // Background drop zone catches drops on empty
                            // page areas (including entirely empty pages).
                            if isEditing {
                                Color.clear
                                    .contentShape(Rectangle())
                                    .onDrop(of: [UTType.text], delegate: PageBackgroundDropDelegate(
                                        pageIndex: index,
                                        pages: $editPages,
                                        draggedItem: $draggedItem
                                    ))
                            }

                            LazyVGrid(columns: columns, alignment: .center, spacing: spacing) {
                                if isEditing {
                                    ForEach(pageItems) { item in
                                        editCardWithDrag(for: item, cardHeight: cardHeight, pageIndex: index)
                                    }
                                } else {
                                    // App cards, installing card, and invisible placeholder spacers
                                    ForEach(pageItems) { item in
                                        if item.isPlaceholder {
                                            Color.clear.frame(height: cardHeight)
                                        } else if case .installing(let inst) = item {
                                            FlekInstallingCard(state: inst.installState, cardHeight: cardHeight)
                                                .contextMenu {
                                                    Button(role: .destructive) {
                                                        onCancelInstall(inst)
                                                    } label: {
                                                        Label("lc.flek.cancelInstall".loc, systemImage: FlekSymbol.cancelDownload)
                                                    }
                                                }
                                        } else {
                                            cardButton(for: item, cardHeight: cardHeight)
                                        }
                                    }
                                }
                            }
                            .padding(.horizontal, FlekTheme.screenHPadding)
                            .frame(maxHeight: .infinity, alignment: .top)

                            // Edge drop zones for cross-page auto-scroll.
                            // Only shown while a drag is active so they don't
                            // block taps on delete buttons along the edges.
                            if isEditing && draggedItem != nil {
                                edgeZones(pageIndex: index, pageCount: displayPages.count)
                            }
                        }
                        .tag(index)
                        .background(ClipDisabler())
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))

                Group {
                    if displayPages.count > 1 || isEditing {
                        FlekPageIndicator(count: displayPages.count, current: $currentPage, isEditing: isEditing)
                            .padding(.bottom, 4)
                            .transition(.opacity)
                    }
                }
                .animation(.easeInOut(duration: 0.2), value: isEditing)
            }
            .onAppear { loadPageSizes() }
            .onChange(of: isEditing) { editing in
                if editing {
                    // Entering edit mode: paginate and pad each page to perPage with placeholders
                    let raw: [[FlekHomeItem]]
                    if !customPageSizes.isEmpty {
                        raw = paginateWithSizes(items, sizes: customPageSizes, fallbackSize: perPage)
                    } else {
                        raw = chunk(items, size: perPage)
                    }
                    editPages = raw.map { padPage($0, toSize: perPage) }
                } else {
                    // Exiting edit mode: trim trailing all-placeholder pages, save, flatten
                    var pages = editPages
                    while pages.count > 1,
                          let last = pages.last,
                          last.allSatisfy(\.isPlaceholder) {
                        pages.removeLast()
                    }
                    savePageSizes(from: pages)
                    items = pages.flatMap { $0 }
                    // Persist order so placeholder positions survive rebuilds
                    onDropCompleted()
                    editPages = []
                    edgeScrollTimer?.invalidate()
                    edgeScrollTimer = nil
                    draggedItem = nil
                    // Clamp page if pages were removed
                    let newPages = paginatedItems(perPage: perPage)
                    if currentPage >= newPages.count {
                        currentPage = max(0, newPages.count - 1)
                    }
                }
            }
            .onChange(of: items.count) { _ in
                // Preserve the current page when items change (e.g. after
                // deletion). The paged TabView can reset to page 0 when its
                // content is rebuilt; capture the page now (before UIKit
                // processes layout) and restore it on the next run-loop.
                let savedPage = currentPage
                // Reload page sizes in case the parent trimmed empty
                // trailing pages from UserDefaults.
                loadPageSizes()
                DispatchQueue.main.async {
                    let newPages = paginatedItems(perPage: perPage)
                    let pageCount = newPages.count

                    if savedPage >= pageCount {
                        // Page no longer exists – go to last valid page
                        currentPage = max(0, pageCount - 1)
                    } else if savedPage == pageCount - 1 && savedPage > 0 {
                        // On the last page – if it's now all placeholders,
                        // move to the previous page
                        let pageItems = newPages[savedPage]
                        if !pageItems.contains(where: { !$0.isPlaceholder }) {
                            currentPage = savedPage - 1
                        } else {
                            currentPage = savedPage
                        }
                    } else {
                        // Stay on same page
                        currentPage = savedPage
                    }
                }
            }
            .onChange(of: realItemIds) { newIds in
                // A real item was removed (confirmed deletion) while in
                // edit mode – replace it with a placeholder then compact
                // the page so remaining icons fill the gap.
                guard isEditing, !editPages.isEmpty else { return }
                let idSet = Set(newIds)
                withAnimation {
                    for pi in editPages.indices {
                        var needsCompact = false
                        for ii in editPages[pi].indices {
                            let editItem = editPages[pi][ii]
                            guard !editItem.isPlaceholder else { continue }
                            if !idSet.contains(editItem.id) {
                                editPages[pi][ii] = .placeholder(UUID().uuidString)
                                needsCompact = true
                            }
                        }
                        if needsCompact {
                            PageBackgroundDropDelegate.compactPage(&editPages, at: pi)
                        }
                    }
                }
            }
            .onChange(of: scrollToPage.wrappedValue) { page in
                guard let page else { return }
                // Clear the request immediately so it doesn't re-trigger.
                scrollToPage.wrappedValue = nil
                // Already on the target page – nothing to animate.
                guard page != currentPage else { return }
                // Dispatch the animated page change to a later run loop
                // iteration so it doesn't compete with the layout
                // transaction that rebuilt the grid content.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    withAnimation(.smooth(duration: 0.45)) {
                        currentPage = page
                    }
                }
            }
        }
    }

    // MARK: - Pagination

    /// Chunks items into pages using custom page sizes if available,
    /// otherwise falls back to uniform chunking.
    private func paginatedItems(perPage: Int) -> [[FlekHomeItem]] {
        let pages: [[FlekHomeItem]]
        if !customPageSizes.isEmpty {
            pages = paginateWithSizes(items, sizes: customPageSizes, fallbackSize: perPage)
        } else {
            pages = chunk(items, size: perPage)
        }
        return pages
    }

    // MARK: - Edge Auto-Scroll Zones

    /// Invisible drop targets at the left/right edges of each page that
    /// trigger timed auto-scroll to adjacent pages during drag, mirroring
    /// iOS SpringBoard's 0.7 s edge dwell behaviour.
    @ViewBuilder
    private func edgeZones(pageIndex: Int, pageCount: Int) -> some View {
        HStack(spacing: 0) {
            // Left edge
            Color.clear
                .frame(width: 36)
                .contentShape(Rectangle())
                .onDrop(of: [UTType.text], delegate: EdgeScrollDelegate(
                    direction: -1,
                    currentPage: $currentPage,
                    maxPage: pageCount,
                    onStartTimer: { dir in startEdgeTimer(direction: dir) },
                    onCancelTimer: { cancelEdgeTimer() }
                ))

            Spacer()

            // Right edge
            Color.clear
                .frame(width: 36)
                .contentShape(Rectangle())
                .onDrop(of: [UTType.text], delegate: EdgeScrollDelegate(
                    direction: 1,
                    currentPage: $currentPage,
                    maxPage: pageCount,
                    onStartTimer: { dir in startEdgeTimer(direction: dir) },
                    onCancelTimer: { cancelEdgeTimer() }
                ))
        }
    }

    private func startEdgeTimer(direction: Int) {
        guard edgeScrollTimer == nil else { return }
        edgeScrollTimer = Timer.scheduledTimer(withTimeInterval: 0.7, repeats: false) { _ in
            let nextPage = currentPage + direction
            guard nextPage >= 0 else { edgeScrollTimer = nil; return }
            withAnimation {
                currentPage = nextPage
            }
            edgeScrollTimer = nil
        }
    }

    private func cancelEdgeTimer() {
        edgeScrollTimer?.invalidate()
        edgeScrollTimer = nil
    }

    // MARK: - Edit Mode Card (DraggableView-backed)

    @ViewBuilder
    private func editCardWithDrag(for item: FlekHomeItem, cardHeight: CGFloat, pageIndex: Int) -> some View {
        if item.isPlaceholder {
            // Invisible drop target for empty grid slots
            Color.clear.frame(height: cardHeight)
                .contentShape(Rectangle())
                .onDrop(of: [UTType.text], delegate: SpringboardReorderDelegate(
                    item: item,
                    pageIndex: pageIndex,
                    pages: $editPages,
                    draggedItem: $draggedItem
                ))
        } else if case .installing(let inst) = item {
            FlekInstallingCard(state: inst.installState, cardHeight: cardHeight)
        } else if item.isDraggable {
            editCard(for: item, cardHeight: cardHeight)
                .hidden()
                .overlay {
                    DraggableView(
                        preview: {
                            // Pass editBadge: .none so the corner control is never
                            // part of the DraggableView's snapshot.
                            FlekAppCard(
                                title: title(for: item),
                                isNew: newDot(for: item),
                                showsSingleModeBadge: singleBadge(for: item),
                                isEditing: true,
                                editBadge: .none,
                                cardHeight: cardHeight,
                                icon: { iconView(for: item) }
                            )
                        },
                        dropView: { cardDropPlaceholder(cardHeight: cardHeight) },
                        itemProvider: { item.getItemProvider() },
                        isBeingDragged: draggedItem?.id == item.id,
                        onDragWillBegin: { draggedItem = item },
                        onDragWillEnd: {
                            draggedItem = nil
                            cancelEdgeTimer()
                            // Save page sizes and sync back to flat array
                            savePageSizes(from: editPages)
                            items = editPages.flatMap { $0 }
                            onDropCompleted()
                        }
                    )
                }
                // Delete button rendered outside DraggableView so it never
                // appears in the drag snapshot.
                .overlay(alignment: .topLeading) {
                    if item.editBadge != .none && draggedItem == nil {
                        Button {
                            onDelete(item)
                        } label: {
                            Image(systemName: "minus")
                                .font(.system(size: 13, weight: .bold))
                                .foregroundStyle(.black)
                                .frame(width: 24, height: 24)
                                .background(Circle().fill(Color(white: 0.85)))
                                .overlay(Circle().strokeBorder(Color.black.opacity(0.15), lineWidth: 0.5))
                        }
                        .buttonStyle(.plain)
                        .offset(x: -6, y: -6)
                        .transition(.scale.combined(with: .opacity))
                    }
                }
                .onDrop(of: [UTType.text], delegate: SpringboardReorderDelegate(
                    item: item,
                    pageIndex: pageIndex,
                    pages: $editPages,
                    draggedItem: $draggedItem
                ))
                .environment(\.dragPreviewCornerRadius, FlekTheme.cardCorner)
        } else {
            editCard(for: item, cardHeight: cardHeight)
        }
    }

    @ViewBuilder
    private func editCard(for item: FlekHomeItem, cardHeight: CGFloat) -> some View {
        FlekAppCard(
            title: title(for: item),
            isNew: newDot(for: item),
            showsSingleModeBadge: singleBadge(for: item),
            isEditing: true,
            editBadge: item.editBadge,
            cardHeight: cardHeight,
            onDelete: { onDelete(item) },
            icon: { iconView(for: item) }
        )
    }

    /// Ghost placeholder shown in the original position while a card is dragged.
    @ViewBuilder
    private func cardDropPlaceholder(cardHeight: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: FlekTheme.cardCorner, style: .continuous)
            .fill(Color.white.opacity(0.08))
            .overlay(
                RoundedRectangle(cornerRadius: FlekTheme.cardCorner, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.15), lineWidth: 1, antialiased: true)
            )
            .frame(height: cardHeight)
    }

    // MARK: - Normal Mode Card

    /// Whether an app is currently being installed.
    private var isInstalling: Bool {
        items.contains { if case .installing = $0 { return true }; return false }
    }

    @ViewBuilder
    private func cardButton(for item: FlekHomeItem, cardHeight: CGFloat) -> some View {
        Button {
            onTap(item)
        } label: {
            FlekAppCard(
                title: title(for: item),
                isNew: newDot(for: item),
                showsSingleModeBadge: singleBadge(for: item),
                isEditing: false,
                editBadge: item.editBadge,
                cardHeight: cardHeight,
                onDelete: { onDelete(item) },
                icon: { iconView(for: item) }
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            if !isInstalling {
                contextMenu(item)
            }
        }
    }

    // MARK: - Helpers

    @ViewBuilder
    private func iconView(for item: FlekHomeItem) -> some View {
        switch item {
        case .defaultApp(let kind):
            Image(kind.iconAssetName)
                .resizable()
                .scaledToFill()
        case .installed(let app):
            Image(uiImage: app.appInfo.iconIsDarkIcon(darkModeIcon))
                .resizable()
                .scaledToFill()
        case .virtualApp(let app):
            Image(uiImage: app.icon ?? UIImage(systemName: "app.fill")!)
                .resizable()
                .scaledToFill()
        case .installing, .placeholder:
            Color.clear
        }
    }

    private func title(for item: FlekHomeItem) -> String {
        switch item {
        case .defaultApp(let kind): return kind.title
        case .installed(let app): return app.appInfo.displayName() ?? "?"
        case .virtualApp(let app): return app.title
        case .installing(let inst): return inst.name ?? ""
        case .placeholder: return ""
        }
    }

    private func newDot(for item: FlekHomeItem) -> Bool {
        if case .installed(let app) = item { return isNew(app) }
        return false
    }

    private func singleBadge(for item: FlekHomeItem) -> Bool {
        if case .installed(let app) = item { return isSingleMode(app) }
        return false
    }


    /// Pads a page with placeholder items to fill it to the given size.
    private func padPage(_ page: [FlekHomeItem], toSize size: Int) -> [FlekHomeItem] {
        guard page.count < size else { return Array(page.prefix(size)) }
        return page + (0 ..< (size - page.count)).map { _ in .placeholder(UUID().uuidString) }
    }

    private func chunk<T>(_ array: [T], size: Int) -> [[T]] {
        guard size > 0 else { return [array] }
        if array.isEmpty { return [[]] }
        return stride(from: 0, to: array.count, by: size).map {
            Array(array[$0 ..< min($0 + size, array.count)])
        }
    }

    /// Distributes items across pages using the given per-page sizes.
    /// Any items beyond the sum of `sizes` are chunked into additional
    /// pages of `fallbackSize` (handles newly installed apps).
    private func paginateWithSizes<T>(_ array: [T], sizes: [Int], fallbackSize: Int) -> [[T]] {
        guard !array.isEmpty else { return [[]] }
        var result: [[T]] = []
        var offset = 0
        for size in sizes where offset < array.count {
            let end = min(offset + size, array.count)
            result.append(Array(array[offset ..< end]))
            offset = end
        }
        // Remaining items (new installs) go into additional pages
        while offset < array.count {
            let end = min(offset + fallbackSize, array.count)
            result.append(Array(array[offset ..< end]))
            offset = end
        }
        return result
    }

    /// Saves the current page sizes to UserDefaults.
    private func savePageSizes(from pages: [[FlekHomeItem]]) {
        // Strip trailing empty pages before saving
        var sizes = pages.map { $0.count }
        while sizes.last == 0 { sizes.removeLast() }
        customPageSizes = sizes
        LCUtils.appGroupUserDefault.set(sizes, forKey: FlekDeckKeys.homeScreenPageSizes)
    }

    /// Loads page sizes from UserDefaults.
    private func loadPageSizes() {
        if let sizes = LCUtils.appGroupUserDefault.array(forKey: FlekDeckKeys.homeScreenPageSizes) as? [Int],
           !sizes.isEmpty {
            customPageSizes = sizes
        }
    }
}

// MARK: - Drop Delegates

/// Catches drops on empty page background areas. Swaps the dragged item
/// with the first available placeholder on the target page.
struct PageBackgroundDropDelegate: DropDelegate {
    let pageIndex: Int
    @Binding var pages: [[FlekHomeItem]]
    @Binding var draggedItem: FlekHomeItem?

    private let generator = UIImpactFeedbackGenerator(style: .rigid)

    func dropEntered(info: DropInfo) {
        guard let dragged = draggedItem else { return }

        // Materialize trailing placeholder page if it only exists in displayPages
        if pageIndex >= pages.count {
            let perPage = pages.first?.count ?? 1
            pages.append((0 ..< perPage).map { _ in .placeholder(UUID().uuidString) })
        }
        guard pageIndex < pages.count else { return }

        // Find the dragged item across all pages
        var fromPage = -1, fromIdx = -1
        for (pi, page) in pages.enumerated() {
            if let idx = page.firstIndex(where: { $0.id == dragged.id }) {
                fromPage = pi
                fromIdx = idx
                break
            }
        }
        guard fromPage >= 0, fromIdx >= 0, fromPage != pageIndex else { return }

        // Find first placeholder on the target page to swap with
        guard let targetIdx = pages[pageIndex].firstIndex(where: { $0.isPlaceholder }) else { return }

        withAnimation(.spring) {
            pages[pageIndex][targetIdx] = pages[fromPage][fromIdx]
            pages[fromPage][fromIdx] = .placeholder(UUID().uuidString)
            // Compact the source page so remaining items fill the gap
            Self.compactPage(&pages, at: fromPage)
        }

        generator.prepare()
        generator.impactOccurred()
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        draggedItem != nil
    }

    /// Moves all real items to the front of the page and fills remaining
    /// slots with fresh placeholders so there are no mid-page gaps.
    static func compactPage(_ pages: inout [[FlekHomeItem]], at pi: Int) {
        let real = pages[pi].filter { !$0.isPlaceholder }
        let padCount = pages[pi].count - real.count
        pages[pi] = real + (0..<padCount).map { _ in .placeholder(UUID().uuidString) }
    }
}

/// Swaps two items' grid positions when one is dragged over the other.
/// Works with both real items and placeholders (empty grid slots).
struct SpringboardReorderDelegate: DropDelegate {
    let item: FlekHomeItem
    let pageIndex: Int
    @Binding var pages: [[FlekHomeItem]]
    @Binding var draggedItem: FlekHomeItem?

    private let generator = UIImpactFeedbackGenerator(style: .rigid)

    func dropEntered(info: DropInfo) {
        guard let dragged = draggedItem, dragged.id != item.id else { return }

        // Materialize trailing placeholder page if it only exists in displayPages
        if pageIndex >= pages.count {
            let perPage = pages.first?.count ?? 1
            pages.append((0 ..< perPage).map { _ in .placeholder(UUID().uuidString) })
        }
        guard pageIndex < pages.count else { return }

        // Find the dragged item across all pages
        var fromPage = -1, fromIdx = -1
        for (pi, page) in pages.enumerated() {
            if let idx = page.firstIndex(where: { $0.id == dragged.id }) {
                fromPage = pi
                fromIdx = idx
                break
            }
        }
        guard fromPage >= 0, fromIdx >= 0 else { return }
        guard let toIdx = pages[pageIndex].firstIndex(where: { $0.id == item.id }) else { return }

        // For cross-page moves onto a placeholder, snap to the first
        // available placeholder so the item fills the earliest empty
        // slot instead of landing wherever the finger happens to be.
        let effectiveToIdx: Int
        if fromPage != pageIndex, item.isPlaceholder,
           let first = pages[pageIndex].firstIndex(where: { $0.isPlaceholder }) {
            effectiveToIdx = first
        } else {
            effectiveToIdx = toIdx
        }

        withAnimation(.spring) {
            // Swap: each item takes the other's grid position
            let temp = pages[pageIndex][effectiveToIdx]
            pages[pageIndex][effectiveToIdx] = pages[fromPage][fromIdx]
            pages[fromPage][fromIdx] = temp
            // Compact the source page when moving cross-page so
            // remaining items fill the gap left behind
            if fromPage != pageIndex {
                PageBackgroundDropDelegate.compactPage(&pages, at: fromPage)
            }
        }

        generator.prepare()
        generator.impactOccurred()
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        draggedItem != nil
    }
}

/// Flat-array reorder delegate used by the list layout (no pages).
struct ListReorderDelegate: DropDelegate {
    let item: FlekHomeItem
    @Binding var items: [FlekHomeItem]
    @Binding var draggedItem: FlekHomeItem?

    private let generator = UIImpactFeedbackGenerator(style: .rigid)

    func dropEntered(info: DropInfo) {
        guard let dragged = draggedItem, dragged.id != item.id else { return }
        guard let fromIndex = items.firstIndex(where: { $0.id == dragged.id }),
              let toIndex = items.firstIndex(where: { $0.id == item.id }) else { return }

        withAnimation(.spring) {
            items.move(fromOffsets: IndexSet(integer: fromIndex),
                       toOffset: toIndex > fromIndex ? toIndex + 1 : toIndex)
        }

        generator.prepare()
        generator.impactOccurred()
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        draggedItem != nil
    }
}

/// Detects drag-dwell at the left/right screen edge and triggers timed
/// auto-scroll to the adjacent page (0.7 s, matching iOS SpringBoard).
struct EdgeScrollDelegate: DropDelegate {
    let direction: Int
    @Binding var currentPage: Int
    let maxPage: Int
    let onStartTimer: (Int) -> Void
    let onCancelTimer: () -> Void

    func dropEntered(info: DropInfo) {
        let nextPage = currentPage + direction
        guard nextPage >= 0 && nextPage < maxPage else { return }
        onStartTimer(direction)
    }

    func dropExited(info: DropInfo) {
        onCancelTimer()
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        false
    }
}

/// Simple iOS-style page dots.
struct FlekPageIndicator: View {
    let count: Int
    @Binding var current: Int
    var isEditing: Bool = false

    var body: some View {
        HStack(spacing: 8) {
            ForEach(0 ..< count, id: \.self) { i in
                Circle()
                    .fill(Color.white.opacity(i == current ? 0.95 : 0.4))
                    .frame(width: 7, height: 7)
                    .contentShape(Circle().scale(3))
                    .onTapGesture {
                        withAnimation(.smooth(duration: 0.45)) {
                            current = i
                        }
                    }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .modifier(GlassBackgroundModifier(isActive: isEditing))
    }
}

/// Conditionally applies a Liquid Glass capsule background in edit mode.
private struct GlassBackgroundModifier: ViewModifier {
    let isActive: Bool

    // Erased to AnyView: an opaque return type would bake the iOS 26-only type
    // `glassEffect` produces into Body, and the runtime resolves Body before the
    // availability check ever runs — which traps on iOS 17.x, where that type
    // does not exist in the system SwiftUI.
    func body(content: Content) -> AnyView {
        guard isActive else { return AnyView(content) }
        if #available(iOS 26.0, *) {
            return AnyView(content.glassEffect(.regular.interactive(false)))
        }
        return AnyView(
            content
                .background(
                    Capsule()
                        .fill(.ultraThinMaterial)
                )
        )
    }
}

/// Invisible helper that walks up the UIKit view hierarchy and disables
/// `clipsToBounds` on every ancestor, preventing the TabView's internal
/// page container from clipping content that extends beyond cell bounds
/// (context menu lift, delete buttons, jiggle rotation, etc.).
private struct ClipDisabler: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isUserInteractionEnabled = false
        DispatchQueue.main.async { disableClipping(from: view) }
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        DispatchQueue.main.async { disableClipping(from: uiView) }
    }

    private func disableClipping(from view: UIView) {
        var v: UIView? = view.superview
        while let parent = v {
            if parent.clipsToBounds {
                parent.clipsToBounds = false
            }
            v = parent.superview
        }
    }
}
