/**
 * MusicFree iOS adapter — NativeUtils
 *
 * Upstream src/native/utils/index.ts exports `NativeModules.NativeUtils` directly,
 * which is undefined on iOS and crashes on first use (bootstrap, panels, drawer).
 * Metro resolves `index.ios.ts` before `index.ts` on iOS, so this file replaces it
 * without touching any upstream source file.
 *
 * Strategy: use the local MusicFreeNative pod when it is linked, otherwise fall
 * back to a pure-JS implementation. Either way the module is never undefined.
 */
import { Dimensions, NativeModules } from "react-native";

interface INativeUtils {
    exitApp: () => void;
    checkStoragePermission: () => Promise<boolean>;
    requestStoragePermission: () => void;
    getWindowDimensions: () => { width: number; height: number };
}

const native = NativeModules.NativeUtils as INativeUtils | undefined;

const jsFallback: INativeUtils = {
    // iOS does not allow an app to terminate itself. Staying alive is the
    // closest behaviour to Android's finishAndRemoveTask().
    exitApp: () => {},
    // App sandbox always grants access to its own Documents directory.
    checkStoragePermission: async () => true,
    requestStoragePermission: () => {},
    getWindowDimensions: () => {
        const { width, height } = Dimensions.get("window");
        return { width, height };
    },
};

const pick = <K extends keyof INativeUtils>(key: K): INativeUtils[K] => {
    const impl = native && typeof native[key] === "function" ? native[key] : undefined;
    return (impl ? impl.bind(native) : jsFallback[key]) as INativeUtils[K];
};

const NativeUtils: INativeUtils = {
    exitApp: pick("exitApp"),
    checkStoragePermission: pick("checkStoragePermission"),
    requestStoragePermission: pick("requestStoragePermission"),
    getWindowDimensions: pick("getWindowDimensions"),
};

export default NativeUtils;
