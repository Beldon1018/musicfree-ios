#!/usr/bin/env bash
# Shared helpers for the MusicFree iOS adapter.
set -euo pipefail

ADAPTER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="${ADAPTER_ROOT}/upstream"
BUILD_DIR="${ADAPTER_ROOT}/build"
UPSTREAM_REPO="${MUSICFREE_UPSTREAM_REPO:-https://github.com/maotoumao/MusicFree.git}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log()  { printf '[musicfree-ios] %s\n' "$*"; }
warn() { printf '[musicfree-ios] WARNING: %s\n' "$*" >&2; }
die()  { printf '[musicfree-ios] ERROR: %s\n' "$*" >&2; exit 1; }

read_ref() {
  tr -d '[:space:]' < "${ADAPTER_ROOT}/UPSTREAM_REF"
}

ensure_upstream() {
  local ref="$1"
  if [[ ! -d "${UPSTREAM_DIR}/.git" ]]; then
    log "cloning upstream into upstream/ (${UPSTREAM_REPO})"
    git clone --filter=blob:none "${UPSTREAM_REPO}" "${UPSTREAM_DIR}"
  fi

  log "fetching upstream tags"
  git -C "${UPSTREAM_DIR}" fetch --tags --force --prune origin

  if ! git -C "${UPSTREAM_DIR}" rev-parse -q --verify "refs/tags/${ref}^{commit}" >/dev/null; then
    die "tag '${ref}' does not exist upstream. Check UPSTREAM_REF or run scripts/sync_upstream.py --apply"
  fi

  log "resetting upstream to ${ref}"
  git -C "${UPSTREAM_DIR}" reset --hard "${ref}" >/dev/null
  # Removes files injected by a previous prepare run. Ignored directories
  # (node_modules/, ios/Pods/) are kept so rebuilds stay fast.
  git -C "${UPSTREAM_DIR}" clean -fd >/dev/null
}

apply_overlay() {
  log "copying overlay/ into upstream/"
  cp -R "${ADAPTER_ROOT}/overlay/." "${UPSTREAM_DIR}/"
}
