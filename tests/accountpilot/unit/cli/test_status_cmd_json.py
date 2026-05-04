# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Tests for `accountpilot status --json`."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.status_cmd import status_cmd
from accountpilot.core.db.connection import open_db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def db_with_synced_account(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    async with open_db(db) as conn:
        await conn.execute(
            "INSERT INTO people (id, name, surname, is_owner, created_at, updated_at) "
            "VALUES (1, 'Ada', 'Lovelace', 1, '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO accounts (id, owner_id, source, account_identifier, "
            "enabled, created_at, updated_at) "
            "VALUES (1, 1, 'gmail', 'ada@example.com', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO sync_status "
            "(account_id, last_sync_at, last_error, messages_ingested) "
            "VALUES (1, '2026-05-05T10:23:00+00:00', NULL, 4521)"
        )
        await conn.commit()
    return db


def test_status_json_envelope(db_with_synced_account: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        status_cmd, ["--json", "--db-path", str(db_with_synced_account)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    accounts = payload["data"]["accounts"]
    assert len(accounts) == 1
    a = accounts[0]
    assert a["id"] == 1
    assert a["source"] == "gmail"
    assert a["last_sync_at"] == "2026-05-05T10:23:00+00:00"
    assert a["last_error"] is None
    assert a["synced_count"] == 4521
    assert payload["data"]["generated_at"] is not None
    assert payload["error"] is None


def test_status_json_account_never_synced(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"

    async def _setup() -> None:
        async with open_db(db) as conn:
            await conn.execute(
                "INSERT INTO people "
                "(id, name, surname, is_owner, created_at, updated_at) "
                "VALUES (1, 'Ada', NULL, 1, '2026-01-01T00:00:00+00:00', "
                "'2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO accounts (id, owner_id, source, account_identifier, "
                "enabled, created_at, updated_at) "
                "VALUES (1, 1, 'imessage', '+15551234567', 1, "
                "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.commit()

    asyncio.run(_setup())

    runner = CliRunner()
    result = runner.invoke(status_cmd, ["--json", "--db-path", str(db)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    a = payload["data"]["accounts"][0]
    assert a["last_sync_at"] is None
    assert a["last_error"] is None
    assert a["synced_count"] == 0
