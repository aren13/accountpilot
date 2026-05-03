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

"""Outlook provider — IMAP folder aliases for Microsoft 365 / Outlook."""

from __future__ import annotations

import logging

from accountpilot.plugins.mail.providers import Provider

logger = logging.getLogger(__name__)


class OutlookProvider(Provider):
    """Provider with Outlook-specific IMAP folder mappings."""

    name = "outlook"
    _aliases: dict[str, str] = {
        "sent": "Sent Items",
        "trash": "Deleted Items",
        "drafts": "Drafts",
        "spam": "Junk Email",
        "archive": "Archive",
    }
