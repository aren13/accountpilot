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

"""Google OAuth handler — refresh_token → access_token with cache."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

_REFRESH_LEEWAY = timedelta(seconds=60)


class GoogleOAuthHandler:
    """Resolves Google OAuth refresh tokens to fresh access tokens.

    Reads ``<secrets_root>/google/<account_id>.json`` containing
    ``{refresh_token, client_id, client_secret, token_uri}``. Caches the
    access_token in memory until within 60s of expiry.
    """

    def __init__(self, secrets_root: Path) -> None:
        self._root = secrets_root
        self._cache: dict[int, tuple[str, datetime]] = {}

    def access_token(self, *, account_id: int) -> str:
        """Return a fresh access token for ``account_id``.

        Reuses a cached token until it is within 60s of expiry, then
        exchanges the refresh token at the configured ``token_uri``.
        """
        cached = self._cache.get(account_id)
        if cached is not None:
            token, expires_at = cached
            if expires_at > datetime.now(UTC) + _REFRESH_LEEWAY:
                return token
        secret = self._read_secret(account_id)
        resp = self._post_token_endpoint(
            client_id=secret["client_id"],
            client_secret=secret["client_secret"],
            refresh_token=secret["refresh_token"],
            grant_type="refresh_token",
            token_uri=secret["token_uri"],
        )
        token = str(resp["access_token"])
        expires_at = datetime.now(UTC) + timedelta(seconds=int(resp["expires_in"]))
        self._cache[account_id] = (token, expires_at)
        return token

    def _read_secret(self, account_id: int) -> dict[str, Any]:
        path = self._root / "oauth" / "google" / f"{account_id}.json"
        data: dict[str, Any] = json.loads(path.read_text())
        return data

    def _post_token_endpoint(
        self, *, token_uri: str, **kwargs: str,
    ) -> dict[str, Any]:
        body = urllib.parse.urlencode(kwargs).encode()
        req = urllib.request.Request(token_uri, data=body, method="POST")  # noqa: S310
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return dict(data)
