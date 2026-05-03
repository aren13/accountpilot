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

"""accountpilot accounts ..."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db


@click.group("accounts")
def accounts_group() -> None:
    """Account management."""


def _db_option(f: Any) -> Any:
    return click.option(
        "--db-path",
        type=click.Path(path_type=Path),
        default=paths.db_path,
        show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
    )(f)


@accounts_group.command("list")
@_db_option
def accounts_list(db_path: Path) -> None:
    async def _run() -> None:
        async with (
            open_db(db_path) as db,
            db.execute(
                "SELECT a.id, a.source, a.account_identifier, a.enabled, "
                "p.name || COALESCE(' ' || p.surname, '') AS owner_name "
                "FROM accounts a JOIN people p ON p.id=a.owner_id "
                "ORDER BY a.id"
            ) as cur,
        ):
            rows = await cur.fetchall()
        for r in rows:
            state = "[on]" if r["enabled"] else "[off]"
            click.echo(
                f"#{r['id']} {state} {r['source']:<10}  {r['account_identifier']:<30} "
                f"owner={r['owner_name']!r}"
            )

    asyncio.run(_run())


@accounts_group.command("disable")
@click.argument("account_id", type=int)
@_db_option
def accounts_disable(account_id: int, db_path: Path) -> None:
    async def _run() -> None:
        async with open_db(db_path) as db:
            await db.execute(
                "UPDATE accounts SET enabled=0, updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), account_id),
            )
            await db.commit()
        click.echo(f"disabled account #{account_id}")

    asyncio.run(_run())


@accounts_group.command("delete")
@click.argument("account_id", type=int)
@click.option("--force", is_flag=True)
@_db_option
def accounts_delete(account_id: int, force: bool, db_path: Path) -> None:
    if not force and not click.confirm(
        f"Delete account #{account_id} and all its messages?", default=False
    ):
        click.echo("aborted.")
        return

    async def _run() -> None:
        async with open_db(db_path) as db:
            await db.execute("DELETE FROM messages WHERE account_id=?", (account_id,))
            await db.execute(
                "DELETE FROM sync_status WHERE account_id=?", (account_id,)
            )
            await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            await db.commit()
        click.echo(f"deleted account #{account_id}")

    asyncio.run(_run())
