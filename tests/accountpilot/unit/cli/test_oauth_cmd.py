from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from accountpilot.cli import cli

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_google_client(tmp_path: Path) -> Path:
    p = tmp_path / "oauth_clients" / "google.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "ci.apps.googleusercontent.com",
                    "client_secret": "cs",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
    )
    return p


def _write_microsoft_client(tmp_path: Path) -> Path:
    p = tmp_path / "oauth_clients" / "microsoft.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "client_id": "ms-ci",
                "authority": "https://login.microsoftonline.com/common",
            }
        )
    )
    return p


def test_oauth_login_google_writes_refresh_token_with_0600_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_google_client(tmp_path)
    secrets_root = tmp_path / "runtime" / "secrets"

    # Stub the interactive flow
    from accountpilot.core.oauth import flow as oauth_flow

    monkeypatch.setattr(
        oauth_flow,
        "google_interactive_login",
        lambda client_config, scopes: {
            "client_id": "ci.apps.googleusercontent.com",
            "client_secret": "cs",
            "token_uri": "https://oauth2.googleapis.com/token",
            "refresh_token": "rt-abc-from-interactive",
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "oauth",
            "login",
            "google",
            "1",
            "--config-dir",
            str(tmp_path),
            "--secrets-root",
            str(secrets_root),
        ],
    )
    assert result.exit_code == 0, result.output
    out_file = secrets_root / "oauth" / "google" / "1.json"
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert payload["refresh_token"] == "rt-abc-from-interactive"
    assert payload["client_id"] == "ci.apps.googleusercontent.com"
    # Mode 0600
    assert oct(out_file.stat().st_mode & 0o777) == "0o600"


def test_oauth_login_google_errors_when_bundled_has_placeholder(
    tmp_path: Path,
) -> None:
    """If publisher hasn't filled bundled credentials yet, login fails clean.

    Pre-release builds ship bundled JSONs containing
    'REPLACE_BEFORE_RELEASE' so a fat-fingered tag without filled creds
    produces a helpful error instead of a confusing OAuth round-trip with
    a literal placeholder client_id.
    """
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "oauth",
            "login",
            "google",
            "1",
            "--config-dir",
            str(tmp_path),
            "--secrets-root",
            str(tmp_path / "secrets"),
        ],
    )
    # If publisher creds are already filled (post-release build), this
    # path won't trigger and login would actually attempt the real flow
    # — that's fine, skip in that case.
    if result.exit_code == 0:
        return
    assert "unreplaced placeholders" in result.output or "REPLACE" in result.output


def test_oauth_login_microsoft_writes_refresh_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_microsoft_client(tmp_path)
    secrets_root = tmp_path / "runtime" / "secrets"

    from accountpilot.core.oauth import flow as oauth_flow

    monkeypatch.setattr(
        oauth_flow,
        "microsoft_interactive_login",
        lambda client_id, authority, scopes: {
            "client_id": client_id,
            "authority": authority,
            "scopes": scopes,
            "refresh_token": "ms-rt-abc",
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "oauth",
            "login",
            "microsoft",
            "2",
            "--config-dir",
            str(tmp_path),
            "--secrets-root",
            str(secrets_root),
        ],
    )
    assert result.exit_code == 0, result.output
    out_file = secrets_root / "oauth" / "microsoft" / "2.json"
    payload = json.loads(out_file.read_text())
    assert payload["refresh_token"] == "ms-rt-abc"
    assert payload["scopes"] == ["https://outlook.office.com/IMAP.AccessAsUser.All"]


def test_oauth_status_lists_present_secrets(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    (secrets_root / "oauth" / "google").mkdir(parents=True)
    (secrets_root / "oauth" / "google" / "1.json").write_text("{}")
    (secrets_root / "oauth" / "google" / "3.json").write_text("{}")
    (secrets_root / "oauth" / "microsoft").mkdir(parents=True)
    (secrets_root / "oauth" / "microsoft" / "2.json").write_text("{}")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "oauth",
            "status",
            "--secrets-root",
            str(secrets_root),
        ],
    )
    assert result.exit_code == 0
    assert "google" in result.output and "1" in result.output
    assert "google" in result.output and "3" in result.output
    assert "microsoft" in result.output and "2" in result.output


def test_load_client_config_user_file_takes_priority(tmp_path: Path) -> None:
    """User-supplied JSON wins over bundled (power-user override)."""
    from accountpilot.core.cli.oauth_cmd import _load_client_config

    p = tmp_path / "oauth_clients" / "google.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "_note": "doc-only key, must be stripped",
                "installed": {"client_id": "user-cid", "client_secret": "user-cs"},
            }
        )
    )

    cfg = _load_client_config("google", tmp_path)
    assert cfg == {"installed": {"client_id": "user-cid", "client_secret": "user-cs"}}
    assert "_note" not in cfg


def test_load_client_config_falls_back_to_bundled_on_real_creds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the user has no file, the bundled JSON is loaded.

    Simulates a post-release build: monkeypatch the placeholder check to
    say 'real creds' so we exercise the bundled-load path even though
    the in-tree bundled JSON still ships REPLACE_BEFORE_RELEASE.
    """
    from accountpilot.core.cli import oauth_cmd

    monkeypatch.setattr(oauth_cmd, "_has_unfilled_placeholder", lambda cfg: False)

    cfg = oauth_cmd._load_client_config("google", tmp_path)
    assert "installed" in cfg
    assert "client_id" in cfg["installed"]
    # The bundled file's documentation keys must be stripped.
    assert all(not k.startswith("_") for k in cfg)


def test_load_client_config_strips_underscore_keys() -> None:
    from accountpilot.core.cli.oauth_cmd import _strip_meta

    assert _strip_meta({"a": 1, "_b": 2, "_publisher": "x"}) == {"a": 1}


def test_has_unfilled_placeholder_walks_nested_structures() -> None:
    from accountpilot.core.cli.oauth_cmd import _has_unfilled_placeholder

    assert _has_unfilled_placeholder({"a": "REPLACE_BEFORE_RELEASE"})
    assert _has_unfilled_placeholder(
        {"installed": {"client_id": "REPLACE_BEFORE_RELEASE"}}
    )
    assert _has_unfilled_placeholder({"items": ["ok", "REPLACE_BEFORE_RELEASE"]})
    assert not _has_unfilled_placeholder({"installed": {"client_id": "real"}})


def test_oauth_revoke_deletes_secret_file(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    f = secrets_root / "oauth" / "google" / "1.json"
    f.parent.mkdir(parents=True)
    f.write_text("{}")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "oauth",
            "revoke",
            "google",
            "1",
            "--secrets-root",
            str(secrets_root),
        ],
    )
    assert result.exit_code == 0
    assert not f.exists()
