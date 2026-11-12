#!/usr/bin/env python3
"""Behavioural self-test for verify_ipa.py — no Xcode required.

Why this exists: `verify_adaptation.py` mostly asserts that certain strings are
present in files, and the injector writes those same strings. That is a
self-confirming loop. A build once shipped with all Live Activity Swift sources
present, no Widget Extension target, and a green `VERIFY OK` — the `.appex` was
missing but the verifier only printed a hint and returned 0.

This test proves the *behaviour* instead: given a produced IPA, it builds a
copy with every PlugIns/*.appex entry removed and asserts the verifier rejects
it, then asserts the verifier accepts the real IPA.

Usage: python3 scripts/selftest_verify_ipa.py <path/to.ipa>
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

VERIFY = Path(__file__).resolve().with_name("verify_ipa.py")


def strip_appex(src: Path, dst: Path) -> int:
    removed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            if "/PlugIns/" in item.filename:
                removed += 1
                continue
            zout.writestr(item, zin.read(item.filename))
    return removed


def verify(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY), str(path)],
        capture_output=True, text=True, check=False,
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: selftest_verify_ipa.py <path/to.ipa>", file=sys.stderr)
        return 2
    ipa = Path(sys.argv[1])
    if not ipa.is_file():
        print(f"SELFTEST FAILED: not found: {ipa}", file=sys.stderr)
        return 1

    good = verify(ipa)
    if good.returncode != 0:
        print("SELFTEST FAILED: the real IPA does not pass verify_ipa.py",
              file=sys.stderr)
        print(good.stdout + good.stderr, file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="mf-selftest-") as tmp:
        fake = Path(tmp) / "no-appex.ipa"
        removed = strip_appex(ipa, fake)
        if removed == 0:
            print("SELFTEST FAILED: real IPA has no PlugIns entries to strip "
                  "(the test would prove nothing)", file=sys.stderr)
            return 1
        bad = verify(fake)
        if bad.returncode == 0:
            print("SELFTEST FAILED: verify_ipa.py returned 0 for an IPA with "
                  "no .appex — the H5 regression is back", file=sys.stderr)
            print(bad.stdout, file=sys.stderr)
            return 1
        if "Widget Extension" not in bad.stderr:
            print("SELFTEST FAILED: rejection did not name the missing Widget "
                  "Extension", file=sys.stderr)
            print(bad.stderr, file=sys.stderr)
            return 1
        print(f"SELFTEST OK: real IPA passes; IPA with {removed} PlugIns "
              "entries removed is rejected as VERIFY FAILED")

    print(good.stdout.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
