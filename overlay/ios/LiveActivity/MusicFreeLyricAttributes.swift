import Foundation
import ActivityKit

/// Shared between the main app target and the Widget Extension target.
/// Add this file to BOTH targets' "Compile Sources" build phase.
///
/// Keep the ContentState tiny: Live Activity updates are budgeted by the system
/// and the whole state must stay well under 4 KB.
struct MusicFreeLyricAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var lyric: String
        var previousLyric: String?
        var isPlaying: Bool
    }

    var title: String
    var artist: String
}
