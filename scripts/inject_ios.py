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


def inject_podfile(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if "MusicFreeNative" in text:
        return "already present"

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
    path.write_text(text.replace(needle, block, 1), encoding="utf-8")
    return "injected local pod"


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

    # Keep the upstream LaunchScreen.storyboard. expo-splash-screen reads
    # UILaunchStoryboardName during startup; an app with NO launch-screen
    # resource at all can be killed before React Native mounts. The earlier
    # ibtool "iOS 18.2 Platform Not Installed" failure came from xcodebuild
    # resolving the simulator platform — build_unsigned_ipa.sh now pins
    # -sdk iphoneos, which fixes ibtool without deleting the storyboard.
    if data.pop("UILaunchScreen", None) is not None:
        changes.append("stale UILaunchScreen plist override removed")
    if data.get("UILaunchStoryboardName") != "LaunchScreen":
        data["UILaunchStoryboardName"] = "LaunchScreen"
        changes.append("UILaunchStoryboardName = LaunchScreen (restored)")

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

    # Intentionally KEEP LaunchScreen.storyboard in the Resources build phase.
    # -sdk iphoneos (see build_unsigned_ipa.sh) is the real ibtool fix; removing
    # the storyboard left the IPA with no launch-screen resource, which breaks
    # expo-splash-screen during startup on a real device.

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
    for required in (podfile, info, pbxproj, bootstrap, entry_index):
        if not required.exists():
            print(json.dumps({"error": f"missing upstream file: {required}"}, indent=2))
            return 1

    try:
        report["Podfile"] = inject_podfile(podfile)
        report["Info.plist"] = inject_info_plist(info)
        report["project.pbxproj"] = inject_pbxproj(pbxproj, args.ref)
        report["bootstrap.ts"] = inject_bootstrap(bootstrap)
        report["src/entry/index.tsx"] = inject_entry_index(entry_index)
    except Exception as exc:  # noqa: BLE001 - surface actionable message to CI
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
