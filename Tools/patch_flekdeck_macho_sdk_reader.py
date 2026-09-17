#!/usr/bin/env python3
from pathlib import Path

header = Path("LiveContainer/LCMachOUtils.h")
h = header.read_text()
arch_decl = "NSString *LCInspectMachOArchitectures(const char *path, bool *hasArm64, bool *hasArm32, bool *isEncrypted);\n"
sdk_decl = "NSString *LCReadMachOSDKVersion(const char *path, bool preferArm32, uint32_t *sdkVersion);\n"
if sdk_decl not in h:
    if arch_decl not in h:
        raise SystemExit(f"{header}: architecture inspection declaration missing")
    h = h.replace(arch_decl, arch_decl + sdk_decl, 1)
header.write_text(h)

macho = Path("LiveContainer/LCMachOUtils.m")
m = macho.read_text()
anchor = "NSString *LCParseMachO(const char *path, bool readOnly, LCParseMachOCallback callback) {\n"
if "NSString *LCReadMachOSDKVersion(" not in m:
    if anchor not in m:
        raise SystemExit(f"{macho}: LCParseMachO anchor missing")
    helper = r'''static BOOL LCReadSliceSDKVersion(void *slice, size_t sliceSize, uint32_t *sdkOut) {
    if (!slice || !sdkOut || sliceSize < sizeof(struct mach_header)) return NO;
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
    uint8_t *end = cursor + sizeofcmds;
    uint32_t found = 0;
    for (uint32_t i = 0; i < ncmds; i++) {
        if ((size_t)(end - cursor) < sizeof(struct load_command)) return NO;
        struct load_command *command = (struct load_command *)cursor;
        if (command->cmdsize < sizeof(struct load_command) || cursor + command->cmdsize > end) return NO;
        if (command->cmd == LC_BUILD_VERSION && command->cmdsize >= sizeof(struct build_version_command)) {
            struct build_version_command *build = (struct build_version_command *)command;
            if (build->platform == PLATFORM_IOS || build->platform == PLATFORM_IOSSIMULATOR) {
                found = build->sdk;
            }
        } else if (command->cmd == LC_VERSION_MIN_IPHONEOS && command->cmdsize >= sizeof(struct version_min_command)) {
            struct version_min_command *minimum = (struct version_min_command *)command;
            if (!found) found = minimum->sdk;
        }
        cursor += command->cmdsize;
    }
    *sdkOut = found;
    return YES;
}

NSString *LCReadMachOSDKVersion(const char *path, bool preferArm32, uint32_t *sdkVersion) {
    if (sdkVersion) *sdkVersion = 0;
    if (!path || !sdkVersion) return @"Invalid SDK reader arguments";

    int fd = open(path, O_RDONLY);
    if (fd < 0) return [NSString stringWithFormat:@"Failed to open %s: %s", path, strerror(errno)];
    struct stat s = {0};
    if (fstat(fd, &s) != 0 || s.st_size < (off_t)sizeof(uint32_t)) {
        NSString *error = [NSString stringWithFormat:@"Failed to inspect SDK for %s: %s", path, strerror(errno)];
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
    BOOL foundTarget = NO;
    cpu_type_t target = preferArm32 ? CPU_TYPE_ARM : CPU_TYPE_ARM64;
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
                if ((cpu_type_t)OSSwapInt32(arch->cputype) != target) continue;
                uint32_t offset = OSSwapInt32(arch->offset);
                uint32_t size = OSSwapInt32(arch->size);
                if ((uint64_t)offset + size > (uint64_t)s.st_size || size < sizeof(struct mach_header)) {
                    result = @"Malformed target Mach-O slice";
                    break;
                }
                foundTarget = YES;
                if (!LCReadSliceSDKVersion((uint8_t *)map + offset, size, sdkVersion)) {
                    result = @"Malformed target Mach-O load commands";
                }
                break;
            }
        }
    } else if (magic == MH_MAGIC_64 || magic == MH_MAGIC) {
        cpu_type_t cpu = magic == MH_MAGIC_64
            ? ((struct mach_header_64 *)map)->cputype
            : ((struct mach_header *)map)->cputype;
        if (cpu == target) {
            foundTarget = YES;
            if (!LCReadSliceSDKVersion(map, (size_t)s.st_size, sdkVersion)) {
                result = @"Malformed Mach-O load commands";
            }
        }
    } else {
        result = @"Not a Mach-O file";
    }
    if (!result && !foundTarget) result = @"Requested ARM slice was not found";

    munmap(map, (size_t)s.st_size);
    close(fd);
    return result;
}

'''
    m = m.replace(anchor, helper + anchor, 1)
macho.write_text(m)

app_info = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
a = app_info.read_text()
old = '''        __block uint32_t sdkVersion = 0;
        LCParseMachO(execPath.UTF8String, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
            sdkVersion = dyld_get_sdk_version((const struct mach_header *)header);
        });
#if is32BitSupported
        // Keep the same compatibility floor as the proven LiveExec32 integration.
        uint32_t minSDK = self.is32bit ? 0x20000 : 0xb0000;'''
new = '''        uint32_t sdkVersion = 0;
#if is32BitSupported
        NSString *sdkReadError = LCReadMachOSDKVersion(execPath.UTF8String, self.is32bit, &sdkVersion);
#else
        NSString *sdkReadError = LCReadMachOSDKVersion(execPath.UTF8String, false, &sdkVersion);
#endif
        if(sdkReadError) {
            NSLog(@"[LC] failed to read linked SDK for %@: %@", execPath, sdkReadError);
        }
#if is32BitSupported
        // Keep the same compatibility floor as the proven LiveExec32 integration,
        // but preserve a real ARM32 SDK when it is newer than that floor.
        uint32_t minSDK = self.is32bit ? 0x20000 : 0xb0000;'''
if new not in a:
    if old not in a:
        raise SystemExit(f"{app_info}: spoof SDK parser anchor missing")
    a = a.replace(old, new, 1)
app_info.write_text(a)

if "LCReadMachOSDKVersion" not in header.read_text() or "LCReadSliceSDKVersion" not in macho.read_text():
    raise SystemExit("Architecture-aware SDK reader was not installed")
if "LCReadMachOSDKVersion(execPath.UTF8String, self.is32bit, &sdkVersion)" not in app_info.read_text():
    raise SystemExit("ARM32 spoof SDK path is not using the architecture-aware reader")

print("FlekDeck reads the real linked SDK from ARM32 without exposing it to mutation callbacks")
