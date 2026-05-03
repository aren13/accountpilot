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

"""SQLite migration runner.

Applies numbered .sql files from a migrations directory in lexicographic order.
Tracks applied versions in a `schema_version` table. Idempotent.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 (used at runtime for path construction)

import aiosqlite  # noqa: TC002 (used at runtime in function signatures)

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    filename   TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL
);
"""

_FILENAME_RE = re.compile(r"^(\d+)_.+\.sql$")


async def current_version(db: aiosqlite.Connection) -> int:
    """Return the highest applied migration version, or 0 if none."""
    await db.execute(_SCHEMA_VERSION_DDL)
    async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def apply_migrations(
    db: aiosqlite.Connection, migrations_dir: Path
) -> list[int]:
    """Apply all migrations in `migrations_dir` newer than `current_version(db)`.

    Returns the list of versions newly applied (empty if up-to-date).
    """
    await db.execute(_SCHEMA_VERSION_DDL)
    applied = await current_version(db)
    newly_applied: list[int] = []

    for path in sorted(migrations_dir.iterdir()):
        match = _FILENAME_RE.match(path.name)
        if match is None:
            continue
        version = int(match.group(1))
        if version <= applied:
            continue
        sql = path.read_text()
        await db.executescript(sql)
        await db.execute(
            "INSERT INTO schema_version (version, filename, applied_at) "
            "VALUES (?, ?, ?)",
            (version, path.name, datetime.now(UTC).isoformat()),
        )
        await db.commit()
        newly_applied.append(version)

    return newly_applied
