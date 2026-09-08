import UIKit

/// Experiment-only bridge that restores the host-owned bottom gesture behavior
/// that the pinned VibeContainers runtime expects, without changing guest code.
///
/// FlekDeck's newer multitask shell replaced Vibe's UIWindow-level recognizers
/// with a small nav-assist swipe zone. That zone only exists in one control mode,
/// so a maximized guest can end up with no Flek-owned Home gesture. This bridge
/// attaches at the host UIWindow instead, matching Vibe's original ownership
/// boundary: the guest may render out of process, but it cannot cover the host's
/// recognizer.
@available(iOS 16.0, *)
final class FlekGuestBottomGestureBridge: NSObject, UIGestureRecognizerDelegate {
    static let shared = FlekGuestBottomGestureBridge()

    private weak var installedWindow: UIWindow?
    private weak var pan: UIPanGestureRecognizer?

    private override init() {
        super.init()
    }

    func install(on window: UIWindow) {
        if installedWindow === window, pan?.view === window {
            return
        }

        if let oldPan = pan, let oldView = oldPan.view {
            oldView.removeGestureRecognizer(oldPan)
        }

        let recognizer = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        recognizer.delegate = self
        recognizer.maximumNumberOfTouches = 1
        recognizer.cancelsTouchesInView = false
        window.addGestureRecognizer(recognizer)

        installedWindow = window
        pan = recognizer
        NSLog("[FlekDeckDiag] installed host-owned guest bottom gesture on %@", String(describing: window))
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let pan = gestureRecognizer as? UIPanGestureRecognizer,
              let view = pan.view else { return false }

        // Only claim the edge while a Flek multitask window is visibly on stage.
        // On the SpringBoard the recognizer becomes inert and cannot steal normal
        // FlekDeck navigation touches.
        let hasForegroundWindow = MultitaskDockManager.shared.windowHostingView.subviews.contains {
            !$0.isHidden && $0.alpha > 0.1
        }
        guard hasForegroundWindow else { return false }

        let start = pan.location(in: view)
        guard start.y >= view.bounds.height - 72 else { return false }

        let velocity = pan.velocity(in: view)
        return velocity.y < -20 || abs(velocity.x) > 20
    }

    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
    ) -> Bool {
        return gestureRecognizer === pan || otherGestureRecognizer === pan
    }

    @objc private func handlePan(_ gesture: UIPanGestureRecognizer) {
        guard gesture.state == .ended, let view = gesture.view else { return }

        let translation = gesture.translation(in: view)
        let velocity = gesture.velocity(in: view)
        let upward = max(0, -translation.y)

        // Mirror the useful part of VibeContainers' original SpringBoard gesture:
        // a normal/fast swipe goes Home without terminating the guest; a shorter
        // intentional pull opens FlekDeck's internal app switcher.
        if upward >= 64 || velocity.y <= -900 {
            NSLog("[FlekDeckDiag] guest bottom gesture -> Home (up=%.1f vy=%.1f)", upward, velocity.y)
            MultitaskDockManager.shared.goHome()
        } else if upward >= 28 {
            NSLog("[FlekDeckDiag] guest bottom gesture -> switcher (up=%.1f vy=%.1f)", upward, velocity.y)
            MultitaskDockManager.shared.showAppSwitcher()
        }
    }
}
