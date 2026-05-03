from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from accountpilot.core.logging import configure_daemon_logging

if TYPE_CHECKING:
    from pathlib import Path


def test_configure_daemon_logging_installs_file_handler(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    configure_daemon_logging("mail", log_dir=log_dir)
    try:
        root = logging.getLogger()
        assert root.level <= logging.INFO
        # The RotatingFileHandler should write to log_dir.
        file_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)  # type: ignore[attr-defined]
        ]
        assert len(file_handlers) >= 1
        assert log_dir.exists()
        # Emit a message and verify it lands in the file.
        logging.getLogger("accountpilot.test").info("hello-from-test")
        for h in file_handlers:
            h.flush()
        log_file = log_dir / "mail.daemon.stdout.log"
        assert log_file.exists()
        assert "hello-from-test" in log_file.read_text()
    finally:
        # Clean up handlers so other tests aren't polluted.
        for h in list(root.handlers):
            root.removeHandler(h)
            h.close()


def test_configure_daemon_logging_creates_log_dir_if_missing(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "deep" / "nested" / "logs"
    assert not log_dir.exists()
    configure_daemon_logging("imessage", log_dir=log_dir)
    try:
        assert log_dir.exists()
    finally:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
            h.close()


def test_configure_daemon_logging_routes_warnings_to_stderr(
    tmp_path: Path, capsys,
) -> None:
    """WARNING+ messages should reach stderr (which launchd redirects to
    .stderr.log)."""
    configure_daemon_logging("mail", log_dir=tmp_path / "logs")
    try:
        logging.getLogger("accountpilot.test").warning("warn-flag")
        captured = capsys.readouterr()
        assert "warn-flag" in captured.err
    finally:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
            h.close()
