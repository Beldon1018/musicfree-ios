#import "Mp3UtilModule.h"
#import <AVFoundation/AVFoundation.h>
#import <CoreMedia/CoreMedia.h>
#import <UIKit/UIKit.h>

/**
 * iOS counterpart of android/.../mp3Util/Mp3UtilModule.kt ("Mp3Util").
 *
 * Two deliberate departures from Android, both forced by the platform:
 *
 *  1. READING embedded lyrics IS possible on iOS. AVFoundation exposes ID3v2
 *     USLT / SYLT and iTunes "©lyr" frames through `asset.metadata` (NOT
 *     `commonMetadata`). Android uses jaudiotagger's FieldKey.LYRICS; we read
 *     the same frames here. The earlier "no public iOS API" note was wrong.
 *
 *  2. WRITING ID3 tags back into the original file is not exposed by
 *     AVFoundation, and rewriting a user's audio binary in a sandbox is risky
 *     anyway. Instead `setMediaTag` persists an in-app metadata override in
 *     Documents/, which `getBasicMeta` / `getMediaMeta` / `getLyric` /
 *     `getMediaTag` merge on top of the file's own metadata. From the JS side
 *     the result is the same (edited title / artist / album / lyric show up),
 *     but the source file is never modified.
 */

#pragma mark - Path helpers

static NSURL *MFURLFromPath(NSString *path)
{
  if (path.length == 0) { return nil; }
  if ([path hasPrefix:@"file://"]) { return [NSURL URLWithString:path]; }
  if ([path hasPrefix:@"/"])       { return [NSURL fileURLWithPath:path]; }
  return [NSURL URLWithString:path];
}

static NSString *MFPathKey(NSString *path)
{
  if (![path isKindOfClass:NSString.class]) { return @""; }
  NSString *p = path;
  if ([p hasPrefix:@"file://"]) {
    p = [[NSURL URLWithString:p] path] ?: p;
  }
  return [p stringByStandardizingPath];
}

#pragma mark - Metadata override store (in-app, never touches the audio file)

static NSString *MFOverridesPath(void)
{
  NSString *dir = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
  return [dir stringByAppendingPathComponent:@"musicfree_meta_overrides.json"];
}

static NSMutableDictionary<NSString *, NSDictionary *> *MFOverrides(void)
{
  static NSMutableDictionary *store;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSData *data = [NSData dataWithContentsOfFile:MFOverridesPath()];
    NSDictionary *loaded = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    store = [loaded isKindOfClass:NSDictionary.class]
      ? [loaded mutableCopy]
      : [NSMutableDictionary dictionary];
  });
  return store;
}

static NSDictionary *MFOverrideForPath(NSString *path)
{
  @synchronized (MFOverrides()) {
    NSDictionary *entry = MFOverrides()[MFPathKey(path)];
    return [entry isKindOfClass:NSDictionary.class] ? entry : nil;
  }
}

static BOOL MFWriteOverrideForPath(NSString *path, NSDictionary *meta)
{
  NSMutableDictionary *clean = [NSMutableDictionary dictionary];
  for (NSString *field in @[@"title", @"artist", @"album", @"lyric", @"comment", @"author", @"duration"]) {
    id value = meta[field];
    if ([value isKindOfClass:NSString.class] && [value length] > 0) {
      clean[field] = value;
    }
  }
  @synchronized (MFOverrides()) {
    NSMutableDictionary *store = MFOverrides();
    store[MFPathKey(path)] = [clean copy];
    NSData *data = [NSJSONSerialization dataWithJSONObject:store options:0 error:nil];
    return data ? [data writeToFile:MFOverridesPath() atomically:YES] : NO;
  }
}

static NSDictionary *MFApplyOverride(NSDictionary *base, NSString *path)
{
  NSDictionary *override = MFOverrideForPath(path);
  if (!override.count) { return base; }
  NSMutableDictionary *merged = [base mutableCopy];
  for (NSString *field in @[@"title", @"artist", @"album", @"author", @"duration"]) {
    NSString *value = override[field];
    if ([value isKindOfClass:NSString.class]) { merged[field] = value; }
  }
  return merged;
}

#pragma mark - Embedded lyric decoding

/** Decode an ID3v2 USLT/SYLT payload: encoding byte + 3-byte lang + descriptor + text. */
static NSString *MFParseUSLTPayload(NSData *data)
{
  const unsigned char *bytes = (const unsigned char *)data.bytes;
  NSUInteger len = data.length;
  if (len < 5 || !bytes) { return nil; }

  NSStringEncoding encoding;
  NSUInteger unit;
  switch (bytes[0]) {
    case 0:  encoding = NSISOLatin1StringEncoding;       unit = 1; break;
    case 1:  encoding = NSUTF16StringEncoding;           unit = 2; break; // BOM present
    case 2:  encoding = NSUTF16BigEndianStringEncoding;  unit = 2; break;
    case 3:  encoding = NSUTF8StringEncoding;            unit = 1; break;
    default: encoding = NSUTF8StringEncoding;            unit = 1; break;
  }

  NSUInteger textStart = 4;
  for (NSUInteger i = 4; i + unit <= len; i += unit) {
    BOOL zero = YES;
    for (NSUInteger k = 0; k < unit; k++) {
      if (bytes[i + k] != 0) { zero = NO; break; }
    }
    if (zero) { textStart = i + unit; break; }
  }
  if (textStart >= len) { return nil; }

  NSData *textData = [data subdataWithRange:NSMakeRange(textStart, len - textStart)];
  NSString *text = [[NSString alloc] initWithData:textData encoding:encoding];
  if (!text) { text = [[NSString alloc] initWithData:textData encoding:NSUTF8StringEncoding]; }
  return text;
}

static NSString *MFStringFromMetadataValue(id value)
{
  if ([value isKindOfClass:NSString.class]) { return (NSString *)value; }
  if ([value isKindOfClass:NSData.class])   { return MFParseUSLTPayload((NSData *)value); }
  if ([value isKindOfClass:NSNumber.class]) { return [(NSNumber *)value stringValue]; }
  return nil;
}

static NSString *MFEmbeddedLyricForAsset(AVURLAsset *asset)
{
  for (AVMetadataItem *item in asset.metadata) {
    id rawKey = item.key;
    NSString *key = [rawKey isKindOfClass:NSString.class] ? (NSString *)rawKey : nil;
    if (!key) { continue; }

    NSString *upper = [key uppercaseString];
    BOOL isLyric = [upper isEqualToString:@"USLT"]
                || [upper isEqualToString:@"SYLT"]
                || [upper isEqualToString:@"LYRICS"]
                || [upper isEqualToString:@"UNSYNCEDLYRICS"]
                || [key isEqualToString:@"\u00A9lyr"];   // iTunes lyrics frame
    if (!isLyric) { continue; }

    NSString *text = MFStringFromMetadataValue(item.value);
    if (!text) { text = item.stringValue; }
    if (text.length > 0) { return text; }
  }
  return nil;
}

#pragma mark - Base metadata (AVFoundation common metadata)

static NSDictionary *MFMetadataForPath(NSString *path)
{
  NSURL *url = MFURLFromPath(path);
  if (!url) { return @{}; }

  AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url options:nil];
  NSMutableDictionary *meta = [NSMutableDictionary dictionary];

  CMTime duration = asset.duration;
  if (CMTIME_IS_VALID(duration) && CMTIME_IS_NUMERIC(duration)) {
    double millis = CMTimeGetSeconds(duration) * 1000.0;
    if (millis > 0) { meta[@"duration"] = [NSString stringWithFormat:@"%.0f", millis]; }
  }

  for (AVMetadataItem *item in asset.commonMetadata) {
    NSString *key = item.commonKey;
    NSString *value = [item.value isKindOfClass:NSString.class] ? (NSString *)item.value : nil;
    if (!key || !value) { continue; }
    if ([key isEqualToString:@"title"])          { meta[@"title"]  = value; }
    else if ([key isEqualToString:@"artist"])    { meta[@"artist"] = value; }
    else if ([key isEqualToString:@"albumName"]) { meta[@"album"]  = value; }
    else if ([key isEqualToString:@"creator"])   { meta[@"author"] = value; }
  }
  return MFApplyOverride(meta, path);
}

#pragma mark - React Native module

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
    @try { [result addObject:MFMetadataForPath(path)]; }
    @catch (__unused NSException *e) { [result addObject:@{}]; }
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
  (void)reject;
  // A user-edited lyric (stored by setMediaTag) takes precedence, mirroring
  // how an edited ID3 tag would win on Android.
  NSString *edited = MFOverrideForPath(filePath)[@"lyric"];
  if ([edited isKindOfClass:NSString.class] && edited.length > 0) {
    resolve(edited);
    return;
  }
  NSURL *url = MFURLFromPath(filePath);
  if (!url) { resolve(@""); return; }
  AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url options:nil];
  resolve(MFEmbeddedLyricForAsset(asset) ?: @"");
}

RCT_EXPORT_METHOD(setMediaTag:(NSString *)filePath
                  meta:(NSDictionary *)meta
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  if (![meta isKindOfClass:NSDictionary.class]) {
    reject(@"EINVAL", @"meta must be an object", nil);
    return;
  }
  BOOL ok = MFWriteOverrideForPath(filePath, meta);
  if (!ok) { reject(@"EIO", @"could not persist metadata override", nil); return; }
  resolve(@YES);
}

RCT_EXPORT_METHOD(getMediaTag:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  (void)reject;
  NSMutableDictionary *result = [MFMetadataForPath(filePath) mutableCopy];
  NSDictionary *override = MFOverrideForPath(filePath);
  for (NSString *field in @[@"lyric", @"comment"]) {
    NSString *value = override[field];
    if ([value isKindOfClass:NSString.class]) { result[field] = value; }
  }
  NSString *lyric = result[@"lyric"];
  if (![lyric isKindOfClass:NSString.class] || lyric.length == 0) {
    NSURL *url = MFURLFromPath(filePath);
    if (url) {
      NSString *embedded = MFEmbeddedLyricForAsset([AVURLAsset URLAssetWithURL:url options:nil]);
      if (embedded.length > 0) { result[@"lyric"] = embedded; }
    }
  }
  resolve(result);
}

@end
