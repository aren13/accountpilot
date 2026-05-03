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

"""ChatDbReader — read-only sqlite query over Apple's chat.db."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from accountpilot.core.models import IMessageMessage, IMessageService
from accountpilot.plugins.imessage.attachments import (
    AttachmentReader,
    load_attachments_for_message,
)
from accountpilot.plugins.imessage.attributed_body import decode_attributed_body

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# Apple's epoch is 2001-01-01 UTC; chat.db `message.date` is nanoseconds
# since that epoch.
_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def _apple_ns_to_datetime(ns: int) -> datetime:
    """Convert Apple-Cocoa nanoseconds-since-2001 → tz-aware UTC datetime."""
    return _APPLE_EPOCH + timedelta(microseconds=ns / 1000)


class ChatDbReader:
    """Read messages from a local Apple chat.db file.

    Opens the database read-only via the sqlite3 URI mode (`?mode=ro`) so
    a missing FDA grant fails fast with a clear error and never mutates
    Apple's file.
    """

    def __init__(
        self,
        chat_db_path: Path,
        account_id: int,
        attachment_reader: AttachmentReader | None = None,
    ) -> None:
        self.chat_db_path = chat_db_path
        self.account_id = account_id
        self.attachment_reader = attachment_reader or AttachmentReader()

    def read_messages(
        self, *, since_ns: int | None = None
    ) -> Iterator[IMessageMessage]:
        """Yield IMessageMessage rows newer than `since_ns` (Apple ns).

        If `since_ns` is None, yields everything.
        """
        uri = f"file:{self.chat_db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield from self._iter_rows(conn, since_ns)
        finally:
            conn.close()

    def _iter_rows(
        self, conn: sqlite3.Connection, since_ns: int | None
    ) -> Iterator[IMessageMessage]:
        # One row per message. Joined to chat (for chat_guid) and handle
        # (for sender_handle). NULL handle (system messages) skipped.
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
            sent_at = _apple_ns_to_datetime(row["date_ns"])
            date_read = (
                _apple_ns_to_datetime(row["date_read_ns"])
                if row["date_read_ns"]
                else None
            )
            svc_raw = row["service"] or "iMessage"
            service: IMessageService = (
                "iMessage" if svc_raw in {"iMessage", "RCS"} else "SMS"
            )
            body_text = str(row["text"] or "")
            if not body_text and row["attributed_body"]:
                # Apple stores rich-content message bodies (replies,
                # link previews, attachments-only) in attributedBody
                # with text=NULL. Fall back to the typedstream decoder.
                body_text = decode_attributed_body(row["attributed_body"])
            yield IMessageMessage(
                account_id=self.account_id,
                external_id=str(row["guid"]),
                sent_at=sent_at,
                direction="outbound" if row["is_from_me"] else "inbound",
                sender_handle=str(row["sender_handle"]),
                chat_guid=str(row["chat_guid"]),
                participants=participants,
                body_text=body_text,
                service=service,
                is_read=bool(row["is_read"]),
                date_read=date_read,
                attachments=load_attachments_for_message(
                    conn,
                    row["msg_rowid"],
                    self.attachment_reader,
                ),
            )
