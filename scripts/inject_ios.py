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

    # GitHub Actions macOS runners ship the iPhoneOS SDK but ibtool cannot
    # resolve a matching "iOS 18.2 Platform" while compiling the RN template's
    # LaunchScreen.storyboard -> "error: iOS 18.2 Platform Not Installed."
    # An Info.plist launch screen (iOS 14+) needs no storyboard compilation at
    # all, which is both deterministic on CI and harmless on a real device.
    if data.pop("UILaunchStoryboardName", None) is not None:
        changes.append("UILaunchStoryboardName removed (ibtool CI workaround)")
    if "UILaunchScreen" not in data:
        data["UILaunchScreen"] = {}
        changes.append("UILaunchScreen = {} (plist-based launch screen)")

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

    # Drop LaunchScreen.storyboard from the Resources build phase (and its
    # PBXBuildFile entry). Keeping the orphan PBXFileReference / group entry is
    # intentional: it keeps the diff tiny and Xcode tolerates it. Without this,
    # ibtool fails on CI with "iOS 18.2 Platform Not Installed".
    text, n = re.subn(
        r'^\s*[0-9A-Fa-f]{24}\s+/\* LaunchScreen\.storyboard in Resources \*/[^\n]*\n',
        '', text, flags=re.M,
    )
    if n:
        changes.append(f"LaunchScreen.storyboard removed from Resources ({n} refs)")

    if text != original:
        path.write_text(text, encoding="utf-8")
    return changes or ["already present"]


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
    for required in (podfile, info, pbxproj):
        if not required.exists():
            print(json.dumps({"error": f"missing upstream file: {required}"}, indent=2))
            return 1

    try:
        report["Podfile"] = inject_podfile(podfile)
        report["Info.plist"] = inject_info_plist(info)
        report["project.pbxproj"] = inject_pbxproj(pbxproj, args.ref)
    except Exception as exc:  # noqa: BLE001 - surface actionable message to CI
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
