from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from accountpilot.core.auth import Secrets
from accountpilot.core.cas import CASStore
from accountpilot.core.db.connection import open_db
from accountpilot.core.models import Identifier
from accountpilot.core.storage import Storage
from accountpilot.plugins.imessage.config import (
    IMessageAccountConfig,
    IMessagePluginConfig,
)
from accountpilot.plugins.imessage.plugin import IMessagePlugin
from tests.accountpilot.plugins.imessage.conftest import (
    add_chat_participant,
    insert_chat,
    insert_handle,
    insert_message,
)

if TYPE_CHECKING:
    from pathlib import Path


async def _seed_account(storage: Storage, identifier: str) -> int:
    owner = await storage.upsert_owner(
        name="Aren", surname=None,
        identifiers=[Identifier(kind="phone", value=identifier)],
    )
    return await storage.upsert_account(
        source="imessage", identifier=identifier, owner_id=owner,
    )


async def test_sync_once_ingests_chat_db_messages(
    tmp_db_path: Path, tmp_runtime: Path, chatdb_path: Path,
) -> None:
    me = "+15551234567"
    melis = "+905052490140"

    # Seed synthetic chat.db with one inbound message from melis.
    h_me = insert_handle(chatdb_path, identifier=me)
    h_melis = insert_handle(chatdb_path, identifier=melis)
    chat = insert_chat(chatdb_path, guid=f"iMessage;-;{melis}",
                       identifier=melis)
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=h_me)
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=h_melis)
    insert_message(
        chatdb_path, guid="GUID-1", text="hi",
        handle_rowid=h_melis, chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )

    async with open_db(tmp_db_path) as db:
        storage = Storage(db, CASStore(tmp_runtime / "attachments"))
        account_id = await _seed_account(storage, me)

        cfg = IMessagePluginConfig(accounts=[IMessageAccountConfig(
            identifier=me, owner=me, chat_db_path=chatdb_path,
        )])
        plugin = IMessagePlugin(
            config=cfg.model_dump(), storage=storage, secrets=Secrets({}),
        )
        await plugin.setup()
        await plugin.sync_once(account_id)

        async with db.execute("SELECT COUNT(*) AS c FROM messages") as cur:
            assert (await cur.fetchone())["c"] == 1
        async with db.execute(
            "SELECT chat_guid FROM imessage_details"
        ) as cur:
            row = await cur.fetchone()
        assert row["chat_guid"] == f"iMessage;-;{melis}"


async def test_sync_once_resolves_phone_handle_as_kind_phone(
    tmp_db_path: Path, tmp_runtime: Path, chatdb_path: Path,
) -> None:
    """Cross-source identity: a phone-shaped iMessage handle should
    create an `identifiers` row with kind='phone', not 'imessage_handle'."""
    h = insert_handle(chatdb_path, identifier="+15559876543")
    chat = insert_chat(chatdb_path, guid="c1")
    insert_message(chatdb_path, guid="m1", text="x", handle_rowid=h,
                   chat_rowid=chat,
                   sent_at=datetime(2026, 5, 1, tzinfo=UTC))

    async with open_db(tmp_db_path) as db:
        storage = Storage(db, CASStore(tmp_runtime / "attachments"))
        account_id = await _seed_account(storage, "+15551234567")
        cfg = IMessagePluginConfig(accounts=[IMessageAccountConfig(
            identifier="+15551234567", owner="+15551234567",
            chat_db_path=chatdb_path,
        )])
        plugin = IMessagePlugin(
            config=cfg.model_dump(), storage=storage, secrets=Secrets({}),
        )
        await plugin.sync_once(account_id)

        async with db.execute(
            "SELECT kind FROM identifiers WHERE value=?",
            ("+15559876543",),
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["kind"] == "phone"


async def test_backfill_marks_accounts_backfilled_at(
    tmp_db_path: Path, tmp_runtime: Path, chatdb_path: Path,
) -> None:
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c1")
    insert_message(chatdb_path, guid="m1", text="x", handle_rowid=h,
                   chat_rowid=chat,
                   sent_at=datetime(2026, 5, 1, tzinfo=UTC))

    async with open_db(tmp_db_path) as db:
        storage = Storage(db, CASStore(tmp_runtime / "attachments"))
        account_id = await _seed_account(storage, "+15551234567")
        cfg = IMessagePluginConfig(accounts=[IMessageAccountConfig(
            identifier="+15551234567", owner="+15551234567",
            chat_db_path=chatdb_path,
        )])
        plugin = IMessagePlugin(
            config=cfg.model_dump(), storage=storage, secrets=Secrets({}),
        )
        await plugin.backfill(account_id)

        async with db.execute(
            "SELECT backfilled_at FROM accounts WHERE id=?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row["backfilled_at"] is not None
