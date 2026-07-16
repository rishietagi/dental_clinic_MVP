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

## Backend

| Choice | Version | Why |
|---|---|---|
| FastAPI | 0.139.2 | The backend framework. Auto-generated OpenAPI docs come free. |
| uvicorn[standard] | 0.51.0 | ASGI server that runs FastAPI. `[standard]` adds fast HTTP parsing and reload. |
| pydantic | 2.13.4 | Request/response validation. Comes with FastAPI. |
| pydantic-settings | 2.14.2 | Loads config from env vars, so nothing is hardcoded and local/prod differ by config only. |
| python-dotenv | 1.2.2 | Lets pydantic-settings read a local `.env` file. |

## Database — installed, not yet used

Pinned now so the environment is stable, but no code imports them until step 0.5.

| Choice | Version | Why |
|---|---|---|
| SQLAlchemy | 2.0.51 | ORM and data access layer. |
| Alembic | 1.18.5 | Schema migrations — evolving the schema without losing real patient data. |
| psycopg[binary] | 3.3.4 | PostgreSQL driver. `[binary]` avoids needing a local compiler. |

## Tests

| Choice | Version | Why |
|---|---|---|
| pytest | 9.1.1 | Test runner. |
| httpx | 0.28.1 | HTTP client backing FastAPI's `TestClient`. |

## Chosen but not yet installed

These are committed decisions from `BUILD_PLAN.md`, listed here so the table above can stay
limited to what exists. Each moves up when the step that introduces it lands.

| Layer | Choice | Arrives in |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui — on Node 24 | Step 0.3 |
| Containers | Docker + Docker Compose — frontend image `node:24-alpine`, backend `python:3.12-slim` | Step 0.4 |
| Proxy | Caddy | Step 0.4 |
| Database | PostgreSQL (managed) | Step 0.5 |
| CI | GitHub Actions — tests only | Step 0.6 |
| Auth | Managed — Supabase Auth or Clerk. Never self-rolled. | Phase 1 |
| Hosting | Single VPS or PaaS — decided in Phase 7 | Phase 7 |
| Monitoring | Sentry + UptimeRobot | Phase 8 |

## Known issues

- **Starlette 1.3 deprecation warning on `TestClient`.** It now prefers `httpx2` over `httpx`.
  The tests pass; this is a warning only. Left as-is because `httpx` is the pinned choice —
  revisit if it becomes an error.
