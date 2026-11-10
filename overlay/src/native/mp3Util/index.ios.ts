/**
 * MusicFree iOS adapter — Mp3Util
 *
 * Upstream uses the Android-only Kotlin module (MediaMetadataRetriever +
 * jaudiotagger). On iOS we delegate to MusicFreeNative (AVFoundation) when the
 * pod is linked, and degrade gracefully to empty metadata otherwise, so local
 * music import never crashes on an undefined NativeModules.Mp3Util.
 *
 * iOS-native behaviour of the previously degraded features:
 *   - getLyric: reads embedded ID3v2 USLT/SYLT and iTunes lyrics frames via
 *     AVURLAsset.metadata (the same frames Android reads with jaudiotagger).
 *   - setMediaTag: does NOT rewrite the audio file. It stores an in-app
 *     metadata override which getBasicMeta/getMediaMeta/getLyric/getMediaTag
 *     merge on top of the file's own tags. Editing tags therefore works from
 *     the user's point of view while the sandbox source file stays untouched.
 *   - getMediaTag: returns merged override + embedded values.
 *
 * The JS fallback below is only used if the pod is not linked at all; it stays
 * intentionally empty rather than rejecting so upstream's promise flow holds.
 */
import { NativeModules } from "react-native";

export interface IBasicMeta {
    album?: string;
    artist?: string;
    author?: string;
    duration?: string;
    title?: string;
}

export interface IWritableMeta extends IBasicMeta {
    lyric?: string;
    comment?: string;
}

interface IMp3Util {
    getBasicMeta: (fileName: string) => Promise<IBasicMeta>;
    getMediaMeta: (fileNames: string[]) => Promise<IBasicMeta[]>;
    getMediaCoverImg: (mediaPath: string) => Promise<string>;
    getLyric: (mediaPath: string) => Promise<string>;
    setMediaTag: (filePath: string, meta: IWritableMeta) => Promise<void>;
    getMediaTag: (filePath: string) => Promise<IWritableMeta>;
}

const native = NativeModules.Mp3Util as IMp3Util | undefined;

const jsFallback: IMp3Util = {
    getBasicMeta: async () => ({}),
    getMediaMeta: async (fileNames: string[]) => fileNames.map(() => ({})),
    getMediaCoverImg: async () => "",
    getLyric: async () => "",
    setMediaTag: async () => {},
    getMediaTag: async () => ({}),
};

const pick = <K extends keyof IMp3Util>(key: K): IMp3Util[K] => {
    const impl = native && typeof native[key] === "function" ? native[key] : undefined;
    return (impl ? impl.bind(native) : jsFallback[key]) as IMp3Util[K];
};

const Mp3Util: IMp3Util = {
    getBasicMeta: pick("getBasicMeta"),
    getMediaMeta: pick("getMediaMeta"),
    getMediaCoverImg: pick("getMediaCoverImg"),
    getLyric: pick("getLyric"),
    setMediaTag: pick("setMediaTag"),
    getMediaTag: pick("getMediaTag"),
};

export default Mp3Util;
