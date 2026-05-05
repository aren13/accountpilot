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

"""accountpilot people ..."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.db.connection import open_db
from accountpilot.core.identity import merge_people


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


@click.group("people")
def people_group() -> None:
    """Person/identifier management."""


def _db_option(f: Any) -> Any:
    return click.option(
        "--db-path",
        type=click.Path(path_type=Path),
        default=paths.db_path,
        show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
    )(f)


@people_group.command("list")
@_db_option
@click.option("--owners/--all", default=False)
@click.option("--json", "json_out", is_flag=True, default=False)
def people_list(db_path: Path, owners: bool, json_out: bool) -> None:
    if json_out:

        async def _run_json() -> None:
            sql_main = (
                "SELECT p.id, p.name, p.surname, p.is_owner, "
                "(SELECT COUNT(*) FROM message_people mp "
                " WHERE mp.person_id = p.id) AS message_count "
                "FROM people p "
                + ("WHERE p.is_owner=1 " if owners else "")
                + "ORDER BY message_count DESC, p.id"
            )
            async with open_db(db_path) as db:
                async with db.execute(sql_main) as cur:
                    rows = await cur.fetchall()

                people_by_id: dict[int, dict[str, Any]] = {}
                ordered_ids: list[int] = []
                for r in rows:
                    people_by_id[r["id"]] = {
                        "id": r["id"],
                        "name": r["name"],
                        "surname": r["surname"],
                        "is_owner": bool(r["is_owner"]),
                        "identifiers": [],
                        "message_count": r["message_count"],
                    }
                    ordered_ids.append(r["id"])

                if people_by_id:
                    placeholders = ",".join("?" * len(people_by_id))
                    async with db.execute(
                        f"SELECT person_id, kind, value FROM identifiers "
                        f"WHERE person_id IN ({placeholders}) "
                        f"ORDER BY id",
                        tuple(people_by_id.keys()),
                    ) as cur2:
                        async for ident in cur2:
                            people_by_id[ident["person_id"]]["identifiers"].append(
                                {
                                    "kind": ident["kind"],
                                    "value": ident["value"],
                                }
                            )

            ordered = [people_by_id[i] for i in ordered_ids]
            _emit_envelope(data={"people": ordered})

        asyncio.run(_run_json())
        return

    async def _run() -> None:
        async with open_db(db_path) as db:
            sql = (
                "SELECT p.id, p.name, p.surname, p.is_owner, "
                "GROUP_CONCAT(i.kind || ':' || i.value) AS idents "
                "FROM people p LEFT JOIN identifiers i ON i.person_id=p.id "
                + ("WHERE p.is_owner=1 " if owners else "")
                + "GROUP BY p.id ORDER BY p.id"
            )
            async with db.execute(sql) as cur:
                rows = await cur.fetchall()
        for r in rows:
            full = f"{r['name']} {r['surname'] or ''}".strip()
            owner = "*" if r["is_owner"] else " "
            click.echo(f"#{r['id']} {owner} {full:<30} {r['idents'] or ''}")

    asyncio.run(_run())


@people_group.command("show")
@click.argument("person_id", type=int)
@_db_option
@click.option("--json", "json_out", is_flag=True, default=False)
def people_show(person_id: int, db_path: Path, json_out: bool) -> None:
    if json_out:

        async def _run_json() -> None:
            async with open_db(db_path) as db:
                async with db.execute(
                    "SELECT id, name, surname, is_owner FROM people WHERE id = ?",
                    (person_id,),
                ) as cur:
                    person = await cur.fetchone()
                if person is None:
                    _emit_envelope(
                        error={
                            "code": "PERSON_NOT_FOUND",
                            "message": f"no person with id={person_id}",
                        }
                    )
                    return

                async with db.execute(
                    "SELECT kind, value FROM identifiers WHERE person_id = ? "
                    "ORDER BY id",
                    (person_id,),
                ) as cur:
                    idents = [
                        {"kind": r["kind"], "value": r["value"]}
                        for r in await cur.fetchall()
                    ]

                async with db.execute(
                    "SELECT mp.role, COUNT(*) AS n, MAX(m.sent_at) AS last_at "
                    "FROM message_people mp "
                    "JOIN messages m ON m.id = mp.message_id "
                    "WHERE mp.person_id = ? GROUP BY mp.role",
                    (person_id,),
                ) as cur:
                    roles: dict[str, int] = {}
                    last_at: str | None = None
                    total = 0
                    for r in await cur.fetchall():
                        roles[r["role"]] = r["n"]
                        total += r["n"]
                        if r["last_at"] is not None and (
                            last_at is None or r["last_at"] > last_at
                        ):
                            last_at = r["last_at"]

            _emit_envelope(
                data={
                    "person": {
                        "id": person["id"],
                        "name": person["name"],
                        "surname": person["surname"],
                        "is_owner": bool(person["is_owner"]),
                        "identifiers": idents,
                        "message_count": total,
                        "last_message_at": last_at,
                        "roles": roles,
                    }
                }
            )

        asyncio.run(_run_json())
        return

    async def _run() -> None:
        async with open_db(db_path) as db:
            async with db.execute(
                "SELECT name, surname, is_owner FROM people WHERE id=?", (person_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                click.echo(f"person id={person_id} not found")
                return
            click.echo(f"id: {person_id}")
            click.echo(f"name: {row['name']} {row['surname'] or ''}".rstrip())
            click.echo(f"owner: {'yes' if row['is_owner'] else 'no'}")
            async with db.execute(
                "SELECT kind, value, is_primary FROM identifiers WHERE person_id=?",
                (person_id,),
            ) as cur:
                idents = await cur.fetchall()
            click.echo("identifiers:")
            for i in idents:
                star = " *" if i["is_primary"] else ""
                click.echo(f"  - {i['kind']}: {i['value']}{star}")

    asyncio.run(_run())


@people_group.command("promote")
@click.argument("person_id", type=int)
@_db_option
def people_promote(person_id: int, db_path: Path) -> None:
    async def _run() -> None:
        async with open_db(db_path) as db:
            await db.execute(
                "UPDATE people SET is_owner=1, updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), person_id),
            )
            await db.commit()
        click.echo(f"promoted #{person_id} to owner")

    asyncio.run(_run())


@people_group.command("demote")
@click.argument("person_id", type=int)
@_db_option
def people_demote(person_id: int, db_path: Path) -> None:
    async def _run() -> None:
        async with open_db(db_path) as db:
            await db.execute(
                "UPDATE people SET is_owner=0, updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), person_id),
            )
            await db.commit()
        click.echo(f"demoted #{person_id} from owner")

    asyncio.run(_run())


@people_group.command("merge")
@click.option("--keep", "keep_id", type=int, required=True)
@click.option("--discard", "discard_id", type=int, required=True)
@_db_option
def people_merge(keep_id: int, discard_id: int, db_path: Path) -> None:
    async def _run() -> None:
        async with open_db(db_path) as db:
            await merge_people(db, keep_id=keep_id, discard_id=discard_id)
        click.echo(f"merged #{discard_id} into #{keep_id}")

    asyncio.run(_run())
