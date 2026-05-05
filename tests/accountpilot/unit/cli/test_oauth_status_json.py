"""Tests for `accountpilot oauth status --json`."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

from click.testing import CliRunner

from accountpilot.core.cli.oauth_cmd import oauth_group


def test_oauth_status_json_empty(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        oauth_group,
        ["status", "--json", "--secrets-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "ok": True,
        "data": {"tokens": []},
        "error": None,
    }


def test_oauth_status_json_with_secrets(tmp_path: Path) -> None:
    secrets = tmp_path / "oauth"
    g = secrets / "google"
    g.mkdir(parents=True)
    (g / "42.json").write_text('{"refresh_token": "x"}')

    runner = CliRunner()
    result = runner.invoke(
        oauth_group, ["status", "--json", "--secrets-root", str(tmp_path)]
    )
    payload = json.loads(result.output)
    assert payload["ok"] is True
    tokens = payload["data"]["tokens"]
    assert len(tokens) == 1
    t = tokens[0]
    assert t["provider"] == "google"
    assert t["account_id"] == 42
    assert t["secret_path"].endswith("oauth/google/42.json")
    assert t["modified_at"] is not None
