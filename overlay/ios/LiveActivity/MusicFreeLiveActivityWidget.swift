import ActivityKit
import SwiftUI
import WidgetKit

/// Widget Extension entry point. Add ONLY to the "MusicFreeLiveActivity"
/// extension target (together with MusicFreeLyricAttributes.swift).
///
/// Shows the current lyric line on the Lock Screen (all iOS 16.1+ devices) and
/// in the Dynamic Island compact / expanded presentations (iPhone 14 Pro and
/// later). This is the iOS-native stand-in for Android's floating lyric.
@main
struct MusicFreeLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MusicFreeLyricAttributes.self) { context in
            // Lock Screen / banner presentation
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Image(systemName: "music.note")
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.attributes.title)
                            .font(.headline)
                            .lineLimit(1)
                        Text(context.attributes.artist)
                            .font(.caption)
                            .opacity(0.75)
                            .lineLimit(1)
                    }
                    Spacer()
                }
                Text(context.state.lyric.isEmpty ? "MusicFree" : context.state.lyric)
                    .font(.body.weight(.semibold))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
            }
            .padding(14)
            .activityBackgroundTint(Color.black.opacity(0.72))
            .activitySystemActionForegroundColor(Color.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label(context.attributes.title, systemImage: "music.note")
                        .font(.caption)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(context.attributes.artist)
                        .font(.caption)
                        .opacity(0.75)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.lyric.isEmpty ? "MusicFree" : context.state.lyric)
                        .font(.callout.weight(.semibold))
                        .lineLimit(2)
                        .minimumScaleFactor(0.7)
                        .multilineTextAlignment(.center)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text("正在播放")
                        .font(.caption2)
                        .opacity(0.7)
                }
            } compactLeading: {
                Image(systemName: "music.note")
                    .foregroundColor(.white)
            } compactTrailing: {
                Text(String(context.state.lyric.prefix(12)))
                    .font(.caption2)
                    .lineLimit(1)
                    .foregroundColor(.white)
            } minimal: {
                Image(systemName: "music.note")
                    .foregroundColor(.white)
            }
            .keylineTint(Color.white)
        }
    }
}
