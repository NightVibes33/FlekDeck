#import <Foundation/Foundation.h>

typedef NS_ENUM(NSInteger, NotifLevel) {
    NotifLevelInfo = 0,
    NotifLevelWarning = 1,
    NotifLevelError = 2,
};

@interface XCButton : NSObject
+ (void)updateProgressWithValue:(double)value;
@end

@interface NotificationServer : NSObject
+ (void)NotifyUserWithLevel:(NotifLevel)level
               notification:(NSString *)notification
                      delay:(double)delay;
@end
