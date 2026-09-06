from pathlib import Path

path = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
s = path.read_text(encoding="utf-8")

old_section = '''                // MARK: - Certificate (shown only when no certificate is detected)
                if sharedModel.multiLCStatus != 2 {
                    Section {
                        Button("lc.settings.importCertificate".loc) {
                            Task { await importCertificate() }
                        }
                    } header: {
                        Text("lc.settings.jitLess".loc)
                    } footer: {
                        Text("lc.settings.jitLessDesc".loc)
                    }
                }
'''
new_section = '''                // MARK: - Certificate
                if sharedModel.multiLCStatus != 2 {
                    Section {
                        if certificateDataFound {
                            Label("Certificate Imported", systemImage: "checkmark.seal.fill")
                                .foregroundStyle(.green)

                            Button("Replace Certificate") {
                                Task { await importCertificate() }
                            }

                            Button("lc.settings.removeCertificate".loc, role: .destructive) {
                                Task { await removeCertificate() }
                            }
                        } else {
                            Button("lc.settings.importCertificate".loc) {
                                Task { await importCertificate() }
                            }
                        }
                    } header: {
                        Text("lc.settings.jitLess".loc)
                    } footer: {
                        Text("lc.settings.jitLessDesc".loc)
                    }
                }
'''
if old_section in s:
    s = s.replace(old_section, new_section, 1)
elif 'Label("Certificate Imported", systemImage: "checkmark.seal.fill")' not in s:
    raise SystemExit("Could not locate main certificate section")

old_import = '''        guard let _ = LCUtils.getCertTeamId(withKeyData: certificateData, password: certificatePassword) else {
            errorInfo = "lc.settings.invalidCertError".loc
            errorShow = true
            return
        }
        
        LCUtils.appGroupUserDefault.set(certificateData, forKey: "LCCertificateData")
        LCUtils.appGroupUserDefault.set(certificatePassword, forKey: "LCCertificatePassword")
        LCUtils.appGroupUserDefault.set(NSDate.now, forKey: "LCCertificateUpdateDate")
        certificateDataFound = true

        UserDefaults.standard.set(LCSharedUtils.appGroupID(), forKey: "LCAppGroupID")
'''
new_import = '''        guard let certificateTeamId = LCUtils.getCertTeamId(withKeyData: certificateData, password: certificatePassword) else {
            errorInfo = "lc.settings.invalidCertError".loc
            errorShow = true
            return
        }

        // Use the same persistence callback as the SideStore certificate path.
        onSideStoreCertificateCallback(certificateData: certificateData, password: certificatePassword)
        UserDefaults.standard.set(LCSharedUtils.appGroupID(), forKey: "LCAppGroupID")

        // Verify that the identity is immediately readable from shared storage.
        certificateDataFound = LCSharedUtils.certificatePassword() != nil
        guard certificateDataFound else {
            errorInfo = "Certificate validated but could not be read back from FlekDeck storage."
            errorShow = true
            return
        }

        successInfo = "Certificate imported successfully. Team ID: \\(certificateTeamId)"
        successShow = true
'''
if old_import in s:
    s = s.replace(old_import, new_import, 1)
elif "Certificate validated but could not be read back from FlekDeck storage." not in s:
    raise SystemExit("Could not locate manual certificate persistence block")

old_appear = '''        .onAppear {
            if !isViewAppeared {
'''
new_appear = '''        .onAppear {
            // Refresh persisted certificate state whenever Settings is shown.
            certificateDataFound = LCSharedUtils.certificatePassword() != nil
            if !isViewAppeared {
'''
if old_appear in s:
    s = s.replace(old_appear, new_appear, 1)
elif "Refresh persisted certificate state whenever Settings is shown." not in s:
    raise SystemExit("Could not locate Settings onAppear")

old_callback = '''    func onSideStoreCertificateCallback(certificateData: Data, password: String) {
        LCUtils.appGroupUserDefault.set(certificateData, forKey: "LCCertificateData")
        LCUtils.appGroupUserDefault.set(password, forKey: "LCCertificatePassword")
        LCUtils.appGroupUserDefault.set(NSDate.now, forKey: "LCCertificateUpdateDate")
        certificateDataFound = true
    }
'''
new_callback = '''    func onSideStoreCertificateCallback(certificateData: Data, password: String) {
        LCUtils.appGroupUserDefault.set(certificateData, forKey: "LCCertificateData")
        LCUtils.appGroupUserDefault.set(password, forKey: "LCCertificatePassword")
        LCUtils.appGroupUserDefault.set(NSDate.now, forKey: "LCCertificateUpdateDate")
        UserDefaults.standard.set(LCSharedUtils.appGroupID(), forKey: "LCAppGroupID")
        certificateDataFound = LCSharedUtils.certificatePassword() != nil
    }
'''
if old_callback in s:
    s = s.replace(old_callback, new_callback, 1)
elif 'certificateDataFound = LCSharedUtils.certificatePassword() != nil' not in s:
    raise SystemExit("Could not locate SideStore certificate callback")

if '.betterFileImporter(isPresented: $certificateImportFileAlert.show, types: [.p12]' not in s:
    raise SystemExit("PKCS#12 .p12 importer missing")

path.write_text(s, encoding="utf-8")
print("Certificate import state patch applied")
