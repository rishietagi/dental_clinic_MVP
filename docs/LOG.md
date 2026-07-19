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

**Where we are:** **PHASE 3 IN PROGRESS.** Phase 2 complete (2.1–2.5). **Steps 3.1–3.5 done:**
the `appointment` model + FKs (3.1, migration `56fda58b828c`), the **booking API + double-booking
prevention** (3.2, migration `feae714ecef5`), the **day-view calendar** (3.3), the **week view +
drag-drop reschedule** (3.4), and the **status workflow** (3.5). **Next is step 3.6** — dashboard v1
(today's schedule + arrivals). Still **six migrations** (head = `feae714ecef5`; 3.3–3.5 were
query/UI/logic only — no schema change). Two seed scripts: `app.seed` (admin) and
`app.seed_patients` (dev patients) — no appointment seed yet.

**Status workflow (3.5):** appointment status is a state machine in the API (no DB CHECK/enum):
`booked → arrived → done`, with `booked/arrived → cancelled | no_show`; `done`/`cancelled`/`no_show`
terminal. Changed via **`POST /appointments/{id}/status`** (`get_current_staff`, audited
`action="status"`). Unknown status → **422** (schema `Literal`); known-but-illegal transition
(incl. same→same) → **409**. `no_show` is stored underscored, shown "No-show". **Only `cancelled`
frees a slot** (the 3.2 constraint) — `done`/`no_show` are historical so they don't, which is why
**no migration** was needed. State machine lives in `services/appointments.py` (`can_transition`);
the frontend mirrors it in `lib/appointment-status.ts` (labels/colours/next-status + `changeStatus`).
Day view has coloured pills **and** status buttons; week view **colours cards** only (grid is
cramped — status controls live in the day view).

**Calendar (3.3 + 3.4):** `/calendar` (`app/calendar/`) has a **Day | Week toggle**
(`calendar-view.tsx`). Day view = read-only list (3.3). **Week view (3.4)** = a time grid (rows =
30-min slots 09:00–17:30, cols = 7 days) with **drag-drop reschedule** via **`@dnd-kit/core`** (new
approved dep): dragging a card PATCHes `start_time`; a same-dentist overlap comes back **409** and
shows inline (card reverts). Fed by `GET /appointments?from=&to=` — the list endpoint now takes
**either** `date=` (one day) **or** `from`/`to` (inclusive range); exactly one form, else 422.
**Carried forward:** clinic hours + slot size are hardcoded in `lib/week.ts` (Phase 4 clinic
settings); the UTC-day-bounds / browser-local-render timezone caveat still stands (Phase 4).

**Day-view (3.3):** screen at `/calendar` (`app/calendar/`), fed by `GET /appointments?date=`,
which now returns **`patient_name` + `dentist_name`** (resolved via a join in `list_appointments`
→ new `AppointmentListItem` schema). Read-only + date nav (Prev/Today/Next + `<input type="date">`).
**Known limitation:** the day query uses **UTC** day bounds and the frontend renders in the
**browser's** zone; the clinic is IST with no clinic-timezone config yet (Phase 4). An IST evening
slot could fall on the next UTC day. Consistent with the app's UTC-everywhere treatment; fix needs
the Phase-4 clinic-timezone setting — **carried forward, do not build ahead.**

**Appointment rules to hold onto:** `patient_id` → `patient.id` is a real FK, NOT NULL;
`dentist_id` → `staff_user.id` is a real FK, nullable (unassigned allowed). **`treatment_id` is a
bare nullable UUID with NO foreign key** — deferred to 4.2. `status` defaults to `booked` (the
transition *workflow* is 3.5); `duration_min` defaults to 30.

**Booking rules (3.2):** endpoints are `POST /appointments`, `GET /appointments/{id}`,
`GET /appointments?date=YYYY-MM-DD` (day list), `PATCH /appointments/{id}` (reschedule) — all
guarded by `get_current_staff`, all mutations audited. **Double-booking is prevented by a Postgres
GiST EXCLUDE constraint `appointment_no_overlap`** (the DB is the real guarantee; the service's
`find_conflicts` pre-check is just for a friendly 409, and an IntegrityError from the constraint is
translated to the same 409). Overlap = half-open `[start, start+duration)` in **UTC wall-clock**,
same dentist, ignoring `cancelled`. NULL dentist never conflicts. No status transitions / cancel
endpoint yet (3.5). No appointment UI yet (3.3).

**Patient rules to hold onto:** soft-delete only via `archived` (never hard-delete — medico-
legal retention); `medical_notes` is one free-text field (banner later); **DOB is stored, not a
stale `age` int** (age is a computed `@property`); no patient id in URL query strings (matters
for 2.2 routes).

**Key linkage:** `staff_user.id` **IS** the Supabase Auth user's UUID (the JWT `sub`). The auth
chain verifies the token → reads `sub` → loads the `staff_user` row by PK → checks roles. Roles
live in **our** Postgres (`staff_user.roles`), never in the token — the token's `role` claim is
just the Postgres role `"authenticated"`. Fetching roles from the DB means role/active changes
take effect immediately, without re-issuing tokens.

**The working rules that matter most** (CLAUDE.md is the authority; this is the fallback copy):
- Plan mode first. No file changes before the user approves.
- **Never run *mutating* git.** No add/commit/push/pull/branch/merge/rebase/tag/reset/stash,
  no touching `.git/`. The user stages, commits, and pushes. At a checkpoint, say it's ready
  and suggest a message — nothing more.
  - **Read-only git IS allowed** (user clarified): `git status`, `git log`, `git diff`,
    `git branch --show-current`, `git show`. Use `git status` when it helps at a checkpoint.
    (This refines CLAUDE.md's blanket "never run git" — the intent was to own commits/history,
    not to ban inspecting state.)
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
| **`proxy.ts`, not `middleware.ts`** | Supabase docs say `middleware.ts` | Next 16.2 **deprecated** the `middleware` file convention (renamed to `proxy`; same API). Our root file is `frontend/proxy.ts` exporting `proxy()`. The Supabase *helper* is still `lib/supabase/middleware.ts` (`updateSession`) — that name is unaffected. | `frontend/proxy.ts` |
| **`staff_user.id` = Supabase UUID** | — | The staff_user PK is literally the Supabase Auth user's UUID (JWT `sub`). No separate linking column. 1.3 maps token→row by PK. | `backend/app/models/staff_user.py` |
| **Migrations ship in the image** | — | `alembic upgrade head` runs from the built image, so **rebuild the backend image after adding a migration** before applying — otherwise Alembic uses the image's stale copy and silently no-ops ("already at head"). Generating a migration uses a `-v backend:/app` bind mount so the file lands on the host. | `backend/Dockerfile` |
| **audit_log has a JSONB `details` col** | ERD has only id/actor_id/action/entity/entity_id/at | Added a nullable `JSONB details` beyond the ERD for context (e.g. what changed). Deliberate, flagged deviation. `actor_id` is nullable with **no FK** (audit outlives its actors; null = system/seed). | `backend/app/models/audit_log.py` |
| **patient stores DOB, not `age`** | ERD says `int age` | A stored age goes stale; we store nullable `date_of_birth` and compute `age` via a read-only `@property`. Also added `updated_at` beyond the ERD. Deliberate, flagged deviations. | `backend/app/models/patient.py` |
| **appointment.treatment_id has NO FK yet** | ERD shows `treatment_id FK` | `treatment` doesn't exist until Phase 4. `treatment_id` is a bare **nullable UUID column** now (so 3.2 can reference it and the shape matches the ERD); the actual FK constraint is added in **Phase 4 (4.2)** once `treatment` exists. A test asserts a random `treatment_id` inserts fine (proves the deferral). `patient_id`/`dentist_id` ARE real FKs. | `backend/app/models/appointment.py` |
| **Status is an app-level state machine (no DB enum)** | — | Appointment `status` stays a free-text column; the allowed transitions (`booked→arrived→done`, `booked/arrived→cancelled\|no_show`, terminals) are enforced in `services/appointments.py` `can_transition` and exposed via `POST /{id}/status`. Unknown value → 422 (schema `Literal`); illegal transition → 409. **Only `cancelled` frees a slot** (3.2 constraint); `done`/`no_show` are historical, so no constraint/migration change. `no_show` stored underscored, shown "No-show". Frontend mirrors the map in `lib/appointment-status.ts` (UX only; API is the guard). | `backend/app/services/appointments.py`, `backend/app/routers/appointments.py` |
| **Double-booking = GiST EXCLUDE constraint (first hand-written migration)** | — | `appointment_no_overlap` is a Postgres `EXCLUDE USING gist` constraint — the real double-booking guarantee (survives two racing PCs). **First hand-written migration** (autogenerate can't emit EXCLUDE / CREATE EXTENSION); needs the **`btree_gist`** extension. The range must use **immutable** arithmetic: `timestamptz + interval` is only STABLE and Postgres rejects it in a constraint, so we use `tsrange(timezone('UTC', start_time), timezone('UTC', start_time) + duration_min*interval '1 min', '[)')`. The service `find_conflicts` pre-check uses the SAME expression (keep them in sync). Excludes `cancelled`; NULL dentist never clashes. | `backend/alembic/versions/feae714ecef5_*.py`, `backend/app/services/appointments.py` |
| **Visual/CSS polish deferred to Phase 6** | — | Frontend is intentionally plain during feature work. **Do NOT** do cosmetic/design passes as tasks in Phases 2–5 — keep UI plain-but-usable. Real design/polish pass lands in **Phase 6 (6.2 + a broader design pass)**, before demo/deploy. (User instruction, 2026-07-19.) | — |

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

## 2026-07-19 — Step 3.5: appointment status workflow

**Status:** complete — state machine + dedicated endpoint + colour-by-status + day-view controls,
verified (65 tests pass; frontend lint+build green; state machine proven live against the compose
Postgres). For commit. **No migration** — status is an existing free-text column.

### Scope decisions (confirmed with user)
- **Enforced state machine** (API-validated): `booked → arrived → done`; `booked/arrived →
  cancelled | no_show`; `done`/`cancelled`/`no_show` terminal. Illegal transition (incl. same→same)
  → **409**; unknown status → **422**.
- **Dedicated `POST /{id}/status`** (mirrors patient archive/unarchive), any active staff, audited
  (`action="status"`, details `{from, to}`). Reschedule PATCH still never touches status.
- **UI: colour-by-status + controls.** Day view = coloured pills + legal-next-status buttons; week
  view = coloured cards only (grid too cramped for buttons — controls live in the day view, the
  front-desk's working screen).
- **No migration:** only `cancelled` frees a slot (3.2 constraint); `done`/`no_show` are historical
  and deliberately don't free slots.

### Built — backend (no migration)
- `app/services/appointments.py` — `STATUSES`, `_ALLOWED` transition map, `can_transition()`.
- `app/schemas/appointment.py` — `AppointmentStatusUpdate` (`Literal` of the 5 statuses → 422 for
  anything else).
- `app/routers/appointments.py` — `POST /{id}/status`: 404 / 409 (illegal) / 200 + audit.
- `tests/test_appointments.py` — +7: happy path booked→arrived→done (+audit), off-ramps
  (cancelled/no_show from booked and arrived), illegal/terminal + same→same → 409, unknown → 422,
  404, and **cancelling frees the slot** (ties status to the booking rule). 58 → **65**.

### Built — frontend
- `lib/appointment-status.ts` — `STATUS_LABELS`, `STATUS_STYLES` (blue/amber/green/muted-strike/red),
  `NEXT_STATUSES` (mirrors the backend map), and `changeStatus()` (POST → "ok"|"conflict"|error).
- `lib/use-day-appointments.ts` — added the `refetch()` nonce (so a status change refreshes).
- `app/calendar/day-view.tsx` — coloured `StatusBadge`; new `StatusActions` (legal-next buttons per
  row, terminal shows "—"; 409 → note + refetch); an Actions column + inline notice.
- `app/calendar/week-view.tsx` — cards coloured by status (`statusStyle`), title = label.

### No new deps / migration / env / CI

### Verified
- **65 tests pass** in-container against real Postgres. Frontend `lint` + `build` green.
- **Live against the compose Postgres:** book→arrived→done (200s); done→arrived → **409** with a
  clear message; unknown status → **422**; unknown appointment → **404**. Cleaned up.
- **Through Caddy** (full stack up): `/calendar` guard 307→/login (checked earlier); stack left up
  with seeded data for a user visual check of the coloured statuses + status buttons.

### Carried forward → 3.6
- **Dashboard v1**: today's schedule + arrivals — will lean on `GET /appointments?date=today` and
  the `arrived` status. Visit recording (what "done" leads to) is Phase 4. Clinic hours/timezone
  still Phase 4.

### Suggested commit
`feat: add appointment status workflow`

---

## 2026-07-19 — Step 3.4: week view + drag-drop reschedule

**Status:** complete — small backend range widening + the week-view calendar with drag-drop,
verified (58 tests pass; frontend lint+build+Docker build green with the new dep; range list +
reschedule + 409 proven live against the compose Postgres; route/guard checked through Caddy). For
commit. **First new frontend dependency since Phase 1.**

### Scope decisions (confirmed with user)
- **List endpoint gains a date-range mode.** `GET /appointments` now takes EITHER `date=` (one day,
  unchanged) OR `from`/`to` (inclusive range) — exactly one form, else **422**. One request loads a
  whole week.
- **Full time-grid drag-drop** (user chose day+time-slot granularity over day-only): rows = 30-min
  slots, cols = 7 days; a drop snaps to a (day, slot) cell and PATCHes `start_time`.
- **Day | Week toggle** on `/calendar`; the 3.3 day view is unchanged.
- **New dependency `@dnd-kit/core`** — user-approved. `core` alone (no `/sortable` or `/modifiers`).

### Built — backend (query only, no migration)
- `app/routers/appointments.py` `list_appointments` — accepts `date` OR `from`+`to` (aliased; `from`
  is a Python keyword). Validation guard: neither, both, or a half-given range → 422
  (`HTTP_422_UNPROCESSABLE_CONTENT`, the non-deprecated constant). Same patient/dentist-name join.
- `tests/test_appointments.py` — `test_list_by_range` (spans days, excludes outside), boundaries
  inclusive, and `test_list_requires_exactly_one_form` (neither/both/half → 422).

### Built — frontend
- **`@dnd-kit/core ^6.3.1`** installed (pulls `@dnd-kit/accessibility` + `/utilities`).
- `lib/week.ts` — pure date/slot helpers: `startOfWeek` (Monday), `weekDays`, `addWeeks`,
  `daySlots` (09:00–17:30 @ 30 min — **hardcoded**, Phase 4 clinic settings), `slotForStart`,
  `slotDate`, `cellId`/`parseCellId`. Local-zone throughout (timezone caveat).
- `lib/use-week-appointments.ts` — range fetch (`?from=&to=`) with `refetch()`, plus
  `rescheduleAppointment(id, iso)` → `"ok" | "conflict" | {error}` (maps the PATCH 409).
- `app/calendar/calendar-view.tsx` — Day|Week toggle wrapper; `page.tsx` renders it instead of
  `<DayView/>` directly. Day view untouched.
- `app/calendar/week-view.tsx` — the grid: `DndContext` + `PointerSensor` (5px activation so clicks
  still work), draggable `ApptCard`s, droppable (day, slot) `Cell`s, `DragOverlay`. On drop:
  compute new local `start_time`, PATCH; **409 → inline "slot taken" + card stays** (refetch on
  success). Week nav (Prev/This week/Next). Patient profile links kept in a separate list below the
  grid (keeps grid cards drag-focused, click-vs-drag clean).

### Dependency added (asked user)
`@dnd-kit/core ^6.3.1` (frontend). Recorded in `docs/TECH_STACK.md`.

### Verified
- **58 tests pass** in-container (55 prior + 3 range) against real Postgres.
- Frontend `lint` + `build` green; **Docker frontend image rebuilds** (npm ci picks up the new dep,
  TS compiles with dnd-kit types). `/calendar` still one route.
- **Live against the compose Postgres** (the drag-drop's data path): range list returns the week's
  appointments with names; **reschedule to a free slot → 200**; **reschedule onto a taken slot (same
  dentist) → 409** "overlaps an existing appointment"; 422 guards (neither/both). Cleaned up.
- **Through Caddy:** `/calendar` signed-out → **307 → /login**.
- **Note:** the drag *gesture* itself (dnd-kit pointer interaction) is a browser action not driven
  headlessly — but every API behaviour it relies on is proven, and the build type-checks the DnD
  wiring. Handed to the user for a visual click-through.

### Carried forward → 3.5
- **Status workflow** (booked → arrived → done / cancelled / no-show) + colour-by-status on the
  calendar. The `cancelled` status already frees a slot (3.2 constraint). Clinic hours/slot config +
  the timezone fix remain Phase 4.

### Suggested commit
`feat: add week view and rescheduling`

---

## 2026-07-19 — Step 3.3: day-view calendar (first appointment UI)

**Status:** complete — small backend widening + the first appointment screen, verified (55 tests
pass; frontend lint+build green; day-list names proven live against the compose Postgres; route +
guard checked through Caddy). For commit. **First appointment UI.**

### Scope decisions (confirmed with user)
- **Day-list response now carries names.** `GET /appointments?date=` returns `patient_name` +
  `dentist_name` (a calendar must show *who*), resolved via a **join** in `list_appointments` — one
  query, no N+1. New lighter `AppointmentListItem` schema; `AppointmentRead` (single-GET/POST/PATCH)
  unchanged.
- **Read-only day view + date navigation only.** No booking form, no status changes, no drag-drop
  (those are later steps / a dedicated screen).

### Built — backend (query only, no migration)
- `app/schemas/appointment.py` — `AppointmentListItem` (adds `patient_name`, `dentist_name`;
  `dentist_name` None when unassigned). `AppointmentListResponse.items` now points at it.
- `app/routers/appointments.py` `list_appointments` — `select(Appointment, Patient.name,
  StaffUser.name).join(Patient).outerjoin(StaffUser)` (dentist nullable → outerjoin), building each
  item from the row tuple. Auth guard + day bounds unchanged.
- `tests/test_appointments.py` — `test_list_items_carry_names`: assigned appt → `dentist_name` set;
  unassigned → None; `patient_name` matches.

### Built — frontend (first appointment screen)
- `lib/use-day-appointments.ts` (`"use client"`) — authed fetch of `GET /appointments?date=`
  (clones `use-patient-search`, no debounce; re-fetches on date change). States loading/ready/error.
- `app/calendar/page.tsx` — server shell (back-link + `<DayView/>`), like `patients/page.tsx`.
- `app/calendar/day-view.tsx` (`"use client"`) — date state (defaults today), **Prev/Today/Next** +
  native `<input type="date">`, a Tailwind table (Time `HH:MM–HH:MM` from start+duration, Patient →
  `/patients/{id}`, Dentist, a neutral Status pill, Reason). loading/error/**empty** states.
- `app/role-nav.tsx` — added a **Calendar** nav link (`CalendarDays`, any staff). Second real
  in-app link after Patients.

### No new deps / migration / env / CI
Native date input + existing shadcn `Button`; `lucide-react` already present. Schema unchanged (the
change is query/response only), so no Alembic migration.

### Verified
- **55 tests pass** in-container (54 prior + 1 names test) against real Postgres.
- Frontend `lint` + `build` green; `/calendar` is a registered route.
- **Live against the compose Postgres:** seeded a patient + dentist + appointment, called the day
  list through the real endpoint → `patient_name="Live Patient"`, `dentist_name="Dr Live"`,
  correct time/duration/status; cleaned up. (Exercises the join end-to-end on the served DB.)
- **Through Caddy:** `/calendar` signed-out → **307 → /login** (proxy guard); `/api/appointments`
  no token → **401**. Backend startup clean.

### Known limitation — carried forward (do NOT fix now)
The day query uses **UTC** day bounds; the frontend renders in the **browser's** local zone. The
clinic is IST (UTC+5:30) and there's no clinic-timezone config yet (Phase 4 clinic settings). So an
IST evening appointment could land on the next UTC day. This is consistent with the app treating
time as UTC everywhere; a proper fix needs the Phase-4 clinic-timezone setting. Don't build timezone
config ahead of Phase 4.

### Carried forward → 3.4
- Week view + drag-drop reschedule (the `PATCH` reschedule API already exists from 3.2). Booking
  form + status workflow still later (3.5 / dedicated screen). Clinic-timezone fix in Phase 4.

### Suggested commit
`feat: add day view calendar`

---

## 2026-07-19 — Step 3.2: booking API + double-booking prevention

**Status:** complete — schemas + service + router + hand-written migration + tests, verified
against the real Docker Postgres (constraint applied + reversible, 54 tests pass, live through
Caddy). For commit. **First appointment endpoints; first hand-written migration.**

### Scope decisions (confirmed with user)
- **Double-booking enforced by a Postgres GiST `EXCLUDE` constraint** — the DB rejects overlapping
  non-cancelled appointments for the same dentist atomically (survives two racing PCs, BUILD_PLAN
  §11). The service also pre-checks for a friendly **409**; a constraint `IntegrityError` that
  slips past the pre-check (the race) is translated to the same 409, not a 500.
- **Cancelled slots don't block** — the constraint's `WHERE (status <> 'cancelled')` frees a
  cancelled slot's time. No cancel endpoint yet (3.5), but building it now = no migration change in 3.5.
- **Endpoints:** `POST /appointments` (conflict-checked, 404 if patient missing), `GET
  /appointments/{id}`, `GET /appointments?date=YYYY-MM-DD` (day list, for 3.3), `PATCH
  /appointments/{id}` (reschedule, re-checks excluding itself). **No status transitions** (3.5).

### Built
- `app/schemas/appointment.py` — `AppointmentCreate` (no `status`; `duration_min` default 30,
  `ge=5`), `AppointmentUpdate` (all optional, PATCH), `AppointmentRead`, `AppointmentListResponse`.
- `app/services/appointments.py` — **second `services/` module.** `find_conflicts(...)` returns
  overlapping non-cancelled appointments for the same dentist (`[]` when `dentist_id is None`);
  `exclude_id` skips the row being rescheduled. Uses the **same UTC `tsrange` expression as the
  constraint** so pre-check and backstop agree.
- `app/routers/appointments.py` — the four endpoints, guarded by `get_current_staff`, mutations
  audited (`entity="appointment"`). `_commit_or_conflict` maps the `appointment_no_overlap`
  IntegrityError → 409. Registered in `app/main.py`.
- `alembic/versions/feae714ecef5_add_appointment_no_overlap_constraint.py` — **hand-written**
  (empty revision then filled). `down_revision = 56fda58b828c`. `CREATE EXTENSION btree_gist` +
  the EXCLUDE constraint; downgrade drops both.
- `tests/test_appointments.py` — 16 endpoint tests (patient-router template): create+audit,
  defaults, patient-404, get/404, **overlap→409**, **back-to-back OK** (half-open `[)`), different-
  dentist OK, NULL-dentist OK, **cancelled-doesn't-block**, **DB-constraint-is-the-backstop** (insert
  a clash straight through the ORM → IntegrityError), list-by-day (ordered), reschedule (+ onto-
  another→409, + self-no-false-conflict).

### No new deps / env / CI
SQLAlchemy + native Postgres. `btree_gist` is a DB extension enabled by the migration, not a pip
package. CI's Postgres + `alembic upgrade head` + pytest cover it.

### Bug hit + fixed during build (worth remembering)
The first constraint used `start_time + make_interval(mins => duration_min)` inside the EXCLUDE —
Postgres rejected it: **"functions in index expression must be marked IMMUTABLE."** `timestamptz +
interval` is only **STABLE** (depends on the session TimeZone). Fix (verified against the DB before
committing to it): cast to a fixed zone first — `timezone('UTC', start_time)` (immutable) → plain
`timestamp`, then `+ interval` (immutable), in a plain `tsrange`. Two appointments overlap in real
time iff their UTC representations overlap, so it's equivalent. The service's `find_conflicts` uses
the identical expression.

### Verified (against the real db)
- Migration applied `56fda58b828c -> feae714ecef5`; `\d appointment` shows the `appointment_no_overlap`
  EXCLUDE constraint. **Reversible:** downgrade drops the constraint **and** `btree_gist`; upgrade
  re-adds. (Rebuilt the backend image before applying — the stale-image footgun.)
- **54 tests pass** in-container (38 prior + 16 appointment) against real Postgres. Host DB-skip
  path still holds.
- **Live through Caddy:** `/api/health` 200; `/api/appointments` GET+POST with no token → **401**
  (route wired, guard active); backend startup clean, no warnings.

### Gotcha (recorded from 3.1, hit again)
Generating/bind-mounting migrations must run from **PowerShell**, not the Bash tool — Git Bash
`${PWD}` (`/c/...`) doesn't map for Docker Desktop, so the file lands in the ephemeral `--rm`
container and is lost.

### Carried forward → 3.3
- API is ready for the **day-view calendar** (`GET /appointments?date=` feeds it). No frontend yet.
  Reschedule exists but no drag-drop (3.4). Status transitions + cancel are 3.5. `treatment_id` FK
  still deferred to Phase 4.

### Suggested commit
`feat: add booking with conflict checks`

---

## 2026-07-19 — Step 3.1: appointment model + migration (Phase 3 begins)

**Status:** complete — model + migration + tests, verified against the real Docker Postgres
(migration up/down, table/FKs inspected, 38 tests pass). For commit. **First table with foreign
keys** in the schema.

### Scope decisions (confirmed with user — deviations flagged)
- **`treatment_id`: bare nullable UUID, NO foreign key yet.** `treatment` doesn't exist until
  Phase 4, so a real FK can't be created without building ahead. Column added now (shape matches
  ERD, 3.2 can reference it); FK constraint deferred to **4.2**. See the standing-decisions row.
- **`patient_id` → `patient.id` (NOT NULL)** and **`dentist_id` → `staff_user.id` (nullable)** are
  **real FK constraints** — the schema's first. `dentist_id` nullable = a slot may be booked
  before a dentist is assigned.
- **No `ondelete` cascades** — patients are soft-deleted and staff deactivated (never hard-
  deleted), so cascade behaviour never triggers. Plain restrict-by-default FKs.
- **`status` column + default `booked` only** — the transition *workflow* (arrived/done/
  cancelled/no-show) is **step 3.5**. No CHECK/enum (kept flexible; validated in the API later).
- **No `relationship()` navigations, no endpoints** — booking API is 3.2.

### Built
- `app/models/appointment.py` — `Appointment`: `id` UUID PK (`gen_random_uuid()`), `patient_id`
  (FK→patient, not null), `treatment_id` (nullable UUID, no FK), `dentist_id` (FK→staff_user,
  nullable), `start_time` (timestamptz, not null), `duration_min` (Integer, default 30), `status`
  (Text, default `booked`), `reason` (nullable Text), `created_at`/`updated_at` (timestamptz).
  Registered in `app/models/__init__.py`.
- `alembic/versions/56fda58b828c_add_appointment.py` — autogenerated, reviewed clean.
  `down_revision = 7d0a0ba7961b`. Two `ForeignKeyConstraint`s (patient, staff_user), none for
  `treatment_id`. `updated_at`'s app-level `onupdate` correctly absent from DDL.
- `tests/test_appointment.py` — all DB-backed (no pure-logic property here), skip-if-no-DB
  fixture like the other suites: table/columns exist; FK introspection proves patient+dentist FKs
  and **treatment_id has none**; insert + server defaults (`status=booked`, `duration_min=30`);
  **patient FK enforced** (bad id → IntegrityError); **treatment_id random id inserts fine**
  (deferral proven behaviourally). Cleans up appointments before patients (FK order).

### No new deps / env / CI
SQLAlchemy `ForeignKey`/`Integer` already available. CI's Postgres + `alembic upgrade head` covers
the new migration and tests automatically.

### Verified (against the real db)
- Autogenerate detected only `appointment`. `\d appointment` shows the exact columns/types, both
  FKs (`appointment_patient_id_fkey`, `appointment_dentist_id_fkey`), **no FK on treatment_id**,
  `duration_min` default 30, `status` default `booked`.
- Migration up: `7d0a0ba7961b -> 56fda58b828c`. Down/up proven: `downgrade -1` drops the table
  (psql "did not find any relation"), `upgrade head` recreates it.
- **38 tests pass** in-container (33 prior + 5 appointment). Host run (no DB): the 5 appointment
  tests **skip fast** — skip-if-no-DB guard holds.

### Gotcha hit (workflow, not the app)
Generating the migration via the bind-mount **must run from PowerShell, not the Bash tool.** In
Git Bash `${PWD}` is `/c/Users/...` (MSYS form), which Docker Desktop does not map to the Windows
host — the file wrote into the ephemeral `--rm` container and was lost. Re-running the exact same
command from PowerShell (where `${PWD}` is a real Windows path) persisted the file. Applying
migrations (no mount) is unaffected.

### Carried forward → 3.2
- No booking API yet. 3.2 adds create/list appointments + **double-booking prevention at the
  service/DB layer** (BUILD_PLAN §11 — two PCs will race). `treatment_id` FK still deferred to 4.2.

### Suggested commit
`feat: add appointment model`

---

## 2026-07-18 — Step 2.5: seed ~50 fake patients (PHASE 2 COMPLETE)

**Status:** complete — script + tests, verified against the real Docker Postgres (seeds 50,
idempotent on re-run, 33 tests pass). For commit. **This finishes Phase 2.**

### Scope decisions (confirmed with user)
- **Hand-rolled Indian name pools + stdlib `random`** — **no faker / no new dependency.**
- **Idempotent via a count guard** — if `patient count >= SEED_COUNT (50)`, skip (no dup pile-up).
  Never wipe/hard-delete patient rows (soft-delete rule holds even for fake data).
- **One summary audit row** (`action="seed", entity="patient", details={"count":50}`), not 50.

### Built
- `app/seed_patients.py` (`python -m app.seed_patients`) — split into **`generate_patients()`**
  (pure, deterministic per seed, no DB — unit-testable) and **`seed_patients()`** (count-guard
  idempotency + `session.add_all` + one summary `record_audit` + commit). ~30 first / 25 last
  Karnataka-plausible names, `+91` mobiles (10 digits starting 6–9), DOB→age ~5–85, ~20% with
  `medical_notes`, ~10% archived. Lets the DB fill `id`/timestamps.
- `tests/test_seed_patients.py` — generator unit tests (count, field shape, determinism —
  **no DB, run everywhere**) + a light DB persistence test (insert a few, confirm, clean up).

### No new deps / migration / env / CI

### Verified (real db)
- Generator tests pass on the host (no DB). Full suite **33 passed** in-container.
- Seed run: 2 pre-existing + 50 → **52 total**, **12 with notes**, **5 archived**; realistic
  Indian names + `+91` phones. **Summary audit row** `seed/patient {"count":50}` present.
  **Re-run → "already seeded (52 present), skipping"** (idempotent, count unchanged).

### Known cosmetic quirk (harmless)
Name and gender are randomized independently, so a seeded row can pair a typically-male first
name with gender "Female" (e.g. "Aarav … Female"). It's fake dev data; not worth gender-tagged
name pools. Noted here so it isn't mistaken for a bug.

### PHASE 2 COMPLETE
Patients: model, CRUD API (auth + audit + soft-delete), list/search, profile + medical-notes
banner, and seed data. The whole patient loop works against ~50 realistic records.

### Suggested commit
`chore: add seed data script`

---

## 2026-07-18 — Step 2.4: patient profile page + medical-notes banner

**Status:** complete — frontend-only; lint+build green, route + auth-guard verified. **Browser
click-through (banner shown/hidden, 404) handed to the user.** For commit.

### Scope decisions (confirmed with user)
- **Overview only** — demographics + medical-notes banner. **No Treatments/Billing tab shells**
  (Phases 4–5; no empty placeholders).
- **Read-only** — display + link list rows to the profile. **No edit/archive/create UI** this
  step (PATCH/archive API exists from 2.2 but isn't surfaced yet).

### Built (all frontend; backend already had `GET /patients/{id}` from 2.2)
- `lib/use-patient.ts` (`"use client"`) — single-patient authed fetch (clones the search-hook
  pattern, no debounce). States `loading | ready | not-found (404) | error`. Returns the FULL
  record incl. `medical_notes` (only the single-patient endpoint returns that).
- `app/patients/[id]/page.tsx` — the app's **first dynamic route**. Next 16 `params` is a
  Promise (`await params`). Id is a **path segment** (allowed; the no-id-in-URL rule is about
  query strings).
- `app/patients/[id]/patient-profile.tsx` — Overview `Card` (name, phone, age, DOB, gender;
  archived marker; "—" for missing) + a **`MedicalNotesBanner`** that renders **only when
  `medical_notes` is non-empty** (amber/warning styling, alert icon) — the one clinically
  important element. Back-to-patients link. not-found/error states handled.
- `app/patients/patient-list.tsx` — each row's name is now a `next/link` to `/patients/{id}`
  (rows were intentionally non-links in 2.3 "until the profile exists").

### No backend / migration / deps / CI change

### Verified
- `npm run lint` + `npm run build` green; build shows `/patients/[id]` as a **dynamic route**
  (`ƒ`) — the app's first.
- Route + guard: `GET /patients/{id}` with no session → **307 → /login** (proxy guard; route
  registered/matched).
- Two test patients created for the browser check (one **with** medical notes: "Diabetic… on
  blood thinners", one **without**). User confirms the banner shows for the first and is absent
  for the second, and an unknown id → "Patient not found".

### Watch-out handled
- `react-hooks/set-state-in-effect` (bit 0.3 and 2.3): the single-patient hook uses the async
  IIFE pattern (setState inside the async body, guarded by `cancelled`), so it's clean.

### Carried forward → 2.5 (last Phase 2 step)
- **Seed ~50 fake patients** (a seed script, faker-style) so the list/search/profile have
  realistic data to browse. Some with `medical_notes` so the banner is visible in the seed set.

### Suggested commit
`feat: add patient profile view`

---

## 2026-07-18 — Step 2.3: patient list + search (API + first frontend page)

**Status:** complete — backend list/search + the first patient UI, verified (29 tests pass;
search proven live through Caddy; frontend lint+build green). For commit.

### Scope decisions (confirmed with user)
- **Backend search API + a frontend list page** (not API-only).
- **No search index / no migration this step.** At clinic scale a plain `ILIKE '%q%'` seq-scan is
  instant; a `pg_trgm` GIN index is premature. Documented as the escalation path if the patient
  count ever grows large. (Resolves 2.1's "defer indexes to 2.3" → "not needed yet".)
- **Lighter list item** — list rows omit `medical_notes` (sensitive; only on the profile). List
  response includes `total`.

### Built — backend
- `app/schemas/patient.py` — `PatientListItem` (id, name, phone, dob, age, gender, archived — **no
  medical_notes**) + `PatientListResponse` (`{items, total}`).
- `app/routers/patients.py` — `GET /patients` (`get_current_staff`): `q` (case-insensitive
  substring on **name OR phone**), `include_archived` (default false), `limit` (1–100, default
  20), `offset`. `total` via a count over the filtered subquery; ordered by name. Reads not
  audited.
- `tests/test_patients.py` — +4 tests: auth required, name+phone search (and the item omits
  medical_notes), archived hidden by default / shown with the flag, pagination + limit-cap 422.

### Built — frontend (first patient UI + first navigation)
- `lib/use-patient-search.ts` (`"use client"`) — debounced (300 ms) authed fetch to
  `/patients?q=…`, cloning the `use-current-staff` token pattern. States loading/ready/error.
- `app/patients/page.tsx` — the route (server shell) + `app/patients/patient-list.tsx`
  (`"use client"`) — a search `Input` + a hand-rolled Tailwind results table (name/phone/age/
  gender, archived marker, total, empty/loading/error states). Rows are **not** links yet (the
  profile page is 2.4 — no dead links).
- `app/role-nav.tsx` — added an optional `href` to `NavItem` and a **Patients** entry; items with
  an `href` now render as `next/link` `<Link>`s. **This is the app's first in-app navigation** —
  nothing used `next/link` before. Placeholder items (Dashboard/Reports/Admin) stay plain spans.

### No new deps / migration / CI change

### Verified
- **29 tests pass** in-container (25 prior + 4 list/search) against real Postgres.
- Frontend `lint` + `build` green; `/patients` route registered.
- **Live through Caddy** (real token): created 2 patients → `GET /patients` `total=2`, **list
  items carry no `medical_notes`**; `?q=asha` → 1 (age computed); `?q=9822` (phone) → matches;
  no-token → 401.

### Fix during build
- ESLint `react-hooks/set-state-in-effect` (same rule as step 0.3): the search hook set loading
  synchronously in the effect body. Moved the `setState({kind:"loading"})` inside the deferred
  debounce callback. Clean after.

### Carried forward → 2.4
- Patient **profile page** at `/patients/{id}` + the **medical-notes banner** (non-empty
  `medical_notes` renders as a banner). Then the list rows can link to it.

### Suggested commit
`feat: add patient list and search`

---

## 2026-07-18 — Step 2.2: patient CRUD API + tests

**Status:** complete — router + schemas + tests, verified (25 tests pass in-container; full CRUD
proven live through Caddy with a real ES256 token, incl. the audit trail). Torn down clean.
For commit. **First real resource API** — where Phase 1's auth + audit machinery gets used.

### Scope decisions (confirmed with user)
- **Single-resource CRUD only** (create / read-one / update / archive / unarchive). **List +
  search are 2.3** — no `GET /patients` list here.
- **All active staff can do everything** (receptionist/dentist/admin) — so every route guards
  with `get_current_staff` ("any active staff"), no per-endpoint role split.
- **Audit mutations only** — create/update/archive/unarchive write an audit row; reads don't.
- **Soft-delete only** — archive flips `archived`; no hard DELETE route exists.

### Built
- `app/schemas/__init__.py` + `app/schemas/patient.py` — **first `schemas/` package.**
  `PatientCreate` (name required), `PatientUpdate` (all optional, PATCH), `PatientRead`
  (`from_attributes`, includes the computed `age`; explicit fields = no column leakage).
- `app/routers/patients.py` (`prefix="/patients"`):
  - `POST /patients` (201), `GET /patients/{id}` (404 if missing; returns archived too),
    `PATCH /patients/{id}` (partial via `exclude_unset`; skips empty patches),
    `POST /patients/{id}/archive` + `/unarchive`.
  - Every mutation calls `record_audit(db, actor_id=staff.id, entity="patient", …)` then a
    single `db.commit()` — the change and its audit row commit **atomically**. `details` via
    `jsonable_encoder` so dates land clean in JSONB.
  - `patient_id` is a **path** param, never a query string (hard rule). `_get_or_404` helper.
- `app/main.py` — `include_router(patients.router)`.
- `tests/test_patients.py` — DB-backed. Auth faked via `dependency_overrides[get_current_claims]`
  = `{"sub": <created staff id>}` (same trick as test_auth). Cases: create→201 + audit,
  no-auth→401, get 200/404, patch changes only sent fields + audit, archive/unarchive soft (row
  still fetchable) + audit.

### No new deps / env / CI
FastAPI/Pydantic/SQLAlchemy already present; CI Postgres + tests cover it.

### Verified
- **25 tests pass** in-container against real Postgres (20 prior + 5 patient-endpoint).
- **Live through Caddy** with a real token (test@clinic.local temp-seeded as staff):
  CREATE→201 (`age=41` from DOB, `archived=false`), GET→200, PATCH phone-only (name untouched),
  ARCHIVE→`archived=true` **and still fetchable** (soft-delete), unknown id→404, no-token→401.
  `audit_log` showed `create` (all fields), `update` (`{"phone": …}`), `archive` rows with the
  actor's id. Temp data cleaned up; stack down clean.

### Gotcha (test script, not the app)
PowerShell `$PID` is a read-only automatic variable, and `$global:` vars don't survive between
separate PowerShell tool calls — the first live-test attempt failed for both reasons. Fixed by
using a non-reserved var and one self-contained script. No app issue.

### Carried forward → 2.3
- Add `GET /patients` list + search by name/phone, pagination, and the **name/phone indexes**
  deferred from 2.1. List should default to non-archived.

### Suggested commit
`feat: add patient CRUD endpoints`

---

## 2026-07-18 — Step 2.1: patient model + migration (Phase 2 begins)

**Status:** complete — model + migration + tests, verified against the real Docker Postgres
(migration up/down, 20 tests pass). Torn down clean. For commit.

### Scope decisions (confirmed with user — deviations flagged)
- **`date_of_birth` (nullable `Date`), not `int age`.** Age is a computed read-only `@property`
  (None when DOB unknown). A stored age silently goes stale; DOB doesn't.
- **Added `updated_at`** (server default `now()`, `onupdate=func.now()`) beyond the ERD.
- **`archived` flag now; name/phone search indexes deferred to 2.3** (index to match the real
  query there).

### Built
- `app/models/patient.py` — `Patient`: `id` UUID PK (`gen_random_uuid()`), `name` (Text, not
  null), `phone`/`date_of_birth`/`gender`/`medical_notes` (nullable), `archived` (bool, default
  false — **soft-delete only, never hard-delete**), `created_at`/`updated_at` (timestamptz).
  Plus the `age` `@property`. Registered in `app/models/__init__.py`.
- `alembic/versions/7d0a0ba7961b_add_patient.py` — autogenerated, reviewed clean.
  `down_revision = bdeca0f73243`. Creates `patient`; downgrade drops it. No name/phone indexes
  (those are 2.3). `updated_at`'s `onupdate` is app-level, so it's correctly absent from the DDL.
- `tests/test_patient.py` — the `age` property tested as **pure logic (no DB, runs everywhere)**:
  None when DOB null, exact-birthday, birthday-not-yet-this-year. Plus DB-backed: table/columns
  exist, insert + server defaults (id/created_at/updated_at, `archived=False`), nullable fields
  accept None. Reuses the skip-if-no-DB fixture.

### No new deps / env / CI
Native Postgres + SQLAlchemy. CI's Postgres + `alembic upgrade head` covers it.

### Verified (against the real db)
- Migration: `\d patient` shows the exact columns/types (uuid PK default `gen_random_uuid()`,
  `date` DOB, `archived` default false, both timestamptz). `downgrade -1` drops it; `upgrade
  head` recreates it.
- **20 tests pass** in-container (health + 3 staff_user + 7 auth + 3 audit + 6 patient). Age
  computation correct. Skip-if-no-DB still holds on a host without Postgres.

### Carried forward → 2.2
- No endpoints yet. 2.2 adds the patient CRUD router: **guard with `require_role(...)`**, **call
  `record_audit` on create/update/archive** (`actor_id=current_staff.id`), **soft-delete via
  `archived`** (no hard delete), and **no patient id in URL query strings**.

### Suggested commit
`feat: add patient model`

---

## 2026-07-18 — Step 1.4: audit_log + record_audit service (PHASE 1 COMPLETE)

**Status:** complete — model + migration + service + seed wiring + tests, all verified against
the real Docker Postgres (migration up/down, seed writes a real row, 14 tests pass). Torn down
clean. For commit. **This finishes Phase 1.**

### Scope decisions (confirmed with user)
- **Table + reusable `record_audit()` helper + the seed writes one entry.** No fake/demo
  endpoints — Phase 2 mutation endpoints will call the helper.
- **Nullable `JSONB details` column** beyond the ERD (flagged deviation — see standing table).
- **`actor_id` nullable, NO foreign key** — audit trails are append-only and must outlive the
  entities they reference; null = a system/seed action.

### Built
- `app/models/audit_log.py` — `AuditLog`: `id` UUID PK (server-generated via
  `gen_random_uuid()`), `actor_id` (nullable, no FK), `action`/`entity` (Text, not null),
  `entity_id` (nullable UUID), `details` (nullable JSONB), `at` (timestamptz default now()).
  Registered in `app/models/__init__.py`.
- `alembic/versions/bdeca0f73243_add_audit_log.py` — autogenerated, reviewed clean.
  `down_revision = 36612590e356`. Creates the table; downgrade drops it.
- `app/services/__init__.py` + `app/services/audit.py` — **first `services/` module.**
  `record_audit(db, *, actor_id, action, entity, entity_id=None, details=None)` inserts one row
  into the **caller's** session and `flush()`es (does NOT commit — the caller owns the
  transaction, so the audit row and the change it records commit atomically together).
- `app/seed.py` — now calls `record_audit(..., actor_id=None, action="seed",
  entity="staff_user", entity_id=admin_id, details={...})` in the same session before commit.
- `tests/test_audit_log.py` — DB-backed (reuses the skip-if-no-DB fixture): table/columns exist;
  `record_audit` populates server defaults (id, at); `details` JSON round-trips as a dict;
  `actor_id=None` allowed; actor-set + no-details case works.

### No new deps / env / CI
JSONB + `gen_random_uuid()` are native to Postgres 16; SQLAlchemy already supports both. CI's
Postgres + `alembic upgrade head` (from 1.2) covers the new migration and tests automatically.

### Verified (against the real db)
- Migration: autogenerate detected only `audit_log`; `\d audit_log` shows the exact
  columns/types (uuid PK default `gen_random_uuid()`, jsonb details, nullable actor_id/entity_id,
  timestamptz default now()). `downgrade -1` drops it; `upgrade head` recreates it.
- **Seed writes a real audit row:** `SELECT … FROM audit_log` →
  `action=seed, entity=staff_user, entity_id=c03c75be-…, actor_id NULL,
  details={"roles":["dentist","admin"],"result":"updated"}`, server `at`. (Append-only: re-running
  the seed adds another seed row — expected.)
- **14 tests pass** in-container (health + 3 staff_user + 7 auth + 3 audit). Skip-if-no-DB still
  holds on a host without Postgres.

### Carried forward → Phase 2
- `record_audit` is the hook: every Phase 2 mutation (create/update/archive patient, etc.) should
  call it with `actor_id=current_staff.id`, inside the same transaction as the change.
- No audit-viewing UI (reports are Phase 6). No middleware auto-audit (too coarse).

### Suggested commit
`feat: add audit logging`

---

## 2026-07-18 — Step 1.3: API JWT verification + role guards + role-aware nav

**Status:** backend built and verified (11 tests pass in-container; all live token paths proven
through Caddy with real ES256 tokens); frontend built (lint+build green). **Browser
interactive login check handed to the user** (same as 1.1). For commit.

### Scope decisions (confirmed with user)
- **ES256 / JWKS, no shared secret.** This project's Supabase tokens are asymmetric (verified
  live: one EC key at `…/auth/v1/.well-known/jwks.json`, `alg=ES256`). Backend verifies with the
  public key — it never holds a secret.
- **JWT lib: `pyjwt[crypto]`** (2.13.0) + `cryptography` (49.0.0). `PyJWKClient` fetches/caches
  the JWKS and refreshes on an unknown `kid`.
- **Demo endpoints only:** `GET /me` + `GET /admin/ping`. No patient/appointment endpoints
  (Phase 2). **Minimal role-aware nav**, no full sidebar shell yet.
- **Frontend reads roles via a browser fetch to `/api/me`** (through Caddy, like health-card) —
  no new env var, no server-container→backend call.

### Built — backend
- `app/auth.py` — the reusable chain:
  `get_current_claims` (HTTPBearer → `jwt.decode` with ES256 + `audience="authenticated"` +
  issuer; 401 on any PyJWT error) → `get_current_staff` (`sub` → `db.get(StaffUser, sub)`; 403
  if no row or `not active`) → `require_role(*roles)` (403 unless the staff row holds one of the
  roles). `PyJWKClient` is built once via `@lru_cache`, lazily, so the app imports without
  `SUPABASE_URL` and only a request that needs it trips the config check.
- `app/routers/auth.py` (first router) — `GET /me` (any active staff → `StaffMe` Pydantic model,
  so no column leakage) and `GET /admin/ping` (`require_role("admin")`). Registered in `main.py`.
- `app/config.py` — `supabase_url` + derived `supabase_jwks_url` / `supabase_issuer` properties.
- `requirements.txt` — `pyjwt[crypto]==2.13.0`, `cryptography==49.0.0` (both pinned, installed
  into `dental-clinic`).
- `tests/test_auth.py` — 2 DB-free (no token → 401) + 5 DB-backed role tests. The DB tests
  override `get_current_claims` via `app.dependency_overrides` to feed a fake `{"sub": …}`, so
  they exercise **our** lookup+role logic deterministically **without minting a real ES256
  token**. Reuses the `test_staff_user` DB-skip fixture pattern.

### Built — frontend (minimal role-aware nav)
- `lib/use-current-staff.ts` (`"use client"`) — gets the session token from the browser Supabase
  client and fetches `/api/me` with a Bearer header. States: loading / staff / not-staff (403) /
  error.
- `app/role-nav.tsx` (`"use client"`) — shows nav items gated by role (Dashboard = all; Reports =
  dentist|admin; Admin = admin), lists the user's roles, and renders a graceful "not set up as
  staff yet" message on 403. Comment stresses this is convenience, not security.
- `app/page.tsx` — renders `<RoleNav />`. (Still a server component reading `user.email`.)

### Env wiring
- Backend `SUPABASE_URL` — added to `config.py`, `backend/.env.example`, and
  `docker-compose.yml` (mapped from the existing root-`.env` `NEXT_PUBLIC_SUPABASE_URL`, so
  there's **one** URL value, no duplication). Root `.env.example` note updated.

### Verified
- **In-container pytest:** `11 passed` (health + 3 staff_user + 7 auth) against real Postgres.
- **DB-free host run:** auth 401 tests pass, DB tests skip fast.
- **Live, real ES256 tokens through Caddy (`http://localhost/api`):**
  - admin token (staff + admin) → `/me` 200 with `roles:[dentist,admin]`; `/admin/ping` 200.
    (Proven by temporarily seeding `test@clinic.local`'s real `sub` as an admin row, hitting the
    endpoints, then deleting it — DB left with only the real admin row.)
  - `test@clinic.local` (valid token, **no** staff row) → `/me` **403** — proves the whole
    signature/JWKS verification succeeded *and* authorization correctly rejected a non-staff user.
  - garbage bearer → **401**; no token → **401**.
- Frontend `lint` + `build` green (`/` dynamic, `/login` static, proxy registered). Stack
  rebuilt and serving on :80.

### Notes / gotchas
- Docker Desktop had exited again between steps (known: the engine doesn't stay up on its own).
  Relaunched; engine 29.6.1 up in ~10s.
- I don't have the real admin's Supabase password — the admin-200 live path was proven via the
  temp-row trick above rather than a real admin login. The frontend admin-nav view is the user's
  browser check.

### Carried forward
- Backend endpoints exist but are still just `/me` + `/admin/ping`. Real resource endpoints
  (patients etc.) are Phase 2 and will use `Depends(require_role(...))`.
- **1.4 next:** `audit_log` table + writing an entry on mutations.

### Suggested commit
`feat: enforce role-based access control`

---

## 2026-07-18 — Step 1.2: staff_user model, roles array, seed admin

**Status:** complete — model + migration + seed + tests + CI all built and verified against the
real Docker Postgres, including the seed run and idempotency. Torn down clean. For commit.

### Scope decisions (confirmed with user)
- **`staff_user.id` = the Supabase Auth UUID** (JWT `sub`) — one identity, no linking column.
- **Roles = Postgres `ARRAY(Text)`** (a set; the mother holds `["dentist","admin"]`).
- **Seed the admin from env vars**, idempotent upsert — `ADMIN_USER_ID` / `ADMIN_EMAIL` /
  `ADMIN_NAME`. No service_role key, no `supabase-py`, no network call (user chose paste-the-UUID
  over the Admin-API lookup).
- **CI gets Postgres now** (first real migration → worth proving), replacing the stale
  "add in Phase 2" comment.

### Built
- `backend/app/models/staff_user.py` — `StaffUser` (SQLAlchemy 2.0 `Mapped`): `id` PGUUID PK
  (not server-generated), `name`, `email` (unique, indexed), `roles ARRAY(Text)` default `{}`,
  `active` bool default true, `created_at` timestamptz default `now()`.
- `backend/app/models/__init__.py` — now imports `StaffUser` at the bottom so it registers on
  `Base.metadata` (else `--autogenerate` sees nothing).
- `backend/alembic/versions/36612590e356_add_staff_user.py` — autogenerated, reviewed, clean.
  `down_revision = 78e9327c7254`. Creates the table + unique email index; downgrade drops both.
- `backend/app/seed.py` — `python -m app.seed`: idempotent upsert of the admin row from env
  vars (fails loud if unset), roles `["dentist","admin"]`. Uses `SessionLocal` from `app/db.py`.
- `backend/app/config.py` — added `admin_user_id` / `admin_email` / `admin_name` (default "").
- `backend/tests/test_staff_user.py` — DB-backed: table/columns exist, roles array round-trips
  as a list, `active`/`created_at` defaults. **Self-skips (fast, ~5s) if no DB reachable** via a
  throwaway engine with `connect_args={"connect_timeout": 2}` — so laptop `pytest` w/o Docker
  passes (health) and skips (staff_user) instead of hanging.
- `.github/workflows/ci.yml` — backend job gains a `postgres:16-alpine` service, a job-level
  `DATABASE_URL`, an `alembic upgrade head` step, then pytest (DB tests now run for real in CI).
- Env wiring: `backend/.env.example`, root `.env.example`, and `docker-compose.yml`
  `backend.environment` all get the three `ADMIN_*` vars (compose reads them from the gitignored
  root `.env` via `${VAR:-}` interpolation, same pattern as the 1.1 Supabase build args).

### Verified (against the running Docker db)
- **Autogenerate** detected `staff_user` + `ix_staff_user_email` only — no stray ops.
- **Migration up:** `alembic upgrade head` → `78e9327c7254 -> 36612590e356`; `psql \d
  staff_user` shows `uuid` PK, `text[]` roles default `{}`, `boolean` active default true,
  `timestamptz` created_at default now(), unique email index. `alembic current` = new head.
- **Migration down/up:** `downgrade -1` drops the table; `upgrade head` recreates it. Both
  directions proven.
- **Tests in-container (bind-mounted):** `4 passed` (health + 3 staff_user) against real PG.
- **Skip path (host, no DB):** `1 passed, 3 skipped` in ~5s — the connect-timeout guard works.
- **CI YAML** parses; backend steps ordered checkout→setup-python→pip→`alembic upgrade head`→
  pytest, with the Postgres service. (Actions run itself is only provable after push.)

### Gotcha hit + recorded (see standing-decisions table)
- `alembic upgrade head` from the plain image silently **no-op'd** at first: the image was built
  before the migration file existed, so it only knew the old head. **Fix: rebuild the backend
  image after adding a migration, then apply.** (Generating still uses the `backend:/app` bind
  mount so the new file persists to the host.)

### Seed verified
- Admin seeded from the gitignored root `.env` (`ADMIN_USER_ID` = the real Supabase UUID
  `c03c75be-…`, email `admin@rndental.com`, name `RN Dental Admin`). First run → "created",
  second run → "updated" (no duplicate). `SELECT … FROM staff_user` → exactly one row,
  `roles = {dentist,admin}`, `active = t`. Idempotency proven.

### Carried forward
- **Backend still has no JWT verification / role guards** — that's 1.3. `/api/*` is open.
- The admin's Supabase user had no display name set; used "RN Dental Admin". Change `ADMIN_NAME`
  in the root `.env` and re-run the seed to update it (idempotent).

### Suggested commit
`feat: add staff users and roles`

---

## 2026-07-18 — Step 1.1: Supabase Auth + login page (Phase 1 begins)

**Status:** complete, verified by-hand in a browser and through the Docker stack, torn down
clean. For commit.

### Scope decisions (confirmed with user before building)
- **Provider: Supabase Auth** (over Clerk) — matches BUILD_PLAN/LOG; same vendor can host prod
  Postgres in Phase 7.
- **Login flow only.** This step ships: login page, cookie session, sign-out, and a route
  guard. **No FastAPI JWT verification** — that is 1.3 (API role guards). Deliberately not
  built ahead. **The backend is untouched this step.**
- **No roles yet.** 1.1 has no `staff_user` table and no role concept: any Supabase-Auth user
  who signs in reaches the app. Roles arrive in 1.2/1.3.
- **User created the Supabase project** (guided step-by-step): free project, Email provider,
  public sign-ups off, one hand-made test user (`test@clinic.local`, auto-confirmed).

### Built (all frontend)
- `frontend/lib/supabase/client.ts` — browser client (`createBrowserClient`).
- `frontend/lib/supabase/server.ts` — server client (`createServerClient`) wired to Next's
  `cookies()`; `setAll` wrapped in try/catch (server components can read but not write cookies).
- `frontend/lib/supabase/middleware.ts` — `updateSession()`: refreshes the token via
  `getUser()` and applies the guard (no user + not `/login` → `/login`; user on `/login` → `/`),
  copying refreshed cookies onto redirects.
- `frontend/proxy.ts` — root proxy delegating to `updateSession`, with a `matcher` excluding
  `_next/*` and static assets. **(Next 16 renamed `middleware.ts` → `proxy.ts`; see the
  standing-decisions table.)**
- `frontend/app/login/page.tsx` + `login-form.tsx` — centered Card, email+password, calls
  `signInWithPassword`, vague "Incorrect email or password." on failure (doesn't leak which),
  `router.refresh()` + push to `/` on success. No signup/forgot links (staff-only).
- `frontend/app/page.tsx` — now an **async server component**: reads the user, shows their email
  + a `SignOutButton`. Still renders the existing `HealthCard`. No role-aware nav (that's 1.3).
- `frontend/app/sign-out-button.tsx` — client button: `signOut()` → refresh → `/login`.
- shadcn `input` + `label` added (form needed them; only `button`/`card` existed before).

### Deps added (asked user)
- `@supabase/supabase-js ^2.110.7`, `@supabase/ssr ^0.12.3` (frontend).

### Env wiring (the build-arg footgun, same as 0.4's `NEXT_PUBLIC_API_URL`)
- `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — **inlined at BUILD
  time**, so they must be present during `npm run build`. Added to: `frontend/.env.local` (dev),
  `frontend/.env.local.example`, `frontend/Dockerfile` (ARG/ENV before build), and
  `docker-compose.yml` frontend build args via `${...}` interpolation.
- Project-specific values come from a **new gitignored root `.env`** (documented by a new
  committed `.env.example`) so nothing project-specific is hardcoded in the committed compose
  file. Root `.env` was already in `.gitignore`.
- **Key naming:** Supabase's current key is the **publishable** key (`sb_publishable_…`), the
  new name for the old "anon" key. The base URL is `https://<ref>.supabase.co` — **not** the
  `/rest/v1/` REST endpoint (user first pasted that; corrected).

### Verified
- `npm run lint` clean; `npm run build` clean, TypeScript clean, `.next/standalone/server.js`
  present. Build shows `/` as `ƒ` (dynamic — reads session), `/login` static, proxy registered.
- **Guard (dev + Docker):** `GET /` signed-out → **307 → `/login`**; `GET /login` → 200.
- **Supabase credentials real:** password grant against `…/auth/v1/token` returns a bearer
  token for `test@clinic.local` (email confirmed). Proves project + key + user.
- **Full browser loop — user confirmed manually:** redirected to `/login` when signed out →
  sign in → home shows email + Sign out + green health card → wrong password shows inline error,
  no crash → reload keeps session → Sign out returns to `/login`.
- **Docker path:** `docker compose up -d --build` → 4 containers, db healthy. Guard + `/login` +
  `/api/health` all correct through Caddy on :80. **Build-arg proof:** the Supabase URL is
  present in a served `/_next/static` JS chunk — confirms it was inlined into the browser
  bundle. `docker compose down` clean.
- Login page screenshotted (styled Card, correct fonts).

### Notes for next session
- **Backend has no auth yet** — no JWT verification, no `Depends` guard. `/api/*` is wide open.
  1.3 adds verification of the Supabase JWT on the API. Don't assume the API is protected.
- The middleware **helper** file is `lib/supabase/middleware.ts` (Supabase's name for
  `updateSession`) — that's fine; only the *root* Next file convention was renamed to `proxy`.
- Test user creds live only in the gitignored `.env`/`.env.local` and Supabase. Not committed.

### Suggested commit
`feat: add authentication`

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
