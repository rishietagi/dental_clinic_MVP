# PROJECT

## What this is

A staff-only clinic management web app for a single small dental clinic in Davangere, India.
Two computers, 2–3 users. It will hold real patient records and run as a production system,
in parallel with a bought vendor product until it has proved itself.

This document describes **what exists today**. The plan for what comes next lives in
[BUILD_PLAN.md](BUILD_PLAN.md); the record of what was done and decided along the way is in
[LOG.md](LOG.md).

## Scope

**In scope:** patient records · appointments & scheduling · visits (recording the procedure
performed) · follow-up scheduling from inside the visit · billing & payments · dashboard and
basic reports · staff auth with three roles.

**Out of scope** — decided, not deferred. Do not build these: prescriptions · treatment plans
(quoted/estimated) · consent forms · dental charting / odontogram · inventory · patient portal
or any patient login · insurance claims.

Two things that *were* on that list and are now deliberately built, at the clinic owner's
request: **patient file uploads** (X-rays/photos — opaque file storage, never charting) and
**lab work tracking**. Do not "correct" them back out.

## Roles

Three roles, staff only — no patient ever logs in. A user holds a **set** of roles, so one
person can be both dentist and admin without logging in twice.

| Role | Who | Access |
|---|---|---|
| **Receptionist** | Front-desk staff | Register/edit patients, book/reschedule/cancel appointments, check-in, schedule follow-ups, create invoices, take payments, view today's dashboard |
| **Dentist** | The clinic owner | Everything a receptionist can do, plus record visits, close or continue a treatment, schedule follow-ups from the visit screen, view reports |
| **Admin** | The clinic owner (same login) | Everything, plus manage staff logins, edit the treatment list, clinic settings |

## Current status

- **Phase:** 6 — reports & local polish **(in progress)**. Phases 0–5 complete, plus the 5.6
  uploads interlude.
- **Step:** 6.9 done. Next: any further demo feedback, then **Phase 7 — deployment**.

The app is **feature-complete on localhost** and still **local-only** — no deploy config exists
before Phase 7. See [LOG.md](LOG.md) for the full record and the decisions behind it.

### What actually exists

**Backend** (`backend/`) — FastAPI + SQLAlchemy + Alembic, **303 tests**
- **15 models**: `staff_user`, `audit_log`, `patient`, `appointment`, `treatment`, `visit`,
  `procedure_performed`, `treatment_item`, `invoice`, `invoice_line`, `payment`,
  `clinic_settings`, `patient_file`, `lab`, `lab_case`. 15 migrations.
- **9 services**: `audit`, `appointments`, `visits`, `treatments`, `clinic`, `billing`,
  `storage`, `reports`, `lab`.
- Supabase JWT verification with roles read from **our** `staff_user.roles`; role guards on the
  API, audit logging on mutations.
- Double-booking prevented by a Postgres **GiST EXCLUDE** constraint — the DB is the guarantee.

**Frontend** (`frontend/`) — Next.js 16 + TS + Tailwind 4 + Base UI/shadcn
- Dashboard (today's schedule, collections, and worklists for follow-ups, unbilled visits, lab
  work), day/week calendar with drag-drop, patients + profile (header with balance/next
  appointment, over tabs), chairside visit recording, billing + printable receipts, invoices
  ledger, lab management, reports (Recharts), and settings (clinic, pricing, staff, labs).
- Warm/mint design system with light + dark themes.

**Infrastructure** (`docker-compose.yml`, `Caddyfile`) — Caddy (`:80`) → frontend + backend,
plus Postgres and an `uploads` volume. Caddy routes `/api/*` to the backend.

## How to run locally

### With Docker (the whole stack)

Requires Docker Desktop running.

```bash
docker compose up --build
```

Open **http://localhost** — clinic name + a green **System OK** card. The API is at
`http://localhost/api/health` (Caddy strips `/api` and forwards to the backend). Stop with
`docker compose down`.

**Run database migrations** (needs the db service up):

```bash
docker compose run --rm backend alembic upgrade head
```

This applies any pending migrations. On a fresh database it creates the `alembic_version`
tracking table and applies the empty baseline. `docker compose down` keeps your data (named
volume `pgdata`); `docker compose down -v` **deletes** it — only do that to reset.

**Seed demo data** (fake data only — never real patient data on a dev machine):

```bash
docker compose run --rm backend python -m app.seed          # the admin staff row
docker compose run --rm backend python -m app.seed_demo     # a full demo clinic
docker compose run --rm backend python -m app.seed_demo --reset   # wipe first, then reseed
```

`seed_demo` **simulates the clinic's workflow forward in time** — each patient is walked through
register → book → arrive → treat → bill → pay (→ follow up / send to lab) — so the data can never
contain a state the app itself couldn't produce. It is deterministic, and a no-op without
`--reset` once seeded.

### By hand (per-service dev)

Faster for iterating on one side. Two terminals.

Requires [conda](https://docs.conda.io/) and Python 3.12 (backend) and Node.js 24 (frontend).

```bash
# One-time: create the environment
conda env create -f environment.yml

# Configure
cp backend/.env.example backend/.env

# Run the API
cd backend
conda run -n dental-clinic uvicorn app.main:app --reload
```

Then `curl http://localhost:8000/health` → `{"status":"ok","environment":"development"}`.
Interactive API docs are at http://localhost:8000/docs.

Run the tests:

```bash
cd backend
conda run -n dental-clinic python -m pytest
```

All Python dependencies install into the `dental-clinic` conda env only — never base, never
global.

### Frontend

Requires Node.js 24.

```bash
cd frontend
npm install                        # first time only
cp .env.local.example .env.local   # sets NEXT_PUBLIC_API_URL
npm run dev
```

Open http://localhost:3000. You should see the clinic name and a green **System OK** card.
If the card is red, the backend isn't running — start it first (above).

**Run both together.** The frontend needs the backend for the health card to go green. Two
terminals: `uvicorn` on :8000, `npm run dev` on :3000. The backend's `CORS_ORIGINS` already
allows `http://localhost:3000`.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and PR to `main`: a backend job (`pytest`) and a
frontend job (`npm ci` + lint + build), in parallel. **Tests only — no deploy.** Deploy is
added to CI in Phase 7, not before.

## How to deploy

**Not yet decided, and deliberately so.** Everything through Phase 6 runs locally. Deployment
is researched and chosen in Phase 7, once there is an application worth sizing; the options
comparison gets written to `docs/DEPLOYMENT_OPTIONS.md` at that point. Real patient data does
not enter the system until a backup restore has been tested in Phase 8.3.
