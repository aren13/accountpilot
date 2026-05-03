"""Build a synthetic chat.db file with the minimal Apple-shaped schema.

Apple's real chat.db has dozens of tables and hundreds of columns; we
mirror only what ChatDbReader joins on. This keeps tests independent of
macOS Full Disk Access and runnable on any platform.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

# Apple's epoch is 2001-01-01 UTC; chat.db stores `date` as nanoseconds
# since that epoch.
_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def to_apple_ns(dt: datetime) -> int:
    """Convert a tz-aware datetime to Apple-Cocoa nanoseconds-since-2001."""
    delta = dt - _APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


@pytest.fixture
def chatdb_path(tmp_path: Path) -> Path:
    """Return a path to a freshly-built synthetic chat.db file."""
    db_path = tmp_path / "chat.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL,
            service TEXT NOT NULL DEFAULT 'iMessage'
        );
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            chat_identifier TEXT,
            display_name TEXT
        );
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            text TEXT,
            attributedBody BLOB,
            handle_id INTEGER REFERENCES handle(ROWID),
            service TEXT,
            date INTEGER,
            date_read INTEGER,
            is_from_me INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            cache_has_attachments INTEGER DEFAULT 0
        );
        CREATE TABLE chat_message_join (
            chat_id INTEGER REFERENCES chat(ROWID),
            message_id INTEGER REFERENCES message(ROWID),
            PRIMARY KEY (chat_id, message_id)
        );
        CREATE TABLE chat_handle_join (
            chat_id INTEGER REFERENCES chat(ROWID),
            handle_id INTEGER REFERENCES handle(ROWID),
            PRIMARY KEY (chat_id, handle_id)
        );
        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            filename TEXT,
            mime_type TEXT,
            transfer_name TEXT
        );
        CREATE TABLE message_attachment_join (
            message_id INTEGER REFERENCES message(ROWID),
            attachment_id INTEGER REFERENCES attachment(ROWID),
            PRIMARY KEY (message_id, attachment_id)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def insert_handle(db: Path, *, identifier: str) -> int:
    """Insert a handle row, return its ROWID."""
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO handle (id, service) VALUES (?, 'iMessage')",
        (identifier,),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    assert rowid is not None
    return rowid


def insert_chat(
    db: Path,
    *,
    guid: str,
    identifier: str | None = None,
    display_name: str | None = None,
) -> int:
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO chat (guid, chat_identifier, display_name) VALUES (?, ?, ?)",
        (guid, identifier, display_name),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    assert rowid is not None
    return rowid


def insert_message(
    db: Path,
    *,
    guid: str,
    text: str | None,
    handle_rowid: int,
    chat_rowid: int,
    sent_at: datetime,
    is_from_me: bool = False,
    is_read: bool = True,
    service: str = "iMessage",
    attributed_body: bytes | None = None,
) -> int:
    """Insert a message and link it to a chat. Returns message ROWID."""
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO message "
        "(guid, text, attributedBody, handle_id, service, date, "
        " is_from_me, is_read) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            guid,
            text,
            attributed_body,
            handle_rowid,
            service,
            to_apple_ns(sent_at),
            1 if is_from_me else 0,
            1 if is_read else 0,
        ),
    )
    msg_rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)",
        (chat_rowid, msg_rowid),
    )
    conn.commit()
    conn.close()
    assert msg_rowid is not None
    return msg_rowid


def add_chat_participant(db: Path, *, chat_rowid: int, handle_rowid: int) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO chat_handle_join (chat_id, handle_id) VALUES (?, ?)",
        (chat_rowid, handle_rowid),
    )
    conn.commit()
    conn.close()


def insert_attachment(
    db: Path,
    *,
    message_rowid: int,
    guid: str,
    filename: str | None,
    mime_type: str | None = None,
    transfer_name: str | None = None,
) -> int:
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO attachment (guid, filename, mime_type, transfer_name) "
        "VALUES (?, ?, ?, ?)",
        (guid, filename, mime_type, transfer_name),
    )
    att_rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO message_attachment_join (message_id, attachment_id) VALUES (?, ?)",
        (message_rowid, att_rowid),
    )
    conn.commit()
    conn.close()
    assert att_rowid is not None
    return att_rowid
