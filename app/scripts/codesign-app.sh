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

# 1.6: Sign Sparkle.framework's nested helpers depth-first.
# Sparkle 2 ships Autoupdate.app, Updater.app, Installer.xpc,
# Downloader.xpc, etc. inside Versions/B/Resources/. Each nested .app/
# .xpc has its own Mach-O at Contents/MacOS/<name> that must be signed
# before its bundle wrapper.
SPARKLE_BUNDLE="$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
if [ -d "$SPARKLE_BUNDLE" ]; then
    echo "==> signing Sparkle.framework nested helpers"
    # find every .app and .xpc bundle nested inside Sparkle.framework
    while IFS= read -r -d '' nested; do
        nested_macos="$nested/Contents/MacOS"
        if [ -d "$nested_macos" ]; then
            for bin in "$nested_macos"/*; do
                [ -f "$bin" ] || continue
                # Magic-byte filter: Mach-O + universal/fat magics.
                if head -c 4 "$bin" | xxd -p | grep -qE '^(cffaedfe|cefaedfe|feedface|feedfacf|cafebabe|cafebabf)' 2>/dev/null; then
                    codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$bin"
                fi
            done
        fi
        # Sign the nested bundle wrapper.
        codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$nested"
    done < <(find "$SPARKLE_BUNDLE" -type d \( -name "*.xpc" -o -name "*.app" \) -print0)

    # Sign any bare Mach-O executables sitting directly in Versions/B/
    # (e.g. Autoupdate, Sparkle itself). These are NOT inside a .app or .xpc
    # bundle so the find-loop above misses them.
    while IFS= read -r -d '' bare_bin; do
        if head -c 4 "$bare_bin" | xxd -p | grep -qE '^(cffaedfe|cefaedfe|feedface|feedfacf|cafebabe|cafebabf)' 2>/dev/null; then
            codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$bare_bin"
        fi
    done < <(find "$SPARKLE_BUNDLE/Versions/B" -maxdepth 1 -type f -perm -u+x -print0)

    # Sign the framework wrapper itself.
    codesign --force --sign "$APPLE_DEV_ID" --options runtime --timestamp "$SPARKLE_BUNDLE"
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
