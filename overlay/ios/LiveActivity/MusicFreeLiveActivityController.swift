import Foundation
import ActivityKit

/// Main-app-side ActivityKit controller (batch 2).
///
/// Add this file to the MAIN app target only. The Objective-C RN module
/// resolves this class by name at runtime via NSClassFromString, so no
/// generated "-Swift.h" import is required.
///
/// Design notes
/// ------------
/// * ONE entry point: `applyState(_ json:)` receives a partial JSON patch.
///   Adding a field to the Lock Screen UI no longer requires touching the
///   Objective-C bridge (performSelector only supports two object arguments).
/// * `start` is IDEMPOTENT: if an activity already exists it is *updated*,
///   never ended and re-requested. Player retries / hot reload / repeated
///   `showStatusBarLyric` can no longer stack cards.
/// * All mutable state lives on the main queue. The RN bridge dispatches every
///   call there; ActivityKit and SwiftUI expect the same.
/// * High-frequency lyric patches are throttled to 250 ms because batch 2
///   raises RNTP's progress interval to 4 Hz. Metadata and play/pause
///   transitions bypass the throttle — they are rare and must not be dropped.
/// * Updates are local (pushType: nil); a sideloaded IPA has no APNs cert.
@objc(MFLiveActivityController)
final class MFLiveActivityController: NSObject {

    /// Every field is optional: a partial patch changes only what it carries.
    /// An empty string explicitly clears an optional line (JSON null cannot be
    /// distinguished from "field absent" with a plain `String?` decoder).
    private struct StatePatch: Codable {
        var action: String?
        var title: String?
        var artist: String?
        var lyric: String?
        var translation: String?
        var previousLyric: String?
        var nextLyric: String?
        var isPlaying: Bool?
        var duration: Double?
        var elapsed: Double?
    }

    /// Plain Swift value (no ActivityKit types), so the class itself does not
    /// need an availability annotation even though the app deploys to 15.1.
    private struct Snapshot {
        var title = "MusicFree"
        var artist = ""
        var lyric = ""
        var translation: String?
        var previousLyric: String?
        var nextLyric: String?
        var isPlaying = true
        var duration = 0.0
        var elapsed = 0.0
    }

    private static var snapshot = Snapshot()
    private static var lastUpdate: Date = .distantPast
    private static let minimumInterval: TimeInterval = 0.25
    private static var wantsActivity = false

    @objc static func isAvailable() -> Bool {
        if #available(iOS 16.1, *) {
            return ActivityAuthorizationInfo().areActivitiesEnabled
        }
        return false
    }

    // MARK: - Single patch entry point

    @objc static func applyState(_ json: String) {
        guard let data = json.data(using: .utf8),
              let patch = try? JSONDecoder().decode(StatePatch.self, from: data) else {
            NSLog("[MusicFree] Live Activity: malformed state patch ignored")
            return
        }
        if Thread.isMainThread {
            handle(patch)
        } else {
            DispatchQueue.main.async { handle(patch) }
        }
    }

    private static func handle(_ patch: StatePatch) {
        guard #available(iOS 16.1, *) else { return }

        if patch.action == "stop" {
            wantsActivity = false
            snapshot = Snapshot()
            lastUpdate = .distantPast
            for activity in Activity<MusicFreeLyricAttributes>.activities {
                Task { await activity.end(dismissalPolicy: .immediate) }
            }
            return
        }

        let startRequested = patch.action == "start"
        let hasMeta = patch.title != nil || patch.artist != nil
        let hasPlayState = patch.isPlaying != nil

        if !startRequested && !hasMeta && !hasPlayState &&
            Date().timeIntervalSince(lastUpdate) < minimumInterval {
            return
        }

        if let value = patch.title { snapshot.title = value }
        if let value = patch.artist { snapshot.artist = value }
        if let value = patch.lyric { snapshot.lyric = value }
        if let value = patch.translation { snapshot.translation = nilIfEmpty(value) }
        if let value = patch.previousLyric { snapshot.previousLyric = nilIfEmpty(value) }
        if let value = patch.nextLyric { snapshot.nextLyric = nilIfEmpty(value) }
        if let value = patch.isPlaying { snapshot.isPlaying = value }
        if let value = patch.duration { snapshot.duration = max(0, value) }
        if let value = patch.elapsed { snapshot.elapsed = max(0, value) }
        if startRequested { wantsActivity = true }

        let state = MusicFreeLyricAttributes.ContentState(
            title: snapshot.title,
            artist: snapshot.artist,
            lyric: snapshot.lyric,
            translation: snapshot.translation,
            previousLyric: snapshot.previousLyric,
            nextLyric: snapshot.nextLyric,
            isPlaying: snapshot.isPlaying,
            duration: snapshot.duration,
            elapsed: snapshot.elapsed)

        let activities = Activity<MusicFreeLyricAttributes>.activities
        if activities.isEmpty {
            // Only an explicit "start" may create an activity. A stray lyric
            // event after the user closed desktop lyrics must NOT resurrect it.
            guard startRequested, wantsActivity, isAvailable() else { return }
            do {
                _ = try Activity.request(
                    attributes: MusicFreeLyricAttributes(source: "MusicFree"),
                    contentState: state,
                    pushType: nil)
            } catch {
                NSLog("[MusicFree] Live Activity start failed: %@",
                      String(describing: error))
            }
        } else {
            for activity in activities {
                Task { await activity.update(using: state) }
            }
        }
        lastUpdate = Date()
    }

    private static func nilIfEmpty(_ value: String) -> String? {
        value.isEmpty ? nil : value
    }

    // MARK: - Legacy shims (kept so an older JS bundle still works)

    private static func encode(_ fields: [String: Any]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: fields),
              let json = String(data: data, encoding: .utf8) else { return "{}" }
        return json
    }

    @objc static func start(title: String, artist: String) {
        applyState(encode(["action": "start", "title": title, "artist": artist]))
    }

    @objc static func updateLyric(_ lyric: String) {
        applyState(encode(["lyric": lyric]))
    }

    @objc static func stop() {
        applyState(encode(["action": "stop"]))
    }
}
