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

"""Integration tests: real CLI output ↔ documented schemas.

Runs each documented read command against a fixture DB, captures
stdout, and validates against the matching schema in jsonschemas/.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from accountpilot.core.db.connection import open_db

SCHEMA_DIR = Path(__file__).parent / "jsonschemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """A DB seeded with one owner + one account + one message + one attachment."""
    db = tmp_path / "test.db"

    async def _seed() -> None:
        async with open_db(db) as conn:
            await conn.execute(
                "INSERT INTO people (id, name, surname, is_owner, "
                "created_at, updated_at) VALUES (1, 'Ada', 'Lovelace', 1, "
                "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO identifiers (id, person_id, kind, value, "
                "is_primary, created_at) VALUES (1, 1, 'email', "
                "'ada@example.com', 1, '2026-01-01T00:00:00+00:00')"
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
                "'2026-04-15T08:23:00+00:00', 'fazla content', 'in', "
                "'2026-04-15T08:23:01+00:00')"
            )
            await conn.execute(
                "INSERT INTO email_details (message_id, subject, "
                "imap_uid, mailbox) VALUES (10, 'Subject', 1, 'INBOX')"
            )
            await conn.execute(
                "INSERT INTO message_people (message_id, person_id, role) "
                "VALUES (10, 1, 'from')"
            )
            await conn.execute(
                "INSERT INTO attachments (message_id, filename, "
                "content_hash, mime_type, size_bytes, cas_path) "
                "VALUES (10, 'pic.jpg', 'abc123', 'image/jpeg', 4096, "
                "'ab/c1/abc123.bin')"
            )
            await conn.commit()

    asyncio.run(_seed())
    return db


def _run(args: list[str], db: Path) -> dict:
    """Run the CLI and parse stdout JSON. Asserts exit 0."""
    cmd = [sys.executable, "-m", "accountpilot.cli"] + args + ["--db-path", str(db)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (
        f"CLI failed (exit {result.returncode}): {result.stderr}"
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "schema_name,args",
    [
        ("accounts_list", ["accounts", "list", "--json"]),
        ("people_list", ["people", "list", "--json"]),
        ("messages_list", ["messages", "list", "--json"]),
        ("search", ["search", "fazla", "--json"]),
        ("status", ["status", "--json"]),
    ],
)
def test_cli_output_matches_schema(
    populated_db: Path, schema_name: str, args: list[str]
) -> None:
    payload = _run(args, populated_db)
    schema = _load_schema(schema_name)
    jsonschema.validate(instance=payload, schema=schema)


def test_messages_get_schema(populated_db: Path) -> None:
    payload = _run(["messages", "get", "10", "--json"], populated_db)
    jsonschema.validate(instance=payload, schema=_load_schema("messages_get"))


def test_people_show_schema(populated_db: Path) -> None:
    payload = _run(["people", "show", "1", "--json"], populated_db)
    jsonschema.validate(instance=payload, schema=_load_schema("people_show"))


def test_attachments_path_schema(populated_db: Path) -> None:
    # attachments path requires the CAS file to exist for `exists: true`,
    # but the schema doesn't constrain `exists` to a value — just structure.
    payload = _run(["attachments", "path", "1", "--json"], populated_db)
    jsonschema.validate(instance=payload, schema=_load_schema("attachments_path"))


def test_oauth_status_schema(tmp_path: Path) -> None:
    # oauth status uses --secrets-root, not --db-path, so don't use _run helper.
    cmd = [
        sys.executable,
        "-m",
        "accountpilot.cli",
        "oauth",
        "status",
        "--json",
        "--secrets-root",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    jsonschema.validate(instance=payload, schema=_load_schema("oauth_status"))
