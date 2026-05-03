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

"""Content-addressed store for attachment bytes.

Writes blobs to `<root>/<hash[:2]>/<hash[2:4]>/<hash>.bin` atomically
(temp file + rename) and idempotently (skip if file exists).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class CASStore:
    """Filesystem-backed content-addressed blob store."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, content: bytes) -> tuple[str, str]:
        """Write `content` and return (sha256_hex, relative_path_from_root)."""
        h = hashlib.sha256(content).hexdigest()
        rel = f"{h[:2]}/{h[2:4]}/{h}.bin"
        target = self.root / rel
        if target.exists():
            return h, rel

        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=target.parent, prefix=".cas-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            os.replace(tmp_path, target)
        except Exception:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
            raise
        return h, rel

    def path(self, relative: str) -> Path:
        """Return absolute path for a CAS-relative path."""
        return (self.root / relative).resolve()
