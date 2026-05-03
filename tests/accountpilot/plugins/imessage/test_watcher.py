from __future__ import annotations

import asyncio
import threading
from pathlib import Path  # noqa: TC003 (used at runtime in fixture parameter)

import pytest

from accountpilot.plugins.imessage.watcher import ChatDbWatcher


@pytest.mark.asyncio
async def test_watcher_fires_on_chat_db_modification(tmp_path: Path) -> None:
    chat_db = tmp_path / "chat.db"
    chat_db.write_bytes(b"")

    fired = asyncio.Event()
    fire_count = 0
    loop = asyncio.get_running_loop()

    def on_change() -> None:
        nonlocal fire_count
        fire_count += 1
        loop.call_soon_threadsafe(fired.set)

    watcher = ChatDbWatcher(chat_db, on_change=on_change, debounce_seconds=0.1)
    watcher.start()
    try:
        # Modify in a separate thread to avoid blocking on the watcher.
        def _touch() -> None:
            chat_db.write_bytes(b"changed")
        threading.Timer(0.05, _touch).start()
        await asyncio.wait_for(fired.wait(), timeout=2.0)
    finally:
        watcher.stop()

    assert fire_count >= 1


@pytest.mark.asyncio
async def test_watcher_debounces_rapid_modifications(tmp_path: Path) -> None:
    chat_db = tmp_path / "chat.db"
    chat_db.write_bytes(b"")

    fired = threading.Event()
    fire_count = 0

    def on_change() -> None:
        nonlocal fire_count
        fire_count += 1
        fired.set()

    watcher = ChatDbWatcher(chat_db, on_change=on_change, debounce_seconds=0.3)
    watcher.start()
    try:
        # 5 rapid writes inside the debounce window → at most 1-2 fires.
        for i in range(5):
            chat_db.write_bytes(f"v{i}".encode())
            await asyncio.sleep(0.02)
        # Wait past the debounce window for any trailing fire.
        await asyncio.sleep(0.5)
    finally:
        watcher.stop()

    # We accept 1 OR 2 fires (depends on whether the burst started a new
    # debounce window mid-flight). The point is "many fewer than 5".
    assert 1 <= fire_count <= 2


def test_chatdb_watcher_restarts_observer_on_inode_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When chat.db's inode changes (simulated by deleting + recreating
    the file), the watcher detects it on its next poll and restarts the
    Observer."""
    chat_db = tmp_path / "chat.db"
    chat_db.write_bytes(b"v1")

    # Use a very large inode_poll_seconds so the Timer never fires during
    # the test — we'll trigger the inode check manually.
    watcher = ChatDbWatcher(
        chat_db,
        on_change=lambda: None,
        debounce_seconds=0.1,
        inode_poll_seconds=3600.0,
    )

    watcher.start()
    try:
        original_inode = watcher._inode  # noqa: SLF001 — test-only seam

        # Recreate the file to (best-effort) force a new inode.
        chat_db.unlink()
        chat_db.write_bytes(b"v2")

        # Robust path: monkeypatch the watcher's own _stat_inode seam to
        # return a different inode regardless of underlying filesystem
        # behavior (tmpfs/HFS+ don't always allocate a new inode on
        # unlink+rewrite).
        fake_inode = (original_inode or 0) + 12345
        monkeypatch.setattr(
            watcher, "_stat_inode", lambda: fake_inode,
        )

        # Trigger the inode check directly.
        watcher._check_inode_now()  # noqa: SLF001 — test-only seam

        assert watcher.observer_restart_count == 1
        assert watcher._inode == fake_inode  # noqa: SLF001
    finally:
        watcher.stop()
