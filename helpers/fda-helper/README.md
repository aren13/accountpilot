# accountpilot-fda-helper

A Developer-ID-signed Swift helper that mediates Full Disk Access
reads of `~/Library/Messages/chat.db` on behalf of the Python
AccountPilot daemon.

See [PROTOCOL.md](PROTOCOL.md) for the IPC schema. See
[../../docs/imessage-fda.md](../../docs/imessage-fda.md) for the
end-user-facing rationale.

## Build (debug)

```sh
swift build
.build/debug/accountpilot-fda-helper --version
```

## Build (release)

```sh
swift build -c release
.build/release/accountpilot-fda-helper read-imessages --since-ns 0 | head
```

## Sign + notarize for distribution

See `../../scripts/release-helper.sh`.

## Why Swift

- Native macOS API ergonomics + signing/notarization toolchain.
- Tiny binary footprint (no Python or Ruby runtime).
- The hardened runtime + entitlement layout is first-class.
