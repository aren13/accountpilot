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

"""accountpilot config — one-shot YAML→DB migration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from accountpilot.core import paths
from accountpilot.core.cas import CASStore
from accountpilot.core.config import load_config
from accountpilot.core.db.connection import open_db
from accountpilot.core.models import Identifier
from accountpilot.core.storage import Storage


def _emit_envelope(
    *, data: object | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


@click.group("config")
def config_group() -> None:
    """Configuration migration commands."""


@config_group.command("import")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=lambda: paths.config_dir() / "config.yaml",
    show_default="$ACCOUNTPILOT_CONFIG_DIR/config.yaml",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=lambda: paths.data_dir() / "accountpilot.db",
    show_default="$ACCOUNTPILOT_DATA_DIR/accountpilot.db",
)
@click.option("--json", "json_out", is_flag=True)
def config_import(config_path: Path, db_path: Path, json_out: bool) -> None:
    """Import accounts from config.yaml into the DB, then rename it.

    The YAML is renamed to ``config.yaml.imported`` to make this a
    one-shot operation: subsequent calls become no-ops, so the Swift
    app can invoke it unconditionally on every launch.
    """
    if not config_path.exists():
        if json_out:
            _emit_envelope(
                data={"accounts_imported": 0, "renamed_to": None, "noop": True}
            )
            return
        click.echo(f"no config at {config_path}; nothing to import")
        return

    cas_root = db_path.parent / "attachments"
    cfg = load_config(config_path)

    async def _run() -> int:
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

            count = 0
            for plugin_name, pcfg in cfg.plugins.items():
                if not pcfg.enabled:
                    continue
                for account in pcfg.accounts:
                    owner_pid = owner_id_by_identifier.get(account.owner.lower())
                    if owner_pid is None:
                        raise click.ClickException(
                            f"plugin {plugin_name!r} account "
                            f"{account.identifier!r} references unknown owner "
                            f"{account.owner!r}"
                        )
                    source = account.provider or plugin_name
                    await storage.upsert_account(
                        source=source,
                        identifier=account.identifier,
                        owner_id=owner_pid,
                        credentials_ref=account.credentials_ref,
                    )
                    count += 1
            return count

    accounts_imported = asyncio.run(_run())
    renamed = config_path.with_suffix(config_path.suffix + ".imported")
    config_path.rename(renamed)

    if json_out:
        _emit_envelope(
            data={
                "accounts_imported": accounts_imported,
                "renamed_to": str(renamed),
                "noop": False,
            }
        )
        return
    click.echo(
        f"imported {accounts_imported} account(s); "
        f"renamed {config_path.name} → {renamed.name}"
    )
