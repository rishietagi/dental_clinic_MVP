"""Clinic app launcher — starts the whole stack as plain processes (step 10.3).

Replaces Docker Compose for the packaged desktop app. Same three services, no
container runtime:

    Postgres (bundled binaries)  ->  backend (uvicorn)  ->  frontend (Next.js)

    python -m packaging.launcher          # run in the foreground, Ctrl+C to stop
    python -m packaging.launcher --check  # verify the bundle layout, then exit

WHY A SCRIPT AND NOT A .BAT
    Startup is ORDERED and CONDITIONAL: Postgres must be accepting connections
    before migrations run, migrations must finish before uvicorn serves, and the
    first run has to create the database cluster that later runs just start. That
    is real logic, and it has to shut everything down cleanly on the way out.

FIRST RUN vs LATER RUNS
    First run does `initdb`, creates the database, runs `alembic upgrade head`
    and seeds the local staff row. It takes a while — tens of seconds. Later runs
    skip straight to starting Postgres. The marker is simply whether the data
    directory exists.

WHERE THINGS LIVE (all under %LOCALAPPDATA%\\ClinicApp)
    pgdata/     the database cluster       <- the clinic's records
    uploads/    X-rays, photos, documents  <- ALSO the clinic's records
    logs/       postgres + app logs
    Both pgdata AND uploads must be in any backup. The X-rays are NOT in the
    database — losing the uploads folder loses them.

PORTS
    Non-standard on purpose (55432/55433/55434) so the app cannot collide with a
    Postgres, or anything else, the machine already runs. Everything binds to
    127.0.0.1 — nothing is reachable from the network.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# --- layout ------------------------------------------------------------------

APP_NAME = "ClinicApp"

# Ports well clear of the defaults (5432/8000/3000) so a developer machine that
# already runs Postgres or a dev server is unaffected.
PG_PORT = 55432
BACKEND_PORT = 55433
FRONTEND_PORT = 55434

PG_USER = "clinic"
PG_DB = "clinic"

HOST = "127.0.0.1"  # never 0.0.0.0 — this app is not a network service


def app_root() -> Path:
    """Where the app's own files (pgsql/, node/, frontend/) live.

    Three layouts to tell apart, which is why this is not a one-liner:
      1. frozen        -> beside the executable
      2. built bundle  -> beside this script (dist/ClinicApp/launcher.py)
      3. development   -> the repo root, one level up from packaging/

    Cases 2 and 3 both run this file unfrozen, so `sys.frozen` cannot separate
    them. The marker is whether pgsql/ sits next to the script: in the bundle it
    does, in the repo it is one level up.
    """
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).parent
    here = Path(__file__).resolve().parent
    if (here / "pgsql").exists():
        return here          # built bundle
    return here.parent       # development checkout


def data_root() -> Path:
    """Per-user writable data. NOT under Program Files — that needs admin."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return Path(base) / APP_NAME


PGDATA = lambda: data_root() / "pgdata"
UPLOADS = lambda: data_root() / "uploads"
LOGS = lambda: data_root() / "logs"


def pg_bin(name: str) -> Path:
    """A bundled Postgres executable (postgres, initdb, pg_isready, ...)."""
    exe = f"{name}.exe" if os.name == "nt" else name
    return app_root() / "pgsql" / "bin" / exe


def database_url() -> str:
    return f"postgresql+psycopg://{PG_USER}:{PG_USER}@{HOST}:{PG_PORT}/{PG_DB}"


# --- helpers -----------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[launcher] {msg}", flush=True)


def port_open(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.35)
        return s.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: float, what: str) -> bool:
    """Block until something is listening, or give up. Returns success."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(port):
            return True
        time.sleep(0.3)
    log(f"ERROR: {what} did not come up on port {port} within {timeout:.0f}s")
    return False


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command to completion, capturing output so failures are readable.

    `errors="replace"` matters on Windows: the child's console codepage is
    usually cp1252, not UTF-8, so a single non-ASCII character in its output
    (our seed prints an em-dash) raised UnicodeDecodeError inside subprocess's
    reader thread and left `stdout` as None — a crash in the launcher caused
    purely by a punctuation mark in a log line.
    """
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# --- postgres ----------------------------------------------------------------

def first_run_needed() -> bool:
    return not (PGDATA() / "PG_VERSION").exists()


def initdb() -> None:
    """Create the database cluster. First run only, and it is slow."""
    log("first run: creating the database (this takes a minute)...")
    PGDATA().parent.mkdir(parents=True, exist_ok=True)
    LOGS().mkdir(parents=True, exist_ok=True)

    # A password file, because initdb refuses --auth=md5 without one. The
    # password is not a secret: Postgres listens only on 127.0.0.1 and the
    # machine's own Windows login is the real boundary. Using trust auth instead
    # would let ANY local process connect, which is worse.
    pwfile = data_root() / ".pgpw"
    pwfile.write_text(PG_USER, encoding="utf-8")
    try:
        res = run([
            str(pg_bin("initdb")),
            "-D", str(PGDATA()),
            "-U", PG_USER,
            "--auth-local=scram-sha-256",
            "--auth-host=scram-sha-256",
            f"--pwfile={pwfile}",
            "-E", "UTF8",
        ])
        if res.returncode != 0:
            raise SystemExit(f"initdb failed:\n{res.stdout}\n{res.stderr}")
    finally:
        pwfile.unlink(missing_ok=True)  # never leave the password on disk
    log("database cluster created")


def start_postgres() -> subprocess.Popen:
    LOGS().mkdir(parents=True, exist_ok=True)
    logfile = LOGS() / "postgres.log"
    log(f"starting postgres on {HOST}:{PG_PORT}")
    proc = subprocess.Popen(
        [
            str(pg_bin("postgres")),
            "-D", str(PGDATA()),
            "-p", str(PG_PORT),
            "-k", "",                    # no unix sockets (Windows)
            "-c", f"listen_addresses={HOST}",
            "-c", f"log_directory={LOGS()}",
        ],
        stdout=logfile.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    # A LISTENING PORT IS NOT READINESS. Postgres binds the port before it has
    # finished starting (and, after an unclean shutdown, before crash recovery
    # completes) — connecting then gives "the database system is starting up".
    # pg_isready is the actual check, and it is why it ships in the bundle.
    if not wait_for_ready(60):
        proc.terminate()
        raise SystemExit(f"postgres failed to become ready — see {logfile}")
    log("postgres is ready")
    return proc


def wait_for_ready(timeout: float) -> bool:
    """Block until Postgres will actually accept a connection."""
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        res = run([
            str(pg_bin("pg_isready")), "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER,
        ])
        if res.returncode == 0:
            return True
        last = (res.stdout or res.stderr).strip()
        time.sleep(0.5)
    log(f"ERROR: postgres not ready after {timeout:.0f}s — {last}")
    return False


def ensure_database() -> None:
    """Create the application database if this cluster has never had it."""
    env = {**os.environ, "PGPASSWORD": PG_USER}
    res = run([
        str(pg_bin("psql")), "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER,
        "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{PG_DB}'",
    ], env=env)
    if res.stdout.strip() == "1":
        return
    log(f"creating database '{PG_DB}'")
    res = run([
        str(pg_bin("createdb")), "-h", HOST, "-p", str(PG_PORT), "-U", PG_USER, PG_DB,
    ], env=env)
    if res.returncode != 0:
        raise SystemExit(f"createdb failed:\n{res.stdout}\n{res.stderr}")


# --- app ---------------------------------------------------------------------

def backend_env() -> dict:
    """Environment for the backend AND for alembic — one definition, no drift."""
    return {
        **os.environ,
        "DATABASE_URL": database_url(),
        "ENVIRONMENT": "production",
        # The browser is served from the frontend port and calls the backend
        # directly (there is no Caddy in the packaged app), so that origin must
        # be allowed or every request fails CORS.
        "CORS_ORIGINS": f"http://{HOST}:{FRONTEND_PORT},http://localhost:{FRONTEND_PORT}",
        "UPLOAD_DIR": str(UPLOADS()),
    }


def migrate_and_seed() -> None:
    """Bring the schema up to date, then ensure the local staff row exists.

    Runs on EVERY start, not just the first: an app update ships new migrations,
    and there is no other moment to apply them. Both are idempotent.
    """
    env = backend_env()
    root = app_root()

    # Prefer the built executable whenever it is present. In a bundle the
    # migration files live INSIDE that binary, so alembic must run through it;
    # in a dev checkout they are on disk and plain python works.
    exe = root / "clinic-backend.exe"
    bundled = exe.exists()
    cwd = str(root) if bundled else str(root / "backend")

    log("applying database migrations...")
    cmd = [str(exe), "--migrate"] if bundled else [sys.executable, "-m", "alembic", "upgrade", "head"]
    res = run(cmd, cwd=cwd, env=env)
    if res.returncode != 0:
        raise SystemExit(f"migrations failed:\n{res.stdout}\n{res.stderr}")
    log("migrations applied")

    log("checking the local staff record...")
    cmd = [str(exe), "--seed"] if bundled else [sys.executable, "-m", "app.seed"]
    res = run(cmd, cwd=cwd, env=env)
    if res.returncode != 0:
        raise SystemExit(f"seed failed:\n{res.stdout}\n{res.stderr}")
    # Defensive: never let a logging line be the thing that fails startup.
    out = (res.stdout or "").strip()
    log(out.splitlines()[0] if out else "staff record ok")


def start_backend() -> subprocess.Popen:
    env = backend_env()
    root = app_root()
    log(f"starting backend on {HOST}:{BACKEND_PORT}")
    # Prefer the built executable whenever it exists, frozen or not — that is
    # what distinguishes a bundle from a dev checkout.
    exe = root / "clinic-backend.exe"
    if exe.exists():
        cmd = [str(exe), "--serve", "--host", HOST, "--port", str(BACKEND_PORT)]
        cwd = str(root)
    else:
        cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(BACKEND_PORT)]
        cwd = str(root / "backend")
    proc = subprocess.Popen(cmd, cwd=cwd, env=env)
    if not wait_for_port(BACKEND_PORT, 60, "backend"):
        proc.terminate()
        raise SystemExit("backend failed to start")
    log("backend is up")
    return proc


def start_frontend() -> subprocess.Popen:
    root = app_root()
    env = {
        **os.environ,
        "NODE_ENV": "production",
        "PORT": str(FRONTEND_PORT),
        "HOSTNAME": HOST,
    }
    # The bundle lays the frontend out flat (frontend/server.js); a dev checkout
    # leaves it where `next build` put it (.next/standalone/server.js).
    bundled_server = root / "frontend" / "server.js"
    if bundled_server.exists():
        bundled_node = root / "node" / "node.exe"
        node = str(bundled_node) if bundled_node.exists() else (shutil.which("node") or "node")
        server = str(bundled_server)
        cwd = str(root / "frontend")
    else:
        node = shutil.which("node") or "node"
        server = str(root / "frontend" / ".next" / "standalone" / "server.js")
        cwd = str(root / "frontend" / ".next" / "standalone")
    log(f"starting frontend on {HOST}:{FRONTEND_PORT}")
    proc = subprocess.Popen([node, server], cwd=cwd, env=env)
    if not wait_for_port(FRONTEND_PORT, 90, "frontend"):
        proc.terminate()
        raise SystemExit("frontend failed to start")
    log("frontend is up")
    return proc


# --- orchestration -----------------------------------------------------------

class Stack:
    """Starts the three services and — importantly — stops all of them.

    An orphaned postgres.exe keeps a lock on the data directory, so the NEXT
    launch fails with a confusing error. Shutdown is therefore not best-effort:
    it runs on normal exit, on Ctrl+C, and on a failure part-way through startup.
    """

    def __init__(self) -> None:
        self.procs: list[tuple[str, subprocess.Popen]] = []

    def start(self) -> None:
        UPLOADS().mkdir(parents=True, exist_ok=True)
        LOGS().mkdir(parents=True, exist_ok=True)

        if first_run_needed():
            initdb()

        self.procs.append(("postgres", start_postgres()))
        ensure_database()
        migrate_and_seed()
        self.procs.append(("backend", start_backend()))
        self.procs.append(("frontend", start_frontend()))

    def url(self) -> str:
        return f"http://{HOST}:{FRONTEND_PORT}"

    def stop(self) -> None:
        # Reverse order: frontend, backend, then postgres last so it can flush
        # and check-point rather than being killed mid-write.
        for name, proc in reversed(self.procs):
            if proc.poll() is not None:
                continue
            log(f"stopping {name}")
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                log(f"{name} did not stop in time — killing it")
                proc.kill()
                proc.wait(timeout=5)
            except Exception as exc:  # noqa: BLE001
                log(f"error stopping {name}: {exc}")
        self.procs.clear()


def check_bundle() -> int:
    """Verify the pieces exist, without starting anything. For the installer."""
    root = app_root()
    frozen = getattr(sys, "frozen", False)
    required = [
        ("postgres binaries", pg_bin("postgres")),
        ("initdb", pg_bin("initdb")),
        ("psql", pg_bin("psql")),
    ]
    if frozen:
        required += [
            ("backend executable", root / "clinic-backend.exe"),
            ("node runtime", root / "node" / "node.exe"),
            ("frontend server", root / "frontend" / "server.js"),
        ]
    ok = True
    print(f"app root : {root}")
    print(f"data root: {data_root()}")
    print(f"mode     : {'packaged' if frozen else 'development'}")
    for label, path in required:
        exists = path.exists()
        ok = ok and exists
        print(f"  [{'ok' if exists else 'MISSING'}] {label}: {path}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Start the clinic app.")
    ap.add_argument("--check", action="store_true", help="verify the bundle layout and exit")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = ap.parse_args()

    if args.check:
        return check_bundle()

    stack = Stack()

    def handle_signal(signum, frame):  # noqa: ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        stack.start()
        log(f"ready — {stack.url()}")
        if not args.no_browser:
            import webbrowser
            webbrowser.open(stack.url())
        # Idle until interrupted, but notice if a service dies underneath us.
        while True:
            time.sleep(1.0)
            for name, proc in stack.procs:
                if proc.poll() is not None:
                    log(f"{name} exited unexpectedly (code {proc.returncode})")
                    return 1
    except KeyboardInterrupt:
        log("shutting down")
        return 0
    finally:
        stack.stop()


if __name__ == "__main__":
    sys.exit(main())
