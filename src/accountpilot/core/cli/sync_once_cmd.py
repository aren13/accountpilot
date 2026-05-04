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

"""accountpilot sync-once {mail,imessage} <id> — one-shot per-account sync.

The XPC service from Phase 3 calls these on a timer instead of running
the long-lived `daemon` subcommand. One-shot keeps the supervisor
simple (spawn → wait → emit JSON → reap) and matches the standard
envelope used elsewhere.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.auth import Secrets
from accountpilot.core.cas import CASStore
from accountpilot.core.db.connection import open_db
from accountpilot.core.storage import Storage


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


def _db_option(f: Any) -> Any:
    return click.option(
        "--db-path",
        type=click.Path(path_type=Path),
        default=paths.db_path,
        show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
    )(f)


async def _resolve_account_source(account_id: int, db_path: Path) -> str | None:
    async with (
        open_db(db_path) as db,
        db.execute("SELECT source FROM accounts WHERE id=?", (account_id,)) as cur,
    ):
        row = await cur.fetchone()
    return row["source"] if row else None


async def _run_mail(account_id: int, db_path: Path) -> int:
    from accountpilot.plugins.mail.plugin import MailPlugin

    async with open_db(db_path) as db:
        storage = Storage(db, CASStore(db_path.parent / "attachments"))
        plugin = MailPlugin(config={}, storage=storage, secrets=Secrets({}))
        return await plugin.sync_once(account_id=account_id, db_path=db_path)


async def _run_imessage(account_id: int, db_path: Path) -> int:
    from accountpilot.plugins.imessage.plugin import IMessagePlugin

    async with open_db(db_path) as db:
        storage = Storage(db, CASStore(db_path.parent / "attachments"))
        plugin = IMessagePlugin(config={}, storage=storage, secrets=Secrets({}))
        return await plugin.sync_once(account_id=account_id, db_path=db_path)


def _emit_account_not_found(account_id: int, json_out: bool) -> None:
    if json_out:
        _emit_envelope(
            error={
                "code": "ACCOUNT_NOT_FOUND",
                "message": f"no account with id={account_id}",
            }
        )
        return
    raise click.ClickException(f"no account with id={account_id}")


def _run_one_shot(
    *,
    account_id: int,
    json_out: bool,
    db_path: Path,
    runner: Any,
    expected_source_kind: str,
) -> None:
    """Shared implementation for mail/imessage sync-once.

    ``runner`` is one of ``_run_mail`` or ``_run_imessage`` (async coroutine
    factory). ``expected_source_kind`` is used for the non-JSON output label.
    """
    source = asyncio.run(_resolve_account_source(account_id, db_path))
    if source is None:
        _emit_account_not_found(account_id, json_out)
        return

    started = time.monotonic()
    try:
        delta = asyncio.run(runner(account_id, db_path))
    except Exception as exc:
        if json_out:
            _emit_envelope(error={"code": "SYNC_FAILED", "message": str(exc)})
            return
        raise
    duration = round(time.monotonic() - started, 2)

    if json_out:
        _emit_envelope(
            data={
                "account_id": account_id,
                "source": source,
                "synced_count_delta": delta,
                "duration_seconds": duration,
            }
        )
        return
    click.echo(
        f"{expected_source_kind} sync-once: account={account_id} "
        f"delta={delta} {duration}s"
    )


@click.group("sync-once")
def sync_once_group() -> None:
    """One-shot per-account sync (used by the .app's XPC service)."""


@sync_once_group.command("mail")
@click.argument("account_id", type=int)
@click.option("--json", "json_out", is_flag=True)
@_db_option
def mail_sync_once(account_id: int, json_out: bool, db_path: Path) -> None:
    """Run a single sync_once cycle for a mail account."""
    _run_one_shot(
        account_id=account_id,
        json_out=json_out,
        db_path=db_path,
        runner=_run_mail,
        expected_source_kind="mail",
    )


@sync_once_group.command("imessage")
@click.argument("account_id", type=int)
@click.option("--json", "json_out", is_flag=True)
@_db_option
def imessage_sync_once(account_id: int, json_out: bool, db_path: Path) -> None:
    """Run a single sync_once cycle for an iMessage account."""
    _run_one_shot(
        account_id=account_id,
        json_out=json_out,
        db_path=db_path,
        runner=_run_imessage,
        expected_source_kind="imessage",
    )
