#!/usr/bin/env python3
"""Detect new upstream MusicFree releases and re-apply the iOS adapter.

  python3 scripts/sync_upstream.py --check          # just report
  python3 scripts/sync_upstream.py --apply          # bump UPSTREAM_REF + prepare
  python3 scripts/sync_upstream.py --apply --ref v0.6.2   # pin a specific tag

Note: GitHub's `/releases/latest` endpoint skips prereleases. MusicFree's newest
tags are all `-beta.N`, so relying on it would silently DOWNGRADE the adapter.
We therefore collect tags from both the releases API and `git ls-remote`, then
pick the highest semantic version ourselves.

On --apply, UPSTREAM_REF is rolled back if prepare/verification fails, so the
repository never ends up pointing at a tag that cannot be adapted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com/repos/maotoumao/MusicFree/releases?per_page=30"
REPO = os.environ.get("MUSICFREE_UPSTREAM_REPO", "https://github.com/maotoumao/MusicFree.git")


def tag_key(tag: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?", tag)
    if not m:
        return (0, 0, 0, 0, tag)
    a, b, c = (int(m.group(i)) for i in (1, 2, 3))
    # A stable release outranks its own betas: beta.4 -> 4, stable -> 999.
    beta = int(m.group(4)) if m.group(4) else 999
    return (a, b, c, beta, tag)


def tags_from_api() -> list[str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "musicfree-ios-adapter"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(API, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return [r["tag_name"] for r in data if isinstance(r, dict) and r.get("tag_name")]
    except Exception as exc:  # noqa: BLE001 - fall back to git
        print(f"[sync] GitHub releases API unavailable ({exc})", file=sys.stderr)
        return []


def tags_from_git() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", "--tags", "--refs", REPO], text=True, timeout=60
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[sync] git ls-remote failed: {exc}", file=sys.stderr)
        return []
    tags = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/tags/"):
            name = parts[1].removeprefix("refs/tags/")
            if name.startswith("v"):
                tags.append(name)
    return tags


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"[sync] $ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=cwd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ref", default="", help="pin a specific upstream tag instead of detecting latest")
    args = ap.parse_args()

    root = Path(args.root)
    ref_file = root / "UPSTREAM_REF"
    current = ref_file.read_text().strip()

    if args.ref.strip():
        latest = args.ref.strip()
    else:
        candidates = set(tags_from_api()) | set(tags_from_git())
        candidates = {t for t in candidates if tag_key(t)[:3] != (0, 0, 0)}
        if not candidates:
            print(json.dumps({"error": "could not determine latest upstream tag"}))
            return 1
        latest = max(candidates, key=tag_key)

    changed = latest != current
    print(json.dumps({"current": current, "latest": latest, "changed": changed}, ensure_ascii=False))

    if args.check or not args.apply:
        return 0
    if not changed:
        print("[sync] already up to date")
        return 0

    old = current
    ref_file.write_text(latest + "\n")
    ok = run(["bash", str(root / "scripts/prepare.sh")], cwd=root) == 0

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    history = root / "SYNC_HISTORY.md"
    with history.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp}: `{old}` -> `{latest}` — {'adaptation OK' if ok else 'FAILED, ref rolled back'}\n")

    if not ok:
        ref_file.write_text(old + "\n")
        print("[sync] adaptation failed; UPSTREAM_REF restored. Review overlay/ before retrying.", file=sys.stderr)
        return 1

    print(f"[sync] {old} -> {latest}: iOS adapter re-applied and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
