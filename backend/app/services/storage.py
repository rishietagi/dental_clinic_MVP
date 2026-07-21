"""File storage — where uploaded patient files' bytes live (step 5.6).

The **seventh `services/` module.** It exists to keep the rest of the app ignorant
of *where* file bytes are stored. Today that's the local disk (a Docker volume);
in Phase 7 it becomes Supabase Storage / S3 — and because everything goes through
the `Storage` protocol, that swap is a new implementation + a config change, with
no call-site edits. This is the "local and prod differ by config, not architecture"
rule applied to file storage.

Bytes never go in Postgres. The DB keeps a `storage_key` (an opaque path this
module generates); given that key, `open` returns the bytes and `delete` removes
them. The key is a generated UUID path — never the user's filename — so a
malicious name can't traverse out of the storage root or collide with another file.
"""

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol


class Storage(Protocol):
    """The storage contract. A Phase-7 cloud backend implements the same three."""

    def save(self, fileobj: BinaryIO) -> str:
        """Store the bytes from `fileobj`; return the opaque storage key."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open the stored bytes for reading. Raises FileNotFoundError if missing."""
        ...

    def delete(self, key: str) -> None:
        """Remove the stored bytes. A no-op if already gone."""
        ...


class LocalStorage:
    """Filesystem-backed storage under a root directory (dev; a Docker volume).

    The key is `<yyyy>/<mm>/<uuid>` — sharded by month so no single directory
    grows unbounded, and a UUID leaf so keys never collide and never derive from
    user input. `root` comes from config (`UPLOAD_DIR`), never hardcoded.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root / key

    def save(self, fileobj: BinaryIO) -> str:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        key = f"{now:%Y}/{now:%m}/{uuid.uuid4().hex}"
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            shutil.copyfileobj(fileobj, out)
        return key

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> Storage:
    """The app's storage backend, chosen by config.

    Local disk today; Phase 7 returns a cloud implementation based on an env var
    without changing any caller.
    """
    from app.config import settings

    return LocalStorage(settings.upload_dir)
