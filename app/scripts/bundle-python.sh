#!/usr/bin/env bash
# Embed a relocatable Python.framework into the .app bundle and install
# the accountpilot package + dependencies into a flat site-packages
# directory inside the bundle.
#
# Inputs (from build-app.sh): $APP_BUNDLE — absolute path to AccountPilot.app
# Output:
#   $APP_BUNDLE/Contents/Frameworks/Python.framework/   (interpreter + stdlib)
#   $APP_BUNDLE/Contents/Resources/python/site-packages/ (accountpilot + deps)
#
# python-build-standalone is relocatable: its dyld load commands and
# stdlib paths are already rewritten to be bundle-relative.
# https://github.com/astral-sh/python-build-standalone
#
# We deliberately DO NOT use venv. venv writes the build-time absolute
# path of the parent interpreter into every script's shebang, which
# breaks when the .app is dragged to /Applications/. Using
# `pip install --target=` produces a flat site-packages with no
# relocation-sensitive scripts.

set -euo pipefail

if [[ -z "${APP_BUNDLE:-}" ]]; then
    echo "error: APP_BUNDLE env var required (path to .app)" >&2
    exit 64
fi

PYTHON_VERSION="3.13.1"
PYTHON_BUILD_TAG="20250115"   # bump as upstream releases new builds
ARCH="$(uname -m)"            # arm64 or x86_64

case "$ARCH" in
    arm64)   PBS_ARCH="aarch64-apple-darwin" ;;
    x86_64)  PBS_ARCH="x86_64-apple-darwin" ;;
    *) echo "error: unsupported arch $ARCH" >&2; exit 65 ;;
esac

CACHE_DIR="$(pwd)/.python-cache"
mkdir -p "$CACHE_DIR"
TARBALL="cpython-${PYTHON_VERSION}+${PYTHON_BUILD_TAG}-${PBS_ARCH}-install_only.tar.gz"
TARBALL_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD_TAG}/${TARBALL}"

if [[ ! -f "$CACHE_DIR/$TARBALL" ]]; then
    echo "==> downloading python-build-standalone $PYTHON_VERSION ($PBS_ARCH)"
    curl -fL --output "$CACHE_DIR/$TARBALL" "$TARBALL_URL"
fi

FW_DIR="$APP_BUNDLE/Contents/Frameworks"
mkdir -p "$FW_DIR"
rm -rf "$FW_DIR/Python.framework" "$FW_DIR/python"
tar -xzf "$CACHE_DIR/$TARBALL" -C "$FW_DIR"
mv "$FW_DIR/python" "$FW_DIR/Python.framework"

PYTHON_BIN="$FW_DIR/Python.framework/bin/python3"
test -x "$PYTHON_BIN" || { echo "error: $PYTHON_BIN not executable" >&2; exit 70; }

SITE_PACKAGES="$APP_BUNDLE/Contents/Resources/python/site-packages"
mkdir -p "$SITE_PACKAGES"

echo "==> installing accountpilot + deps into $SITE_PACKAGES via pip --target"
"$PYTHON_BIN" -m pip install --upgrade pip --quiet
"$PYTHON_BIN" -m pip install --quiet --target="$SITE_PACKAGES" "$(pwd)"

echo "==> verifying embedded accountpilot loads against bundled python"
PYTHONPATH="$SITE_PACKAGES" "$PYTHON_BIN" -c \
    "import accountpilot; print('accountpilot OK from', accountpilot.__file__)"
PYTHONPATH="$SITE_PACKAGES" "$PYTHON_BIN" -m accountpilot.cli --version

echo "==> bundle-python: done"
