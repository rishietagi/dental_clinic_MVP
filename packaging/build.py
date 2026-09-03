"""Build the packaged desktop app (step 10.3).

    python packaging/build.py            # everything
    python packaging/build.py --frontend # just the Next.js bundle
    python packaging/build.py --backend  # just the PyInstaller executable

Produces `dist/ClinicApp/`:

    ClinicApp/
      clinic-backend.exe     backend + alembic + seed, one binary
      launcher.exe           starts everything (or launcher.py in dev)
      pgsql/bin, lib, share  bundled PostgreSQL 16
      node/node.exe          Node runtime for the Next.js server
      frontend/              .next standalone server + static + public

THE TRAP THIS SCRIPT EXISTS TO AVOID
    `NEXT_PUBLIC_API_URL` is INLINED INTO THE BROWSER BUNDLE at `npm run build` —
    it is not read at runtime. Build with the wrong value and the app looks fine
    until the browser silently calls the wrong port and every request fails in a
    way that reads like CORS. The dev build points at Docker (`localhost/api`);
    the packaged build MUST point at the launcher's backend port. This script
    sets it explicitly rather than trusting whatever .env.local happens to hold.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "ClinicApp"


def _launcher_const(name: str) -> str:
    """Read a constant out of launcher.py without importing it.

    `import packaging.launcher` would resolve to the INSTALLED `packaging`
    library (a PyPI package PyInstaller itself depends on), not our directory —
    so the value is parsed from the source instead. Reading it, rather than
    duplicating it, still guarantees the two files cannot drift apart.
    """
    src = (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if line.startswith(f"{name} ="):
            return line.split("=", 1)[1].split("#")[0].strip().strip('"')
    raise SystemExit(f"could not find {name} in launcher.py")


BACKEND_PORT = int(_launcher_const("BACKEND_PORT"))
HOST = _launcher_const("HOST")


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    log(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(cwd), env=env)
    if res.returncode != 0:
        raise SystemExit(f"command failed ({res.returncode}): {' '.join(cmd)}")


def build_frontend() -> None:
    """Next.js standalone build, with the API URL pinned to the packaged port."""
    fe = ROOT / "frontend"
    api_url = f"http://{HOST}:{BACKEND_PORT}"
    log(f"building frontend with NEXT_PUBLIC_API_URL={api_url}")

    env = {**os.environ, "NEXT_PUBLIC_API_URL": api_url, "NODE_ENV": "production"}
    npm = shutil.which("npm") or "npm"
    run([npm, "run", "build"], cwd=fe, env=env)

    out = DIST / "frontend"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # `output: standalone` emits a self-contained server but NOT .next/static or
    # public — copy those in separately or the page loads with no CSS or JS.
    shutil.copytree(fe / ".next" / "standalone", out, dirs_exist_ok=True)
    shutil.copytree(fe / ".next" / "static", out / ".next" / "static", dirs_exist_ok=True)
    if (fe / "public").exists():
        shutil.copytree(fe / "public", out / "public", dirs_exist_ok=True)
    log(f"frontend -> {out}")


def build_backend() -> None:
    """PyInstaller the backend into one executable."""
    be = ROOT / "backend"
    log("building backend executable (PyInstaller)")

    # Hidden imports: PyInstaller follows `import` statements, but these are
    # loaded dynamically by name at runtime, so it cannot see them.
    hidden = [
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "psycopg", "psycopg.pq", "psycopg_binary",
        "alembic", "app.seed",
    ]
    # Alembic resolves migrations from disk, so the scripts and the ini must be
    # packed as DATA and re-pointed at runtime (see app/main_desktop.py).
    # ABSOLUTE source paths: --add-data is resolved relative to --specpath, not
    # the working directory, so a relative path silently looks in build/.
    sep = ";" if os.name == "nt" else ":"
    datas = [
        f"{be / 'alembic'}{sep}alembic",
        f"{be / 'alembic.ini'}{sep}.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "clinic-backend",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
        "--console",
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]
    for d in datas:
        cmd += ["--add-data", d]
    # Collect alembic's own package data (its templates live inside the package).
    cmd += ["--collect-all", "alembic"]
    cmd += [str(be / "app" / "main_desktop.py")]

    run(cmd, cwd=be)

    # PyInstaller one-dir puts everything in dist/ClinicApp/clinic-backend/;
    # flatten so the exe sits beside the launcher, as the launcher expects.
    built = DIST / "clinic-backend"
    exe = built / "clinic-backend.exe"
    if exe.exists():
        for item in built.iterdir():
            target = DIST / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        built.rmdir()
    log(f"backend -> {DIST / 'clinic-backend.exe'}")


def build_launcher() -> None:
    """Freeze the launcher into launcher.exe.

    REQUIRED, not optional. The Tauri shell runs the launcher as a child process;
    if only launcher.py ships, it falls back to whatever `python` is on PATH —
    which on a clinic PC is either nothing at all, or (as here) some unrelated
    Python without fastapi, uvicorn or psycopg installed. The app then starts,
    shows a splash screen, and silently never comes up.

    Frozen, it depends on nothing outside the install folder.
    """
    log("building launcher executable (PyInstaller)")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "launcher",
        "--onefile",                 # one small exe; it only orchestrates
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller-launcher"),
        "--specpath", str(ROOT / "build"),
        "--console",
        str(ROOT / "packaging" / "launcher.py"),
    ]
    run(cmd, cwd=ROOT)
    log(f"launcher -> {DIST / 'launcher.exe'}")


def copy_postgres() -> None:
    src = ROOT / "pgsql"
    if not src.exists():
        raise SystemExit(
            "pgsql/ not found. Run packaging/fetch_postgres.py first."
        )
    dst = DIST / "pgsql"
    if dst.exists():
        shutil.rmtree(dst)
    log("copying bundled PostgreSQL")
    shutil.copytree(src, dst)


def copy_node() -> None:
    """Bundle the Node runtime that runs the Next.js server."""
    node = shutil.which("node")
    if not node:
        raise SystemExit("node not found on PATH — cannot bundle the runtime.")
    dst = DIST / "node"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(node, dst / Path(node).name)
    log(f"node runtime -> {dst}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frontend", action="store_true")
    ap.add_argument("--backend", action="store_true")
    ap.add_argument("--launcher", action="store_true")
    args = ap.parse_args()
    everything = not (args.frontend or args.backend or args.launcher)

    DIST.mkdir(parents=True, exist_ok=True)

    if everything or args.frontend:
        build_frontend()
    if everything or args.backend:
        build_backend()
    if args.launcher:
        build_launcher()
    if everything:
        build_launcher()
        copy_postgres()
        copy_node()

    log(f"done -> {DIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
