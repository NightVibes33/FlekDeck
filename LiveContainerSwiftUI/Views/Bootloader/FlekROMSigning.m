/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 FlekDeck bridge to its configured ZSign identity for ROM payloads.
*/

#import "FlekROMSigning.h"
#import "../../Utilities/LCUtils.h"
#import "../../../LiveContainer/LCSharedUtils.h"
#import <dispatch/dispatch.h>

BOOL FlekDeckSignROMFilesWithZSign(NSArray<NSURL *> *files, NSError **error)
{
    if(files.count == 0)
    {
        return YES;
    }

    dispatch_semaphore_t completed = dispatch_semaphore_create(0);
    __block BOOL succeeded = NO;
    __block NSError *signingError = nil;

    NSProgress *progress = [LCUtils signFilesWithZSignWithURLs:files
                                             completionHandler:^(BOOL success, NSError * _Nullable error) {
        succeeded = success && error == nil;
        signingError = error;
        dispatch_semaphore_signal(completed);
    }];
    (void)progress;

    dispatch_semaphore_wait(completed, DISPATCH_TIME_FOREVER);
    if(!succeeded && error != NULL)
    {
        *error = signingError ?: [NSError errorWithDomain:@"com.fs.flekdeck.bootloader.signing"
                                                     code:1
                                                 userInfo:@{NSLocalizedDescriptionKey: @"FlekDeck could not sign the ROM binaries with its configured identity."}];
    }
    return succeeded;
}

NSURL * _Nullable FlekDeckBootSharedRootURL(void)
{
    NSURL *appGroupURL = [LCSharedUtils appGroupPath];
    if(appGroupURL == nil)
    {
        return nil;
    }
    return [appGroupURL URLByAppendingPathComponent:@"FlekDeck/Boot" isDirectory:YES];
}
