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

"""Load attachment bytes referenced by chat.db rows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from accountpilot.core.models import AttachmentBlob

if TYPE_CHECKING:
    import sqlite3

log = logging.getLogger(__name__)


class AttachmentReader:
    """Read attachment bytes from disk, with `~` expansion against `home`.

    chat.db sometimes stores attachment paths as `~/Library/...` and
    sometimes as absolute `/Users/<name>/Library/...`. The reader
    handles both.
    """

    def __init__(self, home: Path | None = None) -> None:
        self.home = home if home is not None else Path.home()

    def _resolve(self, raw_path: str) -> Path:
        if raw_path.startswith("~"):
            return self.home / raw_path.lstrip("~/")
        return Path(raw_path)

    def read(self, raw_path: str) -> bytes:
        """Read bytes from `raw_path` (may start with `~`)."""
        return self._resolve(raw_path).read_bytes()


def load_attachments_for_message(
    conn: sqlite3.Connection,
    message_rowid: int,
    reader: AttachmentReader | None = None,
) -> list[AttachmentBlob]:
    """Return AttachmentBlob list for `message_rowid` from an open chat.db.

    Missing files (chat.db row references a path that no longer exists,
    common after macOS prunes old attachments) are skipped with a debug
    log line — they don't fail the whole save_imessage call.
    """
    rdr = reader or AttachmentReader()
    blobs: list[AttachmentBlob] = []
    rows = conn.execute(
        "SELECT a.filename, a.mime_type, a.transfer_name "
        "FROM attachment a "
        "JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID "
        "WHERE maj.message_id = ?",
        (message_rowid,),
    )
    for row in rows:
        raw_path = row["filename"]
        if not raw_path:
            continue
        try:
            content = rdr.read(raw_path)
        except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
            log.debug("attachment %r missing/unreadable: %s", raw_path, exc)
            continue
        filename = (
            row["transfer_name"]
            or Path(raw_path).name
            or "attachment.bin"
        )
        blobs.append(AttachmentBlob(
            filename=filename,
            content=content,
            mime_type=row["mime_type"],
        ))
    return blobs
