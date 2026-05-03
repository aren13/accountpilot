# accountpilot-fda-helper IPC protocol

> **Version:** v1
> **Stability:** experimental — Phase 1.
>
> The Python side and the Swift helper share this contract. Breaking
> changes bump the major version and require a coordinated upgrade of
> both sides.

## Why this exists

macOS gates `~/Library/Messages/chat.db` behind Full Disk Access. The
grant is keyed by binary cdhash + path. The Python interpreter that
ships through Homebrew/pip changes hash on every patch upgrade, so a
grant given to `/opt/homebrew/bin/python3.13` evaporates the next time
brew bumps Python.

The Swift helper is a small, signed, notarized binary owned by
AccountPilot's developer team. Its cdhash is stable across Python and
AccountPilot upgrades, so the FDA grant survives. Python shells out to
the helper for every chat.db read.

## Process model

- One short-lived helper process per read pass — Python spawns it via
  `subprocess.Popen`, consumes stdout to EOF, awaits exit code.
- Helper exits 0 on success, even with zero rows.
- Helper holds no state between invocations.

## CLI surface

```
accountpilot-fda-helper --version
accountpilot-fda-helper read-imessages [--since-ns <int>] [--db <path>]
```

`--version` writes `accountpilot-fda-helper <semver>\n` to stdout and
exits 0.

`read-imessages` opens chat.db read-only and emits one JSON object per
line on stdout, terminated by `\n`. With no `--since-ns`, every message
is emitted. With `--since-ns N`, only messages whose `date_ns > N` are
emitted. `--db` defaults to `~/Library/Messages/chat.db`; tests use
`--db` to point at a synthetic fixture.

## Output: stdout JSON Lines

Each line is a complete JSON object. No trailing comma, no leading
array bracket, no pretty-printing. Lines are emitted in
`(date_ns ASC, msg_rowid ASC)` order.

### Schema v1 — message record

```json
{
  "v": 1,
  "type": "message",
  "guid": "BCD-...-EF",
  "text": "hi from melis",
  "attributed_body_b64": null,
  "is_from_me": false,
  "is_read": true,
  "date_ns": 770478000000000000,
  "date_read_ns": 770478001000000000,
  "service": "iMessage",
  "sender_handle": "+905052490140",
  "chat_guid": "iMessage;-;+905052490140",
  "participants": ["+905052490140"],
  "attachments": [
    {
      "filename": "IMG_1234.jpg",
      "mime_type": "image/jpeg",
      "content_b64": "..."
    }
  ]
}
```

Field rules:

- `v` (int, required) — schema version. Always `1` for protocol v1.
  Python rejects records with `v != 1`.
- `type` (string, required) — `"message"`. Reserved for future record
  types (presence-pings, errors-as-records, …).
- `guid` (string, required) — Apple's per-message GUID (chat.db
  `message.guid`). Stable across syncs; serves as the cross-process
  external_id.
- `text` (string | null) — plain text body. `null` when Apple stores
  the body in `attributedBody` only.
- `attributed_body_b64` (string | null) — base64-encoded raw NSKeyed-
  Archived `message.attributedBody` blob. Python decodes via
  `pytypedstream` to recover the body when `text` is null. The helper
  does NOT decode this — it forwards the raw bytes so existing Python
  decode paths keep working.
- `is_from_me` (bool, required).
- `is_read` (bool, required) — defaults to `false` if Apple stores
  `NULL` (covers ancient rows).
- `date_ns` (int, required) — Apple-Cocoa nanoseconds since 2001-01-01
  UTC. Same units as `chat.db message.date`.
- `date_read_ns` (int | null) — same units, null when unread.
- `service` (string, required) — raw `chat.db message.service`. Python
  normalises to the `IMessageService` Literal (`iMessage` | `SMS`).
- `sender_handle` (string, required) — `handle.id`. Helper SQL filters
  rows with `NULL` handles so this is always set.
- `chat_guid` (string, required) — `chat.guid`.
- `participants` (list[string], required) — every `handle.id` joined
  to this chat via `chat_handle_join`. May contain a single member for
  1:1 chats.
- `attachments` (list[object], required) — possibly empty.
  - `filename` (string, required) — preferred display name. Falls back
    in helper to `transfer_name`, then the basename of the raw path,
    then `attachment.bin`. Python does not need to apply further
    fallbacks.
  - `mime_type` (string | null).
  - `content_b64` (string, required) — base64 of the file bytes.
    Attachments whose backing file is missing on disk are dropped by
    the helper (logged to stderr at debug, not a fatal error).

Records that the helper would have skipped today (system messages with
`NULL` handle) are not emitted, matching reader.py's existing SQL.

## Output: stderr

Stderr is **only** for human-readable log lines and for the structured
error envelope below. It is never machine-parsed line-by-line by
Python; Python only reads stderr when exit code is non-zero.

### Error envelope (on non-zero exit)

The helper writes a single JSON object to stderr on its way out:

```json
{
  "v": 1,
  "type": "error",
  "code": "EACCES",
  "message": "Full Disk Access not granted to accountpilot-fda-helper. ...",
  "path": "/Users/ae/Library/Messages/chat.db"
}
```

`code` is one of:

| Code         | Exit | Meaning                                          |
|--------------|------|--------------------------------------------------|
| `EACCES`     | 13   | OS denied the read. Almost always missing FDA.   |
| `ENOENT`     | 2    | chat.db does not exist (rare — pre-iMessage Mac).|
| `EUSAGE`     | 64   | Bad CLI args.                                    |
| `EDATA`      | 65   | Unexpected schema in chat.db (Apple bumped it).  |
| `EUNKNOWN`   | 1    | Catch-all.                                       |

Python reads the envelope, raises a typed exception (`HelperPermission
Error` for `EACCES`, etc.), and surfaces `message` to the user.

## Stability guarantees

- The schema is **append-only** within a major version. Adding fields
  to `message` is non-breaking; Python ignores unknown keys. Removing
  or renaming a field bumps the major version.
- Exit codes and error envelope shape are fixed for v1.
- The CLI surface (`--version`, `read-imessages [--since-ns] [--db]`)
  is fixed for v1. New subcommands may be added.

## Out of scope for v1

- ~/Library/Mail/ reads (a future Apple-Mail.app plugin will add a
  `read-mailbox` subcommand under protocol v2 or as a v1 addition).
- Calendar / Contacts / Photos.
- Streaming / long-running mode. Each invocation is one-shot. The
  Python daemon's polling loop calls the helper repeatedly with an
  advancing `--since-ns`.
