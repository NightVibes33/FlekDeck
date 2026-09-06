//
//  SharedModel.swift
//  LiveContainer
//
//  Created by Alexander Grigoryev on 30.09.2025.
//
import SwiftUI

class FlekstoreSharedModel: ObservableObject {
    @Published var appInstallURL: String = ""

    init() {
        // This fork is standalone. The upstream UI historically required a
        // FlekSt0re-issued encrypted UDID before it would render anything.
        // Keep a local marker only for compatibility with the remaining launch
        // plumbing; no device identity is sent to an access/payment service.
        let key = "FSEncryptedUDID"
        if (UserDefaults.standard.string(forKey: key) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty {
            UserDefaults.standard.set("standalone", forKey: key)
        }
    }
}
