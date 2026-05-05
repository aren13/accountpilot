# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
# Licensed under AGPL-3.0-or-later.

"""accountpilot completion — emit shell completion scripts."""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class


@click.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion_cmd(shell: str) -> None:
    """Emit a shell completion script.

    Usage:
      accountpilot completion bash >> ~/.bash_completion
      accountpilot completion zsh  >> ~/.zfunc/_accountpilot
      accountpilot completion fish > ~/.config/fish/completions/accountpilot.fish
    """
    cls = get_completion_class(shell)
    if cls is None:
        raise click.UsageError(f"unsupported shell: {shell}")

    # Click expects to discover the root command. We synthesize that
    # invocation so `accountpilot completion bash` emits the right
    # script for `accountpilot`.
    from accountpilot.cli import cli as root_cli

    instance = cls(
        cli=root_cli,
        ctx_args={},
        prog_name="accountpilot",
        complete_var="_ACCOUNTPILOT_COMPLETE",
    )
    click.echo(instance.source())
