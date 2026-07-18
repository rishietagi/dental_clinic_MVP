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
| shadcn/ui | CLI 4.13.0 | Component source copied into `components/ui/`, not a dependency to version-lock. Currently: `button`, `card`. |

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

## Chosen but not yet installed

These are committed decisions from `BUILD_PLAN.md`, listed here so the tables above can stay
limited to what exists. Each moves up when the step that introduces it lands.

| Layer | Choice | Arrives in |
|---|---|---|
| Database (app wiring) | SQLAlchemy engine + Alembic against Postgres | Step 0.5 |
| CI | GitHub Actions — tests only | Step 0.6 |
| Auth | Managed — Supabase Auth or Clerk. Never self-rolled. | Phase 1 |
| Hosting | Single VPS or PaaS — decided in Phase 7 | Phase 7 |
| Monitoring | Sentry + UptimeRobot | Phase 8 |

## Known issues

- **Starlette 1.3 deprecation warning on `TestClient`.** It now prefers `httpx2` over `httpx`.
  The tests pass; this is a warning only. Left as-is because `httpx` is the pinned choice —
  revisit if it becomes an error.
