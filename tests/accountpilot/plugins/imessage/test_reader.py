"""Unit tests for the helper-driven ChatDbReader.

The helper binary runs as a separate signed process in production (see
helpers/fda-helper/). These tests exercise the dict→IMessageMessage
conversion and the iter_records subprocess wrapper without spawning the
binary, by constructing JSON-Lines-shaped dicts directly and by
monkeypatching helper_client.iter_records.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest

from accountpilot.plugins.imessage import helper_client, reader
from accountpilot.plugins.imessage.helper_client import (
    APPLE_EPOCH,
    HelperDataError,
    record_to_imessage,
)
from tests.accountpilot.plugins.imessage.test_attributed_body import (
    build_synthetic_attributed_body,
)


def _ns(dt: datetime) -> int:
    delta = dt - APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "v": 1,
        "type": "message",
        "guid": "GUID-1",
        "text": "hello",
        "attributed_body_b64": None,
        "is_from_me": False,
        "is_read": True,
        "date_ns": _ns(datetime(2026, 5, 1, 12, 0, tzinfo=UTC)),
        "date_read_ns": None,
        "service": "iMessage",
        "sender_handle": "+905052490140",
        "chat_guid": "iMessage;-;+905052490140",
        "participants": ["+905052490140"],
        "attachments": [],
    }
    base.update(overrides)
    return base


# ─── record_to_imessage: pure conversion ─────────────────────────────


def test_record_to_imessage_minimal_inbound() -> None:
    rec = _record()
    msg = record_to_imessage(rec, account_id=7)
    assert msg.account_id == 7
    assert msg.external_id == "GUID-1"
    assert msg.body_text == "hello"
    assert msg.sender_handle == "+905052490140"
    assert msg.chat_guid == "iMessage;-;+905052490140"
    assert msg.direction == "inbound"
    assert msg.service == "iMessage"
    assert msg.is_read is True
    assert msg.date_read is None
    assert msg.sent_at == datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def test_record_to_imessage_outbound_marker() -> None:
    msg = record_to_imessage(_record(is_from_me=True), account_id=1)
    assert msg.direction == "outbound"


def test_record_to_imessage_sms_normalisation() -> None:
    msg = record_to_imessage(_record(service="SMS"), account_id=1)
    assert msg.service == "SMS"


def test_record_to_imessage_rcs_falls_back_to_imessage() -> None:
    """RCS rides the iMessage transport in Apple's schema."""
    msg = record_to_imessage(_record(service="RCS"), account_id=1)
    assert msg.service == "iMessage"


def test_record_to_imessage_date_read() -> None:
    sent = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    read = datetime(2026, 5, 1, 12, 1, tzinfo=UTC)
    msg = record_to_imessage(
        _record(date_ns=_ns(sent), date_read_ns=_ns(read)),
        account_id=1,
    )
    assert msg.date_read == read


def test_record_to_imessage_attachment_decode() -> None:
    rec = _record(
        attachments=[
            {
                "filename": "pic.jpg",
                "mime_type": "image/jpeg",
                "content_b64": base64.b64encode(b"\xff\xd8\xffSAMPLE").decode(),
            },
            {
                "filename": "no-mime.bin",
                "mime_type": None,
                "content_b64": base64.b64encode(b"data").decode(),
            },
        ]
    )
    msg = record_to_imessage(rec, account_id=1)
    assert len(msg.attachments) == 2
    assert msg.attachments[0].filename == "pic.jpg"
    assert msg.attachments[0].mime_type == "image/jpeg"
    assert msg.attachments[0].content == b"\xff\xd8\xffSAMPLE"
    assert msg.attachments[1].mime_type is None


def test_record_to_imessage_attributed_body_fallback() -> None:
    """When text is null and attributedBody is present, decode via
    pytypedstream — same path as the legacy SQL reader."""
    blob = build_synthetic_attributed_body("rich body")
    rec = _record(text=None, attributed_body_b64=base64.b64encode(blob).decode())
    msg = record_to_imessage(rec, account_id=1)
    assert msg.body_text == "rich body"


def test_record_to_imessage_rejects_wrong_type() -> None:
    with pytest.raises(HelperDataError):
        record_to_imessage(_record(type="error"), account_id=1)


# ─── ChatDbReader: integration with monkeypatched iter_records ───────


def test_chat_db_reader_yields_imessage_models(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_records = [
        _record(
            guid="m1", text="first", date_ns=_ns(datetime(2026, 5, 1, 10, tzinfo=UTC))
        ),
        _record(
            guid="m2", text="second", date_ns=_ns(datetime(2026, 5, 1, 11, tzinfo=UTC))
        ),
    ]

    def fake_iter_records(**kwargs: object) -> object:
        # Capture call-shape to assert the reader passes through args.
        captured.update(kwargs)
        return iter(fake_records)

    captured: dict[str, object] = {}
    monkeypatch.setattr(helper_client, "iter_records", fake_iter_records)
    monkeypatch.setattr(reader, "iter_records", fake_iter_records)

    rdr = reader.ChatDbReader(chat_db_path=None, account_id=42)
    msgs = list(rdr.read_messages(since_ns=12345))

    assert [m.external_id for m in msgs] == ["m1", "m2"]
    assert [m.body_text for m in msgs] == ["first", "second"]
    assert all(m.account_id == 42 for m in msgs)
    assert captured["since_ns"] == 12345
    assert captured["chat_db_path"] is None


def test_chat_db_reader_passes_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> object:
        seen.update(kwargs)
        return iter([])

    monkeypatch.setattr(reader, "iter_records", fake)
    rdr = reader.ChatDbReader(chat_db_path="/tmp/synthetic.db", account_id=1)
    list(rdr.read_messages())
    assert str(seen["chat_db_path"]) == "/tmp/synthetic.db"


def test_chat_db_reader_since_ns_default_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> object:
        seen.update(kwargs)
        return iter([])

    monkeypatch.setattr(reader, "iter_records", fake)
    rdr = reader.ChatDbReader(chat_db_path=None, account_id=1)
    list(rdr.read_messages())
    assert seen["since_ns"] is None


# ─── Apple ns helpers ────────────────────────────────────────────────


def test_apple_ns_round_trip() -> None:
    dt = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    ns = int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)
    assert helper_client.apple_ns_to_datetime(ns) == dt


def test_apple_ns_to_datetime_micros_resolution() -> None:
    dt = datetime(2026, 5, 1, 12, 0, 0, 500_000, tzinfo=UTC)
    ns = int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)
    assert helper_client.apple_ns_to_datetime(ns) - dt < timedelta(microseconds=1)
