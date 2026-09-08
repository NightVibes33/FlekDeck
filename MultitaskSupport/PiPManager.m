//
//  PiPManager.m
//  LiveContainer
//
//  Created by s s on 2025/6/3.
//
#include "PiPManager.h"
#include "AppSceneViewController.h"
#include "DecoratedAppSceneViewController.h"
#include "../LiveContainer/utils.h"

static void *kPiPBoundsObservationContext = &kPiPBoundsObservationContext;
static const CGFloat kLCMediaPiPAspectRatio = 16.0 / 9.0;

API_AVAILABLE(ios(16.0))
@interface PiPManager()
@property(nonatomic, strong) UIView *pipVideoCallContentView;
@property(nonatomic, strong) AVPictureInPictureVideoCallViewController *pipVideoCallViewController;
@property(nonatomic, strong) AVPictureInPictureController *pipController;
@property(nonatomic) AppSceneViewController* displayingVC;
@property(nonatomic, strong) CALayer *observedLayer;
@property(nonatomic) CGSize sourceContentSize;
@property(nonatomic) BOOL usesMediaCrop;
@property(nonatomic) CGAffineTransform savedContentTransform;
@property(nonatomic) CATransform3D savedContentSublayerTransform;
@property(nonatomic) BOOL hasSavedContentTransforms;
@end

@implementation PiPManager
API_AVAILABLE(ios(16.0))
static PiPManager* sharedInstance = nil;

+ (instancetype)shared {
    if(!sharedInstance)
        sharedInstance = [[self alloc] init];
    return sharedInstance;
}

+ (BOOL)hasShared {
    return sharedInstance != nil;
}

- (DecoratedAppSceneViewController *)displayingDecoratedVC {
    return (id)self.displayingVC.delegate;
}

- (BOOL)isPiP {
    return self.pipController.isPictureInPictureActive;
}

- (BOOL)isPiPWithVC:(AppSceneViewController*)vc {
    return self.pipController.isPictureInPictureActive && self.displayingVC == vc;
}

- (BOOL)isPiPWithDecoratedVC:(UIViewController*)vc {
    return self.pipController.isPictureInPictureActive && self.displayingDecoratedVC == vc;
}

- (instancetype)init {
    NSError* error = nil;
    [[AVAudioSession sharedInstance] setCategory:AVAudioSessionCategoryPlayback error:&error];
    [[AVAudioSession sharedInstance] setActive:YES withOptions:1 error:&error];
    return self;
}

/// The host receives one remote scene surface from LiveProcess; it cannot walk
/// the guest's AVPlayerLayer hierarchy. For a portrait guest, use the common
/// full-width player shape (16:9) and crop from the top. If the guest is already
/// landscape, preserve its current shape.
- (BOOL)shouldUseMediaCropForSourceSize:(CGSize)sourceSize {
    if(sourceSize.width <= 0 || sourceSize.height <= 0) return NO;
    return sourceSize.height > sourceSize.width * 1.15;
}

- (CGSize)preferredPiPContentSizeForSourceSize:(CGSize)sourceSize {
    if(sourceSize.width <= 0 || sourceSize.height <= 0) {
        return CGSizeMake(320, 180);
    }
    if(![self shouldUseMediaCropForSourceSize:sourceSize]) {
        return sourceSize;
    }
    CGFloat width = MAX(sourceSize.width, 320.0);
    return CGSizeMake(width, width / kLCMediaPiPAspectRatio);
}

- (CGSize)sourceSizeForVC:(AppSceneViewController *)vc {
    CGSize size = vc.contentView.bounds.size;
    if(size.width <= 0 || size.height <= 0) {
        size = vc.view.bounds.size;
    }
    return size;
}

- (void)normalizeGuestSurfaceForPiP {
    UIView *contentView = self.displayingVC.contentView;
    if(!contentView || self.hasSavedContentTransforms) return;
    self.savedContentTransform = contentView.transform;
    self.savedContentSublayerTransform = contentView.layer.sublayerTransform;
    self.hasSavedContentTransforms = YES;
    contentView.transform = CGAffineTransformIdentity;
    contentView.layer.sublayerTransform = CATransform3DIdentity;
}

- (void)restoreGuestSurfaceTransforms {
    if(!self.hasSavedContentTransforms || !self.displayingVC.contentView) return;
    self.displayingVC.contentView.transform = self.savedContentTransform;
    self.displayingVC.contentView.layer.sublayerTransform = self.savedContentSublayerTransform;
    self.hasSavedContentTransforms = NO;
}

/// Lay the remote scene into AVKit without distorting it. Portrait/media mode
/// aspect-fills and pins the crop to the top so an inline player stays visible;
/// landscape mode aspect-fits and centers.
- (void)layoutPiPContentForBounds:(CGRect)bounds {
    if(!self.pipVideoCallContentView || self.sourceContentSize.width <= 0 || self.sourceContentSize.height <= 0) {
        return;
    }
    CGFloat width = CGRectGetWidth(bounds);
    CGFloat height = CGRectGetHeight(bounds);
    if(width <= 0 || height <= 0) return;

    CGFloat scaleX = width / self.sourceContentSize.width;
    CGFloat scaleY = height / self.sourceContentSize.height;
    CGFloat scale = self.usesMediaCrop ? MAX(scaleX, scaleY) : MIN(scaleX, scaleY);

    CGFloat visualWidth = self.sourceContentSize.width * scale;
    CGFloat visualHeight = self.sourceContentSize.height * scale;
    CGFloat x = CGRectGetMinX(bounds) + (width - visualWidth) * 0.5;
    CGFloat y = self.usesMediaCrop
        ? CGRectGetMinY(bounds)
        : CGRectGetMinY(bounds) + (height - visualHeight) * 0.5;

    self.pipVideoCallContentView.bounds = (CGRect){CGPointZero, self.sourceContentSize};
    self.pipVideoCallContentView.layer.anchorPoint = CGPointMake(0, 0);
    self.pipVideoCallContentView.layer.position = CGPointMake(x, y);
    self.pipVideoCallContentView.transform = CGAffineTransformMakeScale(scale, scale);
}

- (void)startPiPWithVC:(AppSceneViewController*)vc {
    [self.pipController stopPictureInPicture];
    if(self.displayingVC) {
        [self.displayingDecoratedVC unminimizeWindowPiP];
        [self pictureInPictureControllerDidStopPictureInPicture:self.pipController];
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)([self.pipController isPictureInPictureActive] * 0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        self.displayingVC = vc;
        self.sourceContentSize = [self sourceSizeForVC:vc];
        self.usesMediaCrop = [self shouldUseMediaCropForSourceSize:self.sourceContentSize];

        self.pipVideoCallViewController = [AVPictureInPictureVideoCallViewController new];
        self.pipVideoCallViewController.preferredContentSize = [self preferredPiPContentSizeForSourceSize:self.sourceContentSize];
        self.pipVideoCallViewController.view.backgroundColor = UIColor.blackColor;
        self.pipVideoCallViewController.view.clipsToBounds = YES;

        // Always use a wrapper so PiP geometry never leaks back into the guest.
        self.pipVideoCallContentView = [[UIView alloc] initWithFrame:(CGRect){CGPointZero, self.sourceContentSize}];
        self.pipVideoCallContentView.backgroundColor = UIColor.blackColor;
        self.pipVideoCallContentView.clipsToBounds = NO;
        self.pipVideoCallContentView.layer.anchorPoint = CGPointMake(0, 0);
        self.pipVideoCallContentView.layer.position = CGPointMake(0, 0);
        [self.pipVideoCallViewController.view addSubview:self.pipVideoCallContentView];

        AVPictureInPictureControllerContentSource* contentSource =
            [[AVPictureInPictureControllerContentSource alloc]
                initWithActiveVideoCallSourceView:vc.view
                contentViewController:self.pipVideoCallViewController];
        self.pipController = [[AVPictureInPictureController alloc] initWithContentSource:contentSource];
        self.pipController.canStartPictureInPictureAutomaticallyFromInline = YES;
        self.pipController.delegate = self;
        [self.pipController setValue:@1 forKey:@"controlsStyle"];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            [self.pipController startPictureInPicture];
        });
    });
}

- (void)stopPiP {
    [self.pipController stopPictureInPicture];
}

- (void)pictureInPictureControllerWillStartPictureInPicture:(AVPictureInPictureController *)pictureInPictureController {
    [self.displayingDecoratedVC minimizeWindowPiP];

    self.sourceContentSize = [self sourceSizeForVC:self.displayingVC];
    self.usesMediaCrop = [self shouldUseMediaCropForSourceSize:self.sourceContentSize];
    self.pipVideoCallViewController.preferredContentSize = [self preferredPiPContentSizeForSourceSize:self.sourceContentSize];
    self.pipVideoCallViewController.additionalSafeAreaInsets = UIEdgeInsetsZero;

    [self normalizeGuestSurfaceForPiP];
    self.displayingVC.contentView.frame = (CGRect){CGPointZero, self.sourceContentSize};
    [self.pipVideoCallContentView addSubview:self.displayingVC.contentView];
    [self.pipVideoCallViewController.view addSubview:self.pipVideoCallContentView];

    [self observeBoundsOfLayer:self.pipVideoCallViewController.view.layer];
    [self layoutPiPContentForBounds:self.pipVideoCallViewController.view.bounds];

    [self.displayingVC setBackgroundNotificationEnabled:false];
    self.displayingVC.shouldIgnoreSceneUpdates = YES;
}

- (void)pictureInPictureControllerDidStartPictureInPicture:(AVPictureInPictureController *)pictureInPictureController {
}

- (void)pictureInPictureControllerWillStopPictureInPicture:(AVPictureInPictureController *)pictureInPictureController {
    self.displayingVC.shouldIgnoreSceneUpdates = NO;
    [self.displayingDecoratedVC unminimizeWindowPiP];
}

- (void)pictureInPictureControllerDidStopPictureInPicture:(AVPictureInPictureController *)pictureInPictureController {
    if(pictureInPictureController != self.pipController) return;

    [self restoreGuestSurfaceTransforms];
    [self.displayingVC.view insertSubview:self.displayingVC.contentView atIndex:0];
    [self.displayingVC setBackgroundNotificationEnabled:true];
    [self.displayingDecoratedVC updateVerticalConstraints];

    self.pipVideoCallContentView.transform = CGAffineTransformIdentity;
    [self.pipVideoCallContentView removeFromSuperview];
    [self observeBoundsOfLayer:nil];
    self.sourceContentSize = CGSizeZero;
    self.usesMediaCrop = NO;

    if([NSUserDefaults.lcSharedDefaults boolForKey:@"LCAutoEndPiP"]) {
        self.pipController = nil;
        self.pipVideoCallViewController = nil;
    }
    self.pipVideoCallContentView = nil;
}

- (void)pictureInPictureController:(AVPictureInPictureController *)pictureInPictureController restoreUserInterfaceForPictureInPictureStopWithCompletionHandler:(void (^)(BOOL))completionHandler {
    DecoratedAppSceneViewController *decoratedVC = self.displayingDecoratedVC;
    if(!decoratedVC) {
        completionHandler(YES);
        return;
    }
    [decoratedVC unminimizeWindowPiPWithCompletion:^{
        completionHandler(YES);
    }];
}

- (void)pictureInPictureController:(AVPictureInPictureController *)pictureInPictureController failedToStartPictureInPictureWithError:(NSError *)error {
    NSLog(@"[FlekDeck] PiP failed to start: %@", error.description);
    [self observeBoundsOfLayer:nil];
    [self restoreGuestSurfaceTransforms];
    if(self.displayingVC && self.displayingVC.contentView) {
        [self.displayingVC.view insertSubview:self.displayingVC.contentView atIndex:0];
        [self.displayingVC setBackgroundNotificationEnabled:true];
        self.displayingVC.shouldIgnoreSceneUpdates = NO;
        [self.displayingDecoratedVC unminimizeWindowPiP];
        [self.displayingDecoratedVC updateVerticalConstraints];
    }
    [self.pipVideoCallContentView removeFromSuperview];
    self.pipVideoCallContentView = nil;
    self.sourceContentSize = CGSizeZero;
    self.usesMediaCrop = NO;
}

- (void)observeBoundsOfLayer:(CALayer *)layer {
    if(self.observedLayer == layer) return;
    [self.observedLayer removeObserver:self forKeyPath:@"bounds" context:kPiPBoundsObservationContext];
    self.observedLayer = layer;
    [layer addObserver:self forKeyPath:@"bounds" options:NSKeyValueObservingOptionNew context:kPiPBoundsObservationContext];
}

- (void)observeValueForKeyPath:(NSString*)keyPath ofObject:(NSObject*)object change:(NSDictionary<NSString *,id> *) change context:(void *) context {
    if(context != kPiPBoundsObservationContext) {
        [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
        return;
    }
    CGRect rect = [change[@"new"] CGRectValue];
    [self layoutPiPContentForBounds:rect];
}

@end
