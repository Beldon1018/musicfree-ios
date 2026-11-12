/**
 * MusicFree iOS adapter — LyricUtil
 *
 * Android draws lyrics in a system-wide overlay window. iOS has no public
 * equivalent, so this override keeps the exact same API surface but routes it
 * to iOS-native presentation instead of a no-op:
 *
 *   - MusicFreeNative/LyricUtilModule.m  -> draggable in-app lyric card
 *   - native/liveActivity (batch 2)      -> Dynamic Island / Lock Screen
 *
 * `index.ios.ts` fully replaces upstream's `index.ts` under Metro's platform
 * resolution, so the upstream module-load monkey patch never runs here. The
 * exported object stays mutable so any future upstream wrapper still works.
 *
 * Batch 2: lyric *text* is no longer pushed to the Live Activity from here.
 * The dedicated bridge owns that state (real track title, play/pause,
 * translation, previous/next lines and progress). Having two writers used to
 * let the "\n"-joined translation string overwrite the structured state.
 * This module now only starts / stops the activity around the desktop-lyric
 * toggle and keeps driving the in-app floating card.
 *
 * Deliberately NOT importing `@/native/liveActivity`: that module reads
 * `lyricManager`, which imports this file. Keeping this dependency one-way
 * (liveActivity -> lyricManager -> lyricUtil) avoids a module init cycle.
 */
import { NativeModules } from "react-native";

export enum NativeTextAlignment {
    LEFT = 3,
    RIGHT = 5,
    CENTER = 17,
}

interface ILyricUtil {
    showStatusBarLyric: (
        initLyric?: string,
        config?: Record<string, any>,
    ) => Promise<void>;
    hideStatusBarLyric: () => Promise<void>;
    setStatusBarLyricText: (lyric: string) => Promise<void>;
    setStatusBarLyricTop: (percent: number) => Promise<void>;
    setStatusBarLyricLeft: (percent: number) => Promise<void>;
    setStatusBarLyricWidth: (percent: number) => Promise<void>;
    setStatusBarLyricFontSize: (fontSize: number) => Promise<void>;
    setStatusBarLyricAlign: (alignment: NativeTextAlignment) => Promise<void>;
    setStatusBarColors: (
        textColor: string | null,
        backgroundColor: string | null,
    ) => Promise<void>;
    checkSystemAlertPermission: () => Promise<boolean>;
    requestSystemAlertPermission: () => Promise<boolean>;
}

interface ILiveActivityNative {
    applyState?: (stateJson: string) => void;
}

const native = NativeModules.LyricUtil as Partial<ILyricUtil> | undefined;
const live = NativeModules.MusicFreeLiveActivity as
    | ILiveActivityNative
    | undefined;

const pushLiveState = (patch: Record<string, unknown>): void => {
    try {
        live?.applyState?.(JSON.stringify(patch));
    } catch {
        // A missing / unlinked extension must never break lyric playback.
    }
};

/** Idempotent on the Swift side: an existing activity is updated, not rebuilt. */
const startLiveActivity = (): void => pushLiveState({ action: "start" });
const stopLiveActivity = (): void => pushLiveState({ action: "stop" });

const noop = async (..._args: any[]): Promise<void> => {};

const fallback: ILyricUtil = {
    showStatusBarLyric: noop,
    hideStatusBarLyric: noop,
    setStatusBarLyricText: noop,
    setStatusBarLyricTop: noop,
    setStatusBarLyricLeft: noop,
    setStatusBarLyricWidth: noop,
    setStatusBarLyricFontSize: noop,
    setStatusBarLyricAlign: noop,
    setStatusBarColors: noop,
    // No system permission is needed for an in-app overlay / Live Activity,
    // so returning true keeps upstream's "desktop lyrics" toggle usable.
    checkSystemAlertPermission: async (): Promise<boolean> => true,
    requestSystemAlertPermission: async (): Promise<boolean> => true,
};

const pick = <K extends keyof ILyricUtil>(key: K): ILyricUtil[K] => {
    const impl = native && typeof native[key] === "function" ? native[key] : undefined;
    return (impl ? impl.bind(native) : fallback[key]) as ILyricUtil[K];
};

const LyricUtil: ILyricUtil = {
    showStatusBarLyric: async (initLyric, config) => {
        await pick("showStatusBarLyric")(initLyric, config);
        // Idempotent: the Swift controller updates an existing activity rather
        // than ending + re-requesting it (which used to stack cards).
        startLiveActivity();
    },
    hideStatusBarLyric: async () => {
        await pick("hideStatusBarLyric")();
        stopLiveActivity();
    },
    setStatusBarLyricText: async (lyric: string) => {
        // In-app floating card only. The Live Activity bridge publishes the
        // structured (translation-aware) state from the RNTP progress stream.
        await pick("setStatusBarLyricText")(lyric);
    },
    setStatusBarLyricTop: pick("setStatusBarLyricTop"),
    setStatusBarLyricLeft: pick("setStatusBarLyricLeft"),
    setStatusBarLyricWidth: pick("setStatusBarLyricWidth"),
    setStatusBarLyricFontSize: pick("setStatusBarLyricFontSize"),
    setStatusBarLyricAlign: pick("setStatusBarLyricAlign"),
    setStatusBarColors: pick("setStatusBarColors"),
    checkSystemAlertPermission: pick("checkSystemAlertPermission"),
    requestSystemAlertPermission: pick("requestSystemAlertPermission"),
};

export default LyricUtil;
