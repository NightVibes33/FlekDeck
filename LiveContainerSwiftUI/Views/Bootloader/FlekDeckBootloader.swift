/*
 Adapted for FlekDeck from Nyxian's recovery implementation.
 Nyxian source copyright emexlab; licensed under AGPL-3.0-or-later.
 The imported ROM archive is retained unchanged in FlekDeck's shared boot store.
*/

/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 Copyright (C) 2025 - 2026 emexlab

 This file is part of Nyxian.

 Nyxian is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 Nyxian is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with Nyxian. If not, see <https://www.gnu.org/licenses/>.
*/

import UIKit
import SwiftUI
import UniformTypeIdentifiers
import CryptoKit
import Darwin

final class ROMImporter: NSObject, UIDocumentPickerDelegate {
    private var completion: ((URL?) -> Void)?
    
    func present(from viewController: UIViewController, completion: @escaping (URL?) -> Void) {
        self.completion = completion
        
        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes: [UTType.zip],
            asCopy: true
        )
        
        picker.delegate = self
        picker.allowsMultipleSelection = false
        
        viewController.present(picker, animated: true)
    }
    
    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        let url = urls.first
        
        completion?(url)
        completion = nil
    }
    
    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        completion?(nil)
        completion = nil
    }
}

final class ROMPath {
    let path: String
    let permission: Int
    
    struct ROMPathCodeSigningInfo {
        let needed: Bool
        let neededNXT2: Bool
        let nxt2: [String:Any]
    }
    let codesigning: ROMPath.ROMPathCodeSigningInfo
    
    init(path: String,
         permission: Int,
         codesigning: ROMPath.ROMPathCodeSigningInfo) {
        self.path = path
        self.permission = permission
        self.codesigning = codesigning
    }
}

func adaptiveImage(light: UIImage, dark: UIImage) -> UIImage {
    let asset = UIImageAsset()
    let lightTraits = UITraitCollection(traitsFrom: [
        .current,
        UITraitCollection(userInterfaceStyle: .light)
    ])
    asset.register(light, with: lightTraits)
    let darkTraits = UITraitCollection(traitsFrom: [
        .current,
        UITraitCollection(userInterfaceStyle: .dark)
    ])
    asset.register(dark, with: darkTraits)
    return asset.image(with: .current)
}

final class ROMManifest {
    // ABI
    let manifestVersion: Int
    
    // identity
    let identifier: String
    let name: String
    let version: String
    let minimumNyxianVersion: String
    
    // file permissions
    let defaultFilePermission: Int
    let defaultDirectoryPermission: Int
    let paths: [ROMPath]
    
    // runtime
    let installer: String?
    let uninstaller: String?
    let executable: String
    
    // bootlogo
    let bootlogo: UIImage?
    
    // The Nyxian minimum version remains recorded for compatibility reporting.
    // FlekDeck validates the manifest ABI separately and never claims to provide
    // Nyxian's userspace runtime.
    init(manifestPlistURL: URL) throws {
        // first we'll read the plist
        guard let manifestContent = NSDictionary(contentsOf: manifestPlistURL) as? [String: Any] else {
            throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 1, userInfo: [NSLocalizedDescriptionKey:"failed to read manifest plist"])
        }
        
        // next we need to parse version
        guard let manifestVersion = manifestContent["NXRomManifestVersion"] as? Int,
              manifestVersion == 1,
              let identifier = manifestContent["NXRomIdentifier"] as? String,
              !identifier.isEmpty,
              let name = manifestContent["NXRomName"] as? String,
              let version = manifestContent["NXRomVersion"] as? String,
              let minimumNyxianVersion = manifestContent["NXRomMinimumNyxianVersion"] as? String,
              let executable = manifestContent["NXRomExecutable"] as? String,
              !executable.isEmpty else {
            throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "unsupported or malformed ROM manifest (FlekDeck supports manifest ABI 1)."])
        }
        
        guard minimumNyxianVersion.compare("0.11.5", options: .numeric) != .orderedDescending else {
            throw romError("This ROM requires Nyxian client ABI \(minimumNyxianVersion); FlekDeck currently supplies the 0.11.5 client adapter.")
        }

        // ABI
        self.manifestVersion = manifestVersion
        
        // identity
        self.identifier = identifier
        self.name = name
        self.version = version
        self.minimumNyxianVersion = minimumNyxianVersion
        
        // file permissions
        let defaultFilePermission = manifestContent["NXRomDefaultFilePermission"] as? Int ?? 420
        let defaultDirectoryPermission = manifestContent["NXRomDefaultDirectoryPermission"] as? Int ?? 493
        self.defaultFilePermission = defaultFilePermission
        self.defaultDirectoryPermission = defaultDirectoryPermission
        
        // parsing explicit paths
        var actualPathObjects: [ROMPath] = []
        let paths: [[String:Any]] = manifestContent["NXRomPaths"] as? [[String:Any]] ?? []
        for pathDict in paths {
            let permission: Int = pathDict["NXPermission"] as? Int ?? defaultFilePermission
            let requiresCodeSigning: Bool = pathDict["NXRequiresCodeSigning"] as? Bool ?? false
            var requiresNXT2Signing: Bool = requiresCodeSigning
            let nxt2Entitlements: [String:Any]
            if requiresNXT2Signing {
                if let nxt2: [String:Any] = pathDict["NXT2Entitlements"] as? [String:Any] {
                    nxt2Entitlements = nxt2
                } else {
                    nxt2Entitlements = [:]
                    requiresNXT2Signing = false
                }
            } else {
                nxt2Entitlements = [:]
            }
            
            if let path: [String] = pathDict["NXPath"] as? [String] {
                for additionalPath in path {
                    actualPathObjects.append(ROMPath(path: additionalPath, permission: permission, codesigning: ROMPath.ROMPathCodeSigningInfo(needed: requiresCodeSigning, neededNXT2: requiresNXT2Signing, nxt2: nxt2Entitlements)))
                }
            } else if let path: String = pathDict["NXPath"] as? String {
                actualPathObjects.append(ROMPath(path: path, permission: permission, codesigning: ROMPath.ROMPathCodeSigningInfo(needed: requiresCodeSigning, neededNXT2: requiresNXT2Signing, nxt2: nxt2Entitlements)))
            } else {
                throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 1, userInfo: [NSLocalizedDescriptionKey:"malformed manifest paths"])
            }
        }
        self.paths = actualPathObjects
        
        self.installer = manifestContent["NXRomInstaller"] as? String
        self.uninstaller = manifestContent["NXRomUninstaller"] as? String
        self.executable = executable
        
        // bootlogo
        let slotRoot = manifestPlistURL.deletingLastPathComponent()
        if let bootLogoConfig = manifestContent["NXRomBootLogo"] as? [String:String],
           let lightPath = bootLogoConfig["Light"],
           let darkPath = bootLogoConfig["Dark"],
           let lightURL = try? slotFile(lightPath, in: slotRoot),
           let darkURL = try? slotFile(darkPath, in: slotRoot),
           let light = UIImage(contentsOfFile: lightURL.path) {
            let dark = UIImage(contentsOfFile: darkURL.path) ?? light
            self.bootlogo = adaptiveImage(light: light, dark: dark)
        } else {
            self.bootlogo = nil
        }
    }
}

enum BootFlag: String, CaseIterable {
    case kextLoading = "com.fs.flekdeck.boot.kextLoading"
    case logObfucation = "com.fs.flekdeck.boot.log.obfuscated"
    case sandboxFilesystem = "com.fs.flekdeck.boot.sandbox.filesystems"

    var guestRuntimeKey: String {
        switch self {
        case .kextLoading: return "nyxian.boot.kextLoading"
        case .logObfucation: return "nyxian.boot.log.obfuscated"
        case .sandboxFilesystem: return "nyxian.boot.sandbox.filesystems"
        }
    }
    
    var title: String {
        switch self {
            case .kextLoading: return "Load kexts at boot"
            case .logObfucation: return "Obfuscate Log"
            case .sandboxFilesystem: return "Filesystem Sandbox"
        }
    }
    
    var defaultValue: Bool {
        switch self {
            case .kextLoading: return true
            case .logObfucation: return true
            case .sandboxFilesystem: return true
        }
    }
}

enum BootConfig {
    fileprivate static let entitlementModeKey = "com.fs.flekdeck.boot.entitlements.mode"
    private static let guestEntitlementModeKey = "nyxian.boot.entitlements.mode"
    
    static func registerDefaults() {
        var defaults: [String: Any] = [:]
        for flag in BootFlag.allCases {
            defaults[flag.rawValue] = flag.defaultValue
            defaults[flag.guestRuntimeKey] = flag.defaultValue
        }
        defaults[entitlementModeKey] = EnforcementMode.enforcing.rawValue
        defaults[guestEntitlementModeKey] = EnforcementMode.enforcing.rawValue
        
        UserDefaults.standard.register(defaults: defaults)
        for flag in BootFlag.allCases {
            UserDefaults.standard.set(UserDefaults.standard.bool(forKey: flag.rawValue),
                                      forKey: flag.guestRuntimeKey)
        }
        UserDefaults.standard.set(entitlementMode.rawValue, forKey: guestEntitlementModeKey)
    }
    
    static var entitlementMode: EnforcementMode {
        get {
            guard let raw = UserDefaults.standard.string(forKey: entitlementModeKey),
                  let mode = EnforcementMode(rawValue: raw) else {
                return .enforcing
            }
            return mode
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: entitlementModeKey)
            UserDefaults.standard.set(newValue.rawValue, forKey: guestEntitlementModeKey)
        }
    }
    
    static func isEnabled(_ flag: BootFlag) -> Bool {
        UserDefaults.standard.bool(forKey: flag.rawValue)
    }
    
    static func toggle(_ flag: BootFlag) {
        let enabled = !isEnabled(flag)
        UserDefaults.standard.set(enabled, forKey: flag.rawValue)
        UserDefaults.standard.set(enabled, forKey: flag.guestRuntimeKey)
    }
}

enum EnforcementMode: String, CaseIterable {
    case enforcing
    case permissive
    case disabled
    
    var badge: String {
        switch self {
            case .enforcing: return "E"
            case .permissive: return "P"
            case .disabled: return "-"
        }
    }
    
    var next: EnforcementMode {
        let all = EnforcementMode.allCases
        let i = all.firstIndex(of: self) ?? 0
        return all[(i + 1) % all.count]
    }
}

private typealias NXSlotMainFn = @convention(c) () -> UnsafeMutableRawPointer?
private typealias NXSlotDidAppearFn = @convention(c) () -> Void
private typealias NXSlotCreateWindowFn = @convention(c) (UnsafeMutableRawPointer) -> UnsafeMutableRawPointer?
private typealias NXRomGenericFn = @convention(c) (UnsafePointer<CChar>) -> Int32

private func romError(_ message: String) -> NSError {
    NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 3, userInfo: [NSLocalizedDescriptionKey: message])
}

private func slotFile(_ relative: String,
                      in slot: URL) throws -> URL {
    let components = relative.split(separator: "/", omittingEmptySubsequences: false)
    guard !relative.isEmpty,
          !relative.hasPrefix("/"),
          !relative.utf8.contains(0),
          !components.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) else {
        throw romError("invalid ROM-relative path: \(relative)")
    }

    let root = slot.resolvingSymlinksInPath().standardizedFileURL.path
    let url = slot.appendingPathComponent(relative).resolvingSymlinksInPath().standardizedFileURL
    guard url.path.hasPrefix(root + "/") else {
        throw romError("path escapes ROM slot: \(relative)")
    }
    return url
}

private let nxRomLogFD: Int32 = 27
private let romQueue = DispatchQueue(label: "org.emexlabs.nyxian.bootloader.rom", qos: .userInitiated)
private var romOperationInProgress = false

private struct RomLog {
    let controller: NXRecoveryViewController
    
    func info(_ message: String) {
        DispatchQueue.main.async { controller.recoveryLog(message) }
    }
    
    func error(_ message: String) {
        DispatchQueue.main.async { controller.recoveryLogError(message) }
    }
    
    func rom(_ line: String) {
        if line.hasPrefix("ERROR:") {
            error(line)
        } else {
            info(line)
        }
    }
}

private func romIsBusy(_ c: NXRecoveryViewController) -> Bool {
    if romOperationInProgress {
        c.recoveryLogError("ERROR: a ROM operation is still running")
    }
    return romOperationInProgress
}

private func runRomOperation(_ c: NXRecoveryViewController, _ work: @escaping (RomLog) -> Void) {
    dispatchPrecondition(condition: .onQueue(.main))
    guard !romIsBusy(c) else { return }
    romOperationInProgress = true
    let log = RomLog(controller: c)
    romQueue.async {
        work(log)
        DispatchQueue.main.async {
            romOperationInProgress = false
        }
    }
}

private func runRomGeneric(_ relative: String, symbol: String, slot: URL, onLine: @escaping (String) -> Void) throws {
    dispatchPrecondition(condition: .notOnQueue(.main))
    
    let url = try slotFile(relative, in: slot)
    
    guard let handle = dlopen(url.path, RTLD_NOW | RTLD_LOCAL) else {
        throw romError("couldnt load \(relative): \(lastDlError())")
    }
    defer { dlclose(handle) }
    
    guard let sym = dlsym(handle, symbol) else {
        throw romError("\(relative) has no \(symbol) entry point")
    }
    
    var fds: [Int32] = [0, 0]
    guard pipe(&fds) == 0 else {
        throw romError("pipe failed: \(String(cString: strerror(errno)))")
    }
    
    let readFD = fds[0]
    let writeFD = fds[1]
    
    let oldFD = dup(nxRomLogFD)
    guard dup2(writeFD, nxRomLogFD) >= 0 else {
        close(readFD)
        close(writeFD)
        if oldFD >= 0 { close(oldFD) }
        throw romError("dup2 failed: \(String(cString: strerror(errno)))")
    }
    close(writeFD)
    
    // don't touch this, it works
    let drained = DispatchGroup()
    drained.enter()
    DispatchQueue.global(qos: .userInitiated).async {
        var buf = [UInt8](repeating: 0, count: 4096)
        var pending: [UInt8] = []
        while true {
            let n = read(readFD, &buf, buf.count)
            if n > 0 {
                pending.append(contentsOf: buf[0..<n])
                var start = pending.startIndex
                while let nl = pending[start...].firstIndex(of: 0x0A) {
                    emitRomLine(pending[start..<nl], onLine)
                    start = nl + 1
                }
                pending.removeFirst(start)
                continue
            }
            if n < 0 && errno == EINTR {
                continue
            }
            break
        }
        emitRomLine(pending[...], onLine)
        close(readFD)
        drained.leave()
    }
    let generic = unsafeBitCast(sym, to: NXRomGenericFn.self)
    let rc = slot.path.withCString {
        generic($0)
    }
    close(nxRomLogFD)
    if oldFD >= 0 {
        dup2(oldFD, nxRomLogFD)
        close(oldFD)
    }
    drained.wait()
    guard rc == 0 else {
        throw romError("\(symbol) returned \(rc)")
    }
}

private func emitRomLine(_ bytes: ArraySlice<UInt8>, _ onLine: (String) -> Void) {
    var bytes = bytes
    if bytes.last == 0x0D {
        bytes = bytes.dropLast()
    }
    guard !bytes.isEmpty else { return }
    onLine(String(decoding: bytes, as: UTF8.self))
}

private enum SlotLoadResult: @unchecked Sendable {
    case loaded(name: String, main: NXSlotMainFn, didAppear: NXSlotDidAppearFn?, createWindow: NXSlotCreateWindowFn?)
    case failed(String)
}

private typealias RestartSelfFn = @convention(c) () -> Void

private func restartSelf() {
    let RTLD_DEFAULT = UnsafeMutableRawPointer(bitPattern: -2)
    guard let sym = dlsym(RTLD_DEFAULT, "PERestartSelf") else {
        exit(0)
    }
    unsafeBitCast(sym, to: RestartSelfFn.self)()
}

private func refreshVnode(atPath path: String) -> Bool {
    let fd = open(path, O_RDWR)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    guard unlink(path) == 0 else { return false }
    if fclonefileat(fd, AT_FDCWD, path, 0) == 0 {
        return true
    }
    let copyfd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0o777)
    guard copyfd >= 0 else { return false }
    defer { close(copyfd) }
    lseek(fd, 0, SEEK_SET)
    return fcopyfile(fd, copyfd, nil, copyfile_flags_t(COPYFILE_DATA)) == 0
}

private func flashedSlotURL() -> URL {
    FlekDeckBootPaths.slot
}

/// The imported ROM image owns the Nyxian PE/NXT2 runtime symbols. Check that
/// image after loading it; these symbols are not expected in FlekDeck's host.
private func missingNXT2RuntimeCapabilities(for manifest: ROMManifest,
                                            imageHandle: UnsafeMutableRawPointer) -> [String] {
    guard manifest.paths.contains(where: { $0.codesigning.neededNXT2 }) else {
        return []
    }

    var missing: [String] = []
    if dlsym(imageHandle, "trust_nxt2_sign") == nil {
        missing.append("NXT2 trust signer (trust_nxt2_sign)")
    }
    if dlsym(imageHandle, "ksurface_kinit") == nil {
        missing.append("kernel-surface initializer (ksurface_kinit)")
    }

    let runtimeClasses = [
        ("PEUserspaceManager", "userspace bootstrap manager"),
        ("PEProcessManager", "guest process manager"),
        ("PEBootstrapRegistry", "bootstrap registry"),
        ("PELaunchServiceManager", "launch service manager"),
        ("NXBootstrap", "ROM bootstrap coordinator"),
    ]
    for (className, capability) in runtimeClasses where NSClassFromString(className) == nil {
        missing.append(capability)
    }
    return missing
}

private func lastDlError() -> String {
    if let err = dlerror() { return String(cString: err) }
    return "unknown dyld error"
}

private func loadSlot(loadSuperslotForcefully: Bool) -> SlotLoadResult {
    let fm = FileManager.default
    let slot = flashedSlotURL()
    let manifestURL = slot.appendingPathComponent("manifest.plist")
    
    let image: URL
    let name: String
    var manifestForRuntimeCheck: ROMManifest?
    
    if fm.fileExists(atPath: manifestURL.path),
       !loadSuperslotForcefully {
        do {
            let manifest = try ROMManifest(manifestPlistURL: manifestURL)
            manifestForRuntimeCheck = manifest
            image = try slotFile(manifest.executable, in: slot)
            name = manifest.name
        } catch {
            return .failed("flashed ROM is invalid: \(error.localizedDescription)")
        }
        guard fm.fileExists(atPath: image.path) else {
            return .failed("\(name): executable missing")
        }
    } else if let bundled = Bundle.main.privateFrameworksURL?.appendingPathComponent("SuperSlot.dylib"),
              fm.fileExists(atPath: bundled.path) {
        image = bundled
        name = "SuperSlot.dylib"
    } else {
        return .failed("No slot found (no flashed ROM and no bundled SuperSlot.dylib)")
    }

    guard let handle = dlopen(image.path, RTLD_NOW | RTLD_NODELETE | RTLD_GLOBAL) else {
        return .failed("Couldnt load \(name): \(lastDlError())")
    }

    if let manifest = manifestForRuntimeCheck {
        let missing = missingNXT2RuntimeCapabilities(for: manifest, imageHandle: handle)
        if !missing.isEmpty {
            return .failed("\(name) does not expose the runtime required by its NXT2 manifest: \(missing.joined(separator: ", ")). The ROM remains installed and recovery is still available.")
        }
    }
    
    guard let mainSym = dlsym(handle, "NXSlotMain") else {
        return .failed("\(name) has no NXSlotMain entry point")
    }
    
    let main = unsafeBitCast(mainSym, to: NXSlotMainFn.self)
    let didAppear = dlsym(handle, "NXSlotDidAppear").map { unsafeBitCast($0, to: NXSlotDidAppearFn.self) }
    let createWindow = dlsym(handle, "NXSlotCreateWindow").map { unsafeBitCast($0, to: NXSlotCreateWindowFn.self) }
    return .loaded(name: name, main: main, didAppear: didAppear, createWindow: createWindow)
}

private func bootConfigItems(returningTo parent: @escaping (NXRecoveryViewController) -> Void) -> [NXRecoveryItem] {
    func label(_ flag: BootFlag) -> String {
        "[\(BootConfig.isEnabled(flag) ? "X" : " ")] \(flag.title)"
    }
    
    func reload(_ c: NXRecoveryViewController) {
        let keep = c.recoveryIndex
        c.recoveryItems = bootConfigItems(returningTo: parent)
        c.recoveryIndex = keep
    }
    
    var items: [NXRecoveryItem] = [
        NXRecoveryItem(title: "../") { c in
            if let c = c {
                parent(c)
            }
        }
    ]
    
    for flag in BootFlag.allCases {
        items.append(NXRecoveryItem(title: label(flag)) { c in
            guard let c = c else { return }
            
            BootConfig.toggle(flag)
            reload(c)
            
            let state = BootConfig.isEnabled(flag) ? "enabled" : "disabled"
            c.recoveryLog("\(flag.title): \(state)")
        })
    }
    
    let mode = BootConfig.entitlementMode
    items.append(NXRecoveryItem(title: "[\(mode.badge)] Entitlements: \(mode.rawValue)") { c in
        guard let c = c else { return }
        
        BootConfig.entitlementMode = BootConfig.entitlementMode.next
        reload(c)
        
        switch BootConfig.entitlementMode {
            case .enforcing: c.recoveryLog("entitlements: enforcing")
            case .permissive: c.recoveryLogError("entitlements: permissive, denials logged, not blocked")
            case .disabled: c.recoveryLogError("entitlements: DISABLED, no checks will run")
        }
    })
    
    return items
}

func recoveryShowBootConfig(recoveryController c: NXRecoveryViewController) {
    c.enterRecovery(
        withHeader: "Boot Configuration",
        instructions: nil,
        footer: nil,
        items: bootConfigItems(returningTo: { parent in
            recoveryShowMenu(recoveryController: parent)
        }),
        onSelect: nil,
        onMove: nil
    )
}

private struct WipeFailure {
    let path: String
    let reason: String
}

private struct WipeStats {
    var removedFiles = 0
    var removedDirectories = 0
    var bytes: Int64 = 0
    var failures: [WipeFailure] = []
}

private let maxFailuresShown = 3

private let wipeResourceKeys: [URLResourceKey] = [
    .isDirectoryKey,
    .isSymbolicLinkKey,
    .totalFileAllocatedSizeKey,
]

private func errnoDescription(_ error: Error) -> String {
    let ns = error as NSError
    if let u = ns.userInfo[NSUnderlyingErrorKey] as? NSError, u.domain == NSPOSIXErrorDomain {
        return String(cString: strerror(Int32(u.code)))
    }
    return ns.localizedDescription
}

private func formatBytes(_ bytes: Int64) -> String {
    ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
}

private func relativePath(_ url: URL, home: String) -> String {
    let path = url.standardizedFileURL.path
    return path.hasPrefix(home) ? String(path.dropFirst(home.count)) : path
}

private func recordFailure(_ url: URL, _ error: Error, home: String, stats: inout WipeStats) {
    stats.failures.append(WipeFailure(path: relativePath(url, home: home), reason: errnoDescription(error)))
}

private func removeTree(_ url: URL,
                        keeping keep: Set<String>,
                        isRoot: Bool,
                        home: String,
                        stats: inout WipeStats) -> Bool {
    let fm = FileManager.default
    if !isRoot && keep.contains(url.standardizedFileURL.path) {
        return true
    }
    let values = try? url.resourceValues(forKeys: Set(wipeResourceKeys))
    let isSymlink = values?.isSymbolicLink ?? false
    let isRealDirectory = (values?.isDirectory ?? false) && !isSymlink
    
    var ok = true
    if isRealDirectory {
        let children: [URL]
        do {
            children = try fm.contentsOfDirectory(at: url, includingPropertiesForKeys: wipeResourceKeys, options: [])
        } catch {
            recordFailure(url, error, home: home, stats: &stats)
            return false
        }
        
        for child in children {
            let childOK = removeTree(child, keeping: keep, isRoot: false, home: home, stats: &stats)
            ok = ok && childOK
        }
    }
    
    if isRoot || keep.contains(url.standardizedFileURL.path) || !ok {
        return ok
    }
    
    let size = Int64(values?.totalFileAllocatedSize ?? 0)
    do {
        try fm.removeItem(at: url)
    } catch {
        recordFailure(url, error, home: home, stats: &stats)
        return false
    }
    
    if isRealDirectory {
        stats.removedDirectories += 1
    } else {
        stats.removedFiles += 1
        stats.bytes += size
    }
    
    return true
}

func recoveryWipeData(_ c: NXRecoveryViewController) {
    let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).standardizedFileURL
    let homePath = home.path
    
    let targets = ["Documents", "Library", "tmp"].map {
        home.appendingPathComponent($0, isDirectory: true)
    }
    
    let keep: Set<String> = [
        home.appendingPathComponent("Library/Caches").standardizedFileURL.path,
        home.appendingPathComponent("Library/Preferences").standardizedFileURL.path,
    ]

    c.recoveryLogMax = max(c.recoveryLogMax, 16)
    
    let started = CFAbsoluteTimeGetCurrent()
    c.recoveryLog("\n-- Wiping data...")
    
    var prefsOK = true
    if let id = Bundle.main.bundleIdentifier {
        let savedData = UserDefaults.standard.object(forKey: "LCCertificateData")
        let savedPassword = UserDefaults.standard.object(forKey: "LCCertificatePassword")
        
        let before = UserDefaults.standard.persistentDomain(forName: id)?.count ?? 0
        c.recoveryLog("Clearing preferences (\(before) keys)...")
        
        UserDefaults.standard.removePersistentDomain(forName: id)
        
        if let savedData = savedData {
            UserDefaults.standard.set(savedData, forKey: "LCCertificateData")
        }
        if let savedPassword = savedPassword {
            UserDefaults.standard.set(savedPassword, forKey: "LCCertificatePassword")
        }
        
        let after = UserDefaults.standard.persistentDomain(forName: id)?.count ?? 0
        if after != 2 {
            c.recoveryLogError("  failed: \(after) keys remain")
            prefsOK = false
        }
    } else {
        c.recoveryLogError("  failed: no bundle identifier")
        prefsOK = false
    }
    
    DispatchQueue.global(qos: .userInitiated).async {
        var success = prefsOK
        var totalBytes: Int64 = 0
        
        for dir in targets {
            let name = dir.lastPathComponent
            DispatchQueue.main.async { c.recoveryLog("Formatting /\(name)...") }
            
            var stats = WipeStats()
            let ok = removeTree(dir, keeping: keep, isRoot: true, home: homePath, stats: &stats)
            success = success && ok
            totalBytes += stats.bytes
            
            let summary = "  \(stats.removedFiles) files, \(stats.removedDirectories) dirs, \(formatBytes(stats.bytes))"
            let shown = Array(stats.failures.prefix(maxFailuresShown))
            let hidden = stats.failures.count - shown.count
            
            DispatchQueue.main.async {
                c.recoveryLog(summary)
                for f in shown {
                    c.recoveryLogError("  failed: \(f.path): \(f.reason)")
                }
                if hidden > 0 {
                    c.recoveryLogError("  ... and \(hidden) more (see system log)")
                }
            }
        }
        
        let elapsed = String(format: "%.1f", CFAbsoluteTimeGetCurrent() - started)
        let tail = "(\(formatBytes(totalBytes)) in \(elapsed)s)"
        
        DispatchQueue.main.async {
            if success {
                c.recoveryLog("Data wipe complete. \(tail)")
            } else {
                c.recoveryLogError("Data wipe failed. \(tail)")
            }
        }
    }
}

func recoveryWipeCache(_ c: NXRecoveryViewController) {
    let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).standardizedFileURL
    let homePath = home.path
    
    let targets = ["Library/Caches", "tmp"].map {
        home.appendingPathComponent($0, isDirectory: true)
    }
    
    let keep: Set<String> = []
    
    c.recoveryLogMax = max(c.recoveryLogMax, 16)
    
    let started = CFAbsoluteTimeGetCurrent()
    c.recoveryLog("\n-- Wiping cache...")
    
    DispatchQueue.global(qos: .userInitiated).async {
        var success = true
        var totalBytes: Int64 = 0
        
        for dir in targets {
            let name = dir.lastPathComponent
            DispatchQueue.main.async { c.recoveryLog("Formatting /\(name)...") }
            
            var stats = WipeStats()
            let ok = removeTree(dir, keeping: keep, isRoot: true, home: homePath, stats: &stats)
            success = success && ok
            totalBytes += stats.bytes
            
            let summary = "  \(stats.removedFiles) files, \(stats.removedDirectories) dirs, \(formatBytes(stats.bytes))"
            let shown = Array(stats.failures.prefix(maxFailuresShown))
            let hidden = stats.failures.count - shown.count
            
            DispatchQueue.main.async {
                c.recoveryLog(summary)
                for f in shown {
                    c.recoveryLogError("  failed: \(f.path): \(f.reason)")
                }
                if hidden > 0 {
                    c.recoveryLogError("  ... and \(hidden) more (see system log)")
                }
            }
        }
        
        let elapsed = String(format: "%.1f", CFAbsoluteTimeGetCurrent() - started)
        let tail = "(\(formatBytes(totalBytes)) in \(elapsed)s)"
        
        DispatchQueue.main.async {
            if success {
                c.recoveryLog("Cache wipe complete. \(tail)")
            } else {
                c.recoveryLogError("Cache wipe failed. \(tail)")
            }
        }
    }
}

func recoveryConfirmWipe(recoveryController c: NXRecoveryViewController) {
    c.enterRecovery(
        withHeader: "Wipe all user data?\nTHIS CAN NOT BE UNDONE!",
        instructions: nil,
        footer: nil,
        items: [
            NXRecoveryItem(title: "Cancel") { c in
                if let c = c { recoveryShowMenu(recoveryController: c) }
            },
            NXRecoveryItem(title: "Factory data reset") { c in
                guard let c = c else { return }
                recoveryShowMenu(recoveryController: c)
                recoveryWipeData(c)
            },
        ],
        onSelect: nil,
        onMove: nil
    )
}

@discardableResult private func runUninstaller(_ log: RomLog) -> Bool {
    let slot = flashedSlotURL()
    let manifestURL = slot.appendingPathComponent("manifest.plist")
    guard FileManager.default.fileExists(atPath: manifestURL.path) else { return true }
    
    do {
        let manifest = try ROMManifest(manifestPlistURL: manifestURL)
        guard let uninstaller = manifest.uninstaller else { return true }
        log.info("running uninstaller of \(manifest.name)")
        try runRomGeneric(uninstaller, symbol: "NXRomUninstall", slot: slot, onLine: log.rom)
        log.info("uninstaller finished")
        return true
    } catch {
        log.error("uninstaller failed: \(error.localizedDescription)")
        return false
    }
}

private func removeFlashedSlot(_ log: RomLog) {
    do {
        try FileManager.default.removeItem(at: flashedSlotURL())
        log.info("flashed ROM removed, next boot uses SuperSlot.dylib")
    } catch {
        log.error("ERROR: \(errnoDescription(error))")
    }
}

func recoveryShowUnflash(recoveryController c: NXRecoveryViewController) {
    guard !romIsBusy(c) else { return }
    
    let slot = flashedSlotURL()
    guard FileManager.default.fileExists(atPath: slot.path) else {
        c.recoveryLogError("no ROM flashed")
        return
    }
    
    let manifest = try? ROMManifest(manifestPlistURL: slot.appendingPathComponent("manifest.plist"))
    
    let header: String
    if let manifest {
        header = "Unflash \(manifest.name) \(manifest.version)?\n\(manifest.identifier)"
    } else {
        header = "Unflash ROM?\nmanifest unreadable, only force removal possible"
    }
    
    var items: [NXRecoveryItem] = [
        NXRecoveryItem(title: "../") { c in
            if let c = c { recoveryShowMenu(recoveryController: c) }
        }
    ]
    
    if let manifest {
        let title = manifest.uninstaller != nil ? "Uninstall ROM" : "Remove ROM (no uninstaller)"
        items.append(NXRecoveryItem(title: title) { c in
            guard let c = c else { return }
            recoveryShowMenu(recoveryController: c)
            runRomOperation(c) { log in
                log.info("\n-- Unflashing \(manifest.name)...")
                
                guard runUninstaller(log) else {
                    log.error("ROM kept, use force removal to delete it anyway")
                    return
                }
                removeFlashedSlot(log)
            }
        })
    }
    
    items.append(NXRecoveryItem(title: "Force remove (skip uninstaller)") { c in
        guard let c = c else { return }
        recoveryShowMenu(recoveryController: c)
        runRomOperation(c) { log in
            log.info("\n-- Force removing ROM...")
            log.error("uninstaller skipped, leftovers outside the slot may remain")
            removeFlashedSlot(log)
        }
    })
    
    c.enterRecovery(
        withHeader: header,
        instructions: nil,
        footer: nil,
        items: items,
        onSelect: nil,
        onMove: nil
    )
}

private func flashROM(archive: URL, log: RomLog) throws -> ROMManifest {
    let fm = FileManager.default
    let finalSlot = flashedSlotURL()
    let slot = FlekDeckBootPaths.stagingSlot
    let backup = FlekDeckBootPaths.previousSlot
    
    log.info("\n-- Flashing rom...")
    log.info("selected rom: \(archive.lastPathComponent)")
    
    try FlekDeckBootPaths.recoverInterruptedInstall()
    try fm.createDirectory(at: finalSlot.deletingLastPathComponent(), withIntermediateDirectories: true)
    if fm.fileExists(atPath: slot.path) {
        try fm.removeItem(at: slot)
    }
    try fm.createDirectory(at: slot, withIntermediateDirectories: true, attributes: [:])
    
    var extractionError: NSError?
    guard FlekDeckExtractROMArchive(archive, slot, &extractionError) else {
        throw extractionError ?? romError("failed to extract ROM")
    }
    
    log.info("extracted rom")
    
    let manifest: ROMManifest = try ROMManifest(manifestPlistURL: slot.appendingPathComponent("manifest.plist"))

    if manifest.paths.contains(where: { $0.codesigning.neededNXT2 }),
       FlekDeckBootSharedRootURL() == nil {
        throw romError("This ROM requires an app group shared by FlekDeck and LiveProcess. Re-sign both with the same application group before importing it.")
    }
    let executable = try slotFile(manifest.executable, in: slot)
    guard fm.fileExists(atPath: executable.path) else {
        throw romError("\(manifest.name): executable \(manifest.executable) is missing")
    }
    
    log.info("setting up default file and directory permissions")
    guard let enumerator = fm.enumerator(at: slot, includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey]) else {
        throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 2, userInfo: [NSLocalizedDescriptionKey: "could not enumerate \(slot)"])
    }
    var dirs: [URL] = [slot]
    for case let url as URL in enumerator {
        let values = try url.resourceValues(forKeys: Set([.isDirectoryKey, .isSymbolicLinkKey]))
        if values.isSymbolicLink == true { continue }
        if values.isDirectory == true {
            dirs.append(url)
        } else {
            try fm.setAttributes([.posixPermissions: manifest.defaultFilePermission], ofItemAtPath: url.path)
        }
    }
    for dir in dirs.reversed() {
        try fm.setAttributes([.posixPermissions: manifest.defaultDirectoryPermission], ofItemAtPath: dir.path)
    }
    
    log.info("setting up explicit path permissions and configurations")
    var signFiles: [ROMPath] = []
    for path in manifest.paths {
        log.info("setting up \(path.path)")
        
        if path.codesigning.needed {
            signFiles.append(path)
        } else {
            let safePath = try slotFile(path.path, in: slot)
            try fm.setAttributes([.posixPermissions: path.permission], ofItemAtPath: safePath.path)
        }
    }
    
    if !signFiles.isEmpty {
        log.info("signing files")
        let signingURLs = try signFiles.map { try slotFile($0.path, in: slot) }
        var signingError: NSError?
        guard FlekDeckSignROMFilesWithZSign(signingURLs, &signingError) else {
            throw signingError ?? romError("FlekDeck could not sign the ROM binaries")
        }
        for file in signFiles {
            log.info("signed \(file.path)")
        }
        
        log.info("refreshing signed files")
        for file in signFiles {
            guard refreshVnode(atPath: try slotFile(file.path, in: slot).path) else {
                throw romError("failed to refresh \(file.path)")
            }
            log.info("refreshed \(file.path)")
        }
        
        log.info("adding NXT2 entitlements if needed")
        let nxt2Files = signFiles.filter { $0.codesigning.neededNXT2 }
        if !nxt2Files.isEmpty {
            let runtimeHandle = try openROMRuntimeImage(at: executable)
            let missing = missingNXT2RuntimeCapabilities(for: manifest, imageHandle: runtimeHandle)
            guard missing.isEmpty else {
                throw romError("\(manifest.name) does not expose its NXT2 runtime: \(missing.joined(separator: ", "))")
            }
            for file in nxt2Files {
                let kr = FlekDeckNXT2Sign(imageHandle: runtimeHandle,
                                          path: try slotFile(file.path, in: slot).path,
                                          entitlements: file.codesigning.nxt2 as CFDictionary)
                guard kr == KERN_SUCCESS else {
                    throw romError("failed to add NXT2 entitlements to \(file.path): \(String(cString: mach_error_string(kr)))")
                }
                guard refreshVnode(atPath: try slotFile(file.path, in: slot).path) else {
                    throw romError("failed to refresh NXT2-signed file \(file.path)")
                }
                log.info("added NXT2 entitlements to \(file.path)")
            }
        }
        
        log.info("refixing sign files permissions")
        for file in signFiles {
            try fm.setAttributes([.posixPermissions: file.permission], ofItemAtPath: try slotFile(file.path, in: slot).path)
        }
    }
    
    if let installer = manifest.installer {
        log.info("running installer")
        do {
            try runRomGeneric(installer, symbol: "NXRomInstall", slot: slot, onLine: log.rom)
        } catch {
            throw romError("installer failed: \(error.localizedDescription)")
        }
        log.info("installer finished")
    }
    
    let hadPreviousSlot = fm.fileExists(atPath: finalSlot.path)
    if hadPreviousSlot {
        try fm.moveItem(at: finalSlot, to: backup)
    }
    do {
        try fm.moveItem(at: slot, to: finalSlot)
        try? fm.removeItem(at: backup)
    } catch {
        if hadPreviousSlot {
            try? fm.moveItem(at: backup, to: finalSlot)
        }
        throw error
    }
    
    return manifest
}

private func recoveryFlashROM(_ c: NXRecoveryViewController, archive: URL) {
    guard !romIsBusy(c) else { return }
    c.enterConsole()
    
    runRomOperation(c) { log in
        do {
            let preservedArchive = try FlekDeckBootPaths.preserveImportedArchive(archive)
            log.info("saved unchanged ZIP copy: \(preservedArchive.lastPathComponent)")
            let manifest = try flashROM(archive: preservedArchive, log: log)
            log.info("flashed \(manifest.name) \(manifest.version)")
            DispatchQueue.main.async {
                c.recoveryLog("\nFlash complete. The original ZIP is preserved unchanged and the ROM slot is installed. FlekDeck will try the slot on the next launch; recovery remains available with one Volume Down press during startup.")
                c.finishConsole(selectAction: { _ in
                    restartSelf()
                })
            }
        } catch {
            log.error("ERROR: \(error.localizedDescription)")
            try? FileManager.default.removeItem(at: FlekDeckBootPaths.stagingSlot)
            DispatchQueue.main.async {
                c.recoveryLogError("\nFlash failed.\nPress both volume buttons to return to the menu.")
                c.finishConsole(selectAction: { c in
                    guard let c = c else { return }
                    c.exitConsole()
                    recoveryShowMenu(recoveryController: c)
                })
            }
        }
    }
}

// Cuz it is weak
let romImporter: ROMImporter = ROMImporter()

func recoveryShowMenu(recoveryController: NXRecoveryViewController) {
    recoveryController.enterRecovery(
        withHeader: "FlekDeck Recovery\n\(Bundle.main.object(forInfoDictionaryKey: "CFBundleName") ?? "FlekDeck") \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? "0.0.0") (\(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") ?? "UNKNOWN"))",
        instructions: nil,
        footer: nil,
        items: [
            NXRecoveryItem(title: "Reboot system now") { c in
                restartSelf()
            },
            NXRecoveryItem(title: "Boot Configuration") { c in
                if let c = c {
                    recoveryShowBootConfig(recoveryController: c)
                }
            },
            NXRecoveryItem(title: "Wipe data / factory reset") { c in
                if let c = c {
                    recoveryConfirmWipe(recoveryController: c)
                }
            },
            NXRecoveryItem(title: "Wipe cache") { c in
                if let c = c {
                    recoveryWipeCache(c)
                }
            },
            NXRecoveryItem(title: "Flash ROM") { c in
                guard let c = c, !romIsBusy(c) else { return }
                romImporter.present(from: c) { url in
                    if let url = url {
                        recoveryFlashROM(c, archive: url)
                    }
                }
            },
            NXRecoveryItem(title: "Unflash ROM") { c in
                if let c = c {
                    recoveryShowUnflash(recoveryController: c)
                }
            },
            NXRecoveryItem(title: "FlekDeck Files") { c in
                c?.enterFileBrowser(atPath: NSHomeDirectory(), root: NSHomeDirectory(), header: "FlekDeck Files", onBack: { recovery in
                    if let recovery = recovery {
                        recoveryShowMenu(recoveryController: recovery)
                    }
                }, onFile: { path,name,controller in
                })
            },
            NXRecoveryItem(title: "System Files") { c in
                c?.enterFileBrowser(atPath: "/", root: "/", header: "System Files", onBack: { recovery in
                    if let recovery = recovery {
                        recoveryShowMenu(recoveryController: recovery)
                    }
                }, onFile: { path,name,controller in
                })
            },
            NXRecoveryItem(title: "Power Off") { c in
                UIApplication.shared.perform(Selector("suspend"))
                exit(0)
            },
        ],
        onSelect: nil,
        onMove: nil
    )
}


private enum FlekDeckBootPaths {
    private static let legacyRoot = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("FlekDeck/Boot", isDirectory: true)
    static let root: URL = FlekDeckBootSharedRootURL() ?? legacyRoot
    static let slot: URL = root.appendingPathComponent("Slot/A", isDirectory: true)
    static let stagingSlot: URL = root.appendingPathComponent("Slot/.A.installing", isDirectory: true)
    static let previousSlot: URL = root.appendingPathComponent("Slot/.A.previous", isDirectory: true)
    static let imports: URL = root.appendingPathComponent("Imports", isDirectory: true)

    static func setSessionActive(_ active: Bool) throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let data = try PropertyListSerialization.data(fromPropertyList:
            ["active": active, "hostPID": Int(getpid())], format: .binary, options: 0)
        try data.write(to: root.appendingPathComponent("boot-session.plist"), options: .atomic)
    }

    static func recoverInterruptedInstall() throws {
        let manager = FileManager.default
        // LiveProcess runs in its own sandbox. Keep the installed ROM under
        // the app-group container shared by FlekDeck and that extension. Copy
        // the previous app-container store forward once, retaining the old
        // files as a recovery copy until the user removes them.
        if root.standardizedFileURL != legacyRoot.standardizedFileURL,
           !manager.fileExists(atPath: root.path),
           manager.fileExists(atPath: legacyRoot.path) {
            try manager.createDirectory(at: root.deletingLastPathComponent(), withIntermediateDirectories: true)
            try manager.copyItem(at: legacyRoot, to: root)
        }
        try manager.createDirectory(at: root, withIntermediateDirectories: true)

        let slotExists = manager.fileExists(atPath: slot.path)
        let previousExists = manager.fileExists(atPath: previousSlot.path)

        if !slotExists && previousExists {
            try manager.moveItem(at: previousSlot, to: slot)
        } else if slotExists && previousExists {
            try manager.removeItem(at: previousSlot)
        }

        if manager.fileExists(atPath: stagingSlot.path) {
            try manager.removeItem(at: stagingSlot)
        }
    }

    static func preserveImportedArchive(_ source: URL) throws -> URL {
        guard source.pathExtension.lowercased() == "zip" else {
            throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 10,
                          userInfo: [NSLocalizedDescriptionKey: "Choose a ZIP ROM archive."])
        }
        let manager = FileManager.default
        try manager.createDirectory(at: imports, withIntermediateDirectories: true)
        let originalName = source.lastPathComponent
        let destination = imports.appendingPathComponent(UUID().uuidString + "-" + originalName)

        let sourceDigest = try archiveDigest(source)
        try manager.copyItem(at: source, to: destination)
        do {
            let copiedDigest = try archiveDigest(destination)
            guard Data(sourceDigest) == Data(copiedDigest) else {
                throw NSError(domain: "com.fs.flekdeck.bootloader.rom", code: 11,
                              userInfo: [NSLocalizedDescriptionKey: "The imported ZIP copy did not match the selected file byte-for-byte."])
            }
        } catch {
            try? manager.removeItem(at: destination)
            throw error
        }
        return destination
    }

    private static func archiveDigest(_ url: URL) throws -> SHA256.Digest {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
            hasher.update(data: data)
        }
        return hasher.finalize()
    }
}

private typealias FlekDeckNXT2SignFunction =
    @convention(c) (UnsafePointer<CChar>, CFDictionary, Bool, UnsafePointer<CChar>?) -> Int32

private func openROMRuntimeImage(at executable: URL) throws -> UnsafeMutableRawPointer {
    guard let handle = dlopen(executable.path, RTLD_NOW | RTLD_NODELETE | RTLD_GLOBAL) else {
        throw romError("could not load ROM runtime image: \(lastDlError())")
    }
    guard dlsym(handle, "NXSlotMain") != nil else {
        throw romError("ROM runtime image does not export NXSlotMain")
    }
    return handle
}

private func FlekDeckNXT2Sign(imageHandle: UnsafeMutableRawPointer,
                              path: String,
                              entitlements: CFDictionary) -> Int32 {
    guard let symbol = dlsym(imageHandle, "trust_nxt2_sign") else {
        return KERN_FAILURE
    }
    let sign = unsafeBitCast(symbol, to: FlekDeckNXT2SignFunction.self)
    return path.withCString { pathPointer in
        sign(pathPointer, entitlements, true, nil)
    }
}

struct FlekDeckRecoveryView: UIViewControllerRepresentable {
    var initialError: String? = nil

    func makeUIViewController(context: Context) -> NXRecoveryViewController {
        let controller = NXRecoveryViewController()
        if let initialError {
            controller.recoveryLogError("ERROR: " + initialError)
        }
        BootConfig.registerDefaults()
        recoveryShowMenu(recoveryController: controller)
        return controller
    }

    func updateUIViewController(_ controller: NXRecoveryViewController, context: Context) {}
}

private final class FlekDeckSlotHostController: UIViewController {
    private let slotRootController: UIViewController
    private let slotDidAppear: NXSlotDidAppearFn?
    private let slotCreateWindow: NXSlotCreateWindowFn?
    private var slotWindow: UIWindow?
    private var didNotifySlotAppearance = false

    init(rootController: UIViewController,
         didAppear: NXSlotDidAppearFn?,
         createWindow: NXSlotCreateWindowFn?) {
        self.slotRootController = rootController
        self.slotDidAppear = didAppear
        self.slotCreateWindow = createWindow
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        guard slotCreateWindow == nil else { return }
        embedSlotRootController()
    }

    private func embedSlotRootController() {
        addChild(slotRootController)
        slotRootController.view.frame = view.bounds
        slotRootController.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(slotRootController.view)
        slotRootController.didMove(toParent: self)
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !didNotifySlotAppearance, slotWindow == nil else { return }

        if let slotCreateWindow,
           let scene = view.window?.windowScene,
           let rawWindow = slotCreateWindow(Unmanaged.passUnretained(scene).toOpaque()) {
            let window = Unmanaged<UIWindow>.fromOpaque(rawWindow).takeRetainedValue()
            let hostWindow = view.window
            window.rootViewController = slotRootController
            window.alpha = 0
            slotWindow = window
            window.makeKeyAndVisible()
            UIView.animate(withDuration: 0.3, animations: {
                window.alpha = 1
            }, completion: { _ in
                hostWindow?.isHidden = true
                self.notifySlotAppearance()
            })
            return
        }

        if slotRootController.parent == nil {
            embedSlotRootController()
        }
        notifySlotAppearance()
    }

    private func notifySlotAppearance() {
        guard !didNotifySlotAppearance else { return }
        didNotifySlotAppearance = true
        slotDidAppear?()
    }

    override var childForStatusBarStyle: UIViewController? {
        slotRootController
    }

    override var childForStatusBarHidden: UIViewController? {
        slotRootController
    }
}

private struct FlekDeckSlotView: UIViewControllerRepresentable {
    let name: String
    let main: NXSlotMainFn
    let didAppear: NXSlotDidAppearFn?
    let createWindow: NXSlotCreateWindowFn?

    func makeUIViewController(context: Context) -> UIViewController {
        guard let rawRoot = main() else {
            let recovery = NXRecoveryViewController()
            BootConfig.registerDefaults()
            recovery.recoveryLogError("ERROR: \(name) NXSlotMain returned no view controller.")
            recoveryShowMenu(recoveryController: recovery)
            return recovery
        }
        let root = Unmanaged<UIViewController>.fromOpaque(rawRoot).takeRetainedValue()
        return FlekDeckSlotHostController(rootController: root,
                                          didAppear: didAppear,
                                          createWindow: createWindow)
    }

    func updateUIViewController(_ controller: UIViewController, context: Context) {}
}

private enum FlekDeckBootDestination {
    case checking
    case app
    case recovery(String?)
    case slot(name: String,
              main: NXSlotMainFn,
              didAppear: NXSlotDidAppearFn?,
              createWindow: NXSlotCreateWindowFn?)
}

struct FlekDeckBootGateView<Content: View>: View {
    @State private var destination: FlekDeckBootDestination = .checking
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        Group {
            switch destination {
            case .checking:
                Color.black.ignoresSafeArea()
                    .task { await checkVolumeButtons() }
            case .app:
                content
            case .recovery(let error):
                FlekDeckRecoveryView(initialError: error)
            case .slot(let name, let main, let didAppear, let createWindow):
                FlekDeckSlotView(name: name, main: main, didAppear: didAppear, createWindow: createWindow)
            }
        }
    }

    @MainActor
    private func checkVolumeButtons() async {
        let mode = await Task.detached(priority: .userInitiated) {
            NXVolumeButtonMonitor.scan(for: 1.0)
        }.value
        NXVolumeButtonMonitor.disarm()
        do {
            try await Task.detached(priority: .utility) {
                try FlekDeckBootPaths.recoverInterruptedInstall()
                try FlekDeckBootPaths.setSessionActive(false)
            }.value
        } catch {
            destination = .recovery("Could not recover an interrupted ROM install: \(error.localizedDescription)")
            return
        }
        if mode == 2 {
            destination = .recovery(nil)
            return
        }

        BootConfig.registerDefaults()
        // FlekDeck's built-in slot is its own app shell.
        if mode == 1 {
            destination = .app
            return
        }
        let slotExists = FileManager.default.fileExists(atPath: flashedSlotURL().path)
        guard slotExists else {
            destination = .app
            return
        }

        let result = await Task.detached(priority: .userInitiated) {
            loadSlot(loadSuperslotForcefully: false)
        }.value
        switch result {
        case let .loaded(name, main, didAppear, createWindow):
            do {
                try FlekDeckBootPaths.setSessionActive(true)
            } catch {
                destination = .recovery("Could not activate the ROM boot session: \(error.localizedDescription)")
                return
            }
            destination = .slot(name: name, main: main, didAppear: didAppear, createWindow: createWindow)
        case let .failed(message):
            destination = .recovery(message)
        }
    }
}

