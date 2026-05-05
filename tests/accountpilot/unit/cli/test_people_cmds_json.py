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

"""Tests for `accountpilot people list --json`."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.people_cmds import people_group
from accountpilot.core.db.connection import open_db


@pytest.fixture
async def db_with_people(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    async with open_db(db) as conn:
        # Owner + 1 non-owner contact
        await conn.execute(
            "INSERT INTO people (id, name, surname, is_owner, "
            "created_at, updated_at) "
            "VALUES (1, 'Ada', 'Lovelace', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO people (id, name, surname, is_owner, "
            "created_at, updated_at) "
            "VALUES (2, 'Charles', 'Babbage', 0, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO identifiers (id, person_id, kind, value, "
            "is_primary, created_at) "
            "VALUES (1, 1, 'email', 'ada@example.com', 1, "
            "'2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO identifiers (id, person_id, kind, value, "
            "is_primary, created_at) "
            "VALUES (2, 2, 'email', 'charles@example.com', 1, "
            "'2026-01-01T00:00:00+00:00')"
        )
        # Account + 1 message linking Charles
        await conn.execute(
            "INSERT INTO accounts (id, owner_id, source, "
            "account_identifier, enabled, created_at, updated_at) "
            "VALUES (1, 1, 'gmail', 'ada@example.com', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO messages (id, account_id, source, external_id, "
            "sent_at, body_text, direction, created_at) "
            "VALUES (10, 1, 'gmail', 'a', "
            "'2026-04-01T00:00:00+00:00', 'hi', 'in', "
            "'2026-04-01T00:00:01+00:00')"
        )
        await conn.execute(
            "INSERT INTO message_people (message_id, person_id, role) "
            "VALUES (10, 2, 'from')"
        )
        await conn.commit()
    return db


def test_people_list_json_envelope(db_with_people: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        people_group, ["list", "--json", "--db-path", str(db_with_people)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    people = payload["data"]["people"]
    assert len(people) == 2
    by_id = {p["id"]: p for p in people}
    assert by_id[1]["name"] == "Ada"
    assert by_id[1]["is_owner"] is True
    assert by_id[1]["identifiers"] == [{"kind": "email", "value": "ada@example.com"}]
    assert by_id[1]["message_count"] == 0
    assert by_id[2]["name"] == "Charles"
    assert by_id[2]["is_owner"] is False
    assert by_id[2]["message_count"] == 1


def test_people_list_json_owners_only(db_with_people: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        people_group,
        ["list", "--json", "--owners", "--db-path", str(db_with_people)],
    )
    payload = json.loads(result.output)
    assert len(payload["data"]["people"]) == 1
    assert payload["data"]["people"][0]["is_owner"] is True
