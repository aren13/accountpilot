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

"""accountpilot imessage CLI subgroup."""

from __future__ import annotations

import asyncio
import json
from collections.abc import (
    AsyncIterator,  # noqa: TC003 (used at runtime in async context manager return type)
)
from contextlib import asynccontextmanager
from pathlib import Path  # noqa: TC003 (used at runtime for path construction)
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.auth import Secrets
from accountpilot.core.cas import CASStore
from accountpilot.core.config import load_config
from accountpilot.core.db.connection import open_db
from accountpilot.core.storage import Storage
from accountpilot.plugins.imessage.plugin import IMessagePlugin


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    """Emit the standard JSON envelope to stdout. One call per CLI invocation."""
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


@click.group("imessage")
def imessage_group() -> None:
    """iMessage plugin commands (backfill, sync, daemon)."""


def _db_option(f: Any) -> Any:
    return click.option(
        "--db-path",
        type=click.Path(path_type=Path),
        default=paths.db_path,
        show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
    )(f)


def _config_option(f: Any) -> Any:
    return click.option(
        "--config",
        "config_path",
        type=click.Path(path_type=Path),
        default=paths.config_path,
        show_default="$ACCOUNTPILOT_CONFIG_DIR/config.yaml",
    )(f)


@asynccontextmanager
async def _opened_plugin(
    config_path: Path,
    db_path: Path,
) -> AsyncIterator[tuple[IMessagePlugin, Storage]]:
    """Open DB, build Storage + IMessagePlugin, yield. Closes DB on exit."""
    cfg = load_config(config_path)
    im_cfg_raw = cfg.plugins.get("imessage")
    if im_cfg_raw is None or not im_cfg_raw.enabled:
        raise click.UsageError(
            f"no enabled `plugins.imessage` section in {config_path}"
        )
    im_cfg_dict: dict[str, Any] = {
        "accounts": [
            {
                k: v
                for k, v in a.model_dump(exclude_none=True).items()
                if k in {"identifier", "owner", "chat_db_path"}
            }
            for a in im_cfg_raw.accounts
        ],
        **im_cfg_raw.extra,
    }
    cas = CASStore(db_path.parent / "attachments")
    async with open_db(db_path) as db:
        storage = Storage(db, cas)
        plugin = IMessagePlugin(
            config=im_cfg_dict,
            storage=storage,
            secrets=Secrets({}),
        )
        yield plugin, storage


@imessage_group.command("backfill")
@click.argument("account_id", type=int)
@_db_option
@_config_option
def imessage_backfill(
    account_id: int,
    db_path: Path,
    config_path: Path,
) -> None:
    """One-shot historical pull from chat.db for an account."""

    async def _run() -> None:
        async with _opened_plugin(config_path, db_path) as (plugin, _):
            await plugin.setup()
            await plugin.backfill(account_id)

    asyncio.run(_run())
    click.echo(f"backfill complete: account={account_id}")


@imessage_group.command("sync")
@click.argument("account_id", type=int)
@_db_option
@_config_option
def imessage_sync(
    account_id: int,
    db_path: Path,
    config_path: Path,
) -> None:
    """One incremental sync pass."""

    async def _run() -> None:
        async with _opened_plugin(config_path, db_path) as (plugin, _):
            await plugin.setup()
            await plugin.sync_once(account_id)

    asyncio.run(_run())
    click.echo(f"sync complete: account={account_id}")


@imessage_group.command("daemon")
@click.option(
    "--account-id",
    "account_id",
    type=int,
    default=None,
    help=(
        "Optional: supervise just this one account. Default: all "
        "enabled imessage accounts."
    ),
)
@_db_option
@_config_option
def imessage_daemon(
    account_id: int | None,
    db_path: Path,
    config_path: Path,
) -> None:
    """Long-running daemon: watches chat.db and syncs on each change."""
    from accountpilot.core.logging import configure_daemon_logging

    configure_daemon_logging(
        "imessage",
        log_dir=paths.log_dir(),
    )

    async def _run() -> None:
        async with _opened_plugin(config_path, db_path) as (plugin, storage):
            await plugin.setup()
            if account_id is not None:
                await plugin.daemon(account_id)
                return
            async with storage.db.execute(
                "SELECT id FROM accounts WHERE source='imessage' AND enabled=1"
            ) as cur:
                rows = [r["id"] for r in await cur.fetchall()]
            if not rows:
                raise click.UsageError("no enabled imessage accounts in DB")
            await asyncio.gather(*(plugin.daemon(aid) for aid in rows))

    asyncio.run(_run())


@imessage_group.command("probe-fda")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON envelope to stdout.")
def probe_fda(json_out: bool) -> None:
    """Probe whether the FDA helper can read chat.db.

    Returns ``{ok: true, data: {granted: bool, reason: str, message: str}}``
    regardless of grant state — caller distinguishes via ``data.granted``.
    """
    from accountpilot.plugins.imessage import helper_client

    try:
        helper_client.find_helper_binary()
    except helper_client.HelperNotInstalledError as exc:
        if json_out:
            _emit_envelope(
                data={
                    "granted": False,
                    "reason": "HELPER_MISSING",
                    "message": str(exc),
                }
            )
            return
        click.echo(f"helper not installed: {exc}")
        return

    try:
        # Drain a no-op query: since_ns far in the future → 0 records returned.
        for _ in helper_client.iter_records(since_ns=1 << 62):
            break
        granted, reason, message = True, "OK", "helper can read chat.db"
    except helper_client.HelperPermissionError:
        granted, reason, message = False, "FDA_DENIED", "Full Disk Access not granted"
    except Exception as exc:  # noqa: BLE001
        granted, reason, message = False, "PROBE_FAILED", str(exc)

    if json_out:
        _emit_envelope(
            data={"granted": granted, "reason": reason, "message": message}
        )
        return
    click.echo(f"FDA probe: granted={granted} reason={reason} {message}")
