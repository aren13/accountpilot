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

"""accountpilot db ..."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db


@click.group("db")
def db_group() -> None:
    """Database management commands."""


@db_group.command("migrate")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
def migrate(db_path: Path) -> None:
    """Apply pending migrations."""

    async def _run() -> None:
        async with open_db(db_path):
            pass  # open_db applies migrations.
        click.echo(f"migrated: {db_path}")

    asyncio.run(_run())


@db_group.command("vacuum")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
def vacuum(db_path: Path) -> None:
    """Run SQLite VACUUM on the DB."""

    async def _run() -> None:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("VACUUM")
        click.echo(f"vacuumed: {db_path}")

    asyncio.run(_run())
