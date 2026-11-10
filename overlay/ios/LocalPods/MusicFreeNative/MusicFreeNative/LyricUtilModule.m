#import "LyricUtilModule.h"
#import <React/RCTBridgeModule.h>
#import <UIKit/UIKit.h>

/**
 * iOS replacement for Android's system-wide status-bar / floating lyric.
 *
 * There is no public iOS equivalent of SYSTEM_ALERT_WINDOW, so instead of a
 * no-op we render a draggable lyric card inside a dedicated, transparent
 * UIWindow owned by the app. The window passes touches through everywhere
 * except the card itself (see -hitTest:), so the rest of MusicFree stays fully
 * interactive. The JS API is byte-for-byte the same as Android's LyricUtil.
 *
 * Limitation: this only exists while the app is in the foreground. For
 * lock-screen / Dynamic Island coverage, enable the optional Live Activity
 * module (see overlay/ios/LiveActivity and README).
 */

#pragma mark - Value helpers

static UIColor *MFColorFromValue(id value, UIColor *fallback)
{
  if (!value || [value isKindOfClass:NSNull.class]) { return fallback; }
  unsigned int v = 0;

  if ([value isKindOfClass:NSString.class]) {
    NSString *s = [(NSString *)value stringByTrimmingCharactersInSet:
                   [NSCharacterSet whitespaceAndNewlineCharacterSet]];
    s = [s stringByReplacingOccurrencesOfString:@"#" withString:@""];
    if ([[s lowercaseString] hasPrefix:@"0x"]) { s = [s substringFromIndex:2]; }
    if (s.length == 0 || s.length > 8) { return fallback; }
    NSScanner *scanner = [NSScanner scannerWithString:s];
    unsigned long long parsed = 0;
    if (![scanner scanHexLongLong:&parsed]) { return fallback; }
    v = (unsigned int)parsed;
    if (s.length <= 6) { v |= 0xFF000000u; }   // #RRGGBB -> opaque
  } else if ([value isKindOfClass:NSNumber.class]) {
    v = [(NSNumber *)value unsignedIntValue];
  } else {
    return fallback;
  }

  CGFloat a = ((v >> 24) & 0xFF) / 255.0;
  if (a <= 0.001) { a = 1.0; }              // Android often passes 0xAARRGGBB
  return [UIColor colorWithRed:((v >> 16) & 0xFF) / 255.0
                         green:((v >> 8) & 0xFF) / 255.0
                          blue:(v & 0xFF) / 255.0
                         alpha:a];
}

static CGFloat MFPercent(id value, CGFloat fallback)
{
  if (![value isKindOfClass:NSNumber.class]) { return fallback; }
  CGFloat n = [(NSNumber *)value doubleValue];
  if (n <= 0) { return fallback; }
  return (n > 1.0) ? n / 100.0 : n;         // accept both 0..1 and 0..100
}

static UIWindowScene *MFForegroundWindowScene(void)
{
  if (![NSThread isMainThread]) { return nil; }
  for (UIScene *scene in [UIApplication sharedApplication].connectedScenes) {
    if ([scene isKindOfClass:UIWindowScene.class] &&
        scene.activationState == UISceneActivationStateForegroundActive) {
      return (UIWindowScene *)scene;
    }
  }
  return nil;
}

#pragma mark - Pass-through window

@interface MFLyricWindow : UIWindow
@end

@implementation MFLyricWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event
{
  UIView *hit = [super hitTest:point withEvent:event];
  // Anything outside the lyric card belongs to the app underneath.
  if (hit == self || hit == self.rootViewController.view) { return nil; }
  return hit;
}
@end

#pragma mark - Overlay controller (main thread only)

@interface MFLyricOverlay : NSObject
@property (nonatomic, strong) MFLyricWindow *window;
@property (nonatomic, strong) UIView *card;
@property (nonatomic, strong) UILabel *label;
@property (nonatomic, assign) CGFloat topPercent;
@property (nonatomic, assign) CGFloat leftPercent;
@property (nonatomic, assign) CGFloat widthPercent;
@property (nonatomic, assign) CGFloat fontSize;
@property (nonatomic, assign) NSTextAlignment alignment;
+ (instancetype)shared;
- (void)showWithText:(NSString *)text config:(NSDictionary *)config;
- (void)hide;
- (void)setText:(NSString *)text;
- (void)applyLayout;
@end

@implementation MFLyricOverlay

+ (instancetype)shared
{
  static MFLyricOverlay *instance;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ instance = [[MFLyricOverlay alloc] init]; });
  return instance;
}

- (instancetype)init
{
  if ((self = [super init])) {
    _topPercent   = 0.06;
    _leftPercent  = 0.10;
    _widthPercent = 0.80;
    _fontSize     = 16.0;
    _alignment    = NSTextAlignmentCenter;
  }
  return self;
}

- (void)ensureViews
{
  if (self.window) { return; }

  CGRect screen = [UIScreen mainScreen].bounds;
  UIWindowScene *scene = MFForegroundWindowScene();
  MFLyricWindow *window = scene
    ? [[MFLyricWindow alloc] initWithWindowScene:scene]
    : [[MFLyricWindow alloc] initWithFrame:screen];
  window.frame = screen;
  window.backgroundColor = [UIColor clearColor];
  window.windowLevel = UIWindowLevelStatusBar + 100;
  window.hidden = NO;                 // deliberately NOT makeKeyAndVisible

  UIViewController *root = [[UIViewController alloc] init];
  root.view.backgroundColor = [UIColor clearColor];
  window.rootViewController = root;

  UIView *card = [[UIView alloc] initWithFrame:CGRectZero];
  card.backgroundColor = [[UIColor blackColor] colorWithAlphaComponent:0.55];
  card.layer.cornerRadius = 12.0;
  card.layer.masksToBounds = YES;
  card.layer.shadowColor = [UIColor blackColor].CGColor;
  card.layer.shadowOpacity = 0.25;
  card.layer.shadowRadius = 6.0;

  UILabel *label = [[UILabel alloc] initWithFrame:CGRectZero];
  label.textColor = [UIColor whiteColor];
  label.font = [UIFont boldSystemFontOfSize:self.fontSize];
  label.textAlignment = self.alignment;
  label.numberOfLines = 3;
  label.lineBreakMode = NSLineBreakByTruncatingTail;
  label.backgroundColor = [UIColor clearColor];
  [card addSubview:label];

  UIPanGestureRecognizer *pan =
    [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(handlePan:)];
  [card addGestureRecognizer:pan];
  [root.view addSubview:card];

  self.window = window;
  self.card = card;
  self.label = label;
  [self applyLayout];
}

- (void)handlePan:(UIPanGestureRecognizer *)gesture
{
  if (gesture.state != UIGestureRecognizerStateChanged) { return; }
  UIView *card = self.card;
  CGPoint t = [gesture translationInView:card.superview];
  CGRect f = card.frame;
  f.origin.x += t.x;
  f.origin.y += t.y;

  CGRect bounds = card.superview.bounds;
  CGFloat maxX = bounds.size.width - f.size.width;
  CGFloat maxY = bounds.size.height - f.size.height;
  f.origin.x = MIN(MAX(0, f.origin.x), MAX(0, maxX));
  f.origin.y = MIN(MAX(0, f.origin.y), MAX(0, maxY));
  card.frame = f;
  [gesture setTranslation:CGPointZero inView:card.superview];
}

- (void)applyLayout
{
  if (!self.card) { return; }
  CGRect bounds = self.card.superview.bounds;
  CGFloat width = bounds.size.width * self.widthPercent;
  CGFloat height = MAX(44.0, self.fontSize * 3.4);
  CGFloat x = bounds.size.width * self.leftPercent;
  CGFloat y = bounds.size.height * self.topPercent;
  self.card.frame = CGRectMake(x, y, width, height);
  self.label.frame = CGRectMake(10, 4, width - 20, height - 8);
}

- (void)showWithText:(NSString *)text config:(NSDictionary *)config
{
  [self ensureViews];
  if ([config isKindOfClass:NSDictionary.class]) {
    self.topPercent   = MFPercent(config[@"topPercent"], self.topPercent);
    self.leftPercent  = MFPercent(config[@"leftPercent"], self.leftPercent);
    self.widthPercent = MFPercent(config[@"widthPercent"], self.widthPercent);
    id size = config[@"fontSize"];
    if ([size isKindOfClass:NSNumber.class]) {
      CGFloat f = [size doubleValue];
      if (f >= 8 && f <= 48) { self.fontSize = f; }
    }
    id align = config[@"align"];
    if ([align isKindOfClass:NSNumber.class]) {
      switch ([align intValue]) {
        case 3:  self.alignment = NSTextAlignmentLeft; break;
        case 5:  self.alignment = NSTextAlignmentRight; break;
        default: self.alignment = NSTextAlignmentCenter; break;
      }
    }
    self.label.textColor = MFColorFromValue(config[@"color"], self.label.textColor);
    self.card.backgroundColor =
      MFColorFromValue(config[@"backgroundColor"], self.card.backgroundColor);
  }
  self.label.font = [UIFont boldSystemFontOfSize:self.fontSize];
  self.label.textAlignment = self.alignment;
  [self applyLayout];
  self.window.hidden = NO;
  [self setText:text];
}

- (void)hide
{
  self.window.hidden = YES;
}

- (void)setText:(NSString *)text
{
  [self ensureViews];
  self.label.text = [text isKindOfClass:NSString.class] ? text : @"";
}

@end

#pragma mark - React Native module

@implementation LyricUtilModule

RCT_EXPORT_MODULE(LyricUtil);

static void MFOnMain(dispatch_block_t block)
{
  if ([NSThread isMainThread]) { block(); }
  else { dispatch_async(dispatch_get_main_queue(), block); }
}

RCT_EXPORT_METHOD(showStatusBarLyric:(NSString *)initLyric
                  config:(NSDictionary *)config
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{ [[MFLyricOverlay shared] showWithText:initLyric ?: @"" config:config]; });
  resolve(nil);
}

RCT_EXPORT_METHOD(hideStatusBarLyric:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{ [[MFLyricOverlay shared] hide]; });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricText:(NSString *)lyric
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{ [[MFLyricOverlay shared] setText:lyric]; });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricTop:(nonnull NSNumber *)percent
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    [MFLyricOverlay shared].topPercent = MFPercent(percent, 0.06);
    [[MFLyricOverlay shared] applyLayout];
  });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricLeft:(nonnull NSNumber *)percent
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    [MFLyricOverlay shared].leftPercent = MFPercent(percent, 0.10);
    [[MFLyricOverlay shared] applyLayout];
  });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricWidth:(nonnull NSNumber *)percent
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    [MFLyricOverlay shared].widthPercent = MFPercent(percent, 0.80);
    [[MFLyricOverlay shared] applyLayout];
  });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricFontSize:(nonnull NSNumber *)size
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    MFLyricOverlay *o = [MFLyricOverlay shared];
    CGFloat f = [size doubleValue];
    if (f >= 8 && f <= 48) { o.fontSize = f; }
    o.label.font = [UIFont boldSystemFontOfSize:o.fontSize];
    [o applyLayout];
  });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarLyricAlign:(nonnull NSNumber *)alignment
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    MFLyricOverlay *o = [MFLyricOverlay shared];
    o.alignment = ([alignment intValue] == 3) ? NSTextAlignmentLeft
                : ([alignment intValue] == 5) ? NSTextAlignmentRight
                : NSTextAlignmentCenter;
    o.label.textAlignment = o.alignment;
  });
  resolve(nil);
}

RCT_EXPORT_METHOD(setStatusBarColors:(id)textColor
                  backgroundColor:(id)backgroundColor
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  MFOnMain(^{
    MFLyricOverlay *o = [MFLyricOverlay shared];
    [o ensureViews];
    o.label.textColor = MFColorFromValue(textColor, o.label.textColor);
    o.card.backgroundColor = MFColorFromValue(backgroundColor, o.card.backgroundColor);
  });
  resolve(nil);
}

// An in-app overlay needs no system permission. Returning YES is what makes
// the existing "desktop lyrics" toggle in upstream settings actually work.
RCT_EXPORT_METHOD(checkSystemAlertPermission:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  resolve(@YES);
}

RCT_EXPORT_METHOD(requestSystemAlertPermission:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  resolve(@YES);
}

@end
