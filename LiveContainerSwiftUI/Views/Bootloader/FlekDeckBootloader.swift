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

/// Each update represents actual completed installation work, not elapsed time.
private let procursusInstallInFlightKey = "FlekDeckProcursusInstallInFlight"
private let procursusProgressKey = "FlekDeckProcursusProgressSnapshot"
private let procursusProgressName = Notification.Name("FlekDeckProcursusInstallProgress")

private func reportProcursusProgress(
    _ completedStages: Int, title: String, detail: String,
    current: Int = 0, total: Int = 0, status: String = "running"
) {
    let event: [String: Any] = [
        "pid": Int(ProcessInfo.processInfo.processIdentifier),
        "completedStages": min(6, max(0, completedStages)),
        "title": title,
        "detail": String(detail.prefix(240)),
        "current": current,
        "total": total,
        "status": status
    ]
    if current == 0 || current == total || current % 10 == 0 {
        FlekDeckBootTrace.mark(
            "procursus-progress stage=\(completedStages)/6 status=\(status) " +
            "\(title) \(current)/\(total) \(String(detail.prefix(100)))")
    }
    DispatchQueue.main.async {
        UserDefaults.standard.set(event, forKey: procursusProgressKey)
        NotificationCenter.default.post(
            name: procursusProgressName, object: nil, userInfo: event)
    }
}

private func reportProcursusFailure(_ error: Error) {
    let message = error.localizedDescription
    FlekDeckBootTrace.mark("procursus-progress-failed \(message)")
    DispatchQueue.main.async {
        var event = UserDefaults.standard.dictionary(
            forKey: procursusProgressKey) ?? [:]
        event["pid"] = Int(ProcessInfo.processInfo.processIdentifier)
        event["title"] = "Installation failed"
        event["detail"] = message
        event["status"] = "failed"
        event["current"] = 0
        event["total"] = 0
        UserDefaults.standard.set(event, forKey: procursusProgressKey)
        NotificationCenter.default.post(
            name: procursusProgressName, object: nil, userInfo: event)
    }
}

private struct RomLog {
    let controller: NXRecoveryViewController?

    func info(_ message: String) {
        guard let controller else { NSLog("FlekDeck ROM installer: %@", message); return }
        DispatchQueue.main.async { controller.recoveryLog(message) }
    }

    func error(_ message: String) {
        guard let controller else { NSLog("FlekDeck ROM installer error: %@", message); return }
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

// In-place activation keeps FlekDeck's Home, Settings and app lifecycle
// intact. Procursus is a guest runtime installed *inside* FlekDeck, not a
// separate jailbroken phone UI or a relaunch into Nyxian.
@MainActor
func FlekDeckActivateProcursusAfterInstall() {
    NotificationCenter.default.post(
        name: Notification.Name("FlekDeckActivateInstalledProcursus"),
        object: nil)
}

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
        FlekDeckBootPaths.clearCommittedROM()
        log.info("flashed ROM removed, next boot uses FlekDeck's built-in shell")
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

/// Restore symlinks only after copying signed IPA resources to writable
/// staging storage. The unsigned IPA itself must never include symlinks.
private func restoreEmbeddedProcursusROM(from source: URL, into slot: URL,
                                         onLink: ((Int, Int) -> Void)? = nil) throws {
    let fm = FileManager.default
    guard let expected = FlekDeckBootPaths.embeddedProcursusRoot,
          source.standardizedFileURL == expected.standardizedFileURL else {
        throw romError("Unrecognized bundled Procursus root")
    }
    let container = source.deletingLastPathComponent()
    guard let links = NSDictionary(contentsOf: container.appendingPathComponent("symlinks.plist")) as? [String: String],
          links.count == 101 else {
        throw romError("Procursus extracted ROM metadata is missing or incomplete")
    }
    func validRelative(_ name: String) -> Bool {
        !name.isEmpty && !name.hasPrefix("/") && !name.contains("\\")
            && name.split(separator: "/", omittingEmptySubsequences: false)
                .allSatisfy { !$0.isEmpty && $0 != "." && $0 != ".." }
    }
    // IPA re-signers can rewrite embedded Mach-O code signatures.
    // Stage the signed binaries and re-sign manifest-listed guest programs.
    try fm.removeItem(at: slot)
    try fm.copyItem(at: source, to: slot)
    for required in ["manifest.plist", "System/Rom/init", "usr/libexec/bootstrapd",
                     "System/Library/CoreServices/SpringBoard.app/SpringBoard",
                     "bootstrap.tar.zst"] {
        guard fm.fileExists(atPath: slot.appendingPathComponent(required).path) else {
            throw romError("Required Procursus ROM file missing: " + required)
        }
    }
    FlekDeckBootTrace.mark("procursus-staged-with-resigned-binaries")
    let root = slot.standardizedFileURL.path
    for (index, linkEntry) in links.sorted(by: { $0.key < $1.key }).enumerated() {
        let relative = linkEntry.key
        let target = linkEntry.value
        guard validRelative(relative), !target.isEmpty,
              !target.hasPrefix("/"), !target.contains("\\") else {
            throw romError("Unsafe embedded ROM symlink: \(relative)")
        }
        let link = slot.appendingPathComponent(relative).standardizedFileURL
        let targetURL = link.deletingLastPathComponent()
            .appendingPathComponent(target).standardizedFileURL
        guard link.path.hasPrefix(root + "/"),
              targetURL.path.hasPrefix(root + "/"),
              !fm.fileExists(atPath: link.path) else {
            throw romError("ROM symlink outside staging slot: \(relative)")
        }
        try fm.createSymbolicLink(atPath: link.path, withDestinationPath: target)
        onLink?(index + 1, links.count)
    }
    FlekDeckBootTrace.mark("procursus-extracted-rom-symlinks-restored")
}

private func flashROM(archive: URL, log: RomLog,
                      reportsProgress: Bool = false) throws -> ROMManifest {
    func stage(_ completed: Int, _ title: String, _ detail: String,
               current: Int = 0, total: Int = 0) {
        guard reportsProgress else { return }
        reportProcursusProgress(completed, title: title, detail: detail,
                                current: current, total: total)
    }
    let fm = FileManager.default
    let finalSlot = flashedSlotURL()
    let slot = FlekDeckBootPaths.stagingSlot
    let backup = FlekDeckBootPaths.previousSlot
    
    log.info("\n-- Flashing rom...")
    log.info("selected rom: \(archive.lastPathComponent)")
    stage(0, "Preparing ROM", "Recovering staging directory and preparing files")

    try FlekDeckBootPaths.recoverInterruptedInstall()
    try fm.createDirectory(at: finalSlot.deletingLastPathComponent(), withIntermediateDirectories: true)
    if fm.fileExists(atPath: slot.path) {
        try fm.removeItem(at: slot)
    }
    try fm.createDirectory(at: slot, withIntermediateDirectories: true, attributes: [:])
    
    if archive.hasDirectoryPath {
        stage(0, "Copying ROM files", "Copying bundled files into writable storage")
        try restoreEmbeddedProcursusROM(from: archive, into: slot) { done, total in
            stage(1, "Restoring filesystem links", "Restored \(done) of \(total) links",
                  current: done, total: total)
        }
    } else {
        var extractionError: NSError?
        guard FlekDeckExtractROMArchive(archive, slot, &extractionError) else {
            throw extractionError ?? romError("failed to extract ROM")
        }
    }
    
    log.info("extracted rom")
    stage(2, "Configuring permissions", "ROM filesystem staged; reading manifest")
    
    let manifest: ROMManifest = try ROMManifest(manifestPlistURL: slot.appendingPathComponent("manifest.plist"))

    // PEFilePermissions grants the extension access to host-owned ROM files.
    // App Groups are optional; ESign may legitimately sign without them.
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
    for (index, path) in manifest.paths.enumerated() {
        log.info("setting up \(path.path)")
        stage(2, "Configuring permissions", "\(path.path)",
              current: index + 1, total: manifest.paths.count)
        
        if path.codesigning.needed {
            signFiles.append(path)
        } else {
            let safePath = try slotFile(path.path, in: slot)
            try fm.setAttributes([.posixPermissions: path.permission], ofItemAtPath: safePath.path)
        }
    }
    
    // Native crash prevention: NXT2 must be supplied by the host runtime.
    // dlopen(System/Rom/init) during installation executes the guest's Mach-O
    // initializers in FlekDeck and terminated iOS 27 before dlopen returned.
    // Require a genuine, already-linked host trust function before mutating or
    // signing the staged ROM. A missing build capability is a recoverable setup
    // error, not a reason to crash the app or claim installation succeeded.
    let requiredNXT2 = signFiles.filter { $0.codesigning.neededNXT2 }
    FlekDeckBootTrace.mark("procursus-nxt2-host-preflight requested=\(requiredNXT2.count)")
    if !requiredNXT2.isEmpty && FlekDeckNXT2HostSigner() == nil {
        FlekDeckBootTrace.mark("procursus-nxt2-host-signer-unavailable")
        throw romError("Procursus NXT2 native signer is unavailable. Check Boot Logs for a library or device keychain failure. The ROM was not committed.")
    }
    FlekDeckBootTrace.mark("procursus-nxt2-host-preflight-passed")
    stage(3, "Signing executables",
          signFiles.isEmpty ? "No executable signing requested by ROM manifest" :
              "Signing \(signFiles.count) executables with the configured identity")
    if !signFiles.isEmpty {
        log.info("signing files")
        let signingURLs = try signFiles.map { try slotFile($0.path, in: slot) }
        var signingError: NSError?
        guard FlekDeckSignROMFilesWithZSign(signingURLs, &signingError) else {
            throw signingError ?? romError("FlekDeck could not sign the ROM binaries")
        }
        FlekDeckBootTrace.mark("procursus-zsign-complete count=\(signFiles.count)")
        // ZSigner already copy/renames each signed Mach-O to invalidate vnode
        // signature caches; it reports success only after all those refreshes.
        // Do NOT perform a second unlink + fclonefileat here. On a jailed iOS
        // process that extra operation can terminate the app after signing.
        // Verify all signed paths are still readable without mutating them.
        for (index, file) in signFiles.enumerated() {
            let signedURL = try slotFile(file.path, in: slot)
            guard fm.isReadableFile(atPath: signedURL.path),
                  let size = (try fm.attributesOfItem(atPath: signedURL.path))[.size] as? NSNumber,
                  size.int64Value > 0 else {
                throw romError("Signed ROM executable missing or empty: \(file.path)")
            }
            FlekDeckBootTrace.mark("procursus-signed-file-verified \(index + 1)/\(signFiles.count) \(file.path)")
        }
        FlekDeckBootTrace.mark("procursus-post-zsign-file-verification-complete")
        
        log.info("adding NXT2 entitlements if needed")
        let nxt2Files = requiredNXT2
        FlekDeckBootTrace.mark("procursus-nxt2-required count=\(nxt2Files.count)")
        if !nxt2Files.isEmpty {
            stage(3, "Applying NXT2 entitlements",
                  "Using the host NXT2 signer for \(nxt2Files.count) executables")
            guard let hostSign = FlekDeckNXT2HostSigner() else {
                throw romError("The native NXT2 signer became unavailable during installation.")
            }
            FlekDeckBootTrace.mark("procursus-nxt2-host-signer-ready")
            for (index, file) in nxt2Files.enumerated() {
                FlekDeckBootTrace.mark("procursus-nxt2-sign-enter \(index + 1)/\(nxt2Files.count) \(file.path)")
                let target = try slotFile(file.path, in: slot)
                let kr = FlekDeckNXT2Sign(hostSigner: hostSign.sign,
                                          path: target.path,
                                          entitlements: file.codesigning.nxt2 as CFDictionary)
                FlekDeckBootTrace.mark("procursus-nxt2-sign-result \(index + 1)/\(nxt2Files.count) kr=\(kr)")
                guard kr == KERN_SUCCESS else {
                    throw romError("failed to add NXT2 entitlements to \(file.path): \(String(cString: mach_error_string(kr)))")
                }
                FlekDeckBootTrace.mark("procursus-nxt2-verify-enter \(file.path)")
                guard target.path.withCString({ hostSign.verify($0) }) == 1 else {
                    throw romError("Nyxian NXT2 verification failed for \(file.path): signed blob, code hash, or EC signature is invalid")
                }
                FlekDeckBootTrace.mark("procursus-nxt2-verify-success \(file.path)")
                FlekDeckBootTrace.mark("procursus-nxt2-refresh-enter \(file.path)")
                guard refreshVnode(atPath: target.path) else {
                    throw romError("failed to refresh NXT2-signed file \(file.path)")
                }
                FlekDeckBootTrace.mark("procursus-nxt2-refresh-done \(file.path)")
                stage(3, "Applying NXT2 entitlements",
                      "Signed \(index + 1) of \(nxt2Files.count) guest processes",
                      current: index + 1, total: nxt2Files.count)
                log.info("added NXT2 entitlements to \(file.path)")
            }
        }
        FlekDeckBootTrace.mark("procursus-nxt2-complete")
        
        log.info("refixing sign files permissions")
        for file in signFiles {
            try fm.setAttributes([.posixPermissions: file.permission], ofItemAtPath: try slotFile(file.path, in: slot).path)
        }
    }
    
    FlekDeckBootTrace.mark("procursus-post-sign-permissions-complete")
    stage(4, "Running ROM installer",
          manifest.installer == nil ? "No additional ROM installer required" :
              "Executing the Procursus installer; completion time is unknown")
    if let installer = manifest.installer {
        log.info("running installer")
        do {
            try runRomGeneric(installer, symbol: "NXRomInstall", slot: slot) { line in
                log.rom(line)
                stage(4, "Running ROM installer", String(line.prefix(180)))
            }
        } catch {
            throw romError("installer failed: \(error.localizedDescription)")
        }
        log.info("installer finished")
    }
    
    FlekDeckBootTrace.mark("procursus-rom-installer-finished")
    stage(5, "Committing ROM", "Moving verified staging slot into place")
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

    // The recovery UI must never claim a ROM was flashed without proving its
    // committed manifest is still readable from the same path used at boot.
    let verified = try ROMManifest(manifestPlistURL: finalSlot.appendingPathComponent("manifest.plist"))
    guard verified.identifier == manifest.identifier else {
        throw romError("ROM commit validation failed: slot manifest identity changed")
    }
    try FlekDeckBootPaths.recordCommittedROM(verified)
    stage(6, "ROM installed", "\(verified.name) \(verified.version) committed")
    return verified
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
                c.recoveryLog("\nFlash complete.\nPress both volume buttons to reboot when ready.")
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

/// Install a user-selected Procursus ROM from FlekDeck's Settings, using
/// the SAME verified/signing NXT2 flash path as Nyxian Recovery. The ROM
/// stays persistent under Slot/A; selecting the ZIP is a one-time step.
/// No side-loaded binary is run before signature and manifest verification.
func FlekDeckInstallBundledProcursus(
    _ source: URL,
    completion: @escaping (Result<String, Error>) -> Void
) {
    dispatchPrecondition(condition: .onQueue(.main))
    guard !romOperationInProgress else {
        completion(.failure(romError("A ROM operation is already running")))
        return
    }
    guard source.standardizedFileURL ==
        FlekDeckBootPaths.embeddedProcursusRoot?.standardizedFileURL else {
        completion(.failure(romError("Procursus folder is not the embedded IPA asset")))
        return
    }
    // Validate NXT2 native capability BEFORE copying and relinking the full
    // Procursus filesystem. Logs from iOS 27 show 101 links and 31 manifest
    // entries were repeatedly staged only to fail at the known host preflight.
    // This intentionally does not claim NXT2 signing can be skipped.
    if let manifest = try? ROMManifest(
        manifestPlistURL: source.appendingPathComponent("manifest.plist")),
       manifest.paths.contains(where: { $0.codesigning.neededNXT2 }),
       FlekDeckNXT2HostSigner() == nil {
        let failure = romError(
            "Procursus NXT2 signer could not initialize. Check Boot Logs for the packaged native library or device keychain error; installation was not started.")
        FlekDeckBootTrace.mark("procursus-nxt2-host-preflight-before-staging-unavailable")
        UserDefaults.standard.set(failure.localizedDescription,
                                  forKey: "FlekDeckProcursusLastInstallError")
        reportProcursusFailure(failure)
        completion(.failure(failure))
        return
    }
    romOperationInProgress = true
    // A native SIGKILL/SIGABRT does not run Swift's catch block. Persist the
    // attempt before native signing so the next launch can stop a crash loop.
    UserDefaults.standard.set(true, forKey: procursusInstallInFlightKey)
    UserDefaults.standard.synchronize()
    FlekDeckBootTrace.mark("procursus-attempt-marker-armed")
    reportProcursusProgress(0, title: "Preparing Procursus",
                            detail: "Starting installation")
    FlekDeckBootTrace.mark("procursus-embedded-install-enter")
    romQueue.async {
        let outcome: Result<String, Error>
        do {
            let manifest = try flashROM(archive: source, log: RomLog(controller: nil),
                                        reportsProgress: true)
            FlekDeckBootTrace.mark("procursus-embedded-install-committed")
            outcome = .success("\(manifest.name) \(manifest.version) installed. Restart FlekDeck to initialize the virtual environment.")
        } catch {
            try? FileManager.default.removeItem(at: FlekDeckBootPaths.stagingSlot)
            FlekDeckBootTrace.mark("procursus-embedded-install-failed \(error.localizedDescription)")
            reportProcursusFailure(error)
            outcome = .failure(error)
        }
        DispatchQueue.main.async {
            romOperationInProgress = false
            UserDefaults.standard.removeObject(forKey: procursusInstallInFlightKey)
            UserDefaults.standard.synchronize()
            FlekDeckBootTrace.mark("procursus-attempt-marker-cleared")
            switch outcome {
            case .success:
                UserDefaults.standard.removeObject(forKey: "FlekDeckProcursusLastInstallError")
            case .failure(let error):
                UserDefaults.standard.set(
                    error.localizedDescription,
                    forKey: "FlekDeckProcursusLastInstallError")
                NotificationCenter.default.post(
                    name: Notification.Name("FlekDeckProcursusInstallFailed"),
                    object: nil)
            }
            completion(outcome)
        }
    }
}


/// True only after a valid Procursus manifest is committed to the persistent
/// boot slot. This does not imply NXSlotMain or SpringBoard has booted.
func FlekDeckHasInstalledProcursusROM() -> Bool {
    let manifestURL = flashedSlotURL().appendingPathComponent("manifest.plist")
    guard let manifest = try? ROMManifest(manifestPlistURL: manifestURL) else {
        return false
    }
    return manifest.identifier == "org.emexlabs.procursus.jailed"
}

/// Retry the same already-unpacked IPA resources after importing a P12.
/// Never ask the user to find or flash a ZIP.
func FlekDeckRetryBundledProcursus(
    completion: @escaping (Result<String, Error>) -> Void
) {
    guard let source = FlekDeckBootPaths.embeddedProcursusRoot else {
        completion(.failure(romError("This FlekDeck IPA is missing its unpacked Procursus ROM")))
        return
    }
    FlekDeckInstallBundledProcursus(source, completion: completion)
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


// Lightweight, crash-resilient boot breadcrumbs. These logs live in Documents,
// so Files can export them even when the ROM aborts before UIKit appears.
// No per-frame logging, polling, UserDefaults writes, or unlimited growth.
private enum FlekDeckBootTrace {
    private static let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("BootLogs", isDirectory: true)
    private static let current = directory.appendingPathComponent("current-boot.log")
    private static let previous = directory.appendingPathComponent("previous-boot.log")

    // The original Nyxian klog writes to Documents/kmsg.txt in the host
    // process. It truncates that file when the next ROM boot begins. Preserve
    // the last fatal session before it can be overwritten.
    private static let nyxianKmsg = directory.deletingLastPathComponent()
        .appendingPathComponent("kmsg.txt")
    private static let currentKmsg = directory.appendingPathComponent("current-nyxian-kmsg.log")
    private static let previousKmsg = directory.appendingPathComponent("previous-nyxian-kmsg.log")

    private static func copyNyxianKmsg(to destination: URL) {
        guard FileManager.default.fileExists(atPath: nyxianKmsg.path) else { return }
        do {
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.copyItem(at: nyxianKmsg, to: destination)
        } catch {
            // Diagnostics must never stop the ROM boot.
        }
    }

    // LiveProcess runs in another sandbox. Its optional shared-container
    // breadcrumbs are imported into Documents/BootLogs/LiveProcess at launch.
    // Preserve a bounded number and consume the shared copies only after
    // successful import. Free/ESign profiles without App Groups simply skip it.
    private static func importExtensionDiagnostics() {
        guard let shared = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.SideStore.SideStore") else { return }
        let source = shared.appendingPathComponent("FlekDeck/Boot/Diagnostics", isDirectory: true)
        let destination = directory.appendingPathComponent("LiveProcess", isDirectory: true)
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: source, includingPropertiesForKeys: nil) else { return }
        do {
            try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
            let logs = entries.filter { $0.lastPathComponent.hasPrefix("pe-") && $0.pathExtension == "log" }
            for file in logs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }).suffix(16) {
                let target = destination.appendingPathComponent(file.lastPathComponent)
                if FileManager.default.fileExists(atPath: target.path) {
                    try FileManager.default.removeItem(at: target)
                }
                try FileManager.default.copyItem(at: file, to: target)
                try FileManager.default.removeItem(at: file)
            }
            // No unlimited log accumulation in the user-visible export directory.
            let retained = try FileManager.default.contentsOfDirectory(
                at: destination, includingPropertiesForKeys: nil)
                .filter { $0.pathExtension == "log" }
                .sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
            for old in retained.dropLast(16) {
                try? FileManager.default.removeItem(at: old)
            }
        } catch {
            // A missing App Group or an expired signer must not affect boot.
        }
    }

    static func captureNyxianKmsg() {
        copyNyxianKmsg(to: currentKmsg)
    }

    static func begin() {
        let manager = FileManager.default
        do {
            try manager.createDirectory(at: directory, withIntermediateDirectories: true)
            if manager.fileExists(atPath: previous.path) {
                try manager.removeItem(at: previous)
            }
            if manager.fileExists(atPath: current.path) {
                try manager.moveItem(at: current, to: previous)
            }
            // Always snapshot kmsg from the previous boot before Nyxian opens
            // it with O_TRUNC during the next ROM's first klog message.
            copyNyxianKmsg(to: previousKmsg)
            if manager.fileExists(atPath: currentKmsg.path) {
                try manager.removeItem(at: currentKmsg)
            }
        } catch {
            // Diagnostics must never interfere with boot.
        }
        importExtensionDiagnostics()
        mark("boot-controller-loaded")
    }

    static func mark(_ event: String) {
        let manager = FileManager.default
        try? manager.createDirectory(at: directory, withIntermediateDirectories: true)
        let fd = current.path.withCString {
            Darwin.open($0, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, mode_t(0o600))
        }
        guard fd >= 0 else { return }
        defer { _ = Darwin.close(fd) }
        // Each session is bounded to a few dozen short checkpoints. Preserve the
        // current trace until the next launch, rotating only one previous trace.
        let cleaned = String(event.prefix(420)).replacingOccurrences(of: "\n", with: " ")
        let line = "\(Date().ISO8601Format()) pid=\(getpid()) \(cleaned)\n"
        let bytes = Array(line.utf8)
        _ = bytes.withUnsafeBytes { buffer in
            Darwin.write(fd, buffer.baseAddress, buffer.count)
        }
        _ = Darwin.fsync(fd)
    }
}

private enum FlekDeckBootPaths {
    private static let legacyRoot = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("FlekDeck/Boot", isDirectory: true)
    // The upstream sandbox grant issuer only grants paths inside the host HOME.
    // Store ROMs here even when the signing profile also authorizes App Groups.
    static let root: URL = legacyRoot
    static let slot: URL = root.appendingPathComponent("Slot/A", isDirectory: true)
    static let stagingSlot: URL = root.appendingPathComponent("Slot/.A.installing", isDirectory: true)
    static let previousSlot: URL = root.appendingPathComponent("Slot/.A.previous", isDirectory: true)
    static let imports: URL = root.appendingPathComponent("Imports", isDirectory: true)
    private static let committedReceipt = root.appendingPathComponent("committed-rom.plist")
    /// Real unpacked ROM filesystem, not an archive nested in the IPA.
    static var embeddedProcursusRoot: URL? {
        let root = Bundle.main.bundleURL.appendingPathComponent("EmbeddedROM/ROM", isDirectory: true)
        return FileManager.default.fileExists(
            atPath: root.appendingPathComponent("manifest.plist").path) ? root : nil
    }


    static var expectedFlashedROM: Bool {
        FileManager.default.fileExists(atPath: committedReceipt.path)
    }

    /// Commit a human-readable receipt only after the signed staged slot has
    /// actually become Slot/A. Keep it outside Slot/A so interrupted relaunch
    /// can distinguish a missing slot from a deliberate first launch.
    static func recordCommittedROM(_ manifest: ROMManifest) throws {
        let data = try PropertyListSerialization.data(fromPropertyList: [
            "identifier": manifest.identifier,
            "version": manifest.version,
            "manifestVersion": manifest.manifestVersion
        ], format: .xml, options: 0)
        try data.write(to: committedReceipt, options: .atomic)
    }

    static func clearCommittedROM() {
        try? FileManager.default.removeItem(at: committedReceipt)
    }

    /// Nyxian's NXBootstrap and virtual filesystem resolve these paths
    /// relative to Bundle.main, not the flashed ROM or LiveProcess.appex.
    /// Never jump into NXSlotMain when any required host asset is absent.
    static func missingNyxianBootAssets() -> [String] {
        let resources = [
            "Shared/lib.zip",
            "Shared/include.zip",
            "Shared/swift.zip",
            "Shared/kernel/ksurface_abi.h",
            "Shared/LaunchServices/org.emexlabs.bootstrapd.plist",
            "Shared/LaunchServices/org.emexlabs.compilerd.plist",
            "Frameworks/bootstrapd.dylib",
            "Frameworks/libBroadpatch.dylib",
            "Frameworks/MobileDevelopmentService.dylib",
            "Frameworks/MobileDevelopmentKit.framework/Frameworks/CoreCompiler.framework/CoreCompiler",
            "Frameworks/MobileDevelopmentKit.framework/MobileDevelopmentKit",
            "PlugIns/LiveProcess.appex/Frameworks/FlekDeckPERuntime.dylib",
            "PlugIns/LiveProcess.appex/Frameworks/LiveShim.framework/LiveShim",
            "PlugIns/LiveProcess.appex/Frameworks/libBroadpatch.dylib",
            "EmbeddedROM/ROM/manifest.plist",
            "EmbeddedROM/ROM/System/Rom/init",
            "EmbeddedROM/ROM/System/Library/CoreServices/SpringBoard.app/SpringBoard",
            "EmbeddedROM/ROM/bootstrap.tar.zst",
            "EmbeddedROM/symlinks.plist"
        ]
        return resources.filter {
            !FileManager.default.fileExists(atPath: Bundle.main.bundleURL.appendingPathComponent($0).path)
        }
    }

    static func availableSpaceInMegabytes() -> Int? {
        guard let attrs = try? FileManager.default.attributesOfFileSystem(forPath: NSHomeDirectory()),
              let free = attrs[.systemFreeSize] as? NSNumber else {
            return nil
        }
        return Int(free.int64Value / 1_000_000)
    }

    static func previousSessionWasActive() -> Bool {
        guard let plist = NSDictionary(contentsOf: root.appendingPathComponent("boot-session.plist")) else {
            return false
        }
        return (plist["active"] as? Bool) == true
    }

    static func setSessionActive(_ active: Bool) throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let data = try PropertyListSerialization.data(fromPropertyList:
            ["active": active, "hostPID": Int(getpid())], format: .binary, options: 0)
        try data.write(to: root.appendingPathComponent("boot-session.plist"), options: .atomic)
    }

    static func recoverInterruptedInstall() throws {
        let manager = FileManager.default
        // Recover earlier App Group installs without deleting their source.
        // New installs stay inside the host sandbox and use PE file grants.
        let sharedRoot = FlekDeckBootSharedRootURL()
        if let sharedRoot,
           sharedRoot.standardizedFileURL != root.standardizedFileURL,
           manager.fileExists(atPath: sharedRoot.path),
           !manager.fileExists(atPath: root.path) {
            try manager.createDirectory(at: root.deletingLastPathComponent(), withIntermediateDirectories: true)
            try manager.copyItem(at: sharedRoot, to: root)
        }
        try manager.createDirectory(at: root, withIntermediateDirectories: true)
        if let sharedRoot,
           sharedRoot.standardizedFileURL != root.standardizedFileURL,
           !manager.fileExists(atPath: slot.path) {
            let sharedSlot = sharedRoot.appendingPathComponent("Slot/A", isDirectory: true)
            if manager.fileExists(atPath: sharedSlot.path) {
                try manager.createDirectory(at: slot.deletingLastPathComponent(), withIntermediateDirectories: true)
                try manager.copyItem(at: sharedSlot, to: slot)
            }
        }

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
private typealias FlekDeckNXT2VerifyFunction =
    @convention(c) (UnsafePointer<CChar>) -> Int32

private struct FlekDeckNXT2HostServices {
    let sign: FlekDeckNXT2SignFunction
    let verify: FlekDeckNXT2VerifyFunction
}

private func FlekDeckNXT2HostSigner() -> FlekDeckNXT2HostServices? {
    // A dedicated, safely loadable dylib contains pinned Nyxian signing.c,
    // cdhash.c and key.c. Loading the guest System/Rom/init here executes
    // pre-bootstrap guest initializers and previously crashed iOS 27.
    guard let file = Bundle.main.privateFrameworksURL?
        .appendingPathComponent("FlekDeckNXT2Signer.dylib"),
          FileManager.default.isReadableFile(atPath: file.path) else {
        FlekDeckBootTrace.mark("procursus-nxt2-native-library-not-packaged")
        return nil
    }
    dlerror()
    guard let handle = dlopen(file.path, RTLD_NOW | RTLD_LOCAL) else {
        FlekDeckBootTrace.mark("procursus-nxt2-native-dlopen-error \(lastDlError())")
        return nil
    }
    guard let ready = dlsym(handle, "FlekDeckNXT2SignerReady"),
          let signingFunction = dlsym(handle, "trust_nxt2_sign"),
          let verifyFunction = dlsym(handle, "FlekDeckNXT2VerifySignedPath") else {
        FlekDeckBootTrace.mark("procursus-nxt2-native-signer-symbols-missing")
        return nil
    }
    let selfTest = unsafeBitCast(ready, to: (@convention(c) () -> Int32).self)
    guard selfTest() == 1 else {
        FlekDeckBootTrace.mark("procursus-nxt2-native-keychain-initialization-failed")
        return nil
    }
    FlekDeckBootTrace.mark("procursus-nxt2-native-signer-and-key-ready")
    return FlekDeckNXT2HostServices(
        sign: unsafeBitCast(signingFunction, to: FlekDeckNXT2SignFunction.self),
        verify: unsafeBitCast(verifyFunction, to: FlekDeckNXT2VerifyFunction.self))
}

private func FlekDeckNXT2Sign(hostSigner: FlekDeckNXT2SignFunction,
                              path: String,
                              entitlements: CFDictionary) -> Int32 {
    return path.withCString { pathPointer in
        hostSigner(pathPointer, entitlements, true, nil)
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


/*
 Boot lifecycle adapted directly from Nyxian 0.11.5 BootViewController.
 Preserve its volume scan, ROM splash, entry point, window and appearance hooks,
 transitions and recovery path. FlekDeck supplies the built-in shell and store.
*/
private final class FlekDeckBootViewController: UIViewController {
    private let builtinController: UIViewController
    // Retain the ROM window only as a native bootstrap/guest scene host.
    // FlekDeck's original UIKit/SwiftUI Home always stays frontmost.
    // Never replace its launcher, icon ordering, Installer, or multitask dock.
    private var activeSlotWindow: UIWindow?
    private var didStartBoot = false
    private var guestActivationInProgress = false

    private static let showGuestName = Notification.Name("FlekDeckProcursusGuestDidLaunch")

    private static let guestBootCrashGuardKey = "FlekDeckGuestSpringBoardCrashGuard"
    // Never block a first run behind Procursus provisioning. A valid
    // certificate may be imported from FlekDeck Settings before a user
    // explicitly starts the optional ROM installation.
    private static var wantsProcursusRuntime: Bool { true }

    init(builtinController: UIViewController) {
        self.builtinController = builtinController
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }
    private let splashView = UIView()
    private let logoView = UIImageView()
    
    private enum BootTransition {
        case zoomThrough
        case crossfade
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        guard !didStartBoot else { return }
        didStartBoot = true
        BootConfig.registerDefaults()
        FlekDeckBootTrace.begin()
        // A prior SIGKILL does not invoke the installer completion handler.
        // Do not automatically repeat a fatal native crash on every launch.
        if UserDefaults.standard.bool(forKey: procursusInstallInFlightKey) {
            let manifestURL = flashedSlotURL().appendingPathComponent("manifest.plist")
            let wasCommitted = FileManager.default.fileExists(atPath: manifestURL.path)
            UserDefaults.standard.removeObject(forKey: procursusInstallInFlightKey)
            if !wasCommitted {
                UserDefaults.standard.set(
                    "The previous Procursus installation terminated unexpectedly before the ROM was committed. Open Boot Logs for the last recorded operation, then retry setup.",
                    forKey: "FlekDeckProcursusLastInstallError")
                FlekDeckBootTrace.mark("procursus-interrupted-install-detected-auto-retry-paused")
            } else {
                FlekDeckBootTrace.mark("procursus-interrupted-install-but-rom-committed")
            }
            UserDefaults.standard.synchronize()
        }
        // Do not display stale in-progress UI after a terminated app process.
        UserDefaults.standard.removeObject(forKey: procursusProgressKey)
        NotificationCenter.default.addObserver(
            self, selector: #selector(presentProcursusGuest),
            name: Self.showGuestName, object: nil)
        NotificationCenter.default.addObserver(
            self, selector: #selector(activateInstalledProcursus),
            name: Notification.Name("FlekDeckActivateInstalledProcursus"),
            object: nil)
        
        self.view.backgroundColor = .systemBackground
        
        splashView.backgroundColor = self.view.backgroundColor
        splashView.frame = self.view.bounds
        splashView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        self.view.addSubview(splashView)
        
        let slot: URL = flashedSlotURL()
        if let manifest: ROMManifest = try? ROMManifest(manifestPlistURL: slot.appendingPathComponent("manifest.plist")),
           let logo: UIImage = manifest.bootlogo {
            logoView.image = logo
        } else {
            logoView.image = UIImage(systemName: "square.stack.3d.up")
        }
        logoView.contentMode = .scaleAspectFit
        logoView.translatesAutoresizingMaskIntoConstraints = false
        
        splashView.addSubview(logoView)
        
        NSLayoutConstraint.activate([
            logoView.centerYAnchor.constraint(equalTo: splashView.centerYAnchor),
            logoView.centerXAnchor.constraint(equalTo: splashView.centerXAnchor),
            logoView.heightAnchor.constraint(equalToConstant: 125),
            logoView.widthAnchor.constraint(equalToConstant: 125),
        ])
        
        #if targetEnvironment(simulator)
        // Simulator's kernel / FrontBoard cannot register Nyxian real-device
        // guest Mach-O executables (LC_BUILD_VERSION platform iOS=2,
        // simulator=7). Smoke-test the unchanged FlekDeck Home ONLY.
        FlekDeckBootTrace.mark("simulator-host-smoke-only-real-rom-unsupported")
        self.transition(to: self.builtinController)
        return
        #endif

        DispatchQueue.global(qos: .utility).async {
            let mode = NXVolumeButtonMonitor.scan(for: 1.0)
            NXVolumeButtonMonitor.disarm()
            FlekDeckBootTrace.mark("volume-scan-finished mode=\(mode)")
            
            if mode == 2 {
                DispatchQueue.main.async {
                    self.enterRecovery(error: nil)
                }
                return
            }
            

            do {
                let previousActive = FlekDeckBootPaths.previousSessionWasActive()
                FlekDeckBootTrace.mark("previous-session-active=\(previousActive)")
                // A synchronous trap inside the ROM's NXSlotMain previously made
                // every cold launch crash. Next launch must show FlekDeck
                // instead, keeping the user's installed ROM untouched.
                if previousActive {
                    UserDefaults.standard.set(true, forKey: Self.guestBootCrashGuardKey)
                    FlekDeckBootTrace.mark("integrated-guest-crash-guard-armed")
                }
                try FlekDeckBootPaths.recoverInterruptedInstall()
                try FlekDeckBootPaths.setSessionActive(false)
                FlekDeckBootTrace.mark("rom-store-recovered")
            } catch {
                let message = error.localizedDescription
                DispatchQueue.main.async {
                    self.enterRecovery(error: "ERROR: Could not recover the ROM store: " + message)
                }
                return
            }

            // FlekDeck's own shell is the built-in slot, replacing SuperSlot.
            if mode == 1 || !Self.wantsProcursusRuntime ||
                UserDefaults.standard.bool(forKey: Self.guestBootCrashGuardKey) {
                let reason = mode == 1 ? "volume-override" :
                    (!Self.wantsProcursusRuntime ? "disabled-by-user" : "previous-guest-boot-failed")
                FlekDeckBootTrace.mark("builtin-shell-selected-\(reason)")
                DispatchQueue.main.async {
                    self.transition(to: self.builtinController)
                }
                return
            }
            // FlekDeck Home/Settings are ALWAYS available before Procursus
            // is installed. Never sign or dlopen guest binaries on cold start:
            // a signed host IPA does not carry its P12 private key.
            // The user can import signing identity and explicitly install
            // the optional ROM in FlekDeck Settings -> Procursus.
            let installedManifest = flashedSlotURL().appendingPathComponent("manifest.plist")
            if !FileManager.default.fileExists(atPath: installedManifest.path),
               !FlekDeckBootPaths.expectedFlashedROM {
                FlekDeckBootTrace.mark("procursus-install-deferred-to-settings")
                DispatchQueue.main.async {
                    self.transition(to: self.builtinController)
                }
                return
            }
            if !FileManager.default.fileExists(atPath: installedManifest.path) {
                if FlekDeckBootPaths.expectedFlashedROM {
                    FlekDeckBootTrace.mark("rom-committed-receipt-present-but-manifest-missing")
                    DispatchQueue.main.async {
                        self.enterRecovery(error: "ERROR: A ROM was previously installed, but its slot manifest is missing. The ROM was not automatically removed. Check Files and reflash or restore the slot.")
                    }
                } else {
                    FlekDeckBootTrace.mark("builtin-shell-selected-no-committed-rom")
                    DispatchQueue.main.async {
                        self.transition(to: self.builtinController)
                    }
                }
                return
            }

            // This is FlekDeck's own Home, not another bootable phone.
            // Show it BEFORE loading ROM services. The ROM initializer may
            // terminate the process on a real PE failure; a persistent boot
            // guard protects the next launch, while the user never sees
            // another standalone SpringBoard as the default interface.
            FlekDeckBootTrace.mark("procursus-home-first-activation")
            DispatchQueue.main.async {
                self.transition(to: self.builtinController, style: .crossfade) {
                    self.activateInstalledProcursus()
                }
            }
            return
        }
    }

    // Activate the installed ROM within the SAME running FlekDeck app.
    // The native constructor can abort before returning from dlopen;
    // persist a crash-guard marker first and never retry automatically
    // after the corresponding crash. No fake process state is reported.
    @objc private func activateInstalledProcursus() {
        guard !guestActivationInProgress, activeSlotWindow == nil else {
            FlekDeckBootTrace.mark("procursus-live-activation-already-running")
            return
        }
        guard FlekDeckHasInstalledProcursusROM() else {
            FlekDeckBootTrace.mark("procursus-live-activation-no-committed-rom")
            return
        }
        guard !UserDefaults.standard.bool(forKey: Self.guestBootCrashGuardKey) else {
            FlekDeckBootTrace.mark("procursus-live-activation-crash-guard-blocked")
            return
        }
        guestActivationInProgress = true
        DispatchQueue.global(qos: .utility).async {
            // Validate actual packaged PE services before calling dyld.
            // Never load the guest constructor with a missing runtime.
            let missing = FlekDeckBootPaths.missingNyxianBootAssets()
            guard missing.isEmpty else {
                FlekDeckBootTrace.mark("procursus-live-missing-assets \(missing.joined(separator: ","))")
                DispatchQueue.main.async { self.guestActivationInProgress = false }
                return
            }
            if FlekDeckBootPaths.previousSessionWasActive() {
                FlekDeckBootTrace.mark("procursus-live-activation-already-active")
                DispatchQueue.main.async { self.guestActivationInProgress = false }
                return
            }
            do {
                try FlekDeckBootPaths.setSessionActive(true)
                FlekDeckBootTrace.mark("procursus-live-dlopen-crash-guard-armed")
            } catch {
                FlekDeckBootTrace.mark("procursus-live-activation-session-error \(error.localizedDescription)")
                DispatchQueue.main.async { self.guestActivationInProgress = false }
                return
            }
            FlekDeckTraceROMProcessEnvironment()
            FlekDeckBootTrace.mark("procursus-live-dlopen-enter")
            let result = loadSlot(loadSuperslotForcefully: false)
            FlekDeckBootTrace.mark("procursus-live-dlopen-return")
            DispatchQueue.main.async {
                self.guestActivationInProgress = false
                switch result {
                case let .failed(error):
                    try? FlekDeckBootPaths.setSessionActive(false)
                    FlekDeckBootTrace.mark("procursus-live-dlopen-failed \(error)")
                case let .loaded(name, main, appeared, createWindow):
                    FlekDeckBootTrace.mark("procursus-live-integrated-boot-enter")
                    self.startIntegratedSpringBoard(name: name,
                        slotMain: main,
                        slotDidAppear: appeared,
                        slotCreateWindow: createWindow)
                }
            }
        }
    }

    private func startIntegratedSpringBoard(
        name: String,
        slotMain: NXSlotMainFn,
        slotDidAppear: NXSlotDidAppearFn?,
        slotCreateWindow: NXSlotCreateWindowFn?
    ) {
        guard let slotCreateWindow else {
            FlekDeckBootTrace.mark("integrated-springboard-window-hook-missing")
            try? FlekDeckBootPaths.setSessionActive(false)
            self.transition(to: self.builtinController)
            return
        }
        let extensionPresent = FileManager.default.fileExists(
            atPath: Bundle.main.builtInPlugInsURL?
                .appendingPathComponent("LiveProcess.appex", isDirectory: true).path ?? "")
        FlekDeckBootTrace.mark("integrated-nxslotmain-enter name=\(name) liveprocess-present=\(extensionPresent)")
        // This is the REAL ROM initializer, not a SwiftUI SpringBoard clone.
        // Any synchronous failure leaves the session flag active; a subsequent
        // launch honors the crash guard instead of retrying indefinitely.
        guard let raw = slotMain() else {
            FlekDeckBootTrace.mark("integrated-nxslotmain-returned-nil")
            try? FlekDeckBootPaths.setSessionActive(false)
            self.transition(to: self.builtinController)
            return
        }
        FlekDeckBootTrace.mark("integrated-nxslotmain-return")
        let guestRoot = Unmanaged<UIViewController>.fromOpaque(raw).takeRetainedValue()
        FlekDeckBootTrace.captureNyxianKmsg()
        guard let guestWindow = makeSlotWindow(slotCreateWindow) else {
            FlekDeckBootTrace.mark("integrated-rom-window-creation-failed")
            try? FlekDeckBootPaths.setSessionActive(false)
            return
        }
        guard view.window != nil else {
            FlekDeckBootTrace.mark("procursus-host-window-unavailable")
            try? FlekDeckBootPaths.setSessionActive(false)
            self.transition(to: self.builtinController)
            return
        }

        // Retain Nyxian's real WindowServer / SpringBoard UIKit view so the
        // guest processes can run, but DO NOT replace the FlekDeck host UI
        // with a second "jailbroken phone" display. Actual guest apps
        // (including Sileo once installed by apt) are enumerated through
        // LDEApplicationWorkspace and appear in FlekDeck's existing Home.
        activeSlotWindow = guestWindow
        guestWindow.rootViewController = guestRoot
        guestWindow.windowLevel = .normal - 1
        guestWindow.makeKeyAndVisible()
        guestRoot.view.layoutIfNeeded()
        view.window?.makeKeyAndVisible()
        FlekDeckBootTrace.mark("procursus-integrated-backend-window-ready")
        completeROMBoot(didAppear: slotDidAppear)
    }

    // A real guest app is displayed only after a successful workspace launch.
    // This is normal full-screen app navigation, not a second launcher or
    // floating switcher. Swipe from the left edge to return to FlekDeck's
    // exact existing Home / Settings / Installer and app-switcher state.
    @objc private func presentProcursusGuest() {
        guard let guestWindow = activeSlotWindow,
              let hostWindow = view.window else { return }
        guestWindow.windowLevel = .normal + 1
        if let rootView = guestWindow.rootViewController?.view {
            let alreadyPresent = rootView.gestureRecognizers?.contains {
                $0 is UIScreenEdgePanGestureRecognizer &&
                ($0 as? UIScreenEdgePanGestureRecognizer)?.edges == .left
            } ?? false
            if !alreadyPresent {
                let back = UIScreenEdgePanGestureRecognizer(
                    target: self, action: #selector(procursusGuestBackGesture(_:)))
                back.edges = .left
                rootView.addGestureRecognizer(back)
            }
        }
        guestWindow.makeKeyAndVisible()
        FlekDeckBootTrace.mark("procursus-guest-app-presented")
        _ = hostWindow // Keep FlekDeck's window alive underneath.
    }

    @objc private func procursusGuestBackGesture(_ recognizer: UIScreenEdgePanGestureRecognizer) {
        guard recognizer.state == .ended,
              recognizer.translation(in: recognizer.view).x > 70,
              let hostWindow = view.window else { return }
        activeSlotWindow?.windowLevel = .normal - 1
        hostWindow.makeKeyAndVisible()
        NotificationCenter.default.post(
            name: Notification.Name("FlekDeckProcursusRuntimeReady"),
            object: nil)
        FlekDeckBootTrace.mark("procursus-guest-app-returned-to-flekdeck")
    }

    private func completeROMBoot(didAppear: NXSlotDidAppearFn?) {
        FlekDeckBootTrace.mark("rom-didappear-enter")
        didAppear?()
        FlekDeckBootTrace.mark("rom-didappear-return")
        FlekDeckBootTrace.captureNyxianKmsg()
        do {
            try FlekDeckBootPaths.setSessionActive(false)
            UserDefaults.standard.set(false, forKey: Self.guestBootCrashGuardKey)
            FlekDeckBootTrace.mark("rom-boot-ui-ready")
            NotificationCenter.default.post(
                name: Notification.Name("FlekDeckProcursusRuntimeReady"),
                object: nil)
        } catch {
            FlekDeckBootTrace.mark("rom-session-finalize-failed \(error.localizedDescription)")
        }
    }

    private func makeSlotWindow(_ create: NXSlotCreateWindowFn) -> UIWindow? {
        guard let scene = view.window?.windowScene else { return nil }
        guard let raw = create(Unmanaged.passUnretained(scene).toOpaque()) else { return nil }
        return Unmanaged<UIWindow>.fromOpaque(raw).takeRetainedValue()
    }
    
    private func transition(into slotWindow: UIWindow,
                            root: UIViewController,
                            completion: (() -> Void)? = nil) {
        let hostWindow = view.window
        
        activeSlotWindow = slotWindow
        slotWindow.rootViewController = root
        slotWindow.alpha = 0
        slotWindow.makeKeyAndVisible()
        root.view.layoutIfNeeded()
        
        if let presentation = logoView.layer.presentation() {
            logoView.layer.transform = presentation.transform
        }
        logoView.layer.removeAnimation(forKey: "breathe")
        
        let finish = {
            hostWindow?.isHidden = true
            hostWindow?.rootViewController = nil
            // SwiftUI owns the original scene delegate. Retain the ROM window
            // here instead of assigning Nyxian's SceneDelegate.window.
            completion?()
        }
        
        if UIAccessibility.isReduceMotionEnabled {
            UIView.animate(withDuration: 0.3, animations: {
                slotWindow.alpha = 1
            }, completion: { _ in
                finish()
            })
            return
        }
        
        root.view.transform = CGAffineTransform(scaleX: 0.97, y: 0.97)
        
        let splashOut = UIViewPropertyAnimator(duration: 0.4, curve: .easeOut) {
            self.logoView.transform = CGAffineTransform(scaleX: 1.15, y: 1.15)
            self.splashView.alpha = 0
            slotWindow.alpha = 1
        }
        
        let appIn = UIViewPropertyAnimator(duration: 0.55, dampingRatio: 1.0) {
            root.view.transform = .identity
        }
        
        appIn.addCompletion { _ in
            finish()
        }
        
        splashOut.startAnimation()
        appIn.startAnimation()
    }
    
    private func enterRecovery(error: String?) {
        FlekDeckBootTrace.mark("recovery-enter \(error ?? "user-volume-request")")
        let recoveryController = NXRecoveryViewController()
        if let error {
            recoveryController.recoveryLogError(error)
        }
        recoveryShowMenu(recoveryController: recoveryController)
        self.transition(to: recoveryController, style: .crossfade)
    }
    
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        startBreathing()
    }
    
    private func startBreathing() {
        guard !UIAccessibility.isReduceMotionEnabled,
              splashView.superview != nil,
              logoView.layer.animation(forKey: "breathe") == nil else { return }
        
        let pulse = CABasicAnimation(keyPath: "transform.scale")
        pulse.fromValue = 1.0
        pulse.toValue = 0.94
        pulse.duration = 0.9
        pulse.autoreverses = true
        pulse.repeatCount = .infinity
        pulse.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        logoView.layer.add(pulse, forKey: "breathe")
    }
    
    private func transition(to child: UIViewController,
                            style: BootTransition = .zoomThrough,
                            completion: (() -> Void)? = nil) {
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.insertSubview(child.view, belowSubview: splashView)
        child.view.layoutIfNeeded()
        
        if let presentation = logoView.layer.presentation() {
            logoView.layer.transform = presentation.transform
        }
        logoView.layer.removeAnimation(forKey: "breathe")
        
        let finish = {
            self.splashView.removeFromSuperview()
            child.didMove(toParent: self)
            completion?()
        }
        
        if style == .crossfade || UIAccessibility.isReduceMotionEnabled {
            UIView.animate(withDuration: 0.3, animations: {
                self.splashView.alpha = 0
            }, completion: { _ in
                finish()
            })
            return
        }
        
        child.view.transform = CGAffineTransform(scaleX: 0.97, y: 0.97)
        
        let splashOut = UIViewPropertyAnimator(duration: 0.4, curve: .easeOut) {
            self.logoView.transform = CGAffineTransform(scaleX: 1.15, y: 1.15)
            self.splashView.alpha = 0
        }
        
        let appIn = UIViewPropertyAnimator(duration: 0.55, dampingRatio: 1.0) {
            child.view.transform = .identity
        }
        
        appIn.addCompletion { _ in
            finish()
        }
        
        splashOut.startAnimation()
        appIn.startAnimation()
    }
    
    var changableStatusBarHidden = true
    override var prefersStatusBarHidden: Bool {
        return self.changableStatusBarHidden
    }
    
    override var preferredStatusBarUpdateAnimation: UIStatusBarAnimation {
        return .fade
    }
    
    override var childForStatusBarStyle: UIViewController? {
        splashView.superview == nil ? children.last : nil
    }
}


// Nyxian installs BootViewController directly as its UIWindow root from
// SceneDelegate. SwiftUI must never parent a live ROM boot controller inside
// UIViewControllerRepresentable: the ROM spins its own userspace/scene/window
// state while NXSlotMain is still on the main thread.
@MainActor
private enum FlekDeckNativeBootWindowCache {
    // Retain the UIKit scene host for the entire boot/ROM lifecycle.
    // NXSlotMain is deliberately single-shot per process.
    static var controller: FlekDeckBootViewController?
    static var window: UIWindow?

    static func install(in scene: UIWindowScene, builtin: UIViewController) {
        guard controller == nil else { return }
        let root = FlekDeckBootViewController(builtinController: builtin)
        let bootWindow = UIWindow(windowScene: scene)
        controller = root
        window = bootWindow

        // The same UIWindowSceneDelegate that SwiftUI uses for URL routing
        // now owns the native boot window, as in upstream Nyxian.
        if let delegate = scene.delegate as? SceneDelegate {
            delegate.window = bootWindow
        }
        bootWindow.rootViewController = root
        bootWindow.makeKeyAndVisible()
        FlekDeckBootTrace.mark("native-scene-window-root-active")
    }
}

// A passive bridge obtains the WindowGroup's environment only. The ROM
// controller does not live in this bridge and is not a SwiftUI child.
@MainActor
private final class FlekDeckNativeBootWindowBridge: UIViewController {
    private let builtin: UIViewController

    init(builtin: UIViewController) {
        self.builtin = builtin
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard let scene = view.window?.windowScene else {
            NSLog("[FlekDeck ROM] UIWindowScene not available for native boot")
            return
        }
        FlekDeckNativeBootWindowCache.install(in: scene, builtin: builtin)
    }
}

private struct FlekDeckBootControllerView<Content: View>: UIViewControllerRepresentable {
    let content: Content

    func makeUIViewController(context: Context) -> UIViewController {
        let builtin = UIHostingController(rootView: content.environment(\.self, context.environment))
        return FlekDeckNativeBootWindowBridge(builtin: builtin)
    }

    func updateUIViewController(_ controller: UIViewController, context: Context) {}
}

struct FlekDeckBootGateView<Content: View>: View {
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        FlekDeckBootControllerView(content: content)
            .ignoresSafeArea()
    }
}
