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

"""SQLite connection setup for AccountPilot.

`open_db(path)` is the single entrypoint used by Storage and the CLI to
obtain an aiosqlite.Connection with the right pragmas and an up-to-date
schema. It is an async context manager.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from accountpilot.core.db.migrations import apply_migrations

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@asynccontextmanager
async def open_db(path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Open a SQLite DB at `path`, apply pending migrations, yield the connection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    try:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")
        db.row_factory = aiosqlite.Row
        await apply_migrations(db, _MIGRATIONS_DIR)
        yield db
    finally:
        await db.close()
