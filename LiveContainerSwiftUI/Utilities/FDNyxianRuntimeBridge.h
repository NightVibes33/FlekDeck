#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, FDNyxianRuntimeState) {
    FDNyxianRuntimeStateUnavailable = 0,
    FDNyxianRuntimeStateMissingExtension,
    FDNyxianRuntimeStateMissingEntitlement,
    FDNyxianRuntimeStateReady,
};

@interface FDNyxianRuntimeBridge : NSObject

@property (class, nonatomic, readonly) FDNyxianRuntimeBridge *shared;
@property (nonatomic, readonly) FDNyxianRuntimeState state;
@property (nonatomic, copy, readonly) NSString *diagnosticMessage;

- (void)launchApplicationAtBundlePath:(NSString *)bundlePath
                     bundleIdentifier:(NSString *)bundleIdentifier
                           completion:(void (^)(NSError * _Nullable error))completion;

@end

NS_ASSUME_NONNULL_END
