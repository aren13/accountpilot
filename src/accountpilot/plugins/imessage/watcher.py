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

"""Watch chat.db for modifications, with debounce."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)


class _DebouncedChatDbHandler(FileSystemEventHandler):
    """Fires `on_change` no more than once per `debounce_seconds`."""

    def __init__(
        self,
        target_path: Path,
        on_change: Callable[[], None],
        debounce_seconds: float,
    ) -> None:
        self._target = target_path.resolve()
        self._on_change = on_change
        self._debounce = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _fire(self) -> None:
        try:
            self._on_change()
        except Exception:  # noqa: BLE001
            log.exception("chat.db on_change callback raised")

    def _schedule(self) -> None:
        with self._lock:
            if self._timer is not None and self._timer.is_alive():
                return  # already scheduled — collapse this event
            self._timer = threading.Timer(self._debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # chat.db's directory may also see writes to chat.db-wal /
        # chat.db-shm (SQLite WAL files). Treat those as relevant too.
        path = Path(str(event.src_path)).resolve()
        if path.name in {self._target.name,
                         self._target.name + "-wal",
                         self._target.name + "-shm"}:
            self._schedule()

    on_created = on_modified  # WAL files may be (re)created mid-write


class ChatDbWatcher:
    """File-watcher around `chat_db_path` with debounced `on_change`.

    Also polls `chat_db_path.stat().st_ino` every `inode_poll_seconds` and
    restarts the underlying watchdog Observer if the inode changes. This
    works around macOS FSEvents losing its watch after SQLite's
    `PRAGMA wal_checkpoint(TRUNCATE)` recreates chat.db / chat.db-wal with
    new inodes (observed during AP-SP2 hardware acceptance).
    """

    def __init__(
        self,
        chat_db_path: Path,
        on_change: Callable[[], None],
        debounce_seconds: float = 2.0,
        inode_poll_seconds: float = 30.0,
    ) -> None:
        self._chat_db = chat_db_path.resolve()
        self._handler = _DebouncedChatDbHandler(
            self._chat_db, on_change, debounce_seconds,
        )
        self._observer: Observer | None = None  # type: ignore[valid-type]
        self._inode_poll_seconds = inode_poll_seconds
        self._inode: int | None = None
        self._inode_timer: threading.Timer | None = None
        # Public — observability for tests / logs.
        self.observer_restart_count = 0

    def start(self) -> None:
        if self._observer is not None:
            return
        self._observer = self._build_observer()
        self._inode = self._stat_inode()
        self._schedule_inode_check()
        log.info(
            "chat.db watcher started on %s (inode=%s)",
            self._chat_db,
            self._inode,
        )

    def stop(self) -> None:
        if self._inode_timer is not None:
            self._inode_timer.cancel()
            self._inode_timer = None
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None
        log.info("chat.db watcher stopped")

    def _build_observer(self) -> Observer:  # type: ignore[valid-type]
        obs = Observer()
        obs.schedule(self._handler, str(self._chat_db.parent), recursive=False)
        obs.start()
        return obs

    def _stat_inode(self) -> int | None:
        try:
            return self._chat_db.stat().st_ino
        except FileNotFoundError:
            return None

    def _schedule_inode_check(self) -> None:
        t = threading.Timer(self._inode_poll_seconds, self._check_inode_now)
        t.daemon = True
        t.start()
        self._inode_timer = t

    def _check_inode_now(self) -> None:
        current = self._stat_inode()
        if current is not None and current != self._inode:
            log.warning(
                "chat.db inode changed (%s -> %s); restarting Observer",
                self._inode,
                current,
            )
            self._inode = current
            if self._observer is not None:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            self._observer = self._build_observer()
            self.observer_restart_count += 1
        # Reschedule if still running.
        if self._observer is not None:
            self._schedule_inode_check()
