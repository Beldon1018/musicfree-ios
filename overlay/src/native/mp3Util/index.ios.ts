/**
 * MusicFree iOS adapter — Mp3Util
 *
 * Upstream uses the Android-only Kotlin module (MediaMetadataRetriever +
 * jaudiotagger). On iOS we delegate to MusicFreeNative (AVFoundation) when the
 * pod is linked, and degrade gracefully to empty metadata otherwise, so local
 * music import never crashes on an undefined NativeModules.Mp3Util.
 *
 * Known limitation: ID3 tag writing / embedded lyric reading are Android-only
 * upstream features; the iOS pod returns empty values instead of rejecting, so
 * the caller's existing promise flow keeps working.
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
