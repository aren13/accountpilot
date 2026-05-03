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

"""AccountPilot IMAP client — async IMAP operations with aioimaplib."""

from __future__ import annotations


class ImapError(Exception):
    """Base exception for IMAP operations."""


class AuthenticationError(ImapError):
    """Raised when IMAP authentication fails."""


class ConnectionError(ImapError):  # noqa: A001
    """Raised when an IMAP connection cannot be established or is lost."""


__all__ = ["AuthenticationError", "ConnectionError", "ImapError"]
