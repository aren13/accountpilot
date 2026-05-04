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

"""IMessagePlugin — 5-hook AccountPilotPlugin contract for iMessage."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from accountpilot.core.plugin import AccountPilotPlugin
from accountpilot.plugins.imessage.config import (
    IMessageAccountConfig,
    IMessagePluginConfig,
)
from accountpilot.plugins.imessage.reader import (
    _APPLE_EPOCH,  # noqa: PLC2701
    ChatDbReader,
)
from accountpilot.plugins.imessage.watcher import ChatDbWatcher

if TYPE_CHECKING:
    from pathlib import Path

    from accountpilot.core.auth import Secrets

log = logging.getLogger(__name__)


def _datetime_to_apple_ns(dt: datetime) -> int:
    delta = dt - _APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


class IMessagePlugin(AccountPilotPlugin):
    """iMessage source plugin: chat.db reader + file-watcher daemon."""

    name: ClassVar[str] = "imessage"

    def __init__(
        self,
        config: dict[str, Any],
        storage: Any,
        secrets: Secrets,
    ) -> None:
        super().__init__(config=config, storage=storage, secrets=secrets)
        self._cfg = IMessagePluginConfig.model_validate(config)
        self._accounts: dict[str, IMessageAccountConfig] = {
            a.identifier: a for a in self._cfg.accounts
        }
        # Test seam: tests inject an alternate reader factory if needed.
        self._reader_factory = self._make_real_reader
        self._watcher: ChatDbWatcher | None = None

    def _make_real_reader(
        self,
        account: IMessageAccountConfig,
        account_id: int,
    ) -> ChatDbReader:
        return ChatDbReader(account.chat_db_path, account_id=account_id)

    async def _resolve_account(self, account_id: int) -> IMessageAccountConfig:
        async with self.storage.db.execute(
            "SELECT account_identifier FROM accounts WHERE id=?",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise LookupError(f"account_id={account_id} not in DB")
        identifier = str(row["account_identifier"])
        if identifier not in self._accounts:
            raise LookupError(
                f"account_id={account_id} (identifier={identifier!r}) is not "
                f"configured in plugins.imessage.accounts in config.yaml"
            )
        return self._accounts[identifier]

    # ─── Lifecycle hooks ───────────────────────────────────────────────────

    async def setup(self) -> None:
        log.info(
            "imessage plugin setup: %d account(s) configured",
            len(self._accounts),
        )

    async def backfill(
        self,
        account_id: int,
        *,
        since: datetime | None = None,
    ) -> None:
        await self.sync_once(account_id, since=since)
        await self._mark_backfilled(account_id)

    async def sync_once(
        self,
        account_id: int,
        *,
        since: datetime | None = None,
        db_path: Path | None = None,  # noqa: ARG002 — storage injected via __init__
    ) -> int:
        """Sync once for the given account.

        Returns the number of NEW messages written this invocation.
        ``db_path`` is accepted for API symmetry with the CLI contract but
        is unused — storage was injected at construction time.
        """
        account = await self._resolve_account(account_id)
        # Watermark: if `since` was provided, use it; else read the
        # latest sent_at we've already stored for this account.
        if since is None:
            since = await self.storage.latest_sent_at(account_id)
        since_ns = _datetime_to_apple_ns(since) if since else None

        reader = self._reader_factory(account, account_id)
        inserted = 0
        skipped = 0
        try:
            for msg in reader.read_messages(since_ns=since_ns):
                result = await self.storage.save_imessage(msg)
                if result.action == "inserted":
                    inserted += 1
                elif result.action == "skipped":
                    skipped += 1
            await self.storage.update_sync_status(
                account_id,
                success=True,
                messages_added=inserted,
            )
            log.info(
                "imessage sync_once account=%d inserted=%d skipped=%d",
                account_id,
                inserted,
                skipped,
            )
        except Exception as e:
            await self.storage.update_sync_status(
                account_id,
                success=False,
                error=f"{type(e).__name__}: {e}",
            )
            raise
        return inserted

    async def daemon(self, account_id: int) -> None:
        account = await self._resolve_account(account_id)

        # Run sync_once at startup to catch up since the last shutdown.
        await self.sync_once(account_id)

        # Bridge the watcher's threading.Timer callback into asyncio.
        loop = asyncio.get_running_loop()
        sync_event = asyncio.Event()

        def _on_change() -> None:
            loop.call_soon_threadsafe(sync_event.set)

        self._watcher = ChatDbWatcher(
            account.chat_db_path,
            on_change=_on_change,
            debounce_seconds=self._cfg.debounce_seconds,
        )
        self._watcher.start()
        log.info("imessage daemon started for account=%d", account_id)
        try:
            while True:
                await sync_event.wait()
                sync_event.clear()
                try:
                    await self.sync_once(account_id)
                except Exception:  # noqa: BLE001
                    log.exception("imessage sync_once failed; will retry on next event")
        finally:
            self._watcher.stop()
            self._watcher = None

    async def teardown(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        log.info("imessage plugin teardown")

    # ─── Internals ─────────────────────────────────────────────────────────

    async def _mark_backfilled(self, account_id: int) -> None:
        await self.storage.db.execute(
            "UPDATE accounts SET backfilled_at=? WHERE id=?",
            (datetime.now(UTC).isoformat(), account_id),
        )
        await self.storage.db.commit()
