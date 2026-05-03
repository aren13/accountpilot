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

"""Gmail provider — IMAP folder aliases for Google Workspace / Gmail."""

from __future__ import annotations

import logging

from accountpilot.plugins.mail.providers import Provider

logger = logging.getLogger(__name__)


class GmailProvider(Provider):
    """Provider with Gmail-specific IMAP folder mappings."""

    name = "gmail"
    _aliases: dict[str, str] = {
        "sent": "[Gmail]/Sent Mail",
        "trash": "[Gmail]/Trash",
        "drafts": "[Gmail]/Drafts",
        "spam": "[Gmail]/Spam",
        "archive": "[Gmail]/All Mail",
    }
