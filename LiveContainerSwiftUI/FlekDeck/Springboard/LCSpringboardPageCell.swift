//
//  LCSpringboardPageCell.swift
//  LiveContainerSwiftUI
//
//  One page of the springboard grid. Contains an inner UICollectionView
//  showing LCSpringboardIconCells in a grid layout.
//

import UIKit

protocol LCSpringboardPageCellDelegate: AnyObject {
    func pageCell(_ pageCell: LCSpringboardPageCell, didTapItem item: FlekHomeItem)
    func pageCell(_ pageCell: LCSpringboardPageCell, didTapDeleteFor item: FlekHomeItem)
    func pageCell(_ pageCell: LCSpringboardPageCell, contextMenuFor item: FlekHomeItem) -> UIMenu?
}

final class LCSpringboardPageCell: UICollectionViewCell {
    weak var delegate: LCSpringboardPageCellDelegate?

    var items: [FlekHomeItem] = []
    var draggedItemId: String?
    var darkModeIcon: Bool = false
    private(set) var isEditing = false
    private var isContextMenuActive = false
    private var pendingReloadItems: [FlekHomeItem]?

    let collectionView: UICollectionView = {
        let layout = UICollectionViewFlowLayout()
        layout.scrollDirection = .vertical
        layout.minimumLineSpacing = 8
        layout.minimumInteritemSpacing = 0
        let cv = UICollectionView(frame: .zero, collectionViewLayout: layout)
        cv.backgroundColor = .clear
        cv.clipsToBounds = false
        cv.isScrollEnabled = false
        cv.showsVerticalScrollIndicator = false
        cv.contentInsetAdjustmentBehavior = .never
        cv.register(LCSpringboardIconCell.self, forCellWithReuseIdentifier: "IconCell")
        return cv
    }()

    // MARK: - Layout configuration

    /// Vibe's column setting feeds the same functions used by page capacity and
    /// drag/reorder math. This is deliberately not a visual-only scale.
    static var phoneColumns: Int { FlekAppearanceStore.gridColumns }

    private static let phoneSpacing: CGFloat = 8
    private static let phoneSideMargin: CGFloat = 28
    private static let phoneBottomReserve: CGFloat = 30
    private static let padMinWidth: CGFloat = 600

    /// Preserve FlekDeck's established iPad layout until the user explicitly
    /// chooses a Vibe column count. Once selected, the count applies to both
    /// orientations and rows are derived around the original ~24-icon capacity.
    private static let padPortraitGrid = (columns: 4, rows: 6)
    private static let padLandscapeGrid = (columns: 6, rows: 4)
    private static let padGridWidthFraction: CGFloat = 0.66
    private static let padCellWidthFraction: CGFloat = 0.95
    private static let padCellWidthRange: ClosedRange<CGFloat> = 72...145
    private static let padMinCellHeight: CGFloat = 82
    private static let padMinSpacing: CGFloat = 10
    private static let padMaxSpacing: CGFloat = 20
    private static let padBottomReserve: CGFloat = 34

    static let gridTopPadding: CGFloat = 46
    private static let barClearance: CGFloat = 18

    static func gridBottomPadding(safeAreaBottom: CGFloat) -> CGFloat {
        max(0, FlekTheme.bottomBarScreenMargin + FlekTheme.bottomBarControlSize
               + barClearance - safeAreaBottom)
    }

    static func usesPadGrid(pageSize: CGSize) -> Bool {
        UIDevice.current.userInterfaceIdiom == .pad && pageSize.width >= padMinWidth
    }

    private static func padGrid(forPageSize size: CGSize) -> (columns: Int, rows: Int) {
        if let override = FlekAppearanceStore.gridColumnsOverride {
            let columns = min(max(override, 2), 8)
            let rows = max(2, Int((24.0 / Double(columns)).rounded()))
            return (columns, rows)
        }
        return size.width > size.height ? padLandscapeGrid : padPortraitGrid
    }

    static func columns(forPageSize size: CGSize) -> Int {
        usesPadGrid(pageSize: size) ? padGrid(forPageSize: size).columns : phoneColumns
    }

    private static func padColumnPitch(forPageSize size: CGSize) -> CGFloat {
        size.width * padGridWidthFraction / CGFloat(max(1, padGrid(forPageSize: size).columns))
    }

    static func computeCellWidth(forPageSize size: CGSize) -> CGFloat {
        let columns = max(1, columns(forPageSize: size))
        if !usesPadGrid(pageSize: size) {
            let screenWidth = max(size.width, 320)
            let cols = CGFloat(columns)
            let totalSpacing = phoneSpacing * CGFloat(max(0, columns - 1))
            let availableWidth = screenWidth - (phoneSideMargin * 2) - totalSpacing
            return max(44, floor(availableWidth / cols))
        }
        let target = padColumnPitch(forPageSize: size) * padCellWidthFraction
        return floor(min(max(target, padCellWidthRange.lowerBound), padCellWidthRange.upperBound))
    }

    private static let cellAspect: (width: CGFloat, height: CGFloat) = (11, 12)

    static func computeCellHeight(forPageSize size: CGSize) -> CGFloat {
        let fromAspect = floor(computeCellWidth(forPageSize: size)
                               * cellAspect.height / cellAspect.width)
        return usesPadGrid(pageSize: size) ? max(fromAspect, padMinCellHeight) : fromAspect
    }

    static func interitemSpacing(forPageSize size: CGSize) -> CGFloat {
        guard usesPadGrid(pageSize: size) else { return phoneSpacing }
        let gap = padColumnPitch(forPageSize: size) - computeCellWidth(forPageSize: size)
        return floor(min(max(gap, padMinSpacing), padMaxSpacing))
    }

    static func computeHorizontalInset(forPageSize size: CGSize) -> CGFloat {
        let screenWidth = max(size.width, 320)
        let columns = max(1, columns(forPageSize: size))
        let cols = CGFloat(columns)
        let totalSpacing = interitemSpacing(forPageSize: size) * CGFloat(max(0, columns - 1))
        let cellWidth = computeCellWidth(forPageSize: size)
        let inset = (screenWidth - (cellWidth * cols) - totalSpacing) / 2
        return max(4, usesPadGrid(pageSize: size) ? floor(inset) : inset)
    }

    private static func padVerticalLayout(forPageSize size: CGSize)
        -> (rows: Int, lineSpacing: CGFloat, topInset: CGFloat) {
        let cellHeight = computeCellHeight(forPageSize: size)
        let available = max(0, size.height - padBottomReserve)
        var rows = padGrid(forPageSize: size).rows
        while rows > 1,
              CGFloat(rows) * cellHeight + CGFloat(rows - 1) * padMinSpacing > available {
            rows -= 1
        }
        let target = interitemSpacing(forPageSize: size)
        let spacing: CGFloat
        if rows > 1 {
            let widest = (available - CGFloat(rows) * cellHeight) / CGFloat(rows - 1)
            spacing = max(0, min(target, floor(widest)))
        } else {
            spacing = 0
        }
        let gridHeight = CGFloat(rows) * cellHeight + CGFloat(rows - 1) * spacing
        return (rows, spacing, max(0, floor((available - gridHeight) / 2)))
    }

    static func padItemsPerPage(forPageSize size: CGSize) -> Int? {
        guard usesPadGrid(pageSize: size) else { return nil }
        return max(1, padVerticalLayout(forPageSize: size).rows * columns(forPageSize: size))
    }

    static func phoneRows(forPageSize size: CGSize) -> Int {
        let cellHeight = computeCellHeight(forPageSize: size)
        let available = size.height - phoneBottomReserve
        guard cellHeight > 0, available > 0 else { return 1 }
        return max(1, Int((available + phoneSpacing) / (cellHeight + phoneSpacing)))
    }

    static func itemsPerPage(forPageSize size: CGSize) -> Int {
        if let padCount = padItemsPerPage(forPageSize: size) { return padCount }
        return max(1, phoneRows(forPageSize: size) * columns(forPageSize: size))
    }

    static func estimatedPageSize(screenSize: CGSize, safeAreaInsets: UIEdgeInsets) -> CGSize {
        CGSize(
            width: screenSize.width - safeAreaInsets.left - safeAreaInsets.right,
            height: screenSize.height - safeAreaInsets.top - safeAreaInsets.bottom
                - gridTopPadding - gridBottomPadding(safeAreaBottom: safeAreaInsets.bottom)
        )
    }

    // MARK: - Init / layout

    override init(frame: CGRect) {
        super.init(frame: frame)
        clipsToBounds = false
        contentView.clipsToBounds = false
        contentView.addSubview(collectionView)
        collectionView.dataSource = self
        collectionView.delegate = self
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layoutSubviews() {
        super.layoutSubviews()
        collectionView.frame = contentView.bounds
        updateFlowLayout()
    }

    private func updateFlowLayout() {
        guard let layout = collectionView.collectionViewLayout as? UICollectionViewFlowLayout else { return }
        let size = contentView.bounds.size
        let inset = Self.computeHorizontalInset(forPageSize: size)
        layout.itemSize = CGSize(width: Self.computeCellWidth(forPageSize: size),
                                 height: Self.computeCellHeight(forPageSize: size))
        layout.minimumInteritemSpacing = Self.interitemSpacing(forPageSize: size)
        if Self.usesPadGrid(pageSize: size) {
            let vertical = Self.padVerticalLayout(forPageSize: size)
            layout.minimumLineSpacing = vertical.lineSpacing
            layout.sectionInset = UIEdgeInsets(top: vertical.topInset, left: inset,
                                               bottom: Self.padBottomReserve, right: inset)
        } else {
            layout.minimumLineSpacing = Self.phoneSpacing
            layout.sectionInset = UIEdgeInsets(top: 0, left: inset,
                                               bottom: Self.phoneBottomReserve, right: inset)
        }
    }

    func refreshVisibleCells() {
        for cell in collectionView.visibleCells {
            guard let iconCell = cell as? LCSpringboardIconCell,
                  let idx = collectionView.indexPath(for: iconCell)?.item,
                  idx < items.count else { continue }
            iconCell.configure(with: items[idx], darkMode: darkModeIcon)
            iconCell.nameLabel.isHidden = !FlekAppearanceStore.showLabels
        }
    }

    // MARK: - Edit mode

    func enterEditingMode() {
        guard !isEditing else { return }
        isEditing = true
        for cell in collectionView.visibleCells {
            guard let iconCell = cell as? LCSpringboardIconCell, !iconCell.isPlaceholderCell else { continue }
            let idx = collectionView.indexPath(for: iconCell)?.item ?? 0
            let badge = idx < items.count ? items[idx].editBadge : .none
            iconCell.startJiggle()
            iconCell.setDeleteButtonVisible(badge != .none, animated: true)
        }
    }

    func leaveEditingMode() {
        guard isEditing else { return }
        isEditing = false
        for cell in collectionView.visibleCells {
            guard let iconCell = cell as? LCSpringboardIconCell else { continue }
            iconCell.stopJiggle()
            iconCell.setDeleteButtonVisible(false, animated: true)
        }
    }

    func rowsPerPage() -> Int {
        let size = contentView.bounds.size
        return Self.usesPadGrid(pageSize: size)
            ? Self.padVerticalLayout(forPageSize: size).rows
            : Self.phoneRows(forPageSize: size)
    }

    func itemsPerPage() -> Int { Self.itemsPerPage(forPageSize: contentView.bounds.size) }

    /// Reload items, deferring while a context menu is active. Single deletion
    /// keeps the existing shrink animation so this port does not regress Flek's
    /// SpringBoard interaction quality.
    func safeReloadItems(_ newItems: [FlekHomeItem]) {
        if isContextMenuActive {
            pendingReloadItems = newItems
            return
        }
        if newItems.count == items.count - 1 {
            let oldIDs = Set(items.map(\.id))
            let newIDs = Set(newItems.map(\.id))
            let removed = oldIDs.subtracting(newIDs)
            if removed.count == 1, let removedID = removed.first,
               let index = items.firstIndex(where: { $0.id == removedID }),
               let cell = collectionView.cellForItem(at: IndexPath(item: index, section: 0)) as? LCSpringboardIconCell {
                UIView.animate(withDuration: FlekAppearanceStore.reduceMotion ? 0.01 : 0.25, animations: {
                    cell.iconImageView.transform = CGAffineTransform.identity.scaledBy(x: 0.0001, y: 0.0001)
                    cell.nameLabel.alpha = 0
                    cell.contentView.alpha = 0
                }, completion: { _ in
                    self.items = newItems
                    self.collectionView.performBatchUpdates({
                        self.collectionView.deleteItems(at: [IndexPath(item: index, section: 0)])
                    }, completion: { _ in
                        cell.iconImageView.transform = .identity
                        cell.nameLabel.alpha = 1
                        cell.contentView.alpha = 1
                    })
                })
                return
            }
        }
        items = newItems
        collectionView.reloadData()
    }
}

// MARK: - UICollectionViewDataSource

extension LCSpringboardPageCell: UICollectionViewDataSource {
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        items.count
    }

    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "IconCell", for: indexPath) as! LCSpringboardIconCell
        let item = items[indexPath.item]
        cell.configure(with: item, darkMode: darkModeIcon)
        cell.nameLabel.isHidden = !FlekAppearanceStore.showLabels

        if isEditing && !cell.isPlaceholderCell {
            cell.startJiggle()
            cell.setDeleteButtonVisible(item.editBadge != .none, animated: false)
        } else {
            cell.stopJiggle()
            cell.setDeleteButtonVisible(false, animated: false)
        }

        if let dragId = draggedItemId, item.id == dragId {
            cell.contentView.isHidden = true
        } else if !cell.isPlaceholderCell {
            cell.contentView.isHidden = false
        }

        cell.onTap = { [weak self] in
            guard let self else { return }
            self.delegate?.pageCell(self, didTapItem: item)
        }
        cell.onDeleteTap = { [weak self] in
            guard let self else { return }
            self.delegate?.pageCell(self, didTapDeleteFor: item)
        }
        return cell
    }
}

// MARK: - UICollectionViewDelegate / context menus

extension LCSpringboardPageCell: UICollectionViewDelegate {
    func collectionView(_ collectionView: UICollectionView, shouldHighlightItemAt indexPath: IndexPath) -> Bool { false }

    private(set) static weak var activeContextMenuInteraction: UIContextMenuInteraction?
    private static var activeContextMenuRefresh: (() -> UIMenu?)?
    private static weak var activeContextMenuPageCell: LCSpringboardPageCell?
    private static var activeContextMenuIndexPath: IndexPath?

    static func refreshActiveContextMenu() {
        guard #available(iOS 16.0, *),
              let interaction = activeContextMenuInteraction,
              let refresh = activeContextMenuRefresh else { return }
        interaction.updateVisibleMenu { _ in refresh() ?? UIMenu(children: []) }
    }

    static func refreshActiveCellBadge() {
        guard let pageCell = activeContextMenuPageCell,
              let ip = activeContextMenuIndexPath,
              let cell = pageCell.collectionView.cellForItem(at: ip) as? LCSpringboardIconCell else { return }
        cell.updateBadge()
    }

    func collectionView(_ collectionView: UICollectionView,
                        contextMenuConfigurationForItemAt indexPath: IndexPath,
                        point: CGPoint) -> UIContextMenuConfiguration? {
        guard !isEditing else { return nil }
        let item = items[indexPath.item]
        guard !item.isPlaceholder,
              let menu = delegate?.pageCell(self, contextMenuFor: item) else { return nil }

        Self.activeContextMenuPageCell = self
        Self.activeContextMenuIndexPath = indexPath
        Self.activeContextMenuRefresh = { [weak self] in
            guard let self else { return nil }
            return self.delegate?.pageCell(self, contextMenuFor: item)
        }
        return UIContextMenuConfiguration(identifier: indexPath as NSCopying, previewProvider: nil) { _ in menu }
    }

    func collectionView(_ collectionView: UICollectionView,
                        previewForHighlightingContextMenuWithConfiguration configuration: UIContextMenuConfiguration) -> UITargetedPreview? {
        targetedPreview(collectionView, configuration)
    }

    func collectionView(_ collectionView: UICollectionView,
                        previewForDismissingContextMenuWithConfiguration configuration: UIContextMenuConfiguration) -> UITargetedPreview? {
        targetedPreview(collectionView, configuration)
    }

    private func targetedPreview(_ collectionView: UICollectionView,
                                 _ configuration: UIContextMenuConfiguration) -> UITargetedPreview? {
        guard let indexPath = configuration.identifier as? IndexPath,
              let cell = collectionView.cellForItem(at: indexPath) as? LCSpringboardIconCell else { return nil }
        let params = UIPreviewParameters()
        params.backgroundColor = .clear
        params.visiblePath = UIBezierPath(roundedRect: cell.iconImageView.bounds,
                                          cornerRadius: LCSpringboardIconCell.iconCornerRadius)
        params.shadowPath = UIBezierPath()
        return UITargetedPreview(view: cell.iconImageView, parameters: params)
    }

    func collectionView(_ collectionView: UICollectionView,
                        willDisplayContextMenu configuration: UIContextMenuConfiguration,
                        animator: (any UIContextMenuInteractionAnimating)?) {
        isContextMenuActive = true
        for interaction in collectionView.interactions {
            if let context = interaction as? UIContextMenuInteraction {
                Self.activeContextMenuInteraction = context
                break
            }
        }
    }

    func collectionView(_ collectionView: UICollectionView,
                        willEndContextMenuInteraction configuration: UIContextMenuConfiguration,
                        animator: (any UIContextMenuInteractionAnimating)?) {
        Self.activeContextMenuInteraction = nil
        Self.activeContextMenuRefresh = nil
        Self.activeContextMenuPageCell = nil
        Self.activeContextMenuIndexPath = nil

        let completion = { [weak self] in
            guard let self else { return }
            self.isContextMenuActive = false
            if let pending = self.pendingReloadItems {
                self.pendingReloadItems = nil
                self.items = pending
                self.collectionView.reloadData()
            }
        }
        if let animator { animator.addCompletion(completion) }
        else { completion() }
    }
}
