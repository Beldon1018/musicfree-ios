#!/usr/bin/env python3
"""Verify that the produced .ipa is unsigned and actually contains a JS bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import sys
import zipfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ipa")
    ap.add_argument("--expected-version", default="",
                    help="fail unless the built Info.plist carries this "
                         "ADAPTER_VERSION and CFBundleShortVersionString")
    args = ap.parse_args()

    p = Path(args.ipa)
    if not p.is_file():
        print(json.dumps({"error": f"not found: {p}"}))
        return 1

    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        apps = sorted({n.split("/")[1] for n in names if n.startswith("Payload/") and len(n.split("/")) > 2 and n.split("/")[1].endswith(".app")})
        if not apps:
            print(json.dumps({"error": "no Payload/*.app found"}))
            return 1
        app = f"Payload/{apps[0]}"
        with z.open(f"{app}/Info.plist") as fh:
            info = plistlib.load(fh)

        signature_files = [n for n in names if any(k in n for k in
                           ("_CodeSignature", "embedded.mobileprovision", "CodeResources", "SC_Info"))]
        bundles = [n for n in names if n.endswith("main.jsbundle")]
        executable = info.get("CFBundleExecutable", "")
        exe_present = f"{app}/{executable}" in names
        launch_resources = [n for n in names
                            if ".storyboardc" in n or n.endswith(".nib")]
        # Expo SDK 52 hardcodes UIStoryboard(name: "SplashScreen", bundle: nil)
        # during native startup. Missing this resource throws before RN mounts.
        splash_resources = [n for n in names if "SplashScreen.storyboardc" in n]
        nested_frameworks = sorted({
            n.split("/")[3] for n in names
            if "/Frameworks/" in n
            and len(n.split("/")) > 3
            and n.split("/")[3].endswith(".framework")
        })
        # Widget extensions live in PlugIns/*.appex and are only rendered by
        # the system when the ipa actually contains them — the Dynamic Island
        # lyrics come from MusicFreeLiveActivity.appex, not from the app binary.
        appex = sorted({
            n.split("/")[3] for n in names
            if n.startswith(f"{app}/PlugIns/")
            and len(n.split("/")) > 3
            and n.split("/")[3].endswith(".appex")
        })
        appex_plist = {}
        for bundle in appex:
            try:
                with z.open(f"{app}/PlugIns/{bundle}/Info.plist") as fh:
                    appex_plist[bundle] = plistlib.load(fh)
            except KeyError:
                appex_plist[bundle] = {}

    report = {
        "ipa": str(p),
        "bytes": p.stat().st_size,
        "sha256": sha,
        "app": apps[0],
        "bundle_id": info.get("CFBundleIdentifier"),
        "marketing_version": info.get("CFBundleShortVersionString"),
        "build_version": info.get("CFBundleVersion"),
        "adapter_version": info.get("MusicFreeAdapterVersion"),
        "upstream_ref": info.get("MusicFreeUpstreamRef"),
        "min_os": info.get("MinimumOSVersion"),
        "platforms": info.get("CFBundleSupportedPlatforms"),
        "js_bundle_included": bool(bundles),
        "executable_included": exe_present,
        "launch_screen_resources": len(launch_resources),
        "expo_splash_screen_present": bool(splash_resources),
        "nested_frameworks_to_resign": nested_frameworks,
        "app_extensions": appex,
        "app_extension_point_ids": {
            k: (v.get("NSExtension") or {}).get("NSExtensionPointIdentifier")
            for k, v in appex_plist.items()
        },
        "signature_files": signature_files,
        "unsigned": not signature_files,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    failed = []
    if signature_files:
        failed.append("ipa is signed (expected unsigned)")
    if not bundles:
        failed.append("main.jsbundle missing — app would launch to a blank screen")
    if not exe_present:
        failed.append("Mach-O executable missing")
    if args.expected_version:
        expected = args.expected_version.strip()
        marketing = info.get("CFBundleShortVersionString")
        adapter = info.get("MusicFreeAdapterVersion")
        if marketing != expected:
            failed.append(f"CFBundleShortVersionString is {marketing!r}, "
                          f"expected ADAPTER_VERSION {expected!r}")
        if adapter != expected:
            failed.append(f"MusicFreeAdapterVersion is {adapter!r}, "
                          f"expected {expected!r} — stale pbxproj/plist injection")
    if not launch_resources:
        failed.append("no compiled launch screen in bundle — "
                      "system has nothing to show during cold start")
    if not splash_resources:
        failed.append("SplashScreen.storyboardc missing — Expo SDK 52 calls "
                      "UIStoryboard(name: 'SplashScreen') at native startup "
                      "and throws when it is absent (launch crash)")
    # A missing .appex used to be printed as a hint while the script still
    # returned 0. That is exactly how a build with all three Swift sources
    # present but no Widget Extension target shipped as "VERIFY OK" — the
    # Dynamic Island then silently showed nothing. Treat it as a hard failure.
    if not appex:
        failed.append("Widget Extension (.appex) missing — Dynamic Island / "
                      "Lock Screen lyrics cannot appear")
    else:
        bad_points = []
        for name, ext_plist in appex_plist.items():
            ext = ext_plist.get("NSExtension") or {}
            point = ext.get("NSExtensionPointIdentifier")
            if point != "com.apple.widgetkit-extension":
                bad_points.append(f"{name}: {point!r}")
        if bad_points:
            failed.append("app extension has the wrong extension point "
                          "(expected com.apple.widgetkit-extension): "
                          + ", ".join(bad_points))
    if failed:
        print("VERIFY FAILED: " + "; ".join(failed), file=sys.stderr)
        return 1
    print("VERIFY OK: unsigned iOS ipa with embedded JS bundle and launch screen")
    if nested_frameworks:
        print("RESIGN NOTE: these nested frameworks MUST be codesigned recursively "
              "by the sideload tool, otherwise dyld aborts at launch: "
              + ", ".join(nested_frameworks))
    if appex:
        print("RESIGN NOTE: the embedded Widget Extension MUST be signed too "
              "(sign each .appex first, then the .app, then repack Payload/), "
              "otherwise iOS rejects the install: " + ", ".join(appex))
        print("LIVE ACTIVITY: present — enable 设置 → 歌词 → 桌面歌词 to start it")
    # No appex means `failed` is non-empty and we already returned 1 above.
    return 0


if __name__ == "__main__":
    sys.exit(main())
