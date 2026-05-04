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

"""accountpilot search <query>"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


def _format_local(iso_ts: str) -> str:
    """Parse a stored ISO timestamp and re-emit in the local timezone.

    Stored timestamps are tz-aware (UTC for iMessage, original RFC 2822
    offset for Gmail). Display in local tz so all sources line up.
    """
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return iso_ts
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


@click.command("search")
@click.argument("query")
@click.option("--limit", type=int, default=20)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
@click.option("--json", "json_out", is_flag=True)
def search_cmd(query: str, limit: int, db_path: Path, json_out: bool) -> None:
    """Full-text search over messages."""

    if json_out:

        async def _run_json() -> None:
            async with (
                open_db(db_path) as db,
                db.execute(
                    """
                    SELECT m.id, m.source, m.account_id, m.sent_at,
                           COALESCE(ed.subject, '') AS subject,
                           SUBSTR(m.body_text, 1, 160) AS snippet,
                           bm25(messages_fts) AS score
                    FROM messages m
                    JOIN messages_fts f ON f.rowid = m.id
                    LEFT JOIN email_details ed ON ed.message_id = m.id
                    WHERE messages_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (query, limit),
                ) as cur,
            ):
                rows = await cur.fetchall()
            _emit_envelope(
                data={
                    "query": query,
                    "results": [
                        {
                            "id": r["id"],
                            "source": r["source"],
                            "account_id": r["account_id"],
                            "sent_at": r["sent_at"],
                            "subject": r["subject"],
                            "snippet": r["snippet"],
                            "score": r["score"],
                        }
                        for r in rows
                    ],
                }
            )

        asyncio.run(_run_json())
        return

    async def _run() -> None:
        async with (
            open_db(db_path) as db,
            db.execute(
                """
            SELECT m.id, m.source, m.sent_at, COALESCE(ed.subject, '') AS subject,
                   SUBSTR(m.body_text, 1, 80) AS snippet
            FROM messages m
            JOIN messages_fts f ON f.rowid = m.id
            LEFT JOIN email_details ed ON ed.message_id = m.id
            WHERE messages_fts MATCH ?
            ORDER BY m.sent_at DESC
            LIMIT ?
            """,
                (query, limit),
            ) as cur,
        ):
            rows = await cur.fetchall()
        if not rows:
            click.echo("no matches.")
            return
        for r in rows:
            label = r["subject"] or r["snippet"]
            click.echo(
                f"[{r['source']}] {_format_local(r['sent_at'])}  {label}  "
                f"(id={r['id']})"
            )

    asyncio.run(_run())
