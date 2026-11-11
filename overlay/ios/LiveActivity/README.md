# Optional: Dynamic Island / Lock Screen lyrics (Live Activity)

These files implement the iOS-native stand-in for Android's floating/status-bar
lyrics. They are **wired into the Xcode project automatically** by
`scripts/inject_live_activity.py`, which `prepare.sh` runs on every sync:

- `MusicFreeLyricAttributes.swift` and `MusicFreeLiveActivityController.swift`
  are compiled into the **main app** target (the controller registers
  `@objc(MFLiveActivityController)`; `MusicFreeLiveActivityModule.m` resolves it
  via `NSClassFromString`).
- A **Widget Extension target `MusicFreeLiveActivity`** is created with these
  sources, and the resulting `.appex` is embedded into `PlugIns` through an
  "Embed App Extensions" copy phase.
- `NSSupportsLiveActivities` / `NSSupportsLiveActivitiesFrequentUpdates` are
  injected into the app `Info.plist` by `scripts/inject_ios.py`.

Before this wiring existed the Swift files were present but compiled into no
target at all, so `MFLiveActivityController` was always `nil` and every call
silently no-opped — which is why the Dynamic Island showed nothing.

Because `inject_ios.py`/`prepare.sh` re-checkout upstream on every sync, the
project wiring lives in `scripts/inject_live_activity.py` (not in the
regenerated `project.pbxproj`).

## Manual wiring (reference only)

You should not need this; it documents what the script does, for debugging a
future upstream change.

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
   `MusicFreeLiveActivity.appex` with destination `PlugIns`.
6. **App Info.plist** — `NSSupportsLiveActivities` and
   `NSSupportsLiveActivitiesFrequentUpdates` are already injected by
   `scripts/inject_ios.py`; do not remove them.
7. Re-run `pod install`, then `bash scripts/build_unsigned_ipa.sh`.

### Compilation notes

- `MusicFreeLyricAttributes.swift` carries `@available(iOS 16.1, *)` because it
  is also compiled into the app target, whose deployment target is still 15.1.
  Without the annotation the app target fails to compile (`ActivityAttributes`
  does not exist before 16.1) — this is the one non-obvious requirement.
- `IPHONEOS_DEPLOYMENT_TARGET` for the extension must be ≥ 16.1 (ActivityKit).


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
