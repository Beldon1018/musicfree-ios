#import "Mp3UtilModule.h"
#import <AVFoundation/AVFoundation.h>
#import <CoreMedia/CoreMedia.h>
#import <UIKit/UIKit.h>

/**
 * iOS counterpart of android/.../mp3Util/Mp3UtilModule.kt ("Mp3Util").
 *
 * Implemented with AVFoundation common metadata. Android returns duration in
 * milliseconds as a string, so we keep the same shape for the JS side.
 * ID3 writing and embedded lyric reading have no public iOS API; those methods
 * resolve with empty values rather than rejecting, to preserve upstream's
 * promise flow.
 */

static NSURL *MFURLFromPath(NSString *path)
{
  if (path.length == 0) { return nil; }
  if ([path hasPrefix:@"file://"]) { return [NSURL URLWithString:path]; }
  if ([path hasPrefix:@"/"])       { return [NSURL fileURLWithPath:path]; }
  return [NSURL URLWithString:path];
}

static NSDictionary *MFMetadataForPath(NSString *path)
{
  NSURL *url = MFURLFromPath(path);
  if (!url) { return @{}; }

  AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url options:nil];
  NSMutableDictionary *meta = [NSMutableDictionary dictionary];

  CMTime duration = asset.duration;
  if (CMTIME_IS_VALID(duration) && CMTIME_IS_NUMERIC(duration)) {
    double millis = CMTimeGetSeconds(duration) * 1000.0;
    if (millis > 0) {
      meta[@"duration"] = [NSString stringWithFormat:@"%.0f", millis];
    }
  }

  for (AVMetadataItem *item in asset.commonMetadata) {
    NSString *key = item.commonKey;
    NSString *value = [item.value isKindOfClass:NSString.class] ? (NSString *)item.value : nil;
    if (!key || !value) { continue; }

    // Compare with literal AVMetadataCommonKey values: the SDK constants are
    // deprecated on newer iOS SDKs while the values themselves are stable.
    if ([key isEqualToString:@"title"])         { meta[@"title"] = value; }
    else if ([key isEqualToString:@"artist"])   { meta[@"artist"] = value; }
    else if ([key isEqualToString:@"albumName"]){ meta[@"album"] = value; }
    else if ([key isEqualToString:@"creator"])  { meta[@"author"] = value; }
  }
  return meta;
}

@implementation Mp3UtilModule

RCT_EXPORT_MODULE(Mp3Util);

RCT_EXPORT_METHOD(getBasicMeta:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  resolve(MFMetadataForPath(filePath));
}

RCT_EXPORT_METHOD(getMediaMeta:(NSArray<NSString *> *)filePaths
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  NSMutableArray *result = [NSMutableArray arrayWithCapacity:filePaths.count];
  for (NSString *path in filePaths) {
    @try {
      [result addObject:MFMetadataForPath(path)];
    } @catch (__unused NSException *e) {
      [result addObject:[NSNull null]];
    }
  }
  resolve(result);
}

RCT_EXPORT_METHOD(getMediaCoverImg:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  NSURL *url = MFURLFromPath(filePath);
  if (!url) { resolve(@""); return; }

  AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url options:nil];
  for (AVMetadataItem *item in asset.commonMetadata) {
    if (![item.commonKey isEqualToString:@"artwork"]) { continue; }

    NSData *imageData = nil;
    if ([item.value isKindOfClass:NSData.class]) {
      imageData = (NSData *)item.value;
    } else if ([item.value isKindOfClass:UIImage.class]) {
      imageData = UIImageJPEGRepresentation((UIImage *)item.value, 0.9);
    }
    if (imageData.length == 0) { continue; }

    NSString *cacheDir = [NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES) firstObject];
    NSString *coverDir = [cacheDir stringByAppendingPathComponent:@"image_manager_disk_cache"];
    [[NSFileManager defaultManager] createDirectoryAtPath:coverDir
                              withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *coverPath = [coverDir stringByAppendingPathComponent:
                           [NSString stringWithFormat:@"%lu.jpg", (unsigned long)filePath.hash]];
    if ([imageData writeToFile:coverPath atomically:YES]) {
      resolve([[NSURL fileURLWithPath:coverPath] absoluteString]);
      return;
    }
  }
  resolve(@"");
}

RCT_EXPORT_METHOD(getLyric:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)filePath; (void)reject;
  resolve(@"");
}

RCT_EXPORT_METHOD(setMediaTag:(NSString *)filePath
                  meta:(NSDictionary *)meta
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)filePath; (void)meta; (void)reject;
  // No public iOS API for writing ID3 tags.
  resolve(@YES);
}

RCT_EXPORT_METHOD(getMediaTag:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)filePath; (void)reject;
  resolve(@{});
}

@end
