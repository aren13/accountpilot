# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
# Licensed under AGPL-3.0-or-later.

"""accountpilot messages — list / get + accountpilot attachments path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db


def _emit_envelope(
    *,
    data: Any | None = None,
    error: dict[str, str] | None = None,
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


def _db_option(f: Any) -> Any:
    return click.option(
        "--db-path",
        type=click.Path(path_type=Path),
        default=lambda: paths.data_dir() / "accountpilot.db",
        show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
    )(f)


_LIST_BASE_SQL = """
SELECT
    m.id, m.source, m.account_id, m.sent_at, m.thread_id,
    COALESCE(ed.subject, '') AS subject,
    SUBSTR(m.body_text, 1, 200) AS snippet,
    fp.name AS from_name,
    fp.surname AS from_surname,
    fi.value AS from_identifier,
    EXISTS (
        SELECT 1 FROM attachments a WHERE a.message_id = m.id
    ) AS has_attachments
FROM messages m
LEFT JOIN email_details ed ON ed.message_id = m.id
LEFT JOIN message_people mp_from
    ON mp_from.message_id = m.id AND mp_from.role = 'from'
LEFT JOIN people fp ON fp.id = mp_from.person_id
LEFT JOIN identifiers fi
    ON fi.person_id = fp.id AND fi.is_primary = 1
"""


@click.group("messages")
def messages_group() -> None:
    """Read messages stored in the local DB."""


@messages_group.command("list")
@click.option("--json", "json_out", is_flag=True)
@click.option("--account", "account_id", type=int, default=None)
@click.option(
    "--contact-id",
    "contact_id",
    type=int,
    default=None,
    help="Filter to messages where this person appears (any role).",
)
@click.option(
    "--since",
    "since_date",
    default=None,
    help="ISO date YYYY-MM-DD; sent_at >= this date.",
)
@click.option("--limit", type=int, default=50)
@click.option(
    "--cursor",
    type=int,
    default=None,
    help="Pagination: return rows with id < cursor.",
)
@_db_option
def messages_list(
    json_out: bool,
    account_id: int | None,
    contact_id: int | None,
    since_date: str | None,
    limit: int,
    cursor: int | None,
    db_path: Path,
) -> None:
    """Paginated list of messages, newest first."""
    limit = max(1, min(limit, 500))

    where_clauses: list[str] = []
    params: list[Any] = []
    if account_id is not None:
        where_clauses.append("m.account_id = ?")
        params.append(account_id)
    if contact_id is not None:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM message_people mp "
            "WHERE mp.message_id = m.id AND mp.person_id = ?)"
        )
        params.append(contact_id)
    if since_date is not None:
        where_clauses.append("m.sent_at >= ?")
        params.append(f"{since_date}T00:00:00+00:00")
    if cursor is not None:
        where_clauses.append("m.id < ?")
        params.append(cursor)

    sql = _LIST_BASE_SQL
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY m.sent_at DESC, m.id DESC LIMIT ?"
    params.append(limit)

    async def _run() -> dict[str, Any]:
        async with (
            open_db(db_path) as db,
            db.execute(sql, tuple(params)) as cur,
        ):
            rows = await cur.fetchall()
        messages = []
        for r in rows:
            from_name = None
            if r["from_name"] is not None:
                from_name = (
                    f"{r['from_name']} {r['from_surname']}".strip()
                    if r["from_surname"]
                    else r["from_name"]
                )
            messages.append({
                "id": r["id"],
                "source": r["source"],
                "account_id": r["account_id"],
                "sent_at": r["sent_at"],
                "thread_id": r["thread_id"],
                "subject": r["subject"],
                "snippet": r["snippet"],
                "from_name": from_name,
                "from_identifier": r["from_identifier"],
                "has_attachments": bool(r["has_attachments"]),
            })
        next_cursor = messages[-1]["id"] if len(messages) == limit else None
        return {"messages": messages, "next_cursor": next_cursor}

    result = asyncio.run(_run())
    if json_out:
        _emit_envelope(data=result)
        return
    for m in result["messages"]:
        label = m["subject"] or m["snippet"][:60]
        click.echo(
            f"#{m['id']} [{m['source']}] {m['sent_at']}  {label}"
        )
