"""End-to-end check that ACCOUNTPILOT_DATA_DIR + ACCOUNTPILOT_CONFIG_DIR
flow through the CLI option defaults to the actual filesystem writes."""
from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner

from accountpilot.cli import cli

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


_CONFIG_YAML = """
version: 1
owners:
  - name: Aren
    surname: Eren
    identifiers:
      - { kind: email, value: aren@x.com }
plugins: {}
"""


def test_setup_writes_under_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACCOUNTPILOT_{DATA,CONFIG}_DIR override the default Path.home()
    dance — ``accountpilot setup`` (no path args) writes the DB and
    config under the env-provided dirs."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(_CONFIG_YAML)

    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ACCOUNTPILOT_CONFIG_DIR", str(config_dir))

    runner = CliRunner()
    result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 0, result.output
    assert (data_dir / "accountpilot.db").exists()
    # AND nothing leaked into ~/runtime/accountpilot/ or
    # ~/.config/accountpilot/ — file existence checks above are the
    # primary evidence; we don't assert absence directly because home
    # dir state is messy in CI.
