# Dynamic Island / Lock Screen lyrics (Live Activity)

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
silently no-opped — which is why the Dynamic Island showed nothing. A missing
`.appex` is now a **hard failure** in `scripts/verify_ipa.py`.

Because `inject_ios.py`/`prepare.sh` re-checkout upstream on every sync, the
project wiring lives in `scripts/inject_live_activity.py` (not in the
regenerated `project.pbxproj`).

## Batch 2 state contract

All UI data lives in `ContentState`, **not** in `ActivityAttributes`.
ActivityKit freezes attributes at `Activity.request`, so keeping `title` /
`artist` there meant a track change could never refresh the Lock Screen card and
the only workaround was end + request — which stacked cards on player retries.

The RN side owns the state in exactly one place:
`overlay/src/native/liveActivity/index.ios.ts`. It is installed once from
`bootstrap.ts` (module-scoped `installed` guard) and calls the native bridge's
single method `applyState(jsonString)` with a **partial** JSON patch:

```jsonc
{
  "action": "start",          // "start" | "stop"; omit for a plain update
  "title": "Song",            // track change -> idempotent update, NOT a new activity
  "artist": "Artist",
  "lyric": "current line",
  "translation": "",          // "" clears an optional line
  "previousLyric": "",
  "nextLyric": "",
  "isPlaying": true,
  "duration": 235.0,
  "elapsed": 42.5
}
```

`MusicFreeLiveActivityModule.m` dispatches every call to the main queue;
`MusicFreeLiveActivityController.swift` merges the patch into a snapshot,
throttles high-frequency updates to 250 ms, and either updates the existing
activity or requests one **only** on an explicit `start`. A stray lyric event
after the user closed desktop lyrics can no longer resurrect a card.

`start` / `updateLyric` / `stop` remain exported as compatibility shims; they
build the same JSON patch internally.

### Why the progress bar is a plain `ProgressView(value:)`

`batch 2` raises RNTP's `progressUpdateEventInterval` from 1 s to 0.25 s (O2),
but a 4 Hz event stream is **not** forwarded 1:1 to ActivityKit. The bridge
emits at most ~1 Hz (progress heartbeat) plus an immediate update on track
change, lyric-line change, play/pause and seek. The Widget renders
`ProgressView(value: elapsed / duration)`. The iOS-16-only
`ProgressView(timerInterval:)` initializer is deliberately avoided: this
machine has no iOS SDK for type-checking, so only APIs available well before
the extension's 16.1 deployment target are used.

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
     (both come from `ADAPTER_VERSION` / `ADAPTER_BUILD`)
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
- The Widget's private subviews/helpers carry the same annotation so a type
  declaration never references an availability-gated `ContentState` unguarded.
- `IPHONEOS_DEPLOYMENT_TARGET` for the extension must be ≥ 16.1 (ActivityKit).

## Runtime behaviour & limits

| Item | Value |
| --- | --- |
| Minimum OS | iOS 16.1 (Lock Screen on all devices; Dynamic Island needs iPhone 14 Pro or later) |
| Updates | Local `Activity.update`, no APNs / push certificate — works on sideloaded builds |
| Progress events | 4 Hz from RNTP after O2; lyric accuracy better than 0.3 s |
| State updates | ~1 Hz heartbeat + immediate on track/line/play-state/seek; 250 ms Swift-side throttle |
| Background | `UIBackgroundModes = audio` keeps the process alive |
| State size | short strings + 3 numbers, comfortably under the 4 KB budget |
| Progress bar | static `ProgressView(value:)`, driven by the 1 Hz `elapsed` value |
| Dismiss | `action: "stop"` on queue end, stopped state, or desktop-lyric toggle off |

### Sideloading caveat

A Widget Extension is a separate `.appex` that must be signed together with the
app. AltStore handles this; with Sideloadly / manual `codesign` you must sign
the `.appex` first, then the `.app`, then repack `Payload/`. A free 7-day
personal certificate works — no special entitlement is needed because we do
not use push-based updates. **Do not strip the `.appex`**: `verify_ipa.py` now
rejects such a package, and Dynamic Island / Lock Screen lyrics would silently
disappear. Full commands and the second entitlement are in
`docs/signing-and-crash-guide.html` §3.2.

### Verification

- `NativeModules.MusicFreeLiveActivity.isAvailable()` → `true` when linked and on iOS 16.1+
- Play a track, enable "开启桌面歌词" in settings, lock the device: the real
  track title/artist, current + translated + neighbouring lines, play/pause
  state and progress bar should appear on the Lock Screen / Dynamic Island.
- Switching tracks updates the SAME card (no flicker, no stacked cards).
- Pausing shows 已暂停 and freezes the progress bar; ending playback dismisses
  the card.
- If the user disabled Live Activities in system Settings,
  `ActivityAuthorizationInfo().areActivitiesEnabled` is `false` and the
  controller quietly skips starting an activity.
