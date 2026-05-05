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

"""Tests for `accountpilot people show <id> --json`."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.people_cmds import people_group
from accountpilot.core.db.connection import open_db


@pytest.fixture
async def db_with_charles(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    async with open_db(db) as conn:
        await conn.execute(
            "INSERT INTO people (id, name, surname, is_owner, "
            "created_at, updated_at) VALUES (1, 'Ada', 'Lovelace', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO people (id, name, surname, is_owner, "
            "created_at, updated_at) VALUES (2, 'Charles', 'Babbage', 0, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO identifiers (id, person_id, kind, value, "
            "is_primary, created_at) VALUES (1, 2, 'email', "
            "'charles@example.com', 1, '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO accounts (id, owner_id, source, "
            "account_identifier, enabled, created_at, updated_at) "
            "VALUES (1, 1, 'gmail', 'ada@example.com', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO messages (id, account_id, source, external_id, "
            "sent_at, body_text, direction, created_at) "
            "VALUES (10, 1, 'gmail', 'rfc-1', "
            "'2026-04-15T08:23:00+00:00', 'hi', 'in', "
            "'2026-04-15T08:23:01+00:00')"
        )
        await conn.execute(
            "INSERT INTO message_people (message_id, person_id, role) "
            "VALUES (10, 2, 'from')"
        )
        await conn.commit()
    return db


def test_people_show_json(db_with_charles: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        people_group,
        ["show", "2", "--json", "--db-path", str(db_with_charles)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    p = payload["data"]["person"]
    assert p["id"] == 2
    assert p["name"] == "Charles"
    assert p["surname"] == "Babbage"
    assert p["is_owner"] is False
    assert p["identifiers"] == [{"kind": "email", "value": "charles@example.com"}]
    assert p["message_count"] == 1
    assert p["last_message_at"] == "2026-04-15T08:23:00+00:00"
    assert p["roles"] == {"from": 1}


def test_people_show_unknown_id(db_with_charles: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        people_group,
        ["show", "999", "--json", "--db-path", str(db_with_charles)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PERSON_NOT_FOUND"
