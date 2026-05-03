# AccountPilot Roadmap

> Forward-looking plan for AccountPilot. Architecture is in `ARCHITECTURE.md`.
>
> **Last updated:** 2026-05-02

## Overview

AccountPilot is a unified per-machine account sync framework — pulls
email, iMessage, calendar, and other personal data into a local
SQLite database through a plugin architecture.

Phase 1 delivers the core plus mail and iMessage plugins end-to-end,
followed by an open-source release. Subsequent phases add calendar,
Telegram, and WhatsApp.

## Current Status

AP-SP0 (core foundation), AP-SP1 (mail plugin), AP-SP2 (iMessage
plugin), and AP-SP3 (OAuth + multi-account + polish) are complete as
of 2026-05-02. OAuth arrived as `oauth:google:<id>` /
`oauth:microsoft:<id>` URI handlers in `Secrets.resolve()`, an
interactive `accountpilot oauth login` CLI, and XOAUTH2 SASL in the
IMAP client. Both daemons now supervise all enabled accounts of their
source by default with `--account-id N` for single-account override.
SP2 polish: ChatDbWatcher recovers from chat.db inode changes
(post-WAL-checkpoint stalls), attributedBody decoder via pytypedstream
raises iMessage `body_text` coverage from ~30% to ~100%, and
RotatingFileHandler daemon logging finally fills the empty log files.
214 tests pass on main. AP-SP4 (open-source release) is in progress.

## Phase 1 — Core, Mail, iMessage, Open-Source Release

> Goal: a `pip install accountpilot` that anyone can run end-to-end.
>
> Broken into 5 sequential, independently shippable sub-slices.

### AP-SP0 — Foundation (✓ DONE 2026-05-02)

> Goal: Build the core schema, Storage façade, plugin contract, CLI
> scaffolding, identity resolution, and content-addressed store.

### AP-SP1 — Core + mail plugin (✓ DONE 2026-05-02)

> Goal: Build `accountpilot.core` and a real `mail` plugin with IMAP
> IDLE. Prove the contract end-to-end with live email sync.

**Tasks**

- [x] `core/config.py` — XDG paths, plugin enable list, schema validation
- [x] `core/events.py` — async event emitter and typed event models
- [x] `core/storage.py` — sole writer to SQLite + CAS
- [x] `core/auth.py` — `password_cmd` + Keychain shim + OAuth file resolution
- [x] `core/cli.py` — Click root group with per-plugin subcommand registration
- [x] `core/plugin.py` — `AccountPilotPlugin` base class with 5 lifecycle hooks
- [x] Mail plugin: IMAP client, email parser (RFC822 → EmailMessage),
      sync orchestrator, provider detection (Gmail/Outlook)
- [x] `mail.sync_once()` and `mail.daemon()` with real IMAP IDLE

**Acceptance**

- [x] `accountpilot mail backfill` syncs messages via IMAP into Storage
- [x] `accountpilot mail daemon` wraps IMAP IDLE; new mail emits `mail.new`
- [x] Mail plugin fully functional for a single Gmail account

### AP-SP2 — iMessage plugin (✓ DONE 2026-05-02)

> Goal: Add iMessage as a second source. Reads
> `~/Library/Messages/chat.db` directly via watchdog file-watcher.
> Cross-source identity unification with mail correspondents.

**Tasks**

- [x] `pyproject.toml` — register imessage entry point + add watchdog dep
- [x] iMessage config models (`IMessageAccountConfig`, `IMessagePluginConfig`)
- [x] `ChatDbReader` — read-only sqlite3 over chat.db with synthetic test fixture
- [x] `AttachmentReader` + integration into `ChatDbReader`
- [x] `ChatDbWatcher` — watchdog observer with debounce
- [x] `kind_for_imessage_handle` dispatch helper in `core/identity.py`
- [x] `IMessagePlugin` — 5 lifecycle hooks
- [x] `accountpilot imessage {backfill, sync, daemon}` CLI subcommands

**Acceptance**

1. New iMessage arrives → `accountpilot search` returns it within ~5s
2. Cross-source identity: shared phone collapses mail and iMessage
   correspondents into one `people` row
3. Group chat → ≥3 `message_people` rows
4. iMessage attachment → CAS file + sha256 verifies
5. chat.db WAL checkpoint survived; `total == unique_msgids`; no daemon errors

### AP-SP3 — OAuth + multi-account + polish (✓ DONE 2026-05-02)

> Goal: Production-grade auth for daily use. Replace the SP1 stop-gap
> `password_cmd` Gmail flow with proper OAuth (Google + Microsoft),
> supervise N accounts in one daemon process, and resolve the three
> SP2-deferred polish items.

**Tasks**

- [x] OAuth: `oauth:google:<account_id>` URI handler in `Secrets`
- [x] OAuth: `oauth:microsoft:<account_id>` URI handler (msal-backed)
- [x] `accountpilot oauth {login,status,revoke}` CLI — interactive browser flow
- [x] Mail plugin: XOAUTH2 SASL IMAP authentication when credentials_ref starts with `oauth:`
- [x] Multi-account `mail daemon` / `imessage daemon`
- [x] ChatDbWatcher inode-change recovery
- [x] attributedBody typedstream decoder
- [x] `configure_daemon_logging()` with RotatingFileHandler

**Acceptance**

1. Fresh OAuth login for Gmail → backfill works without `password_cmd`
2. Fresh OAuth login for Outlook → same
3. 2+ concurrent IDLE sessions; new mail in either visible in search within seconds
4. `PRAGMA wal_checkpoint(TRUNCATE)` doesn't stall the iMessage daemon
5. After backfill, < 10% of iMessage rows have empty `body_text`

### AP-SP4 — Open-Source Release

> Goal: Make AccountPilot installable and runnable by any user via
> `pip install accountpilot`. Generalize paths (XDG / platformdirs),
> ship a cross-platform `service install/uninstall/status` command
> (launchd + systemd), scrub the docs of private context, set up CI
> on macOS + Linux, publish to PyPI on git tag.

**Tasks** (high-level)

- [x] `core/paths.py` — platformdirs resolver with `ACCOUNTPILOT_*_DIR` env overrides
- [x] Migrate every CLI default path through `core.paths`
- [x] `accountpilot service install/uninstall/status` (macOS launchd + Linux systemd user units)
- [ ] Docs scrub: README rewritten for end users; CONTRIBUTING / SECURITY / CODE_OF_CONDUCT
- [ ] License flip Apache-2.0 → AGPL-3.0-or-later + PyPI metadata polish
- [ ] GitHub Actions CI: macOS + Ubuntu × Python 3.11/3.12
- [ ] PyPI publish workflow on `v*` tags via Trusted Publishing
- [ ] v0.1.0 tag + first PyPI release

**Acceptance**

- `pip install accountpilot` from a fresh macOS or Linux machine;
  `accountpilot setup` then `accountpilot mail backfill 1` works
  end-to-end with no hand-edits to hardcoded paths.
- `accountpilot service install mail` produces a working launchd
  job on macOS and a working systemd user unit on Linux; both
  auto-respawn on SIGTERM and survive reboot.
- CI matrix green on every PR.

## Phase 2 — Calendar Plugin

> Goal: Add calendar plugin for Google + Outlook. Apple Calendar
> deferred to Phase 3.
>
> Why second: Calendar shares OAuth scopes with Gmail/Outlook; one
> consent covers both. Marginal cost given AP-SP3 already implements
> OAuth.

**Tasks**

- [ ] Calendar source type + Storage event model
- [ ] `accountpilot.plugins.calendar`
- [ ] Google Calendar backend (Google Calendar API; reuses Gmail OAuth client)
- [ ] Outlook Calendar backend (Microsoft Graph; reuses Outlook OAuth client)
- [ ] Sync modes: backfill (default 2y past → 2y future), live sync
      (Google push or 5-min poll, Graph change notifications),
      incremental via sync tokens / `deltaLink`
- [ ] Versioning: modified events trigger update flow

**Acceptance**

- Google Calendar event created/modified/deleted on phone → reflected
  in `accountpilot search` within 5 minutes
- Outlook Calendar parity

## Phase 3 — Telegram + Apple Calendar

> Goal: Cover the remaining message and scheduling surfaces.

**Tasks**

- [ ] Apple Calendar via EventKit (PyObjC), CalDAV fallback
- [ ] Telegram plugin: Telethon; per-chat opt-in

**Acceptance**

- Plugin contract validated across event-driven, OAuth-polled, and
  direct-DB plugin shapes

## Phase 4 — WhatsApp + Long-Tail Sources

> Goal: WhatsApp (manual export only in v1) and any sources that
> emerge later.

**Tasks**

- [ ] WhatsApp plugin: `chat.txt` parser + zip handler
- [ ] (Deferred, conditional) WhatsApp live sync if a sustainable
      approach emerges

**Acceptance**

- WhatsApp manual import working end-to-end

## See Also

- `ARCHITECTURE.md` — implementation architecture for this repo
- `CLAUDE.md` — contributor conventions and architecture invariants
