"""Tests for `accountpilot oauth login {google,microsoft} --json`.

The actual OAuth flow opens a browser and runs a local server; we mock
``oauth_flow.google_interactive_login`` so the test is hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from accountpilot.core.cli.oauth_cmd import oauth_group


def test_login_google_json_emits_envelope(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    config_dir = tmp_path / "config"

    fake_payload = {
        "client_id": "x", "client_secret": "y",
        "refresh_token": "rt", "token_uri": "https://oauth2.googleapis.com/token",
    }

    with patch(
        "accountpilot.core.cli.oauth_cmd.oauth_flow.google_interactive_login",
        return_value=fake_payload,
    ), patch(
        "accountpilot.core.cli.oauth_cmd._load_client_config",
        return_value={"client_id": "x", "client_secret": "y"},
    ):
        runner = CliRunner()
        result = runner.invoke(
            oauth_group,
            [
                "login", "google", "42", "--json",
                "--config-dir", str(config_dir),
                "--secrets-root", str(secrets_root),
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["account_id"] == 42
    assert payload["data"]["provider"] == "google"
    assert payload["data"]["secret_path"].endswith("secrets/oauth/google/42.json")

    # File actually written
    secret_file = secrets_root / "oauth" / "google" / "42.json"
    assert secret_file.exists()
    assert json.loads(secret_file.read_text())["refresh_token"] == "rt"


def test_login_microsoft_json(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    config_dir = tmp_path / "config"

    fake_payload = {
        "access_token": "at", "refresh_token": "rt",
        "client_id": "abc", "authority": "https://login.microsoftonline.com/common",
    }

    with patch(
        "accountpilot.core.cli.oauth_cmd.oauth_flow.microsoft_interactive_login",
        return_value=fake_payload,
    ), patch(
        "accountpilot.core.cli.oauth_cmd._load_client_config",
        return_value={"client_id": "abc", "authority": "https://login.microsoftonline.com/common"},
    ):
        runner = CliRunner()
        result = runner.invoke(
            oauth_group,
            [
                "login", "microsoft", "7", "--json",
                "--config-dir", str(config_dir),
                "--secrets-root", str(secrets_root),
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["account_id"] == 7
    assert payload["data"]["provider"] == "microsoft"
