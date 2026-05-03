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

"""Interactive OAuth flows — separated so tests can monkeypatch them
without spinning up real browsers."""

from __future__ import annotations

from typing import Any


def google_interactive_login(
    client_config: dict[str, Any], scopes: list[str],
) -> dict[str, Any]:
    """Run Google's InstalledAppFlow; return fields needed by the
    Google OAuth handler."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    creds = flow.run_local_server(port=0, open_browser=True)
    return {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "token_uri": creds.token_uri,
        "refresh_token": creds.refresh_token,
    }


def microsoft_interactive_login(
    client_id: str, authority: str, scopes: list[str],
) -> dict[str, Any]:
    """Run msal's interactive flow; return fields needed by the
    Microsoft OAuth handler."""
    import msal

    app = msal.PublicClientApplication(client_id, authority=authority)
    result = app.acquire_token_interactive(scopes)
    if "refresh_token" not in result:
        raise RuntimeError(
            f"Microsoft interactive login did not return a refresh_token: "
            f"{result.get('error')}: {result.get('error_description')}"
        )
    return {
        "client_id": client_id,
        "authority": authority,
        "scopes": scopes,
        "refresh_token": result["refresh_token"],
    }
