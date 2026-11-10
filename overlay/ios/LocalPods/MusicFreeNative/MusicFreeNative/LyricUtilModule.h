#import <Foundation/Foundation.h>
#import <React/RCTBridgeModule.h>

/**
 * iOS counterpart of android/.../lyricUtil/LyricUtilModule.kt ("LyricUtil").
 *
 * Android draws a system-wide overlay window (SYSTEM_ALERT_WINDOW). iOS has no
 * public equivalent, so this module draws a draggable lyric overlay in the
 * app's own UIWindow instead. It keeps the exact same JS API surface.
 */
@interface LyricUtilModule : NSObject <RCTBridgeModule>
@end
