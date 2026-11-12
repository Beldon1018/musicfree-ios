import Foundation
import ActivityKit

/// Shared between the main app target and the Widget Extension target.
///
/// Batch-2 design: EVERYTHING the UI renders lives in `ContentState`, not in
/// `ActivityAttributes`. ActivityKit freezes `attributes` at
/// `Activity.request` time, so keeping `title`/`artist` there meant a track
/// change could never refresh the Lock Screen card (it permanently read
/// "MusicFree"), and the only "fix" was end + request — which stacked cards
/// whenever the player retried. Moving them into `ContentState` lets a track
/// change be a plain `update(using:)`, with no flicker and no duplicate card.
///
/// Keep the state tiny: Live Activity updates are budgeted by the system and
/// the whole state must stay well under 4 KB.
///
/// `@available(iOS 16.1, *)` is required because the app target still deploys
/// back to iOS 15.1: ActivityAttributes does not exist before 16.1, and without
/// the annotation merely *declaring* the conformance fails to compile there.
@available(iOS 16.1, *)
struct MusicFreeLyricAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        // --- track metadata (mutable, so a track change can refresh) ---
        var title: String
        var artist: String

        // --- lyric lines ---
        var lyric: String
        var translation: String?
        var previousLyric: String?
        var nextLyric: String?

        // --- playback ---
        // `elapsed` is pushed once per second by the RN bridge (not on every
        // 4 Hz progress event), so a plain ProgressView(value:) is smooth
        // enough without timerInterval: — that SwiftUI initializer is iOS 16+
        // only and cannot be type-checked on this machine (no iOS SDK here).
        var isPlaying: Bool
        var duration: Double
        var elapsed: Double
    }

    /// Immutable for the lifetime of the activity; informational only.
    var source: String
}
