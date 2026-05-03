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

"""Credential resolution.

Instance-method ``Secrets.resolve(uri)`` recognizes:

- ``password_cmd:<shell cmd>`` — run via shell, return stripped stdout
- ``oauth:google:<account_id>`` — read refresh-token JSON, exchange
  for fresh access token (cached until 60s before expiry)
- ``oauth:microsoft:<account_id>`` — same shape, msal-backed (Task 3)
- anything else — pass through as a literal credential
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from accountpilot.core import paths as _paths
from accountpilot.core.oauth.google import GoogleOAuthHandler
from accountpilot.core.oauth.microsoft import MicrosoftOAuthHandler

if TYPE_CHECKING:
    from pathlib import Path

_CMD_SCHEME = "password_cmd:"
_OAUTH_GOOGLE = "oauth:google:"
_OAUTH_MICROSOFT = "oauth:microsoft:"


@dataclass
class Secrets:
    """In-memory credential registry plus URI resolver with handler cache."""

    values: dict[str, str]
    secrets_root: Path = field(default_factory=lambda: _paths.secrets_dir())
    _google_handler: GoogleOAuthHandler = field(init=False, repr=False)
    _microsoft_handler: MicrosoftOAuthHandler = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._google_handler = GoogleOAuthHandler(self.secrets_root)
        self._microsoft_handler = MicrosoftOAuthHandler(self.secrets_root)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the value registered for ``key``, or ``default`` if absent."""
        return self.values.get(key, default)

    def resolve(self, uri: str) -> str:
        """Resolve a credential URI to its plaintext value.

        - ``oauth:google:<account_id>``: exchange the stored refresh token
          for a fresh access token (cached in-process).
        - ``oauth:microsoft:<account_id>``: same shape, msal-backed.
        - ``password_cmd:<shell cmd>``: run via the shell, return stripped
          stdout. Non-zero exit raises RuntimeError with stderr.
        - anything else: return unchanged (treated as a literal credential).
        """
        if uri.startswith(_OAUTH_GOOGLE):
            account_id = int(uri[len(_OAUTH_GOOGLE):])
            return self._google_handler.access_token(account_id=account_id)
        if uri.startswith(_OAUTH_MICROSOFT):
            account_id = int(uri[len(_OAUTH_MICROSOFT):])
            return self._microsoft_handler.access_token(account_id=account_id)
        if uri.startswith(_CMD_SCHEME):
            return self._resolve_password_cmd(uri[len(_CMD_SCHEME):])
        return uri

    @staticmethod
    def _resolve_password_cmd(cmd: str) -> str:
        try:
            result = subprocess.run(  # noqa: S602 — intentional shell exec
                cmd,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"password_cmd timed out after 30s: {shlex.quote(cmd)}"
            ) from e
        if result.returncode != 0:
            raise RuntimeError(
                f"password_cmd exit {result.returncode}: "
                f"{shlex.quote(cmd)}\nstderr: {result.stderr.strip()}"
            )
        return result.stdout.strip()
