# AccountPilot — unified per-machine account sync framework
# Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
# Licensed under AGPL-3.0-or-later.

"""Stable exit codes for the AccountPilot CLI.

Documented in docs/cli-contract.md. Agents key off these values to
distinguish error categories without parsing stderr or stdout.
"""

from __future__ import annotations

SUCCESS = 0
USAGE_ERROR = 2  # Click default for bad flags / args
PERMISSION_DENIED = 13  # FDA denied, OAuth flow refused
CONFIG_ERROR = 64  # malformed YAML, missing required field
DATA_ERROR = 65  # corrupt DB, schema mismatch, missing row
SERVICE_UNAVAILABLE = 69  # IMAP server down, OAuth token revoked


_CODE_MAP: dict[str, int] = {
    "PERSON_NOT_FOUND": DATA_ERROR,
    "MESSAGE_NOT_FOUND": DATA_ERROR,
    "ACCOUNT_NOT_FOUND": DATA_ERROR,
    "ATTACHMENT_NOT_FOUND": DATA_ERROR,
    "ACCOUNT_EXISTS": DATA_ERROR,
    "OAUTH_FAILED": SERVICE_UNAVAILABLE,
    "SYNC_FAILED": SERVICE_UNAVAILABLE,
    "FDA_DENIED": PERMISSION_DENIED,
    "HELPER_MISSING": SERVICE_UNAVAILABLE,
}


def for_error_code(code: str) -> int:
    """Map an envelope `error.code` string to the documented exit code.

    Falls back to DATA_ERROR (65) for unrecognized codes — better
    than 0 (which would falsely indicate success).
    """
    return _CODE_MAP.get(code, DATA_ERROR)
