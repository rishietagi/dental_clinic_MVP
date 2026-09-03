"""Download the PostgreSQL binaries the packaged app bundles (step 10.3).

    python packaging/fetch_postgres.py

Downloads EDB's Windows x86-64 binary ZIP and extracts only what the app needs
into `pgsql/`, which is gitignored.

WHY THIS IS A SCRIPT AND NOT COMMITTED BINARIES
    The extracted tree is ~126 MB. Committing that would bloat every clone
    forever, for files that are not ours and that we never edit. A fetch script
    is reproducible and keeps the repo about our code.

WHY WE CAN DO THIS AT ALL
    PostgreSQL publishes a ZIP of the binaries — separate from the installer —
    explicitly for "users who wish to include Postgres as part of another
    application installer". That is exactly this. It needs no admin rights and
    installs nothing system-wide. It is also why the packaged app can keep
    PostgreSQL rather than migrating to SQLite: no ARRAY/JSONB/sequence/partial-
    index rewrite, no 17 migrations to redo, no re-verifying 327 tests.

WHAT IS KEPT, AND WHAT IS NOT
    Keep: bin/ lib/ share/   (~126 MB)
    Drop: pgAdmin 4 (719 MB!), StackBuilder, doc/, include/
    pgAdmin alone is more than five times the size of everything we need.

LICENCE
    PostgreSQL ships under the PostgreSQL Licence, which permits redistribution
    with the copyright notice retained. `share/` carries it; do not strip it.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "pgsql"

# PostgreSQL 16.15, Windows x86-64, from EDB's binary-archive page:
# https://www.enterprisedb.com/download-postgresql-binaries
# Matches the postgres:16 image the dev stack and every migration were built on.
PG_VERSION = "16.15"
PG_URL = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260494"

KEEP_PREFIXES = ("bin/", "lib/", "share/")


def log(msg: str) -> None:
    print(f"[fetch-pg] {msg}", flush=True)


def download(url: str, target: Path) -> None:
    log(f"downloading PostgreSQL {PG_VERSION} (~330 MB, this takes a while)...")

    def progress(block: int, block_size: int, total: int) -> None:
        if total <= 0:
            return
        done = min(block * block_size, total)
        pct = done * 100 // total
        if pct % 10 == 0 and (block * block_size) % (total // 10 or 1) < block_size:
            print(f"    {pct}%", end="\r", flush=True)

    urllib.request.urlretrieve(url, target, reporthook=progress)
    log(f"downloaded {target.stat().st_size / 1e6:.0f} MB")


def extract(zip_path: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    kept = 0
    total = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) < 2:
                continue
            rel = parts[1]  # strip the archive's top-level "pgsql/" folder
            if not rel.startswith(KEEP_PREFIXES):
                continue
            target = dest / rel
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            kept += 1
            total += info.file_size
    log(f"extracted {kept} files ({total / 1e6:.0f} MB) -> {dest}")


REQUIRED = ["postgres", "initdb", "psql", "createdb", "pg_isready", "pg_dump", "pg_restore"]


def verify(dest: Path) -> bool:
    """Every binary the launcher and the backup script rely on must be present."""
    ok = True
    for name in REQUIRED:
        exe = dest / "bin" / f"{name}.exe"
        present = exe.exists()
        ok = ok and present
        print(f"  [{'ok' if present else 'MISSING'}] {name}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep-zip", action="store_true", help="keep the downloaded archive")
    args = ap.parse_args()

    if DEST.exists() and verify(DEST):
        log(f"pgsql/ already present and complete — nothing to do")
        return 0

    zip_path = ROOT / "_pg_download.zip"
    try:
        download(PG_URL, zip_path)
        extract(zip_path, DEST)
    finally:
        if not args.keep_zip and zip_path.exists():
            zip_path.unlink()
            log("removed the downloaded archive")

    log("verifying:")
    if not verify(DEST):
        log("ERROR: some required binaries are missing")
        return 1
    log("PostgreSQL is ready to bundle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
