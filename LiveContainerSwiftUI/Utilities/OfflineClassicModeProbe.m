#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import "LCUtils.h"

// Do not construct private SpringBoard application objects in the host process.
// Those objects change between iOS releases and failure can abort below
// Objective-C exception handling. Compatibility Mode is an optional launch
// hint, so use stable generic modes instead: 1 = phone, 12 = iPad.
NSNumber *LCGetDefaultClassicMode(NSURL *appURL) {
    NSBundle *bundle = appURL ? [NSBundle bundleWithURL:appURL] : nil;
    if(!bundle || !bundle.executableURL) {
        return @0;
    }

    NSArray *families = [bundle objectForInfoDictionaryKey:@"UIDeviceFamily"];
    BOOL guestSupportsPad = [families isKindOfClass:NSArray.class] && [families containsObject:@2];
    if(UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad && guestSupportsPad) {
        return @12;
    }
    return @1;
}
