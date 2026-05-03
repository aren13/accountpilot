from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from click.testing import CliRunner

from accountpilot.cli import cli
from accountpilot.core.cas import CASStore
from accountpilot.core.cli.search_cmd import _format_local
from accountpilot.core.db.connection import open_db
from accountpilot.core.models import EmailMessage
from accountpilot.core.storage import Storage

if TYPE_CHECKING:
    from pathlib import Path


def _seed_one_email(db_path: Path) -> None:
    async def _run() -> None:
        async with open_db(db_path) as db:
            await db.execute(
                "INSERT INTO people (name, surname, is_owner, created_at, updated_at) "
                "VALUES ('Aren', NULL, 1, ?, ?)",
                (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()),
            )
            await db.execute(
                "INSERT INTO accounts (owner_id, source, account_identifier, enabled, "
                "created_at, updated_at) VALUES (1, 'gmail', 'a@b.com', 1, ?, ?)",
                (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()),
            )
            await db.commit()
            storage = Storage(db, CASStore(db_path.parent / "attachments"))
            await storage.save_email(
                EmailMessage(
                    account_id=1,
                    external_id="m1",
                    sent_at=datetime(2026, 5, 1, tzinfo=UTC),
                    received_at=None,
                    direction="inbound",
                    from_address="z@z",
                    to_addresses=[],
                    cc_addresses=[],
                    bcc_addresses=[],
                    subject="Project update",
                    body_text="lorem ipsum",
                    body_html=None,
                    in_reply_to=None,
                    references=[],
                    imap_uid=1,
                    mailbox="INBOX",
                    gmail_thread_id=None,
                    labels=[],
                    raw_headers={},
                    attachments=[],
                )
            )

    asyncio.run(_run())


def test_search_returns_matching_message(tmp_db_path: Path) -> None:
    _seed_one_email(tmp_db_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "lorem", "--db-path", str(tmp_db_path)])
    assert result.exit_code == 0, result.output
    assert "Project update" in result.output


def test_search_no_matches(tmp_db_path: Path) -> None:
    _seed_one_email(tmp_db_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "xyzzy", "--db-path", str(tmp_db_path)])
    assert result.exit_code == 0
    assert "no matches" in result.output.lower()


def test_format_local_converts_utc_to_fixed_local_tz() -> None:
    """Stored UTC timestamps display in the local timezone."""
    os.environ["TZ"] = "Europe/Istanbul"  # UTC+3, no DST
    time.tzset()
    try:
        out = _format_local("2026-05-02T17:43:25.882248+00:00")
        assert out == "2026-05-02 20:43:25 +0300"
    finally:
        del os.environ["TZ"]
        time.tzset()


def test_format_local_preserves_non_utc_offset() -> None:
    """Gmail-style offsets are normalized to local tz, not echoed verbatim."""
    os.environ["TZ"] = "Europe/Istanbul"
    time.tzset()
    try:
        out = _format_local("2026-03-19T09:24:34-04:00")
        assert out == "2026-03-19 16:24:34 +0300"
    finally:
        del os.environ["TZ"]
        time.tzset()


def test_format_local_returns_input_on_unparseable() -> None:
    assert _format_local("not-a-date") == "not-a-date"
