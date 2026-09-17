#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


header = Path("LiveContainerSwiftUI/Utilities/LCUtils.h")
replace_once(
    header,
    '''+ (int)validateCertificateWithCompletionHandler:(void(^)(int status, NSDate *expirationDate, NSString *organizationalUnitName, NSString *error))completionHandler;\n\n+ (BOOL)isAppGroupAltStoreLike;''',
    '''+ (int)validateCertificateWithCompletionHandler:(void(^)(int status, NSDate *expirationDate, NSString *organizationalUnitName, NSString *error))completionHandler;\n\n#if is32BitSupported\n+ (BOOL)isTXMScriptRequired;\n+ (NSString *)base64EncodedUniversalJITScript;\n#endif\n\n+ (BOOL)isAppGroupAltStoreLike;''',
    "TXM declarations",
)

impl = Path("LiveContainerSwiftUI/Utilities/LCUtils.m")
text = impl.read_text()
if "#import <dlfcn.h>" not in text:
    if "@import Security;\n" not in text:
        raise SystemExit("LCUtils.m: Security import anchor missing")
    text = text.replace("@import Security;\n", "@import Security;\n#if is32BitSupported\n#import <dlfcn.h>\n#endif\n", 1)
    impl.write_text(text)

replace_once(
    impl,
    '''    int ans = [NSClassFromString(@"ZSigner") checkCert:certData pass:[LCSharedUtils certificatePassword] completionHandler:completionHandler];\n    return ans;\n}\n\n#pragma mark Setup''',
    '''    int ans = [NSClassFromString(@"ZSigner") checkCert:certData pass:[LCSharedUtils certificatePassword] completionHandler:completionHandler];\n    return ans;\n}\n\n#if is32BitSupported\n#pragma mark ARM32 TXM JIT compatibility\n\ntypedef uint32_t FlekIOObject;\ntypedef FlekIOObject (*FlekIORegistryEntryFromPathFn)(uint32_t masterPort, const char *path);\ntypedef CFTypeRef (*FlekIORegistryEntryCreateCFPropertyFn)(FlekIOObject entry, CFStringRef key, CFAllocatorRef allocator, uint32_t options);\ntypedef int32_t (*FlekIOObjectReleaseFn)(FlekIOObject object);\n\n+ (BOOL)isTXMScriptRequired {\n    if (@available(iOS 19.0, *)) {\n        // IOKit is private to iOS SDK consumers even though the runtime symbols\n        // exist. Resolve only the three functions we need instead of importing\n        // or linking the framework, so the normal FlekDeck target keeps building.\n        void *handle = dlopen(\"/System/Library/Frameworks/IOKit.framework/IOKit\", RTLD_LAZY | RTLD_LOCAL);\n        if (!handle) {\n            return NO;\n        }\n\n        FlekIORegistryEntryFromPathFn entryFromPath =\n            (FlekIORegistryEntryFromPathFn)dlsym(handle, \"IORegistryEntryFromPath\");\n        FlekIORegistryEntryCreateCFPropertyFn createProperty =\n            (FlekIORegistryEntryCreateCFPropertyFn)dlsym(handle, \"IORegistryEntryCreateCFProperty\");\n        FlekIOObjectReleaseFn releaseObject =\n            (FlekIOObjectReleaseFn)dlsym(handle, \"IOObjectRelease\");\n        if (!entryFromPath || !createProperty || !releaseObject) {\n            dlclose(handle);\n            return NO;\n        }\n\n        FlekIOObject memoryMap = entryFromPath(0, \"IODeviceTree:/chosen/memory-map\");\n        if (memoryMap == 0) {\n            dlclose(handle);\n            return NO;\n        }\n\n        CFTypeRef value = createProperty(\n            memoryMap, CFSTR(\"IORegistryEntryPropertyKeys\"), kCFAllocatorDefault, 0\n        );\n        releaseObject(memoryMap);\n        dlclose(handle);\n\n        NSArray *keys = CFBridgingRelease(value);\n        return [keys isKindOfClass:NSArray.class] && [keys containsObject:@\"TXM\"];\n    }\n    return NO;\n}\n\n+ (NSString *)base64EncodedUniversalJITScript {\n    static dispatch_once_t onceToken;\n    static NSString *script;\n    dispatch_once(&onceToken, ^{\n        NSString *path = [NSBundle.mainBundle pathForResource:@\"universal\" ofType:@\"js\"];\n        NSData *data = path.length ? [NSData dataWithContentsOfFile:path] : nil;\n        script = data ? [data base64EncodedStringWithOptions:0] : @\"\";\n        if(script.length == 0) {\n            NSLog(@\"[FlekDeck/LC32] universal.js is missing; TXM JIT bootstrap is unavailable\");\n        }\n    });\n    return script;\n}\n#endif\n\n#pragma mark Setup''',
    "TXM implementation",
)

appinfo = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
replace_once(
    appinfo,
    '''- (NSString *)jitLaunchScriptJs {\n    return _info[@"jitLaunchScriptJs"];\n}''',
    '''- (NSString *)jitLaunchScriptJs {\n#if is32BitSupported\n    if (self.is32bit && LCUtils.isTXMScriptRequired) {\n        NSString *universalScript = LCUtils.base64EncodedUniversalJITScript;\n        if (universalScript.length > 0) {\n            return universalScript;\n        }\n    }\n#endif\n    return _info[@"jitLaunchScriptJs"];\n}''',
    "ARM32 automatic TXM script selection",
)

checks = {
    header: ["isTXMScriptRequired", "base64EncodedUniversalJITScript"],
    impl: ["#import <dlfcn.h>", "IORegistryEntryFromPath", "IORegistryEntryPropertyKeys", 'containsObject:@"TXM"', 'pathForResource:@"universal"'],
    appinfo: ["self.is32bit && LCUtils.isTXMScriptRequired", "base64EncodedUniversalJITScript"],
}
for file, needles in checks.items():
    text = file.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{file}: expected TXM marker missing: {needle}")

print("FlekDeck ARM32 TXM JIT compatibility applied without IOKit link dependency")
