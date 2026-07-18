# LOG

Running record of what was done, what was decided, and what a new session needs to know.
**Newest entry first.** Append an entry at the end of every step.

---

## START HERE — context for a new session

**Read first:** `CLAUDE.md` (working rules, hard constraints) **if it exists** — it is
gitignored and local-only, so a fresh clone will not have it. Then `docs/BUILD_PLAN.md` (the
full plan and roadmap), then this file (what actually happened).

> **If `CLAUDE.md` is missing, ask the user for it before doing anything.** It holds the
> working rules and hard constraints, and the essentials are summarised below as a fallback —
> but the file itself is the authority.

**Where we are:** **Phase 0 is complete** (0.6 done). Next is **Phase 1 — Auth & roles**,
starting with step 1.1 (managed auth via a free Supabase project, hit from localhost, + a login
page). Not started. NOTE: Phase 1 is the first step that needs a cloud dependency (Supabase
auth) even in local mode — confirm the approach with the user before building.

**The working rules that matter most** (CLAUDE.md is the authority; this is the fallback copy):
- Plan mode first. No file changes before the user approves.
- **Never run git.** No init/add/commit/push/branch/merge, no touching `.git/`. The user
  stages, commits, and pushes. At a checkpoint, say it's ready and suggest a message —
  nothing more.
- One step at a time. Never build ahead into the next step or phase.
- Ask before adding any dependency not in the agreed tech stack.
- Stop at every checkpoint and wait.
- Local only until Phase 7 — no VPS config, prod compose, domains, or TLS before then.
- Prefer boring, obvious code. This is a maintainability project.

**Hard constraints** (real patients, real data — these are not negotiable):
- Schema changes go through Alembic migrations. Never manual SQL against live data. Never
  `DROP` a table holding real patient data.
- Role checks belong on the API, not just hidden UI. A hidden button is not security.
- Soft-delete patients only (`archived` flag) — medico-legal retention.
- No patient identifiers in URL query strings.
- Never hand-write auth/password handling — use the managed provider.
- Never test against live patient data.
- Roles are a **set** on the user (`["dentist", "admin"]`), never a single role string.
- All config via env vars. Never hardcode localhost, ports, hostnames, or secrets.
- Seed/fake data only until Phase 7. No real patient data on a laptop.

**Out of scope — do not build:** prescriptions · treatment plans (quoted/estimated) · consent
forms · dental charting/odontogram · inventory · lab work tracking · patient portal or any
patient login · insurance claims. If a task seems to need one, stop and ask.

**Environment:**
- Python deps live in the conda env `dental-clinic` (Python 3.12) — **never base, never
  global**. Install with `conda run -n dental-clinic pip install -r backend/requirements.txt`.
- Node.js 24.18.0, npm 11.16.0, at `C:\Program Files\nodejs\`.
- Docker Desktop is installed at `C:\Program Files\Docker\Docker\`.
- Windows 11, PowerShell.

**Standing decisions that override the original brief** — these are easy to get wrong because
the original step instructions say otherwise:
| Decision | Original brief said | Reality | Where |
|---|---|---|---|
| **Node 24, not 20** | `node:20-alpine` in step 0.4 | Machine runs Node 24.18.0; frontend Dockerfile must be `node:24-alpine` | `docs/TECH_STACK.md` |
| **CLAUDE.md is gitignored** | — | Local-only, not in the repo. A fresh clone won't have it; ask the user for it. | `.gitignore` |
| **`next.config.ts`, not `.js`** | `next.config.js` in step 0.3 | Next 16 scaffolds a TypeScript config. `output: "standalone"` lives in the `.ts` file. | `frontend/next.config.ts` |
| **Tailwind 4, not 3** | — | No `tailwind.config.js` exists. v4 is CSS-first: configured in `app/globals.css`. Don't go looking for the JS config. | `docs/TECH_STACK.md` |

**Docker works** (verified 2026-07-17, after the earlier WSL breakage was repaired): WSL
2.9.3.0 / kernel 6.18.35.2, Docker engine 29.6.1 (linux, overlayfs), Compose v5.3.0,
`docker run hello-world` succeeds. Base images `node:24-alpine`, `python:3.12-slim`,
`postgres:16-alpine`, `caddy:2-alpine` all confirmed available.

**Known gotchas:**
- A shell started before an install won't see new PATH entries. Check the filesystem and the
  registry PATH (`[Environment]::GetEnvironmentVariable("Path","Machine")`) before concluding
  something isn't installed.
- `pytest` must run from `backend/` — `backend/pytest.ini` sets `pythonpath = .` so `app.main`
  imports.

---

## 2026-07-18 — Step 0.6: CI pipeline (GitHub Actions) — Phase 0 complete

**Status:** complete. Workflow written and its commands verified locally; the workflow itself
runs on GitHub after the push. For commit.

### Built
- `.github/workflows/ci.yml` — triggers on push + PR to `main`. Two **parallel** jobs:
  - **backend:** `actions/setup-python@v5` (3.12, pip cache) → `pip install -r requirements.txt`
    → `python -m pytest -q`. Plain pip, not conda (CI is a clean machine; pins make versions
    match).
  - **frontend:** `actions/setup-node@v4` (Node 24, npm cache) → `npm ci` → `npm run lint` →
    `npm run build`.
- **Tests only. No deploy** — deploy is Phase 7 (a comment in the file says so).

### Decisions (asked user)
- **Backend + frontend both** (not backend-only). The frontend build/lint catches TS errors
  and standalone-build breaks that wouldn't otherwise surface until `docker compose up`.
- **No Postgres service in CI yet.** The only test hits `/health` and never touches the DB, so
  a Postgres service would prove nothing and slow every run. Add it in **Phase 2** with the
  first model + DB-backed tests. A comment in the workflow records this.

### Verified locally (can't run Actions itself from here)
- YAML parses; jobs `backend`, `frontend`; triggers push + pull_request.
- Backend steps in a **clean throwaway venv** (mimics CI, no conda): `pip install -r
  requirements.txt` then `pytest` → `1 passed`.
- Frontend `npm ci` → exit 0 (lockfile in sync — the thing `npm ci` is strict about). lint +
  build already green since 0.3/0.4, frontend unchanged since.

### Note for after the push
Watch the repo's **Actions** tab — the "CI" workflow should appear with two jobs. That's the
only part not verifiable locally, because Actions runs on GitHub's servers.

### Suggested commit
`ci: add test pipeline`

---

## 2026-07-18 — Step 0.5: Postgres wired in (SQLAlchemy + Alembic)

**Status:** complete, verified in the running db container, torn down clean. For commit.

### Built
- `app/db.py` — SQLAlchemy `engine` (`pool_pre_ping=True`), `SessionLocal`
  (`expire_on_commit=False`), `get_db` dependency. Reuses `settings.database_url` — one config
  source.
- `app/models/__init__.py` — `Base(DeclarativeBase)`. Empty metadata (no models until Phase 2).
- Alembic scaffolded (`alembic init alembic`) → `alembic/`, `alembic.ini`.
- One **empty** migration: `alembic/versions/78e9327c7254_empty_initial_migration.py`
  (`down_revision = None`, both `upgrade`/`downgrade` are `pass`).
- Backend Dockerfile now also copies `alembic/` + `alembic.ini` (migrations ship in the image).

### The two safety-critical Alembic edits (from the brief)
- **Deleted `sqlalchemy.url` from `alembic.ini` entirely** (replaced with a comment explaining
  why). No fallback URL to accidentally migrate the wrong DB.
- **`alembic/env.py`:** `config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])`
  and `target_metadata = Base.metadata`. Uses `os.environ[...]` (subscript) so a missing var
  fails loud, not silent.

### Decisions
- **Migrations run inside the backend container** (user's choice). The db is reachable as host
  `db` on the compose network — same `DATABASE_URL` the app uses, no host Postgres client, and
  the db port is never published. Prod-faithful.
- **Migrations copied into the image**, not just bind-mounted, so app code and migration code
  can't drift.

### Verified (three-way, in the real db)
- `alembic upgrade head` (from the built image) → `Running upgrade -> 78e9327c7254`.
- `psql \dt` → only `alembic_version` exists (correct: no app tables yet).
- `SELECT version_num` → `78e9327c7254`; `alembic current` → `78e9327c7254 (head)`. All agree.
- **Safety net proven:** `alembic current` with `DATABASE_URL` empty errors out
  (`Could not parse SQLAlchemy URL`) and connects to nothing. With the var truly unset it would
  be a `KeyError` — either way it refuses to run.
- `docker compose down` clean; `pgdata` volume persists (holds the migration state).

### Gotcha for next time
Generating a migration needs the file to persist to the host, so it was created via a one-off
container with `backend/` bind-mounted (`docker compose run --rm -v "${PWD}/backend:/app"
backend alembic revision --autogenerate ...`). *Applying* migrations does not need the mount —
run it from the plain image. Also: PowerShell wraps Docker's stderr status lines in red
`NativeCommandError` text; it is not a failure — check the actual last output line.

### Suggested commit
`feat: add Postgres with Alembic migrations`

---

## 2026-07-17 — Step 0.4: Containerise with Docker Compose

**Status:** complete, verified end-to-end in a browser, torn down clean. Handed off for commit.

### Built
- `backend/Dockerfile` (`python:3.12-slim`) + `backend/.dockerignore`.
- `frontend/Dockerfile` — multi-stage deps/builder/runner on **`node:24-alpine`**, serves the
  standalone build as a non-root user. + `frontend/.dockerignore`.
- `Caddyfile` — `{$SITE_ADDRESS:http://localhost}`; `/api/*` → strip `/api` →
  `reverse_proxy backend:8000`; else → `reverse_proxy frontend:3000`.
- `docker-compose.yml` — four services: db (`postgres:16-alpine`, healthchecked, named volume
  `pgdata`), backend (uvicorn `--reload`, source bind-mounted), frontend (built with the API
  URL as a build arg), caddy (`80:80`). Only Caddy publishes a host port.

### Decisions (flagged to user, standing authority to proceed)
- **`NEXT_PUBLIC_API_URL=http://localhost/api`**, not `:8000`. The browser goes through Caddy;
  the backend answers under `/api` (prefix stripped). This makes the whole app a single origin
  on port 80, so **CORS is not even exercised** in the Docker path. `CORS_ORIGINS` is still set
  sanely for the by-hand dev path.
- **Only Caddy publishes to the host.** backend/frontend/db are internal to the compose
  network. If direct API access on :8000 is ever wanted for dev, publish it explicitly.
- **Postgres runs but nothing connects.** The db service completes the topology and is
  healthchecked; no app code opens `DATABASE_URL` until 0.5. Intended, not scope creep.

### Two footguns handled (both from the brief, both verified)
- **`NEXT_PUBLIC_*` is baked at BUILD time.** Frontend Dockerfile declares `ARG` + `ENV`
  before `npm run build`; compose passes the arg. Verified: the browser bundle calls
  `/api`, and the card went green through the proxy.
- **`output: standalone` omits `.next/static` and `public/`.** The runner stage copies all
  three (`standalone`, then `static`, then `public`). Verified: a real CSS asset returned 200
  with 30 KB, and the screenshot shows the styled page.

### Verified
- `docker compose config` valid; `docker compose build` → both images built.
- `docker compose up -d` → all four containers up, **db healthy**, no crash loops. `ports`
  confirms only caddy on `0.0.0.0:80`.
- `curl http://localhost/api/health` → `{"status":"ok","environment":"development"}` (backend
  reached through Caddy, prefix stripped).
- `http://localhost` → 200, clinic name present, `/_next/static` CSS asset loads.
- **Screenshot:** styled page, Geist font, **System OK** green — full loop containerised.
- Backend logs show `WatchFiles` reloader active (bind-mount hot reload works).
- `docker compose down` → clean; port 80 free.

### Snags hit
- **Docker Desktop had exited** between the user's confirmation and this build (`daemon not
  reachable`, process gone). Relaunched `Docker Desktop.exe`; engine up in ~3s. Not a project
  issue — the engine doesn't stay running on its own.

### Suggested commit
`chore: containerise with docker compose`

---

## 2026-07-17 — Step 0.3: Next.js frontend shell

**Status:** complete, verified, handed off for commit.

### Built
- `frontend/` scaffolded with `create-next-app`: Next 16.2.10, React 19.2.4, TypeScript,
  Tailwind 4, ESLint, App Router, **no `src/`**, alias `@/*`.
- `frontend/next.config.ts` — sets `output: "standalone"`. **Step 0.4's Docker build depends
  on this**; without it there is no `.next/standalone/server.js` to copy.
- `frontend/app/page.tsx` — server component: clinic name heading + `<HealthCard />`.
- `frontend/app/health-card.tsx` — **`"use client"`**. Fetches `${NEXT_PUBLIC_API_URL}/health`
  in a `useEffect`. Three states: loading / ok (green) / error (red).
- `frontend/.env.local` (gitignored) and `.env.local.example` (committed) —
  `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- shadcn/ui initialised; `button` and `card` added to `components/ui/`.
- `frontend/app/layout.tsx` — page title set to the clinic name.

### Decisions
- **Clinic name is the placeholder "Dental Clinic"** (user's call). It becomes a real value in
  Phase 4's clinic settings screen.
- **The page is a server component; only the health card is a client component.** Keeps the
  `"use client"` boundary as small as possible — the pattern the rest of the app should follow.
- **Deleted the generated `AGENTS.md` and `frontend/CLAUDE.md`.** `create-next-app` writes both
  by default; neither was asked for, and a nested CLAUDE.md would compete with the root one.
- **Passed `--disable-git`** — `create-next-app` runs `git init` otherwise, which would violate
  the never-run-git rule.
- **`frontend/.gitignore` got a `!.env.local.example` negation.** The scaffold ignores `.env*`,
  which would have swallowed the committed example file.
- **shadcn's init pulled in six deps** not separately chosen: `@base-ui/react`,
  `class-variance-authority`, `clsx`, `lucide-react`, `tailwind-merge`, `tw-animate-css`. These
  are what shadcn components import. Recorded in `docs/TECH_STACK.md`.

### Two bugs found and fixed during verification
- **Font fell back to serif.** `shadcn init` rewrites `globals.css` to map Tailwind's
  `font-sans` to `var(--font-sans)`, but the create-next-app layout defines Geist as
  `--font-geist-sans`. Names didn't match, so `font-sans` resolved to nothing. Fixed by
  renaming the variable in `layout.tsx` to `--font-sans`. (`--font-mono` →
  `--font-geist-mono` already matches; left alone.)
- **ESLint `react-hooks/set-state-in-effect`.** The original card called `setState`
  synchronously inside `useEffect` for the missing-API-URL case. Fixed by seeding that into
  `useState`'s initial value — it's knowable at module load, so no effect is needed.

### Verified
- `npm run build` → compiled, TypeScript clean, and `.next/standalone/server.js` confirmed to
  exist (proves the standalone config works).
- Backend on :8000 + `next dev` on :3000 → page serves 200, clinic name in the HTML.
- **CORS confirmed for real:** `GET /health` with `Origin: http://localhost:3000` returns
  `Access-Control-Allow-Origin: http://localhost:3000`. The browser fetch will not be blocked.
- **Green path:** fetch returns `{"status":"ok","environment":"development"}` → card shows
  System OK.
- **Error path:** backend stopped → fetch throws `ECONNREFUSED`, caught into the error state.
  Frontend still serves 200. No crash.
- **Screenshotted both states in a real browser** (headless Edge, no new dependency): green
  "System OK / Backend ok / Environment development", and red "System unavailable / Failed to
  fetch / Is the backend running at http://localhost:8000?".
- `npm run lint` exits 0.

### Gotcha for next time
`next dev` fails with `Cannot find module '../chunks/ssr/[turbopack]_runtime.js'` if `.next/`
holds artifacts from a production `npm run build`. Delete `.next/` when switching between
`build` and `dev`. Not a code bug — cost 10 minutes to diagnose.

### Suggested commit
`feat: scaffold Next.js frontend`

---

## 2026-07-17 — Step 0.2: FastAPI backend with /health

**Status:** complete, verified, handed off for commit.

### Built
- `backend/app/main.py` — FastAPI app, CORS middleware fed from settings, `GET /health`
  returning `{"status": "ok", "environment": ...}`.
- `backend/app/config.py` — pydantic-settings `Settings` (`database_url`, `environment`,
  `cors_origins`) plus a module-level `settings`.
- `backend/.env.example` — documents the three env vars. Real `.env` is gitignored.
- `backend/requirements.txt` — all ten specified deps, pinned to resolved versions.
- `backend/pytest.ini` — `pythonpath = .` so tests can import `app.main`.
- `backend/tests/test_health.py` — asserts 200, `status == "ok"`, `environment` present.

### Also done (leftovers from step 0.1, with user approval)
- Created conda env `dental-clinic` (Python 3.12) — it did not exist.
- `environment.yml` at repo root.
- Filled `.gitignore`, which existed but was empty.
- Copied `docs/dental-clinic-system-build-plan.md` → `docs/BUILD_PLAN.md` (verified
  byte-identical by SHA256) so CLAUDE.md's reference resolves. **The original was left in
  place — the user removes it with `git rm`, since deletion is a git operation they own.**
- `CLAUDE.md`: bumped current step to 0.2; removed three stale duplicate tech-stack rows
  (Hosting and Monitoring each appeared twice, contradicting each other).
- Created `docs/PROJECT.md`, `docs/TECH_STACK.md`, `docs/ARCHITECTURE.md`.

### Decisions
- **`cors_origins` is a `str`, not `list[str]`**, split on commas by a `cors_origins_list`
  property. pydantic-settings parses list-typed fields as JSON, which would reject the plain
  `CORS_ORIGINS=http://localhost:3000` form in a `.env` file.
- **SQLAlchemy, Alembic, and psycopg are installed but unused** until step 0.5. The step brief
  listed them explicitly, so they are pinned now for a stable env.
- **Node 24 over Node 20** — see the table above and `docs/TECH_STACK.md`.

### Verified
- `cd backend && conda run -n dental-clinic python -m pytest -q` → 1 passed.
- Live uvicorn on 127.0.0.1:8000 → `GET /health` returned HTTP 200
  `{"status":"ok","environment":"development"}`.

### Later addition — CLAUDE.md gitignored
On the user's instruction, `CLAUDE.md` was added to `.gitignore` (2026-07-17). It was already
tracked, so the user also needs `git rm --cached CLAUDE.md` for the ignore to take effect.

Consequence: the working rules and hard constraints no longer travel with the repo. They are
summarised in the START HERE block above as a fallback, but **CLAUDE.md remains the
authority** — if it is absent, ask the user for it rather than proceeding on the summary.

### Open items carried forward
- **Starlette deprecation warning:** Starlette 1.3 wants `httpx2` instead of `httpx` for
  `TestClient`. Tests pass — warning only. Left alone because the brief pins `httpx`; changing
  it is a dependency decision for the user. Noted in `docs/TECH_STACK.md`.
- **PC restart pending** so Docker lands on PATH. Not needed until step 0.4.

### Suggested commit
`feat: add FastAPI backend with health check`

---

## Next up — Phase 1, Step 1.1 (not started)

**Auth & roles.** This is the first cloud dependency, even in local mode — a free Supabase
project's auth API, called from localhost. Never self-roll auth (hard constraint).

- **Confirm the approach with the user first** (Supabase vs Clerk; free project setup).
- 1.1: managed auth + a login page.
- Then 1.2 staff_user model + roles array, 1.3 role guards + role-aware nav, 1.4 audit_log.

This crosses out of Phase 0's "local only" into needing an external account. Plan mode first;
stop and confirm before creating any accounts or adding SDKs.
