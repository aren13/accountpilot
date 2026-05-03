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

"""ChatDbReader — thin façade over the signed FDA helper.

The helper binary (helpers/fda-helper/) is the only path that touches
~/Library/Messages/chat.db on production installs. This module spawns
it via helper_client and converts JSON-Lines records back into the
IMessageMessage model used by Storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from accountpilot.plugins.imessage.helper_client import (
    APPLE_EPOCH,
    apple_ns_to_datetime,
    iter_records,
    record_to_imessage,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from accountpilot.core.models import IMessageMessage

# Re-exported for plugin.py and other callers that compute Apple-ns
# timestamps from datetimes.
__all__ = ["APPLE_EPOCH", "ChatDbReader", "apple_ns_to_datetime"]

# Backwards-compat alias for plugin.py's `_APPLE_EPOCH` private import.
_APPLE_EPOCH = APPLE_EPOCH


class ChatDbReader:
    """Read messages from chat.db via the signed FDA helper.

    Construction takes a chat.db path so the helper can be pointed at a
    non-default database (test fixtures, secondary user accounts). When
    `chat_db_path` is None, the helper defaults to
    ~/Library/Messages/chat.db.
    """

    def __init__(
        self,
        chat_db_path: Path | None,
        account_id: int,
        helper_path: Path | None = None,
    ) -> None:
        self.chat_db_path = chat_db_path
        self.account_id = account_id
        self.helper_path = helper_path

    def read_messages(
        self, *, since_ns: int | None = None
    ) -> Iterator[IMessageMessage]:
        """Yield IMessageMessage rows newer than `since_ns` (Apple ns).

        If `since_ns` is None, yields everything in chat.db.
        """
        for record in iter_records(
            chat_db_path=self.chat_db_path,
            since_ns=since_ns,
            helper_path=self.helper_path,
        ):
            yield record_to_imessage(record, account_id=self.account_id)
