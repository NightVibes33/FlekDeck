/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 FlekDeck bridge to its configured ZSign identity for ROM payloads.
*/

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Signs ROM Mach-O files with the identity already configured in FlekDeck.
/// The ROM archive itself is not modified.
FOUNDATION_EXPORT BOOL FlekDeckSignROMFilesWithZSign(NSArray<NSURL *> *files,
                                                     NSError * _Nullable * _Nullable error);

/// Log bundled LiveProcess readiness without changing Nyxian registration.
FOUNDATION_EXPORT void FlekDeckTraceROMProcessEnvironment(void);

/// Checks Nyxian's required NSExtension and get-task-allow entitlement
/// against the installed, re-signed LiveProcess extension itself.
/// Nil means the required extension is present and correctly entitled.
FOUNDATION_EXPORT NSString * _Nullable FlekDeckROMProcessExtensionFailureReason(void);

/// Returns the ROM store shared by FlekDeck and its LiveProcess extension.
/// Returns nil when the signed app has no usable application-group entitlement.
FOUNDATION_EXPORT NSURL * _Nullable FlekDeckBootSharedRootURL(void);

/// Enumerate actual installed Procursus guest applications through Nyxian's
/// LDEApplicationWorkspace; an empty result means bootstrap is not ready or no
/// guest apps exist. Never fabricate Sileo or other app entries.
FOUNDATION_EXPORT NSArray<NSDictionary<NSString *, id> *> *FlekDeckListProcursusApps(void);

/// Launch one *registered* guest application through the ROM's genuine
/// bootstrapd / PEProcessManager / NXWindowServer pipeline.
FOUNDATION_EXPORT BOOL FlekDeckLaunchProcursusApp(NSString *bundleID);

NS_ASSUME_NONNULL_END
