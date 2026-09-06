import SwiftUI

// Compatibility stub for old call sites. Standalone FlekDeck has no remote ban,
// chargeback, subscription, or payment-access state.
struct AccessBlockedView: View {
    let reason: String
    let message: String

    var body: some View {
        EmptyView()
    }
}
