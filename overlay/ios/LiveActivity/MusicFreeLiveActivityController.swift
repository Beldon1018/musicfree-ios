import Foundation
import ActivityKit

/// Main-app-side ActivityKit controller.
///
/// Add this file to the MAIN app target only. The Objective-C RN module
/// (MusicFreeLiveActivityModule.m) resolves this class by name at runtime via
/// NSClassFromString, so no generated "-Swift.h" import is required — that
/// keeps the default (extension-free) build free of Swift/ObjC bridging risk.
///
/// Updates are local (no APNs / push token), which matters for a sideloaded
/// unsigned IPA. Background audio keeps the app alive so lyric-line updates
/// keep arriving; the 1 s throttle avoids ActivityKit's update budget.
@objc(MFLiveActivityController)
final class MFLiveActivityController: NSObject {

    private static var lastLyric: String = ""
    private static var lastUpdate: Date = .distantPast
    private static let minimumInterval: TimeInterval = 1.0

    @objc static func isAvailable() -> Bool {
        if #available(iOS 16.1, *) {
            return ActivityAuthorizationInfo().areActivitiesEnabled
        }
        return false
    }

    @objc static func start(title: String, artist: String) {
        guard #available(iOS 16.1, *), isAvailable() else { return }

        for activity in Activity<MusicFreeLyricAttributes>.activities {
            Task { await activity.end(dismissalPolicy: .immediate) }
        }

        let attributes = MusicFreeLyricAttributes(title: title, artist: artist)
        let state = MusicFreeLyricAttributes.ContentState(
            lyric: "", previousLyric: nil, isPlaying: true)
        do {
            _ = try Activity.request(
                attributes: attributes,
                contentState: state,
                pushType: nil)
            lastLyric = ""
            lastUpdate = .distantPast
        } catch {
            NSLog("[MusicFree] Live Activity start failed: %@", String(describing: error))
        }
    }

    @objc static func updateLyric(_ lyric: String) {
        guard #available(iOS 16.1, *) else { return }
        let now = Date()
        if lyric == lastLyric || now.timeIntervalSince(lastUpdate) < minimumInterval {
            return
        }
        lastLyric = lyric
        lastUpdate = now

        let state = MusicFreeLyricAttributes.ContentState(
            lyric: lyric, previousLyric: nil, isPlaying: true)
        for activity in Activity<MusicFreeLyricAttributes>.activities {
            Task { await activity.update(using: state) }
        }
    }

    @objc static func stop() {
        guard #available(iOS 16.1, *) else { return }
        for activity in Activity<MusicFreeLyricAttributes>.activities {
            Task { await activity.end(dismissalPolicy: .immediate) }
        }
        lastLyric = ""
        lastUpdate = .distantPast
    }
}
