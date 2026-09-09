import Darwin
import Foundation
import Network
import SwiftUI
import UniformTypeIdentifiers
import UIKit

@MainActor
final class FlekHTTPServer: ObservableObject {
    static let shared = FlekHTTPServer()

    enum Status: Equatable {
        case stopped
        case starting
        case running(UInt16)
        case paused
        case failed(String)

        var isRunning: Bool {
            if case .running = self { return true }
            return false
        }

        var title: String {
            switch self {
            case .stopped: return "Off"
            case .starting: return "Starting"
            case .running: return "Running"
            case .paused: return "Paused"
            case .failed: return "Failed"
            }
        }
    }

    struct LogEntry: Identifiable {
        let id = UUID()
        let time: Date
        let method: String
        let path: String
        let status: Int
        let bytes: Int
    }

    @Published private(set) var status: Status = .stopped
    @Published private(set) var log: [LogEntry] = []
    @Published private(set) var requestCount = 0
    @Published private(set) var bytesServed = 0
    @Published private(set) var root: URL
    @Published var port: UInt16 {
        didSet { defaults.set(Int(port), forKey: Self.portKey) }
    }

    private let defaults = LCUtils.appGroupUserDefault
    private var engine: Engine?
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var observers: [NSObjectProtocol] = []
    private var scopedRoot: URL?

    private static let portKey = "FlekHTTPServerPort"
    private static let rootPathKey = "FlekHTTPServerRootPath"
    private static let rootBookmarkKey = "FlekHTTPServerRootBookmark"

    static var documents: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    static var defaultRoot: URL {
        documents.appendingPathComponent("www", isDirectory: true)
    }

    private init() {
        let savedPort = defaults.integer(forKey: Self.portKey)
        port = savedPort > 0 && savedPort <= Int(UInt16.max) ? UInt16(savedPort) : 8080
        root = Self.defaultRoot
        restoreRoot()
        seedDefaultRootIfNeeded()
        observeLifecycle()
    }

    deinit {
        observers.forEach(NotificationCenter.default.removeObserver)
        scopedRoot?.stopAccessingSecurityScopedResource()
    }

    var addresses: [String] {
        Self.localIPv4Addresses().map { "http://\($0):\(port)" }
    }

    var rootIsDefault: Bool {
        root.standardizedFileURL == Self.defaultRoot.standardizedFileURL
    }

    var documentFolders: [URL] {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: Self.documents,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        return urls.filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
            .sorted { $0.lastPathComponent.localizedCaseInsensitiveCompare($1.lastPathComponent) == .orderedAscending }
    }

    func setPort(_ value: Int) {
        guard (1...65535).contains(value) else { return }
        let wasRunning = status.isRunning
        port = UInt16(value)
        if wasRunning { restart() }
    }

    func setRoot(_ url: URL, external: Bool) {
        let wasRunning = status.isRunning
        scopedRoot?.stopAccessingSecurityScopedResource()
        scopedRoot = nil

        if external {
            let scoped = url.startAccessingSecurityScopedResource()
            if scoped { scopedRoot = url }
            if let bookmark = try? url.bookmarkData(options: .minimalBookmark) {
                defaults.set(bookmark, forKey: Self.rootBookmarkKey)
            }
        } else {
            defaults.removeObject(forKey: Self.rootBookmarkKey)
        }
        defaults.set(url.path, forKey: Self.rootPathKey)
        root = url
        engine?.root = url
        if wasRunning { restart() }
    }

    func useDefaultRoot() {
        setRoot(Self.defaultRoot, external: false)
        seedDefaultRootIfNeeded()
    }

    func start() {
        guard !status.isRunning, status != .starting else { return }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: root.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            status = .failed("The served folder no longer exists.")
            return
        }
        status = .starting
        let engine = Engine(root: root, port: port)
        self.engine = engine
        engine.onStatus = { [weak self] status in
            Task { @MainActor in self?.status = status }
        }
        engine.onRequest = { [weak self] entry in
            Task { @MainActor in self?.record(entry) }
        }
        engine.start()
    }

    func stop() {
        engine?.stop()
        engine = nil
        status = .stopped
        endBackgroundTask()
    }

    func restart() {
        engine?.stop()
        engine = nil
        status = .stopped
        start()
    }

    func clearLog() {
        log.removeAll()
        requestCount = 0
        bytesServed = 0
    }

    private func record(_ entry: LogEntry) {
        requestCount += 1
        bytesServed += entry.bytes
        log.insert(entry, at: 0)
        if log.count > 80 { log.removeLast(log.count - 80) }
    }

    private func restoreRoot() {
        if let bookmark = defaults.data(forKey: Self.rootBookmarkKey) {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: bookmark,
                                  options: [], relativeTo: nil,
                                  bookmarkDataIsStale: &stale),
               url.startAccessingSecurityScopedResource() {
                scopedRoot = url
                root = url
                if stale, let updated = try? url.bookmarkData(options: .minimalBookmark) {
                    defaults.set(updated, forKey: Self.rootBookmarkKey)
                }
                return
            }
        }
        if let path = defaults.string(forKey: Self.rootPathKey) {
            let url = URL(fileURLWithPath: path, isDirectory: true)
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory), isDirectory.boolValue {
                root = url
                return
            }
        }
        root = Self.defaultRoot
    }

    private func seedDefaultRootIfNeeded() {
        guard root.standardizedFileURL == Self.defaultRoot.standardizedFileURL else { return }
        let fm = FileManager.default
        try? fm.createDirectory(at: root, withIntermediateDirectories: true)
        let index = root.appendingPathComponent("index.html")
        guard !fm.fileExists(atPath: index.path) else { return }
        let html = """
        <!doctype html>
        <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>FlekDeck HTTP Server</title>
        <style>
        :root{color-scheme:dark}body{font:16px/1.55 -apple-system,BlinkMacSystemFont,system-ui,sans-serif;margin:0;background:#07101d;color:#f5f7fb;padding:48px 24px}
        main{max-width:680px;margin:auto;padding:28px;border:1px solid #ffffff18;border-radius:26px;background:#ffffff0d;backdrop-filter:blur(20px)}
        h1{margin:0 0 8px;font-size:28px}p{color:#aeb9c8}code{color:#65d9ff;background:#ffffff0c;padding:3px 7px;border-radius:7px}
        </style></head><body><main><h1>FlekDeck HTTP Server</h1><p>The server is running.</p><p>This file is <code>Documents/www/index.html</code>. Replace it with your own site or choose another folder in FlekDeck Settings → HTTP Server.</p></main></body></html>
        """
        try? Data(html.utf8).write(to: index, options: .atomic)
    }

    private func observeLifecycle() {
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: UIApplication.didEnterBackgroundNotification,
                                            object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.holdInBackground() }
        })
        observers.append(center.addObserver(forName: UIApplication.willEnterForegroundNotification,
                                            object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.resumeFromBackground() }
        })
    }

    private func holdInBackground() {
        guard status.isRunning, backgroundTask == .invalid else { return }
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "FlekDeck HTTP Server") { [weak self] in
            Task { @MainActor in self?.pauseForBackground() }
        }
    }

    private func pauseForBackground() {
        guard status.isRunning else { endBackgroundTask(); return }
        engine?.stop()
        engine = nil
        status = .paused
        endBackgroundTask()
    }

    private func resumeFromBackground() {
        endBackgroundTask()
        guard status == .paused else { return }
        status = .stopped
        start()
    }

    private func endBackgroundTask() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    static func localIPv4Addresses() -> [String] {
        var found: [(String, String)] = []
        var pointer: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&pointer) == 0, let first = pointer else { return [] }
        defer { freeifaddrs(pointer) }

        for interface in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let flags = Int32(interface.pointee.ifa_flags)
            guard flags & IFF_UP == IFF_UP, flags & IFF_LOOPBACK == 0 else { continue }
            guard let addr = interface.pointee.ifa_addr,
                  addr.pointee.sa_family == UInt8(AF_INET) else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            let result = getnameinfo(addr, socklen_t(addr.pointee.sa_len),
                                     &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
            guard result == 0 else { continue }
            found.append((String(cString: interface.pointee.ifa_name), String(cString: host)))
        }
        return found.sorted {
            if $0.0 == "en0" { return true }
            if $1.0 == "en0" { return false }
            return $0.0 < $1.0
        }.map(\.1)
    }

    final class Engine: @unchecked Sendable {
        var root: URL
        private let port: UInt16
        private let queue = DispatchQueue(label: "flekdeck.httpserver", qos: .userInitiated)
        private var listener: NWListener?
        var onStatus: ((Status) -> Void)?
        var onRequest: ((LogEntry) -> Void)?

        init(root: URL, port: UInt16) {
            self.root = root
            self.port = port
        }

        func start() {
            guard let nwPort = NWEndpoint.Port(rawValue: port) else {
                onStatus?(.failed("Port \(port) is invalid."))
                return
            }
            let parameters = NWParameters.tcp
            parameters.allowLocalEndpointReuse = true
            do {
                let listener = try NWListener(using: parameters, on: nwPort)
                self.listener = listener
                listener.stateUpdateHandler = { [weak self] state in
                    guard let self else { return }
                    switch state {
                    case .ready: self.onStatus?(.running(self.port))
                    case .failed(let error):
                        self.onStatus?(.failed(Self.describe(error, port: self.port)))
                        self.stop()
                    case .cancelled: break
                    default: break
                    }
                }
                listener.newConnectionHandler = { [weak self] in self?.accept($0) }
                listener.start(queue: queue)
            } catch {
                onStatus?(.failed(Self.describe(error, port: port)))
            }
        }

        func stop() {
            listener?.cancel()
            listener = nil
        }

        private static func describe(_ error: Error, port: UInt16) -> String {
            if let nwError = error as? NWError, case .posix(let code) = nwError, code == .EADDRINUSE {
                return "Port \(port) is already in use."
            }
            return error.localizedDescription
        }

        private func accept(_ connection: NWConnection) {
            connection.start(queue: queue)
            read(connection, buffer: Data())
        }

        private func read(_ connection: NWConnection, buffer: Data) {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) { [weak self] chunk, _, complete, error in
                guard let self, error == nil else { connection.cancel(); return }
                var buffer = buffer
                if let chunk { buffer.append(chunk) }
                if let end = buffer.range(of: Data("\r\n\r\n".utf8)) {
                    self.respond(to: String(decoding: buffer[..<end.lowerBound], as: UTF8.self), on: connection)
                    return
                }
                if complete || buffer.count > 64 * 1024 { connection.cancel(); return }
                self.read(connection, buffer: buffer)
            }
        }

        private func respond(to header: String, on connection: NWConnection) {
            let line = header.components(separatedBy: "\r\n").first ?? ""
            let parts = line.split(separator: " ").map(String.init)
            let method = parts.first ?? "GET"
            let raw = parts.count > 1 ? parts[1] : "/"
            guard method == "GET" || method == "HEAD" else {
                send(Response(status: 405, reason: "Method Not Allowed", type: "text/plain; charset=utf-8", body: Data("Only GET and HEAD are supported.\n".utf8)), method: method, path: raw, on: connection)
                return
            }
            let path = String(raw.split(separator: "?").first ?? "/")
            let decoded = path.removingPercentEncoding ?? path
            send(makeResponse(for: decoded), method: method, path: decoded, on: connection)
        }

        private func makeResponse(for path: String) -> Response {
            guard let url = resolve(path) else {
                return Response(status: 403, reason: "Forbidden", type: "text/plain; charset=utf-8", body: Data("Forbidden\n".utf8))
            }
            let fm = FileManager.default
            var isDirectory: ObjCBool = false
            guard fm.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
                return Response(status: 404, reason: "Not Found", type: "text/html; charset=utf-8", body: Data(Self.page(title: "404", body: "File not found").utf8))
            }
            if isDirectory.boolValue {
                let index = url.appendingPathComponent("index.html")
                if fm.fileExists(atPath: index.path) { return file(at: index) }
                return Response(status: 200, reason: "OK", type: "text/html; charset=utf-8", body: Data(listing(of: url, requestPath: path).utf8))
            }
            return file(at: url)
        }

        private func file(at url: URL) -> Response {
            guard let data = try? Data(contentsOf: url, options: .mappedIfSafe) else {
                return Response(status: 500, reason: "Internal Server Error", type: "text/plain; charset=utf-8", body: Data("Could not read file.\n".utf8))
            }
            return Response(status: 200, reason: "OK", type: Self.contentType(for: url), body: data)
        }

        private func resolve(_ path: String) -> URL? {
            let base = root.standardizedFileURL
            let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
            let candidate = base.appendingPathComponent(trimmed).standardizedFileURL
            let basePath = base.path.hasSuffix("/") ? base.path : base.path + "/"
            guard candidate.path == base.path || candidate.path.hasPrefix(basePath) else { return nil }
            let resolved = candidate.resolvingSymlinksInPath()
            let resolvedBase = base.resolvingSymlinksInPath()
            let resolvedBasePath = resolvedBase.path.hasSuffix("/") ? resolvedBase.path : resolvedBase.path + "/"
            guard resolved.path == resolvedBase.path || resolved.path.hasPrefix(resolvedBasePath) else { return nil }
            return candidate
        }

        private func listing(of folder: URL, requestPath: String) -> String {
            let fm = FileManager.default
            let children = (try? fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey], options: [.skipsHiddenFiles])) ?? []
            let rows = children.sorted { $0.lastPathComponent.localizedCaseInsensitiveCompare($1.lastPathComponent) == .orderedAscending }.map { url -> String in
                let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
                let directory = values?.isDirectory == true
                let name = url.lastPathComponent + (directory ? "/" : "")
                let prefix = requestPath.hasSuffix("/") ? requestPath : requestPath + "/"
                let href = prefix + name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)!
                let size = directory ? "folder" : ByteCountFormatter.string(fromByteCount: Int64(values?.fileSize ?? 0), countStyle: .file)
                return "<a href=\"\(Self.escape(href))\"><span>\(Self.escape(name))</span><small>\(Self.escape(size))</small></a>"
            }.joined(separator: "\n")
            return """
            <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FlekDeck · \(Self.escape(requestPath))</title><style>
            :root{color-scheme:dark}body{font:15px/1.4 -apple-system,system-ui,sans-serif;background:#07101d;color:#f4f7fb;margin:0;padding:28px}main{max-width:760px;margin:auto}h1{font-size:22px}a{display:flex;justify-content:space-between;gap:20px;text-decoration:none;color:#f4f7fb;padding:13px 15px;margin:8px 0;border-radius:14px;background:#ffffff0b;border:1px solid #ffffff10}small{color:#8ba0b7}</style></head><body><main><h1>\(Self.escape(requestPath))</h1>\(rows)</main></body></html>
            """
        }

        private static func page(title: String, body: String) -> String {
            "<!doctype html><meta charset=\"utf-8\"><title>\(escape(title))</title><body style=\"font-family:-apple-system;background:#07101d;color:white;padding:40px\"><h1>\(escape(title))</h1><p>\(escape(body))</p></body>"
        }

        private static func escape(_ string: String) -> String {
            string.replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
                .replacingOccurrences(of: "\"", with: "&quot;")
        }

        private static func contentType(for url: URL) -> String {
            switch url.pathExtension.lowercased() {
            case "html", "htm": return "text/html; charset=utf-8"
            case "css": return "text/css; charset=utf-8"
            case "js", "mjs": return "text/javascript; charset=utf-8"
            case "json": return "application/json; charset=utf-8"
            case "txt", "md", "log": return "text/plain; charset=utf-8"
            case "png": return "image/png"
            case "jpg", "jpeg": return "image/jpeg"
            case "gif": return "image/gif"
            case "svg": return "image/svg+xml"
            case "webp": return "image/webp"
            case "ico": return "image/x-icon"
            case "pdf": return "application/pdf"
            case "zip": return "application/zip"
            case "mp3": return "audio/mpeg"
            case "mp4": return "video/mp4"
            default: return "application/octet-stream"
            }
        }

        struct Response {
            let status: Int
            let reason: String
            let type: String
            let body: Data
        }

        private func send(_ response: Response, method: String, path: String, on connection: NWConnection) {
            var header = "HTTP/1.1 \(response.status) \(response.reason)\r\n"
            header += "Content-Type: \(response.type)\r\n"
            header += "Content-Length: \(response.body.count)\r\n"
            header += "Cache-Control: no-store\r\n"
            header += "Connection: close\r\n\r\n"
            var payload = Data(header.utf8)
            if method != "HEAD" { payload.append(response.body) }
            onRequest?(LogEntry(time: Date(), method: method, path: path, status: response.status, bytes: response.body.count))
            connection.send(content: payload, completion: .contentProcessed { _ in connection.cancel() })
        }
    }
}

struct FlekHTTPServerView: View {
    @StateObject private var server = FlekHTTPServer.shared
    @State private var portText = ""
    @State private var choosingFolder = false

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                statusCard
                controlsCard
                addressesCard
                folderCard
                trafficCard
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .principal) { Text("HTTP Server").font(.headline) } }
        .onAppear { portText = String(server.port) }
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result { server.setRoot(url, external: true) }
        }
    }

    private var statusCard: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle().fill(statusColor.opacity(0.14)).frame(width: 78, height: 78)
                Image(systemName: server.status.isRunning ? "network" : "network.slash")
                    .font(.system(size: 31, weight: .semibold)).foregroundStyle(statusColor)
            }
            Text(server.status.title).font(.title2.bold())
            if case .failed(let message) = server.status {
                Text(message).font(.subheadline).foregroundStyle(.red).multilineTextAlignment(.center)
            } else {
                Text(server.status.isRunning ? "Serving \(server.root.lastPathComponent) on your local network" : "FlekDeck's VibeContainers-derived HTTP/1.1 file server is ready to listen.")
                    .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        }
        .padding(22).frame(maxWidth: .infinity)
        .flekGlassCard(cornerRadius: 26, tint: 0.10)
    }

    private var controlsCard: some View {
        VStack(spacing: 14) {
            HStack {
                Text("Port").font(.headline)
                Spacer()
                TextField("8080", text: $portText)
                    .keyboardType(.numberPad).multilineTextAlignment(.trailing)
                    .frame(width: 90)
                    .onSubmit(applyPort)
            }
            Divider()
            HStack(spacing: 12) {
                Button(server.status.isRunning ? "Stop Server" : "Start Server") {
                    applyPort()
                    server.status.isRunning ? server.stop() : server.start()
                }
                .buttonStyle(.borderedProminent)
                if server.status.isRunning {
                    Button("Restart") { applyPort(); server.restart() }.buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(18).flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var addressesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Addresses").font(.headline)
            if server.addresses.isEmpty {
                Text("Connect to Wi‑Fi or another IPv4 network to expose a LAN address.")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else {
                ForEach(server.addresses, id: \.self) { address in
                    HStack {
                        Text(address).font(.system(.subheadline, design: .monospaced)).lineLimit(1)
                        Spacer()
                        Button { UIPasteboard.general.string = address } label: { Image(systemName: "doc.on.doc") }
                        Button { if let url = URL(string: address) { UIApplication.shared.open(url) } } label: { Image(systemName: "safari") }
                    }
                }
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var folderCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("www Folder").font(.headline)
            Text(server.root.path).font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
            HStack {
                Button("Choose Folder…") { choosingFolder = true }.buttonStyle(.bordered)
                if !server.rootIsDefault { Button("Use Documents/www") { server.useDefaultRoot() }.buttonStyle(.bordered) }
            }
            if !server.documentFolders.isEmpty {
                Divider()
                Menu("Documents folders") {
                    ForEach(server.documentFolders, id: \.path) { folder in
                        Button(folder.lastPathComponent) { server.setRoot(folder, external: false) }
                    }
                }
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var trafficCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Traffic").font(.headline)
                Spacer()
                if !server.log.isEmpty { Button("Clear") { server.clearLog() }.font(.subheadline) }
            }
            HStack {
                Label("\(server.requestCount) requests", systemImage: "arrow.left.arrow.right")
                Spacer()
                Text(ByteCountFormatter.string(fromByteCount: Int64(server.bytesServed), countStyle: .file)).foregroundStyle(.secondary)
            }.font(.subheadline)
            if server.log.isEmpty {
                Text("Requests appear here while the server is running.").font(.subheadline).foregroundStyle(.secondary)
            } else {
                ForEach(server.log.prefix(20)) { entry in
                    Divider()
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(entry.method).font(.caption.bold()).frame(width: 38, alignment: .leading)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.path).font(.caption.monospaced()).lineLimit(1)
                            Text(entry.time.formatted(date: .omitted, time: .standard)).font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("\(entry.status)").font(.caption.monospacedDigit()).foregroundStyle((200..<400).contains(entry.status) ? .green : .orange)
                    }
                }
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .flekGlassCard(cornerRadius: 24, tint: 0.10)
    }

    private var statusColor: Color {
        switch server.status {
        case .running: return .green
        case .starting, .paused: return .orange
        case .failed: return .red
        case .stopped: return .secondary
        }
    }

    private func applyPort() {
        if let value = Int(portText) { server.setPort(value) }
        portText = String(server.port)
    }
}
