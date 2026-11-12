#!/usr/bin/env python3
"""Bump the *adapter* release version, independently of the upstream tag.

Why two version files exist
---------------------------
``UPSTREAM_REF`` pins the upstream MusicFree tag we adapt (``v1.0.0-beta.4``).
It must NOT be used as the shipped app version: the iOS adapter keeps evolving
in batches while upstream stays on the same tag, and shipping every rebuild as
``1.0.0`` / ``MusicFree-v1.0.0-beta.4-unsigned.ipa`` makes it impossible to tell
which build a user actually installed.

``ADAPTER_VERSION`` is the single source of truth for the app version
(``CFBundleShortVersionString`` / ``MARKETING_VERSION`` / IPA filename / release
tag). ``ADAPTER_BUILD`` is ``CFBundleVersion`` / ``CURRENT_PROJECT_VERSION``.
Both are plain files so local builds and CI produce identical numbers.

Version policy
--------------
  * new feature batch  -> ``minor`` (1.1.0 -> 1.2.0)
  * bugfix / docs only -> ``patch`` (1.1.0 -> 1.1.1)
  * upstream tag bump  -> ``minor`` (new baseline, new adapter release)
  * every bump         -> ADAPTER_BUILD += 1

Usage
-----
  python3 scripts/bump_version.py minor
  python3 scripts/bump_version.py patch
  python3 scripts/bump_version.py --set 2.0.0
  python3 scripts/bump_version.py --show

The script only touches the two version files. After bumping, run
``bash scripts/prepare.sh`` so the new numbers are injected into the project.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "ADAPTER_VERSION"
BUILD_FILE = ROOT / "ADAPTER_BUILD"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_version() -> tuple[int, int, int]:
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    m = SEMVER.match(raw)
    if not m:
        raise SystemExit(f"ADAPTER_VERSION is not x.y.z: {raw!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def read_build() -> int:
    raw = BUILD_FILE.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        raise SystemExit(f"ADAPTER_BUILD is not an integer: {raw!r}")
    return int(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", nargs="?", choices=("major", "minor", "patch"),
                    help="which semver component to increment")
    ap.add_argument("--set", dest="explicit", metavar="X.Y.Z",
                    help="set an exact version instead of incrementing")
    ap.add_argument("--show", action="store_true", help="print current values and exit")
    args = ap.parse_args()

    old_version = read_version()
    old_build = read_build()
    if args.show:
        print(json.dumps({
            "adapter_version": ".".join(map(str, old_version)),
            "adapter_build": old_build,
            "upstream_ref": (ROOT / "UPSTREAM_REF").read_text().strip(),
        }))
        return 0
    if not args.part and not args.explicit:
        ap.error("pass major|minor|patch, --set X.Y.Z, or --show")

    if args.explicit:
        m = SEMVER.match(args.explicit.strip())
        if not m:
            raise SystemExit(f"--set expects x.y.z, got {args.explicit!r}")
        new_version = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        major, minor, patch = old_version
        new_version = {
            "major": (major + 1, 0, 0),
            "minor": (major, minor + 1, 0),
            "patch": (major, minor, patch + 1),
        }[args.part]

    if new_version == old_version:
        raise SystemExit("version did not change; nothing to bump")

    new_build = old_build + 1
    VERSION_FILE.write_text(".".join(map(str, new_version)) + "\n", encoding="utf-8")
    BUILD_FILE.write_text(f"{new_build}\n", encoding="utf-8")
    before = ".".join(map(str, old_version))
    after = ".".join(map(str, new_version))
    print(json.dumps({
        "adapter_version": {"from": before, "to": after},
        "adapter_build": {"from": old_build, "to": new_build},
        "ipa": f"MusicFree-v{after}-ios-unsigned.ipa",
        "next": "bash scripts/prepare.sh && bash scripts/build_unsigned_ipa.sh",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
