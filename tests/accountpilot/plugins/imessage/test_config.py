from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from accountpilot.plugins.imessage.config import (
    IMessageAccountConfig,
    IMessagePluginConfig,
)


def test_account_minimum_fields() -> None:
    a = IMessageAccountConfig(
        identifier="+15551234567",
        owner="+15551234567",
    )
    assert a.identifier == "+15551234567"
    assert a.chat_db_path == Path.home() / "Library" / "Messages" / "chat.db"


def test_account_chat_db_path_override() -> None:
    a = IMessageAccountConfig(
        identifier="+15551234567",
        owner="+15551234567",
        chat_db_path=Path("/tmp/test-chat.db"),
    )
    assert a.chat_db_path == Path("/tmp/test-chat.db")


def test_account_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        IMessageAccountConfig(
            identifier="+15551234567",
            owner="+15551234567",
            something_unknown="oops",  # type: ignore[call-arg]
        )


def test_plugin_default_debounce_and_backfill_window() -> None:
    cfg = IMessagePluginConfig(accounts=[])
    assert cfg.debounce_seconds == 2.0
    assert cfg.backfill_chunk == 500
