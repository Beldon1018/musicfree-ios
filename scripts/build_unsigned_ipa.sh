#!/usr/bin/env bash
# Build a genuinely unsigned MusicFree .ipa on a Mac with full Xcode.
#
#   bash scripts/prepare.sh
#   bash scripts/build_unsigned_ipa.sh
#
# In CI, dependencies are installed in a separate step; use --skip-deps there.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

SKIP_DEPS=0
for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=1 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

REF="$(read_ref)"
UP="${UPSTREAM_DIR}"
IOS="${UP}/ios"
ARCHIVE="${BUILD_DIR}/MusicFree.xcarchive"
STAGE="${BUILD_DIR}/ipa"
OUT_IPA="${BUILD_DIR}/MusicFree-${REF}-unsigned.ipa"

command -v node >/dev/null        || die "node not found"
command -v xcodebuild >/dev/null  || die "xcodebuild not found — full Xcode is required (CommandLineTools is not enough)"
command -v pod >/dev/null         || die "CocoaPods (pod) not found"
xcodebuild -version >/dev/null 2>&1 || die "xcodebuild points to CommandLineTools; run: sudo xcode-select -s /Applications/Xcode.app"

[[ -d "${IOS}" ]] || die "upstream/ios missing — run scripts/prepare.sh first"
[[ -f "${UP}/package-lock.json" ]] || die "package-lock.json missing"

if [[ "${SKIP_DEPS}" -eq 0 ]]; then
  log "installing JS dependencies (npm ci)"
  (cd "${UP}" && HUSKY=0 npm ci)
fi

if [[ ! -d "${IOS}/Pods" ]]; then
  log "installing CocoaPods dependencies"
  (cd "${IOS}" && pod install)
else
  log "reusing existing ios/Pods (delete it to force a fresh pod install)"
fi

[[ -d "${IOS}/MusicFree.xcworkspace" ]] || die "MusicFree.xcworkspace not created by pod install"

# The upstream scheme file is named MusicFreeNew.xcscheme even though the target
# is MusicFree. Discover the scheme from the project instead of hard-coding it.
SCHEME="$(xcodebuild -list -project "${IOS}/MusicFree.xcodeproj" -json 2>/dev/null \
  | "${PYTHON_BIN}" -c 'import sys,json; d=json.load(sys.stdin); s=d.get("workspace",{}).get("schemes") or d.get("project",{}).get("schemes") or []; print(s[0] if s else "")')"
if [[ -z "${SCHEME}" ]]; then
  SCHEME="$(basename "$(ls "${IOS}"/MusicFree.xcodeproj/xcshareddata/xcschemes/*.xcscheme | head -1)" .xcscheme)"
fi
log "scheme: ${SCHEME}"

export NODE_BINARY="${NODE_BINARY:-$(command -v node)}"
export EXPO_NO_TELEMETRY=1
export RCT_NO_LAUNCH_PACKAGER=1

rm -rf "${ARCHIVE}" "${STAGE}" "${OUT_IPA}"
mkdir -p "${BUILD_DIR}" "${STAGE}"

log "archiving Release for generic iOS device with code signing disabled"
xcodebuild \
  -workspace "${IOS}/MusicFree.xcworkspace" \
  -scheme "${SCHEME}" \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "${ARCHIVE}" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  DEVELOPMENT_TEAM="" \
  ENABLE_BITCODE=NO \
  clean archive

APP="${ARCHIVE}/Products/Applications/MusicFree.app"
[[ -d "${APP}" ]] || die "archive did not contain MusicFree.app — check the xcodebuild log"

log "packaging unsigned .ipa"
mkdir -p "${STAGE}/Payload"
cp -R "${APP}" "${STAGE}/Payload/"
(cd "${STAGE}" && zip -qry "${OUT_IPA}" Payload)

log "verifying ipa"
"${PYTHON_BIN}" "${ADAPTER_ROOT}/scripts/verify_ipa.py" "${OUT_IPA}"

log "OUTPUT: ${OUT_IPA}"
