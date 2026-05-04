"""Tests for `accountpilot messages list / get` and `attachments path`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path  # noqa: TC003

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.messages_cmds import messages_group
from accountpilot.core.db.connection import open_db


def _seed_three_messages(db: Path) -> None:
    """Two gmail messages + one imessage, with from-attribution and an
    attachment on message id 12.
    """
    async def _run() -> None:
        async with open_db(db) as conn:
            await conn.execute(
                "INSERT INTO people (id, name, surname, is_owner, "
                "created_at, updated_at) "
                "VALUES (1, 'Ada', NULL, 1, "
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
                "VALUES (1, 2, 'email', 'charles@example.com', 1, "
                "'2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO accounts (id, owner_id, source, "
                "account_identifier, enabled, created_at, updated_at) "
                "VALUES (1, 1, 'gmail', 'ada@example.com', 1, "
                "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            await conn.execute(
                "INSERT INTO accounts (id, owner_id, source, "
                "account_identifier, enabled, created_at, updated_at) "
                "VALUES (2, 1, 'imessage', '+15551234567', 1, "
                "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            for mid, acct, src, ext, sent, body in [
                (10, 1, 'gmail', 'g-1',
                 '2026-03-01T00:00:00+00:00', 'oldest msg'),
                (11, 1, 'gmail', 'g-2',
                 '2026-04-01T00:00:00+00:00', 'middle msg'),
                (12, 2, 'imessage', 'im-1',
                 '2026-05-01T00:00:00+00:00', 'newest msg'),
            ]:
                await conn.execute(
                    "INSERT INTO messages (id, account_id, source, "
                    "external_id, sent_at, body_text, direction, "
                    "created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'in', ?)",
                    (mid, acct, src, ext, sent, body, sent),
                )
                await conn.execute(
                    "INSERT INTO message_people (message_id, "
                    "person_id, role) VALUES (?, 2, 'from')",
                    (mid,),
                )
            await conn.execute(
                "INSERT INTO email_details (message_id, subject, "
                "imap_uid, mailbox) VALUES (10, 'Old subject', 1, 'INBOX')"
            )
            await conn.execute(
                "INSERT INTO email_details (message_id, subject, "
                "imap_uid, mailbox) VALUES (11, 'Middle subject', 2, 'INBOX')"
            )
            await conn.execute(
                "INSERT INTO attachments (message_id, filename, "
                "content_hash, mime_type, size_bytes, cas_path) "
                "VALUES (12, 'pic.jpg', 'abc123', 'image/jpeg', 4096, "
                "'ab/c1/abc123.bin')"
            )
            await conn.commit()
    asyncio.run(_run())


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    _seed_three_messages(db)
    return db


def test_messages_list_default(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group, ["list", "--json", "--db-path", str(populated_db)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    msgs = payload["data"]["messages"]
    assert len(msgs) == 3
    assert msgs[0]["id"] == 12
    assert msgs[0]["source"] == "imessage"
    assert msgs[0]["has_attachments"] is True
    assert msgs[0]["from_name"] == "Charles Babbage"
    assert msgs[0]["from_identifier"] == "charles@example.com"
    assert msgs[1]["id"] == 11
    assert msgs[1]["subject"] == "Middle subject"
    assert msgs[2]["id"] == 10
    assert msgs[2]["subject"] == "Old subject"
    assert msgs[2]["has_attachments"] is False
    assert payload["data"]["next_cursor"] is None


def test_messages_list_filtered_by_account(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["list", "--json", "--account", "1",
         "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    assert {m["id"] for m in payload["data"]["messages"]} == {10, 11}


def test_messages_list_filtered_by_contact(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["list", "--json", "--contact-id", "2",
         "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    assert {m["id"] for m in payload["data"]["messages"]} == {10, 11, 12}


def test_messages_list_filtered_by_since(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["list", "--json", "--since", "2026-04-15",
         "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    assert {m["id"] for m in payload["data"]["messages"]} == {12}


def test_messages_list_pagination_via_cursor(populated_db: Path) -> None:
    runner = CliRunner()
    result1 = runner.invoke(
        messages_group,
        ["list", "--json", "--limit", "2",
         "--db-path", str(populated_db)],
    )
    p1 = json.loads(result1.output)
    assert [m["id"] for m in p1["data"]["messages"]] == [12, 11]
    assert p1["data"]["next_cursor"] == 11

    result2 = runner.invoke(
        messages_group,
        ["list", "--json", "--cursor", "11",
         "--db-path", str(populated_db)],
    )
    p2 = json.loads(result2.output)
    assert [m["id"] for m in p2["data"]["messages"]] == [10]
    assert p2["data"]["next_cursor"] is None


def test_messages_get_imessage_with_attachment(populated_db: Path) -> None:
    """Message #12 from the seed has an attachment + Charles is from."""
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["get", "12", "--json", "--db-path", str(populated_db)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    m = payload["data"]["message"]
    assert m["id"] == 12
    assert m["source"] == "imessage"
    assert m["body_text"] == "newest msg"
    assert m["email"] is None
    assert m["subject"] is None
    assert any(
        p["role"] == "from" and p["name"] == "Charles Babbage"
        for p in m["people"]
    )
    assert len(m["attachments"]) == 1
    a = m["attachments"][0]
    assert a["filename"] == "pic.jpg"
    assert a["mime_type"] == "image/jpeg"
    assert a["content_hash"] == "abc123"
    assert "cas_path" not in a   # opaque; fetched separately


def test_messages_get_email_with_subject(populated_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["get", "11", "--json", "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    m = payload["data"]["message"]
    assert m["source"] == "gmail"
    assert m["subject"] == "Middle subject"
    assert m["email"] is not None
    assert m["email"]["mailbox"] == "INBOX"
    assert m["email"]["imap_uid"] == 2
    assert m["imessage"] is None


def test_messages_get_unknown_id(tmp_path: Path) -> None:
    """Returns ACCOUNT_NOT_FOUND-style envelope (not an exception)."""
    db = tmp_path / "fresh.db"
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["get", "999", "--json", "--db-path", str(db)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_attachments_path_returns_resolved_path(populated_db: Path) -> None:
    """Returns the absolute CAS path joined to <db_path.parent>/attachments/."""
    from accountpilot.core.cli.messages_cmds import attachments_group
    runner = CliRunner()
    cas_root = populated_db.parent / "attachments"
    cas_root.joinpath("ab/c1").mkdir(parents=True, exist_ok=True)
    blob = cas_root / "ab/c1/abc123.bin"
    blob.write_bytes(b"x" * 4096)

    result = runner.invoke(
        attachments_group,
        ["path", "1", "--json", "--db-path", str(populated_db)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["id"] == 1
    assert payload["data"]["absolute_path"] == str(blob.resolve())
    assert payload["data"]["exists"] is True
    assert payload["data"]["size_bytes"] == 4096


def test_attachments_path_unknown_id(populated_db: Path) -> None:
    from accountpilot.core.cli.messages_cmds import attachments_group
    runner = CliRunner()
    result = runner.invoke(
        attachments_group,
        ["path", "999", "--json", "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ATTACHMENT_NOT_FOUND"


def test_attachments_path_missing_blob_reports_exists_false(populated_db: Path) -> None:
    from accountpilot.core.cli.messages_cmds import attachments_group
    runner = CliRunner()
    # Don't create the blob on disk.
    result = runner.invoke(
        attachments_group,
        ["path", "1", "--json", "--db-path", str(populated_db)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["exists"] is False
