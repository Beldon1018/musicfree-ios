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
        url_schemes = [
            scheme
            for entry in (plist.get("CFBundleURLTypes") or [])
            if isinstance(entry, dict)
            for scheme in (entry.get("CFBundleURLSchemes") or [])
        ]
        check("musicfree" in url_schemes,
              "musicfree:// URL scheme declared (plugin install deep link)")
        doc_types = plist.get("CFBundleDocumentTypes") or []
        check(any("public.audio" in (d.get("LSItemContentTypes") or [])
                  for d in doc_types if isinstance(d, dict)),
              "audio document types declared (open-in from Files)")
        imported_types = {
            t.get("UTTypeIdentifier")
            for t in (plist.get("UTImportedTypeDeclarations") or [])
            if isinstance(t, dict)
        }
        check("com.musicfree.lrc" in imported_types,
              ".lrc document type declared (open-in from Files)")
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

    # 4d. Plugin installation must not inherit the 2 s runtime axios timeout.
    #     plugin.ts sets axios.defaults.timeout = 2000 for the calls a plugin
    #     makes while playing; the download of the 16-26 KB bundle reuses the
    #     same instance and routinely needs ~1.9 s, so installs failed with
    #     "timeout of 2000ms exceeded".
    plugin_manager = src / "core" / "pluginManager" / "index.ts"
    if plugin_manager.exists():
        pm = plugin_manager.read_text(encoding="utf-8")
        check("timeout: 30000," in pm,
              "plugin download carries its own 30 s timeout "
              "(the 2 s global default made installs fail on any slow network)")
        check("_timedOut" in pm,
              "download timeout is surfaced as an actionable message")
    else:
        check(False, "core/pluginManager/index.ts exists")

    plugin_list = (src / "pages" / "setting" / "settingTypes" / "pluginSetting"
                   / "views" / "pluginList.tsx")
    if plugin_list.exists():
        pl = plugin_list.read_text(encoding="utf-8")
        check('inputUrl.endsWith(".json")' in pl,
              "subscription detection uses the trimmed URL "
              "(raw text made a URL with a trailing newline parse as a plugin)")
        check("timeout: 30000," in pl,
              "subscription manifest fetch carries its own 30 s timeout")
    else:
        check(False, "pluginList.tsx exists")

    # 4e. Plugin sandbox must report the real platform, and the remaining
    #     bare axios.get calls must not inherit the 2 s runtime default.
    plugin_ts = src / "core" / "pluginManager" / "plugin.ts"
    if plugin_ts.exists():
        ptx = plugin_ts.read_text(encoding="utf-8")
        check("os: Platform.OS," in ptx and "platform: Platform.OS," in ptx,
              "plugin sandbox reports the real platform via Platform.OS")
        check('os: "android"' not in ptx and 'platform: "android"' not in ptx,
              "no hardcoded android identity in the plugin sandbox")
        check('import { Platform } from "react-native";' in ptx,
              "Platform import present for the plugin sandbox")
    else:
        check(False, "core/pluginManager/plugin.ts exists")

    check_update = src / "utils" / "checkUpdate.ts"
    if check_update.exists():
        check("timeout: 30000" in check_update.read_text(encoding="utf-8"),
              "version check does not inherit the 2 s plugin timeout")
    else:
        check(False, "utils/checkUpdate.ts exists")

    backup_setting = (src / "pages" / "setting" / "settingTypes"
                      / "backupSetting.tsx")
    if backup_setting.exists():
        bt = backup_setting.read_text(encoding="utf-8")
        check("axios.get(url, { timeout: 30000 })" in bt,
              "backup import uses the trimmed URL and its own 30 s timeout")
        check("axios.get(text)" not in bt,
              "backup import no longer fetches the untrimmed raw input")
    else:
        check(False, "backupSetting.tsx exists")

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

    # 4g. Version identity. The shipped version comes from ADAPTER_VERSION,
    #     NOT from UPSTREAM_REF: one upstream tag can back many adapter
    #     releases, and shipping every rebuild as "1.0.0" makes an installed
    #     IPA impossible to identify.
    version_file = root / "ADAPTER_VERSION"
    build_file = root / "ADAPTER_BUILD"
    adapter_version = (version_file.read_text(encoding="utf-8").strip()
                       if version_file.exists() else "")
    adapter_build = (build_file.read_text(encoding="utf-8").strip()
                     if build_file.exists() else "")
    check(bool(re.fullmatch(r"\d+\.\d+\.\d+", adapter_version)),
          "ADAPTER_VERSION is valid semver", adapter_version)
    check(adapter_build.isdigit(), "ADAPTER_BUILD is numeric", adapter_build)
    check(f"MARKETING_VERSION = {adapter_version};" in pbx_text,
          "pbxproj MARKETING_VERSION == ADAPTER_VERSION",
          f"{adapter_version} expected in all targets")
    check(f"CURRENT_PROJECT_VERSION = {adapter_build};" in pbx_text,
          "pbxproj CURRENT_PROJECT_VERSION == ADAPTER_BUILD")
    if info.exists():
        with info.open("rb") as fh:
            version_plist = plistlib.load(fh)
        check(version_plist.get("MusicFreeAdapterVersion") == adapter_version,
              "Info.plist records the adapter release")
        check(version_plist.get("MusicFreeUpstreamRef")
              == (root / "UPSTREAM_REF").read_text(encoding="utf-8").strip(),
              "Info.plist records the upstream baseline")
        check(version_plist.get("CFBundleShortVersionString") == "$(MARKETING_VERSION)",
              "CFBundleShortVersionString resolves MARKETING_VERSION")
    check((root / "scripts" / "bump_version.py").exists(),
          "bump_version.py available for the next release")

    # 4h. Batch 2 — Live Activity state is structured, mutable and driven by
    #     exactly one guarded publisher. These are structural checks (parse the
    #     ContentState block, look for forbidden patterns), not mere echoes of
    #     the strings the injector wrote.
    if attrs.exists():
        at = attrs.read_text(encoding="utf-8")
        cs_match = re.search(
            r"public struct ContentState: Codable, Hashable \{(.*?)\n    \}",
            at, re.S)
        cs_body = cs_match.group(1) if cs_match else ""
        check(bool(cs_body), "ContentState block parsed structurally")
        for field, label in (
            ("var title: String", "mutable track title"),
            ("var artist: String", "mutable artist"),
            ("var translation: String?", "separate translation line"),
            ("var previousLyric: String?", "previous line"),
            ("var nextLyric: String?", "next line"),
            ("var isPlaying: Bool", "play/pause state"),
            ("var duration: Double", "track duration"),
            ("var elapsed: Double", "playback position for the progress bar"),
        ):
            check(field in cs_body, f"ContentState carries {label}")
        # Frozen attributes must not contain any UI field anymore.
        attr_tail = at[cs_match.end():] if cs_match else ""
        check("var title:" not in attr_tail and "var artist:" not in attr_tail,
              "title/artist removed from immutable ActivityAttributes")

    ctrl = la_dir / "MusicFreeLiveActivityController.swift"
    if ctrl.exists():
        ct = ctrl.read_text(encoding="utf-8")
        check("@objc static func applyState" in ct,
              "single JSON-patch entry point exists")
        check("if activities.isEmpty" in ct and "guard startRequested" in ct,
              "start is idempotent (update existing activity, never re-request)")
        check("activity.end(dismissalPolicy: .immediate)" in ct,
              "stop dismisses activities")
        check("DispatchQueue.main.async" in ct,
              "ActivityKit state is confined to the main queue")
        check("minimumInterval: TimeInterval = 0.25" in ct,
              "high-frequency patches throttled after the 4 Hz change")
        check("pushType: nil" in ct,
              "updates stay local (no APNs certificate in a sideload build)")

    widget = la_dir / "MusicFreeLiveActivityWidget.swift"
    if widget.exists():
        wt = widget.read_text(encoding="utf-8")
        check("context.attributes.title" not in wt,
              "Widget no longer reads immutable attributes.title")
        check("state.isPlaying" in wt, "Widget renders play/pause state")
        check("ProgressView(value:" in wt, "Widget renders a progress bar")
        check("ProgressView(timerInterval:" not in wt
              and "Text(timerInterval:" not in wt,
              "no iOS-16-only timerInterval API (unverifiable without an iOS SDK)")
        check("state.translation" in wt and "state.previousLyric" in wt,
              "Widget renders translation and neighbouring lines")

    la_module = pod_src / "MusicFreeLiveActivityModule.m"
    if la_module.exists():
        lm = la_module.read_text(encoding="utf-8")
        check("RCT_EXPORT_METHOD(applyState:" in lm,
              "RN bridge exports the JSON state patch method")
        check("dispatch_get_main_queue()" in lm,
              "RN bridge dispatches every call to the main queue")

    bridge = src / "native" / "liveActivity" / "index.ios.ts"
    check(bridge.exists(), "Live Activity state publisher overlay exists")
    if bridge.exists():
        br = bridge.read_text(encoding="utf-8")
        check("let installed = false" in br and "if (installed" in br,
              "publisher registers RNTP listeners exactly once (O0.2)")
        check("lastLineAdvanceAt" in br and "lyricManager.setup?.()" in br,
              "publisher nudges lyricManager when the line stops advancing")
        check("TrackPlayer.currentMusic" in br,
              "publisher reads the real track title/artist")
        check("lyricManager.currentLyricItem" in br,
              "publisher reads the parsed lyric line")
        check('"lyric.showTranslation"' in br,
              "publisher honours the translation setting")
        check("action: \"start\"" in br and "action: \"stop\"" in br,
              "publisher starts / dismisses the activity")
        check(">= 900" in br,
              "4 Hz progress stream is throttled to ~1 Hz updates")

    lyric_override = overrides["LyricUtil"]
    if lyric_override.exists():
        lo = lyric_override.read_text(encoding="utf-8")
        check('liveCall("start", "MusicFree", "")' not in lo,
              "hardcoded 'MusicFree' title removed from LyricUtil")
        check("startLiveActivity" in lo and "stopLiveActivity" in lo,
              "desktop-lyric toggle starts / stops the activity")

    if bootstrap.exists():
        bt2 = bootstrap.read_text(encoding="utf-8")
        check("progressUpdateEventInterval: 0.25," in bt2,
              "O2: lyric events arrive at 4 Hz instead of 1 Hz")
        check("setupLiveActivityBridge();" in bt2,
              "bridge installed after lyricManager.setup()")
        check("progressUpdateEventInterval: 1," not in bt2,
              "no stale 1 s progress interval")

    lm_src = src / "core" / "lyricManager.ts"
    if lm_src.exists():
        lm_text = lm_src.read_text(encoding="utf-8")
        check("listenersReady" in lm_text,
              "O0.2: lyricManager.setup() listener registration is guarded")
        check("// Adapter: setup() also re-arms" in lm_text
              and "this.refreshLyric(true);" in lm_text,
              "O0.2: guarded setup() still re-arms the track (frozen-lyric fix)")

    # 5. App entry point.
    check((upstream / "index.js").exists() or (upstream / "index.ts").exists(), "JS entry point exists")

    for ok, name, detail in RESULTS:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))
    failed = [name for ok, name, _ in RESULTS if not ok]
    print(json.dumps({"checks": len(RESULTS), "failed": len(failed), "failures": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
