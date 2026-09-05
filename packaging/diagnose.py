"""Diagnose a broken install (step 10.7).

    diagnose.exe            # run it, read the output, send it to Rishi
    diagnose.exe --fix      # attempt the safe repairs it can do itself

WHY THIS EXISTS
    "Internal server error" tells the user nothing and tells me almost nothing.
    The app runs on a machine I cannot see, in another city, so the difference
    between a five-minute fix and a lost evening is whether the first question
    can be answered in one go.

    Every check here is READ-ONLY unless --fix is passed. It prints the concrete
    state of the things that have actually broken, rather than a generic health
    tick that would be green in every case that matters.

The 500 this was written for: `get_current_staff` returns HTTP 500 when the local
staff row is missing or inactive, and EVERY write goes through it — so registering
a patient fails while the app otherwise looks completely fine.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launcher import (  # noqa: E402
    BACKEND_PORT,
    FRONTEND_PORT,
    HOST,
    PG_DB,
    PG_PORT,
    PG_USER,
    PGDATA,
    UPLOADS,
    app_root,
    data_root,
    pg_bin,
    port_open,
)

OK, BAD, WARN = "[ ok ]", "[FAIL]", "[warn]"
problems: list[str] = []


def say(status: str, label: str, detail: str = "") -> None:
    print(f"  {status} {label}" + (f"  {detail}" if detail else ""))
    if status == BAD:
        problems.append(label)


def psql(sql: str) -> tuple[int, str]:
    """Run one query. Returns (returncode, output)."""
    res = subprocess.run(
        [str(pg_bin("psql")), "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER,
         "-d", PG_DB, "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PGPASSWORD": PG_USER},
    )
    return res.returncode, (res.stdout or res.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true", help="attempt safe repairs")
    args = ap.parse_args()

    print("Dental Clinic - diagnostic report")
    print("=" * 52)
    print(f"app folder : {app_root()}")
    print(f"data folder: {data_root()}")
    print()

    # --- files -------------------------------------------------------------
    print("Files")
    for label, path in [
        ("app database folder", PGDATA()),
        ("X-ray folder", UPLOADS()),
        ("postgres", pg_bin("postgres")),
        ("backend", app_root() / "clinic-backend.exe"),
        ("launcher", app_root() / "launcher.exe"),
    ]:
        say(OK if path.exists() else BAD, label, str(path))
    print()

    # --- is it running? ----------------------------------------------------
    print("Running services")
    pg_up = port_open(PG_PORT)
    say(OK if pg_up else BAD, "database (55432)")
    say(OK if port_open(BACKEND_PORT) else BAD, "backend (55433)")
    say(OK if port_open(FRONTEND_PORT) else BAD, "app window (55434)")
    if not pg_up:
        print()
        print("The database is not running. Open the Dental Clinic app first,")
        print("leave it open, then run this again.")
        return 1
    print()

    # --- the actual state of the data --------------------------------------
    print("Data")
    rc, out = psql("SELECT count(*) FROM patient;")
    say(OK if rc == 0 else BAD, "patients table readable", out if rc == 0 else out[:120])

    rc, out = psql("SELECT count(*) FROM alembic_version;")
    say(OK if rc == 0 and out == "1" else BAD, "database schema present",
        "" if rc == 0 else out[:120])

    # THE ONE THAT CAUSES THE 500.
    rc, out = psql(
        "SELECT id || '|' || name || '|' || active FROM staff_user "
        "WHERE id = '00000000-0000-4000-8000-000000000001';"
    )
    if rc != 0:
        say(BAD, "staff record", out[:120])
    elif not out:
        say(BAD, "staff record MISSING - this is why saving fails with a 500")
    elif out.endswith("|f"):
        say(BAD, "staff record is INACTIVE - this is why saving fails with a 500")
    else:
        say(OK, "staff record", out)
    print()

    # --- can it actually write? --------------------------------------------
    print("Write test")
    rc, out = psql(
        "BEGIN; INSERT INTO patient (name) VALUES ('__diagnostic__') "
        "RETURNING id; ROLLBACK;"
    )
    say(OK if rc == 0 else BAD, "database accepts a new patient (rolled back)",
        "" if rc == 0 else out[:200])
    print()

    # --- verdict -----------------------------------------------------------
    print("=" * 52)
    if not problems:
        print("Everything looks correct.")
        print("If the app is still failing, send Rishi this whole output plus")
        print(f"the last 40 lines of:\n  {data_root() / 'logs' / 'postgres.log'}")
        return 0

    print(f"{len(problems)} problem(s) found:")
    for p in problems:
        print(f"  - {p}")

    if any("staff record" in p for p in problems):
        print()
        if args.fix:
            print("Repairing the staff record...")
            exe = app_root() / "clinic-backend.exe"
            res = subprocess.run(
                [str(exe), "--seed"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env={**os.environ,
                     "DATABASE_URL": f"postgresql+psycopg://{PG_USER}:{PG_USER}@{HOST}:{PG_PORT}/{PG_DB}"},
            )
            if res.returncode == 0:
                print("Fixed. Close the app, reopen it, and try again.")
                return 0
            print(f"Repair failed:\n{res.stdout}\n{res.stderr}")
            return 1
        print("This is repairable. Run:  diagnose.exe --fix")

    return 1


if __name__ == "__main__":
    sys.exit(main())
