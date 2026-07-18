# TECH STACK

Every dependency that is **installed today**, with its pinned version and one line on why.
A new row goes in whenever a dependency is added. Choices that are planned but not yet
installed are listed at the bottom, separately, so this table stays honest.

## Environment

| Choice | Version | Why |
|---|---|---|
| Python | 3.12 | Current stable; matches the `python:3.12-slim` image planned for Docker. |
| conda | env `dental-clinic` | Isolates project deps from base/global. Reproduced by `environment.yml`. |
| Node.js | 24.18.0 (npm 11.16.0) | Installed locally for the frontend. See the decision below — the Docker image must match this major. |

### Decision: Node 24, not Node 20

The original step 0.4 brief pinned the frontend image to `node:20-alpine`, but the machine has
Node 24.18.0 installed (winget package id reads `OpenJS.NodeJS.22`; the binary is the
authority at v24.18.0). Rather than downgrade, **the project standardises on Node 24** —
decided 2026-07-17.

**Therefore `frontend/Dockerfile` must use `node:24-alpine`, not `node:20-alpine`.**

Why it matters: the local machine generates `package-lock.json`, and the container installs
from it. If the two run different Node majors, a lockfile or native dependency can resolve
differently in the container than locally — a failure that surfaces at build or deploy time
and is painful to trace. Local and container majors stay matched.

## Frontend

| Choice | Version | Why |
|---|---|---|
| Next.js | 16.2.10 | The frontend framework. App Router, no `src/` dir, import alias `@/*`. |
| React | 19.2.4 | Comes with Next 16. |
| TypeScript | 5.x | Catches bugs at build time. |
| Tailwind CSS | 4.x | Utility CSS. **v4 is CSS-first** — no `tailwind.config.js`; configured via `@import "tailwindcss"` in `app/globals.css`. |
| @tailwindcss/postcss | 4.x | The PostCSS plugin Tailwind 4 builds through. |
| ESLint | 9.x | Linting, via `eslint-config-next`. |
| shadcn/ui | CLI 4.13.x | Component source copied into `components/ui/`, not a dependency to version-lock. Currently: `button`, `card`, `input`, `label`. |

### Auth (Supabase) — added step 1.1

| Choice | Version | Why |
|---|---|---|
| @supabase/supabase-js | ^2.110.7 | Supabase client SDK. Backs `signInWithPassword`, `signOut`, `getUser`. |
| @supabase/ssr | ^0.12.3 | Cookie-based session handling for the Next.js App Router — browser + server clients and the `proxy.ts` session refresh. |

Managed auth runs in the **frontend/browser layer** for now. Env vars
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (the publishable/anon
key — safe in the browser) are inlined at **build** time, so they are build args in
`frontend/Dockerfile` + `docker-compose.yml`, sourced from the gitignored root `.env`. The
FastAPI backend does **not** yet verify the Supabase JWT — that arrives in step 1.3.

> **Next 16 note:** the request-interception file is `frontend/proxy.ts` (exporting `proxy`),
> not `middleware.ts`. Next 16.2 deprecated the `middleware` convention and renamed it to
> `proxy` (identical API). Supabase's own docs still say `middleware` — we use `proxy`.

**Pulled in by `shadcn init`** — not chosen separately, but they are real dependencies now:

| Choice | Version | Why |
|---|---|---|
| @base-ui/react | ^1.6.0 | Unstyled primitives that shadcn components build on. |
| class-variance-authority | ^0.7.1 | Component style variants. |
| clsx + tailwind-merge | ^2.1.1 / ^3.6.0 | Conditional class names; back the `cn()` helper in `lib/utils.ts`. |
| lucide-react | ^1.24.0 | Icon set shadcn components use. |
| tw-animate-css | ^1.4.0 | Animation utilities for Tailwind 4. |

## Backend

| Choice | Version | Why |
|---|---|---|
| FastAPI | 0.139.2 | The backend framework. Auto-generated OpenAPI docs come free. |
| uvicorn[standard] | 0.51.0 | ASGI server that runs FastAPI. `[standard]` adds fast HTTP parsing and reload. |
| pydantic | 2.13.4 | Request/response validation. Comes with FastAPI. |
| pydantic-settings | 2.14.2 | Loads config from env vars, so nothing is hardcoded and local/prod differ by config only. |
| python-dotenv | 1.2.2 | Lets pydantic-settings read a local `.env` file. |
| PyJWT[crypto] | 2.13.0 | Verifies Supabase access tokens (added 1.3). `PyJWKClient` fetches + caches the JWKS public keys; `jwt.decode` checks the ES256 signature + audience + issuer + expiry. |
| cryptography | 49.0.0 | Backs PyJWT's ES256 (elliptic-curve) signature verification. |

## Database access

Wired into the app as of step 0.5: engine + session in `app/db.py`, `Base` in
`app/models/`, Alembic configured. Models so far: **`staff_user`** (1.2 — `ARRAY(Text)` roles,
UUID PK = the Supabase Auth UUID), **`audit_log`** (1.4 — append-only trail with a `JSONB`
`details` column, written via `app/services/audit.py::record_audit`, the first `services/`
module), and **`patient`** (2.1 — soft-delete via `archived`, stores `date_of_birth` with a
computed `age` property). **Four migrations now:** empty root → `add_staff_user` →
`add_audit_log` → `add_patient`.

Backend app structure as of 2.5: `app/models/` (ORM), `app/schemas/` (Pydantic request/response
contracts — added 2.2), `app/routers/` (`auth`, `patients`), `app/services/` (`audit`), two seed
scripts (`app/seed.py` admin, `app/seed_patients.py` ~50 dev patients — stdlib only, no faker),
plus `auth.py`/`config.py`/`db.py`. The **patient CRUD** router (`app/routers/patients.py`) is
the first full resource API; **2.3 added `GET /patients` list+search** (plain `ILIKE`, no index
yet). **Phase 2 is complete.**

Frontend as of 2.4: the patient list `app/patients/` (search box + Tailwind results table) and
the **profile page** `app/patients/[id]/` — the app's **first dynamic route** — with the
medical-notes banner. Navigation uses `next/link` (built into Next; no new dep) via the
`href`-aware `role-nav`; list rows link to profiles. Patient fetches reuse the authed
browser-fetch pattern (`lib/use-patient-search.ts`, `lib/use-patient.ts`). Still only shadcn
`button`/`card`/`input`/`label` — tables/banner are hand-rolled Tailwind (no table component
added).

| Choice | Version | Why |
|---|---|---|
| SQLAlchemy | 2.0.51 | ORM and data access layer. Engine with `pool_pre_ping`; `SessionLocal`; `get_db` dependency. |
| Alembic | 1.18.5 | Schema migrations. DB URL read from `DATABASE_URL` in `env.py` (removed from `alembic.ini` so no accidental prod migration). |
| psycopg[binary] | 3.3.4 | PostgreSQL driver. `[binary]` avoids needing a local compiler. |

## Tests

| Choice | Version | Why |
|---|---|---|
| pytest | 9.1.1 | Test runner. |
| httpx | 0.28.1 | HTTP client backing FastAPI's `TestClient`. |

## Containers & infrastructure

Local dev runs the whole stack via `docker compose up --build`. Verified with Docker engine
29.6.1 / Compose v5.3.0.

| Choice | Image / version | Why |
|---|---|---|
| Docker Compose | v5.3.0 | Orchestrates the four local services. `docker-compose.yml` at repo root. |
| Frontend image | `node:24-alpine` | Multi-stage (deps/builder/runner), serves the Next.js standalone build. Node 24 to match the local toolchain. |
| Backend image | `python:3.12-slim` | Runs uvicorn. |
| Postgres | `postgres:16-alpine` | The db service. **Runs but nothing connects yet** — app wiring is step 0.5. |
| Caddy | `caddy:2-alpine` | Reverse proxy and single entry point on `:80`. Routes `/api/*` → backend, else → frontend. |
| GitHub Actions | `.github/workflows/ci.yml` | CI on push/PR to main. Two parallel jobs: backend `pytest` (Python 3.12, pip) — **now with a `postgres:16` service + `alembic upgrade head`** so the DB-backed tests run (added 1.2); frontend `npm ci` + lint + build (Node 24). **Tests only — no deploy** (Phase 7). |

## Chosen but not yet installed

These are committed decisions from `BUILD_PLAN.md`, listed here so the tables above can stay
limited to what exists. Each moves up when the step that introduces it lands.

| Layer | Choice | Arrives in |
|---|---|---|
| Hosting | Single VPS or PaaS — decided in Phase 7 | Phase 7 |
| Monitoring | Sentry + UptimeRobot | Phase 8 |

> Auth (Supabase) moved into the installed tables above as of step 1.1.

## Known issues

- **Starlette 1.3 deprecation warning on `TestClient`.** It now prefers `httpx2` over `httpx`.
  The tests pass; this is a warning only. Left as-is because `httpx` is the pinned choice —
  revisit if it becomes an error.
