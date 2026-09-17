//
//  LCSpringboardDragManager.swift
//  LiveContainerSwiftUI
//
//  Drag-and-drop state machine for the UIKit springboard.
//  Faithfully follows jSpringBoard's AppGridManager + AppGridManager+DragOperations
//  pattern, including savedState undo and moveLastItem cascade.
//

import UIKit

// MARK: - Drag operation state

final class LCDragOperation {
    /// The actual item being dragged.
    let item: FlekHomeItem
    var itemId: String { item.id }
    let placeholderView: UIView
    let dragOffset: CGSize
    let originalPage: Int
    let originalIndex: Int
    var currentPage: Int
    var currentIndex: Int
    /// When true, the item moved to a new page and the target PageCell
    /// hasn't appeared yet. updateDrag short-circuits until willDisplay fires.
    var needsUpdate: Bool = false
    /// Snapshot of vc.pages before a cascade overflow. Restored if the item
    /// moves to yet another page (undo previous cascade before doing a new one).
    var savedState: [[FlekHomeItem]]?

    init(item: FlekHomeItem, placeholderView: UIView, dragOffset: CGSize,
         originalPage: Int, originalIndex: Int) {
        self.item = item
        self.placeholderView = placeholderView
        self.dragOffset = dragOffset
        self.originalPage = originalPage
        self.originalIndex = originalIndex
        self.currentPage = originalPage
        self.currentIndex = originalIndex
    }
}

// MARK: - Drag manager

final class LCSpringboardDragManager: NSObject, UIGestureRecognizerDelegate {

    weak var viewController: LCSpringboardViewController?

    private(set) var currentOperation: LCDragOperation?
    private var pageScrollTimer: Timer?
    private let feedbackGenerator = UIImpactFeedbackGenerator(style: .medium)

    // Edge detection
    private let edgeMargin: CGFloat = 50
    private let pageScrollDelay: TimeInterval = 0.7

    var isDragging: Bool { currentOperation != nil }

    // MARK: - Gesture handler

    /// Installed app holds belong to UICollectionView's context-menu recognizer.
    /// Reject the root drag recognizer before it enters `.began`; cancelling it
    /// after `.began` is too late and can suppress the menu entirely.
    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let gesture = gestureRecognizer as? UILongPressGestureRecognizer,
              let vc = viewController,
              !vc.isInEditMode else {
            return true
        }

        let touchInView = gesture.location(in: vc.view)
        guard let (_, pageCell) = vc.pageCellAtPoint(touchInView) else {
            return true
        }

        let touchInPage = gesture.location(in: pageCell.collectionView)
        guard let indexPath = pageCell.collectionView.indexPathForItem(at: touchInPage),
              indexPath.item < pageCell.items.count else {
            // Empty-space holds still belong to FlekDeck's edit-mode gesture.
            return true
        }

        let item = pageCell.items[indexPath.item]
        if case .installed = item {
            return false
        }
        return true
    }

    func handleLongPress(_ gesture: UILongPressGestureRecognizer) {
        switch gesture.state {
        case .began:
            beginDrag(gesture)
        case .changed:
            updateDrag(gesture)
        default:
            endDrag(gesture)
        }
    }

    // MARK: - Begin

    private func beginDrag(_ gesture: UILongPressGestureRecognizer) {
        guard let vc = viewController else { return }

        feedbackGenerator.prepare()

        let touchInView = gesture.location(in: vc.view)
        guard let (pageIndex, pageCell) = vc.pageCellAtPoint(touchInView) else { return }

        let touchInPage = gesture.location(in: pageCell.collectionView)

        // Check if touch landed on an icon cell
        let hitIconCell: LCSpringboardIconCell?
        if let indexPath = pageCell.collectionView.indexPathForItem(at: touchInPage),
           let iconCell = pageCell.collectionView.cellForItem(at: indexPath) as? LCSpringboardIconCell,
           !iconCell.isPlaceholderCell {
            hitIconCell = iconCell
        } else {
            hitIconCell = nil
        }

        // Not in edit mode: long press on empty space or default app → enter edit mode
        // Long press on an installed app icon is handled by context menu, so cancel the gesture
        if !vc.isInEditMode {
            let isDefaultApp: Bool
            if let iconCell = hitIconCell,
               let indexPath = pageCell.collectionView.indexPath(for: iconCell) {
                let item = pageCell.items[indexPath.item]
                if case .defaultApp = item { isDefaultApp = true } else { isDefaultApp = false }
            } else {
                isDefaultApp = false
            }

            if hitIconCell == nil {
                // Empty space → enter edit mode only
                feedbackGenerator.impactOccurred()
                vc.setEditing(true)
                gesture.isEnabled = false
                gesture.isEnabled = true
                return
            }

            if isDefaultApp {
                // Default app → enter edit mode and continue to start drag below
                feedbackGenerator.impactOccurred()
                vc.setEditing(true)
            } else {
                // Installed app → the recognizer delegate should already have
                // rejected this drag so UIKit can present the context menu.
                return
            }
        }

        // In edit mode (or just entered for default app): start drag on an icon
        guard let iconCell = hitIconCell else { return }

        let indexPath = pageCell.collectionView.indexPath(for: iconCell)!
        let item = pageCell.items[indexPath.item]
        guard item.isDraggable else { return }

        // Offset so the snapshot stays centered under the finger
        let dragOffset = CGSize(
            width: iconCell.center.x - touchInPage.x,
            height: iconCell.center.y - touchInPage.y
        )

        // Custom per-subview snapshot (avoids dark blur artefact from whole-cell snapshot)
        let snapshot = iconCell.dragSnapshotView()
        var snapshotCenter = touchInView
        snapshotCenter.x += dragOffset.width
        snapshotCenter.y += dragOffset.height
        snapshot.center = snapshotCenter
        vc.view.addSubview(snapshot)

        // jSpringBoard hides contentView only (not the whole cell)
        iconCell.contentView.isHidden = true

        UIView.animate(withDuration: 0.25) {
            snapshot.transform = CGAffineTransform.identity.scaledBy(x: 1.3, y: 1.3)
            snapshot.alpha = 0.8
            // Animate delete button visible on the snapshot (jSpringBoard pattern)
            snapshot.deleteButtonSnapshot?.transform = .identity
            snapshot.deleteButtonSnapshot?.alpha = 1
            snapshot.deleteButtonSnapshot?.isHidden = false
        }

        currentOperation = LCDragOperation(
            item: item,
            placeholderView: snapshot,
            dragOffset: dragOffset,
            originalPage: pageIndex,
            originalIndex: indexPath.item
        )

        pageCell.draggedItemId = item.id
    }

    // MARK: - Update (within-page: moveItem only, no data model changes)
    // Faithfully follows jSpringBoard's updateDragOperation including
    // left/right half detection, same-line adjustment, and edge cell logic.

    private func updateDrag(_ gesture: UILongPressGestureRecognizer) {
        guard let vc = viewController, let op = currentOperation else { return }

        let touchInView = gesture.location(in: vc.view)

        // Move snapshot to follow touch
        var snapshotCenter = touchInView
        snapshotCenter.x += op.dragOffset.width
        snapshotCenter.y += op.dragOffset.height
        op.placeholderView.center = snapshotCenter

        // If a cross-page scroll is pending, don't do any rearrangement
        if op.needsUpdate {
            return
        }

        // Find current page cell
        guard let pageCell = vc.visiblePageCell(forPage: op.currentPage) else { return }
        let touchInPage = gesture.location(in: pageCell.collectionView)
        guard let layout = pageCell.collectionView.collectionViewLayout as? UICollectionViewFlowLayout else { return }

        let appsPerRow = LCSpringboardPageCell.columns(forPageSize: pageCell.bounds.size)

        var destinationIndex: Int
        var isEdgeCell = false

        if let indexPath = pageCell.collectionView.indexPathForItem(at: touchInPage) {
            // jSpringBoard: use cardFrame.midX to determine left/right half
            guard let itemCell = pageCell.collectionView.cellForItem(at: indexPath) as? LCSpringboardIconCell else { return }

            let convertedPoint = itemCell.convert(touchInPage, from: pageCell.collectionView)
            let midX = itemCell.bounds.midX

            if convertedPoint.x < midX {
                destinationIndex = indexPath.item
            } else {
                // Right half: if at row edge (last column), stay on same index
                if (indexPath.item + 1) % appsPerRow == 0 {
                    destinationIndex = indexPath.item
                    isEdgeCell = true
                } else {
                    destinationIndex = indexPath.item + 1
                }
            }
        } else if touchInPage.x <= edgeMargin {
            // Left edge — trigger page scroll
            if !(pageScrollTimer?.isValid ?? false) {
                startPageScrollTimer(direction: -1)
            }
            return
        } else if touchInPage.x > pageCell.collectionView.frame.size.width - edgeMargin {
            // Right edge — trigger page scroll
            if !(pageScrollTimer?.isValid ?? false) {
                startPageScrollTimer(direction: 1)
            }
            return
        } else {
            // Gap between cells — try with +15px offset (jSpringBoard pattern)
            var adjustedPoint = touchInPage
            adjustedPoint.x += 15
            if let indexPath = pageCell.collectionView.indexPathForItem(at: adjustedPoint) {
                destinationIndex = indexPath.item
            } else {
                cancelPageScrollTimer()
                return
            }
        }

        cancelPageScrollTimer()

        // jSpringBoard: first/last item in row is an edge cell
        if destinationIndex % appsPerRow == 0 {
            isEdgeCell = true
        }

        // jSpringBoard "same line" adjustment:
        // On the same line, the dragged app takes the place of the app on its left.
        // On other lines it takes the place of the app on its right.
        let destinationLine = destinationIndex / appsPerRow
        let originalLine = op.originalIndex / appsPerRow
        if destinationLine == originalLine && op.currentPage == op.originalPage && !isEdgeCell {
            destinationIndex -= 1
        }

        // Boundary clamping (jSpringBoard pattern — clamp instead of returning)
        let numberOfItems = pageCell.collectionView.numberOfItems(inSection: 0)
        if destinationIndex >= numberOfItems && destinationIndex > 0 {
            destinationIndex = numberOfItems - 1
        } else if destinationIndex < 0 {
            destinationIndex = 0
        }

        if destinationIndex == op.currentIndex { return }

        // jSpringBoard pattern: only call moveItem if both indices are valid
        guard op.currentIndex < numberOfItems && destinationIndex < numberOfItems else { return }

        // jSpringBoard pattern: only call moveItem, do NOT touch the data model.
        // The data model is synced at end-of-drag via updateState().
        pageCell.collectionView.moveItem(at: IndexPath(item: op.currentIndex, section: 0),
                                         to: IndexPath(item: destinationIndex, section: 0))
        op.currentIndex = destinationIndex
    }

    // MARK: - End

    private func endDrag(_ gesture: UILongPressGestureRecognizer) {
        guard let vc = viewController, let op = currentOperation else { return }

        cancelPageScrollTimer()

        // jSpringBoard pattern: read the UI state back into the data model.
        if let pageCell = vc.visiblePageCell(forPage: op.currentPage) {
            updateState(forPageCell: pageCell, pageIndex: op.currentPage)
        }

        // Sync flatItems and page sizes back to SwiftUI so page
        // boundaries survive through persistence and rebuild.
        vc.syncPagesToSwiftUI()

        // jSpringBoard: fix inconsistencies BEFORE the slide-back animation.
        // Skip the dragged cell — it stays hidden until the animation completes.
        for cell in vc.outerCollectionView.visibleCells {
            guard let pageCell = cell as? LCSpringboardPageCell else { continue }
            for iconCell in pageCell.collectionView.visibleCells {
                guard let iconCell = iconCell as? LCSpringboardIconCell else { continue }
                if let configItem = iconCell.configuredItem, configItem.id == op.itemId {
                    continue
                }
                iconCell.nameLabel.alpha = 1
                iconCell.contentView.isHidden = false
                if vc.isInEditMode {
                    iconCell.startJiggle(force: true)
                }
            }
        }

        // Animate snapshot back into position
        if let pageCell = vc.visiblePageCell(forPage: op.currentPage),
           op.currentIndex < pageCell.collectionView.numberOfItems(inSection: 0),
           let targetCell = pageCell.collectionView.cellForItem(at: IndexPath(item: op.currentIndex, section: 0)) {

            let convertedFrame = pageCell.collectionView.convert(targetCell.frame, to: vc.view)
            UIView.animate(withDuration: 0.25, animations: {
                op.placeholderView.transform = .identity
                op.placeholderView.frame = convertedFrame
            }, completion: { _ in
                // Only unhide the dragged cell and clear state in completion
                targetCell.contentView.isHidden = false
                op.placeholderView.removeFromSuperview()
                self.currentOperation = nil
                for cell in vc.outerCollectionView.visibleCells {
                    (cell as? LCSpringboardPageCell)?.draggedItemId = nil
                }
                // Apply any item changes that arrived while dragging
                // (e.g. an installing app finished and became .installed).
                vc.applyPendingItemsIfNeeded()
                // The icon has landed, so a page it was the last one on is
                // now a page with nothing on it: close it up.
                vc.collapseEmptyPagesAfterDrag()
            })
        } else {
            op.placeholderView.removeFromSuperview()
            currentOperation = nil
            for cell in vc.outerCollectionView.visibleCells {
                (cell as? LCSpringboardPageCell)?.draggedItemId = nil
            }
            vc.applyPendingItemsIfNeeded()
            vc.collapseEmptyPagesAfterDrag()
        }
    }

    // MARK: - Read cell order back from UICollectionView (jSpringBoard's updateState)

    private func updateState(forPageCell pageCell: LCSpringboardPageCell, pageIndex: Int) {
        guard let vc = viewController else { return }

        var items: [FlekHomeItem] = []
        let count = pageCell.collectionView.numberOfItems(inSection: 0)
        for i in 0..<count {
            let indexPath = IndexPath(item: i, section: 0)
            if let cell = pageCell.collectionView.cellForItem(at: indexPath) as? LCSpringboardIconCell,
               let item = cell.configuredItem {
                items.append(item)
            }
        }

        if !items.isEmpty {
            pageCell.items = items
            vc.pages[pageIndex] = items
        }
    }

    // MARK: - Page scroll timer (cross-page drag)

    private func startPageScrollTimer(direction: Int) {
        cancelPageScrollTimer()
        pageScrollTimer = Timer.scheduledTimer(
            timeInterval: pageScrollDelay,
            target: self,
            selector: #selector(pageScrollTimerFired(_:)),
            userInfo: direction,
            repeats: false
        )
    }

    private func cancelPageScrollTimer() {
        pageScrollTimer?.invalidate()
        pageScrollTimer = nil
    }

    /// Cross-page move handler. Faithfully follows jSpringBoard's pageTimerHandler:
    /// 1. Sync current page from cells (within-page moveItem didn't update data)
    /// 2. Find the dragged item by ID in the data array
    /// 3. If savedState exists, restore it (undo previous cascade)
    /// 4. Remove item from current page
    /// 5. If destination page is full, save state and cascade overflow
    /// 6. Append item to destination page
    /// 7. Update current page cell, scroll to destination
    @objc private func pageScrollTimerFired(_ timer: Timer) {
        guard let vc = viewController,
              let op = currentOperation,
              let direction = timer.userInfo as? Int else { return }

        pageScrollTimer = nil

        let nextPage = op.currentPage + direction
        guard nextPage >= 0 && nextPage < vc.pages.count else { return }

        // Step 1: Sync current page from cells (moveItem didn't update data)
        if let currentPageCell = vc.visiblePageCell(forPage: op.currentPage) {
            updateState(forPageCell: currentPageCell, pageIndex: op.currentPage)
        }

        // Step 2: Find the dragged item's actual index in the data array
        guard let currentIndex = vc.pages[op.currentPage].firstIndex(where: { $0.id == op.itemId }) else { return }
        let currentPageInitialCount = vc.pages[op.currentPage].count

        // Step 3: If savedState exists, restore it (undo previous cascade)
        if let savedState = op.savedState {
            vc.pages = savedState
            op.savedState = nil
        } else {
            // Step 4: Remove item from current page
            vc.pages[op.currentPage].remove(at: currentIndex)
        }

        // Step 5: If destination page is full, save state and cascade
        if vc.pages[nextPage].count >= vc.itemsPerPage {
            op.savedState = vc.pages
            vc.moveLastItem(inPage: nextPage)
        }

        // Step 6: Append item to destination page
        vc.pages[nextPage].append(op.item)

        // Step 7: Update current page cell visuals
        if let currentPageCell = vc.visiblePageCell(forPage: op.currentPage) {
            currentPageCell.items = vc.pages[op.currentPage]
            op.needsUpdate = true

            // jSpringBoard: only batch-delete if we're still on the original page AND count decreased
            if op.currentPage == op.originalPage && vc.pages[op.currentPage].count < currentPageInitialCount {
                currentPageCell.collectionView.performBatchUpdates({
                    currentPageCell.collectionView.deleteItems(at: [IndexPath(item: currentIndex, section: 0)])
                }, completion: nil)
            } else {
                currentPageCell.collectionView.reloadData()
            }
        }

        op.currentPage = nextPage
        op.needsUpdate = true

        // Scroll to destination page
        let offset = CGPoint(x: vc.outerCollectionView.bounds.width * CGFloat(nextPage), y: 0)
        vc.outerCollectionView.setContentOffset(offset, animated: true)
    }

    /// Called by the VC when a page cell becomes visible during a drag (willDisplay).
    /// Matches jSpringBoard's willDisplay logic.
    /// Called by the VC when a page cell becomes visible during a drag (willDisplay).
    /// Matches jSpringBoard's willDisplay logic — sets items and currentIndex,
    /// then lets the caller (willDisplay) handle reloadData.
    func adoptDragOnVisiblePage(_ pageCell: LCSpringboardPageCell, pageIndex: Int) {
        guard let vc = viewController,
              let op = currentOperation,
              op.needsUpdate,
              op.currentPage == pageIndex else { return }

        pageCell.items = vc.pages[pageIndex]
        // The dragged item was appended last, so its index is count - 1
        op.currentIndex = pageCell.collectionView(pageCell.collectionView, numberOfItemsInSection: 0) - 1
        op.needsUpdate = false
    }
}
