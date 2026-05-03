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

"""Microsoft OAuth handler — refresh_token → access_token via msal."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import msal

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

_REFRESH_LEEWAY = timedelta(seconds=60)


class MicrosoftOAuthHandler:
    """Resolves Microsoft OAuth refresh tokens to fresh access tokens.

    Reads ``<secrets_root>/oauth/microsoft/<account_id>.json`` containing
    ``{client_id, authority, scopes, refresh_token}``. Caches the
    access_token in memory until within 60s of expiry.
    """

    def __init__(self, secrets_root: Path) -> None:
        self._root = secrets_root
        self._cache: dict[int, tuple[str, datetime]] = {}

    def access_token(self, *, account_id: int) -> str:
        """Return a fresh access token for ``account_id``.

        Reuses a cached token until it is within 60s of expiry, then
        exchanges the refresh token via msal's
        ``acquire_token_by_refresh_token``.
        """
        cached = self._cache.get(account_id)
        if cached is not None:
            token, expires_at = cached
            if expires_at > datetime.now(UTC) + _REFRESH_LEEWAY:
                return token
        secret = self._read_secret(account_id)
        result = self._acquire_token(
            client_id=secret["client_id"],
            authority=secret["authority"],
            scopes=secret["scopes"],
            refresh_token=secret["refresh_token"],
        )
        if "access_token" not in result:
            raise RuntimeError(
                f"Microsoft token refresh failed for account_id={account_id}: "
                f"{result.get('error')}: {result.get('error_description')}"
            )
        token = str(result["access_token"])
        expires_at = datetime.now(UTC) + timedelta(
            seconds=int(result["expires_in"])
        )
        self._cache[account_id] = (token, expires_at)
        return token

    def _read_secret(self, account_id: int) -> dict[str, Any]:
        path = self._root / "oauth" / "microsoft" / f"{account_id}.json"
        data: dict[str, Any] = json.loads(path.read_text())
        return data

    def _acquire_token(
        self,
        *,
        client_id: str,
        authority: str,
        scopes: list[str],
        refresh_token: str,
    ) -> dict[str, Any]:
        app = msal.PublicClientApplication(client_id, authority=authority)
        result: dict[str, Any] = app.acquire_token_by_refresh_token(
            refresh_token, scopes=scopes,
        )
        return result
