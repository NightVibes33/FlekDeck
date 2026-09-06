//
//  AccessVerification.swift
//  LiveContainer
//
//  Standalone compatibility layer for the upstream access-verification API.
//  This fork does not use FlekSt0re device, subscription, ban, or payment state.
//

import Foundation

enum AccessCheckResult {
    case answered(DeviceStatusResponse)
    case unreachable
    case serviceError
}

struct CachedAccessVerdict {
    let isBanned: Bool
    let banReason: String?
    let banMessage: String?
    let checkedAt: Date
    let graceWindow: TimeInterval

    func isFresh(asOf now: Date = Date()) -> Bool { true }
    func isWithinGraceWindow(asOf now: Date = Date()) -> Bool { true }
}

enum AccessVerdictStore {
    static let refreshInterval: TimeInterval = 3650 * 24 * 60 * 60
    static let defaultGraceWindow: TimeInterval = 3650 * 24 * 60 * 60

    static func load(for encryptedUDID: String, asOf now: Date = Date()) -> CachedAccessVerdict? {
        CachedAccessVerdict(
            isBanned: false,
            banReason: nil,
            banMessage: nil,
            checkedAt: now,
            graceWindow: defaultGraceWindow
        )
    }

    static func save(_ response: DeviceStatusResponse, for encryptedUDID: String, asOf now: Date = Date()) {
        // Deliberately no persistence: standalone FlekDeck has no remote access
        // verdict, subscription, ban, chargeback, or device-entitlement state.
    }
}

enum AccessVerificationService {
    static func fetchStatus(encryptedUDID: String) async -> AccessCheckResult {
        // Preserve the old call contract for source compatibility, but resolve it
        // locally. No UDID or other device identifier leaves the app.
        let payload = Data(#"{"status":true,"endDate":"","udid":"standalone","isBanned":false}"#.utf8)
        guard let response = try? JSONDecoder().decode(DeviceStatusResponse.self, from: payload) else {
            return .serviceError
        }
        return .answered(response)
    }
}
