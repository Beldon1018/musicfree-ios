#import <Foundation/Foundation.h>
#import <React/RCTBridgeModule.h>

/**
 * Optional React Native bridge for the Dynamic Island / Live Activity feature.
 *
 * It resolves the Swift controller by class name at runtime, so compiling this
 * file into the app is harmless even when the Widget Extension is NOT added:
 * every method becomes a silent no-op. No "-Swift.h" import, no target
 * dependency, no change to the default unsigned IPA build.
 */
@interface MusicFreeLiveActivityModule : NSObject <RCTBridgeModule>
@end
