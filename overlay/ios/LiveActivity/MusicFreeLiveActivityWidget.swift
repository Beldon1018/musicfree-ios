import ActivityKit
import Foundation
import SwiftUI
import WidgetKit

/// Widget Extension entry point. Compiled into the "MusicFreeLiveActivity"
/// extension target ONLY (together with MusicFreeLyricAttributes.swift).
///
/// Batch 2: the card now shows the real track title/artist, a play/pause
/// indicator, the previous / current / translated / next lyric lines and a
/// progress bar. All of it comes from `context.state`, i.e. it can change on
/// every update without recreating the activity.
///
/// Only SwiftUI APIs available well before the extension's iOS 16.1 deployment
/// target are used: no `timerInterval` initializers, no App Intents, no App
/// Group. The progress bar is driven by a 1 Hz `elapsed` value from the RN
/// bridge instead.
@main
struct MusicFreeLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MusicFreeLyricAttributes.self) { context in
            LockScreenCard(state: context.state)
                .padding(14)
                .activityBackgroundTint(Color.black.opacity(0.72))
                .activitySystemActionForegroundColor(Color.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label(stateTitle(context.state), systemImage: "music.note")
                        .font(.caption)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Label(context.state.isPlaying ? "播放中" : "已暂停",
                          systemImage: context.state.isPlaying
                            ? "play.fill" : "pause.fill")
                        .font(.caption2)
                        .opacity(0.75)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(spacing: 2) {
                        if let previous = context.state.previousLyric, !previous.isEmpty {
                            Text(previous)
                                .font(.caption2)
                                .opacity(0.45)
                                .lineLimit(1)
                        }
                        Text(mainLine(context.state))
                            .font(.callout.weight(.semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .multilineTextAlignment(.center)
                        if let translation = context.state.translation,
                           !translation.isEmpty {
                            Text(translation)
                                .font(.caption2)
                                .opacity(0.8)
                                .lineLimit(1)
                        }
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ProgressRow(state: context.state)
                }
            } compactLeading: {
                Image(systemName: context.state.isPlaying
                      ? "play.fill" : "pause.fill")
                    .foregroundColor(.white)
            } compactTrailing: {
                Text(String(mainLine(context.state).prefix(12)))
                    .font(.caption2)
                    .lineLimit(1)
                    .foregroundColor(.white)
            } minimal: {
                Image(systemName: context.state.isPlaying
                      ? "music.note" : "pause.circle")
                    .foregroundColor(.white)
            }
            .keylineTint(Color.white)
        }
    }
}

// MARK: - Subviews

@available(iOS 16.1, *)
private struct LockScreenCard: View {
    let state: MusicFreeLyricAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Image(systemName: state.isPlaying
                      ? "play.circle.fill" : "pause.circle.fill")
                VStack(alignment: .leading, spacing: 1) {
                    Text(stateTitle(state))
                        .font(.headline)
                        .lineLimit(1)
                    Text(state.artist)
                        .font(.caption)
                        .opacity(0.75)
                        .lineLimit(1)
                }
                Spacer()
                Text(state.isPlaying ? "播放中" : "已暂停")
                    .font(.caption2)
                    .opacity(0.65)
            }

            if let previous = state.previousLyric, !previous.isEmpty {
                Text(previous)
                    .font(.caption)
                    .opacity(0.45)
                    .lineLimit(1)
            }
            Text(mainLine(state))
                .font(.body.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.8)
            if let translation = state.translation, !translation.isEmpty {
                Text(translation)
                    .font(.caption)
                    .opacity(0.8)
                    .lineLimit(1)
            }
            if let next = state.nextLyric, !next.isEmpty {
                Text(next)
                    .font(.caption)
                    .opacity(0.35)
                    .lineLimit(1)
            }
            ProgressRow(state: state)
        }
    }
}

@available(iOS 16.1, *)
private struct ProgressRow: View {
    let state: MusicFreeLyricAttributes.ContentState

    var body: some View {
        if state.duration > 0 {
            HStack(spacing: 6) {
                Text(mmss(state.elapsed))
                    .font(.caption2)
                    .monospacedDigit()
                    .opacity(0.7)
                ProgressView(value: min(max(state.elapsed / state.duration, 0), 1))
                    .progressViewStyle(.linear)
                Text(mmss(state.duration))
                    .font(.caption2)
                    .monospacedDigit()
                    .opacity(0.7)
            }
        }
    }
}

// MARK: - Helpers

@available(iOS 16.1, *)
private func stateTitle(_ state: MusicFreeLyricAttributes.ContentState) -> String {
    state.title.isEmpty ? "MusicFree" : state.title
}

@available(iOS 16.1, *)
private func mainLine(_ state: MusicFreeLyricAttributes.ContentState) -> String {
    if !state.lyric.isEmpty { return state.lyric }
    return state.title.isEmpty ? "MusicFree" : state.title
}

/// Plain interpolation instead of String(format: "%d"), whose CVarArg width
/// does not match Swift.Int on 64-bit and is easy to get subtly wrong here.
private func mmss(_ seconds: Double) -> String {
    let value = max(0, Int(seconds))
    let rest = value % 60
    return "\(value / 60):\(rest < 10 ? "0" : "")\(rest)"
}
