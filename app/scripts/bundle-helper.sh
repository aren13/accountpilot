#!/usr/bin/env bash
# Copy the signed FDA helper into the .app bundle's Contents/Helpers/.
#
# Inputs:
#   $APP_BUNDLE — absolute path to AccountPilot.app
#   Optionally: $HELPER_BIN — explicit path to helper binary (defaults
#               to repo's dist/accountpilot-fda-helper from release-helper.sh)
#
# Output: $APP_BUNDLE/Contents/Helpers/accountpilot-fda-helper

set -euo pipefail

if [[ -z "${APP_BUNDLE:-}" ]]; then
    echo "error: APP_BUNDLE env var required" >&2
    exit 64
fi

HELPER_BIN="${HELPER_BIN:-$(pwd)/dist/accountpilot-fda-helper}"
if [[ ! -x "$HELPER_BIN" ]]; then
    echo "error: helper binary not at $HELPER_BIN" >&2
    echo "       run scripts/release-helper.sh first to build + sign + notarize the helper" >&2
    exit 66
fi

HELPERS_DIR="$APP_BUNDLE/Contents/Helpers"
mkdir -p "$HELPERS_DIR"
cp -f "$HELPER_BIN" "$HELPERS_DIR/accountpilot-fda-helper"
chmod +x "$HELPERS_DIR/accountpilot-fda-helper"

echo "==> bundle-helper: copied $HELPER_BIN -> $HELPERS_DIR/"

# Sanity-check the helper's identity hasn't drifted
codesign -dv "$HELPERS_DIR/accountpilot-fda-helper" 2>&1 | grep -E "Identifier|TeamIdentifier"
