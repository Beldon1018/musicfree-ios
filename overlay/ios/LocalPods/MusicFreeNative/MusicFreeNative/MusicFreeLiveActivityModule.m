#import "MusicFreeLiveActivityModule.h"
#import <React/RCTBridgeModule.h>
#import <UIKit/UIKit.h>

/**
 * React Native bridge for the Dynamic Island / Live Activity feature.
 *
 * The Swift controller is resolved by class name at runtime
 * (@objc(MFLiveActivityController)), so no generated "-Swift.h" import is
 * needed and this file compiles harmlessly even if the Swift source were ever
 * dropped from the app target — every call would simply no-op.
 *
 * Batch 2: `applyState:` is the single real entry point. The Swift side takes
 * a partial JSON patch, so adding a Lock Screen field never requires another
 * performSelector signature here (performSelector supports at most two object
 * arguments). start/updateLyric/stop remain as compatibility shims for an
 * older JS bundle.
 *
 * Every call is dispatched to the main queue: ActivityKit + the controller's
 * state snapshot are main-queue confined, while RN bridge methods arrive on
 * a module-specific background queue.
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

/** Invoke a one-object-argument controller selector on the main queue. */
static void MFDispatch1(SEL sel, id object)
{
  Class controller = MFLiveControllerClass();
  if (!controller || ![controller respondsToSelector:sel]) { return; }
  dispatch_async(dispatch_get_main_queue(), ^{
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
    [controller performSelector:sel withObject:object];
#pragma clang diagnostic pop
  });
}

static NSString *MFSafeString(id value, NSString *fallback)
{
  return [value isKindOfClass:NSString.class] ? (NSString *)value : fallback;
}

static NSString *MFJSON(NSDictionary *fields)
{
  NSError *error = nil;
  NSData *data = [NSJSONSerialization dataWithJSONObject:fields
                                                 options:0
                                                   error:&error];
  if (!data || error) { return @"{}"; }
  return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{}";
}

@implementation MusicFreeLiveActivityModule

RCT_EXPORT_MODULE(MusicFreeLiveActivity);

RCT_EXPORT_METHOD(applyState:(NSString *)stateJson)
{
  MFDispatch1(NSSelectorFromString(@"applyState:"),
              MFSafeString(stateJson, @"{}"));
}

RCT_EXPORT_METHOD(start:(NSString *)title artist:(NSString *)artist)
{
  NSString *patch = MFJSON(@{
    @"action": @"start",
    @"title": MFSafeString(title, @"MusicFree"),
    @"artist": MFSafeString(artist, @""),
  });
  MFDispatch1(NSSelectorFromString(@"applyState:"), patch);
}

RCT_EXPORT_METHOD(updateLyric:(NSString *)lyric)
{
  MFDispatch1(NSSelectorFromString(@"applyState:"),
              MFJSON(@{@"lyric": MFSafeString(lyric, @"")}));
}

RCT_EXPORT_METHOD(stop)
{
  MFDispatch1(NSSelectorFromString(@"applyState:"),
              MFJSON(@{@"action": @"stop"}));
}

RCT_EXPORT_METHOD(isAvailable:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  BOOL linked = (MFLiveControllerClass() != Nil);
  BOOL osOK = [[UIDevice currentDevice].systemVersion
                compare:@"16.1" options:NSNumericSearch] != NSOrderedAscending;
  resolve(@(linked && osOK));
}

@end
