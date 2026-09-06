//
//  FlekstoreAppsListView.swift
//  LiveContainer
//
//  Created by Alexander Grigoryev on 30.09.2025.
//

import SwiftUI
import Kingfisher

struct FlekstoreAppsListView: View {
    @StateObject private var viewModel = FlekstoreAppsListViewModel()
    @Binding var selectedTab: LCTabIdentifier

    @State private var showRepositorySheet = false
    @State private var repos: [AppRepository] = []

    private var selectedRepo: AppRepository? {
        repos.first(where: { $0.isSelected })
    }

    private var selectedSourceURLBinding: Binding<String> {
        Binding(
            get: { selectedRepo?.sourceURL ?? "" },
            set: { newValue in
                guard let repo = repos.first(where: { $0.sourceURL == newValue }) else { return }
                selectRepository(repo)
            }
        )
    }

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if viewModel.repository == .flekstore {
                    ScrollView(.horizontal, showsIndicators: false) {
                        LazyHStack(spacing: 8) {
                            CategoryButton(
                                title: "Updates",
                                isSelected: viewModel.selectedCategoryID == nil
                            ) {
                                viewModel.selectCategory(nil)
                            }

                            CategoryButton(
                                title: "Top",
                                isSelected: viewModel.selectedCategoryID == "downloads"
                            ) {
                                viewModel.selectCategory("downloads")
                            }

                            ForEach(viewModel.categories) { cat in
                                CategoryButton(
                                    title: cat.name,
                                    isSelected: viewModel.selectedCategoryID == cat.id
                                ) {
                                    viewModel.selectCategory(cat.id)
                                }
                            }
                        }
                        .padding(.horizontal)
                    }
                    .frame(height: 44)
                }

                Group {
                    if viewModel.apps.isEmpty && viewModel.isLoading {
                        ProgressView("Loading apps…")
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let error = viewModel.errorMessage {
                        VStack(spacing: 12) {
                            Text(error)
                                .foregroundColor(.red)

                            Button("Retry") {
                                Task { await viewModel.resetAndFetchApps() }
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List {
                            ForEach(viewModel.visibleApps) { app in
                                AppRow(
                                    app: app,
                                    selectedTab: $selectedTab,
                                    isCustomRepository: viewModel.repository != .flekstore
                                )
                                .onAppear {
                                    if app == viewModel.apps.last {
                                        Task { await viewModel.fetchApps() }
                                    }
                                }
                            }

                            if viewModel.isLoading {
                                HStack {
                                    Spacer()
                                    ProgressView()
                                    Spacer()
                                }
                            }
                        }
                        .listStyle(.plain)
                        .refreshable {
                            Task { await viewModel.resetAndFetchApps() }
                        }
                    }
                }
            }
            .searchable(
                text: $viewModel.searchQuery,
                placement: .navigationBarDrawer(displayMode: .always),
                prompt: "Search by app name"
            )
            .onChange(of: viewModel.searchQuery) { _ in
                if viewModel.repository == .flekstore {
                    Task { await viewModel.resetAndFetchApps() }
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Picker("Repository", selection: selectedSourceURLBinding) {
                            ForEach(repos) { repo in
                                HStack(spacing: 8) {
                                    if let url = URL(string: repo.iconUrl) {
                                        KFImage(url)
                                            .placeholder { Color.gray.opacity(0.2) }
                                            .resizable()
                                            .scaledToFit()
                                            .frame(width: 16, height: 16)
                                            .clipShape(RoundedRectangle(cornerRadius: 4))
                                    } else {
                                        Image(systemName: "square.stack")
                                            .foregroundColor(.secondary)
                                    }
                                    Text(repo.name)
                                }
                                .tag(repo.sourceURL)
                            }
                        }
                        Divider()
                        Button("Manage Sources") {
                            showRepositorySheet = true
                        }
                    } label: {
                        HStack(spacing: 6) {
                            if let iconUrl = selectedRepo?.iconUrl,
                               let url = URL(string: iconUrl) {
                                KFImage(url)
                                    .placeholder { Color.gray.opacity(0.2) }
                                    .resizable()
                                    .scaledToFit()
                                    .frame(width: 16, height: 16)
                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                            } else {
                                Image(systemName: "square.stack")
                                    .foregroundColor(.secondary)
                            }
                            Text(selectedRepo?.name ?? "Sources")
                                .lineLimit(1)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 12))
                        }
                    }
                }
            }
            .sheet(isPresented: $showRepositorySheet) {
                AppRepositoryListView(
                    repos: $repos,
                    onSelect: { repo in
                        switchRepository(repo)
                    }
                )
            }
        }
        .onAppear {
            Task {
                if let repo = await loadRepos() {
                    switchRepository(repo)
                } else {
                    await viewModel.fetchApps()
                }
            }
        }
    }

    // MARK: - Repos

    private func selectRepository(_ repo: AppRepository) {
        let updated = repos.map {
            AppRepository(
                name: $0.name,
                iconUrl: $0.iconUrl,
                sourceURL: $0.sourceURL,
                isSelected: $0.sourceURL == repo.sourceURL
            )
        }
        repos = updated
        saveRepos(updated)
        switchRepository(repo)
    }

    private func switchRepository(_ repo: AppRepository) {
        viewModel.searchQuery = ""

        if repo.sourceURL == "Default app catalog" {
            viewModel.repository = .flekstore
        } else {
            viewModel.repository = .custom(url: repo.sourceURL)
        }

        Task {
            await viewModel.resetAndFetchApps()
        }
    }

    private func loadRepos() async -> AppRepository? {
        if let data = UserDefaults.standard.data(forKey: "savedRepositories"),
           let savedRepos = try? JSONDecoder().decode([AppRepository].self, from: data) {
            await MainActor.run {
                self.repos = savedRepos
            }
            return savedRepos.first(where: { $0.isSelected })
        }
        return nil
    }

    private func saveRepos(_ repos: [AppRepository]) {
        if let data = try? JSONEncoder().encode(repos) {
            UserDefaults.standard.set(data, forKey: "savedRepositories")
        }
    }
}

fileprivate struct CategoryButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline)
                .lineLimit(1)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    Group {
                        if isSelected {
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color.blue)
                        } else {
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color.gray.opacity(0.16))
                        }
                    }
                )
                .foregroundColor(isSelected ? .white : .primary)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(isSelected ? Color.blue.opacity(0.8) : Color.clear, lineWidth: 0)
                )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct AppRow: View {
    let app: FSAppModel
    @Binding var selectedTab: LCTabIdentifier
    @EnvironmentObject private var flekstoreSharedModel: FlekstoreSharedModel

    let isCustomRepository: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            KFImage(URL(string: app.app_icon))
                .placeholder { Color.gray.opacity(0.2) }
                .resizable()
                .scaledToFit()
                .frame(width: 60, height: 60)
                .cornerRadius(12)

            VStack(alignment: .leading, spacing: 4) {
                Text(app.app_name)
                    .font(.headline)
                    .lineLimit(1)

                Text("Version \(app.app_version)")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                Text(app.app_short_description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }

            Spacer()
            VStack {
                Spacer()
                Button(action: {
                    selectedTab = .apps
                    flekstoreSharedModel.appInstallURL = app.install_url
                    if !isCustomRepository {
                        FlekstoreAppsListViewModel.recordDownload(appId: app.app_id)
                    }
                }) {
                    Text("GET")
                        .font(.subheadline.bold())
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(14)
                }
                Spacer()
            }
        }
        .padding(.vertical, 6)
    }
}

#Preview {
    FlekstoreAppsListView(
        selectedTab: .constant(.apps)
    )
    .environmentObject(FlekstoreSharedModel())
}
