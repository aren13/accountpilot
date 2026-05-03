# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and other
contributors working in this repository.

## What This Repo Is

AccountPilot is a unified per-machine account sync framework — pulls
email, iMessage, calendar, and other personal data into a local
SQLite database through a plugin architecture. Source lives under
`src/accountpilot/`.

Treat `ROADMAP.md` as the source of truth for what exists and what is
planned.

## Architecture Invariants

These are load-bearing — violating them corrupts the data model.

- **Plugins never write to the DB or to disk directly.** Plugins emit
  events (`mail.new`, `message.new`, `calendar.event`, …) via the
  core's event bus. The `Storage` façade is the sole writer.
- **Plugins never embed or query a vector store.** Once Storage has
  written the row + attachments, AccountPilot's job is done.
- **Identity is first-class.** A unified `people` table with an
  `identifiers` map collapses the same person across email / phone /
  iMessage handle into one row. Plugins call `Storage.upsert_person`;
  they don't invent their own identity model.
- **Filename + content addressing is enforced by Storage.**
  Attachments live in a content-addressed store keyed by sha256;
  plugins never pick filenames.
- **Secrets never enter the repo.** Credentials live under the
  user's data directory (resolved via `core.paths`); never in source.
- **No cross-plugin direct imports.** Plugins communicate via the
  event bus. A plugin importing another plugin is an architecture
  violation.

## Sub-Slice Ordering

The Phase 1 work was broken into sequential, gating sub-slices:

- **AP-SP0** (✓ done) — Foundation: schema, Storage façade, plugin
  contract, CLI scaffolding, identity resolution, CAS.
- **AP-SP1** (✓ done) — Core + mail plugin with IMAP IDLE.
- **AP-SP2** (✓ done) — iMessage plugin (chat.db reader, watchdog
  file-watcher, attachment + group-chat support, cross-source
  identity).
- **AP-SP3** (✓ done) — OAuth (Google + Microsoft), multi-account
  daemon supervision, attributedBody decoder, daemon logging,
  chat.db inode-change recovery.
- **AP-SP4** (in progress) — open-source release: `pip install
  accountpilot`, AGPL-3.0, platformdirs paths, cross-platform
  service supervisor, CI matrix, PyPI publish.

## Plugin Contract

Plugins live under `src/accountpilot/plugins/<name>/`. Every plugin
implements a class derived from `AccountPilotPlugin` with five async
hooks: `setup`, `backfill`, `sync_once`, `daemon`, `teardown`.

Plugins register through the `accountpilot.plugins` entry-point group
in `pyproject.toml`. The CLI auto-registers a plugin's `<name>_group`
Click subgroup if the plugin's `cli.py` exports one.

## Working Conventions

- **Tests:** pytest + pytest-asyncio + pytest-cov. `asyncio_mode=auto`.
  Run `pytest -q` from the repo root.
- **Lint / format:** `ruff check`, `ruff format`. Pre-commit hooks
  enforce both — install with `pre-commit install`.
- **Types:** `mypy src/accountpilot`.
- **TDD:** add a failing test before the implementation. Mail and
  iMessage plugins have synthetic chat.db / IMAP fixtures so most
  tests run hermetically.
- **Commits:** Conventional Commits style (`feat(scope): …`,
  `fix(scope): …`, `chore: …`, etc.).
- **Dates in docs:** absolute YYYY-MM-DD.

## What This Repo Is Not

- Not a deployment system per se. The `accountpilot service install`
  command wraps launchd / systemd, but the project assumes one user
  on one machine; multi-user deployment is out of scope.
- Not a knowledge base. AccountPilot writes a queryable SQLite DB +
  CAS; downstream indexing / vector search is the user's choice.
- Not a daemon orchestrator across plugins. Each plugin runs under
  its own service unit; AccountPilot's `daemon` command is the
  process, the OS supervises.
