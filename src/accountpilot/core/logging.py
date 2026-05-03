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

"""Daemon logging configuration.

Daemon entry points (mail_daemon, imessage_daemon) call
configure_daemon_logging() before running their asyncio loops. This
installs a RotatingFileHandler (10MB x 5 backups) on the root logger
for INFO+ messages, plus a StreamHandler(sys.stderr) for WARNING+
so launchd / systemd's stderr redirection captures problems.

Without this helper, log.info/log.warning calls throughout the
codebase emit nowhere - the SP2 acceptance bug.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def configure_daemon_logging(plugin: str, *, log_dir: Path) -> None:
    """Install file + stderr handlers on the root logger.

    Args:
        plugin: short name like "mail" or "imessage" - used to derive
            the log filename `<plugin>.daemon.stdout.log`.
        log_dir: directory to write the rotating log file. Created if
            absent.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{plugin}.daemon.stdout.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    err_handler = logging.StreamHandler(sys.stderr)
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(err_handler)
