# AccountPilot CLI agent contract

Version: 0.2.0

This document describes the AccountPilot CLI's public surface for
agents and automation. Every read command emits the standard JSON
envelope on `--json`. Exit codes are stable. Schemas live in
`tests/integration/jsonschemas/`.

## Stability promise

- **Backwards-compatible additions** (new optional flags, new fields
  on `data` payloads, new `error.code` values) can land in any
  release. Agents that ignore unknown fields stay working.
- **Backwards-incompatible changes** (renamed/removed flags, removed
  `data` fields, changed exit codes) only happen at major version
  bumps and are listed under `### Removed` in the CHANGELOG.

## Exit codes

| Code | Meaning |
|---|---|
| 0   | success |
| 2   | usage error (Click's default for bad flags/args) |
| 13  | permission denied (FDA, OAuth) |
| 64  | config error (malformed YAML, missing required field) |
| 65  | data error (corrupt DB, schema mismatch, missing row, duplicate) |
| 69  | external service unavailable (IMAP server down, OAuth token revoked) |

The mapping from envelope `error.code` strings to exit codes is in
`src/accountpilot/core/cli/exit_codes.py`.

## Envelope

Every `--json` invocation emits a single line of JSON:

```json
{"ok": true,  "data": <command-specific>, "error": null}
{"ok": false, "data": null,                "error": {"code": "STRING", "message": "human-readable"}}
```

`ok` is the boolean truth of the operation. `data` is null on error;
`error` is null on success. Always-present fields keep parsers simple.

## Read commands

### `accountpilot accounts list --json`

**Schema:** `tests/integration/jsonschemas/accounts_list.schema.json`

Returns all accounts in the local DB.

```bash
$ accountpilot accounts list --json
{"ok": true, "data": {"accounts": [{"id": 1, "source": "gmail", …}]}, "error": null}
```

**Errors:** none (always returns ok with possibly empty list).

---

### `accountpilot people list --json`

**Schema:** `tests/integration/jsonschemas/people_list.schema.json`

Returns people sorted by message_count DESC. Optional `--owners` filter.

```bash
$ accountpilot people list --json --owners
{"ok": true, "data": {"people": [{"id": 1, "name": "Ada", "is_owner": true, …}]}, "error": null}
```

---

### `accountpilot people show <id> --json`

**Schema:** `tests/integration/jsonschemas/people_show.schema.json`

Returns a single person with identifiers + message stats.

**Errors:**
- `PERSON_NOT_FOUND` (exit 65) — id doesn't exist

---

### `accountpilot messages list [filters] --json`

**Schema:** `tests/integration/jsonschemas/messages_list.schema.json`

Paginated newest-first message list. Filters: `--account ID`,
`--contact-id ID`, `--since YYYY-MM-DD`, `--limit N` (default 50,
max 500), `--cursor ID` (paginate by id < cursor).

`next_cursor` in the response is `null` when fewer than `limit` rows
returned (= last page).

---

### `accountpilot messages get <id> --json`

**Schema:** `tests/integration/jsonschemas/messages_get.schema.json`

Returns full message body + email/imessage discriminated fields +
people refs + attachment metadata. The email/imessage subtree is
exactly one of `null` (the other is null), keying off `source`.

**Errors:**
- `MESSAGE_NOT_FOUND` (exit 65)

---

### `accountpilot attachments path <id> --json`

**Schema:** `tests/integration/jsonschemas/attachments_path.schema.json`

Resolves an attachment id to its absolute filesystem path. The path
is opaque to the agent — the CLI is the source of truth for CAS
layout.

**Errors:**
- `ATTACHMENT_NOT_FOUND` (exit 65)

`exists: false` in the data payload if the row exists but the CAS
file is missing on disk.

---

### `accountpilot search "<query>" [--limit N] --json`

**Schema:** `tests/integration/jsonschemas/search.schema.json`

FTS5 BM25-ranked search. Lower `score` = more relevant. Default
limit 20.

```bash
$ accountpilot search "fazla" --json
{"ok": true, "data": {"query": "fazla", "results": [{"id": 42, "score": -1.43, …}]}, "error": null}
```

---

### `accountpilot status --json`

**Schema:** `tests/integration/jsonschemas/status.schema.json`

Per-account sync state (last_sync_at, last_error, synced_count) +
generated_at timestamp.

---

### `accountpilot oauth status --json`

**Schema:** `tests/integration/jsonschemas/oauth_status.schema.json`

Lists OAuth secret files present per provider/account.

---

### `accountpilot config import [--config PATH] [--db-path PATH] --json`

**Schema:** `tests/integration/jsonschemas/config_import.schema.json`

One-shot YAML→DB migration. Idempotent (noop on missing or
already-imported YAML). Renames `config.yaml` to
`config.yaml.imported` once applied.

## Write commands

These are agent-callable but their `--json` emits a thinner ack
envelope. Most have `--json` already; some don't (in which case the
exit code + stderr are the contract).

### `accountpilot accounts add --provider X --identifier Y --owner-name Z [--owner-surname S] --json`

Creates an account row + owner (find-or-create by name).

**Errors:**
- `ACCOUNT_EXISTS` (exit 65) — `(provider, identifier)` already in DB

### `accountpilot accounts remove ID --json`

Deletes account + cascades messages + sync_status. No confirmation.

**Errors:**
- `ACCOUNT_NOT_FOUND` (exit 65)

### `accountpilot oauth login {google,microsoft} <id> --json`

Runs the interactive OAuth flow. Blocks until consent (or timeout)
in the user's browser. Persists the refresh token.

**Errors:**
- `OAUTH_FAILED` (exit 69)

### `accountpilot sync-once {mail,imessage} <id> --json`

One-shot sync for one account. Returns `synced_count_delta` +
`duration_seconds`.

**Errors:**
- `SYNC_FAILED` (exit 69)

## Agent recipes

### Smoke test: add a Gmail account, sync, search

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Add the account.
ADD_OUT="$(accountpilot accounts add --provider gmail \
  --identifier ada@example.com --owner-name Ada --owner-surname Lovelace --json)"
ACCOUNT_ID="$(echo "$ADD_OUT" | jq -r '.data.account.id')"

# 2. Run OAuth (opens browser, blocks until user consent).
accountpilot oauth login google "$ACCOUNT_ID" --json > /dev/null

# 3. Sync once.
accountpilot sync-once mail "$ACCOUNT_ID" --json > /dev/null

# 4. Search.
accountpilot search "interview" --limit 3 --json | jq '.data.results[].subject'
```

This recipe is exercised by `tests/integration/agent_smoke.sh`
(Phase 6 verification).

## CLI installation

The bundled CLI lives at:

```
/Applications/AccountPilot.app/Contents/Resources/bin/accountpilot
```

Run `accountpilot self link` (or accept the first-launch prompt) to
create `/usr/local/bin/accountpilot` as a symlink so agents and shell
users can call `accountpilot` directly.

If `/usr/local/bin/` is root-owned (no Homebrew), the symlink fails
with `error.code = "PERMISSION_DENIED"`. Run manually with sudo:

```bash
sudo ln -sf /Applications/AccountPilot.app/Contents/Resources/bin/accountpilot \
  /usr/local/bin/accountpilot
```

## Schema reference

JSON Schemas for every documented command live in
`tests/integration/jsonschemas/`. Each file is a Draft 7 schema
validating the entire envelope (including `{ok, error}` cross-fields
where relevant). The `tests/integration/cli_contract_test.py` test
runs each command against a fixture DB and validates the real output
against its schema.

## Changelog

Breaking changes to this contract land at major version bumps only.
See `CHANGELOG.md` for the full release history.
