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

"""Mail-plugin-specific config models.

The global config loader (accountpilot.core.config) hands the `plugins.mail`
sub-tree to MailPluginConfig.model_validate(...). This module owns the
mail-specific shape; the global loader stays source-agnostic.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


MailProvider = Literal["gmail", "outlook", "imap-generic"]
MailAuthMethod = Literal["password", "oauth"]


class MailAccountConfig(_StrictBase):
    identifier: str
    owner: str
    provider: MailProvider
    auth_method: MailAuthMethod = "password"
    credentials_ref: str | None = None
    # OAuth-specific (only meaningful when auth_method='oauth'):
    oauth_client_id: str | None = None
    oauth_tenant: str | None = None


class MailPluginConfig(_StrictBase):
    accounts: list[MailAccountConfig] = Field(default_factory=list)
    idle_timeout_seconds: int = 1740   # ~29 min; IMAP RFC requires <30
    batch_size: int = 100              # how many UIDs to fetch per chunk
