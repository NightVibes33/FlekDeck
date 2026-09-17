#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
text = path.read_text()

# loadStoreFrameworksWithError2 may return immediately once ZSign is already
# loaded. Callers must never observe an uninitialized NSError pointer in that
# case. Clear the out-parameter at entry and only fill it on a real load error.
old_loader = '''+ (void)loadStoreFrameworksWithError2:(NSError **)error {
    // too lazy to use dispatch_once
    static BOOL loaded = NO;
    if (loaded) return;'''
new_loader = '''+ (void)loadStoreFrameworksWithError2:(NSError **)error {
    // too lazy to use dispatch_once
    if (error) *error = nil;
    static BOOL loaded = NO;
    if (loaded) return;'''
if old_loader in text:
    text = text.replace(old_loader, new_loader, 1)
elif new_loader not in text:
    raise SystemExit(f"{path}: ZSign loader anchor missing")

# NSError object pointers are ordinary local variables here; leaving them
# uninitialized makes `if (error)` undefined behavior after an early-returning
# loader call. Initializing to nil is behavior-preserving on success and makes
# failure checks deterministic.
text = text.replace("    NSError *error;\n", "    NSError *error = nil;\n")

old_validate = '''+ (int)validateCertificateWithCompletionHandler:(void(^)(int status, NSDate *expirationDate, NSString *organizationalUnitName, NSString *error))completionHandler {
    NSError *error = nil;
    NSData *certData = [LCUtils certificateData];
    if (error) {
        return -6;
    }
    [self loadStoreFrameworksWithError2:&error];
    int ans = [NSClassFromString(@"ZSigner") checkCert:certData pass:[LCSharedUtils certificatePassword] completionHandler:completionHandler];
    return ans;
}'''
new_validate = '''+ (int)validateCertificateWithCompletionHandler:(void(^)(int status, NSDate *expirationDate, NSString *organizationalUnitName, NSString *error))completionHandler {
    NSError *error = nil;
    NSData *certData = [LCUtils certificateData];
    [self loadStoreFrameworksWithError2:&error];
    if (error) {
        if (completionHandler) {
            completionHandler(-6, nil, nil, error.localizedDescription);
        }
        return -6;
    }
    int ans = [NSClassFromString(@"ZSigner") checkCert:certData pass:[LCSharedUtils certificatePassword] completionHandler:completionHandler];
    return ans;
}'''
if old_validate in text:
    text = text.replace(old_validate, new_validate, 1)
elif new_validate not in text:
    raise SystemExit(f"{path}: certificate validation anchor missing")

path.write_text(text)

final = path.read_text()
if "NSError *error;" in final:
    raise SystemExit(f"{path}: uninitialized NSError local remains")
if "if (error) *error = nil;" not in final:
    raise SystemExit(f"{path}: ZSign loader does not initialize its out error")
validate_region = final[final.find("+ (int)validateCertificateWithCompletionHandler"):final.find("#pragma mark", final.find("+ (int)validateCertificateWithCompletionHandler"))]
if validate_region.find("loadStoreFrameworksWithError2:&error") > validate_region.find("if (error)"):
    raise SystemExit(f"{path}: certificate validation still checks error before loading ZSign")

print("FlekDeck signer error state hardened")
