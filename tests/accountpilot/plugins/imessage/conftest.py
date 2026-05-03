"""Build a synthetic chat.db file with the minimal Apple-shaped schema.

Apple's real chat.db has dozens of tables and hundreds of columns; we
mirror only what the FDA helper joins on. This keeps tests independent
of macOS Full Disk Access and runnable on any platform.

In production the Swift helper at helpers/fda-helper/ is the only path
that reads chat.db. Tests stub helper_client.iter_records via the
``patch_helper_client`` autouse fixture below — it runs the same JOIN
query the helper does, against the synthetic SQLite file, and emits
the dict-shaped JSON-Lines records the helper would produce. This lets
the existing integration tests exercise the full plugin pipeline
without needing the Swift toolchain or a built helper binary.
"""

from __future__ import annotations

import base64
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from accountpilot.plugins.imessage import helper_client, reader

if TYPE_CHECKING:
    from collections.abc import Iterator

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


# ─── Helper-binary stub ───────────────────────────────────────────────


def _python_iter_records(
    *,
    chat_db_path: Path | None = None,
    since_ns: int | None = None,
    helper_path: Path | None = None,  # noqa: ARG001 — accepted for signature parity
) -> Iterator[dict[str, Any]]:
    """Drop-in for helper_client.iter_records that reads a synthetic SQLite.

    Re-implements the Swift helper's JOIN query in Python so tests can
    exercise the full plugin pipeline without needing the signed helper
    binary or macOS FDA. Emits the same dict shape the helper does
    (PROTOCOL.md v1).
    """
    if chat_db_path is None:
        raise RuntimeError(
            "test stub requires an explicit chat_db_path; production calls "
            "the signed helper which defaults to ~/Library/Messages/chat.db"
        )
    uri = f"file:{chat_db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT
                m.ROWID                AS msg_rowid,
                m.guid                 AS guid,
                m.text                 AS text,
                m.attributedBody       AS attributed_body,
                m.is_from_me           AS is_from_me,
                COALESCE(m.is_read, 0) AS is_read,
                m.date                 AS date_ns,
                m.date_read            AS date_read_ns,
                m.service              AS service,
                h.id                   AS sender_handle,
                c.guid                 AS chat_guid
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE h.id IS NOT NULL
        """
        params: tuple[int, ...] = ()
        if since_ns is not None:
            sql += " AND m.date > ?"
            params = (since_ns,)
        sql += " ORDER BY m.date ASC, m.ROWID ASC"

        for row in conn.execute(sql, params):
            participants = [
                p["id"]
                for p in conn.execute(
                    "SELECT h.id FROM chat_handle_join chj "
                    "JOIN handle h ON h.ROWID = chj.handle_id "
                    "WHERE chj.chat_id = (SELECT ROWID FROM chat WHERE guid=?)",
                    (row["chat_guid"],),
                )
            ]
            attachments: list[dict[str, Any]] = []
            for att in conn.execute(
                "SELECT a.filename, a.mime_type, a.transfer_name "
                "FROM attachment a "
                "JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID "
                "WHERE maj.message_id = ?",
                (row["msg_rowid"],),
            ):
                raw_path = att["filename"]
                if not raw_path:
                    continue
                resolved = Path(
                    raw_path.replace("~/", str(Path.home()) + "/")
                    if raw_path.startswith("~/")
                    else raw_path
                )
                try:
                    content = resolved.read_bytes()
                except (FileNotFoundError, IsADirectoryError, PermissionError):
                    continue
                display = att["transfer_name"] or resolved.name or "attachment.bin"
                attachments.append(
                    {
                        "filename": display,
                        "mime_type": att["mime_type"],
                        "content_b64": base64.b64encode(content).decode(),
                    }
                )
            attr_blob = row["attributed_body"]
            yield {
                "v": 1,
                "type": "message",
                "guid": row["guid"],
                "text": row["text"],
                "attributed_body_b64": (
                    base64.b64encode(attr_blob).decode() if attr_blob else None
                ),
                "is_from_me": bool(row["is_from_me"]),
                "is_read": bool(row["is_read"]),
                "date_ns": int(row["date_ns"]),
                "date_read_ns": int(row["date_read_ns"])
                if row["date_read_ns"]
                else None,
                "service": row["service"] or "iMessage",
                "sender_handle": row["sender_handle"],
                "chat_guid": row["chat_guid"],
                "participants": participants,
                "attachments": attachments,
            }
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def patch_helper_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace helper_client.iter_records with the in-Python stub.

    Autouse so every test in the iMessage suite runs against the stub
    by default. Tests that need the production subprocess path can
    monkeypatch back, but no test currently does.
    """
    monkeypatch.setattr(helper_client, "iter_records", _python_iter_records)
    monkeypatch.setattr(reader, "iter_records", _python_iter_records)
