#!/usr/bin/env python3
from pathlib import Path

# ARM32 must be inspected, but existing FlekDeck mutation callbacks were written
# for mach_header_64. Do not broaden LCParseMachO's mutation contract to ARM32.
# Instead, classify/encryption-check ARM32 with a separate read-only scanner.

header = Path("LiveContainer/LCMachOUtils.h")
h = header.read_text()
decl = "NSString *LCInspectMachOArchitectures(const char *path, bool *hasArm64, bool *hasArm32, bool *isEncrypted);\n"
anchor = "NSString *LCParseMachO(const char *path, bool readOnly, NS_NOESCAPE LCParseMachOCallback callback);\n"
if decl not in h:
    if anchor not in h:
        raise SystemExit(f"{header}: LCParseMachO declaration anchor missing")
    h = h.replace(anchor, anchor + decl, 1)
header.write_text(h)

macho = Path("LiveContainer/LCMachOUtils.m")
m = macho.read_text()

start = m.find("NSString *LCParseMachO(const char *path, bool readOnly, LCParseMachOCallback callback) {")
end = m.find("NSString *LCPatchMachOFixupARM64eSlice(const char *path) {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{macho}: LCParseMachO markers missing")

replacement = r'''static BOOL LCInspectSliceEncryption(void *slice, size_t sliceSize, BOOL *encryptedOut) {
    if (!slice || sliceSize < sizeof(struct mach_header)) return NO;
    uint32_t magic = *(uint32_t *)slice;
    size_t headerSize = 0;
    uint32_t ncmds = 0;
    uint32_t sizeofcmds = 0;
    if (magic == MH_MAGIC_64) {
        if (sliceSize < sizeof(struct mach_header_64)) return NO;
        struct mach_header_64 *h = (struct mach_header_64 *)slice;
        headerSize = sizeof(struct mach_header_64);
        ncmds = h->ncmds;
        sizeofcmds = h->sizeofcmds;
    } else if (magic == MH_MAGIC) {
        struct mach_header *h = (struct mach_header *)slice;
        headerSize = sizeof(struct mach_header);
        ncmds = h->ncmds;
        sizeofcmds = h->sizeofcmds;
    } else {
        return NO;
    }
    if ((uint64_t)headerSize + sizeofcmds > sliceSize) return NO;

    uint8_t *cursor = (uint8_t *)slice + headerSize;
    uint8_t *commandsEnd = cursor + sizeofcmds;
    for (uint32_t i = 0; i < ncmds; i++) {
        if ((size_t)(commandsEnd - cursor) < sizeof(struct load_command)) return NO;
        struct load_command *command = (struct load_command *)cursor;
        if (command->cmdsize < sizeof(struct load_command) || cursor + command->cmdsize > commandsEnd) return NO;
        if (command->cmd == LC_ENCRYPTION_INFO || command->cmd == LC_ENCRYPTION_INFO_64) {
            if (command->cmdsize < sizeof(struct encryption_info_command)) return NO;
            if (((struct encryption_info_command *)command)->cryptid != 0 && encryptedOut) *encryptedOut = YES;
        }
        cursor += command->cmdsize;
    }
    return YES;
}

NSString *LCInspectMachOArchitectures(const char *path, bool *hasArm64, bool *hasArm32, bool *isEncrypted) {
    if (hasArm64) *hasArm64 = false;
    if (hasArm32) *hasArm32 = false;
    if (isEncrypted) *isEncrypted = false;
    if (!path) return @"Invalid Mach-O path";

    int fd = open(path, O_RDONLY);
    if (fd < 0) return [NSString stringWithFormat:@"Failed to open %s: %s", path, strerror(errno)];
    struct stat s = {0};
    if (fstat(fd, &s) != 0 || s.st_size < (off_t)sizeof(uint32_t)) {
        NSString *error = [NSString stringWithFormat:@"Failed to inspect %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }
    void *map = mmap(NULL, (size_t)s.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    if (map == MAP_FAILED) {
        NSString *error = [NSString stringWithFormat:@"Failed to map %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }

    NSString *result = nil;
    BOOL encrypted = NO;
    uint32_t magic = *(uint32_t *)map;
    if (magic == FAT_CIGAM) {
        struct fat_header *fat = (struct fat_header *)map;
        uint32_t count = OSSwapInt32(fat->nfat_arch);
        size_t tableSize = sizeof(struct fat_header) + ((size_t)count * sizeof(struct fat_arch));
        if (count > 128 || tableSize > (size_t)s.st_size) {
            result = @"Malformed FAT Mach-O architecture table";
        } else {
            struct fat_arch *arch = (struct fat_arch *)((uint8_t *)map + sizeof(struct fat_header));
            for (uint32_t i = 0; i < count; i++, arch++) {
                cpu_type_t cpu = (cpu_type_t)OSSwapInt32(arch->cputype);
                uint32_t offset = OSSwapInt32(arch->offset);
                uint32_t size = OSSwapInt32(arch->size);
                if ((uint64_t)offset + size > (uint64_t)s.st_size || size < sizeof(struct mach_header)) {
                    result = @"Malformed FAT Mach-O slice";
                    break;
                }
                if (cpu != CPU_TYPE_ARM64 && cpu != CPU_TYPE_ARM) continue;
                if (cpu == CPU_TYPE_ARM64 && hasArm64) *hasArm64 = true;
                if (cpu == CPU_TYPE_ARM && hasArm32) *hasArm32 = true;
                if (!LCInspectSliceEncryption((uint8_t *)map + offset, size, &encrypted)) {
                    result = @"Malformed ARM Mach-O load commands";
                    break;
                }
            }
        }
    } else if (magic == MH_MAGIC_64) {
        struct mach_header_64 *mh = (struct mach_header_64 *)map;
        if (mh->cputype == CPU_TYPE_ARM64 && hasArm64) *hasArm64 = true;
        if (!LCInspectSliceEncryption(map, (size_t)s.st_size, &encrypted)) result = @"Malformed 64-bit Mach-O load commands";
    } else if (magic == MH_MAGIC) {
        struct mach_header *mh = (struct mach_header *)map;
        if (mh->cputype == CPU_TYPE_ARM && hasArm32) *hasArm32 = true;
        if (!LCInspectSliceEncryption(map, (size_t)s.st_size, &encrypted)) result = @"Malformed 32-bit Mach-O load commands";
    } else {
        result = @"Not a Mach-O file";
    }

    if (isEncrypted) *isEncrypted = encrypted;
    munmap(map, (size_t)s.st_size);
    close(fd);
    return result;
}

NSString *LCParseMachO(const char *path, bool readOnly, LCParseMachOCallback callback) {
    if (!path || !callback) return @"Invalid Mach-O parser arguments";
    int fd = open(path, readOnly ? O_RDONLY : O_RDWR, readOnly ? 0400 : 0600);
    if (fd < 0) return [NSString stringWithFormat:@"Failed to open %s: %s", path, strerror(errno)];

    struct stat s = {0};
    if (fstat(fd, &s) != 0) {
        NSString *error = [NSString stringWithFormat:@"Failed to stat %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }
    if (s.st_size < (off_t)sizeof(uint32_t)) { close(fd); return @"Mach-O file is too small"; }

    int protection = readOnly ? PROT_READ : (PROT_READ | PROT_WRITE);
    int flags = readOnly ? MAP_PRIVATE : MAP_SHARED;
    void *map = mmap(NULL, (size_t)s.st_size, protection, flags, fd, 0);
    if (map == MAP_FAILED) {
        NSString *error = [NSString stringWithFormat:@"Failed to map %s: %s", path, strerror(errno)];
        close(fd);
        return error;
    }

    NSString *result = nil;
    uint32_t magic = *(uint32_t *)map;
    if (magic == FAT_CIGAM) {
        struct fat_header *fat = (struct fat_header *)map;
        uint32_t count = OSSwapInt32(fat->nfat_arch);
        size_t tableSize = sizeof(struct fat_header) + ((size_t)count * sizeof(struct fat_arch));
        if (count > 128 || tableSize > (size_t)s.st_size) {
            result = @"Malformed FAT Mach-O architecture table";
        } else {
            struct fat_arch *arch = (struct fat_arch *)((uint8_t *)map + sizeof(struct fat_header));
            for (uint32_t i = 0; i < count; i++, arch++) {
                cpu_type_t cpu = (cpu_type_t)OSSwapInt32(arch->cputype);
                if (cpu != CPU_TYPE_ARM64) continue;
                uint32_t offset = OSSwapInt32(arch->offset);
                uint32_t size = OSSwapInt32(arch->size);
                if ((uint64_t)offset + size > (uint64_t)s.st_size || size < sizeof(struct mach_header_64)) {
                    result = @"Malformed ARM64 Mach-O slice";
                    break;
                }
                callback(path, (struct mach_header_64 *)((uint8_t *)map + offset), fd, map);
            }
        }
    } else if (magic == MH_MAGIC_64) {
        callback(path, (struct mach_header_64 *)map, fd, map);
    } else if (magic == MH_MAGIC) {
        // ARM32 is intentionally inspection-only. Existing mutation callbacks
        // assume mach_header_64 and must never receive a 32-bit header.
    } else {
        result = @"Not a Mach-O file";
    }

    if (!readOnly && result == nil) msync(map, (size_t)s.st_size, MS_SYNC);
    munmap(map, (size_t)s.st_size);
    close(fd);
    return result;
}

'''
m = m[:start] + replacement + m[end:]

# Fix the standalone helper too, so any direct caller is safe on a 32-bit header.
enc_start = m.find("bool LCIsMachOEncrypted(struct mach_header_64 *header) {")
enc_end = m.find("uint64_t LCFindSymbolOffset", enc_start)
if enc_start < 0 or enc_end < 0:
    raise SystemExit(f"{macho}: LCIsMachOEncrypted markers missing")
enc = r'''bool LCIsMachOEncrypted(struct mach_header_64 *header) {
    if (!header) return false;
    uint32_t magic = *(uint32_t *)header;
    size_t headerSize = magic == MH_MAGIC_64 ? sizeof(struct mach_header_64) :
                        magic == MH_MAGIC ? sizeof(struct mach_header) : 0;
    if (!headerSize) return false;
    uint32_t ncmds = magic == MH_MAGIC_64 ? header->ncmds : ((struct mach_header *)header)->ncmds;
    struct load_command *command = (struct load_command *)((uint8_t *)header + headerSize);
    for(uint32_t i = 0; i < ncmds; i++) {
        if(command->cmd == LC_ENCRYPTION_INFO || command->cmd == LC_ENCRYPTION_INFO_64) {
            return ((struct encryption_info_command *)command)->cryptid != 0;
        }
        if(command->cmdsize < sizeof(struct load_command)) return false;
        command = (struct load_command *)((uint8_t *)command + command->cmdsize);
    }
    return false;
}

'''
m = m[:enc_start] + enc + m[enc_end:]
macho.write_text(m)

# App classification uses the inspection API. LCParseMachO then patches only the
# ARM64 slice; a genuine ARM32-only guest remains byte-for-byte untouched for
# LiveExec32.
app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
a = app_info.read_text()
old = '''        __block bool has64bitSlice = NO;
        __block bool isEncrypted = false;
        NSString *error = LCParseMachO(execPath.UTF8String, false, ^(const char *path, struct mach_header_64 *header, int fd, void* filePtr) {
            if(header->cputype == CPU_TYPE_ARM64) {
                has64bitSlice |= YES;
                int patchResult = LCPatchExecSlice(path, header, ![self dontInjectTweakLoader]);
                if(patchResult & PATCH_EXEC_RESULT_NO_SPACE_FOR_TWEAKLOADER) {
                    info[@"LCTweakLoaderCantInject"] = @YES;
                    info[@"dontInjectTweakLoader"] = @YES;
                }
                if(patchResult & PATCH_EXEC_RESULT_SEG_COUNT_MISMATCH) {
                    info[@"segCountMismatch"] = @YES;
                }
            }
            isEncrypted |= LCIsMachOEncrypted(header);
        });
        is32bit = !has64bitSlice;'''
new = '''        bool has64bitSlice = false;
        bool has32bitSlice = false;
        bool isEncrypted = false;
        NSString *error = LCInspectMachOArchitectures(execPath.UTF8String, &has64bitSlice, &has32bitSlice, &isEncrypted);
        if(!error && !has64bitSlice && !has32bitSlice) {
            error = @"The app executable has no supported ARM slice.";
        }
        if(!error && has64bitSlice) {
            error = LCParseMachO(execPath.UTF8String, false, ^(const char *path, struct mach_header_64 *header, int fd, void* filePtr) {
                int patchResult = LCPatchExecSlice(path, header, ![self dontInjectTweakLoader]);
                if(patchResult & PATCH_EXEC_RESULT_NO_SPACE_FOR_TWEAKLOADER) {
                    info[@"LCTweakLoaderCantInject"] = @YES;
                    info[@"dontInjectTweakLoader"] = @YES;
                }
                if(patchResult & PATCH_EXEC_RESULT_SEG_COUNT_MISMATCH) {
                    info[@"segCountMismatch"] = @YES;
                }
            });
        }
        is32bit = !has64bitSlice && has32bitSlice;'''
if old not in a:
    if new not in a:
        raise SystemExit(f"{app_info}: ARM32 classification callback anchor missing")
else:
    a = a.replace(old, new, 1)
app_info.write_text(a)

# Contract invariants.
if "cpu != CPU_TYPE_ARM64) continue" not in macho.read_text():
    raise SystemExit(f"{macho}: mutation parser still exposes non-ARM64 slices")
if "LCInspectMachOArchitectures" not in header.read_text() or "LCInspectMachOArchitectures" not in app_info.read_text():
    raise SystemExit("ARM architecture inspection API is not wired end-to-end")
if "is32bit = !has64bitSlice && has32bitSlice" not in app_info.read_text():
    raise SystemExit(f"{app_info}: ARM32-only classification is not explicit")

print("FlekDeck Mach-O contract repaired: ARM32 inspection separated from ARM64 mutation")
