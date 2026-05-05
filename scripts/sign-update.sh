#!/usr/bin/env bash
# Generate the Sparkle EdDSA signature for a DMG.
#
# Inputs:
#   $1                     path to the DMG file
#   $SPARKLE_PRIVATE_KEY   (optional) base64 private key — if set, the
#                          tool reads from this env-var content rather
#                          than the macOS Keychain.
#
# Output (to stdout): the line emitted by sign_update, looks like:
#   sparkle:edSignature="..." length="..."
#
# CI consumes this and embeds it into the new appcast <item>.
# Local invocation (without env) reads the private key from the user's
# Keychain (stored there by Sparkle's generate_keys tool).

set -euo pipefail

DMG="${1:?usage: sign-update.sh <dmg-path>}"
test -f "$DMG" || {
    echo "error: $DMG not found" >&2
    exit 1
}

# Resolve the directory of this script so relative find paths work
# regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Try to locate sign_update — search SwiftPM cache locations in priority order.
SIGN_UPDATE=""
for candidate in \
    "$(find ~/Library/Developer/Xcode/DerivedData -name "sign_update" -not -path "*/old_dsa_scripts/*" -type f 2>/dev/null | head -1)" \
    "$(find "$SCRIPT_DIR/../app/build/SourcePackages/artifacts" -name "sign_update" -not -path "*/old_dsa_scripts/*" -type f 2>/dev/null | head -1)" \
    "$(find "$SCRIPT_DIR/../app/build/SourcePackages/checkouts" -name "sign_update" -not -path "*/old_dsa_scripts/*" -type f 2>/dev/null | head -1)" \
    "/tmp/sign_update"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        SIGN_UPDATE="$candidate"
        break
    fi
done

if [ -z "$SIGN_UPDATE" ]; then
    echo "error: sign_update not found — Sparkle's tools must be available." >&2
    echo "       Build the .app at least once (xcodebuild) so SwiftPM caches" >&2
    echo "       Sparkle's checkout, OR download Sparkle's release tarball" >&2
    echo "       and place sign_update at /tmp/sign_update." >&2
    exit 1
fi

echo "==> using $SIGN_UPDATE" >&2

# CI path: SPARKLE_PRIVATE_KEY env holds the base64 private key string.
# Write to a temp file with mode 600, pass via -f, ensure trap cleans up.
if [ -n "${SPARKLE_PRIVATE_KEY:-}" ]; then
    KEY_FILE="$(mktemp)"
    chmod 600 "$KEY_FILE"
    # shellcheck disable=SC2064
    trap "rm -f '$KEY_FILE'" EXIT
    printf '%s' "$SPARKLE_PRIVATE_KEY" > "$KEY_FILE"
    "$SIGN_UPDATE" -f "$KEY_FILE" "$DMG"
else
    # Local dev: sign_update reads the key from the user's Keychain
    # (where generate_keys put it under https://sparkle-project.org).
    "$SIGN_UPDATE" "$DMG"
fi
