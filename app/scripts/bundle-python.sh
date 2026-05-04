#!/usr/bin/env bash
# Embed a relocatable Python distribution into the .app bundle and install
# the accountpilot package + dependencies into a flat site-packages
# directory inside the bundle.
#
# Inputs (from build-app.sh): $APP_BUNDLE — absolute path to AccountPilot.app
# Output:
#   $APP_BUNDLE/Contents/Resources/python/runtime/       (interpreter + stdlib)
#   $APP_BUNDLE/Contents/Resources/python/site-packages/ (accountpilot + deps)
#
# python-build-standalone is relocatable: its dyld load commands and
# stdlib paths are already rewritten to be bundle-relative.
# https://github.com/astral-sh/python-build-standalone
#
# WHY Resources/ AND NOT Frameworks/:
# We deliberately put the embedded Python under Contents/Resources/, NOT
# Contents/Frameworks/. python-build-standalone's `install_only` layout
# (`bin/`, `lib/`, …) is not an Apple framework structure (which would
# require `Versions/A/...`). When that tree lives under Frameworks/,
# codesign treats every nested file as a signable subcomponent and trips
# on data files (lib/tcl8/8.6, lib/pkgconfig/python-3.13.pc, bin/pip,
# …), rejecting the outer .app with "bundle format unrecognized" or
# "code object is not signed at all". Files under Contents/Resources/
# are recorded in the bundle's CodeResources manifest instead, which is
# what we want for a relocated CPython tree.
#
# WHY NOT venv:
# venv writes the build-time absolute path of the parent interpreter
# into every script's shebang, which breaks when the .app is dragged to
# /Applications/. Using `pip install --target=` produces a flat
# site-packages with no relocation-sensitive scripts.

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

PY_PARENT="$APP_BUNDLE/Contents/Resources/python"
RUNTIME_DIR="$PY_PARENT/runtime"
mkdir -p "$PY_PARENT"
rm -rf "$RUNTIME_DIR" "$APP_BUNDLE/Contents/Frameworks/Python.framework" "$APP_BUNDLE/Contents/Frameworks/python"
tar -xzf "$CACHE_DIR/$TARBALL" -C "$PY_PARENT"
mv "$PY_PARENT/python" "$RUNTIME_DIR"

# Strip components accountpilot (a CLI) doesn't need. Tcl/Tk in particular
# ship versioned data dirs (e.g. lib/tcl8/8.6/) — irrelevant for codesign
# now that we're under Resources/, but still pure bloat. Also strip
# headers, share/, and GUI Python tools.
echo "==> stripping unused Python components (tcl/tk, headers, idle, test)"
rm -rf \
    "$RUNTIME_DIR/lib/tcl8" \
    "$RUNTIME_DIR/lib/tcl8.6" \
    "$RUNTIME_DIR/lib/tk8.6" \
    "$RUNTIME_DIR/lib/itcl4.2.4" \
    "$RUNTIME_DIR/lib/thread2.8.9" \
    "$RUNTIME_DIR/lib/python3.13/tkinter" \
    "$RUNTIME_DIR/lib/python3.13/idlelib" \
    "$RUNTIME_DIR/lib/python3.13/turtledemo" \
    "$RUNTIME_DIR/lib/python3.13/test" \
    "$RUNTIME_DIR/lib/python3.13/config-3.13-darwin" \
    "$RUNTIME_DIR/include" \
    "$RUNTIME_DIR/share" \
    "$RUNTIME_DIR/bin/idle3" \
    "$RUNTIME_DIR/bin/idle3.13" \
    "$RUNTIME_DIR/bin/2to3" \
    "$RUNTIME_DIR/bin/2to3-3.13"

PYTHON_BIN="$RUNTIME_DIR/bin/python3"
test -x "$PYTHON_BIN" || { echo "error: $PYTHON_BIN not executable" >&2; exit 70; }

SITE_PACKAGES="$PY_PARENT/site-packages"
mkdir -p "$SITE_PACKAGES"

echo "==> installing accountpilot + deps into $SITE_PACKAGES via pip --target"
"$PYTHON_BIN" -m pip install --upgrade pip --quiet
"$PYTHON_BIN" -m pip install --quiet --target="$SITE_PACKAGES" "$(pwd)"

# Strip script-style executables left in bin/ by pip + the Python distro.
# These are install-time helpers (pip, pydoc, python-config) — we already
# pip-installed accountpilot above and don't need them at runtime.
echo "==> stripping post-install scripts from runtime/bin/"
rm -f \
    "$RUNTIME_DIR/bin/pip" \
    "$RUNTIME_DIR/bin/pip3" \
    "$RUNTIME_DIR/bin/pip3.13" \
    "$RUNTIME_DIR/bin/pydoc3" \
    "$RUNTIME_DIR/bin/pydoc3.13" \
    "$RUNTIME_DIR/bin/python3-config" \
    "$RUNTIME_DIR/bin/python3.13-config" \
    "$RUNTIME_DIR/bin/wheel" \
    "$RUNTIME_DIR/bin/wheel3" \
    "$RUNTIME_DIR/bin/wheel3.13"

echo "==> verifying embedded accountpilot loads against bundled python"
PYTHONPATH="$SITE_PACKAGES" "$PYTHON_BIN" -c \
    "import accountpilot; print('accountpilot OK from', accountpilot.__file__)"
PYTHONPATH="$SITE_PACKAGES" "$PYTHON_BIN" -m accountpilot.cli --version

echo "==> writing public CLI shim at Contents/Resources/bin/accountpilot"
SHIM_DIR="$APP_BUNDLE/Contents/Resources/bin"
mkdir -p "$SHIM_DIR"
cat > "$SHIM_DIR/accountpilot" <<'SHIM'
#!/bin/bash
# Public CLI entry. Agents install /usr/local/bin/accountpilot as a
# symlink to this file. Resolves the bundle root at runtime so the .app
# is fully relocatable.
set -e
SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "$SHIM_DIR/../../.." && pwd)"
export PYTHONPATH="$BUNDLE_ROOT/Contents/Resources/python/site-packages"
exec "$BUNDLE_ROOT/Contents/Resources/python/runtime/bin/python3" \
    -m accountpilot.cli "$@"
SHIM
chmod +x "$SHIM_DIR/accountpilot"

echo "==> bundle-python: done"
