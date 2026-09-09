//
//  MultitaskDockManager+VibeCompat.swift
//  FlekDeck
//
//  ObjC compatibility surface required by the VibeContainers-style LCUtils
//  multitask launch path. Kept in the host shell so normal guest execution and
//  signing logic remain unchanged.
//

import UIKit

@available(iOS 16.0, *)
extension MultitaskDockManager {
    /// Returns the deterministic FlekDeck host window used to embed a parallel
    /// guest. LCUtils.m calls this selector from the main queue before creating
    /// DecoratedAppSceneViewController and once more after setup to keep the
    /// guest hierarchy above the Springboard subtree.
    @objc(prepareHostWindowForGuestLaunch)
    public func prepareHostWindowForGuestLaunch() -> UIWindow? {
        dispatchPrecondition(condition: .onQueue(.main))

        guard let window = keyWindow,
              window.rootViewController != nil,
              window.windowScene != nil else {
            return nil
        }

        windowHostingView.frame = window.bounds
        return window
    }
}
