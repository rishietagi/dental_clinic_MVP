"""Backend entry point for the packaged desktop app (step 10.3).

PyInstaller produces ONE executable, but the launcher needs three different jobs
from it. A subcommand flag keeps that to a single binary instead of three:

    clinic-backend.exe --serve --host 127.0.0.1 --port 55433
    clinic-backend.exe --migrate     # alembic upgrade head
    clinic-backend.exe --seed        # ensure the local staff row exists

WHY NOT JUST SHIP alembic.exe AND uvicorn.exe
    Both are Python entry points that would each need their own PyInstaller
    bundle, tripling the size and giving three chances for a missing hidden
    import. One binary, three flags, one set of bundled dependencies.

WHY MIGRATIONS RUN THROUGH HERE
    `alembic upgrade head` normally needs alembic.ini and the alembic/ directory
    on disk next to the app. Inside a PyInstaller bundle those are packed into
    the executable, so the path has to be resolved against sys._MEIPASS. Doing it
    here means the launcher does not have to know any of that.

In development this module is unused — the launcher calls `python -m uvicorn`
and `python -m alembic` directly, which keeps the dev path identical to what it
has always been.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    """Where PyInstaller unpacked our data files (or the source tree in dev)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def run_migrations() -> int:
    """Apply Alembic migrations up to head.

    Driven through Alembic's Python API rather than its CLI so it works the same
    frozen or not. `DATABASE_URL` comes from the environment — alembic/env.py
    already reads it, so there is no second source of truth for the connection.
    """
    from alembic import command
    from alembic.config import Config

    root = _bundle_dir()
    ini = root / "alembic.ini"
    scripts = root / "alembic"
    if not ini.exists() or not scripts.exists():
        print(f"error: migration files missing (looked in {root})", file=sys.stderr)
        return 1

    cfg = Config(str(ini))
    # The packed location differs from what alembic.ini records, so point it at
    # the unpacked copy explicitly.
    cfg.set_main_option("script_location", str(scripts))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")
    return 0


def run_seed() -> int:
    from app.seed import seed_local_staff

    seed_local_staff()
    return 0


def run_server(host: str, port: int) -> int:
    import uvicorn

    from app.main import app

    # log_config=None: PyInstaller bundles have no logging config file, and
    # uvicorn's default dictConfig tries to load one.
    uvicorn.run(app, host=host, port=port, log_config=None)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Clinic backend (packaged).")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--serve", action="store_true", help="run the API server")
    group.add_argument("--migrate", action="store_true", help="apply migrations")
    group.add_argument("--seed", action="store_true", help="ensure the staff row exists")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=55433)
    args = ap.parse_args(argv)

    if args.migrate:
        return run_migrations()
    if args.seed:
        return run_seed()
    return run_server(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
