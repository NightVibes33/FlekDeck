from pathlib import Path

# Keep the experiment bridge in MultitaskDockView.swift itself so it is compiled
# by exactly the same target membership as the existing multitask manager. This
# avoids relying on Xcode's synchronized-folder membership for a newly added file.
p = Path("MultitaskSupport/MultitaskDockView.swift")
s = p.read_text()

if "final class FlekGuestBottomGestureBridge" not in s:
    s += r'''

// MARK: - Experiment: host-owned guest bottom gesture

/// Restores the UIWindow-owned bottom gesture boundary present in the pinned
/// VibeContainers runtime. FlekDeck's newer small swipe zone is only installed
/// after the main switcher bar has been hidden, so it is not a universal escape
/// gesture for a maximized guest.
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
        gestureRecognizer === pan || otherGestureRecognizer === pan
    }

    @objc private func handlePan(_ gesture: UIPanGestureRecognizer) {
        guard gesture.state == .ended, let view = gesture.view else { return }

        let translation = gesture.translation(in: view)
        let velocity = gesture.velocity(in: view)
        let upward = max(0, -translation.y)

        if upward >= 64 || velocity.y <= -900 {
            NSLog("[FlekDeckDiag] guest bottom gesture -> Home (up=%.1f vy=%.1f)", upward, velocity.y)
            MultitaskDockManager.shared.goHome()
        } else if upward >= 28 {
            NSLog("[FlekDeckDiag] guest bottom gesture -> switcher (up=%.1f vy=%.1f)", upward, velocity.y)
            MultitaskDockManager.shared.showAppSwitcher()
        }
    }
}
'''

p.write_text(s)
print("Injected host-owned guest bottom gesture bridge into MultitaskDockView.swift")
