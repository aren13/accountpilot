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

"""accountpilot setup"""

from __future__ import annotations

import asyncio
import contextlib
import platform
import subprocess
from pathlib import Path

import click

from accountpilot.core import paths
from accountpilot.core.cas import CASStore
from accountpilot.core.config import load_config
from accountpilot.core.db.connection import open_db
from accountpilot.core.models import Identifier
from accountpilot.core.storage import Storage

# A timestamp deep in the future — `read-imessages --since-ns N` returns
# zero rows but proves the helper can open chat.db, which is what we
# care about for FDA probing. 2^62 ns ≈ year 2147 in Apple's epoch and
# fits in the helper's Int64 parser without overflow.
_FDA_PROBE_SINCE_NS = 1 << 62

_PRIVACY_PANE_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)


def _probe_imessage_fda() -> None:
    """Run a zero-row read-imessages call to verify FDA + helper install.

    Prints status to stdout and, on EACCES, deep-links into System
    Settings → Privacy & Security → Full Disk Access. Never raises —
    this is best-effort onboarding, not a hard prerequisite for setup.
    """
    if platform.system() != "Darwin":
        return  # iMessage is macOS-only

    # Local import keeps the heavy plugin import out of `setup` for
    # users who never enable iMessage.
    from accountpilot.plugins.imessage import helper_client

    try:
        binary = helper_client.find_helper_binary()
    except helper_client.HelperNotInstalledError as exc:
        click.echo(
            click.style("⚠ accountpilot-fda-helper not found.", fg="yellow"),
            err=True,
        )
        click.echo(f"   {exc}", err=True)
        click.echo(
            "   iMessage sync needs the signed helper. "
            "Install via `brew install aren13/tap/accountpilot`.",
            err=True,
        )
        return

    try:
        # Drain to EOF so the subprocess closes cleanly.
        for _ in helper_client.iter_records(
            since_ns=_FDA_PROBE_SINCE_NS,
            helper_path=binary,
        ):
            pass
    except helper_client.HelperPermissionError:
        click.echo(
            click.style(
                "⚠ Full Disk Access not granted to the FDA helper.",
                fg="yellow",
            )
        )
        click.echo(f"   helper:  {binary}")
        click.echo("   To grant FDA:")
        click.echo(
            "     1. Open System Settings → Privacy & Security → Full Disk Access"
        )
        click.echo(f"     2. Click +, navigate to: {binary}")
        click.echo("     3. Re-run `accountpilot setup` to verify")
        click.echo()
        # Deep-link into the right pane. Best-effort — silent on
        # headless / missing `open` (e.g. SSH session).
        with contextlib.suppress(OSError):
            subprocess.run(["open", _PRIVACY_PANE_URL], check=False)
        return
    except helper_client.HelperError as exc:
        click.echo(
            click.style(f"⚠ helper probe failed: {exc}", fg="yellow"),
            err=True,
        )
        return

    click.echo(click.style("✓ FDA helper reachable, chat.db readable.", fg="green"))


@click.command("setup")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=paths.config_path,
    show_default="$ACCOUNTPILOT_CONFIG_DIR/config.yaml",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
def setup_cmd(config_path: Path, db_path: Path) -> None:
    """Apply config.yaml to the DB (idempotent)."""

    cfg = load_config(config_path)
    cas_root = db_path.parent / "attachments"

    async def _run() -> None:
        async with open_db(db_path) as db:
            storage = Storage(db, CASStore(cas_root))
            owner_id_by_identifier: dict[str, int] = {}
            for owner in cfg.owners:
                pid = await storage.upsert_owner(
                    name=owner.name,
                    surname=owner.surname,
                    identifiers=[
                        Identifier(kind=i.kind, value=i.value)
                        for i in owner.identifiers
                    ],
                )
                for i in owner.identifiers:
                    owner_id_by_identifier[i.value.lower()] = pid

            for plugin_name, pcfg in cfg.plugins.items():
                if not pcfg.enabled:
                    continue
                for account in pcfg.accounts:
                    owner_pid = owner_id_by_identifier.get(account.owner.lower())
                    if owner_pid is None:
                        raise click.UsageError(
                            f"plugin '{plugin_name}' account "
                            f"{account.identifier!r} references unknown owner "
                            f"{account.owner!r} (not declared in owners[])"
                        )
                    source = account.provider or plugin_name
                    await storage.upsert_account(
                        source=source,
                        identifier=account.identifier,
                        owner_id=owner_pid,
                        credentials_ref=account.credentials_ref,
                    )
        click.echo(f"setup applied: {config_path} -> {db_path}")

    asyncio.run(_run())

    # If iMessage is enabled, verify the FDA helper is reachable and
    # has permission to read chat.db. Best-effort; no hard fail.
    imessage_cfg = cfg.plugins.get("imessage")
    if imessage_cfg is not None and imessage_cfg.enabled:
        _probe_imessage_fda()
