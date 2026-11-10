#!/usr/bin/env python3
"""Verify that the produced .ipa is unsigned and actually contains a JS bundle."""
from __future__ import annotations

import hashlib
import json
import plistlib
import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_ipa.py <path/to.ipa>", file=sys.stderr)
        return 2

    p = Path(sys.argv[1])
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

    report = {
        "ipa": str(p),
        "bytes": p.stat().st_size,
        "sha256": sha,
        "app": apps[0],
        "bundle_id": info.get("CFBundleIdentifier"),
        "marketing_version": info.get("CFBundleShortVersionString"),
        "build_version": info.get("CFBundleVersion"),
        "min_os": info.get("MinimumOSVersion"),
        "platforms": info.get("CFBundleSupportedPlatforms"),
        "js_bundle_included": bool(bundles),
        "executable_included": exe_present,
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
    if failed:
        print("VERIFY FAILED: " + "; ".join(failed), file=sys.stderr)
        return 1
    print("VERIFY OK: unsigned iOS ipa with embedded JS bundle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
