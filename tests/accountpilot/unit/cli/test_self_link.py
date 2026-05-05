"""Tests for `accountpilot self link`."""

from __future__ import annotations

import json
import os
from pathlib import Path  # noqa: TC003

from click.testing import CliRunner

from accountpilot.core.cli.self_cmd import self_group


def test_self_link_creates_symlink(tmp_path: Path) -> None:
    source = tmp_path / "src" / "accountpilot"
    source.parent.mkdir()
    source.write_text("#!/bin/bash\necho hello\n")
    source.chmod(0o755)

    target = tmp_path / "bin" / "accountpilot"
    target.parent.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        self_group,
        ["link", "--json", "--source", str(source), "--target", str(target)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["created"] is True
    assert target.is_symlink()
    assert os.readlink(target) == str(source)


def test_self_link_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "src" / "accountpilot"
    source.parent.mkdir()
    source.write_text("#!/bin/bash\necho hello\n")
    source.chmod(0o755)

    target = tmp_path / "bin" / "accountpilot"
    target.parent.mkdir()
    target.symlink_to(source)

    runner = CliRunner()
    result = runner.invoke(
        self_group,
        ["link", "--json", "--source", str(source), "--target", str(target)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["created"] is False  # already there


def test_self_link_target_exists_as_file(tmp_path: Path) -> None:
    source = tmp_path / "accountpilot"
    source.write_text("#!/bin/bash\necho src\n")
    source.chmod(0o755)
    target = tmp_path / "bin" / "accountpilot"
    target.parent.mkdir()
    target.write_text("not a symlink")

    runner = CliRunner()
    result = runner.invoke(
        self_group,
        ["link", "--json", "--source", str(source), "--target", str(target)],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TARGET_EXISTS"
    assert result.exit_code == 65  # exits with 65 per Task 3
