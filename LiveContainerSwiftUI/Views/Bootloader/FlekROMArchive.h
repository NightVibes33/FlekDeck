#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Extracts the uploaded Nyxian ROM ZIP without changing the ZIP itself.
/// The archive's single top-level ROM/ directory is the slot root; all entries,
/// file bytes, permissions, and symlink targets are preserved below destinationURL.
FOUNDATION_EXPORT BOOL FlekDeckExtractROMArchive(NSURL *archiveURL,
                                                  NSURL *destinationURL,
                                                  NSError * _Nullable * _Nullable error);

NS_ASSUME_NONNULL_END

