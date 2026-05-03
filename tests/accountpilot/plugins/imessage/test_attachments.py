from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from accountpilot.plugins.imessage.attachments import (
    AttachmentReader,
    load_attachments_for_message,
)
from tests.accountpilot.plugins.imessage.conftest import (
    insert_attachment,
    insert_chat,
    insert_handle,
    insert_message,
)

if TYPE_CHECKING:
    from pathlib import Path


def _seed_attachment_file(tmp_path: Path) -> Path:
    p = tmp_path / "Attachments" / "ab" / "01" / "pic.jpg"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\xff\xd8\xffSAMPLE")
    return p


def test_load_attachments_reads_bytes(
    chatdb_path: Path, tmp_path: Path
) -> None:
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c1")
    from datetime import UTC, datetime
    msg_rowid = insert_message(
        chatdb_path, guid="m-att-1", text="see pic",
        handle_rowid=h, chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    att_path = _seed_attachment_file(tmp_path)
    insert_attachment(
        chatdb_path, message_rowid=msg_rowid,
        guid="att-1", filename=str(att_path), mime_type="image/jpeg",
        transfer_name="pic.jpg",
    )

    conn = sqlite3.connect(f"file:{chatdb_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        blobs = load_attachments_for_message(conn, msg_rowid)
    finally:
        conn.close()

    assert len(blobs) == 1
    assert blobs[0].filename == "pic.jpg"
    assert blobs[0].mime_type == "image/jpeg"
    assert blobs[0].content == b"\xff\xd8\xffSAMPLE"


def test_load_attachments_skips_missing_file(
    chatdb_path: Path, tmp_path: Path
) -> None:
    """If an attachment row references a path that no longer exists on
    disk, the loader skips it rather than raising. macOS sometimes
    purges old attachments while leaving chat.db rows behind."""
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c1")
    from datetime import UTC, datetime
    msg_rowid = insert_message(
        chatdb_path, guid="m-att-2", text="missing",
        handle_rowid=h, chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    insert_attachment(
        chatdb_path, message_rowid=msg_rowid,
        guid="att-missing",
        filename=str(tmp_path / "ghost.bin"),  # never created
        mime_type="application/octet-stream",
    )

    conn = sqlite3.connect(f"file:{chatdb_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        blobs = load_attachments_for_message(conn, msg_rowid)
    finally:
        conn.close()

    assert blobs == []


def test_attachment_reader_expands_tilde(tmp_path: Path) -> None:
    """chat.db sometimes stores `~/Library/...` paths verbatim. The
    reader expands `~` before reading."""
    home_attachments = tmp_path / "fake-home" / "Library" / "Messages" / "Attachments"
    home_attachments.mkdir(parents=True)
    f = home_attachments / "x.txt"
    f.write_bytes(b"data")

    reader = AttachmentReader(home=tmp_path / "fake-home")
    assert reader.read("~/Library/Messages/Attachments/x.txt") == b"data"
