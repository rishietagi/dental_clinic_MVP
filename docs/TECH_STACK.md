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
| shadcn/ui | CLI 4.13.x | Component source copied into `components/ui/`, not a dependency to version-lock. Currently: `badge`, `button`, `card`, `dialog`, `dropdown-menu`, `input`, `label`, `separator`, `sonner`, `status-pill`, `table`, `tabs`, `tooltip`. **The primitives underneath are Base UI, not Radix — there is no `asChild`** (use `buttonVariants()` on a `Link` instead). |
| recharts | 3.10.0 | Charts on the Reports screen (6.1) — React+SVG, React-19-compatible. Styled to the **dataviz** validated palette (`lib/chart-theme.ts`), theme-aware. First frontend charting dep. |

### Component library + toasts (6.4)

The UI adopted a larger **shadcn/ui** component set — `table`, `dialog`, `dropdown-menu`, `tabs`,
`tooltip`, `badge`, `separator`, `sonner` — copied into `components/ui/` (source, not a versioned dep).
The one real new npm dependency is **`sonner`** (toast notifications; `next-themes` came along as a
transitive but is **unused** — our Toaster reads the app's own `data-theme` stamp, so we did NOT adopt
next-themes). shadcn's interactive components pull Radix primitives (bundled). No backend dep. The clinic
**logo** lives at `frontend/public/clinic-logo.png` (shown in the sidebar).

### Design system (6.2)

The UI has a real token system as of 6.2 — **no new dependency**, built on the existing Tailwind 4 +
shadcn setup. Colour/radius tokens live in `app/globals.css` (`:root` = warm-sand/mint light theme,
`@media (prefers-color-scheme: dark)` = dark, plus `:root[data-theme]` overrides so a manual toggle wins
over the OS). **Shadcn's token names were kept** (`--primary`, `--card`, `--accent`, `--border`, …) so
components re-skin without markup changes; semantic status tokens (`--good`/`--warning`/`--danger`) are
exposed to Tailwind via `@theme inline`. Shared UI: `components/app-shell.tsx` (header/nav/theme toggle),
`components/states/` (loading/error/empty/skeleton), `components/ui/status-pill.tsx`,
`components/page-header.tsx`. Fonts stay **Geist** via `next/font` (no webfont CDN).

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
| @base-ui/react | ^1.6.0 | Unstyled primitives that shadcn components build on. **Base UI, not Radix** — see the note below. |
| class-variance-authority | ^0.7.1 | Component style variants. |
| clsx + tailwind-merge | ^2.1.1 / ^3.6.0 | Conditional class names; back the `cn()` helper in `lib/utils.ts`. |
| lucide-react | ^1.24.0 | Icon set shadcn components use. |
| tw-animate-css | ^1.4.0 | Animation utilities for Tailwind 4. |

> **No `asChild` — these primitives are Base UI, not Radix.** Most shadcn examples online assume
> Radix and compose with `<Button asChild><Link/></Button>`. That prop **does not exist here** and is
> silently ignored. Base UI composes via a **`render` prop** instead. For a link styled as a button,
> the simplest option is to apply **`buttonVariants()`** to the `Link`'s `className` — which is what
> the profile's "Record visit" does (4.4), and it avoids nesting interactive elements.

**Chosen deliberately** (approved additions beyond the scaffold):

| Choice | Version | Why |
|---|---|---|
| @dnd-kit/core | ^6.3.1 | Pointer-based drag-and-drop for the week-view calendar's drag-drop reschedule (step 3.4). Modular + React-19-compatible; `core` alone (no `/sortable` or `/modifiers`) — snapping comes from discrete droppable (day, slot) cells. Pulls `@dnd-kit/accessibility` + `@dnd-kit/utilities`. |
| date-fns + date-fns-tz | ^4.4.0 / ^3.2.0 | Clinic-timezone handling (step 4.9): `formatInTimeZone` / `toZonedTime` / `fromZonedTime` render times and compute (day, slot) in the clinic's IANA zone instead of the browser's local zone. `date-fns-tz` needs `date-fns` as its peer. Chosen over browser `Intl` for robust zone/offset math; the **backend** does the equivalent with stdlib `zoneinfo` (no backend dep). |

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
| python-multipart | 0.0.32 | Parses multipart form uploads — required for FastAPI `UploadFile`/`Form`. Added 5.6 for patient file uploads (X-rays/photos/documents). |

### File storage (5.6)

Uploaded patient files' **bytes live on disk**, never in Postgres. In local dev they go to a Docker
named volume (`uploads`) mounted at `UPLOAD_DIR=/data/uploads`; the DB (`patient_file`) keeps only
metadata + an opaque `storage_key`. All file I/O goes through a `Storage` protocol in
`app/services/storage.py` (today `LocalStorage`), so **Phase 7 can swap in Supabase Storage / S3 by
implementing the same interface and changing config — no call-site changes.** No cloud storage
dependency is installed yet (that's a Phase-7 decision); `python-multipart` is the only new dep here.

## Database access

Wired into the app as of step 0.5: engine + session in `app/db.py`, `Base` in
`app/models/`, Alembic configured. Models so far: **`staff_user`** (1.2 — `ARRAY(Text)` roles,
UUID PK = the Supabase Auth UUID), **`audit_log`** (1.4 — append-only trail with a `JSONB`
`details` column, written via `app/services/audit.py::record_audit`, the first `services/`
module), and **`patient`** (2.1 — soft-delete via `archived`, stores `date_of_birth` with a
computed `age` property). **Four migrations now:** empty root → `add_staff_user` →
`add_audit_log` → `add_patient`.

Backend app structure as of 6.9: `app/models/` (**15** ORM models), `app/schemas/` (Pydantic
request/response contracts), `app/routers/` (`appointments`, `auth`, `clinic_settings`, `invoices`,
`lab_cases`, `labs`, `patient_files`, `patients`, `reports`, `staff`, `treatment_items`,
`treatments`, `visits`), `app/services/` (**9** modules: `audit`, `appointments`, `visits`,
`treatments`, `clinic`, `billing`, `storage`, `reports`, `lab`), three seed scripts
(`app/seed.py` admin, `app/seed_patients.py` dev patients, `app/seed_demo.py` a full simulated
demo clinic — stdlib only, no faker), plus `auth.py`/`config.py`/`db.py`. **303 tests.**

Frontend as of 6.9: **17 routes** — dashboard `/` (today's schedule, collections, and the
follow-up / ready-to-bill / nothing-recorded / lab worklists), `/calendar` (day + week, drag-drop),
`/patients` + `/patients/new` + `/patients/[id]` (header with balance and next appointment, over
Treatments · Billing · Appointments · Files · Details tabs) + `/patients/[id]/visits/new`
(chairside), `/appointments/new`, `/invoices` + `/invoices/[id]` + `/receipt` +
`/invoices/new/[visitId]`, `/lab` + `/lab/new`, `/reports`, `/settings/clinic`,
`/settings/treatments` (Pricing), and `/login`.

A persistent **app shell** (`components/app-shell.tsx`) wraps every signed-in page with a left
sidebar, role-aware nav, and theme toggle; `/login` opts out. Data access is one hook module per
resource in `lib/` (`use-patients`, `use-appointments`, `use-visits`, `use-invoices`, `use-labs`,
`use-worklists`, …), all sharing the authed browser→Caddy→backend fetch pattern with a refetch
nonce. Money crosses the wire as **decimal strings** and is formatted with `Intl.NumberFormat` —
never float arithmetic.

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
