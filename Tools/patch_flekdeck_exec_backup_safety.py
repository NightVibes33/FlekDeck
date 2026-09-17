#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Models/LCAppInfo.m")
s = path.read_text()

old_exec = '''    NSFileManager* fm = NSFileManager.defaultManager;\n    NSString *execPath = [NSString stringWithFormat:@"%@/%@", appPath, _infoPlist[@"CFBundleExecutable"]];\n    \n    // Update patch\n'''
new_exec = '''    NSFileManager* fm = NSFileManager.defaultManager;\n    NSString *execName = _infoPlist[@"CFBundleExecutable"];\n    if(![execName isKindOfClass:NSString.class] || execName.length == 0) {\n        [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n        completetionHandler(NO, @"The app bundle has no valid CFBundleExecutable.");\n        return;\n    }\n    NSString *execPath = [appPath stringByAppendingPathComponent:execName];\n    BOOL execIsDirectory = NO;\n    if(![fm fileExistsAtPath:execPath isDirectory:&execIsDirectory] || execIsDirectory) {\n        [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n        completetionHandler(NO, [NSString stringWithFormat:@"The app executable is missing: %@", execPath]);\n        return;\n    }\n    \n    // Update patch\n'''
if new_exec not in s:
    if old_exec not in s:
        raise SystemExit(f"{path}: executable validation anchor missing")
    s = s.replace(old_exec, new_exec, 1)

old_cycle = '''    if (needPatch || forceSign) {\n        // copy-delete-move to avoid EXC_BAD_ACCESS (SIGKILL - CODESIGNING)\n        NSString *backupPath = [NSString stringWithFormat:@"%@/%@_LiveContainerPatchBackUp", appPath, _infoPlist[@"CFBundleExecutable"]];\n        NSError *err;\n        [fm copyItemAtPath:execPath toPath:backupPath error:&err];\n        [fm removeItemAtPath:execPath error:&err];\n        [fm moveItemAtPath:backupPath toPath:execPath error:&err];\n    }\n'''
new_cycle = '''    if (needPatch || forceSign) {\n        // copy-delete-move avoids EXC_BAD_ACCESS (SIGKILL - CODESIGNING), but\n        // it must be transactional: never delete the only executable unless the\n        // backup copy is known-good.\n        NSString *backupPath = [NSString stringWithFormat:@"%@/%@_LiveContainerPatchBackUp", appPath, execName];\n        NSError *err = nil;\n        if([fm fileExistsAtPath:backupPath]) {\n            if(![fm removeItemAtPath:backupPath error:&err]) {\n                [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n                completetionHandler(NO, [NSString stringWithFormat:@"Could not clear stale executable backup: %@", err.localizedDescription ?: @"unknown filesystem error"]);\n                return;\n            }\n        }\n        err = nil;\n        if(![fm copyItemAtPath:execPath toPath:backupPath error:&err]) {\n            [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n            completetionHandler(NO, [NSString stringWithFormat:@"Could not back up the app executable: %@", err.localizedDescription ?: @"unknown filesystem error"]);\n            return;\n        }\n        err = nil;\n        if(![fm removeItemAtPath:execPath error:&err]) {\n            [fm removeItemAtPath:backupPath error:nil];\n            [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n            completetionHandler(NO, [NSString stringWithFormat:@"Could not replace the app executable: %@", err.localizedDescription ?: @"unknown filesystem error"]);\n            return;\n        }\n        err = nil;\n        if(![fm moveItemAtPath:backupPath toPath:execPath error:&err]) {\n            NSError *restoreError = nil;\n            if([fm fileExistsAtPath:backupPath]) {\n                [fm copyItemAtPath:backupPath toPath:execPath error:&restoreError];\n                if(!restoreError) [fm removeItemAtPath:backupPath error:nil];\n            }\n            [NSUserDefaults.standardUserDefaults removeObjectForKey:@"SigningInProgress"];\n            NSString *detail = err.localizedDescription ?: @"unknown filesystem error";\n            if(restoreError) {\n                detail = [detail stringByAppendingFormat:@"; restore also failed: %@", restoreError.localizedDescription];\n            }\n            completetionHandler(NO, [NSString stringWithFormat:@"Could not restore the app executable after patch preparation: %@", detail]);\n            return;\n        }\n    }\n'''
if new_cycle not in s:
    if old_cycle not in s:
        raise SystemExit(f"{path}: unsafe executable backup cycle anchor missing")
    s = s.replace(old_cycle, new_cycle, 1)

path.write_text(s)

final = path.read_text()
for marker in (
    'The app bundle has no valid CFBundleExecutable.',
    'Could not back up the app executable:',
    'Could not restore the app executable after patch preparation:',
):
    if marker not in final:
        raise SystemExit(f"{path}: executable safety marker missing: {marker}")
if 'NSError *err;\n        [fm copyItemAtPath:execPath' in final:
    raise SystemExit(f"{path}: unsafe unchecked executable backup cycle survived")

print("FlekDeck guest executable patch cycle made transactional and error-reporting")
