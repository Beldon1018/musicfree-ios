#!/usr/bin/env bash
# One-time: create a GitHub repo for this adapter, push it, and kick off the
# first macOS build. Requires `gh auth login` (already available on this Mac).
#
#   bash scripts/bootstrap_github.sh [repo-name] [private|public]
#
# Public repos get free macOS runners on GitHub Actions. Private repos consume
# macOS minutes at 10x the normal rate, so prefer public for an OSS adapter.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REPO_NAME="${1:-musicfree-ios}"
VISIBILITY="${2:-private}"

command -v gh >/dev/null || die "gh (GitHub CLI) not found"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated — run: gh auth login"

cd "${ADAPTER_ROOT}"
if [[ ! -d .git ]]; then
  git init -b main
fi
git add -A
git commit -m "feat: MusicFree iOS adapter with unsigned IPA build and upstream sync" || log "nothing new to commit"

log "creating ${VISIBILITY} repository '${REPO_NAME}'"
gh repo create "${REPO_NAME}" --"${VISIBILITY}" --source . --remote origin --push

OWNER="$(gh api user --jq .login)"
log "triggering first build"
gh workflow run build-ios-unsigned.yml --repo "${OWNER}/${REPO_NAME}" --ref main

log "watch it with:"
log "  gh run list --repo ${OWNER}/${REPO_NAME} --workflow build-ios-unsigned.yml"
log "  gh run watch --repo ${OWNER}/${REPO_NAME}"
log "download the result with:"
log "  gh run download --repo ${OWNER}/${REPO_NAME} -n unsigned-ipa"
