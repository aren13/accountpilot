# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — IN PROGRESS (AP-SP5)

### Added
- **macOS .app distribution.** AccountPilot now ships as a drag-to-Applications
  `.app` bundle with embedded Python.framework. End users no longer need brew or
  pip. Phase 1 ships the skeleton: a notarized .app that opens and runs the
  bundled CLI. Subsequent phases add account UI, FDA wizard, sync status,
  data viewer, and Sparkle auto-update.
- **Account management UI.** SwiftUI accounts list view replaces
  `config.yaml` as the source of truth. Add Gmail/Outlook accounts
  via in-app OAuth flow against bundled publisher credentials —
  no terminal interaction, no YAML editing. Remove deletes the
  account row, all its messages, and the OAuth secret file.
- **First-launch config.yaml migration.** Existing 0.1.x installs
  with `~/Library/Application Support/accountpilot/config.yaml`
  see all accounts auto-imported on first launch. The YAML is
  renamed to `config.yaml.imported` once applied so the migration
  is one-shot.
- **CLI: `accountpilot accounts add --json`,
  `accountpilot accounts remove ID --json`,
  `accountpilot config import --json`,
  `accountpilot oauth login {google,microsoft} --json`.** All emit
  a stable `{"ok": bool, "data": ..., "error": ...}` envelope so
  downstream agents (and the SwiftUI app) get a single contract
  for both happy and error paths.
- **FDA wizard.** First launch on a Mac without Full Disk Access for
  the helper now opens a guided wizard that deep-links into System
  Settings → Privacy & Security → Full Disk Access and auto-advances
  within ~1 second of the grant taking effect. "Skip for now" path
  lets the user proceed with mail-only sync.
- **Status-bar app + XPC sync.** AccountPilot is now a menu-bar app
  (LSUIElement). An embedded XPC service `com.accountpilot.SyncService`
  runs one timer per enabled account, calling
  `accountpilot sync-once {mail,imessage} <id> --json`. Status bar
  shows last-sync per account and offers Sync Now / Pause Sync /
  Open AccountPilot…. Settings sheet has a master "Background sync
  enabled" toggle that actually starts/stops the XPC service.
- **CLI: `accountpilot status --json`,
  `accountpilot sync-once {mail,imessage} <id> --json`,
  `accountpilot imessage probe-fda --json`.** Plugins'
  `sync_once` now returns the count of new messages written.
- **Data viewer.** New SwiftUI three-pane browse experience: sidebar
  with accounts + people, message list with FTS5-ranked
  `.searchable()` query bar, message detail with attachment thumbnails
  and one-click "Open" via NSWorkspace. Replaces the Phase 2/3
  bare-AccountsView main window; AccountsView is now reachable via
  the sidebar's "Manage Accounts…" row.
- **CLI: `accountpilot messages list [--account ID] [--contact-id ID] [--since YYYY-MM-DD] [--limit N] [--cursor ID] --json`,
  `accountpilot messages get <id> --json`,
  `accountpilot attachments path <id> --json`,
  `accountpilot search "query" --json`,
  `accountpilot people list --json`.** All return the standard JSON
  envelope. `messages list` paginates by `id` cursor. `search`
  returns FTS5 BM25-ranked results.
- **Sparkle auto-update + DMG distribution.** Tagged `v*` releases
  produce a notarized DMG attached to the GitHub Release plus an
  appcast entry on the `gh-pages` branch. The .app's main menu has
  a "Check for Updates…" item. EdDSA-signed updates verify
  authenticity. Bundle ID + TeamID stay constant across updates so
  the FDA grant survives.
- **`app/scripts/build-dmg.sh`** wraps `create-dmg` to package the
  signed .app into a notarized + stapled DMG.
  **`scripts/sign-update.sh`** generates Sparkle's EdDSA signature
  for the appcast entry. **`scripts/append-appcast-entry.sh`** is
  an idempotent appcast XML editor.
- **`.github/workflows/release-app.yml`** orchestrates the full
  flow on `macos-latest`: import cert → build .app → build DMG →
  sign update → attach to GitHub Release → append appcast → push
  to `gh-pages`. See `docs/release.md` for one-time setup.
- **Agent-friendly CLI hardening.** `--json` on every read command:
  `people show` and `oauth status` (the two that lacked it). Stable
  exit codes (0/2/13/64/65/69) — every error envelope's `error.code`
  maps to a documented exit code in
  `src/accountpilot/core/cli/exit_codes.py`.
  `accountpilot completion <bash|zsh|fish>` emits shell completion
  scripts. `accountpilot self link` creates a `/usr/local/bin/`
  symlink; first launch of the .app prompts for it.
- **`docs/cli-contract.md`** — public agent contract: per-command
  schemas, exit-code matrix, stability promise.
  `tests/integration/cli_contract_test.py` validates real CLI output
  against JSON Schemas in `tests/integration/jsonschemas/`.
  `tests/integration/agent_smoke.sh` is a runnable add→OAuth→sync→
  search smoke (manual; requires real Gmail + browser).

## [0.1.4] — 2026-05-04 (AP-SP4)

### Fixed
- **Helper FDA grant now survives `brew upgrade`.** The signed helper
  Mach-O now embeds an `Info.plist` (CFBundleIdentifier
  `com.accountpilot.fda-helper`) into the `__TEXT,__info_plist`
  section, so macOS TCC keys the Full Disk Access grant by code-signing
  requirement (TeamID + bundle id) instead of by absolute path. Before
  this, every brew upgrade moved the helper into a fresh
  `Cellar/<version>/bin` path and TCC required a re-grant — defeating
  the entire point of the signed-helper architecture.
  Requires bumping the bundled helper to **fda-helper-v0.1.1**. After
  upgrading to 0.1.4 from 0.1.2/0.1.3, the user grants FDA one more
  time (because the cdhash changed in 0.1.1) and from then on the
  grant is permanent across all future Python and AccountPilot
  upgrades.
- **`accountpilot service install` no longer hard-codes the wrong
  Python interpreter into the launchd / systemd unit.** Previously,
  service install used `shutil.which("accountpilot")` which picks up
  whichever `accountpilot` is first on `$PATH` — frequently a stale
  anaconda or pyenv install, not the brew-managed one the user just
  invoked. The daemon then ran under that other interpreter, often
  with broken plugin discovery or missing FDA. New default resolves
  the script alongside `sys.executable`, so the daemon always runs
  under the same install that registered it. New `--bin` option lets
  power users override.

### Helper
- **fda-helper-v0.1.1.** Embeds `Info.plist` in the Mach-O. Same
  source-level behavior as 0.1.0; the only change is the linker flag
  `-sectcreate __TEXT __info_plist Info.plist` and a `CFBundleVersion`
  bump. Re-signed + re-notarized under the same Developer ID
  (FAZLA GIDA ANONIM SIRKETI, team P2R7PD8VGY).

## [0.1.3] — 2026-05-04 (AP-SP4)

### Added
- **Publisher-bundled OAuth client credentials.** End users no longer
  need to register their own GCP / Azure apps to use Mail. The wheel
  ships `accountpilot/oauth_clients/{google,microsoft}.json` with
  AccountPilot's published OAuth Desktop client (Google) and
  multi-tenant Public Client (Microsoft, authority `common`).
  `accountpilot oauth login google <id>` now opens the standard Google
  consent screen against AccountPilot's app — no Cloud Console, no JSON
  download, no manual config. Same for Microsoft: any work, school, or
  personal MS account works without touching Azure.
  Power-user override is preserved: drop a custom
  `oauth_clients/{google,microsoft}.json` under `$ACCOUNTPILOT_CONFIG_DIR`
  and AccountPilot prefers it over the bundled credentials.
  Until Google verifies the OAuth consent screen for the
  `https://mail.google.com/` scope, end users see the standard
  "unverified app" warning they can click through. Verification is
  async (weeks).

### Changed
- `oauth_cmd._load_client_config(provider, config_dir)` is the new
  resolver. User file beats bundled. Documentation-only keys (anything
  starting with `_`) are stripped before passing to the OAuth flow.
- Pre-release builds ship bundled JSONs containing
  `REPLACE_BEFORE_RELEASE` placeholders; `_has_unfilled_placeholder`
  fails-fast at login time with a clear message instead of producing a
  confusing OAuth round-trip with a literal placeholder client_id.

## [0.1.2] — 2026-05-04 (AP-SP4)

### Fixed
- **iMessage daemon: helper FDA grant is now actually checked under
  launchd.** `helper_client.iter_records` previously spawned the signed
  helper via `subprocess.Popen`, so macOS attributed all TCC checks to
  the parent (Python) — meaning the helper's own Full Disk Access grant
  was ignored and the daemon hit `EACCES` even when the helper was
  granted FDA. The whole point of the signed helper was to decouple FDA
  from Python's cdhash, but without disclaim that decoupling never
  happened. The new spawn primitive calls
  `responsibility_spawnattrs_setdisclaim(1)` via `posix_spawn`, making
  the helper its own TCC responsible process. Falls back to
  `subprocess.Popen` on Linux/Windows or when the env var
  `ACCOUNTPILOT_DISABLE_DISCLAIM=1` is set.
  After upgrading, users still need to grant FDA to
  `accountpilot-fda-helper` once (System Settings → Privacy & Security
  → Full Disk Access). The grant then survives all future Python and
  AccountPilot upgrades, as originally intended.

## [0.1.1] — 2026-05-04 (AP-SP4)

### Added
- **Signed FDA helper for iMessage.** `accountpilot-fda-helper` is a
  Developer-ID-signed Swift CLI (team `P2R7PD8VGY`,
  `com.accountpilot.fda-helper`) that mediates all
  `~/Library/Messages/chat.db` reads. Its cdhash is stable across
  AccountPilot and Python upgrades, so the macOS Full Disk Access
  grant survives `brew upgrade python@3.13` — the underlying issue
  that made AccountPilot effectively undistributable to non-technical
  users on previous releases. See
  [`docs/imessage-fda.md`](docs/imessage-fda.md) and
  [`helpers/fda-helper/PROTOCOL.md`](helpers/fda-helper/PROTOCOL.md)
  for the rationale and IPC contract.
- `accountpilot.plugins.imessage.helper_client` — subprocess client
  for the helper, plus `record_to_imessage()` for converting
  helper-emitted JSON-Lines records into `IMessageMessage` models.
- `scripts/release-helper.sh` — local build/sign/notarize/staple
  pipeline (defaults to FAZLA GIDA ANONIM SIRKETI cert; env-driven
  for other identities and CI).
- `accountpilot setup` now probes Full Disk Access on iMessage-enabled
  configs. On `EACCES` it deep-links into System Settings → Privacy
  & Security → Full Disk Access with copy guiding the user through
  toggling the auto-populated entry on.
- `.github/workflows/publish-pypi.yml` — Trusted Publishing for the
  Python sdist + wheel on `v*` tags.
- `.github/workflows/release-helper.yml` — Builds, signs, and notarizes
  the helper on `fda-helper-v*` tags. Runs on `macos-14` with the
  Developer ID cert imported from secrets and notarytool authenticated
  via App Store Connect API key.
- `docs/ci-setup.md` walks operators through one-time GitHub secret
  configuration for both workflows.

### Changed
- `accountpilot.plugins.imessage.reader.ChatDbReader` is now a thin
  façade over `helper_client`. The previous direct
  `sqlite3.connect(chat.db)` path is removed (hard cutover); existing
  users will need to grant FDA to the helper once and the grant then
  persists.
- iMessage tests stub `helper_client.iter_records` with an autouse
  fixture (`patch_helper_client` in `tests/.../conftest.py`) so the
  existing synthetic-chat.db suite runs without needing the Swift
  toolchain or a built helper binary.

### Removed
- `accountpilot.plugins.imessage.attachments` module
  (`AttachmentReader`, `load_attachments_for_message`). Disk reads of
  attachment files are now performed by the helper, base64-encoded,
  and inlined into the JSON-Lines message records.

### Distribution
- Homebrew tap (`aren13/tap`) bundles the signed helper as a
  `Resource` block fetched from GitHub Releases on Apple Silicon Mac.
  Mail-only users on Linux or Intel Mac install the formula without
  the helper. `brew upgrade` no longer requires the user to re-grant
  Full Disk Access.

## [Unreleased] — 2026-05-02 (AP-SP3)

### Added
- OAuth URI handlers in `Secrets.resolve()`: `oauth:google:<id>` (via
  google-auth + token endpoint) and `oauth:microsoft:<id>` (via msal),
  both with in-memory token cache and 60s pre-expiry refresh leeway.
- `accountpilot oauth {login,status,revoke}` CLI with interactive
  browser flow per provider. Refresh tokens persist at
  `~/runtime/accountpilot/secrets/oauth/<provider>/<id>.json` mode 0600.
- XOAUTH2 SASL in `accountpilot.plugins.mail.imap.client` — when
  `credentials_ref` starts with `oauth:`, IMAP authenticates via
  XOAUTH2 instead of LOGIN.
- `--account-id N` option on `mail daemon` and `imessage daemon` for
  single-account supervision (default: all enabled).
- `accountpilot.plugins.imessage.attributed_body.decode_attributed_body`
  via pytypedstream — fills `body_text` when chat.db's `text` column
  is NULL but `attributedBody` is present. Drops empty-body row count
  from ~70% to ~0% on real chat.db data.
- `accountpilot.core.logging.configure_daemon_logging` installs
  RotatingFileHandler (10MB × 5) on the root logger for daemon entry
  points. Logs that previously emitted nowhere now land in
  `~/runtime/accountpilot/logs/<plugin>.daemon.stdout.log`.
- `docs/how-to/ap-sp3-acceptance-guide.md` runbook.

### Changed
- `Secrets` is no longer a frozen dataclass with `@staticmethod resolve`.
  It's a mutable dataclass with instance-method `resolve` that holds
  per-handler token caches. `secrets_root` is a constructor param with
  default `~/runtime/accountpilot/secrets/`. All ~10 existing
  `Secrets({})` call sites continue to work.
- `pyproject.toml` adds `google-auth>=2.0`, `google-auth-oauthlib>=1.0`,
  `pytypedstream>=0.1` (LGPL-3.0).
- `MailAccountConfig.auth_method` field is now a no-op (kept for
  back-compat). The dispatch lives in `MailPlugin._make_real_imap`
  via `credentials_ref.startswith("oauth:")`.
- `ChatDbWatcher` now polls the chat.db inode every 30s and restarts
  watchdog's Observer on inode change — fixes SP2's post-WAL-checkpoint
  daemon stall.

### Fixed
- Latent runtime bug from AP-SP3 Task 2 refactor: `imap/client.py`
  was calling `Secrets.resolve()` statically but Secrets had been
  refactored to instance-method. Bug never fired in tests because the
  production ImapClient is replaced by FakeImapClient at the
  `_imap_factory` test seam. Removed in Task 5.

### Removed
- `.github/workflows/ci.yml` — stale MailPilot-era workflow that
  always failed (referenced `--cov=mailpilot`, no FDA, etc.). AP-SP4
  ships proper CI on macOS + Ubuntu.

## [Unreleased] — 2026-05-02 (AP-SP2)

### Added
- iMessage plugin under `accountpilot.plugins.imessage`: ChatDbReader
  (read-only sqlite3 over `~/Library/Messages/chat.db`),
  AttachmentReader (loads attachment bytes with `~` expansion),
  ChatDbWatcher (watchdog file-watcher with debounce), IMessagePlugin
  (5-hook lifecycle), `imessage backfill/sync/daemon` CLI subcommands.
- `kind_for_imessage_handle` in `core/identity.py` — dispatches
  iMessage handles to `kind='phone'` / `kind='email'` /
  `kind='imessage_handle'` for cross-source identity unification with
  Gmail correspondents.
- `~/Projects/infra/configs/machines/ae/launchd/com.accountpilot.imessage.daemon.plist`
  for AE deployment.
- `docs/how-to/ap-sp2-acceptance-guide.md` runbook.

### Changed
- `pyproject.toml` adds `watchdog>=4.0` dependency and registers the
  `imessage` plugin entry point.
- `Storage.save_imessage` resolves sender/participant handles via
  `kind_for_imessage_handle` instead of hard-coding
  `kind='imessage_handle'`.

## [Unreleased] — 2026-05-02 (AP-SP1)

### Added
- Mail plugin under `accountpilot.plugins.mail`: IMAP client, IDLE
  listener, Gmail/Outlook providers, OAuth helper, RFC822 → EmailMessage
  parser, sync orchestrator, MailPlugin lifecycle, `mail backfill/sync/daemon`
  CLI subcommands.
- `Secrets.resolve` recognizes `password_cmd:<shell cmd>` URIs
  (1Password CLI integration via `op read ...` shell wrapper).
- `Storage.latest_imap_uid(account_id, mailbox)` for sync watermarking.
- `MailPluginConfig` / `MailAccountConfig` typed config models for
  the `plugins.mail` block of `config.yaml`.
- Plugin entry-point discovery: root CLI registers plugin Click groups
  via `accountpilot.plugins` entry points instead of hard imports.
- `~/Projects/infra/configs/machines/ae/launchd/com.accountpilot.mail.daemon.plist`
  for AE deployment.

### Changed
- `pyproject.toml` project name flipped from `mailpilot` to `accountpilot`.
  The `mailpilot` console script is removed.
- `Storage.upsert_owner` now auto-merges cross-person identifier
  collisions (per AP-SP0 final review).

### Removed
- `src/mailpilot/` package (entirely).
- `tests/test_*.py` for mailpilot-specific features (composer, smtp,
  search/Xapian, tags, threading, events, database, daemon, cli, api,
  config, sync — replacements live under `tests/accountpilot/`).
- `mailpilot` console script.

[Unreleased]: https://github.com/ae/mail-pilot/commits/main
