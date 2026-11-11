import Foundation
import ActivityKit

/// Shared between the main app target and the Widget Extension target.
/// Add this file to BOTH targets' "Compile Sources" build phase.
///
/// Keep the ContentState tiny: Live Activity updates are budgeted by the system
/// and the whole state must stay well under 4 KB.
///
/// `@available(iOS 16.1, *)` is required because the app target still deploys
/// back to iOS 15.1: ActivityAttributes does not exist before 16.1, and without
/// the annotation merely *declaring* the conformance fails to compile there.
@available(iOS 16.1, *)
struct MusicFreeLyricAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var lyric: String
        var previousLyric: String?
        var isPlaying: Bool
    }

    var title: String
    var artist: String
}
