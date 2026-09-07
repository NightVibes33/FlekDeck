#import "FDNyxianUIAdapters.h"

NSString *const FDNyxianRuntimeNotification = @"FDNyxianRuntimeNotification";

@implementation XCButton
+ (void)updateProgressWithValue:(double)value {
    [[NSNotificationCenter defaultCenter] postNotificationName:@"FDNyxianBootstrapProgress"
                                                        object:nil
                                                      userInfo:@{ @"progress": @(value) }];
}
@end

@implementation NotificationServer
+ (void)NotifyUserWithLevel:(NotifLevel)level notification:(NSString *)notification delay:(double)delay {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(MAX(0, delay) * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        [[NSNotificationCenter defaultCenter] postNotificationName:FDNyxianRuntimeNotification
                                                            object:nil
                                                          userInfo:@{ @"level": @(level), @"message": notification ?: @"" }];
    });
}
@end
