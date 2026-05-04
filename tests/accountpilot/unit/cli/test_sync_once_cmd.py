"""Tests for `accountpilot sync-once {mail,imessage} <id>`.

The actual sync is mocked — these tests verify the CLI wiring + envelope.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.sync_once_cmd import sync_once_group
from accountpilot.core.db.connection import open_db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_account(tmp_path: Path) -> Path:
    """Seed an accounts row so the CLI can look up the source."""
    db = tmp_path / "test.db"

    async def _setup() -> None:
        async with open_db(db) as conn:
            await conn.execute(
                "INSERT INTO people"
                " (id, name, surname, is_owner, created_at, updated_at)"
                " VALUES (1, 'Ada', NULL, 1,"
                " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO accounts"
                " (id, owner_id, source, account_identifier,"
                " enabled, created_at, updated_at)"
                " VALUES (1, 1, 'gmail', 'ada@example.com', 1,"
                " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.commit()

    asyncio.run(_setup())
    return db


def test_mail_sync_once_success(db_with_account: Path) -> None:
    """sync-once mail returns synced_count_delta on a clean run."""
    with patch(
        "accountpilot.plugins.mail.plugin.MailPlugin.sync_once",
        new=AsyncMock(return_value=12),
    ):
        runner = CliRunner()
        result = runner.invoke(
            sync_once_group,
            ["mail", "1", "--json", "--db-path", str(db_with_account)],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["account_id"] == 1
    assert payload["data"]["source"] == "gmail"
    assert payload["data"]["synced_count_delta"] == 12
    assert "duration_seconds" in payload["data"]
    assert payload["error"] is None


def test_mail_sync_once_failure_emits_error_envelope(db_with_account: Path) -> None:
    with patch(
        "accountpilot.plugins.mail.plugin.MailPlugin.sync_once",
        new=AsyncMock(side_effect=RuntimeError("IMAP timeout")),
    ):
        runner = CliRunner()
        result = runner.invoke(
            sync_once_group,
            ["mail", "1", "--json", "--db-path", str(db_with_account)],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "SYNC_FAILED"
    assert "IMAP timeout" in payload["error"]["message"]


def test_imessage_sync_once_success(tmp_path: Path) -> None:
    """sync-once imessage uses the imessage source string."""
    db = tmp_path / "im.db"

    async def _setup() -> None:
        async with open_db(db) as conn:
            await conn.execute(
                "INSERT INTO people"
                " (id, name, surname, is_owner, created_at, updated_at)"
                " VALUES (1, 'Ada', NULL, 1,"
                " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO accounts"
                " (id, owner_id, source, account_identifier,"
                " enabled, created_at, updated_at)"
                " VALUES (5, 1, 'imessage', '+15551234567', 1,"
                " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.commit()

    asyncio.run(_setup())

    with patch(
        "accountpilot.plugins.imessage.plugin.IMessagePlugin.sync_once",
        new=AsyncMock(return_value=3),
    ):
        runner = CliRunner()
        result = runner.invoke(
            sync_once_group,
            ["imessage", "5", "--json", "--db-path", str(db)],
        )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data"]["account_id"] == 5
    assert payload["data"]["source"] == "imessage"
    assert payload["data"]["synced_count_delta"] == 3


def test_sync_once_unknown_account(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"

    async def _setup() -> None:
        async with open_db(db) as _conn:
            pass

    asyncio.run(_setup())

    runner = CliRunner()
    result = runner.invoke(
        sync_once_group,
        ["mail", "999", "--json", "--db-path", str(db)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ACCOUNT_NOT_FOUND"
