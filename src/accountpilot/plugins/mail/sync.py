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

"""Sync orchestrator: ImapClient + Storage → ingested rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from accountpilot.plugins.mail.parser import parse_rfc822_to_email_message

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from accountpilot.core.models import EmailMessage
    from accountpilot.core.storage import Storage


class _ImapClientProto(Protocol):
    async def fetch_uids(self, folder: str, *, since_uid: int = 0) -> list[int]: ...
    async def fetch_message(self, folder: str, uid: int) -> bytes: ...


@dataclass(frozen=True)
class SyncResult:
    inserted: int
    skipped: int


async def sync_account_mailbox(
    *,
    storage: Storage,
    imap: _ImapClientProto,
    account_id: int,
    mailbox: str,
    gmail_thread_resolver: Callable[[bytes], Awaitable[str | None]] | None,
    labels: list[str],
) -> SyncResult:
    """Fetch new UIDs from `imap`, parse, and persist via `storage.save_email`.

    Resumes from `Storage.latest_imap_uid(account_id, mailbox)`. Re-running is
    safe: the IMAP UID watermark advances monotonically and Storage dedupes by
    `(account_id, external_id)` regardless.
    """
    watermark = await storage.latest_imap_uid(account_id, mailbox) or 0
    uids = await imap.fetch_uids(mailbox, since_uid=watermark)
    inserted = 0
    skipped = 0

    for uid in uids:
        raw = await imap.fetch_message(mailbox, uid)
        gmail_thread_id = (
            await gmail_thread_resolver(raw) if gmail_thread_resolver else None
        )
        msg: EmailMessage = parse_rfc822_to_email_message(
            raw_bytes=raw,
            account_id=account_id,
            mailbox=mailbox,
            imap_uid=uid,
            direction="inbound",
            gmail_thread_id=gmail_thread_id,
            labels=list(labels),
        )
        result = await storage.save_email(msg)
        if result.action == "inserted":
            inserted += 1
        elif result.action == "skipped":
            skipped += 1

    return SyncResult(inserted=inserted, skipped=skipped)
