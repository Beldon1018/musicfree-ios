/**
 * MusicFree iOS adapter — LyricUtil
 *
 * Android draws lyrics in a system-wide overlay window. iOS has no public
 * equivalent, so this override keeps the exact same API surface but routes it
 * to iOS-native presentation instead of a no-op:
 *
 *   - MusicFreeNative/LyricUtilModule.m  -> draggable in-app lyric card
 *   - MusicFreeLiveActivity (optional)   -> Dynamic Island / Lock Screen
 *
 * `index.ios.ts` fully replaces upstream's `index.ts` under Metro's platform
 * resolution, so the upstream module-load monkey patch never runs here. The
 * exported object stays mutable so any future upstream wrapper still works.
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

interface ILiveActivity {
    start?: (title: string, artist: string) => void;
    updateLyric?: (lyric: string) => void;
    stop?: () => void;
}

const native = NativeModules.LyricUtil as Partial<ILyricUtil> | undefined;
const live = NativeModules.MusicFreeLiveActivity as ILiveActivity | undefined;

const noop = async (..._args: any[]): Promise<void> => {};

/** The optional Live Activity module is absent unless ENABLE_LIVE_ACTIVITY=1. */
const liveCall = (name: keyof ILiveActivity, ...args: any[]): void => {
    try {
        const fn = live?.[name];
        if (typeof fn === "function") {
            (fn as (...a: any[]) => void).apply(live, args);
        }
    } catch {
        // A missing or unlinked extension must never break lyric playback.
    }
};

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
        liveCall("start", "MusicFree", "");
        if (initLyric) { liveCall("updateLyric", initLyric); }
    },
    hideStatusBarLyric: async () => {
        await pick("hideStatusBarLyric")();
        liveCall("stop");
    },
    setStatusBarLyricText: async (lyric: string) => {
        await pick("setStatusBarLyricText")(lyric);
        liveCall("updateLyric", lyric);
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
