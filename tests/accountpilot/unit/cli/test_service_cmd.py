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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run prints the rendered plist to stdout without touching
    LaunchAgents or running launchctl."""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr("shutil.which", lambda _: "/fake/bin/accountpilot")

    # Stub subprocess.run to fail loudly if called — dry-run must NOT shell out.
    def _shouldnt_call(*a: object, **kw: object) -> None:
        raise AssertionError("dry-run should not call subprocess.run")

    monkeypatch.setattr(subprocess, "run", _shouldnt_call)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["service", "install", "mail", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    out = result.output
    assert "<key>Label</key>" in out
    assert "<string>com.accountpilot.mail.daemon</string>" in out
    assert "<string>/fake/bin/accountpilot</string>" in out
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
    monkeypatch.setattr("shutil.which", lambda _: "/fake/bin/accountpilot")
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
    result = runner.invoke(cli, ["service", "install", "imessage"])
    assert result.exit_code == 0, result.output
    plist = fake_la / "com.accountpilot.imessage.daemon.plist"
    assert plist.exists()
    content = plist.read_text()
    assert "com.accountpilot.imessage.daemon" in content

    # Verify the launchctl call sequence: bootout, bootstrap, enable, kickstart
    verbs = [c[1] for c in calls if c[0] == "launchctl"]
    assert verbs == ["bootout", "bootstrap", "enable", "kickstart"]


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run on Linux prints the rendered unit file without writing
    or invoking systemctl."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/accountpilot")

    def _shouldnt_call(*a: object, **kw: object) -> None:
        raise AssertionError("dry-run should not call subprocess.run")

    monkeypatch.setattr(subprocess, "run", _shouldnt_call)

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "install", "mail", "--dry-run"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "[Unit]" in out
    assert "[Service]" in out
    assert "Restart=always" in out
    assert "ExecStart=/usr/local/bin/accountpilot mail daemon" in out
    assert "WantedBy=default.target" in out


def test_service_install_writes_unit_and_calls_systemctl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real install on Linux writes the unit into XDG systemd/user/ and
    calls daemon-reload + enable --now."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/accountpilot")
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
    result = runner.invoke(cli, ["service", "install", "imessage"])
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
