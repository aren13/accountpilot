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


def test_add_creates_account_with_new_owner(tmp_path: Path) -> None:
    """Add an account with --owner-name; the owner row is created."""
    db = tmp_path / "test.db"
    import asyncio

    async def _setup() -> None:
        async with open_db(db) as conn:
            pass  # open_db auto-applies migrations

    asyncio.run(_setup())

    runner = CliRunner()
    result = runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--owner-surname",
            "Lovelace",
            "--db-path",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["account"]["id"] == 1
    assert payload["data"]["account"]["source"] == "gmail"
    assert payload["data"]["account"]["identifier"] == "ada@example.com"
    assert payload["data"]["account"]["owner_id"] == 1
    assert payload["error"] is None


def test_add_reuses_existing_owner_by_identifier(tmp_path: Path) -> None:
    """Adding a second gmail account for the same owner reuses person row 1."""
    db = tmp_path / "test.db"
    import asyncio

    async def _setup() -> None:
        async with open_db(db) as conn:
            pass

    asyncio.run(_setup())

    runner = CliRunner()
    runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--owner-surname",
            "Lovelace",
            "--db-path",
            str(db),
        ],
    )
    result2 = runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada+work@example.com",
            "--owner-name",
            "Ada",
            "--owner-surname",
            "Lovelace",
            "--db-path",
            str(db),
        ],
    )
    assert result2.exit_code == 0, result2.output
    payload = json.loads(result2.output)
    assert payload["data"]["account"]["owner_id"] == 1, "should reuse owner #1"
    assert payload["data"]["account"]["id"] == 2


def test_add_duplicate_identifier_returns_error(tmp_path: Path) -> None:
    """Same (source, identifier) twice is a unique-constraint violation —
    surface as a clean error, not a stack trace."""
    db = tmp_path / "test.db"
    import asyncio

    async def _setup() -> None:
        async with open_db(db) as conn:
            pass

    asyncio.run(_setup())

    runner = CliRunner()
    runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--db-path",
            str(db),
        ],
    )
    result2 = runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--db-path",
            str(db),
        ],
    )
    # Exit code is 0 because we surface the error in the JSON envelope, not via
    # exit code — the Swift caller parses stdout regardless of exit code.
    assert result2.exit_code == 0, result2.output
    payload = json.loads(result2.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ACCOUNT_EXISTS"
    assert "ada@example.com" in payload["error"]["message"]


def test_remove_deletes_account(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        accounts_group, ["remove", "1", "--json", "--db-path", str(populated_db)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "ok": True,
        "data": {"removed_id": 1},
        "error": None,
    }

    list_result = runner.invoke(
        accounts_group, ["list", "--json", "--db-path", str(populated_db)]
    )
    assert json.loads(list_result.output)["data"]["accounts"] == []


def test_remove_unknown_id_returns_error(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        accounts_group, ["remove", "999", "--json", "--db-path", str(populated_db)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ACCOUNT_NOT_FOUND"
