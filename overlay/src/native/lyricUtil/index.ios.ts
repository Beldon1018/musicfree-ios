/**
 * MusicFree iOS adapter — LyricUtil (status-bar lyrics)
 *
 * The Android implementation draws lyrics in a system overlay window, which iOS
 * has no equivalent for. Upstream's index.ts reads
 * `NativeModules.LyricUtil.showStatusBarLyric` at module load time, so leaving
 * it undefined crashes the whole app at startup on iOS.
 *
 * This platform override keeps the exact same API surface (including the
 * NativeTextAlignment enum imported by setting pages) as no-op promises.
 * The setting entry still exists but simply does nothing on iOS.
 */
export enum NativeTextAlignment {
    LEFT = 3,
    RIGHT = 5,
    CENTER = 17,
}

const noop = async (..._args: any[]): Promise<void> => {};

const LyricUtil = {
    showStatusBarLyric: noop,
    hideStatusBarLyric: noop,
    setStatusBarLyricText: noop,
    setStatusBarLyricTop: noop,
    setStatusBarLyricLeft: noop,
    setStatusBarLyricWidth: noop,
    setStatusBarLyricFontSize: noop,
    setStatusBarLyricAlign: noop,
    setStatusBarColors: noop,
    // Returning false lets the UI show "unavailable" instead of looping on
    // a permission request that can never succeed on iOS.
    checkSystemAlertPermission: async (): Promise<boolean> => false,
    requestSystemAlertPermission: async (): Promise<boolean> => false,
};

export default LyricUtil;
