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

"""Tests for `accountpilot accounts ... --json`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.accounts_cmds import accounts_group
from accountpilot.core.db.connection import open_db


@pytest.fixture
async def populated_db(tmp_path: Path) -> Path:
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
        await conn.commit()
    return db


def test_list_json_returns_envelope(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        accounts_group,
        ["list", "--json", "--db-path", str(populated_db)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "ok": True,
        "data": {
            "accounts": [
                {
                    "id": 1,
                    "source": "gmail",
                    "identifier": "ada@example.com",
                    "enabled": True,
                    "owner_id": 1,
                    "owner_name": "Ada Lovelace",
                }
            ]
        },
        "error": None,
    }


def test_list_json_empty_db(tmp_path: Path) -> None:
    """Empty accounts list still emits a valid envelope, not no output."""
    import asyncio

    db = tmp_path / "empty.db"

    async def _setup() -> None:
        async with open_db(db) as _conn:
            pass  # open_db auto-applies migrations; no rows needed

    asyncio.run(_setup())

    runner = CliRunner()
    result = runner.invoke(
        accounts_group, ["list", "--json", "--db-path", str(db)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"ok": True, "data": {"accounts": []}, "error": None}
