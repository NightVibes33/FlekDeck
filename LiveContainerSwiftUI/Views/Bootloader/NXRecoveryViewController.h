/*
 SPDX-License-Identifier: AGPL-3.0-or-later

 Copyright (C) 2025 - 2026 emexlab

 This file is part of Nyxian.

 Nyxian is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 Nyxian is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with Nyxian. If not, see <https://www.gnu.org/licenses/>.
*/

#ifndef NXRECOVERYVIEWCONTROLLER_H
#define NXRECOVERYVIEWCONTROLLER_H

#import <UIKit/UIKit.h>

typedef NS_ENUM(NSInteger, NXRecoveryLogLevel) {
    NXRecoveryLogLevelInfo = 0,
    NXRecoveryLogLevelError = 1,
};

typedef NS_ENUM(NSInteger, NXRecoveryButton) {
    NXRecoveryButtonNone = 0,
    NXRecoveryButtonVolumeUp = 1,
    NXRecoveryButtonVolumeDown = 2,
};

typedef NS_ENUM(NSInteger, NXRecoveryEventKind) {
    NXRecoveryEventKindTap = 0,
    NXRecoveryEventKindSelect = 1,
};

@class NXRecoveryViewController;
@class NXRecoveryItem;

typedef void (^NXRecoveryAction)(NXRecoveryViewController *controller);
typedef void (^NXRecoveryIndexHandler)(NXRecoveryViewController *controller, NSInteger index, NXRecoveryItem *item);
typedef void (^NXRecoveryFileHandler)(NSString *path, NSString *name, NXRecoveryViewController *controller);

extern const CGFloat NXRecoveryFontSize;

@interface NXRecoveryItem : NSObject

@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NXRecoveryAction action;

- (instancetype)initWithTitle:(NSString *)title action:(NXRecoveryAction)action;

+ (instancetype)itemWithTitle:(NSString *)title;
+ (instancetype)itemWithTitle:(NSString *)title action:(NXRecoveryAction)action;

@end

@interface NXRecoveryViewController : UIViewController

@property (nonatomic, copy) NSArray<NXRecoveryItem *> *recoveryItems;
@property (nonatomic) NSInteger recoveryIndex;
@property (nonatomic, readonly) NXRecoveryItem *currentRecoveryItem;
@property (nonatomic, readonly, getter=isRecoveryActive) BOOL recoveryActive;
@property (nonatomic) NSInteger recoveryLogMax;
@property (nonatomic, readonly, getter=isConsoleActive) BOOL consoleActive;

+ (UIColor *)recoveryBackgroundColor;
+ (UIColor *)recoveryHeaderColor;
+ (UIColor *)recoveryInfoColor;
+ (UIColor *)recoveryItemColor;
+ (UIColor *)recoveryHighlightColor;
+ (UIColor *)recoveryHighlightTextColor;
+ (UIColor *)recoveryFooterColor;
+ (UIColor *)recoveryLogInfoColor;
+ (UIColor *)recoveryLogErrorColor;

- (void)attachToViewController:(UIViewController *)parent;
- (void)createRecoveryView;

- (void)setRecoveryHeader:(NSString *)text;
- (void)setRecoveryInstructions:(NSString *)text;
- (void)setRecoveryFooter:(NSString *)text;
- (void)setRecoveryItems:(NSArray<NXRecoveryItem *> *)items;

- (void)showRecovery:(BOOL)visible;

- (void)enterRecoveryWithHeader:(NSString *)header instructions:(NSString *)instructions footer:(NSString *)footer items:(NSArray<NXRecoveryItem *> *)items onSelect:(NXRecoveryIndexHandler)onSelect onMove:(NXRecoveryIndexHandler)onMove;
- (void)exitRecovery;

- (void)handleButton:(NXRecoveryButton)button kind:(NXRecoveryEventKind)kind;
- (void)handleButton:(NSInteger)button kindString:(NSString *)kind;

- (void)recoveryLog:(NSString *)line;
- (void)recoveryLog:(NSString *)line level:(NXRecoveryLogLevel)level;
- (void)recoveryLogError:(NSString *)line;
- (void)clearRecoveryLog;

- (void)browsePath:(NSString *)path root:(NSString *)root header:(NSString *)header onBack:(NXRecoveryAction)onBack onFile:(NXRecoveryFileHandler)onFile;
- (void)browsePath:(NSString *)path;
- (void)enterFileBrowserAtPath:(NSString *)path root:(NSString *)root header:(NSString *)header onBack:(NXRecoveryAction)onBack onFile:(NXRecoveryFileHandler)onFile;

- (void)enterConsole;
- (void)finishConsoleWithSelectAction:(nullable NXRecoveryAction)action;
- (void)exitConsole;

@end

#endif /* NXRECOVERYVIEWCONTROLLER_H */

