#import "MusicFreeLiveActivityModule.h"
#import <React/RCTBridgeModule.h>
#import <UIKit/UIKit.h>

/**
 * See header. The Swift file MusicFreeLiveActivityController.swift registers
 * @objc(MFLiveActivityController); NSClassFromString finds it only when that
 * file has been added to the main app target. Otherwise every call no-ops.
 */
static Class MFLiveControllerClass(void)
{
  static Class cached;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    cached = NSClassFromString(@"MFLiveActivityController");
  });
  return cached;
}

@implementation MusicFreeLiveActivityModule

RCT_EXPORT_MODULE(MusicFreeLiveActivity);

RCT_EXPORT_METHOD(start:(NSString *)title artist:(NSString *)artist)
{
  Class controller = MFLiveControllerClass();
  if (!controller) { return; }
  SEL sel = NSSelectorFromString(@"startWithTitle:artist:");
  if (![controller respondsToSelector:sel]) { return; }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
  [controller performSelector:sel
                   withObject:([title isKindOfClass:NSString.class] ? title : @"MusicFree")
                   withObject:([artist isKindOfClass:NSString.class] ? artist : @"")];
#pragma clang diagnostic pop
}

RCT_EXPORT_METHOD(updateLyric:(NSString *)lyric)
{
  Class controller = MFLiveControllerClass();
  if (!controller) { return; }
  SEL sel = NSSelectorFromString(@"updateLyric:");
  if (![controller respondsToSelector:sel]) { return; }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
  [controller performSelector:sel
                   withObject:([lyric isKindOfClass:NSString.class] ? lyric : @"")];
#pragma clang diagnostic pop
}

RCT_EXPORT_METHOD(stop)
{
  Class controller = MFLiveControllerClass();
  if (!controller) { return; }
  SEL sel = NSSelectorFromString(@"stop");
  if (![controller respondsToSelector:sel]) { return; }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
  [controller performSelector:sel];
#pragma clang diagnostic pop
}

RCT_EXPORT_METHOD(isAvailable:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  // Cheap capability check that avoids NSInvocation / objc_msgSend casts:
  // the Swift controller is only linked when the extension was wired in, and
  // Live Activities require iOS 16.1+.
  BOOL linked = (MFLiveControllerClass() != Nil);
  BOOL osOK = [[UIDevice currentDevice].systemVersion
                compare:@"16.1" options:NSNumericSearch] != NSOrderedAscending;
  resolve(@(linked && osOK));
}

@end
