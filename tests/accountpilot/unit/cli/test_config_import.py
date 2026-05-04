"""Tests for `accountpilot config import`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import asyncio
import json
from textwrap import dedent

from click.testing import CliRunner

from accountpilot.core.cli.config_cmd import config_group
from accountpilot.core.db.connection import open_db


def _seed_db(db: Path) -> None:
    """Open the DB once so migrations run; no rows added."""

    async def _run() -> None:
        async with open_db(db):
            pass

    asyncio.run(_run())


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        dedent(
            """\
        version: 1
        owners:
          - name: Ada
            surname: Lovelace
            identifiers:
              - kind: email
                value: ada@example.com
        plugins:
          mail:
            enabled: true
            accounts:
              - identifier: ada@example.com
                owner: ada@example.com
                provider: gmail
        """
        )
    )


def test_import_applies_yaml_then_renames_it(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    config = tmp_path / "config.yaml"
    _seed_db(db)
    _write_minimal_config(config)

    runner = CliRunner()
    result = runner.invoke(
        config_group,
        ["import", "--config", str(config), "--db-path", str(db), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["accounts_imported"] == 1
    assert payload["data"]["renamed_to"].endswith("config.yaml.imported")

    # YAML moved out of the way
    assert not config.exists()
    assert (tmp_path / "config.yaml.imported").exists()

    # DB has the row
    async def _check() -> int:
        async with (
            open_db(db) as conn,
            conn.execute("SELECT COUNT(*) AS n FROM accounts") as cur,
        ):
            row = await cur.fetchone()
        return int(row["n"])

    assert asyncio.run(_check()) == 1


def test_import_missing_yaml_is_noop_success(tmp_path: Path) -> None:
    """If config.yaml is absent, return a "nothing to do" success (the Swift
    caller invokes this unconditionally on first launch)."""
    db = tmp_path / "test.db"
    _seed_db(db)
    runner = CliRunner()
    result = runner.invoke(
        config_group,
        [
            "import",
            "--json",
            "--config",
            str(tmp_path / "config.yaml"),  # does not exist
            "--db-path",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "ok": True,
        "data": {"accounts_imported": 0, "renamed_to": None, "noop": True},
        "error": None,
    }


def test_import_already_imported_is_noop(tmp_path: Path) -> None:
    """Re-running import after a successful import should do nothing."""
    db = tmp_path / "test.db"
    config = tmp_path / "config.yaml"
    _seed_db(db)
    _write_minimal_config(config)

    runner = CliRunner()
    runner.invoke(
        config_group,
        ["import", "--config", str(config), "--db-path", str(db), "--json"],
    )
    # Second invocation: config.yaml is gone (renamed); should noop.
    result2 = runner.invoke(
        config_group,
        ["import", "--config", str(config), "--db-path", str(db), "--json"],
    )
    payload = json.loads(result2.output)
    assert payload["data"]["noop"] is True
    assert payload["data"]["accounts_imported"] == 0
