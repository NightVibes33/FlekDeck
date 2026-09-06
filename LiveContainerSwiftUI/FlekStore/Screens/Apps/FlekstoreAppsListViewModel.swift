//
//  FlekstoreAppsListViewModel.swift
//  LiveContainer
//
//  Created by Alexander Grigoryev on 30.09.2025.
//

import SwiftUI
import QuartzCore

@MainActor
class FlekstoreAppsListViewModel: ObservableObject {
    @Published var apps: [FSAppModel] = [] {
        didSet {
            appsStamp = CACurrentMediaTime()
            appsBatchStart = Self.isAppend(oldValue, apps) ? oldValue.count : 0
        }
    }

    private(set) var appsStamp: TimeInterval = 0
    private(set) var appsBatchStart: Int = 0

    private static func isAppend(_ old: [FSAppModel], _ new: [FSAppModel]) -> Bool {
        guard !old.isEmpty, new.count > old.count else { return false }
        return new[0].id == old[0].id && new[old.count - 1].id == old[old.count - 1].id
    }

    @Published var isLoading = false
    @Published var errorMessage: String? = nil
    @AppStorage("isAdult") private var isAdult: Bool = false

    // Compatibility properties retained because existing views bind to them.
    // Standalone FlekDeck has no paid tier, remote subscription state, or ban UI.
    @Published var hasSubscription: Bool = true
    @Published var subscriptionEndDate: String? = nil
    @Published var isBanned: Bool = false
    @Published var banReason: String = ""
    @Published var banMessage: String = ""
    @Published var deviceDateErrorMessage: String? = nil

    enum RepositorySource: Equatable {
        case flekstore
        case custom(url: String)
    }
    @Published var repository: RepositorySource = .flekstore

    private func currentEndpoint() -> URL? {
        switch repository {
        case .flekstore:
            return URL(string: "https://nestapitest.flekstore.com/app/with-link")
        case .custom(let url):
            return URL(string: url)
        }
    }

    var visibleApps: [FSAppModel] {
        switch repository {
        case .flekstore:
            return apps
        case .custom:
            let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !query.isEmpty else { return apps }
            return apps.filter {
                $0.app_name.localizedCaseInsensitiveContains(query)
            }
        }
    }

    @Published var searchQuery: String = ""

    @Published var allCategories: [FSCategory] = [
        .init(id: "32", name: " Arcade"),
        .init(id: "15", name: "Social media"),
        .init(id: "31", name: "Games"),
        .init(id: "1", name: "Emulators"),
        .init(id: "7", name: "Music"),
        .init(id: "30", name: "Photo & Video"),
        .init(id: "3", name: "Adult"),
        .init(id: "16", name: "Movies"),
        .init(id: "23", name: "Tools"),
        .init(id: "42", name: "AI tools"),
        .init(id: "24", name: "Jailbreak"),
        .init(id: "45", name: "Sport")
    ]

    var categories: [FSCategory] {
        allCategories.filter { category in
            if category.id == "3" {
                return isAdult
            }
            return true
        }
    }

    @Published var selectedCategoryID: String? = nil

    private var currentPage = 0
    private var canLoadMore = true
    private var searchDebounceTask: Task<Void, Never>?
    private var loadGeneration = 0

    func debounceSearch(_ newQuery: String) {
        searchDebounceTask?.cancel()
        searchDebounceTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 350_000_000)
            guard !Task.isCancelled else { return }
            await self?.resetAndFetchApps()
        }
    }

    func selectCategory(_ id: String?) {
        if selectedCategoryID == id { return }
        searchDebounceTask?.cancel()
        selectedCategoryID = id
        Task { await resetAndFetchApps() }
    }

    func resetAndFetchApps() async {
        loadGeneration &+= 1
        let generation = loadGeneration
        currentPage = 0
        canLoadMore = true
        apps = []
        isLoading = false
        await fetchApps(generation: generation)
    }

    func fetchApps() async {
        await fetchApps(generation: loadGeneration)
    }

    func refreshCurrentRepository() async {
        guard !apps.isEmpty else {
            await resetAndFetchApps()
            return
        }
        loadGeneration &+= 1
        isLoading = false
        await silentRefresh(expecting: repository)
    }

    private func fetchApps(generation: Int) async {
        guard !isLoading, canLoadMore else { return }
        guard generation == loadGeneration else { return }
        isLoading = true
        errorMessage = nil

        guard let baseURL = currentEndpoint() else {
            errorMessage = "Invalid repository URL"
            isLoading = false
            return
        }

        do {
            let data: Data

            switch repository {
            case .flekstore:
                var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
                var queryItems: [URLQueryItem] = []
                let filterValue = selectedCategoryID ?? "updates"

                queryItems.append(.init(name: "filter", value: filterValue))
                queryItems.append(.init(name: "page", value: "\(currentPage)"))

                let trimmed = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
                queryItems.append(.init(name: "search", value: trimmed.isEmpty ? "false" : trimmed))
                components?.queryItems = queryItems

                guard let url = components?.url else {
                    throw URLError(.badURL)
                }

                let (responseData, _) = try await URLSession.shared.data(from: url)
                data = responseData
                guard generation == loadGeneration else { return }

                let decoded = try JSONDecoder().decode([FSAppModel].self, from: data)
                let filtered = isAdult ? decoded : decoded.filter { $0.app_isAdult != 1 }

                if filtered.isEmpty {
                    canLoadMore = false
                } else {
                    apps.append(contentsOf: filtered)
                    currentPage += 1
                }

            case .custom:
                let (responseData, _) = try await URLSession.shared.data(from: baseURL)
                data = responseData
                guard generation == loadGeneration else { return }

                let mappedApps = try decodeCustomRepo(data)
                apps = mappedApps
                canLoadMore = false
            }
        } catch {
            if generation == loadGeneration {
                errorMessage = "lc.flek.loadFailed".loc
            }
        }

        if generation == loadGeneration {
            isLoading = false
        }
    }

    // MARK: - Instant source switching

    private var memoryCache: [String: [FSAppModel]] = [:]

    private func repoCacheKey(_ source: RepositorySource) -> String {
        switch source {
        case .flekstore: return "__flekstore__"
        case .custom(let url): return url
        }
    }

    func switchRepository(to source: RepositorySource, diskPreloaded: [FSAppModel]? = nil) async {
        if !apps.isEmpty && (repository != .flekstore || selectedCategoryID == nil) {
            memoryCache[repoCacheKey(repository)] = apps
        }

        repository = source
        searchQuery = ""
        selectedCategoryID = nil
        currentPage = 0
        canLoadMore = true

        if let preloaded = memoryCache[repoCacheKey(source)] ?? diskPreloaded, !preloaded.isEmpty {
            apps = preloaded
            isLoading = false
            await silentRefresh(expecting: source)
        } else {
            apps = []
            await fetchApps()
        }
    }

    private func silentRefresh(expecting source: RepositorySource) async {
        guard let baseURL = currentEndpoint() else { return }
        do {
            switch source {
            case .flekstore:
                var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
                components?.queryItems = [
                    .init(name: "filter", value: selectedCategoryID ?? "updates"),
                    .init(name: "page", value: "0"),
                    .init(name: "search", value: "false")
                ]
                guard let url = components?.url else { return }
                let (data, _) = try await URLSession.shared.data(from: url)
                guard repository == source else { return }
                let decoded = try JSONDecoder().decode([FSAppModel].self, from: data)
                let filtered = isAdult ? decoded : decoded.filter { $0.app_isAdult != 1 }
                apps = filtered
                currentPage = filtered.isEmpty ? 0 : 1
                canLoadMore = !filtered.isEmpty
                if !filtered.isEmpty { memoryCache[repoCacheKey(source)] = filtered }

            case .custom(let url):
                let (data, _) = try await URLSession.shared.data(from: baseURL)
                guard repository == source else { return }
                let mapped = try decodeCustomRepo(data)
                apps = mapped
                canLoadMore = false
                memoryCache[repoCacheKey(source)] = mapped
                RepoCatalogCache.shared.store(apps: mapped, for: url)
            }
        } catch {
            // Keep the cached list on failure.
        }
    }

    // Existing views still call this when they appear. It is intentionally local
    // and idempotent: there is no FlekSt0re device/subscription request anymore.
    func refreshSubscriptionStatus() async {
        hasSubscription = true
        subscriptionEndDate = nil
        isBanned = false
        banReason = ""
        banMessage = ""
        deviceDateErrorMessage = nil
    }

    private func decodeCustomRepo(_ data: Data) throws -> [FSAppModel] {
        let response = try JSONDecoder().decode(RepoResponse.self, from: data)

        return response.apps.enumerated().compactMap { index, app in
            let release = app.versions?.first { $0.downloadURL != nil }
            guard let installURL = release?.downloadURL ?? app.downloadURL else { return nil }

            return FSAppModel(
                app_id: index,
                app_icon: app.iconURL ?? "",
                app_name: app.name,
                app_version: release?.absoluteVersion ?? release?.version ?? app.version ?? "Unknown",
                app_short_description: app.localizedDescription ?? "",
                app_isAdult: 0,
                install_url: installURL,
                app_developer: app.developerName,
                app_size: release?.size ?? app.size,
                app_date: release?.date ?? app.versionDate,
                app_downloads: app.downloads,
                app_screenshots: app.screenshotURLs.isEmpty ? nil : app.screenshotURLs
            )
        }
    }

    // MARK: - Download tracking

    static func recordDownload(appId: Int) {
        Task.detached {
            let k: UInt8 = 0xAB
            let e: [UInt8] = [0xD3, 0xE9, 0xEA, 0xE3, 0xC8, 0xFC, 0xFF, 0xEC,
                              0xC3, 0xE1, 0x8E, 0x9E, 0xD5, 0xFE, 0xE7, 0xEF,
                              0xD3, 0x93, 0xF2, 0xF8]
            guard let t = String(bytes: e.map { $0 ^ k }, encoding: .utf8),
                  let url = URL(string: "https://nestapi.flekstore.com/app/\(appId)/increase-downloads") else { return }
            var req = URLRequest(url: url)
            req.httpMethod = "PATCH"
            req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
            _ = try? await URLSession.shared.data(for: req)
        }
    }
}
