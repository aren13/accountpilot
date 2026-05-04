#!/usr/bin/env bash
# Post-build verification of dist/AccountPilot.app. Run automatically by
# build-app.sh; can be re-run independently. Exits non-zero on any
# missing or mis-signed component.

set -euo pipefail

APP_BUNDLE="${APP_BUNDLE:-$(pwd)/dist/AccountPilot.app}"
test -d "$APP_BUNDLE" || { echo "error: $APP_BUNDLE missing"; exit 1; }

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "  ✓ $*"; }

echo "==> verify $APP_BUNDLE"

# 1. Bundle structure
for path in \
    "Contents/MacOS/AccountPilot" \
    "Contents/Resources/python/runtime/bin/python3" \
    "Contents/Resources/python/site-packages/accountpilot/__init__.py" \
    "Contents/Resources/python/site-packages/accountpilot/cli.py" \
    "Contents/Resources/bin/accountpilot" \
    "Contents/Helpers/accountpilot-fda-helper" \
    "Contents/Info.plist"; do
    test -e "$APP_BUNDLE/$path" || fail "missing $path"
    pass "exists $path"
done

# 2. Codesign of outer bundle
# Buffer output before grep: with `set -o pipefail`, `grep -q` closes the
# pipe on first match and codesign exits on SIGPIPE (non-zero), tripping
# pipefail and failing the check despite the signature being valid.
codesign_outer="$(codesign --verify --verbose=2 "$APP_BUNDLE" 2>&1)"
echo "$codesign_outer" | grep -q "valid on disk" \
    || fail "outer bundle codesign invalid"
pass "outer bundle signature valid"

# 3. Helper signing identity unchanged
helper_codesign="$(codesign -dv "$APP_BUNDLE/Contents/Helpers/accountpilot-fda-helper" 2>&1)"
echo "$helper_codesign" | grep -q "TeamIdentifier=P2R7PD8VGY" \
    || fail "helper missing P2R7PD8VGY team"
echo "$helper_codesign" | grep -q "Identifier=com.accountpilot.fda-helper" \
    || fail "helper bundle id wrong"
pass "helper signing identity correct"

# 4. App bundle id
app_codesign="$(codesign -dv "$APP_BUNDLE" 2>&1)"
echo "$app_codesign" | grep -q "Identifier=com.accountpilot.app" \
    || fail "app bundle id should be com.accountpilot.app"
pass "app bundle id correct"

# 5. Notarization staple
xcrun stapler validate "$APP_BUNDLE" >/dev/null 2>&1 \
    || fail "notarization staple invalid"
pass "notarization stapled"

# 6. Public CLI works
cli_version="$("$APP_BUNDLE/Contents/Resources/bin/accountpilot" --version)"
echo "$cli_version" | grep -q "0.2.0" \
    || fail "bundled CLI does not report 0.2.0 (got: $cli_version)"
pass "CLI reports correct version"

# 7. FDA helper runs (returns EACCES without grant — that's expected)
helper_version="$("$APP_BUNDLE/Contents/Helpers/accountpilot-fda-helper" --version)"
echo "$helper_version" | grep -q "0.1.1" \
    || fail "FDA helper does not report 0.1.1 (got: $helper_version)"
pass "FDA helper runs and reports 0.1.1"

echo "==> all verification passed"
