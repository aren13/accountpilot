from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from accountpilot.core.oauth.microsoft import MicrosoftOAuthHandler

if TYPE_CHECKING:
    from pathlib import Path


def test_microsoft_oauth_handler_returns_fresh_access_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "microsoft"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "client_id": "ci",
        "authority": "https://login.microsoftonline.com/common",
        "scopes": ["https://outlook.office.com/IMAP.AccessAsUser.All"],
        "refresh_token": "rt-abc",
    }))
    handler = MicrosoftOAuthHandler(tmp_path)
    monkeypatch.setattr(
        handler,
        "_acquire_token",
        lambda **_: {"access_token": "at-fresh", "expires_in": 3599},
    )
    assert handler.access_token(account_id=1) == "at-fresh"


def test_microsoft_oauth_handler_caches_token_until_near_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "microsoft"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "client_id": "ci",
        "authority": "https://login.microsoftonline.com/common",
        "scopes": ["scope"],
        "refresh_token": "rt",
    }))
    handler = MicrosoftOAuthHandler(tmp_path)

    calls = {"n": 0}

    def fake_acquire(**_: object) -> dict:
        calls["n"] += 1
        return {"access_token": f"tok-{calls['n']}", "expires_in": 3599}

    monkeypatch.setattr(handler, "_acquire_token", fake_acquire)
    a = handler.access_token(account_id=1)
    b = handler.access_token(account_id=1)
    assert a == b == "tok-1"
    assert calls["n"] == 1


def test_microsoft_oauth_handler_refreshes_when_within_60s_of_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "microsoft"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "client_id": "ci",
        "authority": "https://login.microsoftonline.com/common",
        "scopes": ["scope"],
        "refresh_token": "rt",
    }))
    handler = MicrosoftOAuthHandler(tmp_path)

    calls = {"n": 0}

    def fake_acquire(**_: object) -> dict:
        calls["n"] += 1
        # First call → near-expired (30s); subsequent → fresh
        return {
            "access_token": f"tok-{calls['n']}",
            "expires_in": 30 if calls["n"] == 1 else 3599,
        }

    monkeypatch.setattr(handler, "_acquire_token", fake_acquire)
    handler.access_token(account_id=1)  # first → tok-1, expires_in=30
    second = handler.access_token(account_id=1)  # within 60s → refresh
    assert second == "tok-2"
    assert calls["n"] == 2


def test_microsoft_oauth_handler_raises_on_missing_secret_file(
    tmp_path: Path,
) -> None:
    handler = MicrosoftOAuthHandler(tmp_path)
    with pytest.raises(FileNotFoundError):
        handler.access_token(account_id=99)


def test_microsoft_oauth_handler_raises_on_msal_error_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """msal returns {error, error_description} on failure (no access_token).

    The handler should raise instead of silently returning None.
    """
    secret_dir = tmp_path / "oauth" / "microsoft"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "client_id": "ci",
        "authority": "https://login.microsoftonline.com/common",
        "scopes": ["scope"],
        "refresh_token": "rt-revoked",
    }))
    handler = MicrosoftOAuthHandler(tmp_path)
    monkeypatch.setattr(
        handler,
        "_acquire_token",
        lambda **_: {
            "error": "invalid_grant",
            "error_description": "rt revoked",
        },
    )
    with pytest.raises(RuntimeError, match="invalid_grant"):
        handler.access_token(account_id=1)
