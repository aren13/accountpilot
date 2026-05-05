"""Tests for `accountpilot completion <shell>`."""

from __future__ import annotations

from click.testing import CliRunner

from accountpilot.core.cli.completion_cmd import completion_cmd


def test_completion_bash_emits_script() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_cmd, ["bash"])
    assert result.exit_code == 0, result.output
    assert "_accountpilot_completion" in result.output


def test_completion_zsh_emits_script() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_cmd, ["zsh"])
    assert result.exit_code == 0, result.output
    assert "_accountpilot_completion" in result.output


def test_completion_invalid_shell_exits_2() -> None:
    runner = CliRunner()
    # 'csh' is not a Click-supported shell; exit code 2 (Click usage error)
    result = runner.invoke(completion_cmd, ["csh"])
    assert result.exit_code == 2, result.output
