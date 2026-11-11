#!/usr/bin/env python3
"""Idempotent, conflict-free injections into upstream iOS project files.

Why injection instead of .patch files: upstream may edit Podfile / Info.plist /
project.pbxproj in any future release. A patch with fixed context would break;
these marker-based, content-aware rewrites simply re-apply (or no-op) on any
version. This is what keeps "sync with upstream" low-maintenance.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inject_live_activity  # noqa: E402  (sibling script, same directory)

MARKER = "musicfree-ios-adapter"
BUNDLE_ID = "com.musicfree.ios.unsigned"


def version_from_ref(ref: str) -> str:
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", ref)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else "1.0.0"


def inject_podfile(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    original = text
    changes: list[str] = []

    # Force the legacy (bridge) architecture.
    #
    # React Native 0.76 turns the New Architecture ON by default:
    # react_native_pods.rb -> use_react_native!(:new_arch_enabled =>
    # NewArchitectureHelper.new_arch_enabled), and that helper returns *true*
    # whenever ENV['RCT_NEW_ARCH_ENABLED'] is unset:
    #
    #     def self.new_arch_enabled
    #       return ENV["RCT_NEW_ARCH_ENABLED"] == nil ||
    #              ENV["RCT_NEW_ARCH_ENABLED"] == "1"
    #     end
    #
    # This bare-RN Podfile never reads Podfile.properties.json, so writing
    # newArchEnabled=false there has NO effect. The default silently built the
    # app in bridgeless mode, where BridgelessNativeModuleProxy::get() ->
    # TurboModuleBinding::getModule() -> moduleProvider_() died on
    # std::string(NULL) / strlen(NULL) during startup bundle evaluation on
    # iOS 26.4 (SIGSEGV, JS thread). Setting the env var *before* the RN/Expo
    # pod helpers run keeps the build on the classic bridge, which is the
    # intended and far better-tested path for these native pods.
    if "RCT_NEW_ARCH_ENABLED" not in text:
        anchor = "platform :ios"
        if anchor not in text:
            raise RuntimeError(
                "Podfile shape changed: cannot find \"platform :ios\" to force "
                "the legacy architecture. Manual review required."
            )
        text = text.replace(
            anchor,
            "# >>> musicfree-ios-adapter: legacy architecture >>>\n"
            "ENV['RCT_NEW_ARCH_ENABLED'] = '0'\n"
            "# <<< musicfree-ios-adapter <<<\n\n" + anchor,
            1,
        )
        changes.append("forced legacy architecture (RCT_NEW_ARCH_ENABLED=0)")

    # Local pod with the iOS counterparts of the Android-only Kotlin modules.
    if "MusicFreeNative" not in text:
        needle = "target 'MusicFree' do"
        if needle not in text:
            raise RuntimeError(
                "Podfile shape changed: cannot find \"target 'MusicFree' do\". "
                "Manual review required (see README, 'When upstream changes')."
            )
        block = (
            f"{needle}\n"
            f"  # >>> {MARKER} >>>\n"
            f"  pod 'MusicFreeNative', :path => './LocalPods/MusicFreeNative'\n"
            f"  # <<< {MARKER} <<<"
        )
        text = text.replace(needle, block, 1)
        changes.append("injected local pod")

    if text != original:
        path.write_text(text, encoding="utf-8")
    return changes or ["already present"]


def inject_info_plist(path: Path) -> list[str]:
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    changes: list[str] = []

    backgrounds = list(data.get("UIBackgroundModes") or [])
    if "audio" not in backgrounds:
        backgrounds.append("audio")
        changes.append("UIBackgroundModes += audio")
    data["UIBackgroundModes"] = backgrounds

    ats = dict(data.get("NSAppTransportSecurity") or {})
    if ats.get("NSAllowsArbitraryLoads") is not True:
        ats["NSAllowsArbitraryLoads"] = True
        changes.append("NSAllowsArbitraryLoads = true")
    ats.setdefault("NSAllowsLocalNetworking", True)
    data["NSAppTransportSecurity"] = ats

    for key, label in (
        ("UIFileSharingEnabled", "UIFileSharingEnabled = true"),
        ("LSSupportsOpeningDocumentsInPlace", "LSSupportsOpeningDocumentsInPlace = true"),
    ):
        if data.get(key) is not True:
            data[key] = True
            changes.append(label)

    if data.get("ITSAppUsesNonExemptEncryption") is not False:
        data["ITSAppUsesNonExemptEncryption"] = False
        changes.append("ITSAppUsesNonExemptEncryption = false")

    # Expo SDK 52's SplashScreenManager calls
    #   UIStoryboard(name: "SplashScreen", bundle: nil).instantiateInitialViewController()
    # from SplashScreenAppDelegateSubscriber.customizeRootView during native
    # startup. UIStoryboard(name:) throws when that storyboard is missing, so an
    # app that only ships "LaunchScreen" can be killed before React Native
    # mounts. inject_storyboard() produces a single minimal storyboard named
    # SplashScreen and points BOTH the system launch screen and Expo at it.
    if data.pop("UILaunchScreen", None) is not None:
        changes.append("stale UILaunchScreen plist override removed")
    if data.get("UILaunchStoryboardName") != "SplashScreen":
        data["UILaunchStoryboardName"] = "SplashScreen"
        changes.append("UILaunchStoryboardName = SplashScreen (Expo-compatible)")

    # Capability keys for the optional Dynamic Island / Live Activity module.
    # They are inert until a Widget Extension target is added, so it is safe to
    # always emit them; the Swift sources use #available(iOS 16.1, *) guards.
    for key, label in (
        ("NSSupportsLiveActivities", "NSSupportsLiveActivities = true"),
        ("NSSupportsLiveActivitiesFrequentUpdates",
         "NSSupportsLiveActivitiesFrequentUpdates = true"),
    ):
        if data.get(key) is not True:
            data[key] = True
            changes.append(label)

    if changes:
        with path.open("wb") as fh:
            plistlib.dump(data, fh, sort_keys=True)
    return changes or ["already present"]


def inject_pbxproj(path: Path, ref: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    original = text
    changes: list[str] = []

    text, n = re.subn(
        r'(PRODUCT_BUNDLE_IDENTIFIER\s*=\s*)"?org\.reactjs\.native\.example[^;]*;',
        lambda m: f'{m.group(1)}"{BUNDLE_ID}";',
        text,
    )
    if n:
        changes.append(f"bundle id -> {BUNDLE_ID} ({n} places)")

    marketing = version_from_ref(ref)
    text, n = re.subn(
        r'(MARKETING_VERSION\s*=\s*)[^;]+;',
        lambda m: f"{m.group(1)}{marketing};",
        text,
    )
    if n:
        changes.append(f"MARKETING_VERSION -> {marketing} ({n} places)")

    build_number = os.environ.get("BUILD_NUMBER", "1").strip() or "1"
    text, n = re.subn(
        r'(CURRENT_PROJECT_VERSION\s*=\s*)[^;]+;',
        lambda m: f"{m.group(1)}{build_number};",
        text,
    )
    if n:
        changes.append(f"CURRENT_PROJECT_VERSION -> {build_number} ({n} places)")

    # Rename the single storyboard resource to SplashScreen so that both
    # UILaunchStoryboardName and Expo's hardcoded UIStoryboard(name:) resolve.
    # Only the filename strings change — the pbxproj object structure stays
    # intact, so this stays valid across upstream project-file edits.
    text, n = re.subn(r"LaunchScreen\.storyboard", "SplashScreen.storyboard", text)
    if n:
        changes.append(f"LaunchScreen.storyboard -> SplashScreen.storyboard ({n} places)")

    if text != original:
        path.write_text(text, encoding="utf-8")
    return changes or ["already present"]


def inject_bootstrap(path: Path) -> list[str]:
    """Stop upstream bootstrap from running Android-only permissions on iOS.

    `if (Platform.OS === "android" && Platform.Version >= 30) { ... } else {`
    sends iOS into an else branch that calls PERMISSIONS.ANDROID.* through
    react-native-permissions. iOS needs no storage permission, and an unknown
    permission makes startup fail. Gate the else branch to Android only.
    """
    text = path.read_text(encoding="utf-8")
    needle = ("    } else {\n"
              "        const [readStoragePermission, writeStoragePermission]")
    patched = ("    } else if (Platform.OS === \"android\") {\n"
               "        const [readStoragePermission, writeStoragePermission]")
    changes: list[str] = []
    if needle in text:
        path.write_text(text.replace(needle, patched, 1), encoding="utf-8")
        changes.append("iOS skips PERMISSIONS.ANDROID.* in bootstrap")
    elif patched in text:
        changes.append("already present")
    else:
        raise RuntimeError(
            "bootstrap.ts: Android permission branch anchor not found — "
            "upstream changed, review manually before trusting this build")
    return changes


PLUGIN_INSTALL_TIMEOUT = 30000


def inject_plugin_install(manager: Path, plugin_list: Path) -> dict[str, list[str]]:
    """Give plugin downloads their own timeout instead of the 2 s global one.

    `core/pluginManager/plugin.ts` does

        axios.defaults.timeout = 2000;

    on the shared axios instance. That 2 s budget is deliberate for the API
    calls a *plugin* makes at runtime (it keeps a dead platform from freezing
    the UI), but `installPluginFromUrl` reuses the very same instance to fetch
    the plugin bundle itself. A plugin is 16-26 KB served from jsDelivr, and a
    cold TLS handshake to the edge alone costs ~1.1-1.2 s; measured end-to-end
    downloads of 26 KB took 1.93 s, i.e. right on the edge of the limit. Any
    jitter and the install dies with "timeout of 2000ms exceeded", which the UI
    reports as a generic install failure.

    The fix raises the timeout for the two *download* requests only — plugin
    runtime calls keep their 2 s guard — and turns the timeout into a message
    the user can act on. It also fixes `text.endsWith(".json")` in the install
    helper, which tested the raw input while the request used the trimmed one,
    so a subscription URL pasted with a trailing newline was fetched as a
    plugin and failed to parse.
    """
    report: dict[str, list[str]] = {}

    # --- 1. core/pluginManager/index.ts: timeout for the plugin download ----
    text = manager.read_text(encoding="utf-8")
    old_get = ("            const funcCode = (\n"
               "                await axios.get(url, {\n"
               "                    headers: {\n")
    new_get = ("            const funcCode = (\n"
               "                await axios.get(url, {\n"
               "                    // Deliberately NOT the 2 s default from plugin.ts:\n"
               "                    // that guards plugin runtime calls, while this is a\n"
               "                    // 16-26 KB CDN download whose cold TLS handshake\n"
               "                    // already costs ~1.2 s on mobile.\n"
               "                    timeout: 30000,\n"
               "                    headers: {\n")
    old_fail = ("                return {\n"
                "                    success: false,\n"
                "                    message: e?.message ?? \"\",\n"
                "                    pluginUrl: url,\n"
                "                };")
    new_fail = ("                const _timedOut =\n"
                "                    e?.code === \"ECONNABORTED\" ||\n"
                "                    /timeout/i.test(e?.message ?? \"\");\n"
                "                return {\n"
                "                    success: false,\n"
                "                    message: _timedOut\n"
                "                        ? \"下载超时，请检查网络后重试\"\n"
                "                        : e?.message ?? \"\",\n"
                "                    pluginUrl: url,\n"
                "                };")
    changes: list[str] = []
    if "timeout: 30000," in text and "_timedOut" in text:
        changes.append("already present")
    else:
        if text.count(old_get) != 1:
            raise RuntimeError(
                "core/pluginManager/index.ts: installPluginFromUrl download "
                "anchor not unique/found — upstream changed, review manually")
        if text.count(old_fail) != 1:
            raise RuntimeError(
                "core/pluginManager/index.ts: installPluginFromUrl failure "
                "anchor not unique/found — upstream changed, review manually")
        text = text.replace(old_get, new_get, 1).replace(old_fail, new_fail, 1)
        manager.write_text(text, encoding="utf-8")
        changes.append(
            "plugin download uses a 30 s timeout instead of the 2 s runtime default")
        changes.append("timeout is reported as an actionable message")
    report["core/pluginManager/index.ts"] = changes

    # --- 2. pluginList.tsx: subscription fetch + trimmed suffix test --------
    text = plugin_list.read_text(encoding="utf-8")
    old_json = ("                await axios.get(inputUrl, {\n"
                "                    headers: {\n")
    new_json = ("                await axios.get(inputUrl, {\n"
                "                    timeout: 30000,\n"
                "                    headers: {\n")
    old_test = '        if (text.endsWith(".json")) {'
    new_test = '        if (inputUrl.endsWith(".json")) {'
    changes = []
    if "timeout: 30000," in text and new_test in text:
        changes.append("already present")
    else:
        if text.count(old_json) != 1:
            raise RuntimeError(
                "pluginList.tsx: subscription fetch anchor not unique/found — "
                "upstream changed, review manually")
        if text.count(old_test) != 1:
            raise RuntimeError(
                "pluginList.tsx: .json suffix test anchor not unique/found — "
                "upstream changed, review manually")
        text = (text.replace(old_json, new_json, 1)
                    .replace(old_test, new_test, 1))
        plugin_list.write_text(text, encoding="utf-8")
        changes.append(
            "subscription JSON fetch uses a 30 s timeout")
        changes.append(
            "'.json' is tested on the trimmed URL, so a pasted URL with a "
            "trailing newline is no longer fetched as a plugin")
    report["pluginList.tsx"] = changes

    return report


def inject_storyboard(launch_path: Path, splash_path: Path) -> list[str]:
    """Create the SplashScreen.storyboard that expo-splash-screen requires.

    Two problems are solved at once:

    1. Expo SDK 52 hardcodes `UIStoryboard(name: "SplashScreen", bundle: nil)`
       in SplashScreenManager.showSplashScreen(), which runs from
       SplashScreenAppDelegateSubscriber.customizeRootView during native app
       startup. That initializer throws if the storyboard is absent. The
       upstream RN template only ships LaunchScreen.storyboard, and the
       ExpoSplashScreen pod contains no storyboard resource of its own.

    2. The template's `<deployment identifier="iOS"/>` inside <dependencies>
       makes ibtool on Xcode 16.2 look for a platform named "iOS 18.2" and
       fail with "iOS 18.2 Platform Not Installed." when Xcode does not pass
       --platform. Strip <dependencies> / <device> and refresh toolsVersion
       so the storyboard compiles on a plain macOS runner.

    The resulting file is named SplashScreen.storyboard; inject_pbxproj()
    rewrites the project references to match, and Info.plist points
    UILaunchStoryboardName at the same name.
    """
    if not launch_path.exists():
        raise RuntimeError(
            "LaunchScreen.storyboard missing — upstream changed its launch "
            "screen setup, review manually before trusting this build")

    text = launch_path.read_text(encoding="utf-8")
    cleaned = re.sub(r"\s*<dependencies>.*?</dependencies>", "", text, flags=re.S)
    cleaned = re.sub(r"\s*<device\s[^>]*/>", "", cleaned)
    cleaned = re.sub(r'toolsVersion="\d+"', 'toolsVersion="22505"', cleaned, count=1)
    if "<scenes>" not in cleaned or "initialViewController" not in cleaned:
        raise RuntimeError(
            "LaunchScreen.storyboard: scene/initialViewController missing — "
            "upstream changed, review manually")

    if splash_path.exists() and splash_path.read_text(encoding="utf-8") == cleaned:
        return ["already present"]
    splash_path.write_text(cleaned, encoding="utf-8")
    return ["SplashScreen.storyboard generated (Expo-compatible, ibtool-safe)"]


def inject_entry_index(path: Path) -> list[str]:
    """Guard the Android-only StatusBar calls that run at JS-bundle load time.

    `src/entry/index.tsx` executes these two statements at module scope, i.e.
    before React even mounts:

        StatusBar.setBackgroundColor("transparent");
        StatusBar.setTranslucent(true);

    Both are Android-only. Depending on the React Native version iOS either
    logs a warning or reaches a missing native method, which would abort the
    bundle evaluation right at startup. Gate them so the very first JS
    statements cannot kill the app.
    """
    text = path.read_text(encoding="utf-8")
    changes: list[str] = []

    guarded = ("if (Platform.OS === \"android\") {\n"
               "    StatusBar.setBackgroundColor(\"transparent\");\n"
               "    StatusBar.setTranslucent(true);\n"
               "}")
    plain = ("StatusBar.setBackgroundColor(\"transparent\");\n"
             "StatusBar.setTranslucent(true);")

    if "import { Platform, StatusBar }" in text and guarded in text:
        return ["already present"]

    if plain not in text:
        raise RuntimeError(
            "src/entry/index.tsx: StatusBar top-level calls not found — "
            "upstream changed, review manually before trusting this build")
    text = text.replace(plain, guarded, 1)
    changes.append("Android-only StatusBar calls gated to android")

    if "import { StatusBar } from \"react-native\";" in text:
        text = text.replace("import { StatusBar } from \"react-native\";",
                            "import { Platform, StatusBar } from \"react-native\";", 1)
        changes.append("Platform imported for the startup guard")
    elif not re.search(
            r"import\s*\{[^}]*\bPlatform\b[^}]*\}\s*from\s*[\"']react-native[\"']",
            text):
        raise RuntimeError(
            "src/entry/index.tsx: cannot add Platform import — review manually")

    path.write_text(text, encoding="utf-8")
    return changes


def inject_keyboard_avoidance(panels: Path, dialogs: Path) -> dict[str, list[str]]:
    """Keep text inputs visible when the iOS keyboard is up.

    Two independent defects, both only visible on iOS (Android resizes the
    window and the layout reflows by itself, which is why upstream never hit
    them):

    1. panels/base/panelBase.tsx puts the sheet inside a KeyboardAvoidingView
       whose style is only `{ zIndex: 15010 }`. The sheet body is
       `position: absolute; bottom: 0`, so that wrapper has no in-flow content
       and lays out 0px tall, which means:
         * behavior="height"   -> _initialFrameHeight (0) - keyboardHeight is
                                  clamped to 0: the sheet never moves, and the
                                  "install plugin from URL" input stays under
                                  the keyboard;
         * behavior="position" -> the inner offset View is 0px tall and sits at
                                  the top of the wrapper: fine only as long as
                                  the wrapper itself happens to sit at the
                                  bottom of the screen (SimpleSelect, the "+"
                                  menu, relies on that).
       Resizing the wrapper therefore fixes one case and breaks the other, so
       this patch stops using KeyboardAvoidingView for sheets altogether: the
       sheet body is anchored in an explicit full-screen box and the keyboard
       height is applied as a translateY offset in the existing Reanimated
       style. Both cases then share one code path, and panels with no input
       are untouched (their keyboard height stays 0).

    2. dialogs/components/base/index.tsx centres the dialog card in a
       full-screen absolute container with no keyboard handling whatsoever, so
       any dialog with a TextInput (SubscribePluginDialog, ...) ends up with
       its inputs under the keyboard. The card is put inside a full-screen
       KeyboardAvoidingView with behavior="padding": the bottom padding
       shrinks the centring box, which moves the card up by half the keyboard
       height — enough for a two-input dialog, and it keeps the card centred
       when the keyboard is dismissed.
    """
    report: dict[str, list[str]] = {}

    # --- 1. bottom sheets -------------------------------------------------
    text = panels.read_text(encoding="utf-8")
    changes: list[str] = []

    replacements = [
        (
            "react-native import",
            "import {\n"
            "    BackHandler,\n"
            "    DeviceEventEmitter,\n"
            "    KeyboardAvoidingView,\n"
            "    NativeEventSubscription,\n"
            "    Pressable,\n"
            "    StyleSheet,\n"
            "} from \"react-native\";",
            "import {\n"
            "    BackHandler,\n"
            "    DeviceEventEmitter,\n"
            "    Dimensions,\n"
            "    Keyboard,\n"
            "    NativeEventSubscription,\n"
            "    Platform,\n"
            "    Pressable,\n"
            "    StyleSheet,\n"
            "    View,\n"
            "} from \"react-native\";",
        ),
        (
            "shared value",
            "    const snapPoint = useSharedValue(0);",
            "    const snapPoint = useSharedValue(0);\n"
            "    // keyboard height, applied as a translateY offset (see below)\n"
            "    const kbOffset = useSharedValue(0);",
        ),
        (
            "keyboard subscription",
            "            listenerSubscription.remove();\n"
            "        };\n"
            "    }, []);",
            "            listenerSubscription.remove();\n"
            "        };\n"
            "    }, []);\n"
            "\n"
            "    // Lift the sheet above the soft keyboard. KeyboardAvoidingView\n"
            "    // cannot do this here: the sheet body is absolutely positioned,\n"
            "    // so the wrapper has no in-flow content.\n"
            "    useEffect(() => {\n"
            "        if (keyboardAvoidBehavior === \"none\" || Platform.OS !== \"ios\") {\n"
            "            return;\n"
            "        }\n"
            "        // Measure the overlap with the window bottom instead of the raw\n"
            "        // keyboard height: when the keyboard is dismissed iOS reports the\n"
            "        // old height together with an off-screen screenY, so a\n"
            "        // height-based calculation would leave the sheet lifted.\n"
            "        const onChange = Keyboard.addListener(\n"
            "            \"keyboardWillChangeFrame\",\n"
            "            e => {\n"
            "                const windowHeight = Dimensions.get(\"window\").height;\n"
            "                const keyboardTop = e.endCoordinates?.screenY ?? windowHeight;\n"
            "                kbOffset.value = withTiming(\n"
            "                    Math.max(0, windowHeight - keyboardTop),\n"
            "                    { duration: 250 },\n"
            "                );\n"
            "            },\n"
            "        );\n"
            "        const onHide = Keyboard.addListener(\"keyboardWillHide\", () => {\n"
            "            kbOffset.value = withTiming(0, { duration: 250 });\n"
            "        });\n"
            "        return () => {\n"
            "            onChange.remove();\n"
            "            onHide.remove();\n"
            "            kbOffset.value = 0;\n"
            "        };\n"
            "    }, []);",
        ),
        (
            "animated transform",
            "                    ? {\n"
            "                        translateY: (1 - snapPoint.value) * useAnimatedBase,\n"
            "                    }",
            "                    ? {\n"
            "                        translateY:\n"
            "                            (1 - snapPoint.value) * useAnimatedBase -\n"
            "                            kbOffset.value,\n"
            "                    }",
        ),
        (
            "wrapper element",
            "                <KeyboardAvoidingView\n"
            "                    style={style.kbContainer}\n"
            "                    behavior={keyboardAvoidBehavior || \"position\"}>",
            "                <View style={style.kbContainer} pointerEvents=\"box-none\">",
        ),
        (
            "wrapper element close",
            "                    {panelBody}\n"
            "                </KeyboardAvoidingView>",
            "                    {panelBody}\n"
            "                </View>",
        ),
        (
            "kbContainer style",
            "    kbContainer: {\n"
            "        zIndex: 15010,\n"
            "    },",
            "    kbContainer: {\n"
            "        position: \"absolute\",\n"
            "        top: 0,\n"
            "        left: 0,\n"
            "        width: \"100%\",\n"
            "        height: \"100%\",\n"
            "        zIndex: 15010,\n"
            "    },",
        ),
    ]

    if "kbOffset.value" in text and "keyboardWillChangeFrame" in text:
        report["panelBase.tsx"] = ["already present"]
    else:
        for label, old, new in replacements:
            if old not in text:
                raise RuntimeError(
                    f"panels/base/panelBase.tsx: {label} anchor not found — "
                    "upstream changed the keyboard handling, review manually")
            text = text.replace(old, new, 1)
        panels.write_text(text, encoding="utf-8")
        changes.append(
            "sheets anchored in a full-screen box and lifted by the keyboard "
            "height (no more KeyboardAvoidingView on absolutely positioned bodies)")
        report["panelBase.tsx"] = changes

    # --- 2. dialogs -------------------------------------------------------
    text = dialogs.read_text(encoding="utf-8")
    changes = []
    old_import = "    BackHandler,\n    NativeEventSubscription,"
    new_import = "    BackHandler,\n    KeyboardAvoidingView,\n    NativeEventSubscription,"
    old_card = (
        "            <Animated.View\n"
        "                style={[\n"
        "                    styles.dialogContainer,\n"
        "                    dialogContainerStyle,\n"
        "                    containerStyle,\n"
        "                    scaleAnimationStyle,\n"
        "                    {\n"
        "                        backgroundColor: colors.backdrop,\n"
        "                        shadowColor: colors.shadow,\n"
        "                    },\n"
        "                ]}>\n"
        "                {children}\n"
        "            </Animated.View>\n"
        "        </View>"
    )
    new_card = (
        "            <KeyboardAvoidingView\n"
        "                behavior=\"padding\"\n"
        "                pointerEvents=\"box-none\"\n"
        "                style={styles.dialogLayer}>\n"
        "                <Animated.View\n"
        "                    style={[\n"
        "                        styles.dialogContainer,\n"
        "                        dialogContainerStyle,\n"
        "                        containerStyle,\n"
        "                        scaleAnimationStyle,\n"
        "                        {\n"
        "                            backgroundColor: colors.backdrop,\n"
        "                            shadowColor: colors.shadow,\n"
        "                        },\n"
        "                    ]}>\n"
        "                    {children}\n"
        "                </Animated.View>\n"
        "            </KeyboardAvoidingView>\n"
        "        </View>"
    )
    old_container = '    dialogContainer: {\n        position: "absolute",\n        width: "80%",'
    new_container = (
        "    dialogLayer: {\n"
        "        position: \"absolute\",\n"
        "        top: 0,\n"
        "        left: 0,\n"
        "        width: \"100%\",\n"
        "        height: \"100%\",\n"
        "        alignItems: \"center\",\n"
        "        justifyContent: \"center\",\n"
        "        zIndex: 16310,\n"
        "    },\n"
        "    dialogContainer: {\n"
        "        width: \"80%\","
    )
    if new_card in text and "dialogLayer:" in text and new_import in text:
        report["dialogs/base/index.tsx"] = ["already present"]
    else:
        for label, needle in (
            ("KeyboardAvoidingView import", old_import),
            ("dialog card markup", old_card),
            ("dialogContainer style", old_container),
        ):
            if needle not in text:
                raise RuntimeError(
                    f"dialogs/components/base/index.tsx: {label} anchor not found — "
                    "upstream changed the dialog layout, review manually")
        text = (
            text.replace(old_import, new_import, 1)
            .replace(old_card, new_card, 1)
            .replace(old_container, new_container, 1)
        )
        dialogs.write_text(text, encoding="utf-8")
        changes.append("dialog card moved into a keyboard-avoiding centring layer")
        report["dialogs/base/index.tsx"] = changes

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--ref", required=True)
    args = ap.parse_args()

    upstream = Path(args.root) / "upstream"
    ios = upstream / "ios"
    report: dict[str, object] = {"ref": args.ref}

    podfile = ios / "Podfile"
    info = ios / "MusicFree" / "Info.plist"
    pbxproj = ios / "MusicFree.xcodeproj" / "project.pbxproj"
    bootstrap = upstream / "src/entry/bootstrap/bootstrap.ts"
    entry_index = upstream / "src/entry/index.tsx"
    panel_base = upstream / "src/components/panels/base/panelBase.tsx"
    dialog_base = upstream / "src/components/dialogs/components/base/index.tsx"
    plugin_manager = upstream / "src/core/pluginManager/index.ts"
    plugin_list = upstream / ("src/pages/setting/settingTypes/pluginSetting"
                              "/views/pluginList.tsx")
    launch_storyboard = ios / "MusicFree" / "LaunchScreen.storyboard"
    splash_storyboard = ios / "MusicFree" / "SplashScreen.storyboard"
    for required in (podfile, info, pbxproj, bootstrap, entry_index,
                     panel_base, dialog_base, launch_storyboard,
                     plugin_manager, plugin_list):
        if not required.exists():
            print(json.dumps({"error": f"missing upstream file: {required}"}, indent=2))
            return 1

    try:
        report["Podfile"] = inject_podfile(podfile)
        report["Info.plist"] = inject_info_plist(info)
        # The Widget Extension must be added BEFORE inject_pbxproj so the
        # version-number rewrites in that step also reach the new target.
        report["LiveActivity target"] = inject_live_activity.inject(pbxproj)
        inject_live_activity.verify_definitions(pbxproj)
        report["project.pbxproj"] = inject_pbxproj(pbxproj, args.ref)
        report["SplashScreen.storyboard"] = inject_storyboard(
            launch_storyboard, splash_storyboard)
        report["bootstrap.ts"] = inject_bootstrap(bootstrap)
        report["src/entry/index.tsx"] = inject_entry_index(entry_index)
        report.update(inject_keyboard_avoidance(panel_base, dialog_base))
        report.update(inject_plugin_install(plugin_manager, plugin_list))
    except Exception as exc:  # noqa: BLE001 - surface actionable message to CI
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
