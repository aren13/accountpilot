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

"""AccountPilot plugin base class and entry-point discovery."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003 - needed for function signatures
from importlib.metadata import entry_points
from typing import Any, ClassVar

import click  # noqa: TC002 - needed for cli() return type

from accountpilot.core.auth import Secrets  # noqa: TC001 - needed for __init__


class AccountPilotPlugin(ABC):
    """Base class for AccountPilot plugins.

    A plugin handles one source (mail, imessage, ...). All accounts of that
    source are managed by a single plugin instance.
    """

    name: ClassVar[str]

    def __init__(self, config: dict[str, Any], storage: Any, secrets: Secrets) -> None:
        self.config = config
        self.storage = storage
        self.secrets = secrets

    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def backfill(
        self, account_id: int, *, since: datetime | None = None
    ) -> None: ...

    @abstractmethod
    async def sync_once(self, account_id: int) -> None: ...

    @abstractmethod
    async def daemon(self, account_id: int) -> None: ...

    @abstractmethod
    async def teardown(self) -> None: ...

    def cli(self) -> click.Group | None:
        return None


def discover_plugins() -> dict[str, type[AccountPilotPlugin]]:
    """Read `accountpilot.plugins` entry points and return name -> class map."""
    found: dict[str, type[AccountPilotPlugin]] = {}
    for ep in entry_points(group="accountpilot.plugins"):
        cls = ep.load()
        if not (isinstance(cls, type) and issubclass(cls, AccountPilotPlugin)):
            continue
        found[ep.name] = cls
    return found
