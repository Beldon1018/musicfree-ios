/**
 * MusicFree iOS adapter — Live Activity state publisher (batch 2).
 *
 * Why a separate module instead of patching lyricManager.ts in five places:
 * it keeps ONE owner for the Lock Screen / Dynamic Island state, and module
 * scope gives us a free, reliable "installed" guard. `lyricManager.setup()`
 * can be invoked more than once (player retry / hot reload); previously every
 * call added another RNTP listener and multiplied lyric events. This bridge
 * registers its listeners exactly once, no matter how often setup runs.
 *
 * Data sources (all already public on the upstream singletons):
 *   - TrackPlayer.currentMusic          -> title / artist / duration
 *   - lyricManager.currentLyricItem    -> current line + translation
 *   - lyricManager.lyricState.lyrics   -> previous / next lines
 *   - RNTrackPlayer events             -> play state, progress, queue end
 *
 * Publishing policy: Live Activity updates are budgeted. A 4 Hz progress
 * event stream is NOT forwarded 1:1 — we emit at most ~1 Hz (progress bar),
 * plus an immediate update on track change, lyric-line change, play/pause
 * transition and seek. The Swift controller throttles as a second line of
 * defence.
 */
import { NativeModules } from "react-native";
import RNTrackPlayer, {
    Event,
    State,
} from "react-native-track-player";
import lyricManager from "@/core/lyricManager";
import TrackPlayer from "@/core/trackPlayer";
import PersistStatus from "@/utils/persistStatus";

interface ILiveActivityNative {
    applyState?: (stateJson: string) => void;
}

interface IStatePatch {
    action?: "start" | "stop";
    title?: string;
    artist?: string;
    lyric?: string;
    translation?: string;
    previousLyric?: string;
    nextLyric?: string;
    isPlaying?: boolean;
    duration?: number;
    elapsed?: number;
}

const live = NativeModules.MusicFreeLiveActivity as
    | ILiveActivityNative
    | undefined;

let installed = false;
let lastMetaKey = "";
let lastLineKey = "";
let lastPosition = 0;
let lastDuration = 0;
let lastHeartbeat = 0;
let lastKnownPlaying = true;

function publish(patch: IStatePatch): void {
    try {
        live?.applyState?.(JSON.stringify(patch));
    } catch {
        // A missing / unlinked Live Activity must never break playback.
    }
}

/** RNTP enum members are stable in v4, but fall back to the raw event names
 *  so a minor version bump cannot silently disable the whole bridge. */
const EVENT_STATE = (Event as any)?.PlaybackState ?? "playback-state";
const EVENT_PROGRESS =
    (Event as any)?.PlaybackProgressUpdated ?? "playback-progress-updated";
const EVENT_QUEUE_ENDED =
    (Event as any)?.PlaybackQueueEnded ?? "playback-queue-ended";

function safeListen(event: string, handler: (evt: any) => void): void {
    try {
        (RNTrackPlayer as any).addEventListener(event, handler);
    } catch {
        // Unknown event on this RNTP build: degrade, never crash startup.
    }
}

function isPlayingState(state: any): boolean {
    return String(state) === String(State.Playing);
}

function isStoppedState(state: any): boolean {
    const value = String(state);
    return value === "stopped" || value === "ended";
}

function safePosition(value: any): number {
    return typeof value === "number" && Number.isFinite(value) && value > 0
        ? value
        : 0;
}

function currentLineInfo(): {
    key: string;
    patch: IStatePatch;
} {
    const item = lyricManager.currentLyricItem as any;
    const lyrics = (lyricManager.lyricState?.lyrics ?? []) as any[];
    const index = item
        ? Math.max(0, lyrics.findIndex(
            it => it === item ||
                (it?.time !== undefined && it.time === item.time)))
        : -1;
    const showTranslation = !!PersistStatus.get("lyric.showTranslation");
    const translation = showTranslation
        ? (item?.translation ?? "")
        : "";
    const line = item?.lrc ?? "";
    const key = `${index}|${line}|${translation}`;
    return {
        key,
        patch: {
            lyric: line,
            // Empty string clears an optional line on the Swift side.
            translation,
            previousLyric: index > 0 ? (lyrics[index - 1]?.lrc ?? "") : "",
            nextLyric: index >= 0 && index + 1 < lyrics.length
                ? (lyrics[index + 1]?.lrc ?? "")
                : "",
        },
    };
}

/** Install the bridge once. Called from bootstrap.ts after player setup. */
export function setupLiveActivityBridge(): void {
    if (installed || typeof live?.applyState !== "function") {
        return;
    }
    installed = true;

    // Play / pause / stop: also refresh elapsed so a paused progress bar
    // stays where the audio stopped instead of freezing at the last lyric.
    safeListen(EVENT_STATE, async (evt: any) => {
        const playing = isPlayingState(evt?.state);
        lastKnownPlaying = playing;
        if (isStoppedState(evt?.state)) {
            lastMetaKey = "";
            lastLineKey = "";
            publish({ action: "stop" });
            return;
        }
        let elapsed = 0;
        try {
            elapsed = safePosition((await RNTrackPlayer.getProgress())?.position);
        } catch {
            // Keep the last known position.
        }
        publish({ isPlaying: playing, elapsed, duration: lastDuration });
    });

    safeListen(EVENT_QUEUE_ENDED, () => {
        lastMetaKey = "";
        lastLineKey = "";
        publish({ action: "stop" });
    });

    // 4 Hz heartbeat. Only three things can leave this callback as an update:
    // a new track, a new lyric line (or seek), or the 1 Hz progress tick.
    safeListen(EVENT_PROGRESS, (evt: any) => {
        const now = Date.now();
        const position = safePosition(evt?.position);
        const duration = safePosition(evt?.duration) || lastDuration;
        if (duration > 0) {
            lastDuration = duration;
        }
        const seeked = position < lastPosition - 0.5 ||
            position - lastPosition > 2.5;
        lastPosition = position;

        // --- track change: idempotent "start", the Swift side only updates ---
        if (now - lastHeartbeat >= 900 || seeked) {
            const music = TrackPlayer.currentMusic as any;
            if (music) {
                const title = music.title ?? "MusicFree";
                const artist = music.artist ?? "";
                const metaKey = `${title}|${artist}|${Math.round(duration)}`;
                if (metaKey !== lastMetaKey) {
                    lastMetaKey = metaKey;
                    lastLineKey = "";
                    publish({
                        action: "start",
                        title,
                        artist,
                        lyric: "",
                        previousLyric: "",
                        nextLyric: "",
                        translation: "",
                        isPlaying: lastKnownPlaying,
                        elapsed: position,
                        duration,
                    });
                    lastHeartbeat = now;
                    return;
                }
            }
        }

        // --- lyric line / translation change, or an explicit seek ---
        const info = currentLineInfo();
        if (info.key !== lastLineKey || seeked) {
            lastLineKey = info.key;
            publish({
                ...info.patch,
                isPlaying: lastKnownPlaying,
                elapsed: position,
                duration,
            });
            lastHeartbeat = now;
            return;
        }

        // --- plain 1 Hz progress tick (drives the progress bar) ---
        if (now - lastHeartbeat >= 900) {
            lastHeartbeat = now;
            publish({ elapsed: position, duration });
        }
    });
}

/** Desktop-lyric toggle: opening starts (idempotent), closing dismisses. */
export function startLiveActivity(): void {
    lastMetaKey = "";
    lastLineKey = "";
    publish({ action: "start" });
}

export function stopLiveActivity(): void {
    lastMetaKey = "";
    lastLineKey = "";
    publish({ action: "stop" });
}

export default { setupLiveActivityBridge, startLiveActivity, stopLiveActivity };
