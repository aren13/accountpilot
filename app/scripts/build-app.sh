#!/usr/bin/env bash
# Orchestrator: build Swift .app, embed Python, copy helper, codesign,
# notarize, staple. Output: dist/AccountPilot.app
#
# Pre-reqs:
#   - helpers/fda-helper/release-helper.sh has been run (dist/accountpilot-fda-helper exists)
#   - notarization keychain profile 'accountpilot-notary' exists

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

DIST="$REPO_ROOT/dist"
APP_BUNDLE="$DIST/AccountPilot.app"
mkdir -p "$DIST"
rm -rf "$APP_BUNDLE"

echo "==> [1/5] xcodebuild AccountPilot.app shell"
cd app && xcodegen generate && cd ..
xcodebuild -project app/AccountPilot.xcodeproj \
    -scheme AccountPilot \
    -configuration Release \
    -derivedDataPath app/build/ \
    CODE_SIGNING_ALLOWED=NO \
    -skipMacroValidation \
    build
BUILT_APP=$(find app/build/Build/Products/Release -name "AccountPilot.app" -maxdepth 2 -type d | head -1)
test -d "$BUILT_APP" || { echo "error: xcodebuild did not produce AccountPilot.app"; exit 70; }
cp -R "$BUILT_APP" "$APP_BUNDLE"

echo "==> [2/5] embed Python runtime + accountpilot package"
APP_BUNDLE="$APP_BUNDLE" "$REPO_ROOT/app/scripts/bundle-python.sh"

echo "==> [3/5] copy FDA helper into Contents/Helpers/"
APP_BUNDLE="$APP_BUNDLE" "$REPO_ROOT/app/scripts/bundle-helper.sh"

echo "==> [4/5] codesign (depth-first)"
APP_BUNDLE="$APP_BUNDLE" "$REPO_ROOT/app/scripts/codesign-app.sh"

echo "==> [5/5] notarize + staple"
ZIP="$DIST/AccountPilot-staging.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile accountpilot-notary --wait
xcrun stapler staple "$APP_BUNDLE"
xcrun stapler validate "$APP_BUNDLE"
rm -f "$ZIP"

echo "==> done"
echo "    .app: $APP_BUNDLE"
"$REPO_ROOT/app/scripts/verify-app.sh"
