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

"""Decode Apple's attributedBody BLOB to plain text.

Apple stores message body in `attributedBody` (typedstream-archived
NSMutableAttributedString) when the body has rich content — replies,
attachments, link previews, formatting. The plain `text` column is
NULL in those cases, so SP2 stored ~70% of recent messages with empty
body_text.

This decoder unpacks the typedstream and extracts the first text run.
Unsupported / malformed blobs return "" — body_text stays empty rather
than raising and breaking sync.
"""

from __future__ import annotations

import logging

import typedstream

log = logging.getLogger(__name__)


def decode_attributed_body(blob: bytes | None) -> str:
    """Unpack an attributedBody blob and return its plain-text content.

    Returns "" on None, empty input, or any decode failure (logs the
    failure at DEBUG so it's visible in daemon logs without flooding
    INFO).
    """
    if not blob:
        return ""
    try:
        obj = typedstream.unarchive_from_data(blob)
        # Top-level shape is GenericArchivedObject with .contents
        # being a list. The first element is typically a TypedValue
        # whose .values[0] is an NSString / NSMutableString.
        first = obj.contents[0]
        ns_string = first.values[0]
        text: str = str(ns_string.value)
    except Exception:  # noqa: BLE001 — defensive: bad blobs stay empty
        log.debug("attributedBody decode failed", exc_info=True)
        return ""
    return text
