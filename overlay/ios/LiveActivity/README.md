# Optional: Dynamic Island / Lock Screen lyrics (Live Activity)

These files implement the iOS-native stand-in for Android's floating/status-bar
lyrics. They are **shipped but not wired into any Xcode target by default**:

- `MusicFreeNative/MusicFreeLiveActivityModule.{h,m}` IS compiled into the app
  (it is part of the local pod). It resolves the Swift controller via
  `NSClassFromString`, so with no extension present every call is a silent
  no-op. The default unsigned-IPA build is therefore unaffected.
- The three `.swift` files + `Info.plist` here are source material. Add them to
  targets as described below to turn the feature on.

## Wiring it up (once, in Xcode)

Do this on a machine with full Xcode. Prefer the GUI / XcodeGen over hand-editing
`project.pbxproj` — adding an app extension target touches ~10 project sections.

1. **File → New → Target → Widget Extension**
   - Product name: `MusicFreeLiveActivity`
   - Bundle identifier: a child of the app id, e.g. `com.musicfree.ios.unsigned.lyrics`
   - Uncheck "Include Live Activity" (we supply our own files); delete the
     template Swift files Xcode generates.
2. **Target Membership**
   - `MusicFreeLyricAttributes.swift` → **both** the main app and the extension
   - `MusicFreeLiveActivityController.swift` → **main app only**
   - `MusicFreeLiveActivityWidget.swift` → **extension only**
3. **Extension Info.plist** — use the `Info.plist` in this directory, or ensure:
   - `NSExtensionPointIdentifier` = `com.apple.widgetkit-extension`
   - `MinimumOSVersion` = `16.1`
4. **Build settings for the extension**
   - `IPHONEOS_DEPLOYMENT_TARGET` = `16.1`
   - `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` identical to the main app
5. **Main app Build Phases** — verify "Embed App Extensions" contains
   `MusicFreeLiveActivity.appex` with "Copy only when installing" / destination
   `PlugIns`. Xcode normally adds this automatically.
6. **App Info.plist** — `NSSupportsLiveActivities` and
   `NSSupportsLiveActivitiesFrequentUpdates` are already injected by
   `scripts/inject_ios.py`; do not remove them.
7. Re-run `pod install`, then `bash scripts/build_unsigned_ipa.sh`.

Because `inject_ios.py` and `prepare.sh` re-checkout upstream on every sync,
keep these files in `overlay/ios/LiveActivity/` (they are copied back each run).
The Xcode target wiring lives in `upstream/ios/MusicFree.xcodeproj`, which is
regenerated from upstream — so either commit a small pbxproj injection step or
re-apply step 1–5 after a major upstream change.

## Runtime behaviour & limits

| Item | Value |
| --- | --- |
| Minimum OS | iOS 16.1 (Lock Screen on all devices; Dynamic Island needs iPhone 14 Pro or later) |
| Updates | Local `Activity.update`, no APNs / push certificate — works on sideloaded builds |
| Throttle | 1 s minimum + dedupe on identical text, to fit ActivityKit's update budget |
| Background | `UIBackgroundModes = audio` keeps the process alive; lyric lines come from upstream's `PlaybackProgressUpdated` |
| State size | tiny (`lyric` + title/artist), comfortably under the 4 KB budget |

### Sideloading caveat

A Widget Extension is a separate `.appex` that must be signed together with the
app. AltStore handles this; with Sideloadly / manual `codesign` you must sign
the `.appex` first, then the `.app`, then repack `Payload/`. A free 7-day
personal certificate works — no special entitlement is needed because we do
not use push-based updates. If the extension fails to sign, leave it out: the
in-app draggable lyric overlay (`LyricUtilModule.m`) still works and the RN
bridge degrades to a no-op.

### Verification

- `NativeModules.MusicFreeLiveActivity.isAvailable()` → `true` when linked and on iOS 16.1+
- Play a local track, enable "开启桌面歌词" in settings, lock the device: the
  current lyric line should appear on the Lock Screen / Dynamic Island.
- If the user disabled Live Activities in system Settings,
  `ActivityAuthorizationInfo().areActivitiesEnabled` is `false` and the
  controller quietly skips starting an activity.
