# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""accountpilot service — install/uninstall/status the daemon supervisor.

Renders a platform-native service file so the daemon auto-starts on
login and respawns on crash:

- macOS  → launchd plist into ~/Library/LaunchAgents/, bootstrapped via
  `launchctl bootstrap/enable/kickstart`.
- Linux  → systemd user-unit into $XDG_CONFIG_HOME/systemd/user/,
  registered via `systemctl --user daemon-reload` + `enable --now`.

Windows and other platforms are unsupported — chat.db is macOS-only,
and IMAP can run on WSL via pip.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import click
from jinja2 import Environment, PackageLoader, select_autoescape

from accountpilot.core import paths

_LAUNCHAGENTS = Path.home() / "Library" / "LaunchAgents"
_DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"

_jinja_env = Environment(
    loader=PackageLoader("accountpilot", "templates/services"),
    autoescape=select_autoescape(["xml"]),
    keep_trailing_newline=True,
)


@click.group("service")
def service_group() -> None:
    """Install/uninstall/status the AccountPilot daemon supervisor."""


@service_group.command("install")
@click.argument("plugin", type=click.Choice(["mail", "imessage"]))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the rendered service file but don't write or bootstrap.",
)
def install(plugin: str, dry_run: bool) -> None:
    """Render and bootstrap the launchd/systemd job for PLUGIN."""
    sysname = platform.system()
    if sysname == "Darwin":
        _install_launchd(plugin, dry_run=dry_run)
    elif sysname == "Linux":
        _install_systemd(plugin, dry_run=dry_run)
    else:
        raise click.UsageError(f"unsupported platform: {sysname}")


@service_group.command("uninstall")
@click.argument("plugin", type=click.Choice(["mail", "imessage"]))
def uninstall(plugin: str) -> None:
    """Bootout/disable and remove the service file for PLUGIN."""
    sysname = platform.system()
    if sysname == "Darwin":
        _uninstall_launchd(plugin)
    elif sysname == "Linux":
        _uninstall_systemd(plugin)
    else:
        raise click.UsageError(f"unsupported platform: {sysname}")


@service_group.command("status")
def status() -> None:
    """List registered AccountPilot daemon jobs."""
    sysname = platform.system()
    if sysname == "Darwin":
        _status_launchd()
    elif sysname == "Linux":
        _status_systemd()
    else:
        raise click.UsageError(f"unsupported platform: {sysname}")


# ─── macOS launchd ─────────────────────────────────────────────────


def _install_launchd(plugin: str, *, dry_run: bool) -> None:
    accountpilot_bin = shutil.which("accountpilot")
    if not accountpilot_bin:
        raise click.UsageError(
            "couldn't find `accountpilot` on PATH — install the package "
            "first (e.g. pip install accountpilot)"
        )
    rendered = _jinja_env.get_template("launchd.plist.j2").render(
        plugin=plugin,
        accountpilot_bin=accountpilot_bin,
        log_dir=str(paths.log_dir()),
        data_dir=str(paths.data_dir()),
        env_path=_DEFAULT_PATH,
        extra_env={},
    )
    if dry_run:
        click.echo(rendered)
        return

    paths.log_dir().mkdir(parents=True, exist_ok=True)
    paths.data_dir().mkdir(parents=True, exist_ok=True)

    label = f"com.accountpilot.{plugin}.daemon"
    plist_path = _LAUNCHAGENTS / f"{label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(rendered)

    uid = _current_uid()
    domain = f"gui/{uid}"

    # Bootout existing first (idempotent — ignore exit code).
    subprocess.run(
        ["launchctl", "bootout", domain, str(plist_path)],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "enable", f"{domain}/{label}"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "kickstart", f"{domain}/{label}"],
        check=True,
        capture_output=True,
    )
    click.echo(f"service install: {plugin} → {plist_path}")


def _uninstall_launchd(plugin: str) -> None:
    label = f"com.accountpilot.{plugin}.daemon"
    plist_path = _LAUNCHAGENTS / f"{label}.plist"
    uid = _current_uid()
    domain = f"gui/{uid}"

    subprocess.run(
        ["launchctl", "bootout", domain, str(plist_path)],
        check=False,
        capture_output=True,
    )
    if plist_path.exists():
        plist_path.unlink()
        click.echo(f"service uninstall: removed {plist_path}")
    else:
        click.echo(f"service uninstall: no plist at {plist_path}")


def _status_launchd() -> None:
    result = subprocess.run(
        ["launchctl", "list"],
        check=True,
        capture_output=True,
        text=True,
    )
    matches = [
        line for line in result.stdout.splitlines()
        if "com.accountpilot." in line
    ]
    if not matches:
        click.echo("no AccountPilot daemons registered")
        return
    click.echo("PID\tStatus\tLabel")
    for line in matches:
        click.echo(line)


def _current_uid() -> int:
    return os.getuid()


# ─── Linux systemd ─────────────────────────────────────────────────


def _systemd_user_dir() -> Path:
    """XDG-compliant systemd user-unit directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "systemd" / "user"


def _install_systemd(plugin: str, *, dry_run: bool) -> None:
    accountpilot_bin = shutil.which("accountpilot")
    if not accountpilot_bin:
        raise click.UsageError(
            "couldn't find `accountpilot` on PATH — install the package "
            "first (e.g. pip install accountpilot)"
        )
    rendered = _jinja_env.get_template("systemd.service.j2").render(
        plugin=plugin,
        accountpilot_bin=accountpilot_bin,
        log_dir=str(paths.log_dir()),
        data_dir=str(paths.data_dir()),
        env_path=_DEFAULT_PATH,
        extra_env={},
    )
    if dry_run:
        click.echo(rendered)
        return

    paths.log_dir().mkdir(parents=True, exist_ok=True)
    paths.data_dir().mkdir(parents=True, exist_ok=True)

    unit_dir = _systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_name = f"accountpilot-{plugin}.service"
    unit_path = unit_dir / unit_name
    unit_path.write_text(rendered)

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", unit_name],
        check=True,
        capture_output=True,
    )
    click.echo(f"service install: {plugin} → {unit_path}")


def _uninstall_systemd(plugin: str) -> None:
    unit_name = f"accountpilot-{plugin}.service"
    unit_path = _systemd_user_dir() / unit_name

    subprocess.run(
        ["systemctl", "--user", "disable", "--now", unit_name],
        check=False,
        capture_output=True,
    )
    if unit_path.exists():
        unit_path.unlink()
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            capture_output=True,
        )
        click.echo(f"service uninstall: removed {unit_path}")
    else:
        click.echo(f"service uninstall: no unit at {unit_path}")


def _status_systemd() -> None:
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "list-units",
            "--type=service",
            "--all",
            "--no-pager",
            "accountpilot-*.service",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        click.echo("no AccountPilot daemons registered")
        return
    click.echo(result.stdout)
