from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from accountpilot.core.oauth.google import GoogleOAuthHandler

if TYPE_CHECKING:
    from pathlib import Path


def test_google_oauth_handler_returns_fresh_access_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "google"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "refresh_token": "rt-abc",
        "client_id": "ci",
        "client_secret": "cs",
        "token_uri": "https://oauth2.googleapis.com/token",
    }))
    handler = GoogleOAuthHandler(tmp_path)
    monkeypatch.setattr(
        handler,
        "_post_token_endpoint",
        lambda **_: {"access_token": "at-fresh", "expires_in": 3599},
    )
    assert handler.access_token(account_id=1) == "at-fresh"


def test_google_oauth_handler_caches_token_until_near_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "google"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "refresh_token": "rt", "client_id": "ci",
        "client_secret": "cs", "token_uri": "u",
    }))
    handler = GoogleOAuthHandler(tmp_path)

    calls = {"n": 0}

    def fake_post(**_: str) -> dict:
        calls["n"] += 1
        return {"access_token": f"tok-{calls['n']}", "expires_in": 3599}

    monkeypatch.setattr(handler, "_post_token_endpoint", fake_post)
    a = handler.access_token(account_id=1)
    b = handler.access_token(account_id=1)
    assert a == b == "tok-1"
    assert calls["n"] == 1


def test_google_oauth_handler_refreshes_when_within_60s_of_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "oauth" / "google"
    secret_dir.mkdir(parents=True)
    (secret_dir / "1.json").write_text(json.dumps({
        "refresh_token": "rt", "client_id": "ci",
        "client_secret": "cs", "token_uri": "u",
    }))
    handler = GoogleOAuthHandler(tmp_path)

    calls = {"n": 0}

    def fake_post(**_: str) -> dict:
        calls["n"] += 1
        # First call → near-expired (30s); subsequent → fresh
        return {
            "access_token": f"tok-{calls['n']}",
            "expires_in": 30 if calls["n"] == 1 else 3599,
        }

    monkeypatch.setattr(handler, "_post_token_endpoint", fake_post)
    handler.access_token(account_id=1)  # first → tok-1, expires_in=30
    second = handler.access_token(account_id=1)  # within 60s → refresh
    assert second == "tok-2"
    assert calls["n"] == 2


def test_google_oauth_handler_raises_on_missing_secret_file(
    tmp_path: Path,
) -> None:
    handler = GoogleOAuthHandler(tmp_path)
    with pytest.raises(FileNotFoundError):
        handler.access_token(account_id=99)
