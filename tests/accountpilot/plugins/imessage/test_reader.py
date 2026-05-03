from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from accountpilot.plugins.imessage.reader import ChatDbReader

if TYPE_CHECKING:
    from pathlib import Path
from tests.accountpilot.plugins.imessage.conftest import (
    add_chat_participant,
    insert_chat,
    insert_handle,
    insert_message,
    to_apple_ns,
)
from tests.accountpilot.plugins.imessage.test_attributed_body import (
    build_synthetic_attributed_body,
)


def test_read_messages_yields_imessage_models(chatdb_path: Path) -> None:
    melis = insert_handle(chatdb_path, identifier="+905052490140")
    chat = insert_chat(chatdb_path, guid="iMessage;-;+905052490140",
                       identifier="+905052490140")
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=melis)
    insert_message(
        chatdb_path, guid="GUID-1", text="hi from melis",
        handle_rowid=melis, chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        is_from_me=False,
    )

    reader = ChatDbReader(chatdb_path, account_id=1)
    messages = list(reader.read_messages())

    assert len(messages) == 1
    msg = messages[0]
    assert msg.account_id == 1
    assert msg.external_id == "GUID-1"
    assert msg.body_text == "hi from melis"
    assert msg.sender_handle == "+905052490140"
    assert msg.chat_guid == "iMessage;-;+905052490140"
    assert msg.direction == "inbound"
    assert msg.service == "iMessage"
    assert msg.is_read is True
    assert msg.sent_at == datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def test_read_messages_outbound_marker(chatdb_path: Path) -> None:
    me = insert_handle(chatdb_path, identifier="+15551234567")
    chat = insert_chat(chatdb_path, guid="iMessage;-;+15551234567")
    insert_message(
        chatdb_path, guid="GUID-OUT", text="reply",
        handle_rowid=me, chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, 12, 5, tzinfo=UTC),
        is_from_me=True,
    )

    reader = ChatDbReader(chatdb_path, account_id=1)
    messages = list(reader.read_messages())

    assert messages[0].direction == "outbound"


def test_read_messages_since_filter(chatdb_path: Path) -> None:
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c1")
    t1 = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 5, 1, 11, 0, tzinfo=UTC)
    t3 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    insert_message(chatdb_path, guid="m1", text="a", handle_rowid=h,
                   chat_rowid=chat, sent_at=t1)
    insert_message(chatdb_path, guid="m2", text="b", handle_rowid=h,
                   chat_rowid=chat, sent_at=t2)
    insert_message(chatdb_path, guid="m3", text="c", handle_rowid=h,
                   chat_rowid=chat, sent_at=t3)

    reader = ChatDbReader(chatdb_path, account_id=1)
    msgs = list(reader.read_messages(since_ns=to_apple_ns(t1)))

    # since_ns=t1 means strict >, so m2 and m3 only.
    guids = {m.external_id for m in msgs}
    assert guids == {"m2", "m3"}


def test_read_messages_group_chat_lists_participants(
    chatdb_path: Path,
) -> None:
    a = insert_handle(chatdb_path, identifier="+1")
    b = insert_handle(chatdb_path, identifier="+2")
    c = insert_handle(chatdb_path, identifier="+3")
    chat = insert_chat(chatdb_path, guid="iMessage;+;chat-grp")
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=a)
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=b)
    add_chat_participant(chatdb_path, chat_rowid=chat, handle_rowid=c)
    insert_message(chatdb_path, guid="grp-1", text="hello group",
                   handle_rowid=a, chat_rowid=chat,
                   sent_at=datetime(2026, 5, 1, tzinfo=UTC))

    reader = ChatDbReader(chatdb_path, account_id=1)
    msg = list(reader.read_messages())[0]

    assert sorted(msg.participants) == ["+1", "+2", "+3"]


def test_read_messages_null_text_yields_empty_body(chatdb_path: Path) -> None:
    """When chat.db's text is NULL (rich-content message), body_text is empty
    rather than the literal string 'None'."""
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c")
    insert_message(chatdb_path, guid="m1", text=None, handle_rowid=h,
                   chat_rowid=chat,
                   sent_at=datetime(2026, 5, 1, tzinfo=UTC))

    reader = ChatDbReader(chatdb_path, account_id=1)
    msg = list(reader.read_messages())[0]

    assert msg.body_text == ""


def test_read_messages_falls_back_to_attributed_body(
    chatdb_path: Path,
) -> None:
    """text=NULL + attributedBody present → body_text decoded from blob."""
    h = insert_handle(chatdb_path, identifier="+1")
    chat = insert_chat(chatdb_path, guid="c")
    insert_message(
        chatdb_path,
        guid="m-attr",
        text=None,
        attributed_body=build_synthetic_attributed_body("rich body text"),
        handle_rowid=h,
        chat_rowid=chat,
        sent_at=datetime(2026, 5, 1, tzinfo=UTC),
    )

    reader = ChatDbReader(chatdb_path, account_id=1)
    msg = list(reader.read_messages())[0]

    assert msg.body_text == "rich body text"
