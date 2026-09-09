import SwiftUI
import UniformTypeIdentifiers

/// Direct FlekDeck-quality adaptation of VibeContainers' Tweaks / Manage / Apps
/// workflow. The UI preserves Vibe's scope semantics while FlekTweakStore maps
/// those semantics onto the existing FlekDeck TweakLoader.
struct FlekVibeTweaksView: View {
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var store = FlekTweakStore.shared
    @State private var tab = 0
    @State private var importing = false

    private var apps: [LCAppModel] {
        var seen = Set<ObjectIdentifier>()
        return (sharedModel.apps + sharedModel.hiddenApps).filter { seen.insert(ObjectIdentifier($0)).inserted }
            .sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                hero
                Picker("Tweaks", selection: $tab) {
                    Text("Tweaks").tag(0)
                    Text("Manage").tag(1)
                    Text("Apps").tag(2)
                }
                .pickerStyle(.segmented)

                if tab == 0 { libraryTab }
                else if tab == 1 { manageTab }
                else { appsTab }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle("Tweaks")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { store.refresh() }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.dylib, .lcFramework], allowsMultipleSelection: true) { result in
            switch result {
            case .success(let urls): store.importItems(urls)
            case .failure(let error): store.lastError = error.localizedDescription
            }
        }
        .alert("Tweaks", isPresented: Binding(get: { store.lastError != nil }, set: { if !$0 { store.lastError = nil } })) {
            Button("OK", role: .cancel) { store.lastError = nil }
        } message: { Text(store.lastError ?? "") }
        .overlay(alignment: .top) {
            if let notice = store.lastNotice {
                HStack(spacing: 9) {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    Text(notice).font(.subheadline).lineLimit(2)
                    Spacer()
                    Button { store.lastNotice = nil } label: { Image(systemName: "xmark") }
                }
                .padding(14)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
                .padding(.horizontal, 16)
                .padding(.top, 4)
            }
        }
    }

    private var hero: some View {
        HStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color.purple.opacity(0.14))
                Image(systemName: "puzzlepiece.extension.fill")
                    .font(.system(size: 29, weight: .semibold))
                    .foregroundStyle(.purple)
            }
            .frame(width: 66, height: 66)
            VStack(alignment: .leading, spacing: 4) {
                Text("Tweak Library").font(.title2.bold())
                Text("Vibe-style global and per-app scope, resolved by FlekDeck's existing TweakLoader.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(18)
        .flekGlassCard(cornerRadius: 25, tint: 0.10)
    }

    // MARK: Tweaks

    @ViewBuilder
    private var libraryTab: some View {
        if store.library.isEmpty {
            emptyCard("No tweaks installed", detail: "Import a .dylib or .framework from Manage. Imported tweaks enter the library without becoming global automatically.", symbol: "tray")
        } else {
            VStack(spacing: 12) {
                summary
                ForEach(store.library) { tweak in
                    NavigationLink {
                        FlekTweakDetailView(tweakID: tweak.id)
                            .environmentObject(sharedModel)
                    } label: {
                        tweakCard(tweak)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var summary: some View {
        let globals = store.library.filter(store.isGlobal).count
        let loadable = store.library.filter(\.isLoadable).count
        return HStack(spacing: 0) {
            stat("Tweaks", "\(store.library.count)")
            Divider().frame(height: 35)
            stat("Global", "\(globals)")
            Divider().frame(height: 35)
            stat("Loadable", "\(loadable)")
            Divider().frame(height: 35)
            stat("Apps", "\(apps.count)")
        }
        .padding(.vertical, 14)
        .flekGlassCard(cornerRadius: 20, tint: 0.07)
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.headline.monospacedDigit())
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func tweakCard(_ tweak: FlekManagedTweak) -> some View {
        HStack(spacing: 14) {
            tweakIcon(tweak, size: 50)
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Text(tweak.name).font(.headline).foregroundStyle(.primary).lineLimit(1)
                    if !tweak.isLoadable {
                        Text("INVALID").font(.system(size: 8, weight: .bold)).foregroundStyle(.orange)
                            .padding(.horizontal, 6).padding(.vertical, 3)
                            .background(Color.orange.opacity(0.12), in: Capsule())
                    }
                }
                Text(tweak.detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Text(store.scopeText(tweak, apps: apps)).font(.caption2).foregroundStyle(store.isGlobal(tweak) ? .green : .secondary)
            }
            Spacer(minLength: 8)
            Toggle("Global", isOn: Binding(
                get: { store.isGlobal(tweak) },
                set: { store.setGlobal($0, tweak: tweak) }
            ))
            .labelsHidden()
            .tint(.green)
            .disabled(!tweak.isLoadable)
            Image(systemName: "chevron.forward").font(.caption.bold()).foregroundStyle(.tertiary)
        }
        .padding(16)
        .contentShape(Rectangle())
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    // MARK: Manage

    private var manageTab: some View {
        VStack(spacing: 12) {
            actionCard(title: "Add Tweak…", detail: "Import .dylib or .framework files into the managed library.", symbol: "square.and.arrow.down.fill", tint: .blue) {
                importing = true
            }
            actionCard(title: "Scan Documents Folder", detail: "Adopt loose tweak files from the top level of Documents.", symbol: "doc.badge.gearshape", tint: .orange) {
                store.scanDocuments()
            }
            actionCard(title: "Re-sync All Apps", detail: "Repairs broken per-app overlay links without touching existing LCTweakFolder profiles.", symbol: "arrow.triangle.2.circlepath", tint: .purple) {
                store.repair()
            }
            actionCard(title: store.isSigning ? "Signing…" : "Sign / Re-sign Tweaks", detail: "Uses FlekDeck's existing certificate and tweak signer.", symbol: "signature", tint: .green) {
                Task { await store.signAll() }
            }
            .disabled(store.isSigning)

            if !store.library.isEmpty {
                sectionTitle("Installed Tweaks")
                ForEach(store.library) { tweak in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            tweakIcon(tweak, size: 44)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(tweak.name).font(.subheadline.weight(.semibold))
                                Text(tweak.machO.detail).font(.caption2).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button(role: .destructive) { store.delete(tweak) } label: { Image(systemName: "trash") }
                        }
                        Text(tweak.loadPath)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .textSelection(.enabled)
                    }
                    .padding(15)
                    .flekGlassCard(cornerRadius: 20, tint: 0.07)
                }
            }

            VStack(alignment: .leading, spacing: 9) {
                Label("TweakLoader Backend", systemImage: "checkmark.shield.fill")
                    .font(.headline).foregroundStyle(.green)
                Text("Global tweaks stay in Documents/Tweaks. Per-app Vibe toggles use __FlekPerApp overlays. Existing named LCTweakFolder profiles still load recursively. Guest executables are never rewritten by this manager.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .flekGlassCard(cornerRadius: 20, tint: 0.07)
        }
    }

    // MARK: Apps

    @ViewBuilder
    private var appsTab: some View {
        if apps.isEmpty {
            emptyCard("No installed apps", detail: "Install an IPA and it will appear here for Vibe-style per-app tweak scope.", symbol: "square.stack.3d.up.slash")
        } else {
            VStack(spacing: 12) {
                ForEach(apps.indices, id: \.self) { index in
                    let app = apps[index]
                    NavigationLink {
                        FlekAppTweakScopeView(app: app)
                            .environmentObject(sharedModel)
                    } label: {
                        HStack(spacing: 14) {
                            Image(uiImage: app.appInfo.iconIsDarkIcon(false))
                                .resizable().scaledToFill()
                                .frame(width: 50, height: 50)
                                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            VStack(alignment: .leading, spacing: 3) {
                                Text(app.displayName).font(.headline).foregroundStyle(.primary).lineLimit(1)
                                Text(app.bundleIdentifier).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                let effective = store.effectiveTweaks(for: app)
                                let invalid = effective.filter { !$0.isLoadable }.count
                                Text("\(effective.count) effective tweak\(effective.count == 1 ? "" : "s")\(invalid > 0 ? " · \(invalid) invalid" : "")")
                                    .font(.caption2)
                                    .foregroundStyle(invalid > 0 ? Color.orange : Color.secondary)
                            }
                            Spacer()
                            if let folder = app.uiTweakFolder {
                                Text(folder).font(.caption2).foregroundStyle(.purple)
                                    .padding(.horizontal, 7).padding(.vertical, 4)
                                    .background(Color.purple.opacity(0.10), in: Capsule())
                            }
                            Image(systemName: "chevron.forward").font(.caption.bold()).foregroundStyle(.tertiary)
                        }
                        .padding(16)
                        .contentShape(Rectangle())
                        .flekGlassCard(cornerRadius: 22, tint: 0.08)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func tweakIcon(_ tweak: FlekManagedTweak, size: CGFloat) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
                .fill((tweak.isLoadable ? Color.purple : Color.orange).opacity(0.13))
            Image(systemName: tweak.isFramework ? "shippingbox.fill" : "puzzlepiece.extension.fill")
                .font(.system(size: size * 0.43, weight: .semibold))
                .foregroundStyle(tweak.isLoadable ? Color.purple : Color.orange)
        }
        .frame(width: size, height: size)
    }

    private func actionCard(title: String, detail: String, symbol: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous).fill(tint.opacity(0.13))
                    Image(systemName: symbol).font(.system(size: 22, weight: .semibold)).foregroundStyle(tint)
                }.frame(width: 50, height: 50)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.headline).foregroundStyle(.primary)
                    Text(detail).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.leading)
                }
                Spacer()
                Image(systemName: "chevron.forward").font(.caption.bold()).foregroundStyle(.tertiary)
            }
            .padding(16).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private func emptyCard(_ title: String, detail: String, symbol: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 35)).foregroundStyle(.secondary)
            Text(title).font(.headline)
            Text(detail).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding(30).frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 24, tint: 0.08)
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title).font(.title3.bold()).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 6)
    }
}

struct FlekTweakDetailView: View {
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var store = FlekTweakStore.shared
    let tweakID: String

    private var tweak: FlekManagedTweak? { store.library.first { $0.id == tweakID } }
    private var apps: [LCAppModel] { sharedModel.apps + sharedModel.hiddenApps }

    var body: some View {
        ScrollView {
            if let tweak {
                VStack(spacing: 14) {
                    VStack(spacing: 11) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 22, style: .continuous)
                                .fill((tweak.isLoadable ? Color.purple : Color.orange).opacity(0.13))
                            Image(systemName: tweak.isFramework ? "shippingbox.fill" : "puzzlepiece.extension.fill")
                                .font(.system(size: 40, weight: .semibold))
                                .foregroundStyle(tweak.isLoadable ? Color.purple : Color.orange)
                        }.frame(width: 86, height: 86)
                        Text(tweak.name).font(.title2.bold())
                        Text(tweak.detail).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    }
                    .padding(22).frame(maxWidth: .infinity)
                    .flekGlassCard(cornerRadius: 25, tint: 0.08)

                    infoCard(tweak)

                    VStack(alignment: .leading, spacing: 12) {
                        Toggle("Global", isOn: Binding(get: { store.isGlobal(tweak) }, set: { store.setGlobal($0, tweak: tweak) }))
                            .tint(.green).disabled(!tweak.isLoadable)
                        Divider()
                        Text(store.scopeText(tweak, apps: apps)).font(.subheadline).foregroundStyle(.secondary)
                    }
                    .padding(18).flekGlassCard(cornerRadius: 22, tint: 0.08)

                    if !apps.isEmpty {
                        Text("Per-App Scope").font(.title3.bold()).frame(maxWidth: .infinity, alignment: .leading)
                        ForEach(apps.indices, id: \.self) { index in
                            let app = apps[index]
                            HStack(spacing: 12) {
                                Image(uiImage: app.appInfo.iconIsDarkIcon(false)).resizable().scaledToFill()
                                    .frame(width: 40, height: 40).clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(app.displayName).font(.subheadline.weight(.semibold))
                                    Text(store.isGlobal(tweak) ? (store.isBlocked(tweak, for: app) ? "Blocked from global" : "Inherited global") : (store.isExplicitPerApp(tweak, for: app) ? "Per-app overlay" : "Not selected"))
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Toggle("", isOn: Binding(get: { store.isEffective(tweak, for: app) }, set: { store.setEnabled($0, tweak: tweak, for: app) }))
                                    .labelsHidden().tint(.green).disabled(!tweak.isLoadable)
                            }
                            .padding(14).flekGlassCard(cornerRadius: 18, tint: 0.06)
                        }
                    }
                }
                .padding(16)
            }
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle(tweak?.name ?? "Tweak")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { store.refresh() }
    }

    private func infoCard(_ tweak: FlekManagedTweak) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            row("Architecture", tweak.machO.architectureText)
            row("Platform", tweak.machO.platform)
            row("Mach-O", tweak.machO.fileType)
            row("Loadable", tweak.isLoadable ? "Yes" : "No")
            row("Size", ByteCountFormatter.string(fromByteCount: tweak.bytes, countStyle: .file))
            Divider()
            Text(tweak.binaryURL.path).font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).textSelection(.enabled)
            if let error = tweak.machO.error {
                Label(error, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(.orange)
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 22, tint: 0.08)
    }

    private func row(_ key: String, _ value: String) -> some View {
        HStack { Text(key).foregroundStyle(.secondary); Spacer(); Text(value) }.font(.subheadline)
    }
}

struct FlekAppTweakScopeView: View {
    @ObservedObject var app: LCAppModel
    @EnvironmentObject private var sharedModel: SharedModel
    @StateObject private var store = FlekTweakStore.shared

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                VStack(spacing: 9) {
                    Image(uiImage: app.appInfo.iconIsDarkIcon(false)).resizable().scaledToFill()
                        .frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: 17, style: .continuous))
                    Text(app.displayName).font(.title2.bold())
                    Text(app.bundleIdentifier).font(.caption).foregroundStyle(.secondary)
                }
                .padding(22).frame(maxWidth: .infinity)
                .flekGlassCard(cornerRadius: 24, tint: 0.08)

                effectivePlan

                if store.library.isEmpty {
                    Text("No managed tweaks are installed.").font(.subheadline).foregroundStyle(.secondary).padding(24)
                } else {
                    Text("Managed Tweaks").font(.title3.bold()).frame(maxWidth: .infinity, alignment: .leading)
                    ForEach(store.library) { tweak in
                        HStack(spacing: 12) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 11, style: .continuous).fill((tweak.isLoadable ? Color.purple : Color.orange).opacity(0.12))
                                Image(systemName: tweak.isFramework ? "shippingbox.fill" : "puzzlepiece.extension.fill").foregroundStyle(tweak.isLoadable ? Color.purple : Color.orange)
                            }.frame(width: 42, height: 42)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tweak.name).font(.subheadline.weight(.semibold))
                                Text(scopeSubtitle(tweak)).font(.caption2).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Toggle("", isOn: Binding(get: { store.isEffective(tweak, for: app) }, set: { store.setEnabled($0, tweak: tweak, for: app) }))
                                .labelsHidden().tint(.green).disabled(!tweak.isLoadable)
                        }
                        .padding(14).flekGlassCard(cornerRadius: 18, tint: 0.06)
                    }
                }

                let profiles = store.profileTweaks(for: app)
                if app.uiTweakFolder != nil || !profiles.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Existing FlekDeck Profile").font(.headline)
                        Text(app.uiTweakFolder ?? "None").font(.subheadline).foregroundStyle(.purple)
                        if profiles.isEmpty {
                            Text("The selected folder is empty or unavailable.").font(.caption).foregroundStyle(.secondary)
                        } else {
                            ForEach(profiles) { tweak in
                                HStack {
                                    Image(systemName: tweak.isLoadable ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                        .foregroundStyle(tweak.isLoadable ? Color.green : Color.orange)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(tweak.name).font(.subheadline)
                                        Text(tweak.machO.detail).font(.caption2).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                }
                            }
                        }
                    }
                    .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                    .flekGlassCard(cornerRadius: 20, tint: 0.07)
                }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationTitle("Tweaks")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { store.refresh() }
    }

    private var effectivePlan: some View {
        let effective = store.effectiveTweaks(for: app)
        let invalid = effective.filter { !$0.isLoadable }
        return VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("Effective Load Plan").font(.headline)
                Spacer()
                Text("\(effective.count)").font(.headline.monospacedDigit()).foregroundStyle(.secondary)
            }
            if effective.isEmpty {
                Text("No managed/global/profile tweaks resolve for this app.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(effective) { tweak in
                    HStack {
                        Image(systemName: tweak.isLoadable ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(tweak.isLoadable ? Color.green : Color.orange)
                        Text(tweak.name).font(.caption)
                        Spacer()
                        Text(sourceLabel(tweak)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            if !invalid.isEmpty {
                Text("\(invalid.count) selected tweak\(invalid.count == 1 ? " is" : "s are") not arm64 MH_DYLIB and may fail to load.")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 20, tint: 0.07)
    }

    private func scopeSubtitle(_ tweak: FlekManagedTweak) -> String {
        if store.isGlobal(tweak) {
            return store.isBlocked(tweak, for: app) ? "Global · blocked for this app" : "Global · inherited"
        }
        if store.isExplicitPerApp(tweak, for: app) { return "Per-app overlay" }
        if store.profileTweaks(for: app).contains(where: { $0.name.caseInsensitiveCompare(tweak.name) == .orderedSame }) { return "Loaded by existing profile" }
        return tweak.machO.detail
    }

    private func sourceLabel(_ tweak: FlekManagedTweak) -> String {
        if store.isGlobal(tweak) && !store.isBlocked(tweak, for: app) { return "Global" }
        if store.isExplicitPerApp(tweak, for: app) { return "Per-app" }
        return "Profile"
    }
}
