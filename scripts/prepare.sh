#!/usr/bin/env bash
# Rebuild a clean, iOS-adapted MusicFree checkout from upstream + overlay.
#
# This script is idempotent: running it twice, or running it after an upstream
# tag change, always produces the same deterministic result.
#
#   MUSICFREE_UPSTREAM_REPO=https://gh-proxy.com/https://github.com/... \
#     bash scripts/prepare.sh
#
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REF="$(read_ref)"
log "adapter root : ${ADAPTER_ROOT}"
log "upstream ref : ${REF}"

ensure_upstream "${REF}"
apply_overlay

log "injecting iOS project settings (Podfile / Info.plist / pbxproj)"
"${PYTHON_BIN}" "${ADAPTER_ROOT}/scripts/inject_ios.py" --root "${ADAPTER_ROOT}" --ref "${REF}"

log "verifying adaptation"
"${PYTHON_BIN}" "${ADAPTER_ROOT}/scripts/verify_adaptation.py" --root "${ADAPTER_ROOT}"

log "done. Next: bash scripts/build_unsigned_ipa.sh"
