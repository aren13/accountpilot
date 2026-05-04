from __future__ import annotations

import platform
import subprocess
from typing import TYPE_CHECKING

from click.testing import CliRunner

from accountpilot.cli import cli

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_service_install_dry_run_renders_launchd_plist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run prints the rendered plist to stdout without touching
    LaunchAgents or running launchctl."""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    fake_bin = tmp_path / "accountpilot"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)

    def _shouldnt_call(*a: object, **kw: object) -> None:
        raise AssertionError("dry-run should not call subprocess.run")

    monkeypatch.setattr(subprocess, "run", _shouldnt_call)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "service",
            "install",
            "mail",
            "--dry-run",
            "--bin",
            str(fake_bin),
        ],
    )
    assert result.exit_code == 0, result.output
    out = result.output
    assert "<key>Label</key>" in out
    assert "<string>com.accountpilot.mail.daemon</string>" in out
    assert f"<string>{fake_bin.resolve()}</string>" in out
    assert "<string>mail</string>" in out
    assert "<key>RunAtLoad</key>" in out
    assert "<key>KeepAlive</key>" in out


def test_service_install_writes_plist_and_bootstraps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real install path writes the plist into the LaunchAgents dir and
    calls launchctl bootstrap + enable + kickstart."""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    fake_bin = tmp_path / "accountpilot"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    fake_la = tmp_path / "LaunchAgents"
    monkeypatch.setattr(
        "accountpilot.core.cli.service_cmd._LAUNCHAGENTS",
        fake_la,
    )
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ACCOUNTPILOT_LOG_DIR", str(tmp_path / "logs"))

    calls: list[list[str]] = []

    def _capture(args: list[str], **kw: object) -> object:
        calls.append(args)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(subprocess, "run", _capture)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["service", "install", "imessage", "--bin", str(fake_bin)]
    )
    assert result.exit_code == 0, result.output
    plist = fake_la / "com.accountpilot.imessage.daemon.plist"
    assert plist.exists()
    content = plist.read_text()
    assert "com.accountpilot.imessage.daemon" in content

    # Verify the launchctl call sequence: bootout, bootstrap, enable, kickstart
    verbs = [c[1] for c in calls if c[0] == "launchctl"]
    assert verbs == ["bootout", "bootstrap", "enable", "kickstart"]


def test_resolve_accountpilot_bin_prefers_sys_executable_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolver must default to the script next to sys.executable.

    This is the core fix: PATH-based lookup picks an arbitrary install
    when the user has multiple Pythons (anaconda + brew + system). The
    daemon must run under the SAME install that registered it.
    """
    from accountpilot.core.cli.service_cmd import _resolve_accountpilot_bin

    # Fake "interpreter dir" containing a fake accountpilot script.
    interp_dir = tmp_path / "interp"
    interp_dir.mkdir()
    fake_python = interp_dir / "python"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    fake_script = interp_dir / "accountpilot"
    fake_script.write_text("#!/bin/sh\n")
    fake_script.chmod(0o755)

    # And a *different* binary on PATH that we must NOT pick.
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other_bin = other_dir / "accountpilot"
    other_bin.write_text("#!/bin/sh\n")
    other_bin.chmod(0o755)

    monkeypatch.setattr("sys.executable", str(fake_python))
    monkeypatch.setattr("shutil.which", lambda _: str(other_bin))

    resolved = _resolve_accountpilot_bin(None)
    assert resolved == str(fake_script), (
        f"resolver must prefer sys.executable's directory, got {resolved}"
    )


def test_resolve_accountpilot_bin_falls_back_to_path_when_no_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If no script lives next to the interpreter, fall back to PATH."""
    from accountpilot.core.cli.service_cmd import _resolve_accountpilot_bin

    interp_dir = tmp_path / "interp"
    interp_dir.mkdir()
    fake_python = interp_dir / "python"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    # NO accountpilot script next to it.

    fallback = tmp_path / "fallback" / "accountpilot"
    fallback.parent.mkdir()
    fallback.write_text("#!/bin/sh\n")
    fallback.chmod(0o755)

    monkeypatch.setattr("sys.executable", str(fake_python))
    monkeypatch.setattr("shutil.which", lambda _: str(fallback))

    resolved = _resolve_accountpilot_bin(None)
    assert resolved == str(fallback)


def test_resolve_accountpilot_bin_explicit_override_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--bin always wins, even when sys.executable's dir has a script."""
    from accountpilot.core.cli.service_cmd import _resolve_accountpilot_bin

    interp_dir = tmp_path / "interp"
    interp_dir.mkdir()
    fake_python = interp_dir / "python"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    sibling = interp_dir / "accountpilot"
    sibling.write_text("#!/bin/sh\n")
    sibling.chmod(0o755)

    override = tmp_path / "override" / "accountpilot"
    override.parent.mkdir()
    override.write_text("#!/bin/sh\n")
    override.chmod(0o755)

    monkeypatch.setattr("sys.executable", str(fake_python))

    resolved = _resolve_accountpilot_bin(override)
    assert resolved == str(override.resolve())


def test_service_install_errors_on_truly_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Now that Linux is supported, only Windows / etc. should raise."""
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    runner = CliRunner()
    result = runner.invoke(cli, ["service", "install", "mail"])
    assert result.exit_code != 0
    assert "unsupported platform" in result.output.lower()


def test_service_uninstall_removes_plist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    fake_la = tmp_path / "LaunchAgents"
    fake_la.mkdir()
    plist = fake_la / "com.accountpilot.mail.daemon.plist"
    plist.write_text("<dummy/>")
    monkeypatch.setattr(
        "accountpilot.core.cli.service_cmd._LAUNCHAGENTS",
        fake_la,
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type(
            "_R", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "uninstall", "mail"])
    assert result.exit_code == 0
    assert not plist.exists()


def test_service_status_lists_registered_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    fake_stdout = (
        "PID\tStatus\tLabel\n"
        "1234\t0\tcom.accountpilot.mail.daemon\n"
        "5678\t0\tcom.accountpilot.imessage.daemon\n"
        "9999\t0\tcom.something.else\n"
    )

    def _fake(args: list[str], **kw: object) -> object:
        class _R:
            returncode = 0
            stdout = fake_stdout
            stderr = ""

        return _R()

    monkeypatch.setattr(subprocess, "run", _fake)

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "status"])
    assert result.exit_code == 0
    assert "com.accountpilot.mail.daemon" in result.output
    assert "com.accountpilot.imessage.daemon" in result.output
    assert "com.something.else" not in result.output


# ─── Linux systemd ─────────────────────────────────────────────────


def test_service_install_dry_run_renders_systemd_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run on Linux prints the rendered unit file without writing
    or invoking systemctl."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    fake_bin = tmp_path / "accountpilot"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)

    def _shouldnt_call(*a: object, **kw: object) -> None:
        raise AssertionError("dry-run should not call subprocess.run")

    monkeypatch.setattr(subprocess, "run", _shouldnt_call)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "service",
            "install",
            "mail",
            "--dry-run",
            "--bin",
            str(fake_bin),
        ],
    )
    assert result.exit_code == 0, result.output
    out = result.output
    assert "[Unit]" in out
    assert "[Service]" in out
    assert "Restart=always" in out
    assert f"ExecStart={fake_bin.resolve()} mail daemon" in out
    assert "WantedBy=default.target" in out


def test_service_install_writes_unit_and_calls_systemctl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real install on Linux writes the unit into XDG systemd/user/ and
    calls daemon-reload + enable --now."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    fake_bin = tmp_path / "accountpilot"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ACCOUNTPILOT_LOG_DIR", str(tmp_path / "logs"))

    calls: list[list[str]] = []

    def _capture(args: list[str], **kw: object) -> object:
        calls.append(args)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(subprocess, "run", _capture)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["service", "install", "imessage", "--bin", str(fake_bin)]
    )
    assert result.exit_code == 0, result.output
    unit = tmp_path / "config" / "systemd" / "user" / "accountpilot-imessage.service"
    assert unit.exists()
    content = unit.read_text()
    assert "AccountPilot imessage daemon" in content
    assert "Restart=always" in content

    # Verify systemctl call sequence: daemon-reload, then enable --now
    verbs = [(c[0], c[2]) for c in calls if c[0] == "systemctl"]
    assert verbs == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "enable"),
    ]


def test_service_uninstall_systemd_removes_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    unit_dir = tmp_path / "config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit = unit_dir / "accountpilot-mail.service"
    unit.write_text("# dummy")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type(
            "_R", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "uninstall", "mail"])
    assert result.exit_code == 0
    assert not unit.exists()
