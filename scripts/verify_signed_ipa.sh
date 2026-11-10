#!/usr/bin/env bash
# Check that a *signed* IPA was signed recursively, not just the main binary.
#
#   bash scripts/verify_signed_ipa.sh path/to/MusicFree-signed.ipa
#
# The unsigned build ships Payload/MusicFree.app/Frameworks/hermes.framework.
# If a sideload tool only signs the .app, dyld aborts before main() and the app
# appears to "crash on open". This script catches exactly that case.
#
# Requires macOS with codesign (full Xcode OR CommandLineTools is enough).
set -uo pipefail

IPA="${1:-}"
if [[ -z "${IPA}" || ! -f "${IPA}" ]]; then
  echo "usage: bash scripts/verify_signed_ipa.sh <path/to/signed.ipa>" >&2
  exit 2
fi
command -v codesign >/dev/null 2>&1 || {
  echo "codesign not found — this script must run on macOS" >&2
  exit 2
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
unzip -q "${IPA}" -d "${TMP}" || { echo "cannot unzip ipa" >&2; exit 1; }

APP="$(find "${TMP}/Payload" -maxdepth 1 -type d -name '*.app' -print -quit 2>/dev/null)"
if [[ -z "${APP}" ]]; then
  echo "FAIL: no Payload/*.app found" >&2
  exit 1
fi

echo "ipa : ${IPA}"
echo "app : $(basename "${APP}")"
FAIL=0

# 1. Every nested framework must carry its own valid signature.
FW_COUNT=0
if [[ -d "${APP}/Frameworks" ]]; then
  while IFS= read -r -d '' fw; do
    FW_COUNT=$((FW_COUNT + 1))
    if codesign --verify --strict --verbose=1 "${fw}" >"${TMP}/ok" 2>"${TMP}/err"; then
      echo "  [OK]   framework signed : $(basename "${fw}")"
    else
      echo "  [FAIL] framework NOT signed : $(basename "${fw}")"
      sed 's/^/           /' "${TMP}/err" | head -4
      FAIL=1
    fi
  done < <(find "${APP}/Frameworks" -type d -name '*.framework' -print0 2>/dev/null)
else
  echo "  [--]   no Frameworks/ directory in this ipa"
fi

# 2. App extensions (Widget / Live Activity) must be signed before the .app.
for ext in "${APP}"/PlugIns/*.appex; do
  [[ -d "${ext}" ]] || continue
  if codesign --verify --strict --verbose=1 "${ext}" >"${TMP}/ok" 2>"${TMP}/err"; then
    echo "  [OK]   extension signed : $(basename "${ext}")"
  else
    echo "  [FAIL] extension NOT signed : $(basename "${ext}")"
    sed 's/^/           /' "${TMP}/err" | head -4
    FAIL=1
  fi
done

# 3. Whole-bundle deep verification.
if codesign --verify --deep --strict --verbose=1 "${APP}" >"${TMP}/ok" 2>"${TMP}/err"; then
  echo "  [OK]   codesign --verify --deep --strict passed"
else
  echo "  [FAIL] deep signature verification failed"
  sed 's/^/           /' "${TMP}/err" | head -8
  FAIL=1
fi

# 4. Provisioning profile + entitlements must be present and self-consistent.
if [[ -f "${APP}/embedded.mobileprovision" ]]; then
  echo "  [OK]   embedded.mobileprovision present"
else
  echo "  [WARN] no embedded.mobileprovision (free dev signing may still work)"
fi
ENT="$(codesign -d --entitlements - "${APP}" 2>/dev/null | tr -d '\0' | tr -d '\n' | head -c 300)"
if [[ -n "${ENT}" ]]; then
  echo "  [OK]   entitlements: ${ENT}"
else
  echo "  [WARN] no entitlements found"
fi

echo "frameworks checked: ${FW_COUNT}"
if [[ "${FAIL}" -eq 0 ]]; then
  echo "SIGN OK: nested frameworks, extensions and the app all verify."
  echo "If the app still crashes on launch, export the .ips crash log — the cause is no longer code signing."
  exit 0
fi
echo "SIGN FAILED: re-sign the IPA with a tool that recursively signs Frameworks/" >&2
echo "See docs/signing-and-crash-guide.html for the exact codesign order." >&2
exit 1
