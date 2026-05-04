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

"""accountpilot status"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    """Emit the standard JSON envelope to stdout. One call per CLI invocation."""
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


@click.command("status")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
@click.option("--json", "json_out", is_flag=True, help="Emit JSON envelope.")
def status_cmd(db_path: Path, json_out: bool) -> None:
    """Per-account health summary."""

    if json_out:

        async def _run_json() -> None:
            async with (
                open_db(db_path) as db,
                db.execute(
                    "SELECT a.id, a.source, a.account_identifier AS identifier, "
                    "       s.last_sync_at, s.last_error, "
                    "       COALESCE(s.messages_ingested, 0) AS synced_count "
                    "FROM accounts a "
                    "LEFT JOIN sync_status s ON s.account_id = a.id "
                    "ORDER BY a.id"
                ) as cur,
            ):
                rows = await cur.fetchall()
            _emit_envelope(
                data={
                    "accounts": [
                        {
                            "id": r["id"],
                            "source": r["source"],
                            "identifier": r["identifier"],
                            "last_sync_at": r["last_sync_at"],
                            "last_error": r["last_error"],
                            "synced_count": r["synced_count"],
                        }
                        for r in rows
                    ],
                    "generated_at": datetime.now(UTC).isoformat(),
                }
            )

        asyncio.run(_run_json())
        return

    async def _run() -> None:
        async with (
            open_db(db_path) as db,
            db.execute(
                """
            SELECT a.id, a.source, a.account_identifier, a.enabled,
                   p.name || COALESCE(' ' || p.surname, '') AS owner_name,
                   (SELECT COUNT(*) FROM messages m WHERE m.account_id=a.id)
                     AS msg_count,
                   s.last_sync_at, s.last_error
            FROM accounts a
            JOIN people p ON p.id = a.owner_id
            LEFT JOIN sync_status s ON s.account_id = a.id
            ORDER BY a.id
            """
            ) as cur,
        ):
            rows = await cur.fetchall()
        if not rows:
            click.echo("no accounts.")
            return
        for r in rows:
            enabled = "on" if r["enabled"] else "off"
            click.echo(
                f"#{r['id']} [{enabled}] {r['source']:<10}  "
                f"{r['account_identifier']:<30} "
                f"owner={r['owner_name']!r}  messages={r['msg_count']}  "
                f"last_sync={r['last_sync_at'] or '—'}  "
                f"last_error={r['last_error'] or '—'}"
            )

    asyncio.run(_run())
