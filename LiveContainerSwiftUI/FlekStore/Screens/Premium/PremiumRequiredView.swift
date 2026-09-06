import SwiftUI

// Kept as an inert compatibility view because older installer screens still
// reference this symbol. Standalone FlekDeck has no premium tier or purchase UI.
struct PremiumRequiredView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Color.clear
            .ignoresSafeArea()
            .onAppear {
                dismiss()
            }
    }
}
