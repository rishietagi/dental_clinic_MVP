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
(quoted/estimated) · consent forms · dental charting / odontogram · inventory · lab work
tracking · patient portal or any patient login · insurance claims.

## Roles

Three roles, staff only — no patient ever logs in. A user holds a **set** of roles, so one
person can be both dentist and admin without logging in twice.

| Role | Who | Access |
|---|---|---|
| **Receptionist** | Front-desk staff | Register/edit patients, book/reschedule/cancel appointments, check-in, schedule follow-ups, create invoices, take payments, view today's dashboard |
| **Dentist** | The clinic owner | Everything a receptionist can do, plus record visits, close or continue a treatment, schedule follow-ups from the visit screen, view reports |
| **Admin** | The clinic owner (same login) | Everything, plus manage staff logins, edit the treatment list, clinic settings |

## Current status

- **Phase:** 0 — Foundation
- **Step:** 0.4 — Containerised with Docker Compose

### What actually exists

**Backend** (`backend/`)
- A FastAPI app with a single `GET /health` endpoint.
- Settings loaded from environment variables via pydantic-settings.
- CORS middleware driven by the `CORS_ORIGINS` setting.
- One test covering `/health`.

**Frontend** (`frontend/`)
- A Next.js app with one page: the clinic name and a "System OK" card.
- The card calls the backend's `/health` from the browser and shows loading, ok, or error.
- shadcn/ui set up, with `button` and `card` added.

**Infrastructure** (`docker-compose.yml`, `Caddyfile`)
- The whole stack runs under Docker Compose: Caddy (`:80`) → frontend + backend, plus a
  Postgres container. Caddy routes `/api/*` to the backend and everything else to the frontend.
- Postgres runs but **nothing connects to it yet** — that's step 0.5.

Nothing else. No database wiring, no models, no auth, no routing beyond the one page.

## How to run locally

### With Docker (the whole stack)

Requires Docker Desktop running.

```bash
docker compose up --build
```

Open **http://localhost** — clinic name + a green **System OK** card. The API is at
`http://localhost/api/health` (Caddy strips `/api` and forwards to the backend). Stop with
`docker compose down`.

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

## How to deploy

**Not yet decided, and deliberately so.** Everything through Phase 6 runs locally. Deployment
is researched and chosen in Phase 7, once there is an application worth sizing; the options
comparison gets written to `docs/DEPLOYMENT_OPTIONS.md` at that point. Real patient data does
not enter the system until a backup restore has been tested in Phase 8.3.
