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

**Where we are:** Phase 0 — Foundation. **Step 0.3 is complete.** Step 0.4 (Docker Compose)
is next and has not been started — but see the WSL blocker below.

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

**Blocker for step 0.4 (not 0.3):** Docker Desktop cannot start — its WSL2 backend is broken.
`wsl --version` fails with `Wsl/CallMsi/Install/REGDB_E_CLASSNOTREG` ("class not registered"),
and Docker Desktop shows "WSL needs updating" / "Engine starting". Fix from an **elevated**
PowerShell: `wsl --update`, or `wsl --install --no-distribution` if that errors the same way,
then reboot and wait for "Engine running". The Docker CLI itself is fine (29.6.1, on PATH) —
only the engine is down. Node-based work (step 0.3) is unaffected.

**Known gotchas:**
- A shell started before an install won't see new PATH entries. Check the filesystem and the
  registry PATH (`[Environment]::GetEnvironmentVariable("Path","Machine")`) before concluding
  something isn't installed.
- `pytest` must run from `backend/` — `backend/pytest.ini` sets `pythonpath = .` so `app.main`
  imports.

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

## Next up — Step 0.4 (not started)

Docker. **Blocked until WSL is fixed** — see the blocker note in START HERE.

- Backend `Dockerfile` on `python:3.12-slim`.
- Frontend `Dockerfile` **multi-stage** (deps / builder / runner) on **`node:24-alpine`**
  (not 20 — see the decisions table), using the standalone output.
- **The frontend Dockerfile needs `ARG NEXT_PUBLIC_API_URL` + `ENV` before `npm run build`.**
  `NEXT_PUBLIC_*` is inlined at **build** time. Miss this and production calls `localhost`
  from the user's browser and fails silently, looking like a CORS problem.
- `docker-compose.yml` (local): db (`postgres:16-alpine` + healthcheck + named volume),
  backend (`--reload`, bind mount), frontend, caddy on :80.
- `Caddyfile`: `{$SITE_ADDRESS:http://localhost}`, `handle /api/*` → `strip_prefix /api` →
  `reverse_proxy backend:8000`; `handle` → `reverse_proxy frontend:3000`.

Then stop at CHECKPOINT 0.4.
