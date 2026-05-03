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

"""Subprocess client for the signed Swift FDA helper.

The helper binary is the only path that reads ~/Library/Messages/chat.db
on production installs (see helpers/fda-helper/PROTOCOL.md). This module
spawns the helper, parses its JSON-Lines output, and converts records
into the IMessageMessage model used by the rest of the plugin.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from accountpilot.core.models import (
    AttachmentBlob,
    IMessageMessage,
    IMessageService,
)
from accountpilot.plugins.imessage.attributed_body import decode_attributed_body

if TYPE_CHECKING:
    from collections.abc import Iterator

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
HELPER_BINARY_NAME = "accountpilot-fda-helper"
HELPER_OVERRIDE_ENV = "ACCOUNTPILOT_FDA_HELPER"

# Apple's epoch is 2001-01-01 UTC; chat.db `message.date` is nanoseconds
# since that epoch.
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def apple_ns_to_datetime(ns: int) -> datetime:
    """Convert Apple-Cocoa nanoseconds-since-2001 → tz-aware UTC datetime."""
    return APPLE_EPOCH + timedelta(microseconds=ns / 1000)


def datetime_to_apple_ns(dt: datetime) -> int:
    """Inverse of apple_ns_to_datetime."""
    delta = dt - APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


# ─── Exceptions ───────────────────────────────────────────────────────


class HelperError(RuntimeError):
    """Base for all FDA-helper failures."""

    code: str = "EUNKNOWN"


class HelperNotInstalledError(HelperError):
    """The helper binary could not be found on disk."""

    code = "ENOTFOUND"


class HelperPermissionError(HelperError):
    """The helper exited with EACCES — Full Disk Access not granted."""

    code = "EACCES"


class HelperUsageError(HelperError):
    """The helper rejected our CLI arguments."""

    code = "EUSAGE"


class HelperDataError(HelperError):
    """The helper hit an unexpected chat.db schema."""

    code = "EDATA"


_ERROR_CLASS_BY_CODE = {
    "EACCES": HelperPermissionError,
    "EUSAGE": HelperUsageError,
    "EDATA": HelperDataError,
    # Missing chat.db is functionally indistinguishable from FDA denied for the user.
    "ENOENT": HelperPermissionError,
}


# ─── Helper discovery ────────────────────────────────────────────────


def _dev_tree_paths() -> list[Path]:
    """Candidate helper binary paths inside an editable repo checkout."""
    here = Path(__file__).resolve()
    # src/accountpilot/plugins/imessage/helper_client.py → repo root is 5 up.
    repo_root = here.parents[4]
    base = repo_root / "helpers" / "fda-helper" / ".build"
    return [
        base / "release" / HELPER_BINARY_NAME,
        base / "arm64-apple-macosx" / "release" / HELPER_BINARY_NAME,
        base / "debug" / HELPER_BINARY_NAME,
        base / "arm64-apple-macosx" / "debug" / HELPER_BINARY_NAME,
    ]


def find_helper_binary() -> Path:
    """Locate the helper binary, raising HelperNotInstalledError on miss.

    Search order:
      1. $ACCOUNTPILOT_FDA_HELPER env override (absolute path).
      2. $PATH (homebrew shim or system install).
      3. $HOMEBREW_PREFIX/bin (in case PATH is sanitised).
      4. Dev-tree .build/{release,debug}/accountpilot-fda-helper.
    """
    override = os.environ.get(HELPER_OVERRIDE_ENV)
    if override:
        p = Path(override).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
        raise HelperNotInstalledError(
            f"{HELPER_OVERRIDE_ENV}={override!r} does not point to an executable file"
        )

    on_path = shutil.which(HELPER_BINARY_NAME)
    if on_path:
        return Path(on_path)

    brew_prefix = os.environ.get("HOMEBREW_PREFIX") or "/opt/homebrew"
    brew_candidate = Path(brew_prefix) / "bin" / HELPER_BINARY_NAME
    if brew_candidate.is_file() and os.access(brew_candidate, os.X_OK):
        return brew_candidate

    for candidate in _dev_tree_paths():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise HelperNotInstalledError(
        f"could not find {HELPER_BINARY_NAME} on PATH, in $HOMEBREW_PREFIX/bin, or in "
        f"the local dev tree. Install via `brew install aren13/tap/accountpilot` or "
        f"build from source under helpers/fda-helper/."
    )


# ─── Subprocess invocation ───────────────────────────────────────────


def _raise_from_stderr(returncode: int, stderr: str, fallback: str) -> None:
    """Parse the helper's error envelope (last JSON line of stderr) and raise."""
    envelope: dict[str, Any] = {}
    for line in reversed(stderr.splitlines()):
        line = line.strip()  # noqa: PLW2901 — intentional rebind in narrow loop
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "error":
            envelope = obj
            break
    code = str(envelope.get("code", "EUNKNOWN"))
    message = str(envelope.get("message", fallback))
    cls = _ERROR_CLASS_BY_CODE.get(code, HelperError)
    raise cls(f"[{code}] {message} (helper exit={returncode})")


def iter_records(
    *,
    chat_db_path: Path | None = None,
    since_ns: int | None = None,
    helper_path: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Spawn the helper and yield one parsed JSON record per stdout line.

    Records have shape `{v: 1, type: "message", ...}`. See PROTOCOL.md.

    Raises HelperPermissionError on EACCES (missing FDA grant), and other
    HelperError subclasses on protocol/usage/data errors.
    """
    binary = helper_path or find_helper_binary()
    args: list[str] = [str(binary), "read-imessages"]
    if since_ns is not None:
        args += ["--since-ns", str(since_ns)]
    if chat_db_path is not None:
        args += ["--db", str(chat_db_path)]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    try:
        for line in proc.stdout:
            line = line.strip()  # noqa: PLW2901
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                proc.kill()
                proc.wait()
                raise HelperDataError(f"helper emitted invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                proc.kill()
                proc.wait()
                raise HelperDataError(f"helper emitted non-object record: {obj!r}")
            if obj.get("v") != PROTOCOL_VERSION:
                proc.kill()
                proc.wait()
                raise HelperDataError(
                    f"helper protocol version mismatch: got v={obj.get('v')!r}, "
                    f"expected {PROTOCOL_VERSION}"
                )
            yield obj
    finally:
        stderr_buf = proc.stderr.read() or ""
        returncode = proc.wait()
        if returncode != 0:
            _raise_from_stderr(returncode, stderr_buf, fallback="helper failed")


# ─── Record → model conversion ───────────────────────────────────────


def _attachment_from_record(item: dict[str, Any]) -> AttachmentBlob:
    return AttachmentBlob(
        filename=str(item["filename"]),
        content=base64.b64decode(item["content_b64"]),
        mime_type=item.get("mime_type"),
    )


def record_to_imessage(record: dict[str, Any], *, account_id: int) -> IMessageMessage:
    """Convert one helper record (dict) into an IMessageMessage.

    Mirrors the shape produced by `accountpilot-fda-helper read-imessages`,
    documented in PROTOCOL.md.
    """
    if record.get("type") != "message":
        raise HelperDataError(f"expected type=message, got {record.get('type')!r}")

    body_text = record.get("text") or ""
    if not body_text and record.get("attributed_body_b64"):
        # Apple stores rich-content message bodies (replies, link previews,
        # attachments-only) in attributedBody with text=NULL. Decode via
        # pytypedstream to recover them.
        body_text = decode_attributed_body(
            base64.b64decode(record["attributed_body_b64"])
        )

    svc_raw = record.get("service") or "iMessage"
    service: IMessageService = "iMessage" if svc_raw in {"iMessage", "RCS"} else "SMS"

    sent_at = apple_ns_to_datetime(int(record["date_ns"]))
    date_read_ns = record.get("date_read_ns")
    date_read = apple_ns_to_datetime(int(date_read_ns)) if date_read_ns else None

    attachments_raw = record.get("attachments") or []
    attachments = [_attachment_from_record(item) for item in attachments_raw]

    return IMessageMessage(
        account_id=account_id,
        external_id=str(record["guid"]),
        sent_at=sent_at,
        direction="outbound" if record.get("is_from_me") else "inbound",
        sender_handle=str(record["sender_handle"]),
        chat_guid=str(record["chat_guid"]),
        participants=[str(p) for p in record.get("participants", [])],
        body_text=body_text,
        service=service,
        is_read=bool(record.get("is_read")),
        date_read=date_read,
        attachments=attachments,
    )
