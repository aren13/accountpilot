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
    p.write_text(json.dumps({
        "installed": {
            "client_id": "ci.apps.googleusercontent.com",
            "client_secret": "cs",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }))
    return p


def _write_microsoft_client(tmp_path: Path) -> Path:
    p = tmp_path / "oauth_clients" / "microsoft.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "client_id": "ms-ci",
        "authority": "https://login.microsoftonline.com/common",
    }))
    return p


def test_oauth_login_google_writes_refresh_token_with_0600_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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
    result = runner.invoke(cli, [
        "oauth", "login", "google", "1",
        "--config-dir", str(tmp_path),
        "--secrets-root", str(secrets_root),
    ])
    assert result.exit_code == 0, result.output
    out_file = secrets_root / "oauth" / "google" / "1.json"
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert payload["refresh_token"] == "rt-abc-from-interactive"
    assert payload["client_id"] == "ci.apps.googleusercontent.com"
    # Mode 0600
    assert oct(out_file.stat().st_mode & 0o777) == "0o600"


def test_oauth_login_google_errors_when_client_json_missing(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "oauth", "login", "google", "1",
        "--config-dir", str(tmp_path),
        "--secrets-root", str(tmp_path / "secrets"),
    ])
    assert result.exit_code != 0
    assert "oauth_clients/google.json" in result.output


def test_oauth_login_microsoft_writes_refresh_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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
    result = runner.invoke(cli, [
        "oauth", "login", "microsoft", "2",
        "--config-dir", str(tmp_path),
        "--secrets-root", str(secrets_root),
    ])
    assert result.exit_code == 0, result.output
    out_file = secrets_root / "oauth" / "microsoft" / "2.json"
    payload = json.loads(out_file.read_text())
    assert payload["refresh_token"] == "ms-rt-abc"
    assert payload["scopes"] == [
        "https://outlook.office.com/IMAP.AccessAsUser.All"
    ]


def test_oauth_status_lists_present_secrets(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    (secrets_root / "oauth" / "google").mkdir(parents=True)
    (secrets_root / "oauth" / "google" / "1.json").write_text("{}")
    (secrets_root / "oauth" / "google" / "3.json").write_text("{}")
    (secrets_root / "oauth" / "microsoft").mkdir(parents=True)
    (secrets_root / "oauth" / "microsoft" / "2.json").write_text("{}")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "oauth", "status", "--secrets-root", str(secrets_root),
    ])
    assert result.exit_code == 0
    assert "google" in result.output and "1" in result.output
    assert "google" in result.output and "3" in result.output
    assert "microsoft" in result.output and "2" in result.output


def test_oauth_revoke_deletes_secret_file(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    f = secrets_root / "oauth" / "google" / "1.json"
    f.parent.mkdir(parents=True)
    f.write_text("{}")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "oauth", "revoke", "google", "1",
        "--secrets-root", str(secrets_root),
    ])
    assert result.exit_code == 0
    assert not f.exists()
