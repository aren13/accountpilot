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

"""accountpilot setup"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from accountpilot.core import paths
from accountpilot.core.cas import CASStore
from accountpilot.core.config import load_config
from accountpilot.core.db.connection import open_db
from accountpilot.core.models import Identifier
from accountpilot.core.storage import Storage


@click.command("setup")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=paths.config_path,
    show_default="$ACCOUNTPILOT_CONFIG_DIR/config.yaml",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=paths.db_path,
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
def setup_cmd(config_path: Path, db_path: Path) -> None:
    """Apply config.yaml to the DB (idempotent)."""

    cfg = load_config(config_path)
    cas_root = db_path.parent / "attachments"

    async def _run() -> None:
        async with open_db(db_path) as db:
            storage = Storage(db, CASStore(cas_root))
            owner_id_by_identifier: dict[str, int] = {}
            for owner in cfg.owners:
                pid = await storage.upsert_owner(
                    name=owner.name,
                    surname=owner.surname,
                    identifiers=[
                        Identifier(kind=i.kind, value=i.value)
                        for i in owner.identifiers
                    ],
                )
                for i in owner.identifiers:
                    owner_id_by_identifier[i.value.lower()] = pid

            for plugin_name, pcfg in cfg.plugins.items():
                if not pcfg.enabled:
                    continue
                for account in pcfg.accounts:
                    owner_pid = owner_id_by_identifier.get(account.owner.lower())
                    if owner_pid is None:
                        raise click.UsageError(
                            f"plugin '{plugin_name}' account "
                            f"{account.identifier!r} references unknown owner "
                            f"{account.owner!r} (not declared in owners[])"
                        )
                    source = account.provider or plugin_name
                    await storage.upsert_account(
                        source=source,
                        identifier=account.identifier,
                        owner_id=owner_pid,
                        credentials_ref=account.credentials_ref,
                    )
        click.echo(f"setup applied: {config_path} -> {db_path}")

    asyncio.run(_run())
