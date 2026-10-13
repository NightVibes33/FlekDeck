/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 Adapted for FlekDeck from Nyxian's ZIP installation flow.
 The selected archive is never rewritten; extraction is confined to a staged slot.
*/

#import "FlekROMArchive.h"
#include "../../Utilities/archive.h"
#include "../../Utilities/archive_entry.h"
#include <sys/stat.h>
#include <stdint.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

static NSString * const FlekROMArchiveErrorDomain = @"com.fs.flekdeck.bootloader.archive";
static const uint64_t FlekROMArchiveMaximumExpandedBytes = 8ull * 1024ull * 1024ull * 1024ull;
static const uint64_t FlekROMArchiveMaximumEntries = 200000;

static NSError *FlekROMArchiveError(struct archive *archive, NSInteger code, NSString *fallback)
{
    const char *message = archive ? archive_error_string(archive) : NULL;
    NSString *detail = message ? [NSString stringWithUTF8String:message] : nil;
    return [NSError errorWithDomain:FlekROMArchiveErrorDomain
                               code:code
                           userInfo:@{ NSLocalizedDescriptionKey:
                                          detail.length ? [NSString stringWithFormat:@"%@: %@", fallback, detail] : fallback }];
}

static NSString * _Nullable FlekROMArchiveMemberPath(const char *rawPath, NSError **error)
{
    if (!rawPath) {
        if (error) *error = FlekROMArchiveError(NULL, 1, @"Archive entry has no pathname.");
        return nil;
    }

    NSString *path = [NSString stringWithUTF8String:rawPath];
    if (!path.length || [path hasPrefix:@"/"] || [path containsString:@"\\"]) {
        if (error) *error = FlekROMArchiveError(NULL, 2, @"Archive contains an absolute or invalid pathname.");
        return nil;
    }

    while ([path hasSuffix:@"/"] && path.length > 1) {
        path = [path substringToIndex:path.length - 1];
    }
    if ([path isEqualToString:@"ROM"]) return @"";
    if (![path hasPrefix:@"ROM/"]) {
        if (error) *error = FlekROMArchiveError(NULL, 3, @"ZIP entries must be contained in its top-level ROM/ directory.");
        return nil;
    }

    NSString *relative = [path substringFromIndex:4];
    NSArray<NSString *> *components = [relative componentsSeparatedByString:@"/"];
    for (NSString *component in components) {
        if (!component.length || [component isEqualToString:@"."] || [component isEqualToString:@".."]) {
            if (error) *error = FlekROMArchiveError(NULL, 4, @"Archive contains a path traversal component.");
            return nil;
        }
    }
    if (relative.length > 4096) {
        if (error) *error = FlekROMArchiveError(NULL, 5, @"Archive pathname is too long.");
        return nil;
    }
    return relative;
}

static BOOL FlekROMArchiveSymlinkStaysInsideRoot(NSString *memberPath, const char *rawTarget)
{
    if (!rawTarget) return NO;
    NSString *target = [NSString stringWithUTF8String:rawTarget];
    if (!target.length || [target hasPrefix:@"/"]) return NO;

    NSMutableArray<NSString *> *resolved = [[memberPath.stringByDeletingLastPathComponent
                                              componentsSeparatedByString:@"/"] mutableCopy];
    if (resolved.count == 1 && resolved.firstObject.length == 0) {
        [resolved removeAllObjects];
    }

    for (NSString *component in [target componentsSeparatedByString:@"/"]) {
        if (!component.length || [component isEqualToString:@"."]) continue;
        if ([component isEqualToString:@".."]) {
            if (!resolved.count) return NO;
            [resolved removeLastObject];
        } else {
            [resolved addObject:component];
        }
    }
    return YES;
}

static BOOL FlekROMArchiveReadEntryData(struct archive *reader,
                                        struct archive *writer,
                                        uint64_t *expandedBytes,
                                        NSError **error)
{
    const void *buffer = NULL;
    size_t size = 0;
    la_int64_t offset = 0;
    int result = 0;
    while ((result = archive_read_data_block(reader, &buffer, &size, &offset)) == ARCHIVE_OK) {
        if (offset < 0) {
            if (error) *error = FlekROMArchiveError(reader, 6, @"Archive entry has a negative data offset.");
            return NO;
        }
        uint64_t blockOffset = (uint64_t)offset;
        uint64_t blockSize = (uint64_t)size;
        if (blockOffset > FlekROMArchiveMaximumExpandedBytes ||
            blockSize > FlekROMArchiveMaximumExpandedBytes - blockOffset ||
            blockSize > FlekROMArchiveMaximumExpandedBytes - *expandedBytes) {
            if (error) *error = FlekROMArchiveError(reader, 16, @"ZIP expands beyond FlekDeck's safe import limit.");
            return NO;
        }
        *expandedBytes += blockSize;
        int writeResult = archive_write_data_block(writer, buffer, size, offset);
        if (writeResult < ARCHIVE_WARN) {
            if (error) *error = FlekROMArchiveError(writer, 7, @"Could not write an extracted archive entry.");
            return NO;
        }
    }
    if (result != ARCHIVE_EOF) {
        if (error) *error = FlekROMArchiveError(reader, 8, @"Could not read an archive entry.");
        return NO;
    }
    return YES;
}

BOOL FlekDeckExtractROMArchive(NSURL *archiveURL, NSURL *destinationURL, NSError **error)
{
    NSError *failure = nil;
    struct archive *reader = archive_read_new();
    struct archive *writer = NULL;
    NSString *rootPath = nil;
    NSMutableSet<NSString *> *seenPaths = [NSMutableSet set];
    BOOL success = NO;

    // iOS exposes /var through a symlink to /private/var. Foundation path
    // standardization may turn a resolved path back into /var, which the disk
    // writer correctly rejects with SECURE_SYMLINKS. Resolve the existing staged
    // directory with realpath and preserve those exact bytes for every member.
    char *resolvedRoot = realpath(destinationURL.path.fileSystemRepresentation, NULL);
    if (!resolvedRoot) {
        failure = FlekROMArchiveError(NULL, 25,
            [NSString stringWithFormat:@"Could not resolve the ROM staging directory: %s.", strerror(errno)]);
        goto cleanup;
    }
    rootPath = [[NSFileManager defaultManager] stringWithFileSystemRepresentation:resolvedRoot
                                                                         length:strlen(resolvedRoot)];
    free(resolvedRoot);
    struct stat rootStat;
    if (!rootPath.length || lstat(rootPath.fileSystemRepresentation, &rootStat) != 0 ||
        !S_ISDIR(rootStat.st_mode)) {
        failure = FlekROMArchiveError(NULL, 26, @"ROM staging destination is not an existing directory.");
        goto cleanup;
    }

    if (!reader) {
        failure = FlekROMArchiveError(NULL, 9, @"Could not allocate ZIP reader.");
        goto cleanup;
    }

    archive_read_support_filter_all(reader);
    archive_read_support_format_zip(reader);
    int result = archive_read_open_filename(reader, archiveURL.path.fileSystemRepresentation, 65536);
    if (result != ARCHIVE_OK) {
        failure = FlekROMArchiveError(reader, 10, @"Could not open the selected ZIP.");
        goto cleanup;
    }

    writer = archive_write_disk_new();
    if (!writer) {
        failure = FlekROMArchiveError(NULL, 11, @"Could not allocate safe archive extractor.");
        goto cleanup;
    }
    int extractFlags = ARCHIVE_EXTRACT_TIME |
                       ARCHIVE_EXTRACT_PERM |
                       ARCHIVE_EXTRACT_ACL |
                       ARCHIVE_EXTRACT_FFLAGS |
                       ARCHIVE_EXTRACT_SECURE_NODOTDOT |
                       ARCHIVE_EXTRACT_SECURE_SYMLINKS;
    result = archive_write_disk_set_options(writer, extractFlags);
    if (result < ARCHIVE_WARN) {
        failure = FlekROMArchiveError(writer, 12, @"Could not enable safe ZIP extraction.");
        goto cleanup;
    }
    archive_write_disk_set_standard_lookup(writer);

    uint64_t entryCount = 0;
    uint64_t expandedBytes = 0;
    BOOL foundROMRoot = NO;
    struct archive_entry *entry = NULL;
    while ((result = archive_read_next_header(reader, &entry)) != ARCHIVE_EOF) {
        if (result < ARCHIVE_WARN) {
            failure = FlekROMArchiveError(reader, 13, @"Could not read ZIP directory.");
            break;
        }
        if (++entryCount > FlekROMArchiveMaximumEntries) {
            failure = FlekROMArchiveError(reader, 14, @"ZIP contains too many entries.");
            break;
        }

        const char *rawPath = archive_entry_pathname(entry);
        NSString *relativePath = FlekROMArchiveMemberPath(rawPath, &failure);
        if (!relativePath) break;
        if (!relativePath.length) {
            foundROMRoot = YES;
            continue;
        }
        // The app container is normally case-insensitive. Normalize and fold
        // archive names so colliding entries cannot replace one another there.
        NSString *collisionKey = relativePath.precomposedStringWithCanonicalMapping.lowercaseString;
        if ([seenPaths containsObject:collisionKey]) {
            failure = FlekROMArchiveError(reader, 15, [NSString stringWithFormat:@"ZIP contains duplicate path %@.", relativePath]);
            break;
        }
        [seenPaths addObject:collisionKey];

        mode_t fileType = archive_entry_filetype(entry);
        la_int64_t declaredSize = archive_entry_size(entry);
        if (declaredSize > 0) {
            uint64_t fileSize = (uint64_t)declaredSize;
            if (fileType == AE_IFREG && fileSize > FlekROMArchiveMaximumExpandedBytes - expandedBytes) {
                failure = FlekROMArchiveError(reader, 16, @"ZIP expands beyond FlekDeck's safe import limit.");
                break;
            }
        }

        const char *rawSymlink = archive_entry_symlink(entry);
        const char *rawHardlink = archive_entry_hardlink(entry);
        if (rawSymlink && !FlekROMArchiveSymlinkStaysInsideRoot(relativePath, rawSymlink)) {
            failure = FlekROMArchiveError(reader, 17, [NSString stringWithFormat:@"Symlink escapes the ROM slot: %@.", relativePath]);
            break;
        }
        if (rawHardlink) {
            NSString *hardlinkPath = FlekROMArchiveMemberPath(rawHardlink, &failure);
            if (!hardlinkPath.length) {
                if (!failure) failure = FlekROMArchiveError(reader, 18, @"Hard link points outside the ROM slot.");
                break;
            }
            NSString *hardlinkDestination = [rootPath stringByAppendingFormat:@"/%@", hardlinkPath];
            archive_entry_set_hardlink(entry, hardlinkDestination.fileSystemRepresentation);
        }
        if (fileType != AE_IFREG && fileType != AE_IFDIR && fileType != AE_IFLNK) {
            failure = FlekROMArchiveError(reader, 19, [NSString stringWithFormat:@"Unsupported special file in ZIP: %@.", relativePath]);
            break;
        }

        // Member components were validated above; do not standardize the
        // canonical root back into an iOS symlink alias here.
        NSString *outputPath = [rootPath stringByAppendingFormat:@"/%@", relativePath];
        archive_entry_set_pathname(entry, outputPath.fileSystemRepresentation);
        result = archive_write_header(writer, entry);
        if (result < ARCHIVE_WARN) {
            failure = FlekROMArchiveError(writer, 20, [NSString stringWithFormat:@"Could not create %@.", relativePath]);
            break;
        }
        if (fileType == AE_IFREG &&
            !FlekROMArchiveReadEntryData(reader, writer, &expandedBytes, &failure)) {
            break;
        }
        result = archive_write_finish_entry(writer);
        if (result < ARCHIVE_WARN) {
            failure = FlekROMArchiveError(writer, 21, [NSString stringWithFormat:@"Could not finish %@.", relativePath]);
            break;
        }
    }

    if (!failure && result != ARCHIVE_EOF) {
        failure = FlekROMArchiveError(reader, 22, @"ZIP extraction stopped before end of archive.");
    }
    if (!failure && (!foundROMRoot || !seenPaths.count)) {
        failure = FlekROMArchiveError(reader, 23, @"ZIP does not contain a ROM/ payload.");
    }
    success = failure == nil;

cleanup:
    if (writer) {
        archive_write_close(writer);
        archive_write_free(writer);
    }
    if (reader) {
        archive_read_close(reader);
        archive_read_free(reader);
    }
    if (!success && error) {
        *error = failure ?: FlekROMArchiveError(NULL, 24, @"ZIP extraction failed.");
    }
    return success;
}

