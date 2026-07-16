# CLAUDE.md — Dental Clinic Management System

Staff-only clinic management web app for a single small dental clinic in Davangere, India. 2 computers, 2–3 users. Real patients, real data, production system.

**The full plan — architecture, ERD, user journeys, screens, and the phased roadmap — is in `docs/BUILD_PLAN.md`. Read it when you need scope or design detail. Do not duplicate it here.**

---

## Working rules

- **Plan mode first, always.** Propose a plan and wait for my approval. No file changes before I approve.
- **One roadmap step at a time.** Never build ahead into the next step or phase, even if it seems trivial. If a step seems to need something from a later phase, stop and ask.
- **Every step must run and be committable** before moving on.
- **Ask before adding any dependency** not already in the tech stack below.
- If something in `docs/BUILD_PLAN.md` looks wrong or contradictory, **say so and ask** — don't silently work around it.
- Prefer boring, obvious code. This is a maintainability project, not a cleverness project.
- **Local only until Phase 7.** Do not add VPS config, prod compose files, domains, TLS,
  cloud hosting, or CI deploy steps before then. If a step seems to need prod config, stop and ask.

## Git — I handle it, you don't

- **Never run `git` commands.** No `init`, `add`, `commit`, `push`, `branch`, `merge`, or `tag`.
- **Never create or modify** `.git/`, or run anything that writes to it.
- I initialise the repo, stage, commit, and push myself.
- When a step is done, just tell me it's ready to commit and suggest a commit message. Nothing more.

## Current status

- **Current phase:** Phase 0 — Foundation
- **Current step:** 0.2
- *(Update these two lines as we progress.)*

## Tech stack (do not deviate without asking)

| Layer | Choice |
|---|---|
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui |
| Backend | FastAPI + Pydantic |
| Database | PostgreSQL (managed — Supabase/Neon) |
| ORM / migrations | SQLAlchemy + Alembic |
| Auth | Managed (Supabase Auth or Clerk) — never self-rolled |
| Containers | Docker + Docker Compose |
| Proxy / TLS | Caddy |
| Hosting | Single VPS or PaaS — **decided in Phase 7, do not implement before** |
| Monitoring | Sentry + UptimeRobot — **Phase 8** |
| CI/CD | GitHub Actions — tests from Phase 0, **deploy only from Phase 7** |

## Hard constraints

- **Schema changes go through Alembic migrations.** Never manual SQL against live data. Never `DROP` on a table holding real patient data.
- **Role checks belong on the API**, not just hidden UI. A hidden button is not security.
- **Soft-delete patients only** (`archived` flag). Never hard-delete — medico-legal retention.
- **No patient identifiers in URL query strings.**
- **Never write auth/password handling by hand.** Use the managed provider.
- **Never test against live patient data.** That's what staging is for.
- Roles are a **set** on the user (`["dentist", "admin"]`), never a single role string.
- **All config via env vars.** Never hardcode localhost, ports, hostnames, or secrets —
  local and prod must differ by config only.
- **Seed/fake data only until Phase 7.** No real patient data on a laptop.

## Out of scope — do not build

Prescriptions · treatment plans (quoted/estimated) · consent forms · dental charting / odontogram · inventory · lab work tracking · patient portal or any patient login · insurance claims.

If a task seems to require one of these, stop and ask.

## Domain note (the one thing to get right)

Dental treatment is **multi-visit**. An RCT may take 2–4 sittings, and the dentist often doesn't know the count upfront. So:

- A `TREATMENT` threads multiple `VISIT`s together (`"RCT tooth 36"`, status `in_progress` / `completed`).
- A `TREATMENT` is **not** a treatment plan — no estimates, no quotes, no acceptance tracking. Only: what, which tooth, still ongoing?
- Single-visit work (e.g. a cleaning) auto-creates and auto-closes a treatment. The user never sees the concept.
- Follow-ups must be schedulable **inline from the visit screen**, not via a separate trip to the calendar.
