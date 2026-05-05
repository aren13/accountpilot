#!/usr/bin/env bash
# Package dist/AccountPilot.app into a notarized + stapled DMG.
#
# Inputs:
#   $APP_BUNDLE   absolute path to AccountPilot.app
#                 (default: $REPO_ROOT/dist/AccountPilot.app)
#   $VERSION      version string for the output filename
#                 (default: read from Info.plist's CFBundleShortVersionString)
#
# Output:
#   dist/AccountPilot-<version>.dmg   (notarized + stapled)
#
# Notarization auth (mirrors scripts/release-helper.sh):
#   Mode A (local): APPLE_NOTARY_PROFILE=accountpilot-notary (default)
#   Mode B (CI):    APPLE_API_KEY_PATH + APPLE_API_KEY_ID + APPLE_API_ISSUER_ID
#                   takes precedence when set.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

APP_BUNDLE="${APP_BUNDLE:-$REPO_ROOT/dist/AccountPilot.app}"
test -d "$APP_BUNDLE" || {
    echo "error: $APP_BUNDLE missing — run app/scripts/build-app.sh first" >&2
    exit 1
}

if [ -z "${VERSION:-}" ]; then
    VERSION="$(plutil -extract CFBundleShortVersionString raw \
        "$APP_BUNDLE/Contents/Info.plist")"
fi
test -n "$VERSION" || {
    echo "error: could not read CFBundleShortVersionString" >&2
    exit 1
}

DMG_PATH="$REPO_ROOT/dist/AccountPilot-$VERSION.dmg"
rm -f "$DMG_PATH"

echo "==> building DMG → $DMG_PATH"
create-dmg \
    --volname "AccountPilot $VERSION" \
    --window-pos 200 120 \
    --window-size 600 360 \
    --icon-size 100 \
    --icon "AccountPilot.app" 150 180 \
    --hide-extension "AccountPilot.app" \
    --app-drop-link 450 180 \
    --no-internet-enable \
    "$DMG_PATH" \
    "$APP_BUNDLE"

echo "==> codesign the DMG"
: "${APPLE_DEV_ID:=Developer ID Application: FAZLA GIDA ANONIM SIRKETI (P2R7PD8VGY)}"
codesign --force --sign "$APPLE_DEV_ID" --timestamp "$DMG_PATH"

echo "==> notarize + staple"
# Auth resolution mirrors scripts/release-helper.sh: API key wins if set.
if [ -n "${APPLE_API_KEY_PATH:-}" ]; then
    if [ -z "${APPLE_API_KEY_ID:-}" ] || [ -z "${APPLE_API_ISSUER_ID:-}" ]; then
        echo "error: APPLE_API_KEY_PATH set but key-id or issuer-id missing" >&2
        exit 64
    fi
    NOTARY_AUTH=(--key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID")
    echo "==> notary auth: App Store Connect API key"
else
    NOTARY_AUTH=(--keychain-profile "${APPLE_NOTARY_PROFILE:-accountpilot-notary}")
    echo "==> notary auth: keychain profile ${APPLE_NOTARY_PROFILE:-accountpilot-notary}"
fi

xcrun notarytool submit "$DMG_PATH" "${NOTARY_AUTH[@]}" --wait
xcrun stapler staple "$DMG_PATH"
xcrun stapler validate "$DMG_PATH"

echo "==> done: $DMG_PATH"
ls -lh "$DMG_PATH"
