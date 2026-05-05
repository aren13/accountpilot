# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
# Licensed under AGPL-3.0-or-later.

"""accountpilot self link — bridge bundled CLI to /usr/local/bin/."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import click

from accountpilot.core.cli import exit_codes


def _emit_envelope(
    *, data: Any | None = None, error: dict[str, str] | None = None
) -> None:
    payload = {"ok": error is None, "data": data, "error": error}
    click.echo(json.dumps(payload))


def _default_source() -> Path:
    """Path to the bundled CLI shim, derived from sys.executable.

    sys.executable is the bundled python3; walk up to the .app's
    Resources/bin/accountpilot.
    Layout: Resources/python/runtime/bin/python3 → Resources/bin/accountpilot
    """
    interp = Path(sys.executable).resolve()
    return interp.parent.parent.parent.parent / "bin" / "accountpilot"


@click.group("self")
def self_group() -> None:
    """Operations on the AccountPilot install itself."""


@self_group.command("link")
@click.option(
    "--source",
    type=click.Path(path_type=Path),
    default=_default_source,
    show_default="<bundle>/Contents/Resources/bin/accountpilot",
)
@click.option(
    "--target",
    type=click.Path(path_type=Path),
    default=Path("/usr/local/bin/accountpilot"),
    show_default="/usr/local/bin/accountpilot",
)
@click.option("--json", "json_out", is_flag=True)
def self_link(source: Path, target: Path, json_out: bool) -> None:
    """Symlink target → source. Idempotent; safe to re-run."""
    if not source.exists():
        if json_out:
            _emit_envelope(
                error={
                    "code": "SOURCE_MISSING",
                    "message": f"source CLI not found at {source}",
                }
            )
            sys.exit(exit_codes.DATA_ERROR)
        raise click.ClickException(f"source CLI not found at {source}")

    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        # Already a symlink — verify it points where we want.
        if os.readlink(target) == str(source):
            if json_out:
                _emit_envelope(
                    data={
                        "source": str(source),
                        "target": str(target),
                        "created": False,
                    }
                )
                return
            click.echo(f"already linked: {target} → {source}")
            return
        # Wrong target — replace.
        target.unlink()
    elif target.exists():
        # Regular file/dir blocking the path.
        if json_out:
            _emit_envelope(
                error={
                    "code": "TARGET_EXISTS",
                    "message": (
                        f"{target} exists and is not a symlink — refusing to "
                        "overwrite. Remove it manually if intentional."
                    ),
                }
            )
            sys.exit(exit_codes.DATA_ERROR)
        raise click.ClickException(f"{target} exists and is not a symlink")

    target.symlink_to(source)

    if json_out:
        _emit_envelope(
            data={
                "source": str(source),
                "target": str(target),
                "created": True,
            }
        )
        return
    click.echo(f"linked: {target} → {source}")
