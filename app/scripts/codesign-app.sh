#!/usr/bin/env bash
# Codesign every Mach-O inside the .app bundle, depth-first, then the
# outer bundle. The embedded Python tree lives under
# Contents/Resources/python/runtime/ — codesign treats Resources/ as
# data, but we still sign the actual Mach-O binaries (interpreter +
# .dylib/.so) for hardened-runtime compliance.

set -euo pipefail

if [[ -z "${APP_BUNDLE:-}" ]]; then
    echo "error: APP_BUNDLE env var required" >&2
    exit 64
fi
: "${APPLE_DEV_ID:=Developer ID Application: FAZLA GIDA ANONIM SIRKETI (P2R7PD8VGY)}"

ENT="$(pwd)/app/AccountPilot/AccountPilot.entitlements"
HELPER_ENT="$(pwd)/helpers/fda-helper/helper.entitlements"

# 1. Sign every Mach-O inside Resources/python/ — both runtime/ (interpreter
# + stdlib .so) AND site-packages/ (PyPI C extensions like pydantic_core,
# cryptography, watchdog). Notarization REQUIRES every Mach-O in the
# bundle to be signed with our Developer ID + secure timestamp; PyPI .so
# files come pre-signed by their publishers (or unsigned), so we must
# re-sign them.
echo "==> signing embedded Python Mach-Os (runtime + site-packages)"
find "$APP_BUNDLE/Contents/Resources/python" \
     -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) \
     -print0 | while IFS= read -r -d '' mach; do
    # filter to Mach-O via magic bytes (skip .py, .pyc, hash files, etc.).
    # Magics: feedface/feedfacf = 32/64-bit Mach-O,
    #         cefaedfe/cffaedfe = 32/64-bit byte-swapped,
    #         cafebabe/cafebabf = universal (fat) binaries — common for PyPI
    #         wheels (cryptography, mypyc, charset_normalizer ship fat .so).
    head -c 4 "$mach" | xxd -p | grep -qE '^(cffaedfe|cefaedfe|feedface|feedfacf|cafebabe|cafebabf)' || continue
    codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$mach"
done

# 1.5: Sign the XPC service bundle (Mach-O inside, then outer .xpc)
XPC_BUNDLE="$APP_BUNDLE/Contents/PlugIns/AccountPilotXPC.xpc"
if [ -d "$XPC_BUNDLE" ]; then
    echo "==> signing XPC service Mach-O"
    XPC_BIN="$XPC_BUNDLE/Contents/MacOS/AccountPilotXPC"
    if [ -f "$XPC_BIN" ]; then
        codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$XPC_BIN"
    else
        echo "warning: $XPC_BIN missing, skipping XPC binary signing" >&2
    fi
    echo "==> signing XPC service bundle"
    XPC_ENT="$(pwd)/app/AccountPilotXPC/SyncServiceXPC.entitlements"
    if [ ! -f "$XPC_ENT" ]; then
        echo "error: XPC entitlements not found at $XPC_ENT — run 'cd app && xcodegen generate' first" >&2
        exit 1
    fi
    codesign --force --sign "$APPLE_DEV_ID" \
        --options runtime \
        --entitlements "$XPC_ENT" \
        --identifier "com.accountpilot.SyncService" \
        --timestamp \
        "$XPC_BUNDLE"
fi

# 2. Sign the helper with its own entitlements
echo "==> signing FDA helper"
codesign --force --sign "$APPLE_DEV_ID" \
    --options runtime \
    --entitlements "$HELPER_ENT" \
    --identifier "com.accountpilot.fda-helper" \
    --timestamp \
    "$APP_BUNDLE/Contents/Helpers/accountpilot-fda-helper"

# 3. Sign the outer bundle with the app's entitlements
echo "==> signing AccountPilot.app"
codesign --force --sign "$APPLE_DEV_ID" \
    --options runtime \
    --entitlements "$ENT" \
    --identifier "com.accountpilot.app" \
    --timestamp \
    "$APP_BUNDLE"

# 4. Verify
echo "==> verifying signature"
codesign --verify --verbose=2 "$APP_BUNDLE"
codesign --verify --verbose=2 "$APP_BUNDLE/Contents/Helpers/accountpilot-fda-helper"

echo "==> codesign: done"
