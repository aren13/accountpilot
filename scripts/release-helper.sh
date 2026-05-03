#!/usr/bin/env bash
# Build, codesign, notarize, and verify the AccountPilot FDA helper.
#
# Output: dist/accountpilot-fda-helper            (signed binary, ready to run)
#         dist/accountpilot-fda-helper-<v>-<arch>.tar.gz  (release artifact)
#         dist/SHA256SUMS                          (sha256 of every dist/ file)
#
# Required env vars:
#   APPLE_DEV_ID         e.g. "Developer ID Application: Hasan Arda Eren (TEAM12345)"
#   APPLE_TEAM_ID        e.g. "TEAM12345"
#   APPLE_NOTARY_PROFILE keychain profile created via:
#                          xcrun notarytool store-credentials \
#                            --apple-id you@example.com \
#                            --team-id TEAM12345 \
#                            --password APP-SPECIFIC-PASSWORD \
#                            <profile-name>
#
# Optional:
#   HELPER_VERSION       overrides version baked into the tarball name.

set -euo pipefail

cd "$(dirname "$0")/../helpers/fda-helper"

# Defaults match the FAZLA GIDA ANONIM SIRKETI Apple Developer org cert.
# Override via env vars if signing under a different identity.
: "${APPLE_DEV_ID:=Developer ID Application: FAZLA GIDA ANONIM SIRKETI (P2R7PD8VGY)}"
: "${APPLE_TEAM_ID:=P2R7PD8VGY}"
: "${APPLE_NOTARY_PROFILE:=accountpilot-notary}"

ARCH="$(uname -m)"   # arm64 or x86_64
VERSION="${HELPER_VERSION:-$(grep -m1 'HELPER_VERSION' Sources/AccountpilotFDAHelper/main.swift | sed -E 's/.*"([^"]+)".*/\1/')}"
DIST="$(pwd)/../../dist"
mkdir -p "$DIST"

echo "==> swift build -c release"
swift build -c release

# SwiftPM puts the binary in a different path on universal vs single-arch builds.
BUILT="$(swift build -c release --show-bin-path)/accountpilot-fda-helper"
if [[ ! -x "$BUILT" ]]; then
    echo "error: build did not produce $BUILT" >&2
    exit 65
fi

OUT="$DIST/accountpilot-fda-helper"
cp -f "$BUILT" "$OUT"

echo "==> codesign --options runtime --timestamp"
codesign --force \
    --sign "$APPLE_DEV_ID" \
    --options runtime \
    --entitlements helper.entitlements \
    --identifier "com.accountpilot.fda-helper" \
    --timestamp \
    "$OUT"

echo "==> codesign --verify"
codesign --verify --verbose=2 "$OUT"

ZIP="$DIST/accountpilot-fda-helper-${VERSION}-${ARCH}.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$OUT" "$ZIP"

echo "==> notarytool submit --wait"
xcrun notarytool submit "$ZIP" \
    --keychain-profile "$APPLE_NOTARY_PROFILE" \
    --wait

echo "==> spctl --assess (Gatekeeper acceptance, advisory)"
# spctl --type execute only validates .app bundles. For a bare CLI
# binary, verifying codesign + a successful notarytool submission is
# sufficient — Gatekeeper does an online ticket lookup on first run.
# We still try the open/install context as a sanity check but treat
# any failure as advisory (notarized CLI binaries cannot be stapled).
spctl --assess --type install --verbose=2 "$OUT" || \
    echo "    (spctl rejection is expected for unstapled CLI binaries; ignoring)"

# Repackage as tar.gz for the GitHub release (brew Resource expects tar.gz).
TARBALL="$DIST/accountpilot-fda-helper-${VERSION}-${ARCH}.tar.gz"
rm -f "$TARBALL"
tar -czf "$TARBALL" -C "$DIST" "$(basename "$OUT")"

(
    cd "$DIST"
    shasum -a 256 \
        "$(basename "$OUT")" \
        "$(basename "$ZIP")" \
        "$(basename "$TARBALL")" \
        > SHA256SUMS
)

echo "==> done"
echo "    binary: $OUT"
echo "    zip:    $ZIP"
echo "    tar.gz: $TARBALL"
echo "    sha256: $DIST/SHA256SUMS"
