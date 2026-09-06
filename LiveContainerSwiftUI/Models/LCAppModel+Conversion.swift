//
//  LCAppModel+Conversion.swift
//  LiveContainerSwiftUI
//
//  Moving an app between the shared app group and this instance's own Documents.
//

import Foundation

/// Converting an app from shared to private and back.
///
/// This lives on the model rather than in the settings screen because the
/// settings screen is no longer the only way in: deleting a shared app from the
/// home screen converts it first, since a shared bundle is not one install's to
/// take away. Both go through the same checks and the same moves, so what
/// "convert" means cannot drift between them.
///
/// Every reason a conversion cannot go ahead is thrown, so the caller only has
/// to decide where to show it.
extension LCAppModel {

    /// Carries a message a conversion stops on, so every reason one stops
    /// reaches the caller the same way.
    struct ConversionRefused: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// Moves the app's bundle, container folders and tweak folder into the app
    /// group, where every LiveContainer on the device sees the same copy.
    func convertToShared(sharedModel: SharedModel) throws {
        try checkContainersNotInUse()
        try LCPath.ensureAppGroupPaths()

        var moves: [(URL, URL)] = []
        let bundleSource = URL(fileURLWithPath: appInfo.bundlePath())
        let bundleDestination = LCPath.lcGroupBundlePath.appendingPathComponent(appInfo.relativeBundlePath)
        switch bundleMoveStep(from: bundleSource, to: bundleDestination, sharedModel: sharedModel) {
        case .pending:
            moves.append((bundleSource, bundleDestination))
        case .alreadyDone:
            break
        case .missing:
            throw ConversionRefused(message: missingBundleMessage)
        case .blocked:
            throw ConversionRefused(message: duplicateBundleMessage(destinationIsShared: true))
        }
        for container in uiContainers {
            if container.storageBookMark != nil {
                continue
            }
            try appendIfPending(
                &moves,
                LCPath.dataPath.appendingPathComponent(container.folderName),
                LCPath.lcGroupDataPath.appendingPathComponent(container.folderName),
                destinationIsShared: true
            )
        }
        if let tweakFolder = appInfo.tweakFolder, tweakFolder.count > 0 {
            try appendIfPending(
                &moves,
                LCPath.tweakPath.appendingPathComponent(tweakFolder),
                LCPath.lcGroupTweakPath.appendingPathComponent(tweakFolder),
                destinationIsShared: true
            )
        }

        try LCUtils.moveFilesAtomicallyAfterPreflight(moves)

        for container in uiContainers {
            if container.storageBookMark != nil {
                continue
            }
            sharedModel.appDataFolderNames.removeAll(where: { s in
                return s == container.folderName
            })
            container.isShared = true
        }

        if let tweakFolder = appInfo.tweakFolder, tweakFolder.count > 0 {
            sharedModel.tweakFolderNames.removeAll(where: { s in
                return s == tweakFolder
            })
        }

        appInfo.setBundlePath(LCPath.lcGroupBundlePath.appendingPathComponent(appInfo.relativeBundlePath).path)
        appInfo.isShared = true
        uiIsShared = true
    }

    /// Moves the app's bundle and container folders out of the app group and
    /// into this instance's own Documents, taking it away from every other
    /// LiveContainer on the device.
    ///
    /// `movingTweakFolder` is what separates converting an app the user means to
    /// keep from converting one on its way to being deleted. A tweak folder is
    /// not owned by the app that names it — another shared app can name the same
    /// one, and uninstalling never deletes one — so dragging it into private
    /// storage for an app that is about to be removed strands it there and takes
    /// it from whatever else was using the shared copy. A conversion the user
    /// asked for on its own still moves it, which is the whole point of asking.
    func convertToPrivate(sharedModel: SharedModel, movingTweakFolder: Bool) throws {
        try checkCanConvertToPrivate(sharedModel: sharedModel)
        try checkContainersNotInUse()

        var moves: [(URL, URL)] = []
        let bundleSource = URL(fileURLWithPath: appInfo.bundlePath())
        let bundleDestination = LCPath.bundlePath.appendingPathComponent(appInfo.relativeBundlePath)
        switch bundleMoveStep(from: bundleSource, to: bundleDestination, sharedModel: sharedModel) {
        case .pending:
            moves.append((bundleSource, bundleDestination))
        case .alreadyDone:
            break
        case .missing:
            throw ConversionRefused(message: missingBundleMessage)
        case .blocked:
            throw ConversionRefused(message: duplicateBundleMessage(destinationIsShared: false))
        }
        for container in uiContainers {
            if container.storageBookMark != nil {
                continue
            }
            try appendIfPending(
                &moves,
                LCPath.lcGroupDataPath.appendingPathComponent(container.folderName),
                LCPath.dataPath.appendingPathComponent(container.folderName),
                destinationIsShared: false
            )
        }
        if movingTweakFolder, let tweakFolder = appInfo.tweakFolder, tweakFolder.count > 0 {
            try appendIfPending(
                &moves,
                LCPath.lcGroupTweakPath.appendingPathComponent(tweakFolder),
                LCPath.tweakPath.appendingPathComponent(tweakFolder),
                destinationIsShared: false
            )
        }

        try LCUtils.moveFilesAtomicallyAfterPreflight(moves)

        let fm = FileManager.default
        for container in uiContainers {
            if container.storageBookMark != nil {
                continue
            }
            // A container folder is created on the app's first run, so one
            // that was never used has nothing on either side and does not
            // belong in the list of folders sitting in our Documents.
            let folder = LCPath.dataPath.appendingPathComponent(container.folderName)
            if fm.fileExists(atPath: folder.path), !sharedModel.appDataFolderNames.contains(container.folderName) {
                sharedModel.appDataFolderNames.append(container.folderName)
            }
        }
        // Only a folder that actually arrived belongs in the list, which holds
        // the private Tweaks folder's contents and nothing from the group.
        if movingTweakFolder, let tweakFolder = appInfo.tweakFolder, tweakFolder.count > 0,
           fm.fileExists(atPath: LCPath.tweakPath.appendingPathComponent(tweakFolder).path) {
            if !sharedModel.tweakFolderNames.contains(tweakFolder) {
                sharedModel.tweakFolderNames.append(tweakFolder)
            }
            uiTweakFolder = tweakFolder
        }

        appInfo.setBundlePath(LCPath.bundlePath.appendingPathComponent(appInfo.relativeBundlePath).path)
        appInfo.isShared = false
        uiIsShared = false
        for container in uiContainers {
            container.isShared = false
        }
    }

    /// Refuses on a FlekDeck that is not the main one.
    ///
    /// The app group's copy is the one every FlekDeck on the device shares, and
    /// pulling it into a secondary FlekDeck's own Documents leaves it where the
    /// main one cannot see it — so the settings screen only offers the
    /// conversion on the main FlekDeck. Deleting a shared app converts it too,
    /// which would otherwise have been a way around that rule, so the rule lives
    /// here where both go through it.
    ///
    /// Public for the same reason as `checkContainersNotInUse`: the home screen
    /// asks before it puts the user to a confirmation it cannot honour.
    func checkCanConvertToPrivate(sharedModel: SharedModel) throws {
        guard sharedModel.multiLCStatus != 2 else {
            throw ConversionRefused(message: secondaryFlekDeckMessage)
        }
    }

    /// Shown when a secondary FlekDeck is asked to convert a shared app.
    private var secondaryFlekDeckMessage: String {
        "Only the main FlekDeck can convert a shared app to a private one, and this app has to be converted before it can be deleted.\n\nOpen the main FlekDeck and delete it from there."
    }

    /// Refuses while a LiveContainer has one of the app's containers open: its
    /// files are about to move out from under it. Public because the settings
    /// screen asks it before it puts the user to a confirmation, rather than
    /// confirming and then failing.
    func checkContainersNotInUse() throws {
        for container in appInfo.containers {
            guard let runningLC = LCSharedUtils.getContainerUsingLCScheme(withFolderName: container.folderName) else {
                continue
            }
            // The lock names whichever FlekDeck holds the container, this one
            // included: an app running in a window here answers exactly as one
            // running in another instance does. Sending the user off to open
            // another FlekDeck when the app is open in front of them is no help,
            // so say which of the two it is.
            //
            // A container held by the guest process is filed under the scheme
            // with a `.liveprocess` extension, which is not a FlekDeck the user
            // can open — the instance is what is left after dropping it, which
            // is how the launch path reads this same value.
            let holder = (runningLC as NSString).deletingPathExtension
            if holder.caseInsensitiveCompare(LCUtils.appUrlScheme() ?? "") == .orderedSame {
                throw ConversionRefused(message: appStillOpenHereMessage)
            }
            throw ConversionRefused(
                message: "lc.appSettings.appOpenInOtherLc %@ %@".localizeWithFormat(holder, holder)
            )
        }
    }

    /// Shown when the app is open in this FlekDeck rather than another one. The
    /// cross-instance wording tells the user to go and open the FlekDeck that
    /// has it, which reads as nonsense when that FlekDeck is the one they are
    /// looking at.
    private var appStillOpenHereMessage: String {
        "This app is still open in this FlekDeck. Close its window and try again."
    }

    /// Shown when neither side of a conversion has the app's bundle.
    private var missingBundleMessage: String {
        "This app's files are no longer on disk, so there is nothing to convert.\n\nThis usually follows an install that was interrupted after the previous copy had been removed. Press and hold the app on the home screen and choose Uninstall to clear the leftover entry, then install it again."
    }

    /// Shown when both sides already hold a copy of the app under the same
    /// folder name — normal enough, since installing the same IPA shared and
    /// private gives each side its own copy. Converting would have to write
    /// over one of them, so it stops and says which one is in the way.
    private func duplicateBundleMessage(destinationIsShared: Bool) -> String {
        let side = destinationIsShared ? "shared" : "private"
        return "There is already a \(side) copy of this app installed, under the same folder name (\(appInfo.relativeBundlePath ?? "")).\n\nConverting would overwrite it. Uninstall whichever of the two copies you no longer want, then convert this one again."
    }

    /// Shown when a data or tweak folder of the app's has a namesake waiting on
    /// the other side. Only tweak folders realistically hit this — container
    /// folders are named by UUID — so the fix is to rename one of them.
    private func duplicateFolderMessage(_ url: URL, destinationIsShared: Bool) -> String {
        let side = destinationIsShared ? "shared" : "private"
        return "A \(side) folder named \"\(url.lastPathComponent)\" already exists, so this app's folder of that name has nowhere to go.\n\nRename one of the two, then convert again."
    }

    private enum FlekMoveStep {
        case pending
        case alreadyDone
        case missing
        case blocked
    }

    private func flekPlanMove(from source: URL, to destination: URL) -> FlekMoveStep {
        let fm = FileManager.default
        let sourceExists = fm.fileExists(atPath: source.standardizedFileURL.path)
        let destinationExists = fm.fileExists(atPath: destination.standardizedFileURL.path)
        switch (sourceExists, destinationExists) {
        case (true, false): return .pending
        case (true, true): return .blocked
        case (false, true): return .alreadyDone
        case (false, false): return .missing
        }
    }

    /// Whether the bundle still has to be moved, has already been moved by an
    /// earlier attempt, or is gone entirely.
    ///
    /// This is `LCUtils.planMove` plus one guard specific to the bundle: another
    /// installed app may already own the folder we would move into, and adopting
    /// its bundle would leave two entries sharing a single copy, where removing
    /// either one takes the app away from both. That is not a half-finished
    /// conversion of ours, so it counts as missing.
    private func bundleMoveStep(from source: URL, to destination: URL, sharedModel: SharedModel) -> FlekMoveStep {
        let step = flekPlanMove(from: source, to: destination)
        if case .alreadyDone = step, bundleIsClaimedByAnotherApp(destination, sharedModel: sharedModel) {
            return .missing
        }
        return step
    }

    private func bundleIsClaimedByAnotherApp(_ url: URL, sharedModel: SharedModel) -> Bool {
        let path = url.standardizedFileURL.path
        return (sharedModel.apps + sharedModel.hiddenApps).contains { other in
            guard other !== self, let otherPath = other.appInfo.bundlePath() else {
                return false
            }
            return URL(fileURLWithPath: otherPath).standardizedFileURL.path == path
        }
    }

    /// Adds a move to the batch only if there is anything left to move. Data and
    /// tweak folders can legitimately be absent — a container folder is created
    /// on the app's first run — and a folder already sitting at the destination
    /// was moved by an earlier attempt. Neither should stop the conversion. A
    /// namesake on the other side does, since the move would write over it.
    private func appendIfPending(
        _ moves: inout [(URL, URL)],
        _ source: URL,
        _ destination: URL,
        destinationIsShared: Bool
    ) throws {
        switch flekPlanMove(from: source, to: destination) {
        case .pending:
            moves.append((source, destination))
        case .blocked:
            throw ConversionRefused(
                message: duplicateFolderMessage(destination, destinationIsShared: destinationIsShared)
            )
        case .alreadyDone, .missing:
            break
        }
    }
}


private enum FlekUninstallRefused: LocalizedError {
    case sharedBundle

    var errorDescription: String? {
        switch self {
        case .sharedBundle:
            return "This app is stored in the shared folder, so every FlekDeck on this device uses the same copy — deleting it here would remove it for all of them.\n\nTo delete it, open the app's settings and tap \"Convert to Private App\" first."
        }
    }
}

extension LCAppModel {
    var isBundleMissing: Bool {
        guard let bundlePath = appInfo.bundlePath(), !bundlePath.isEmpty else {
            return true
        }
        return !FileManager.default.fileExists(atPath: bundlePath)
    }

    var isUninstallable: Bool {
        !uiIsShared || isBundleMissing
    }

    func uninstall(removingContainers: Bool) throws {
        guard isUninstallable else {
            throw FlekUninstallRefused.sharedBundle
        }

        let fm = FileManager.default
        if let bundlePath = appInfo.bundlePath(), !isBundleMissing {
            try fm.removeItem(atPath: bundlePath)
        }

        guard removingContainers else { return }
        for container in uiContainers {
            let folderName = container.folderName
            if container.storageBookMark == nil {
                try? fm.removeItem(at: container.containerURL)
            }
            LCUtils.removeAppKeychain(dataUUID: folderName)
            DispatchQueue.main.async {
                DataManager.shared.model.appDataFolderNames.removeAll { $0 == folderName }
            }
        }
    }
}
