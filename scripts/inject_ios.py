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
    launch_storyboard = ios / "MusicFree" / "LaunchScreen.storyboard"
    splash_storyboard = ios / "MusicFree" / "SplashScreen.storyboard"
    for required in (podfile, info, pbxproj, bootstrap, entry_index, launch_storyboard):
        if not required.exists():
            print(json.dumps({"error": f"missing upstream file: {required}"}, indent=2))
            return 1

    try:
        report["Podfile"] = inject_podfile(podfile)
        report["Info.plist"] = inject_info_plist(info)
        report["project.pbxproj"] = inject_pbxproj(pbxproj, args.ref)
        report["SplashScreen.storyboard"] = inject_storyboard(
            launch_storyboard, splash_storyboard)
        report["bootstrap.ts"] = inject_bootstrap(bootstrap)
        report["src/entry/index.tsx"] = inject_entry_index(entry_index)
    except Exception as exc:  # noqa: BLE001 - surface actionable message to CI
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
