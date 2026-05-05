"""Tests for stable exit codes across CLI error paths."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest
from click.testing import CliRunner

from accountpilot.core.cli.accounts_cmds import accounts_group
from accountpilot.core.cli.messages_cmds import attachments_group, messages_group
from accountpilot.core.db.connection import open_db


@pytest.fixture
async def empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    async with open_db(db):
        pass
    return db


def test_messages_get_unknown_exits_65(empty_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        messages_group,
        ["get", "999", "--json", "--db-path", str(empty_db)],
    )
    assert result.exit_code == 65, result.output


def test_attachments_path_unknown_exits_65(empty_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        attachments_group,
        ["path", "999", "--json", "--db-path", str(empty_db)],
    )
    assert result.exit_code == 65, result.output


def test_accounts_remove_unknown_exits_65(empty_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        accounts_group,
        ["remove", "999", "--json", "--db-path", str(empty_db)],
    )
    assert result.exit_code == 65, result.output


def test_accounts_add_duplicate_exits_65(empty_db: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--db-path",
            str(empty_db),
        ],
    )
    result = runner.invoke(
        accounts_group,
        [
            "add",
            "--json",
            "--provider",
            "gmail",
            "--identifier",
            "ada@example.com",
            "--owner-name",
            "Ada",
            "--db-path",
            str(empty_db),
        ],
    )
    assert result.exit_code == 65, result.output
