"""Mail plugin CLI tests."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 (used at runtime in function signature)

import pytest  # noqa: TC002 (MonkeyPatch used at runtime in fixture annotations)
from click.testing import CliRunner

from accountpilot.cli import cli
from accountpilot.core.db.connection import open_db
from accountpilot.plugins.mail.plugin import MailPlugin


def test_mail_subgroup_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "--help"])
    assert result.exit_code == 0
    assert "backfill" in result.output
    assert "sync" in result.output
    assert "daemon" in result.output


def test_mail_sync_runs_against_unconfigured_db_errors_cleanly(
    tmp_db_path: Path,
) -> None:
    """sync against a DB with no mail config should fail fast, not crash."""
    runner = CliRunner()
    missing_cfg = tmp_db_path.parent / "no-such-config.yaml"
    result = runner.invoke(
        cli,
        [
            "mail",
            "sync",
            "1",
            "--db-path",
            str(tmp_db_path),
            "--config",
            str(missing_cfg),
        ],
    )
    assert result.exit_code != 0


# ─── Daemon supervision tests (AP-SP3 Task 6) ────────────────────────────────


def _seed_two_gmail_accounts(db_path: Path) -> None:
    """Run migrations against db_path then seed: 1 owner + 2 enabled gmail accounts."""

    async def _migrate() -> None:
        async with open_db(db_path):
            pass

    asyncio.run(_migrate())

    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO people (name, surname, is_owner, created_at, updated_at) "
        "VALUES ('Aren', 'E', 1, ?, ?)",
        (now, now),
    )
    owner_id = conn.execute("SELECT id FROM people").fetchone()[0]
    conn.execute(
        "INSERT INTO accounts (owner_id, source, account_identifier, enabled, "
        "created_at, updated_at) VALUES (?, 'gmail', 'a@example.com', 1, ?, ?)",
        (owner_id, now, now),
    )
    conn.execute(
        "INSERT INTO accounts (owner_id, source, account_identifier, enabled, "
        "created_at, updated_at) VALUES (?, 'gmail', 'b@example.com', 1, ?, ?)",
        (owner_id, now, now),
    )
    conn.commit()
    conn.close()


def _write_two_account_config(cfg_path: Path) -> None:
    cfg_path.write_text(
        """version: 1
owners:
  - name: Aren
    surname: E
    identifiers:
      - kind: email
        value: a@example.com
      - kind: email
        value: b@example.com
plugins:
  mail:
    enabled: true
    accounts:
      - identifier: a@example.com
        owner: Aren
        provider: gmail
        credentials_ref: password_cmd:echo a
      - identifier: b@example.com
        owner: Aren
        provider: gmail
        credentials_ref: password_cmd:echo b
"""
    )


def test_mail_daemon_with_account_id_only_supervises_that_one(
    tmp_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --account-id N is passed, the daemon supervises only N,
    even if other accounts are enabled in the DB."""
    _seed_two_gmail_accounts(tmp_db_path)
    cfg_path = tmp_path / "config.yaml"
    _write_two_account_config(cfg_path)

    seen: list[int] = []

    async def fake_daemon(self: MailPlugin, account_id: int) -> None:
        seen.append(account_id)

    async def fake_setup(self: MailPlugin) -> None:
        return None

    monkeypatch.setattr(MailPlugin, "daemon", fake_daemon)
    monkeypatch.setattr(MailPlugin, "setup", fake_setup)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "mail", "daemon",
            "--account-id", "1",
            "--db-path", str(tmp_db_path),
            "--config", str(cfg_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == [1]


def test_mail_daemon_without_account_id_supervises_all_enabled(
    tmp_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no --account-id, daemon supervises every enabled gmail account."""
    _seed_two_gmail_accounts(tmp_db_path)
    cfg_path = tmp_path / "config.yaml"
    _write_two_account_config(cfg_path)

    seen: list[int] = []

    async def fake_daemon(self: MailPlugin, account_id: int) -> None:
        seen.append(account_id)

    async def fake_setup(self: MailPlugin) -> None:
        return None

    monkeypatch.setattr(MailPlugin, "daemon", fake_daemon)
    monkeypatch.setattr(MailPlugin, "setup", fake_setup)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "mail", "daemon",
            "--db-path", str(tmp_db_path),
            "--config", str(cfg_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert sorted(seen) == [1, 2]
