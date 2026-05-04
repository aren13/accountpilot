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
from importlib import resources
from pathlib import Path
from typing import Any

import click

from accountpilot.core import paths
from accountpilot.core.oauth import flow as oauth_flow

_GOOGLE_SCOPES = ["https://mail.google.com/"]
_MICROSOFT_SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All"]


def _load_client_config(provider: str, config_dir: Path) -> dict[str, Any]:
    """Resolve an OAuth client config for *provider*.

    Order:
      1. ``$ACCOUNTPILOT_CONFIG_DIR/oauth_clients/<provider>.json`` —
         explicit user override (power users with their own GCP / Azure
         app registration).
      2. The bundled ``accountpilot.oauth_clients.<provider>.json`` —
         the AccountPilot-published credentials. End users never need to
         set anything up; they just see the standard provider consent
         screen on ``accountpilot oauth login``.

    The bundled JSONs are package data; see pyproject.toml's
    ``[tool.hatch.build.targets.wheel.force-include]``.
    """
    user_path = config_dir / "oauth_clients" / f"{provider}.json"
    if user_path.exists():
        return _strip_meta(json.loads(user_path.read_text()))
    raw = (
        resources.files("accountpilot.oauth_clients")
        .joinpath(f"{provider}.json")
        .read_text(encoding="utf-8")
    )
    cfg = _strip_meta(json.loads(raw))
    if _has_unfilled_placeholder(cfg):
        raise click.UsageError(
            f"bundled oauth_clients/{provider}.json contains unreplaced "
            f"placeholders. This AccountPilot build is missing publisher "
            f"OAuth credentials. Drop a working {provider}.json at {user_path} "
            f"to override, or upgrade to a release that ships real bundled "
            f"credentials."
        )
    return cfg


def _strip_meta(cfg: dict[str, Any]) -> dict[str, Any]:
    """Drop documentation-only keys (anything starting with '_')."""
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def _has_unfilled_placeholder(cfg: dict[str, Any]) -> bool:
    """Check whether the bundled JSON still contains REPLACE_BEFORE_RELEASE."""

    def walk(value: object) -> bool:
        if isinstance(value, str):
            return value == "REPLACE_BEFORE_RELEASE"
        if isinstance(value, dict):
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return any(walk(v) for v in value)
        return False

    return walk(cfg)


def _emit_envelope(
    *, data: dict[str, Any] | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


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
@click.option("--json", "json_out", is_flag=True)
def login_google(
    account_id: int,
    config_dir: Path,
    secrets_root: Path,
    json_out: bool,
) -> None:
    """Run Google OAuth Desktop flow and persist refresh token."""
    try:
        client_config = _load_client_config("google", config_dir)
        payload = oauth_flow.google_interactive_login(
            client_config,
            scopes=_GOOGLE_SCOPES,
        )
    except Exception as exc:
        if json_out:
            _emit_envelope(error={"code": "OAUTH_FAILED", "message": str(exc)})
            return
        raise

    out = secrets_root / "oauth" / "google" / f"{account_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    out.chmod(0o600)
    if json_out:
        _emit_envelope(
            data={
                "account_id": account_id,
                "provider": "google",
                "secret_path": str(out),
            }
        )
        return
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
@click.option("--json", "json_out", is_flag=True)
def login_microsoft(
    account_id: int,
    config_dir: Path,
    secrets_root: Path,
    json_out: bool,
) -> None:
    """Run Microsoft msal interactive flow and persist refresh token."""
    try:
        client_config = _load_client_config("microsoft", config_dir)
        payload = oauth_flow.microsoft_interactive_login(
            client_id=client_config["client_id"],
            authority=client_config["authority"],
            scopes=_MICROSOFT_SCOPES,
        )
    except Exception as exc:
        if json_out:
            _emit_envelope(error={"code": "OAUTH_FAILED", "message": str(exc)})
            return
        raise

    out = secrets_root / "oauth" / "microsoft" / f"{account_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    out.chmod(0o600)
    if json_out:
        _emit_envelope(
            data={
                "account_id": account_id,
                "provider": "microsoft",
                "secret_path": str(out),
            }
        )
        return
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
