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

**Where we are:** Phase 0 — Foundation. **Step 0.2 is complete.** Step 0.3 (Next.js frontend)
is next and has not been started.

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

**Known gotchas:**
- A shell started before an install won't see new PATH entries. Check the filesystem and the
  registry PATH (`[Environment]::GetEnvironmentVariable("Path","Machine")`) before concluding
  something isn't installed.
- `pytest` must run from `backend/` — `backend/pytest.ini` sets `pythonpath = .` so `app.main`
  imports.

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

## Next up — Step 0.3 (not started)

Scaffold `frontend/` with create-next-app: TypeScript, Tailwind, App Router, ESLint, **no
`src/`**, alias `@/*`. Init shadcn/ui, add button + card. One page: clinic name + a "System OK"
card.

Two constraints from the brief that are easy to miss:
- `next.config.js` **must** set `output: "standalone"` — step 0.4's Docker build depends on it.
- The health fetch **must** be client-side (`"use client"`) hitting `NEXT_PUBLIC_API_URL`.
  A server component using a Docker hostname breaks in the browser.

Then stop at CHECKPOINT 0.3.
