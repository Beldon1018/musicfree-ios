#import "NativeUtilsModule.h"
#import <UIKit/UIKit.h>

/**
 * iOS counterpart of android/.../utils/UtilsModule.kt ("NativeUtils").
 *
 * getWindowDimensions is declared isBlockingSynchronousMethod upstream, so it
 * must be exported as a blocking synchronous method here too.
 */
@implementation NativeUtilsModule

RCT_EXPORT_MODULE(NativeUtils);

- (NSDictionary *)currentDimensions
{
  CGRect bounds = UIScreen.mainScreen.bounds;
  return @{ @"width": @(CGRectGetWidth(bounds)), @"height": @(CGRectGetHeight(bounds)) };
}

RCT_EXPORT_BLOCKING_SYNCHRONOUS_METHOD(getWindowDimensions)
{
  __block NSDictionary *result;
  if ([NSThread isMainThread]) {
    result = [self currentDimensions];
  } else {
    dispatch_sync(dispatch_get_main_queue(), ^{
      result = [self currentDimensions];
    });
  }
  return result;
}

RCT_EXPORT_METHOD(checkStoragePermission:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  // The app sandbox always grants access to its own Documents / Caches dirs.
  resolve(@YES);
}

RCT_EXPORT_METHOD(requestStoragePermission)
{
  // No runtime storage permission on iOS.
}

RCT_EXPORT_METHOD(exitApp)
{
  // iOS does not allow an application to terminate itself.
}

@end
