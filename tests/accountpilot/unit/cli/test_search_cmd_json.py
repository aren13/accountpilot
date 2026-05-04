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

"""Tests for `accountpilot search --json`."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — used by click.Path

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.search_cmd import search_cmd
from accountpilot.core.db.connection import open_db


@pytest.fixture
async def db_with_searchable_messages(tmp_path: Path) -> Path:
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
            "VALUES (2, 1, 'gmail', 'ada@example.com', 1, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await conn.execute(
            "INSERT INTO messages (id, account_id, source, external_id, sent_at, "
            "body_text, direction, created_at) "
            "VALUES (10, 2, 'gmail', 'rfc-1', '2026-04-15T08:23:00+00:00', "
            "'the fazla quarterly numbers were strong', 'in', "
            "'2026-04-15T08:23:01+00:00')"
        )
        await conn.execute(
            "INSERT INTO email_details (message_id, subject, imap_uid, mailbox) "
            "VALUES (10, 'Q1 board update', 1234, 'INBOX')"
        )
        await conn.execute(
            "INSERT INTO messages (id, account_id, source, external_id, sent_at, "
            "body_text, direction, created_at) "
            "VALUES (11, 2, 'gmail', 'rfc-2', '2026-03-01T08:00:00+00:00', "
            "'unrelated text', 'in', '2026-03-01T08:00:01+00:00')"
        )
        await conn.execute(
            "INSERT INTO email_details (message_id, subject, imap_uid, mailbox) "
            "VALUES (11, 'Other', 1235, 'INBOX')"
        )
        await conn.commit()
    return db


def test_search_json_returns_only_matches(db_with_searchable_messages: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        search_cmd, ["fazla", "--json", "--db-path", str(db_with_searchable_messages)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    results = payload["data"]["results"]
    assert len(results) == 1
    r = results[0]
    assert r["id"] == 10
    assert r["source"] == "gmail"
    assert r["account_id"] == 2
    assert r["subject"] == "Q1 board update"
    assert "fazla" in r["snippet"].lower()
    assert "score" in r
    assert payload["data"]["query"] == "fazla"


def test_search_json_no_matches_returns_empty_list(
    db_with_searchable_messages: Path,
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        search_cmd,
        ["xyznotfound", "--json", "--db-path", str(db_with_searchable_messages)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["results"] == []


def test_search_json_respects_limit(db_with_searchable_messages: Path) -> None:
    runner = CliRunner()
    # "the" appears in both messages
    result = runner.invoke(
        search_cmd,
        ["the", "--json", "--limit", "1",
         "--db-path", str(db_with_searchable_messages)],
    )
    payload = json.loads(result.output)
    assert len(payload["data"]["results"]) == 1
