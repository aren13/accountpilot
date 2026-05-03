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

"""OS-correct paths for AccountPilot data, config, logs, cache.

Resolves through platformdirs by default (XDG-Base on Linux,
Apple-style ~/Library/... on macOS). Per-directory env vars override
for tests and advanced users:

  ACCOUNTPILOT_DATA_DIR    — accountpilot.db + attachments/ live here
  ACCOUNTPILOT_CONFIG_DIR  — config.yaml lives here
  ACCOUNTPILOT_LOG_DIR     — daemon logs land here
  ACCOUNTPILOT_CACHE_DIR   — transient caches (Xapian, etc.)

These are intentionally not coupled to ``Path.home()``; CI runners,
Linux distros, and packagers may map them anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import PlatformDirs

_DIRS = PlatformDirs(appname="accountpilot", appauthor=False)


def _env_or(env_key: str, default: str) -> Path:
    raw = os.environ.get(env_key)
    return Path(raw) if raw else Path(default)


def data_dir() -> Path:
    return _env_or("ACCOUNTPILOT_DATA_DIR", _DIRS.user_data_dir)


def config_dir() -> Path:
    return _env_or("ACCOUNTPILOT_CONFIG_DIR", _DIRS.user_config_dir)


def log_dir() -> Path:
    return _env_or("ACCOUNTPILOT_LOG_DIR", _DIRS.user_log_dir)


def cache_dir() -> Path:
    return _env_or("ACCOUNTPILOT_CACHE_DIR", _DIRS.user_cache_dir)


def db_path() -> Path:
    return data_dir() / "accountpilot.db"


def attachments_dir() -> Path:
    return data_dir() / "attachments"


def config_path() -> Path:
    return config_dir() / "config.yaml"


def secrets_dir() -> Path:
    return data_dir() / "secrets"
