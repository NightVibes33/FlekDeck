//
//  FlekAppCard.swift
//  LiveContainerSwiftUI
//
//  A single springboard tile: a frosted glass card holding an app icon and
//  its label. Used for both built-in apps and installed guest apps.
//

import SwiftUI

struct FlekAppCard<Icon: View>: View {
    let title: String
    /// Shows the blue "new / not yet launched" dot before the title.
    var isNew: Bool = false
    /// Shows the single-mode (non-multitask) launch badge on the icon.
    var showsSingleModeBadge: Bool = false
    /// Whether the card is wiggling in edit mode.
    var isEditing: Bool = false
    /// The corner control shown in edit mode: the minus that uninstalls, the
    /// info mark for an app that cannot be removed from here, or nothing at all
    /// for the built-in apps.
    var editBadge: FlekEditBadge = .remove
    /// Height the card should occupy; the contents scale to fit it.
    var cardHeight: CGFloat = FlekTheme.cardHeight
    var onDelete: (() -> Void)? = nil
    @ViewBuilder var icon: () -> Icon

    @State private var wigglePhase = false
    /// Random delay so each card wiggles at a different phase, like real iOS.
    @State private var wiggleDelay: Double = 0
    @AppStorage(FlekDeckKeys.cardStyleGlass, store: LCUtils.appGroupUserDefault) private var cardStyleGlass: Bool = true
    @AppStorage(FlekDeckKeys.showAppCardBackgrounds, store: LCUtils.appGroupUserDefault) private var showCardBackgrounds = true
    @Environment(\.colorScheme) private var colorScheme

    private var scale: CGFloat { cardHeight / FlekTheme.cardHeight }

    /// Whether the glass background should stay still (content-only wobble).
    private var isGlassMode: Bool {
        if #available(iOS 26, *) { return cardStyleGlass }
        return false
    }

    /// Current wobble rotation angle.
    private var wiggleAngle: Double {
        isEditing ? (wigglePhase ? 0.75 : -0.75) : 0
    }

    var body: some View {
        VStack(spacing: FlekTheme.cardInnerSpacing * scale) {
            ZStack(alignment: .topTrailing) {
                icon()
                    .frame(width: FlekTheme.iconSize * scale, height: FlekTheme.iconSize * scale)
                    .clipShape(RoundedRectangle(cornerRadius: FlekTheme.iconCorner * scale, style: .continuous))

                if showsSingleModeBadge {
                    Image(systemName: "1.circle.fill")
                        .font(.system(size: 16 * scale))
                        .symbolRenderingMode(.palette)
                        .foregroundStyle(.white, Color.accentColor)
                        .background(Circle().fill(Color.white))
                        .offset(x: 6, y: -6)
                }
            }

            HStack(spacing: 4) {
                if isNew {
                    Circle()
                        .fill(Color.blue)
                        .frame(width: 7 * scale, height: 7 * scale)
                }
                Text(title)
                    .font(.system(size: FlekTheme.labelSize * scale, weight: .medium))
                    .foregroundStyle(Color.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
        }
        .padding(.top, FlekTheme.cardTopPadding * scale)
        .padding(.bottom, FlekTheme.cardBottomPadding * scale)
        .padding(.horizontal, FlekTheme.cardHPadding)
        .frame(maxWidth: .infinity)
        .frame(height: cardHeight)
        // Glass mode: wobble content before applying the glass background
        .rotationEffect(.degrees(isGlassMode ? wiggleAngle : 0))
        .modifier(FlekCardBackgroundVisibility(
            visible: showCardBackgrounds,
            cornerRadius: FlekTheme.cardCorner * min(1, scale)))
        .overlay(alignment: .topLeading) {
            if isEditing && editBadge != .none {
                Button {
                    onDelete?()
                } label: {
                    Image(systemName: "minus")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(colorScheme == .dark ? .white : .black)
                        .frame(width: 24, height: 24)
                        .background(Circle().fill(colorScheme == .dark ? Color(white: 0.25) : Color(white: 0.85)))
                        .overlay(Circle().strokeBorder((colorScheme == .dark ? Color.white : Color.black).opacity(0.15), lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .offset(x: -6, y: -6)
                .transition(.scale.combined(with: .opacity))
            }
        }
        // Thin material mode: wobble the whole card including background
        .rotationEffect(.degrees(!isGlassMode ? wiggleAngle : 0))
        .animation(isEditing
                   ? .easeInOut(duration: 0.1).repeatForever(autoreverses: true).delay(wiggleDelay)
                   : .default,
                   value: wigglePhase)
        .onChange(of: isEditing) { editing in
            wigglePhase = editing
        }
        .onChange(of: isGlassMode) { _ in
            // Restart the wobble so the newly-active rotation effect
            // picks up the repeating animation.
            if isEditing {
                wigglePhase = false
                DispatchQueue.main.async { wigglePhase = true }
            }
        }
        .onAppear {
            wiggleDelay = Double.random(in: 0...0.24)
            if isEditing { wigglePhase = true }
        }
    }
}


/// Preserves the full-size tap target and edit badge when card glass is hidden.
private struct FlekCardBackgroundVisibility: ViewModifier {
    let visible: Bool
    let cornerRadius: CGFloat

    @ViewBuilder
    func body(content: Content) -> some View {
        if visible {
            content.flekGlassCard(cornerRadius: cornerRadius)
        } else {
            content
        }
    }
}
