#import <Foundation/Foundation.h>
#import "../LiveContainerSwiftUI/Views/Bootloader/FlekROMArchive.h"
#include "../LiveContainerSwiftUI/Utilities/archive.h"
#include "../LiveContainerSwiftUI/Utilities/archive_entry.h"

static void Require(BOOL condition, NSString *message)
{
    if (!condition) {
        fprintf(stderr, "%s\n", message.UTF8String);
        exit(1);
    }
}

static void MakeZIP(NSURL *url, NSArray<NSDictionary *> *members)
{
    struct archive *writer = archive_write_new();
    Require(writer != NULL, @"Allocate ZIP writer");
    Require(archive_write_set_format_zip(writer) == ARCHIVE_OK, @"ZIP format");
    Require(archive_write_open_filename(writer, url.path.fileSystemRepresentation) == ARCHIVE_OK, @"Open ZIP");
    for (NSDictionary *member in members) {
        struct archive_entry *entry = archive_entry_new();
        NSString *path = member[@"path"];
        NSString *target = member[@"link"];
        NSData *data = [member[@"data"] dataUsingEncoding:NSUTF8StringEncoding];
        archive_entry_set_pathname(entry, path.fileSystemRepresentation);
        archive_entry_set_filetype(entry, target ? AE_IFLNK : (data ? AE_IFREG : AE_IFDIR));
        archive_entry_set_perm(entry, data ? 0644 : 0755);
        archive_entry_set_size(entry, data.length);
        if (target) archive_entry_set_symlink(entry, target.fileSystemRepresentation);
        Require(archive_write_header(writer, entry) == ARCHIVE_OK, @"Write ZIP header");
        if (data) Require(archive_write_data(writer, data.bytes, data.length) == (la_ssize_t)data.length, @"Write ZIP data");
        archive_entry_free(entry);
    }
    Require(archive_write_close(writer) == ARCHIVE_OK, @"Close ZIP");
    archive_write_free(writer);
}

int main(void)
{
    @autoreleasepool {
        NSFileManager *fm = NSFileManager.defaultManager;
        NSURL *temporary = [NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES];
        NSURL *testRoot = [temporary URLByAppendingPathComponent:[@"flek-rom-test-" stringByAppendingString:NSUUID.UUID.UUIDString] isDirectory:YES];
        NSURL *physical = [testRoot URLByAppendingPathComponent:@"physical" isDirectory:YES];
        NSURL *alias = [testRoot URLByAppendingPathComponent:@"alias" isDirectory:YES];
        Require([fm createDirectoryAtURL:physical withIntermediateDirectories:YES attributes:nil error:nil], @"Create fixture root");
        Require([fm createSymbolicLinkAtPath:alias.path withDestinationPath:@"physical" error:nil], @"Create iOS-style ancestor alias");
        NSURL *slot = [alias URLByAppendingPathComponent:@"Slot/.A.installing" isDirectory:YES];
        Require([fm createDirectoryAtURL:slot withIntermediateDirectories:YES attributes:nil error:nil], @"Create staged slot");
        NSURL *zip = [testRoot URLByAppendingPathComponent:@"rom.zip"];
        MakeZIP(zip, @[
            @{@"path": @"ROM/"},
            @{@"path": @"ROM/manifest.plist", @"data": @"manifest fixture"},
            @{@"path": @"ROM/bin/"},
            @{@"path": @"ROM/bin/tool", @"data": @"executable fixture"},
            @{@"path": @"ROM/bin/tool-link", @"link": @"tool"}
        ]);
        NSData *original = [NSData dataWithContentsOfURL:zip];
        NSError *error = nil;
        Require(FlekDeckExtractROMArchive(zip, slot, &error), [NSString stringWithFormat:@"Ancestor symlink extraction failed: %@", error]);
        Require([[NSString stringWithContentsOfURL:[slot URLByAppendingPathComponent:@"manifest.plist"] encoding:NSUTF8StringEncoding error:nil] isEqualToString:@"manifest fixture"], @"Manifest contents");
        Require([[fm destinationOfSymbolicLinkAtPath:[slot URLByAppendingPathComponent:@"bin/tool-link"].path error:nil] isEqualToString:@"tool"], @"Preserve safe ROM symlink");
        Require([original isEqualToData:[NSData dataWithContentsOfURL:zip]], @"ZIP was modified");
        Require([fm removeItemAtURL:slot error:nil], @"Reset staged slot");
        Require([fm createDirectoryAtURL:slot withIntermediateDirectories:YES attributes:nil error:nil], @"Recreate staged slot");
        // A link target can stay inside the slot, but extracting a subsequent
        // member through that link must still be forbidden by libarchive.
        MakeZIP(zip, @[
            @{@"path": @"ROM/"},
            @{@"path": @"ROM/real/"},
            @{@"path": @"ROM/link", @"link": @"real"},
            @{@"path": @"ROM/link/injected", @"data": @"must not be written"}
        ]);
        error = nil;
        Require(!FlekDeckExtractROMArchive(zip, slot, &error), @"Extraction through ROM symlink was accepted");
        Require(![fm fileExistsAtPath:[slot URLByAppendingPathComponent:@"real/injected"].path], @"Symlink traversal wrote a file");
        Require([fm removeItemAtURL:testRoot error:nil], @"Remove fixture");
        puts("ROM archive ancestor-alias regression and member-symlink protection passed.");
    }
    return 0;
}
