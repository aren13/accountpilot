# AccountPilot

A unified per-machine account sync framework. Pulls email, iMessage,
calendar, and other personal data into a local SQLite database via a
plugin architecture. Designed for individual users who want a queryable
archive of their own data.

## Features

- **Mail (IMAP IDLE):** Gmail + Outlook + generic IMAP, OAuth2 (XOAUTH2)
  or password auth, RFC 2047 + MIME attachment handling, multi-account.
- **iMessage:** macOS chat.db reader with watchdog file-watcher,
  attachment + group-chat support, attributedBody decoder.
- **Cross-source identity:** one phone number = one person whether
  it appears in iMessage handles or Gmail signatures.
- **SQLite + FTS5 full-text search** across every source.
- **Auto-restarting background daemon** via launchd (macOS) or
  systemd (Linux) — install with one command.

## Installation

**Homebrew (macOS / Linuxbrew):**

```bash
brew install aren13/tap/accountpilot
```

**pip:**

```bash
pip install accountpilot
```

**pipx** (recommended for CLI-only use, isolates dependencies):

```bash
pipx install accountpilot
```

Requires Python 3.11+. macOS or Linux. (iMessage support is macOS-only;
mail works on both.)

## Quick start

```bash
# Create the config skeleton
accountpilot setup

# Edit ~/.config/accountpilot/config.yaml to add your accounts
$EDITOR ~/.config/accountpilot/config.yaml

# For OAuth-based accounts (recommended): set up Google Cloud Console /
# Azure AD OAuth client JSON, then run the interactive login:
accountpilot oauth login google 1
accountpilot oauth login microsoft 2

# One-shot historical pull:
accountpilot mail backfill 1
accountpilot imessage backfill 2

# Install the auto-restarting background daemon:
accountpilot service install mail
accountpilot service install imessage

# Search across all sources:
accountpilot search 'invoice'
accountpilot search '"meeting tomorrow"'
```

## Configuration

`~/.config/accountpilot/config.yaml` defines the people you sync FOR
(owners) and the accounts you sync FROM. See
[docs/configuration.md](docs/configuration.md) for the full schema.

## Documentation

- [Configuration](docs/configuration.md) — config.yaml schema
- [Plugins: Mail](docs/plugins/mail.md) — Gmail / Outlook / IMAP setup
- [Plugins: iMessage](docs/plugins/imessage.md) — chat.db permissions
- [OAuth setup](docs/oauth-setup.md) — Google Cloud / Azure AD recipes
- [Search](docs/search.md) — FTS5 query syntax
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

The AGPL'ed copy of `aioimaplib` (an upstream dependency) means
AccountPilot ships under AGPL too. If you build a network service
that exposes AccountPilot's functionality to end users, you must
publish your modifications under AGPL — see the LICENSE file.
