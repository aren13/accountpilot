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

"""YAML config loader with Pydantic validation."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - used in load_config signature and body
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from accountpilot.core.models import (
    IdentifierKind,  # noqa: TC001 - used for Pydantic validation
)


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentifierEntry(_StrictBase):
    kind: IdentifierKind
    value: str


class OwnerEntry(_StrictBase):
    name: str
    surname: str | None = None
    identifiers: list[IdentifierEntry]


class AccountEntry(_StrictBase):
    identifier: str
    owner: str
    provider: Literal["gmail", "outlook", "imap-generic"] | None = None
    credentials_ref: str | None = None
    chat_db_path: str | None = None  # iMessage-specific


class PluginConfig(_StrictBase):
    enabled: bool = True
    accounts: list[AccountEntry] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Config(_StrictBase):
    version: Literal[1]
    owners: list[OwnerEntry]
    plugins: dict[str, PluginConfig] = Field(default_factory=dict)


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        raise ValueError(f"invalid config at {path}: {e}") from e
