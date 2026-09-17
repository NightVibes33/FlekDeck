@import Darwin;
@import Foundation;
@import MachO;
#import "../litehook/src/litehook.h"
#import "LCUtils.h"
#include "dyld_cache_format.h"

static uint32_t rnd32(uint32_t v, uint32_t r) {
    r--;
    return (v + r) & ~r;
}

struct dyld_all_image_infos *_alt_dyld_get_all_image_infos(void) {
    static struct dyld_all_image_infos *result;
    if (result) {
        return result;
    }
    struct task_dyld_info dyld_info;
    mach_vm_address_t image_infos;
    mach_msg_type_number_t count = TASK_DYLD_INFO_COUNT;
    kern_return_t ret;
    ret = task_info(mach_task_self_,
                    TASK_DYLD_INFO,
                    (task_info_t)&dyld_info,
                    &count);
    if (ret != KERN_SUCCESS) {
        return NULL;
    }
    image_infos = dyld_info.all_image_info_addr;
    result = (struct dyld_all_image_infos *)image_infos;
    return result;
}

static uint32_t get_chained_fixups_seg_count(void *macho, struct linkedit_data_command *fixups) {
    printf("[*] Found DYLD_CHAINED_FIXUPS!\n");
    
    if (fixups->dataoff == 0 || fixups->datasize < sizeof(struct dyld_chained_fixups_header)) {
        printf("\t\t[!] Invalid chained fixups payload\n");
        return 0;
    }
    
    off_t fixups_offset = fixups->dataoff;
    struct dyld_chained_fixups_header *header = (struct dyld_chained_fixups_header *)(macho+fixups_offset);
    
    if (header->starts_offset == 0 || header->starts_offset + sizeof(struct dyld_chained_starts_in_image) > fixups->datasize) {
        printf("\t\t[!] No chained starts to patch\n");

        return 0;
    }
    
    off_t starts_offset = fixups_offset + header->starts_offset;
    uint32_t *seg_count = (uint32_t *)(macho+starts_offset);

    return *seg_count;
}


static void insertDylibCommand(uint32_t cmd, const char *path, struct mach_header_64 *header) {
    const char *name = cmd==LC_ID_DYLIB ? basename((char *)path) : path;
    struct dylib_command *dylib;
    size_t cmdsize = sizeof(struct dylib_command) + rnd32((uint32_t)strlen(name) + 1, 8);
    if (cmd == LC_ID_DYLIB) {
        // Make this the first load command on the list (like dylibify does), or some UE3 games may break
        dylib = (struct dylib_command *)(sizeof(struct mach_header_64) + (uintptr_t)header);
        memmove((void *)((uintptr_t)dylib + cmdsize), (void *)dylib, header->sizeofcmds);
        bzero(dylib, cmdsize);
    } else {
        dylib = (struct dylib_command *)(sizeof(struct mach_header_64) + (void *)header+header->sizeofcmds);
    }
    dylib->cmd = cmd;
    dylib->cmdsize = cmdsize;
    dylib->dylib.name.offset = sizeof(struct dylib_command);
    dylib->dylib.compatibility_version = 0x10000;
    dylib->dylib.current_version = 0x10000;
    dylib->dylib.timestamp = 2;
    strncpy((void *)dylib + dylib->dylib.name.offset, name, strlen(name));
    header->ncmds++;
    header->sizeofcmds += dylib->cmdsize;
}

static void replaceDylinkerWithIDDylibCommand(struct dylinker_command* dylinkerCommand, const char *path) {
    uint32_t size = dylinkerCommand->cmdsize;
    struct dylib_command* newDylibCommand = (struct dylib_command*)dylinkerCommand;
    newDylibCommand->cmd = LC_ID_DYLIB;

    newDylibCommand->dylib.name.offset = sizeof(struct dylib_command);
    newDylibCommand->dylib.compatibility_version = 0x10000;
    newDylibCommand->dylib.current_version = 0x10000;
    newDylibCommand->dylib.timestamp = 2;
    uint32_t nameSize = size - sizeof(struct dylib_command);
    // we only have 8 bytes to use
    const char* name = basename((char *)path);
    strncpy((void *)newDylibCommand + newDylibCommand->dylib.name.offset, name, nameSize);
    *((char *)newDylibCommand + newDylibCommand->dylib.name.offset + nameSize - 1) = 0;
}

static void insertRPathCommand(const char *path, struct mach_header_64 *header) {
    struct rpath_command *rpath = (struct rpath_command *)(sizeof(struct mach_header_64) + (void *)header+header->sizeofcmds);
    rpath->cmd = LC_RPATH;
    rpath->cmdsize = sizeof(struct rpath_command) + rnd32((uint32_t)strlen(path) + 1, 8);
    rpath->path.offset = sizeof(struct rpath_command);
    strncpy((void *)rpath + rpath->path.offset, path, strlen(path));
    header->ncmds++;
    header->sizeofcmds += rpath->cmdsize;
}

void LCPatchAddRPath(const char *path, struct mach_header_64 *header) {
    insertRPathCommand("@executable_path/../../Tweaks", header);
    insertRPathCommand("@loader_path", header);
}

int LCPatchExecSlice(const char *path, struct mach_header_64 *header, bool doInject) {
    uint8_t *imageHeaderPtr = (uint8_t*)header + sizeof(struct mach_header_64);
    int ans = 0;
    // Literally convert an executable to a dylib
    if (header->magic == MH_MAGIC_64) {
        //assert(header->flags & MH_PIE);
        header->filetype = MH_DYLIB;
        header->flags |= MH_NO_REEXPORTED_DYLIBS;
        header->flags &= ~MH_PIE;
    }

    // Patch __PAGEZERO to map just a single zero page, fixing "out of address space"
    struct segment_command_64 *seg = (struct segment_command_64 *)imageHeaderPtr;
    assert(seg->cmd == LC_SEGMENT_64 || seg->cmd == LC_ID_DYLIB);
    if (seg->cmd == LC_SEGMENT_64 && seg->vmaddr == 0) {
        seg->vmaddr = 0x100000000 - 0x4000;
        seg->vmsize = 0x4000;
    }

    BOOL hasDylibCommand = NO;
    struct dylib_command * dylibLoaderCommand = 0;
    const char *tweakLoaderPath = "@loader_path/../../Tweaks/TweakLoader.dylib";
    const char *libCppPath = "/usr/lib/libc++.1.dylib";
    int textSectionOffest = 0;
    struct load_command *command = (struct load_command *)imageHeaderPtr;
    struct dylinker_command* dylinkerCommand = 0;
    bool codeSignatureCommandFound = false;
    uint32_t loadCommandSegCount = 0;
    for(int i = 0; i < header->ncmds; i++) {
        if(command->cmd == LC_ID_DYLIB) {
            hasDylibCommand = YES;
        } else if(command->cmd == LC_LOAD_DYLIB) {
            struct dylib_command *dylib = (struct dylib_command *)command;
            char *dylibName = (void *)dylib + dylib->dylib.name.offset;
            if (!strncmp(dylibName, tweakLoaderPath, strlen(tweakLoaderPath))) {
                dylibLoaderCommand = dylib;
            }
        } else if(command->cmd == 0x114514) {
            dylibLoaderCommand = (struct dylib_command *)command;
        } else if(command->cmd == LC_SEGMENT_64) {
            struct segment_command_64* seglc = (struct segment_command_64*)command;
            loadCommandSegCount++;
            if (strcmp("__TEXT", seglc->segname) == 0) {
                for (uint32_t j = 0; j < seglc->nsects; j++) {
                    struct section_64* sect = (struct section_64*)(((void*)command + sizeof(struct segment_command_64) + sizeof(struct section_64) * j));
                    if (0 == strcmp("__text", sect->sectname)) {
                        textSectionOffest = sect->offset;
                    }
                }
            }
        } else if (command->cmd == LC_CODE_SIGNATURE) {
            codeSignatureCommandFound = true;
        } else if (command->cmd == LC_LOAD_DYLINKER) {
            dylinkerCommand = (struct dylinker_command*)command;
        } else if (command->cmd == LC_DYLD_CHAINED_FIXUPS) {
            if(loadCommandSegCount != get_chained_fixups_seg_count((void*)header, (struct linkedit_data_command *)command)) {
                ans |= PATCH_EXEC_RESULT_SEG_COUNT_MISMATCH;
            }
        }
        
        command = (struct load_command *)((void *)command + command->cmdsize);
    }
    long freeLoadCommandCountLeft = (void*)header + textSectionOffest - (void*)command;
    int tweakLoaderLoadDylibCmdSize = 0x48;
    
    // Insert command priority: LC_CODE_SIGNATURE > LC_ID_DYLIB > LC_LOAD_DYLIB
    if(!codeSignatureCommandFound) {
        freeLoadCommandCountLeft -= 0x10;
    }
    
    int idDylibCommandSize = sizeof(struct dylib_command) + rnd32((uint32_t)strlen(basename((char*)path)) + 1, 8);
    if(!hasDylibCommand) {
        if (freeLoadCommandCountLeft >= idDylibCommandSize) {
            freeLoadCommandCountLeft -= idDylibCommandSize;
            insertDylibCommand(LC_ID_DYLIB, path, header);
        } else if (dylinkerCommand) {
            // #1042 fix: if there's not enough space for LC_ID_DYLIB we resue LC_LOAD_DYLINKER's space for LC_ID_DYLIB
            replaceDylinkerWithIDDylibCommand(dylinkerCommand, path);
        }
    }

    if (dylibLoaderCommand) {
        dylibLoaderCommand->cmd = doInject ? LC_LOAD_DYLIB : 0x114514;
        strcpy((void *)dylibLoaderCommand + dylibLoaderCommand->dylib.name.offset, doInject ? tweakLoaderPath : libCppPath);
    } else  {
        if (freeLoadCommandCountLeft >= tweakLoaderLoadDylibCmdSize) {
            freeLoadCommandCountLeft -= tweakLoaderLoadDylibCmdSize;
            insertDylibCommand(doInject ? LC_LOAD_DYLIB : 0x114514, doInject ? tweakLoaderPath : libCppPath, header);
        } else {
            // Not enough free space of injection tweak loader!
            ans |= PATCH_EXEC_RESULT_NO_SPACE_FOR_TWEAKLOADER;
        }
    }
    
    // Ensure No duplicated dylibs, often caused by incorrect tweak injection
    // https://github.com/LiveContainer/LiveContainer/issues/582
    // https://github.com/apple-oss-distributions/dyld/blob/93bd81f9d7fcf004fcebcb66ec78983882b41e71/mach_o/Header.cpp#L678
    struct load_command *command2 = (struct load_command *)imageHeaderPtr;
    __block int   depCount = 0;
    const char**  depPaths = malloc(header->ncmds * sizeof(char*));
    for(int i = 0; i < header->ncmds; i++) {
        switch ( command2->cmd ) {
            case LC_LOAD_DYLIB:
            case LC_LOAD_WEAK_DYLIB:
            case LC_REEXPORT_DYLIB:
            case LC_LOAD_UPWARD_DYLIB: {
                char* loadPath =  (void *)command2 + ((struct dylib_command*)command2)->dylib.name.offset;
                for ( int i = 0; i < depCount; ++i ) {
                    if ( strcmp(loadPath, depPaths[i]) == 0 ) {
                        // replace this duplicated dylib command with an invalid command number
                        command2->cmd = 0x114515;
                        continue;
                    }
                }
                depPaths[depCount] = loadPath;
                ++depCount;
            }
        }
        command2 = (struct load_command *)((void *)command2 + command2->cmdsize);
    }
    free(depPaths);
    
    return ans;
}

static BOOL LCInspectSliceEncryption(void *slice, size_t sliceSize, BOOL *encryptedOut) {
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

static BOOL LCReadSliceSDKVersion(void *slice, size_t sliceSize, uint32_t *sdkOut) {
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

NSString *LCPatchMachOFixupARM64eSlice(const char *path) {
    int fd = open(path, O_RDWR, 0600);
    if(fd < 0) {
        return [NSString stringWithFormat:@"Failed to open %s: %s", path, strerror(errno)];
    }
    struct stat s = {0};
    fstat(fd, &s);
    void *map = mmap(NULL, s.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if(map == MAP_FAILED) {
        close(fd);
        return [NSString stringWithFormat:@"Failed to map %s: %s", path, strerror(errno)];
    }

    uint32_t magic = *(uint32_t *)map;
    if(magic == FAT_CIGAM) {
        // Find arm64e slice without CPU_SUBTYPE_LIB64
        struct fat_header *header = (struct fat_header *)map;
        struct fat_arch *arch = (struct fat_arch *)(map + sizeof(struct fat_header));
        for(int i = 0; i < OSSwapInt32(header->nfat_arch); i++) {
            if(OSSwapInt32(arch->cputype) == CPU_TYPE_ARM64 && OSSwapInt32(arch->cpusubtype) == CPU_SUBTYPE_ARM64E) {
                struct mach_header_64 *header = (struct mach_header_64 *)(map + OSSwapInt32(arch->offset));
                header->cpusubtype |= CPU_SUBTYPE_LIB64;
                arch->cpusubtype = htonl(header->cpusubtype);
                break;
            }
            arch = (struct fat_arch *)((void *)arch + sizeof(struct fat_arch));
        }
    }

    msync(map, s.st_size, MS_SYNC);
    munmap(map, s.st_size);
    close(fd);
    return nil;
}

void LCPatchAppBundleFixupARM64eSlice(NSURL *bundleURL) {
    NSFileManager *fm = [NSFileManager defaultManager];
    NSDirectoryEnumerator *enumerator = [fm enumeratorAtURL:bundleURL includingPropertiesForKeys:nil options:NSDirectoryEnumerationSkipsHiddenFiles errorHandler:nil];
    for (NSURL *fileURL in enumerator) {
        if ([fileURL.pathExtension isEqualToString:@"dylib"]) {
            LCPatchMachOFixupARM64eSlice(fileURL.path.fileSystemRepresentation);
        } else if ([fileURL.pathExtension isEqualToString:@"framework"]) {
            NSDictionary *info = [NSDictionary dictionaryWithContentsOfURL:[fileURL URLByAppendingPathComponent:@"Info.plist"]];
            NSString *executableName = info[@"CFBundleExecutable"];
            if(!executableName) {
                executableName = fileURL.lastPathComponent.stringByDeletingPathExtension;
            }
            NSURL *executableURL = [fileURL URLByAppendingPathComponent:executableName];
            LCPatchMachOFixupARM64eSlice(executableURL.path.fileSystemRepresentation);
        }
    }
}

void LCChangeMachOUUID(struct mach_header_64 *header) {
    struct load_command *command = (struct load_command *)(header + 1);
    for(int i = 0; i < header->ncmds; i++) {
        if(command->cmd == LC_UUID) {
            struct uuid_command *uuidCmd = (struct uuid_command *)command;
            // let's add the first byte by 1
            uuidCmd->uuid[0] += 1;
            break;
        }
        command = (struct load_command *)((void *)command + command->cmdsize);
    }
}

const uint8_t* LCGetMachOUUID(struct mach_header_64 *header) {
    if (!header) return NULL;
    if(*(uint32_t*)header != 0x646c7964) { // dyld
        // Find load commands
        const struct load_command* command = (const struct load_command*)(header + 1);
        
        // Iterate through load commands to find LC_SYMTAB
        for(uint32_t i = 0; i < header->ncmds; i++) {
            if(command->cmd == LC_UUID) {
                return ((const struct uuid_command*)command)->uuid;
            }
            command = (const struct load_command*)((void *)command + command->cmdsize);
        }
        return NULL;
    } else {
        struct dyld_cache_header* dsc_header = (struct dyld_cache_header*)header;
        return dsc_header->uuid;
    }
}

bool LCIsMachOEncrypted(struct mach_header_64 *header) {
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

uint64_t LCFindSymbolOffset(const char *basePath, const char *symbol) {
#if !TARGET_OS_SIMULATOR
    const char *path = basePath;
#else
    char path[PATH_MAX];
    const char *rootPath = getenv("DYLD_ROOT_PATH") ?: "";
    snprintf(path, sizeof(path), "%s%s", rootPath, basePath);
#endif
    __block uint64_t offset = 0;
    LCParseMachO(path, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        if(header->cputype != CPU_TYPE_ARM64) return;
        void *result = litehook_find_symbol_file(header, symbol);
        if(result) {
            offset = (uint64_t)result - (uint64_t)header;
        }
    });
    NSCAssert(offset != 0, @"Failed to find symbol %s in %s", symbol, path);
    return offset;
}

mach_header_u *LCGetLoadedImageHeader(int i0, const char* name) {
    for(uint32_t i = i0; i < _dyld_image_count(); ++i) {
        const char* imgName = _dyld_get_image_name(i);
        // cover simulator path aswell
        if(imgName && strcmp(imgName + (strlen(imgName) - strlen(name)), name) == 0) {
            return (struct mach_header_64*)_dyld_get_image_header(i);
        }
    }
    return NULL;
}

#if TARGET_OS_SIMULATOR
// Make it init first on simulator to find dyld_sim
__attribute__((constructor))
#endif
void *getDyldBase(void) {
    static void *dyldBase = 0;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        dyldBase = (void *)_alt_dyld_get_all_image_infos()->dyldImageLoadAddress;
    });
#if !TARGET_OS_SIMULATOR
    return dyldBase;
#else
    static void *dyldSimBase = NULL;
    if(!dyldSimBase) {
        __block size_t textSize = 0;
        LCParseMachO("/usr/lib/dyld", true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
            if(header->cputype != CPU_TYPE_ARM64) return;
            getsegmentdata(header, SEG_TEXT, &textSize);
        });
        NSArray *callStack = [NSThread callStackReturnAddresses];
        for(NSNumber *addr in callStack.reverseObjectEnumerator) {
            // the first addresss outside of dyld's text is dyld_sim
            uintptr_t addrValue = addr.unsignedLongLongValue;
            if(addrValue < (uintptr_t)dyldBase || addrValue >= (uintptr_t)dyldBase + textSize) {
                dyldSimBase = (void *)(addrValue & ~PAGE_MASK);
                while (((mach_header_u *)dyldSimBase)->magic != MH_MAGIC_64) {
                    dyldSimBase -= PAGE_SIZE;
                }
                break;
            }
        }
    }
    return dyldSimBase;
#endif
}

struct code_signature_command {
    uint32_t    cmd;
    uint32_t    cmdsize;
    uint32_t    dataoff;
    uint32_t    datasize;
};

// from zsign
struct ui_CS_BlobIndex {
    uint32_t type;                    /* type of entry */
    uint32_t offset;                /* offset of entry */
};

struct ui_CS_SuperBlob {
    uint32_t magic;                    /* magic number */
    uint32_t length;                /* total length of SuperBlob */
    uint32_t count;                    /* number of index entries following */
    //CS_BlobIndex index[];            /* (count) entries */
    /* followed by Blobs in no particular order as indicated by offsets in index */
};

struct ui_CS_blob {
    uint32_t magic;
    uint32_t length;
};


struct code_signature_command* findSignatureCommand(struct mach_header_64* header) {
    uint8_t *imageHeaderPtr = (uint8_t*)header + sizeof(struct mach_header_64);
    struct load_command *command = (struct load_command *)imageHeaderPtr;
    struct code_signature_command* codeSignCommand = 0;
    for(int i = 0; i < header->ncmds; i++) {
        if(command->cmd == LC_CODE_SIGNATURE) {
            codeSignCommand = (struct code_signature_command*)command;
            break;
        }
        command = (struct load_command *)((void *)command + command->cmdsize);
    }
    return codeSignCommand;
}

NSString* getEntitlementXML(struct mach_header_64* header, void** entitlementXMLPtrOut) {
    struct code_signature_command* codeSignCommand = findSignatureCommand(header);

    if(!codeSignCommand) {
        return @"Unable to find LC_CODE_SIGNATURE command.";
    }
    struct ui_CS_SuperBlob* blob = (void*)header + codeSignCommand->dataoff;
    if(blob->magic != OSSwapInt32(0xfade0cc0)) {
        return [NSString stringWithFormat:@"CodeSign blob magic mismatch %8x.", blob->magic];
    }
    struct ui_CS_BlobIndex* entitlementBlobIndex = 0;
    struct ui_CS_BlobIndex* nowIndex = (void*)blob + sizeof(struct ui_CS_SuperBlob);
    for(int i = 0; i < OSSwapInt32(blob->count); i++) {
        if(OSSwapInt32(nowIndex->type) == 5) {
            entitlementBlobIndex = nowIndex;
            break;
        }
        nowIndex = (void*)nowIndex + sizeof(struct ui_CS_BlobIndex);
    }
    if(entitlementBlobIndex == 0) {
        return @"[LC] entitlement blob index not found.";
    }
    struct ui_CS_blob* entitlementBlob = (void*)blob + OSSwapInt32(entitlementBlobIndex->offset);
    if(entitlementBlob->magic != OSSwapInt32(0xfade7171)) {
        return [NSString stringWithFormat:@"EntitlementBlob magic mismatch %8x.", blob->magic];
    };
    int32_t xmlLength = OSSwapInt32(entitlementBlob->length) - sizeof(struct ui_CS_blob);
    void* xmlPtr = (void*)entitlementBlob + sizeof(struct ui_CS_blob);
    
    if(entitlementXMLPtrOut) {
        *entitlementXMLPtrOut = xmlPtr;
    }

    // entitlement xml in executable don't have \0 so we have to copy it first
    char* xmlString = malloc(xmlLength + 1);
    memcpy(xmlString, xmlPtr, xmlLength);
    xmlString[xmlLength] = 0;

    NSString* ans = [NSString stringWithUTF8String:xmlString];
    free(xmlString);
    return ans;
}

bool checkCodeSignature(const char* path) {
    __block bool checked = false;
    __block bool ans = false;
    LCParseMachO(path, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        if(checked || header->cputype != CPU_TYPE_ARM64) {
            return;
        }
        checked = true;
        
        struct code_signature_command* codeSignatureCommand = findSignatureCommand(header);
        if(!codeSignatureCommand) {
            return;
        }
        off_t sliceOffset = (void*)header - filePtr;
        fsignatures_t siginfo;
        siginfo.fs_file_start = sliceOffset;
        siginfo.fs_blob_start = (void*)(long)(codeSignatureCommand->dataoff);
        siginfo.fs_blob_size  = codeSignatureCommand->datasize;
        int addFileSigsReault = fcntl(fd, F_ADDFILESIGS_RETURN, &siginfo);
        if ( addFileSigsReault == -1 ) {
            ans = false;
            return;
        }
        
        fchecklv_t checkInfo;
        char     messageBuffer[512];
        messageBuffer[0]                = '\0';
        checkInfo.lv_error_message_size = sizeof(messageBuffer);
        checkInfo.lv_error_message      = messageBuffer;
        checkInfo.lv_file_start= sliceOffset;
        int checkLVresult = fcntl(fd, F_CHECK_LV, &checkInfo);
        
        if (checkLVresult == 0) {
            ans = true;
            return;
        } else {
            ans = false;
            return;
        }
    });
    return ans;
}

NSString* getExecutableEntitlementXML(NSString* executablePath) {
    if(executablePath.length == 0) return nil;
    __block NSString* ans = @"Failed to find executable?";
    LCParseMachO(executablePath.UTF8String, true, ^(const char *path, struct mach_header_64 *header, int fd, void *filePtr) {
        ans = getEntitlementXML(header, 0);
    });
    return ans;
}

NSString* getLCEntitlementXML(void) {
    // Keep the historical API for callers that only need the host executable.
    return getExecutableEntitlementXML(NSBundle.mainBundle.executablePath);
}
