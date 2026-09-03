"""Back up and restore the clinic's data (step 10.5).

    python packaging/backup.py                 # make a backup now
    python packaging/backup.py --list          # show what backups exist
    python packaging/backup.py --restore FILE  # restore one (asks first)
    python packaging/backup.py --verify FILE   # check a backup is readable

Installed, this runs as `backup.exe` from the app folder and is registered as a
Windows scheduled task, so it happens nightly without anyone remembering.

WHY THIS IS THE MOST IMPORTANT FILE IN THE PACKAGE
    The clinic's entire record now lives on ONE disk in ONE building. There is no
    vendor, no replica, no snapshot. This script is the only thing standing
    between a dead SSD and losing years of patient history. BUILD_PLAN §11 and
    step 8.3 both say the same thing: untested backups are decoration, and real
    patient data does not go in until a restore has actually been rehearsed.

TWO THINGS GET BACKED UP, NOT ONE
    1. the database   — patients, visits, invoices, the dental chart
    2. the uploads/   — X-rays and photos, which are NOT in the database
                        (5.6 deliberately keeps bytes on disk, with only a
                        storage_key in Postgres)
    Backing up only the database would restore records whose X-rays are all
    broken links. Both go into one archive so they cannot drift apart.

FORMAT
    A plain .zip holding `database.dump` (pg_dump custom format) and `uploads/`.
    Deliberately boring: recoverable with standard tools and no special software,
    by someone who is not me, years from now.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Reuse the launcher's layout and connection settings — one source of truth.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from launcher import (  # noqa: E402
    HOST,
    PG_DB,
    PG_PORT,
    PG_USER,
    UPLOADS,
    app_root,
    data_root,
    pg_bin,
    wait_for_ready,
)

KEEP_DAYS = 30  # a month of history; each backup is only a few MB


def backups_dir() -> Path:
    return data_root() / "backups"


def log(msg: str) -> None:
    print(f"[backup] {msg}", flush=True)


def _pg_env() -> dict:
    return {**os.environ, "PGPASSWORD": PG_USER}


def make_backup() -> Path:
    """Dump the database + copy the uploads into one timestamped zip."""
    if not wait_for_ready(10):
        raise SystemExit(
            "the database is not running — open the Dental Clinic app first, "
            "then run the backup."
        )

    backups_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = backups_dir() / f"clinic-backup-{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        dump = tmpdir / "database.dump"

        log("dumping the database...")
        res = subprocess.run(
            [
                str(pg_bin("pg_dump")),
                "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER,
                "-d", PG_DB,
                "--format=custom",      # compressed, and restorable selectively
                "--file", str(dump),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_pg_env(),
        )
        if res.returncode != 0:
            raise SystemExit(f"pg_dump failed:\n{res.stdout}\n{res.stderr}")

        log("packing the database and the X-ray files together...")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(dump, "database.dump")
            uploads = UPLOADS()
            count = 0
            if uploads.exists():
                for path in uploads.rglob("*"):
                    if path.is_file():
                        z.write(path, f"uploads/{path.relative_to(uploads).as_posix()}")
                        count += 1
            # A manifest, so a human opening this in five years knows what it is.
            z.writestr(
                "README.txt",
                "Dental Clinic backup\n"
                f"created: {datetime.now(timezone.utc).isoformat()}\n"
                f"files:   database.dump (PostgreSQL custom format)\n"
                f"         uploads/ ({count} X-ray/photo/document files)\n\n"
                "To restore, open the Dental Clinic app and run:\n"
                "  backup.exe --restore <this file>\n",
            )
    log(f"backup written: {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def prune() -> None:
    """Delete backups older than KEEP_DAYS, newest always kept."""
    files = sorted(backups_dir().glob("clinic-backup-*.zip"), key=lambda p: p.stat().st_mtime)
    if len(files) <= 1:
        return
    cutoff = datetime.now().timestamp() - KEEP_DAYS * 86400
    for path in files[:-1]:  # never delete the most recent, whatever its age
        if path.stat().st_mtime < cutoff:
            path.unlink()
            log(f"removed old backup: {path.name}")


def list_backups() -> int:
    files = sorted(backups_dir().glob("clinic-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        log(f"no backups yet in {backups_dir()}")
        return 1
    log(f"{len(files)} backup(s) in {backups_dir()}:")
    for path in files:
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {when}   {path.stat().st_size / 1e6:6.1f} MB   {path.name}")
    return 0


def verify(archive: Path) -> int:
    """Check the archive opens and holds what it should — without restoring."""
    if not archive.exists():
        log(f"not found: {archive}")
        return 1
    try:
        with zipfile.ZipFile(archive) as z:
            bad = z.testzip()
            if bad:
                log(f"CORRUPT: first bad file is {bad}")
                return 1
            names = z.namelist()
            has_db = "database.dump" in names
            uploads = [n for n in names if n.startswith("uploads/")]
            size = z.getinfo("database.dump").file_size if has_db else 0
        print(f"  database.dump : {'present' if has_db else 'MISSING'} ({size / 1e6:.1f} MB)")
        print(f"  uploads       : {len(uploads)} file(s)")
        if not has_db:
            log("this archive has no database — it cannot be restored")
            return 1
        log("the archive is readable and complete")
        return 0
    except zipfile.BadZipFile:
        log("CORRUPT: not a readable zip file")
        return 1


def restore(archive: Path, *, assume_yes: bool = False) -> int:
    """Replace the current data with a backup. Destructive, and says so."""
    if verify(archive) != 0:
        return 1

    if not assume_yes:
        print()
        print("  This REPLACES all current patient data with the backup.")
        print("  Anything recorded since the backup was made will be lost.")
        print()
        if input("  Type RESTORE to continue: ").strip() != "RESTORE":
            log("cancelled — nothing was changed")
            return 1

    if not wait_for_ready(10):
        raise SystemExit("the database is not running — open the app first.")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmpdir)

        log("restoring the database...")
        # --clean --if-exists drops existing objects first, so this is a true
        # replace rather than a merge into whatever is already there.
        res = subprocess.run(
            [
                str(pg_bin("pg_restore")),
                "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER,
                "-d", PG_DB,
                "--clean", "--if-exists", "--no-owner",
                str(tmpdir / "database.dump"),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_pg_env(),
        )
        # pg_restore warns about objects that did not exist to drop; those are
        # expected on a fresh database and are not failures.
        if res.returncode != 0 and "errors ignored on restore" not in (res.stderr or ""):
            log(f"pg_restore reported problems:\n{res.stderr}")

        src_uploads = tmpdir / "uploads"
        if src_uploads.exists():
            log("restoring the X-ray files...")
            dest = UPLOADS()
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src_uploads, dest)

    log("restore complete — close and reopen the app to see the restored data")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up or restore the clinic's data.")
    ap.add_argument("--list", action="store_true", help="list existing backups")
    ap.add_argument("--restore", metavar="FILE", help="restore from a backup (destructive)")
    ap.add_argument("--verify", metavar="FILE", help="check a backup is readable")
    ap.add_argument("--yes", action="store_true", help="skip the restore confirmation")
    args = ap.parse_args()

    if args.list:
        return list_backups()
    if args.verify:
        return verify(Path(args.verify))
    if args.restore:
        return restore(Path(args.restore), assume_yes=args.yes)

    make_backup()
    prune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
