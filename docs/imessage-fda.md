# iMessage and Full Disk Access (FDA)

The iMessage plugin reads `~/Library/Messages/chat.db`, which macOS
gates behind Full Disk Access. This page explains how AccountPilot
makes that grant survive `brew upgrade`.

## TL;DR

1. `brew install aren13/tap/accountpilot` installs both the Python
   package and a Developer-ID-signed Swift helper at
   `$(brew --prefix)/bin/accountpilot-fda-helper`.
2. Run `accountpilot setup`. If iMessage is enabled in your config and
   FDA hasn't been granted, AccountPilot opens System Settings →
   Privacy & Security → Full Disk Access and prints the path to add.
3. Add the helper to the FDA list. Done — that's the only manual step.

The grant survives because TCC keys it on the helper's code signature,
not the calling Python interpreter.

## Why a separate helper

macOS keys FDA grants by code-directory hash + path. Every
`brew upgrade python@3.13` rehashes the Python interpreter, which
invalidates a grant given to `python3.13`. Anaconda, pip, and pipx
have the same problem.

The helper binary is signed by a stable Developer ID, lives at a
stable path (`$(brew --prefix)/bin/accountpilot-fda-helper`), and
ships through GitHub Releases as a notarized Mach-O. Its cdhash does
not change when Python or AccountPilot upgrades. Once granted, the
grant stays granted.

The helper is intentionally minimal: it reads chat.db, base64-encodes
attachment bytes, and emits JSON Lines on stdout. No network, no
disk writes, no business logic. See
[`helpers/fda-helper/PROTOCOL.md`](../helpers/fda-helper/PROTOCOL.md)
for the full IPC contract.

## Granting FDA

`accountpilot setup` deep-links into the right preferences pane. To do
it manually:

1. **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **+** button.
3. Press `⌘ Shift G` and paste:
   ```
   /opt/homebrew/bin/accountpilot-fda-helper
   ```
   (or `/usr/local/bin/...` on Intel Macs)
4. Click **Open**, then toggle the entry on.

You'll be prompted for your password. macOS may ask for confirmation
again the first time the helper runs.

## Verifying the grant

```sh
accountpilot setup
# ...
# ✓ FDA helper reachable, chat.db readable.
```

Or directly:

```sh
accountpilot-fda-helper read-imessages --since-ns 0 | head -1
```

If this prints a JSON line, the grant is in effect. If it prints an
error envelope with `"code": "EACCES"` and exits 13, FDA is missing
or was revoked.

## Revoking the grant

Remove the helper entry from the same Privacy & Security pane.
AccountPilot will refuse to sync iMessage on the next pass and
reprompt via `accountpilot setup`.

## Why not bundle our own Python

We considered shipping a py2app/PyInstaller bundle so the entire
AccountPilot package would have a stable cdhash. We rejected it
because:

- Bundled Python distros are an order of magnitude larger and slower
  to ship.
- They lock users out of `pip install <plugin>` extensibility.
- The signing surface area (every imported native module) becomes a
  notarization treadmill.

A 1MB Swift helper that handles only the FDA-gated reads is dramatically
simpler.
