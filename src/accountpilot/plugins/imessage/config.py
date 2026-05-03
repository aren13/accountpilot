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

"""iMessage plugin config models.

The global config loader hands the `plugins.imessage` sub-tree to
IMessagePluginConfig.model_validate(...). iMessage is single-account-
per-machine in v1 (the local user's chat.db).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _default_chat_db_path() -> Path:
    return Path.home() / "Library" / "Messages" / "chat.db"


class IMessageAccountConfig(_StrictBase):
    identifier: str
    owner: str
    chat_db_path: Path = Field(default_factory=_default_chat_db_path)


class IMessagePluginConfig(_StrictBase):
    accounts: list[IMessageAccountConfig] = Field(default_factory=list)
    debounce_seconds: float = 2.0
    backfill_chunk: int = 500
