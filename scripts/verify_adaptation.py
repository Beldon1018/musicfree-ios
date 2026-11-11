#!/usr/bin/env python3
"""Static verification of the iOS adaptation — runs without Xcode.

It checks that every Android-only native module referenced by upstream JS has a
platform override, that the local pod is wired in, and that the Xcode project
will actually embed a JS bundle in a Release archive.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()

    root = Path(args.root)
    upstream = root / "upstream"
    src = upstream / "src"
    ios = upstream / "ios"

    # 1. Platform overrides for every Android-only native module.
    overrides = {
        "NativeUtils": src / "native/utils/index.ios.ts",
        "Mp3Util": src / "native/mp3Util/index.ios.ts",
        "LyricUtil": src / "native/lyricUtil/index.ios.ts",
    }
    for module, path in overrides.items():
        check(path.exists(), f"override for {module}", str(path.relative_to(upstream)) if path.exists() else "MISSING")

    lyric = overrides["LyricUtil"]
    if lyric.exists():
        text = lyric.read_text(encoding="utf-8")
        check("NativeTextAlignment" in text, "NativeTextAlignment enum preserved",
              "upstream setting pages import it")
        check("checkSystemAlertPermission" in text, "status-bar lyric API complete")

    # Scan upstream JS for any *other* bare NativeModules.X usage.
    referenced: set[str] = set()
    for file in src.rglob("*"):
        if file.suffix not in {".ts", ".tsx", ".js", ".jsx"} or ".ios." in file.name:
            continue
        referenced.update(re.findall(r"NativeModules\.([A-Za-z_][A-Za-z0-9_]*)", file.read_text(encoding="utf-8", errors="ignore")))
    unknown = referenced - set(overrides) - {"NativeModules"}
    check(not unknown, "no uncovered native modules", f"uncovered: {sorted(unknown)}" if unknown else f"covered: {sorted(referenced)}")

    # 2. Local pod wired in and complete.
    podfile = ios / "Podfile"
    podfile_text = podfile.read_text(encoding="utf-8") if podfile.exists() else ""
    check("MusicFreeNative" in podfile_text, "Podfile links MusicFreeNative")
    check("ENV['RCT_NEW_ARCH_ENABLED'] = '0'" in podfile_text,
          "Podfile forces legacy architecture (RN 0.76 defaults new arch ON; "
          "bridgeless proxy crashed on strlen(NULL) at startup)")
    pod_dir = ios / "LocalPods" / "MusicFreeNative"
    for rel in ("MusicFreeNative.podspec", "MusicFreeNative/NativeUtilsModule.m", "MusicFreeNative/Mp3UtilModule.m"):
        check((pod_dir / rel).exists(), f"pod file {rel}")
    if (pod_dir / "MusicFreeNative/NativeUtilsModule.m").exists():
        check("RCT_EXPORT_MODULE(NativeUtils)" in (pod_dir / "MusicFreeNative/NativeUtilsModule.m").read_text(),
              "NativeUtils module name matches Android")
    if (pod_dir / "MusicFreeNative/Mp3UtilModule.m").exists():
        check("RCT_EXPORT_MODULE(Mp3Util)" in (pod_dir / "MusicFreeNative/Mp3UtilModule.m").read_text(),
              "Mp3Util module name matches Android")

    # 3. Info.plist capabilities.
    info = ios / "MusicFree" / "Info.plist"
    if info.exists():
        with info.open("rb") as fh:
            plist = plistlib.load(fh)
        check("audio" in (plist.get("UIBackgroundModes") or []), "background audio enabled")
        check((plist.get("NSAppTransportSecurity") or {}).get("NSAllowsArbitraryLoads") is True,
              "arbitrary loads allowed (plugin sources use http)")
        check(plist.get("UIFileSharingEnabled") is True, "document/file sharing enabled")
        check(plist.get("UILaunchStoryboardName") == "SplashScreen",
              "launch screen points at SplashScreen (Expo hardcodes that name)")
        check("UILaunchScreen" not in plist,
              "no stale plist-based launch-screen override")
        check(plist.get("NSSupportsLiveActivities") is True,
              "Live Activity capability declared")
    else:
        check(False, "Info.plist exists")

    splash = ios / "MusicFree" / "SplashScreen.storyboard"
    check(splash.exists(), "SplashScreen.storyboard source present")
    if splash.exists():
        st = splash.read_text(encoding="utf-8")
        check("<dependencies>" not in st and "<device " not in st,
              "storyboard has no <deployment identifier=iOS> (ibtool CI fix)")
        check("initialViewController" in st and "<scenes>" in st,
              "storyboard still has a launch scene")

    # 4. Xcode project settings + JS bundle phase.
    pbxproj = ios / "MusicFree.xcodeproj" / "project.pbxproj"
    pbx_text = pbxproj.read_text(encoding="utf-8") if pbxproj.exists() else ""
    check("org.reactjs.native.example" not in pbx_text, "template bundle id replaced")
    check("export:embed" in pbx_text or "react-native-xcode.sh" in pbx_text,
          "Release archive will embed main.jsbundle")
    check((ios / "Podfile.properties.json").exists(), "Expo Podfile.properties.json present")
    check("SplashScreen.storyboard in Resources" in pbx_text,
          "SplashScreen.storyboard compiled into Resources")
    check("LaunchScreen.storyboard" not in pbx_text,
          "no stale LaunchScreen.storyboard references in project")

    # 4a. iOS startup path must not run Android-only APIs.
    bootstrap = src / "entry" / "bootstrap" / "bootstrap.ts"
    if bootstrap.exists():
        bt = bootstrap.read_text(encoding="utf-8")
        check('} else if (Platform.OS === "android") {' in bt,
              "bootstrap skips PERMISSIONS.ANDROID.* on iOS")
    else:
        check(False, "bootstrap.ts exists")

    entry_index = src / "entry" / "index.tsx"
    if entry_index.exists():
        et = entry_index.read_text(encoding="utf-8")
        check('import { Platform, StatusBar } from "react-native";' in et
              and 'if (Platform.OS === "android") {' in et,
              "top-level Android-only StatusBar calls guarded on iOS")
    else:
        check(False, "src/entry/index.tsx exists")

    # 4c. Soft keyboard must not cover dialog / bottom-sheet text inputs.
    #     Android resizes the window so upstream never needed this; on iOS the
    #     keyboard just overlays the app.
    panel_base = src / "components" / "panels" / "base" / "panelBase.tsx"
    if panel_base.exists():
        pt = panel_base.read_text(encoding="utf-8")
        check("kbOffset.value" in pt and "keyboardWillChangeFrame" in pt,
              "bottom sheet lifted by the keyboard height "
              "(KeyboardAvoidingView cannot move an absolutely positioned sheet)")
        check('<View style={style.kbContainer} pointerEvents="box-none">' in pt,
              "sheet anchored in an explicit box-none container")
        check("<KeyboardAvoidingView" not in pt,
              "no KeyboardAvoidingView rendered by panelBase (behaviour=position "
              "inverted panels such as the '+' menu once the wrapper had size)")
    else:
        check(False, "panels/base/panelBase.tsx exists")

    dialog_base = src / "components" / "dialogs" / "components" / "base" / "index.tsx"
    if dialog_base.exists():
        dt = dialog_base.read_text(encoding="utf-8")
        check("KeyboardAvoidingView" in dt and 'behavior="padding"' in dt,
              "dialog card wrapped in KeyboardAvoidingView")
        check("dialogLayer:" in dt and "justifyContent: \"center\"" in dt,
              "dialog centring layer exists")
    else:
        check(False, "dialogs/components/base/index.tsx exists")

    # 4b. iOS-native replacements for the three degraded features.
    pod_src = pod_dir / "MusicFreeNative"
    lyric_native = pod_src / "LyricUtilModule.m"
    check(lyric_native.exists(), "LyricUtil native module exists")
    if lyric_native.exists():
        lt = lyric_native.read_text(encoding="utf-8")
        check("RCT_EXPORT_MODULE(LyricUtil)" in lt, "LyricUtil module name matches Android")
        check("MFLyricWindow" in lt and "UIPanGestureRecognizer" in lt,
              "draggable in-app lyric overlay implemented")

    mp3_native = pod_src / "Mp3UtilModule.m"
    if mp3_native.exists():
        mt = mp3_native.read_text(encoding="utf-8")
        check("USLT" in mt and "MFEmbeddedLyricForAsset" in mt,
              "embedded ID3 lyric reading implemented")
        check("MFWriteOverrideForPath" in mt and "MFApplyOverride" in mt,
              "in-app metadata override (ID3 write replacement) implemented")

    check((pod_src / "MusicFreeLiveActivityModule.m").exists(),
          "optional Live Activity RN bridge present")

    # 4d. Live Activity must be WIRED INTO THE PROJECT, not just present as
    #     source. A Widget Extension target is the only place ActivityKit can
    #     render Dynamic Island / Lock Screen lyrics; without it the RN module
    #     silently no-ops (NSClassFromString returns nil), which is exactly the
    #     state this check exists to prevent from shipping again.
    la_dir = ios / "LiveActivity"
    for rel in ("MusicFreeLyricAttributes.swift",
                "MusicFreeLiveActivityController.swift",
                "MusicFreeLiveActivityWidget.swift",
                "Info.plist", "README.md"):
        check((la_dir / rel).exists(), f"LiveActivity source {rel}")

    attrs = la_dir / "MusicFreeLyricAttributes.swift"
    if attrs.exists():
        check("@available(iOS 16.1, *)" in attrs.read_text(encoding="utf-8"),
              "ActivityAttributes guarded for the iOS 15.1 app target")

    ext_info = la_dir / "Info.plist"
    if ext_info.exists():
        with ext_info.open("rb") as fh:
            ext_plist = plistlib.load(fh)
        check((ext_plist.get("NSExtension") or {}).get("NSExtensionPointIdentifier")
              == "com.apple.widgetkit-extension",
              "extension Info.plist declares the widgetkit extension point")

    check("name = MusicFreeLiveActivity;\n\t\t\tproductName = MusicFreeLiveActivity;"
          in pbx_text,
          "Widget Extension target exists in project.pbxproj")
    check("Embed App Extensions" in pbx_text and "dstSubfolderSpec = 13" in pbx_text,
          "app embeds the .appex into PlugIns")
    check("com.apple.product-type.app-extension" in pbx_text,
          "extension target uses the app-extension product type")
    check("INFOPLIST_FILE = LiveActivity/Info.plist;" in pbx_text,
          "extension builds against LiveActivity/Info.plist")
    check("IPHONEOS_DEPLOYMENT_TARGET = 16.1;" in pbx_text,
          "extension deploys to iOS 16.1 (ActivityKit minimum)")
    for swift_ref in ("MusicFreeLiveActivityWidget.swift in Sources",
                      "MusicFreeLiveActivityController.swift in Sources"):
        check(pbx_text.count(swift_ref) >= 2,  # build file + build phase entry
              f"target compiles {swift_ref.split(' in ')[0]}")

    build_script = root / "scripts" / "build_unsigned_ipa.sh"
    check(build_script.exists() and "-sdk iphoneos" in build_script.read_text(encoding="utf-8"),
          "xcodebuild pins -sdk iphoneos")

    # 5. App entry point.
    check((upstream / "index.js").exists() or (upstream / "index.ts").exists(), "JS entry point exists")

    for ok, name, detail in RESULTS:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))
    failed = [name for ok, name, _ in RESULTS if not ok]
    print(json.dumps({"checks": len(RESULTS), "failed": len(failed), "failures": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
