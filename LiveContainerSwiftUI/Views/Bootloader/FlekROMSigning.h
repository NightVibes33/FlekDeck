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

/// Returns the ROM store shared by FlekDeck and its LiveProcess extension.
/// Returns nil when the signed app has no usable application-group entitlement.
FOUNDATION_EXPORT NSURL * _Nullable FlekDeckBootSharedRootURL(void);

NS_ASSUME_NONNULL_END
