from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from accountpilot.core.auth import Secrets

if TYPE_CHECKING:
    from pathlib import Path


def test_get_returns_literal_value() -> None:
    s = Secrets({"a": "literal"})
    assert s.get("a") == "literal"


def test_get_returns_none_for_missing_key() -> None:
    s = Secrets({})
    assert s.get("missing") is None


def test_get_with_default_returns_default() -> None:
    s = Secrets({})
    assert s.get("missing", "fallback") == "fallback"


def test_resolve_literal_passes_through() -> None:
    assert Secrets({}).resolve("plain-string") == "plain-string"


def test_resolve_password_cmd_runs_shell_and_returns_stripped_stdout() -> None:
    assert Secrets({}).resolve("password_cmd:echo hello") == "hello"


def test_resolve_password_cmd_strips_trailing_newline() -> None:
    assert Secrets({}).resolve("password_cmd:printf 'abc\\n'") == "abc"


def test_resolve_password_cmd_propagates_nonzero_exit() -> None:
    with pytest.raises(RuntimeError) as exc:
        Secrets({}).resolve("password_cmd:false")
    assert "exit" in str(exc.value).lower()


def test_secrets_resolve_oauth_google_uri_dispatches_to_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "google"
    secret_dir.mkdir(parents=True)
    (secret_dir / "5.json").write_text(
        '{"refresh_token":"rt","client_id":"ci",'
        '"client_secret":"cs","token_uri":"u"}'
    )

    s = Secrets({}, secrets_root=tmp_path)
    monkeypatch.setattr(
        s._google_handler,  # noqa: SLF001
        "_post_token_endpoint",
        lambda **_: {"access_token": "at-resolved", "expires_in": 3599},
    )
    assert s.resolve("oauth:google:5") == "at-resolved"


def test_secrets_resolve_oauth_microsoft_uri_dispatches_to_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "microsoft"
    secret_dir.mkdir(parents=True)
    (secret_dir / "7.json").write_text(
        '{"client_id":"ci",'
        '"authority":"https://login.microsoftonline.com/common",'
        '"scopes":["scope"],'
        '"refresh_token":"rt"}'
    )

    s = Secrets({}, secrets_root=tmp_path)
    monkeypatch.setattr(
        s._microsoft_handler,  # noqa: SLF001
        "_acquire_token",
        lambda **_: {"access_token": "at-ms-resolved", "expires_in": 3599},
    )
    assert s.resolve("oauth:microsoft:7") == "at-ms-resolved"
