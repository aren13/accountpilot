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


@messages_group.command("get")
@click.argument("message_id", type=int)
@click.option("--json", "json_out", is_flag=True)
@_db_option
def messages_get(message_id: int, json_out: bool, db_path: Path) -> None:
    """Fetch a single message + its attachments + recipients."""

    async def _run() -> dict[str, Any]:
        async with open_db(db_path) as db:
            async with db.execute(
                "SELECT id, account_id, source, sent_at, received_at, "
                "thread_id, body_text, body_html, direction "
                "FROM messages WHERE id = ?",
                (message_id,),
            ) as cur:
                m = await cur.fetchone()
            if m is None:
                return {
                    "ok": False,
                    "error": {
                        "code": "MESSAGE_NOT_FOUND",
                        "message": f"no message with id={message_id}",
                    },
                }

            msg: dict[str, Any] = {
                "id": m["id"],
                "source": m["source"],
                "account_id": m["account_id"],
                "sent_at": m["sent_at"],
                "received_at": m["received_at"],
                "thread_id": m["thread_id"],
                "body_text": m["body_text"],
                "body_html": m["body_html"],
                "direction": m["direction"],
                "subject": None,
                "email": None,
                "imessage": None,
                "people": [],
                "attachments": [],
            }

            async with db.execute(
                "SELECT subject, in_reply_to, references_json, imap_uid, "
                "mailbox, gmail_thread_id, labels_json "
                "FROM email_details WHERE message_id = ?",
                (message_id,),
            ) as cur:
                ed = await cur.fetchone()
            if ed is not None:
                msg["subject"] = ed["subject"]
                msg["email"] = {
                    "in_reply_to": ed["in_reply_to"],
                    "references_json": ed["references_json"],
                    "imap_uid": ed["imap_uid"],
                    "mailbox": ed["mailbox"],
                    "gmail_thread_id": ed["gmail_thread_id"],
                    "labels_json": ed["labels_json"],
                }

            async with db.execute(
                "SELECT chat_guid, service, is_from_me, is_read, date_read "
                "FROM imessage_details WHERE message_id = ?",
                (message_id,),
            ) as cur:
                im = await cur.fetchone()
            if im is not None:
                msg["imessage"] = {
                    "chat_guid": im["chat_guid"],
                    "service": im["service"],
                    "is_from_me": bool(im["is_from_me"]),
                    "is_read": bool(im["is_read"]),
                    "date_read": im["date_read"],
                }

            async with db.execute(
                """
                SELECT mp.role, p.id, p.name, p.surname,
                       (SELECT value FROM identifiers
                        WHERE person_id = p.id AND is_primary = 1
                        LIMIT 1) AS identifier
                FROM message_people mp
                JOIN people p ON p.id = mp.person_id
                WHERE mp.message_id = ?
                ORDER BY mp.role
                """,
                (message_id,),
            ) as cur:
                async for row in cur:
                    full_name = (
                        f"{row['name']} {row['surname']}".strip()
                        if row["surname"]
                        else row["name"]
                    )
                    msg["people"].append({
                        "role": row["role"],
                        "id": row["id"],
                        "name": full_name,
                        "identifier": row["identifier"],
                    })

            async with db.execute(
                "SELECT id, filename, content_hash, mime_type, size_bytes "
                "FROM attachments WHERE message_id = ? ORDER BY id",
                (message_id,),
            ) as cur:
                async for row in cur:
                    msg["attachments"].append({
                        "id": row["id"],
                        "filename": row["filename"],
                        "content_hash": row["content_hash"],
                        "mime_type": row["mime_type"],
                        "size_bytes": row["size_bytes"],
                    })

        return {"ok": True, "message": msg}

    result = asyncio.run(_run())
    if json_out:
        if result["ok"]:
            _emit_envelope(data={"message": result["message"]})
        else:
            _emit_envelope(error=result["error"])
        return
    if not result["ok"]:
        raise click.ClickException(result["error"]["message"])
    msg = result["message"]
    label = msg.get("subject") or (msg["body_text"][:80])
    click.echo(f"#{msg['id']} [{msg['source']}] {msg['sent_at']}  {label}")
    for a in msg["attachments"]:
        click.echo(
            f"  attachment: {a['filename']} ({a['size_bytes']} bytes)"
        )
