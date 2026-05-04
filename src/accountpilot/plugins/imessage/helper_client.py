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
import contextlib
import ctypes
import ctypes.util
import io
import json
import logging
import os
import platform
import shutil
import signal
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
DISABLE_DISCLAIM_ENV = "ACCOUNTPILOT_DISABLE_DISCLAIM"

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


# ─── TCC responsibility-disclaim spawn ───────────────────────────────
#
# macOS attributes TCC checks (Full Disk Access, etc.) to the
# *responsible process*, which by default is the parent of any newly
# spawned child. When the AccountPilot Python daemon (which has no FDA
# grant — Python's cdhash changes on every brew upgrade, exactly the
# problem the helper exists to solve) spawns the helper via plain
# `subprocess.Popen`, TCC asks "does the parent (Python) have FDA?",
# the answer is no, and the helper either hangs on a TCC prompt the
# user never sees (under launchd) or denies outright.
#
# `responsibility_spawnattrs_setdisclaim(1)` (Apple-private but stable
# since macOS 10.14, used by Homebrew, sudo, and Python's own
# subprocess code in some paths) tells the kernel to make the child
# its own responsible process. With disclaim set, TCC checks the
# helper's signed identity against its own FDA grant — exactly what
# the signed-helper architecture relies on.
#
# Without this call, the helper architecture is structurally broken on
# launchd-supervised installs.


_LIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def _bind_libc_symbols() -> None:
    """Declare argtypes/restype for every libc call we make.

    Without these, ctypes guesses int-sized args/returns, which produces
    SIGSEGV on arm64 where pointer args must be passed as full 64-bit
    values.
    """
    voidpp = ctypes.POINTER(ctypes.c_void_p)

    _LIBC.posix_spawn_file_actions_init.argtypes = [voidpp]
    _LIBC.posix_spawn_file_actions_init.restype = ctypes.c_int
    _LIBC.posix_spawn_file_actions_destroy.argtypes = [voidpp]
    _LIBC.posix_spawn_file_actions_destroy.restype = ctypes.c_int
    _LIBC.posix_spawn_file_actions_addclose.argtypes = [voidpp, ctypes.c_int]
    _LIBC.posix_spawn_file_actions_addclose.restype = ctypes.c_int
    _LIBC.posix_spawn_file_actions_adddup2.argtypes = [
        voidpp,
        ctypes.c_int,
        ctypes.c_int,
    ]
    _LIBC.posix_spawn_file_actions_adddup2.restype = ctypes.c_int

    _LIBC.posix_spawnattr_init.argtypes = [voidpp]
    _LIBC.posix_spawnattr_init.restype = ctypes.c_int
    _LIBC.posix_spawnattr_destroy.argtypes = [voidpp]
    _LIBC.posix_spawnattr_destroy.restype = ctypes.c_int

    _LIBC.posix_spawn.argtypes = [
        ctypes.POINTER(ctypes.c_int),  # pid_t *
        ctypes.c_char_p,  # path
        voidpp,  # file_actions *
        voidpp,  # attrp *
        ctypes.POINTER(ctypes.c_char_p),  # argv
        ctypes.POINTER(ctypes.c_char_p),  # envp
    ]
    _LIBC.posix_spawn.restype = ctypes.c_int


_bind_libc_symbols()


def _resolve_disclaim_symbol() -> Any | None:
    """Return the disclaim symbol, or None on platforms missing it."""
    if platform.system() != "Darwin":
        return None
    if os.environ.get(DISABLE_DISCLAIM_ENV) == "1":
        return None
    try:
        sym = _LIBC.responsibility_spawnattrs_setdisclaim
    except AttributeError:
        return None
    sym.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
    sym.restype = ctypes.c_int
    return sym


_DISCLAIM = _resolve_disclaim_symbol()


def _spawn_helper(args: list[str]) -> subprocess.Popen[str] | _DisclaimedProcess:
    """Spawn the helper with TCC responsibility disclaimed when possible.

    On macOS, uses posix_spawn with `responsibility_spawnattrs_setdisclaim(1)`
    so the helper becomes its own TCC responsible process. On other
    platforms (or when the disclaim symbol is missing), falls back to
    `subprocess.Popen`.
    """
    if _DISCLAIM is None:
        return subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    return _DisclaimedProcess(args)


class _DisclaimedProcess:
    """subprocess.Popen-compatible wrapper around posix_spawn + disclaim.

    Exposes only the subset of the Popen surface that `iter_records`
    relies on: `.stdout`, `.stderr`, `.wait()`, `.kill()`, `.poll()`,
    `.returncode`. Stdout/stderr are line-buffered text streams.
    """

    def __init__(self, args: list[str]) -> None:
        # Pipes for the child's stdout/stderr.
        out_r, out_w = os.pipe()
        err_r, err_w = os.pipe()

        # posix_spawn_file_actions: dup pipe write ends onto fd 1 and 2,
        # close the read ends in the child.
        actions = ctypes.c_void_p()
        actions_p = ctypes.byref(actions)
        _check(_LIBC.posix_spawn_file_actions_init(actions_p))
        try:
            _check(_LIBC.posix_spawn_file_actions_addclose(actions_p, out_r))
            _check(_LIBC.posix_spawn_file_actions_addclose(actions_p, err_r))
            _check(_LIBC.posix_spawn_file_actions_adddup2(actions_p, out_w, 1))
            _check(_LIBC.posix_spawn_file_actions_adddup2(actions_p, err_w, 2))
            _check(_LIBC.posix_spawn_file_actions_addclose(actions_p, out_w))
            _check(_LIBC.posix_spawn_file_actions_addclose(actions_p, err_w))

            # posix_spawnattr with disclaim=1.
            attr = ctypes.c_void_p()
            attr_p = ctypes.byref(attr)
            _check(_LIBC.posix_spawnattr_init(attr_p))
            try:
                assert _DISCLAIM is not None  # narrowed by caller
                rc = _DISCLAIM(attr_p, 1)
                if rc != 0:
                    raise OSError(rc, "responsibility_spawnattrs_setdisclaim failed")

                argv = [a.encode() for a in args]
                argv_arr = (ctypes.c_char_p * (len(argv) + 1))(*argv, None)
                envv = [f"{k}={v}".encode() for k, v in os.environ.items()]
                env_arr = (ctypes.c_char_p * (len(envv) + 1))(*envv, None)

                pid = ctypes.c_int(0)
                rc = _LIBC.posix_spawn(
                    ctypes.byref(pid),
                    argv[0],
                    actions_p,
                    attr_p,
                    argv_arr,
                    env_arr,
                )
                if rc != 0:
                    raise OSError(rc, f"posix_spawn({args[0]!r}) failed")
                self.pid = pid.value
            finally:
                _LIBC.posix_spawnattr_destroy(attr_p)
        finally:
            _LIBC.posix_spawn_file_actions_destroy(actions_p)
            # Parent closes the write ends — child has its own copies.
            os.close(out_w)
            os.close(err_w)

        self.args = args
        self.returncode: int | None = None
        self.stdout: io.TextIOWrapper = io.TextIOWrapper(
            io.FileIO(out_r, mode="r", closefd=True),
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
        self.stderr: io.TextIOWrapper = io.TextIOWrapper(
            io.FileIO(err_r, mode="r", closefd=True),
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )

    def _reap(self, status: int) -> int:
        if os.WIFEXITED(status):
            self.returncode = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            self.returncode = -os.WTERMSIG(status)
        else:
            self.returncode = -1
        return self.returncode

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        wpid, status = os.waitpid(self.pid, os.WNOHANG)
        if wpid == 0:
            return None
        return self._reap(status)

    def wait(self) -> int:
        if self.returncode is not None:
            return self.returncode
        _, status = os.waitpid(self.pid, 0)
        return self._reap(status)

    def kill(self) -> None:
        if self.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.kill(self.pid, signal.SIGKILL)


def _check(rc: int) -> None:
    if rc != 0:
        raise OSError(rc, os.strerror(rc) if rc > 0 else "posix_spawn libc call failed")


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

    proc = _spawn_helper(args)
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
