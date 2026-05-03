# Contributing to AccountPilot

Thanks for considering a contribution. This is an early-stage project
maintained by one person; expect bumpy patches.

## Development setup

```bash
git clone https://github.com/aren13/accountpilot
cd accountpilot
pip install -e ".[dev]"
pytest -q
```

You'll need Python 3.11+. macOS or Linux. (Some tests are gated on
`sys.platform == 'darwin'` because they touch chat.db.)

## Style + tools

- **ruff** for linting + formatting (`ruff check`, `ruff format`).
- **mypy** for type checks (`mypy src/accountpilot`).
- **pytest** + **pytest-asyncio** for tests. `asyncio_mode=auto`.
- **TDD discipline:** add a failing test BEFORE the implementation.
- Conventional Commits style for commit messages
  (`feat(scope): ...`, `fix(scope): ...`, `chore: ...`, etc.).

Pre-commit hooks are configured — install with `pre-commit install`.

## Plugin contract

Plugins live under `src/accountpilot/plugins/<name>/`. Every plugin
implements a class derived from `AccountPilotPlugin` with five
async hooks: `setup`, `backfill`, `sync_once`, `daemon`, `teardown`.
Register the class via the `accountpilot.plugins` entry-point group
in `pyproject.toml`. The CLI auto-registers the plugin's
`<name>_group` Click subgroup if the plugin's `cli.py` exports one.

## Pull requests

Open against `main`. CI runs `ruff check`, `mypy`, and the test
suite on macOS + Ubuntu x Python 3.11/3.12. Keep PRs focused — one
feature or fix per PR. Reviewers may ask to split larger PRs.

## Reporting issues

Use GitHub Issues. The bug-report template asks for a minimal repro,
your OS + Python version, and a stack trace. Feature requests should
include the use case and how it differs from existing functionality.

## Code of Conduct

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By submitting a contribution you agree to license it under the
project's AGPL-3.0-or-later license.
