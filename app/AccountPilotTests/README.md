# AccountPilot Tests — Phase 1 Limitation

`PythonRuntime` resolves the bundled Python via `Bundle.main`. In
`xcodebuild test`, `Bundle.main` is the test bundle's host
(`build/Build/Products/Debug/AccountPilot.app`) — a bare
`xcodebuild` output that does **not** have the embedded Python
runtime (that's added later by `bundle-python.sh` against the
final `dist/AccountPilot.app`).

Tests that exercise the real Python invocation therefore fail in
`xcodebuild test` until Phase 2 introduces an injectable bundle
root (e.g. `PythonRuntime.bundleURL`). For Phase 1, the canonical
test gate is the post-build smoke check:

```sh
./app/scripts/build-app.sh   # produces dist/AccountPilot.app
./app/scripts/verify-app.sh  # ✓ exits zero on a fully-built bundle
```

`verify-app.sh` exercises the bundled CLI (which IS the same code
the Swift app calls into) and is what CI gates on.
