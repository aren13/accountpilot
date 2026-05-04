from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 (used at runtime in function signature)
from unittest.mock import patch

import pytest  # noqa: TC002 (MonkeyPatch used at runtime in fixture annotations)
from click.testing import CliRunner

from accountpilot.cli import cli
from accountpilot.core.db.connection import open_db
from accountpilot.plugins.imessage.plugin import IMessagePlugin


def test_imessage_subgroup_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["imessage", "--help"])
    assert result.exit_code == 0, result.output
    assert "backfill" in result.output
    assert "sync" in result.output
    assert "daemon" in result.output


def test_imessage_sync_with_missing_config_errors_cleanly(
    tmp_db_path: Path,
) -> None:
    runner = CliRunner()
    missing_cfg = tmp_db_path.parent / "no-such-config.yaml"
    result = runner.invoke(
        cli,
        [
            "imessage",
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


def _seed_two_imessage_accounts(db_path: Path) -> None:
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
        "created_at, updated_at) VALUES (?, 'imessage', 'aren@local', 1, ?, ?)",
        (owner_id, now, now),
    )
    conn.execute(
        "INSERT INTO accounts (owner_id, source, account_identifier, enabled, "
        "created_at, updated_at) VALUES (?, 'imessage', 'aren@laptop', 1, ?, ?)",
        (owner_id, now, now),
    )
    conn.commit()
    conn.close()


def _write_two_imessage_config(cfg_path: Path, chat_db_path: Path) -> None:
    cfg_path.write_text(
        f"""version: 1
owners:
  - name: Aren
    surname: E
    identifiers:
      - kind: email
        value: aren@example.com
plugins:
  imessage:
    enabled: true
    accounts:
      - identifier: aren@local
        owner: Aren
        chat_db_path: {chat_db_path}
      - identifier: aren@laptop
        owner: Aren
        chat_db_path: {chat_db_path}
"""
    )


def test_imessage_daemon_with_account_id_only_supervises_that_one(
    tmp_db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --account-id N is passed, the daemon supervises only N,
    even if other accounts are enabled in the DB."""
    _seed_two_imessage_accounts(tmp_db_path)
    chat_db = tmp_path / "chat.db"
    chat_db.touch()
    cfg_path = tmp_path / "config.yaml"
    _write_two_imessage_config(cfg_path, chat_db)

    seen: list[int] = []

    async def fake_daemon(self: IMessagePlugin, account_id: int) -> None:
        seen.append(account_id)

    async def fake_setup(self: IMessagePlugin) -> None:
        return None

    monkeypatch.setattr(IMessagePlugin, "daemon", fake_daemon)
    monkeypatch.setattr(IMessagePlugin, "setup", fake_setup)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "imessage",
            "daemon",
            "--account-id",
            "1",
            "--db-path",
            str(tmp_db_path),
            "--config",
            str(cfg_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == [1]


def test_imessage_daemon_without_account_id_supervises_all_enabled(
    tmp_db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no --account-id, daemon supervises every enabled imessage account."""
    _seed_two_imessage_accounts(tmp_db_path)
    chat_db = tmp_path / "chat.db"
    chat_db.touch()
    cfg_path = tmp_path / "config.yaml"
    _write_two_imessage_config(cfg_path, chat_db)

    seen: list[int] = []

    async def fake_daemon(self: IMessagePlugin, account_id: int) -> None:
        seen.append(account_id)

    async def fake_setup(self: IMessagePlugin) -> None:
        return None

    monkeypatch.setattr(IMessagePlugin, "daemon", fake_daemon)
    monkeypatch.setattr(IMessagePlugin, "setup", fake_setup)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "imessage",
            "daemon",
            "--db-path",
            str(tmp_db_path),
            "--config",
            str(cfg_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert sorted(seen) == [1, 2]


# ─── probe-fda tests (Task 9) ────────────────────────────────────────────────


def test_probe_fda_helper_missing() -> None:
    """HELPER_MISSING when find_helper_binary raises HelperNotInstalledError."""
    from accountpilot.plugins.imessage import helper_client
    from accountpilot.plugins.imessage.cli import imessage_group

    with patch.object(
        helper_client,
        "find_helper_binary",
        side_effect=helper_client.HelperNotInstalledError("not in $PATH"),
    ):
        runner = CliRunner()
        result = runner.invoke(imessage_group, ["probe-fda", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["granted"] is False
    assert payload["data"]["reason"] == "HELPER_MISSING"


def test_probe_fda_denied() -> None:
    """FDA_DENIED when iter_records raises HelperPermissionError."""
    from accountpilot.plugins.imessage import helper_client
    from accountpilot.plugins.imessage.cli import imessage_group

    def _raise_permission(*args: object, **kwargs: object) -> None:
        raise helper_client.HelperPermissionError("FDA denied")

    fake_path = Path("/fake/helper")
    with (
        patch.object(helper_client, "find_helper_binary", return_value=fake_path),
        patch.object(helper_client, "iter_records", _raise_permission),
    ):
        runner = CliRunner()
        result = runner.invoke(imessage_group, ["probe-fda", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["granted"] is False
    assert payload["data"]["reason"] == "FDA_DENIED"


def test_probe_fda_granted() -> None:
    """OK when iter_records returns an empty iterator (no records, no error)."""
    from accountpilot.plugins.imessage import helper_client
    from accountpilot.plugins.imessage.cli import imessage_group

    def _empty_iter(*args: object, **kwargs: object):  # type: ignore[return]
        return iter([])

    fake_path = Path("/fake/helper")
    with (
        patch.object(helper_client, "find_helper_binary", return_value=fake_path),
        patch.object(helper_client, "iter_records", _empty_iter),
    ):
        runner = CliRunner()
        result = runner.invoke(imessage_group, ["probe-fda", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["granted"] is True
    assert payload["data"]["reason"] == "OK"
