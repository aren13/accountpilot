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

"""accountpilot oauth — interactive OAuth login + secret management."""

from __future__ import annotations

import json
from pathlib import Path

import click

from accountpilot.core import paths
from accountpilot.core.oauth import flow as oauth_flow

_GOOGLE_SCOPES = ["https://mail.google.com/"]
_MICROSOFT_SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All"]


@click.group("oauth")
def oauth_group() -> None:
    """Interactive OAuth login + secret management."""


@oauth_group.group("login")
def login_group() -> None:
    """Run an interactive browser OAuth flow."""


@login_group.command("google")
@click.argument("account_id", type=int)
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=paths.config_dir,
    show_default="$ACCOUNTPILOT_CONFIG_DIR",
)
@click.option(
    "--secrets-root",
    type=click.Path(path_type=Path),
    default=paths.secrets_dir,
    show_default="$ACCOUNTPILOT_DATA_DIR/secrets",
)
def login_google(account_id: int, config_dir: Path, secrets_root: Path) -> None:
    """Run Google OAuth Desktop flow and persist refresh token."""
    client_path = config_dir / "oauth_clients" / "google.json"
    if not client_path.exists():
        raise click.UsageError(
            f"missing oauth_clients/google.json at {client_path}\n"
            f"Download an OAuth Desktop client JSON from Google Cloud "
            f"Console and save it there."
        )
    client_config = json.loads(client_path.read_text())
    payload = oauth_flow.google_interactive_login(
        client_config,
        scopes=_GOOGLE_SCOPES,
    )
    out = secrets_root / "oauth" / "google" / f"{account_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    out.chmod(0o600)
    click.echo(f"oauth login: account={account_id} provider=google → {out}")


@login_group.command("microsoft")
@click.argument("account_id", type=int)
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=paths.config_dir,
    show_default="$ACCOUNTPILOT_CONFIG_DIR",
)
@click.option(
    "--secrets-root",
    type=click.Path(path_type=Path),
    default=paths.secrets_dir,
    show_default="$ACCOUNTPILOT_DATA_DIR/secrets",
)
def login_microsoft(
    account_id: int,
    config_dir: Path,
    secrets_root: Path,
) -> None:
    """Run Microsoft msal interactive flow and persist refresh token."""
    client_path = config_dir / "oauth_clients" / "microsoft.json"
    if not client_path.exists():
        raise click.UsageError(
            f"missing oauth_clients/microsoft.json at {client_path}\n"
            f"Create it manually with the client_id + authority from your "
            f"Azure AD app registration."
        )
    client_config = json.loads(client_path.read_text())
    payload = oauth_flow.microsoft_interactive_login(
        client_id=client_config["client_id"],
        authority=client_config["authority"],
        scopes=_MICROSOFT_SCOPES,
    )
    out = secrets_root / "oauth" / "microsoft" / f"{account_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    out.chmod(0o600)
    click.echo(f"oauth login: account={account_id} provider=microsoft → {out}")


@oauth_group.command("status")
@click.option(
    "--secrets-root",
    type=click.Path(path_type=Path),
    default=paths.secrets_dir,
    show_default="$ACCOUNTPILOT_DATA_DIR/secrets",
)
def status(secrets_root: Path) -> None:
    """List which oauth secret files are present."""
    base = secrets_root / "oauth"
    if not base.exists():
        click.echo("no oauth secrets present")
        return
    for provider_dir in sorted(base.iterdir()):
        if not provider_dir.is_dir():
            continue
        for f in sorted(provider_dir.glob("*.json")):
            click.echo(f"  {provider_dir.name}/{f.stem}: {f}")


@oauth_group.command("revoke")
@click.argument("provider", type=click.Choice(["google", "microsoft"]))
@click.argument("account_id", type=int)
@click.option(
    "--secrets-root",
    type=click.Path(path_type=Path),
    default=paths.secrets_dir,
    show_default="$ACCOUNTPILOT_DATA_DIR/secrets",
)
def revoke(provider: str, account_id: int, secrets_root: Path) -> None:
    """Delete the local oauth secret file for an account."""
    f = secrets_root / "oauth" / provider / f"{account_id}.json"
    if not f.exists():
        raise click.UsageError(f"no secret at {f}")
    f.unlink()
    click.echo(f"oauth revoke: removed {f}")
