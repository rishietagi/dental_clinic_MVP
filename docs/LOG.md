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

**Where we are:** Phases 0–3 are complete. **PHASE 4 HAS BEGUN** (the clinical core). Phase 3 gave
us the appointment stack: model + FKs (3.1, migration `56fda58b828c`), **booking API +
double-booking prevention** (3.2, migration `feae714ecef5`), **day-view calendar** (3.3), **week
view + drag-drop reschedule** (3.4), **status workflow** (3.5), **dashboard v1 on `/`** (3.6).
**Step 4.1 is done:** the **treatment catalogue** (`treatment_item` + admin Settings CRUD, migration
`73aeddd50693`). **Step 4.2 is done:** the **clinical core models** — `treatment` + `visit` +
`procedure_performed`, and **`appointment.treatment_id` finally got its real FK** (migration
`999215bea700`). **Step 4.3 is done:** the **visit recording API** (`POST /visits` auto-creates and
auto-closes treatments; the project's **second role-split resource**). **Step 4.4 is done:** the
**visit record screen** at `/patients/{id}/visits/new`, plus a read-only **`GET /treatments`** and
visit history on the profile. **Step 4.5 is done:** the **treatment lifecycle** —
`POST /treatments/{id}/close` + `/reopen` (the treatments router's **first write routes**) and
Close/Reopen controls in a compact Treatments section on the profile. **Step 4.6 is done:** the
**inline follow-up scheduler** on the visit form — after recording, it books the next appointment
linked to the treatment (`appointment.treatment_id`, first use of that FK from the UI, and the
**first booking-from-UI path** at all). **Step 4.7 is done:** the patient profile now shows
**treatments each expandable to their nested visits** (merged from the old flat Treatments list +
separate visit-history card; grouped **client-side**, no new endpoint). **Step 4.8 is done —
PHASE 4'S FEATURE WORK IS COMPLETE:** the dashboard flags **open treatments with no next appointment**
("the single most valuable report in the app", BUILD_PLAN §3) via **`GET /treatments/needs-follow-up`**
+ a section at the top of `/`. The clinical loop is closed: record a visit → keep the treatment open
→ if no follow-up is booked, the dashboard says so. Now **eight migrations** (head = `999215bea700`,
unchanged since 4.2) and **eight models**. Two seed scripts: `app.seed` (admin) and
`app.seed_patients` (dev patients). **130 backend tests pass.**

**Step 4.9 is done — PHASE 4 IS FULLY COMPLETE (features + infra).** The Phase-4 wrap added
**clinic settings** (a singleton `clinic_settings` row: hours, slot size, timezone; migration
`1c72084fac9c`, the **ninth**) and **actually applied the clinic timezone**: the appointments
day/range query now bounds "a day" in the **clinic zone** (`clinic_day_bounds`), not UTC, and the
calendar/dashboard render times in the clinic zone. `GET/PATCH /clinic-settings` (admin-write),
`/settings/clinic` screen, `useClinicSettings` hook. **New frontend deps: `date-fns` + `date-fns-tz`**
(backend uses stdlib `zoneinfo`). **The UTC-everywhere caveat carried since 3.3 is retired.** Migration
head = **`1c72084fac9c`**; **nine models**. **143 backend tests pass.** Next is **Phase 5 (billing)**.

**OPEN ITEMS** (deliberately deferred, don't lose these):
| Item | What's owed | Where it bites |
|---|---|---|
| ~~Clinic hours + slot size hardcoded~~ | **DONE in 4.9** — from `clinic_settings` via `useClinicSettings`; `week.ts` constants are now just fallbacks. | — |
| ~~No clinic timezone~~ | **DONE in 4.9** — day bounds are clinic-zone (`clinic_day_bounds`), UI renders in the clinic zone via `date-fns-tz`. | — |
| **No appointment seed script** | Only `app.seed` (admin) + `app.seed_patients` exist. Demo appointments have been created ad hoc. Would help exercise the calendar/dashboard with data. | `backend/app/` |
| **Price snapshot question (→ 5.2)** | `procedure_performed` has **no price column**. 5.2 must decide whether an invoice line snapshots the price at the time of the procedure, so re-reading an old visit doesn't show today's price. Raised in 4.2, answered in Phase 5. | `backend/app/models/procedure_performed.py` |

**Treatment catalogue (4.1):** `treatment_item` = flat `name` (unique) + `default_price` + `active`.
**`GET /treatment-items`** (+ `?include_inactive=`) and `GET /{id}` are **any active staff**;
`POST` / `PATCH` / `{id}/deactivate` / `{id}/activate` are **`require_role("admin")`** — the
project's **first role-split resource**. Duplicate name → **409**. **Deactivate, never delete**, so
historical visits/invoices keep resolving. Admin screen at **`/settings/treatments`** (RoleNav's
admin item now points there); non-admins see a read-only view (and the API rejects them anyway).

**Dashboard (3.6):** `/` **is** the dashboard (was a landing page). Shows an **arrivals summary**
(count tiles: total + one per status, same colours) and **today's schedule** table, both derived
from `GET /appointments?date=<today>` via the existing `useDayAppointments` hook — **no new API**.
Always today (no date nav — the calendar browses other days). **No status controls here** — those
live in the day view so one place owns them. The dev `HealthCard` was kept, moved to the bottom.
RoleNav's "Dashboard" now links to `/`.

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

**Clinical core (4.2):** `treatment` threads visits together — `patient_id` (FK, NOT NULL), `title`,
nullable `tooth_ref`, `status` (`in_progress`/`completed`, default `in_progress`, **no CHECK/enum** —
transitions are API-enforced in 4.5), `started_at`, nullable `closed_at`. **NOT a treatment plan** —
no estimates/quotes/acceptance. `visit` = one sitting; **`treatment_id` is NOT NULL** (every visit
hangs off a treatment — 4.3 auto-creates/auto-closes one for single-visit work so the user never
sees the concept), `patient_id` NOT NULL and deliberately denormalised, `appointment_id` **nullable**
(walk-ins), `dentist_id` nullable. `procedure_performed` = `visit_id` + `treatment_item_id` + nullable
`tooth_ref`, **no price column** (open question for 5.2). No `relationship()` navigations on any of
them yet. No endpoints — that's 4.3.

**Visit recording (4.3):** **`POST /visits` takes EITHER `treatment_id` (continue a thread) OR a
`treatment` stub `{title, tooth_ref}` (start one) — exactly one, else 422.** `treatment_status`
(`in_progress` | `completed`, `Literal` → 422 for anything else) decides whether the treatment is
closed **in the same request**: that's the auto-close half of the rule, and it's what stops a one-off
cleaning lingering on 4.8's open-treatments report. **Writes = `require_role("dentist","admin")`,
reads = any active staff** (BUILD_PLAN §2: clinical recording is the dentist's; the receptionist
still needs history for billing). Endpoints: `POST /visits`, `GET /visits/{id}`,
`GET /visits?patient_id=` **or** `?treatment_id=` (exactly one, else 422), `PATCH /visits/{id}`
(notes/complaint/date only — **cannot re-thread** a visit). One request = one transaction: treatment
+ visit + procedures + audit commit together, and unknown `treatment_item_id`s are rejected **before
anything is written** (404, not a 500 from the FK). `dentist_id` defaults to whoever recorded it.
Auto-created treatments get their own audit row (`details.auto_created_by_visit = true`). The rule
lives in `services/visits.py` (`resolve_treatment`), which raises domain exceptions, not
`HTTPException`, so the router owns status codes and 4.6 can reuse it.

**Visit screen + treatment reads (4.4):** the visit record screen is
**`/patients/{id}/visits/new`** (`app/patients/[id]/visits/new/`), reached from a **Record visit**
button on the patient profile (dentist/admin, hidden for archived patients). The treatment choice is
a **radio group** — the patient's open treatments plus "Start new treatment" — so the API's
exactly-one-of rule is unrepresentable-if-wrong in the UI. It defaults to the single open treatment
when there's exactly one, else to "new". **`GET /treatments?patient_id=&status=`** and
**`GET /treatments/{id}`** were added for it (read-only, any active staff): `patient_id` is
**required**, and results are **open-first, then newest**, because every caller wants actionable
threads on top. **There are still NO treatment write routes** — treatments are created by
`POST /visits`, and close/reopen is **4.5**; `test_no_write_routes` asserts POST/PATCH return 405.
The profile also gained a flat **visit history** (the richer nested Treatments tab is 4.7). The
medical-notes banner was **extracted to `components/medical-notes-banner.tsx`** and is shown on the
visit form too — it matters most while treating.

**Appointment rules to hold onto:** `patient_id` → `patient.id` is a real FK, NOT NULL;
`dentist_id` → `staff_user.id` is a real FK, nullable (unassigned allowed). **`treatment_id` →
`treatment.id` is a real FK as of 4.2**, still nullable (a first booking has no treatment; a
follow-up does). `status` defaults to `booked` (the transition *workflow* is 3.5); `duration_min`
defaults to 30.

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
| **appointment.treatment_id FK — CLOSED in 4.2** | ERD shows `treatment_id FK` | Was a bare nullable UUID from 3.1 (the `treatment` table didn't exist). **4.2 added the real FK** (`appointment_treatment_id_fkey`, migration `999215bea700`); the column stays nullable and has no `ondelete`. The test that asserted the FK's *absence* was **inverted, not deleted** (`test_treatment_id_fk_is_enforced`), so the deferral being paid off stays visible. | `backend/app/models/appointment.py` |
| **`visit.treatment_id` is NOT NULL** | ERD draws a plain FK | Every visit hangs off a treatment, no exceptions — that's what makes the thread real. Single-visit work doesn't escape it: **4.3 auto-creates and auto-closes a treatment** for a one-off cleaning (BUILD_PLAN §3), so the receptionist never sees the word. Allowing NULL would let orphan visits accumulate and silently break the "open treatments with no next appointment" report (4.8), the app's most valuable report. `visit.patient_id` is also NOT NULL and **deliberately denormalised** from the treatment — nearly every clinical read is "this patient's visits". | `backend/app/models/visit.py` |
| **`procedure_performed` has no price column** | — | Strictly the ERD's four columns. Whether a procedure should snapshot the price at the time it was performed (so an old visit doesn't re-read at today's price) is a real question, but it belongs to **5.2** — invoices are the record of what was charged. Deliberately deferred, not overlooked. | `backend/app/models/procedure_performed.py` |
| **Clinic settings = a single-row table (`id = 1` CHECK)** | — | One clinic, so `clinic_settings` is a singleton: `id` pinned to 1 by a CHECK, seeded by the migration, read/written as `db.get(ClinicSettings, 1)`. No create/delete. Plus CHECKs for sane hours (`close > open`) and positive slot. The migration hand-adds the CHECKs + the seed `INSERT` (autogenerate emits neither). | `backend/app/models/clinic_settings.py`, `backend/alembic/versions/1c72084fac9c_*.py` |
| **"A day" is a CLINIC-zone day (`clinic_day_bounds`)** | 3.3 caveat: UTC-everywhere | 4.9 retired the UTC-day caveat. `list_appointments` bounds day/range in the clinic's IANA zone via `services/clinic.clinic_day_bounds` (stdlib `zoneinfo`), so an IST-evening appointment (previous UTC date) lands on the right clinic day. The frontend renders times + resolves "today" in the clinic zone via `date-fns-tz` (`formatInTimeZone`, `toZonedTime`, `fromZonedTime`) instead of browser-local. The overlap constraint/`find_conflicts` are unaffected — they compare instants. | `backend/app/services/clinic.py`, `backend/app/routers/appointments.py`, `frontend/lib/week.ts` |
| **Literal routes before `/{id}` routes** | — | `GET /treatments/needs-follow-up` (4.8) MUST be declared **before** `GET /{treatment_id}`, or FastAPI matches "needs-follow-up" as a `{treatment_id}` UUID path param and 422s. A test (`test_needs_follow_up_not_shadowed_by_id_route`) pins it. Applies to any future literal sub-path on a router that also has a `/{id}` route. | `backend/app/routers/treatments.py` |
| **"No next appointment" = no FUTURE non-cancelled appt, not zero appts** | — | 4.8's report flags an `in_progress` treatment unless it has an appointment (linked by `treatment_id`) that is **upcoming AND not cancelled**. A *past* sitting or a *cancelled* future booking does NOT cover it — those are exactly the walk-out cases. "Future" is measured in **UTC** (`now()`), consistent with the app's UTC-everywhere time (clinic-timezone caveat from 3.3 still applies). | `backend/app/routers/treatments.py` |
| **Inline follow-up = two sequential writes; the visit is the durable one** | — | 4.6 books the follow-up by `POST /visits` **then** `POST /appointments` — NOT one combined endpoint (4.3 deliberately kept booking out of the visit route). If the booking fails (e.g. slot-taken 409) after the visit saved, **the visit is never lost**: the form keeps the created `treatment_id` in state (`savedTreatmentId`) and the next submit only retries the booking. So `recordVisit` now **returns the created visit** (`RecordVisitResult`, not a bare `"ok"`) — a first visit auto-creates its treatment server-side, so the client needs the response to get the id. Any future caller that needs the visit body relies on this. | `frontend/lib/use-visits.ts`, `frontend/app/patients/[id]/visits/new/visit-form.tsx` |
| **First appointment-CREATE from the UI is `lib/use-appointments.ts`** | — | `POST /appointments` has existed since 3.2 but the calendar only ever *reschedules* (PATCH) — bookings were seed-only. 4.6's `bookAppointment` is the first browser booking path; the follow-up's `dentist_id` defaults to the recorder, and the DB's `appointment_no_overlap` 409 is surfaced inline. The standalone New/Edit-appointment screen (BUILD_PLAN §7) is still unbuilt. | `frontend/lib/use-appointments.ts` |
| **UI primitives are Base UI, NOT Radix/shadcn — there is no `asChild`** | shadcn/ui in the tech stack | `components/ui/button.tsx` wraps **`@base-ui/react/button`**. Base UI uses a **`render` prop**, not Radix's `asChild`, so `<Button asChild><Link/></Button>` silently fails to compose. For a link that looks like a button, apply **`buttonVariants()`** to the `Link`'s `className` (used on the profile's "Record visit"). Hit in 4.4. | `frontend/components/ui/button.tsx`, `frontend/app/patients/[id]/patient-profile.tsx` |
| **`/treatments` writes = close/reopen ONLY** | — | The treatments router was read-only in 4.4; **4.5 added its first writes: `POST /{id}/close` + `/reopen`** (the `in_progress ⇄ completed` state machine in `services/treatments.py`, illegal transition → 409, audited). There is **still no create or replace** — treatments are born from `POST /visits`. `test_no_create_or_replace_routes` asserts bare `POST /treatments` + `PATCH /{id}` still 405, so a broad write route can't appear unnoticed. Ordering on the reads stays **open-first, then newest**. | `backend/app/routers/treatments.py`, `backend/app/services/treatments.py` |
| **`POST /visits` auto-create/auto-close contract** | Roadmap says only "auto-creates treatment if new" | The request carries **exactly one** of `treatment_id` / `treatment` stub (else 422), plus `treatment_status`. `completed` sets `status` **and** `closed_at` in the same transaction — so a single-visit cleaning is one call that leaves nothing open (BUILD_PLAN §3). Auto-close is **explicit on the request**, never inferred from which procedures were performed. **4.4 (screen) and 4.6 (inline follow-up) both depend on this exact shape** — don't change it without updating them. | `backend/app/services/visits.py`, `backend/app/routers/visits.py` |
| **Second role-split resource: visits are dentist-write** | Phases 2–3 let any active staff do everything | Visit writes are `require_role("dentist","admin")`; reads stay `get_current_staff`. BUILD_PLAN §2 gives "record visits/treatments" to the Dentist — clinical notes are the dentist's record — while the receptionist still needs visit history for billing (5.2) and follow-ups. A test asserts a receptionist gets **403** on POST/PATCH but **200** on GET. | `backend/app/routers/visits.py` |
| **Services raise domain exceptions, not HTTPException** | — | `services/visits.py` raises `TreatmentNotFound` / `TreatmentPatientMismatch` / `TreatmentAlreadyClosed`; the router maps them to 404/409/409. Keeps the rule unit-testable without HTTP and leaves status codes in one place. Follow this for future service modules. | `backend/app/services/visits.py` |
| **Autogenerated FK constraints need a name by hand** | — | `op.create_foreign_key(None, ...)` upgrades fine (Postgres invents a name) but the paired `op.drop_constraint(None, ...)` **cannot drop an unnamed constraint** — the downgrade fails and the migration is silently irreversible. Hit in `999215bea700`; fixed by naming it `appointment_treatment_id_fkey`. **Always test the downgrade.** | `backend/alembic/versions/999215bea700_*.py` |
| **Money is `Numeric`, NEVER float** | — | `treatment_item.default_price` is `Numeric(10, 2)` in Postgres and `Decimal` in Python/Pydantic — the project's first money column (4.1). Binary floating point can't represent decimal currency exactly, and a rounding error in an invoice is a real bug. **Phase 5's invoice/payment columns must follow the same rule.** Prices cross the wire as strings so the exact decimal survives; the frontend formats with `Intl.NumberFormat` and never does float arithmetic on them. | `backend/app/models/treatment_item.py` |
| **Treatment items deactivate, never delete** | — | No DELETE route: `active` is flipped via `POST /{id}/deactivate` / `/activate`. Retired items vanish from pickers but stay readable so past visits/invoices that reference them still resolve. Same instinct as patient soft-delete. `name` is unique (duplicates would wreck "revenue by procedure" reporting) → duplicate returns **409**. | `backend/app/routers/treatment_items.py` |
| **First role-split resource: `require_role` on the API** | — | Everything before 4.1 guarded every route with `get_current_staff`. The treatment catalogue splits it: **reads = any active staff** (the dentist/receptionist need the list for visits + invoices), **writes = `require_role("admin")`** (BUILD_PLAN §2). The UI hides the controls from non-admins, but that's convenience — the API is the guard, and a test asserts a receptionist gets **403** on every mutation. | `backend/app/routers/treatment_items.py`, `backend/app/auth.py` |
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

## 2026-07-21 — Step 4.9: Phase 4 wrap — clinic settings + clinic timezone

**Status:** complete — a singleton settings table + migration, a role-split settings API, the
timezone day-bounds fix, and the frontend threading, verified (143 backend tests pass; migration
applies + reverses + reseeds; lint + build + Docker images green; settings API and the tz fix proven
live; Caddy guards checked). For commit. **PHASE 4 IS NOW FULLY COMPLETE.**

### Why this step
The two infra caveats carried since Phase 3 — hardcoded clinic hours/slot (`lib/week.ts`) and no
clinic timezone (UTC-everywhere) — needed closing before Phase 5's billing dates make the timezone
load-bearing. The user chose to do both now.

### Scope decisions (confirmed with user)
- **Single-row `clinic_settings` table** (`id = 1` CHECK), seeded by the migration
  (09:00–18:00 / 30-min / `Asia/Kolkata`). `GET` any staff, `PATCH` admin-only, audited.
- **Timezone actually applied** — day bounds computed in the clinic zone; UI renders in it.
- **`useClinicSettings` hook** feeds the calendar grid, the dashboard, and the visit form.
- **New frontend dep `date-fns-tz`** (+ `date-fns` peer), user-approved after I flagged it. Backend
  uses stdlib `zoneinfo` — no backend dep.

### Built — backend
- `app/models/clinic_settings.py` — `ClinicSettings` singleton (`id=1`, hours, `slot_minutes`,
  `timezone`, `updated_at`).
- `alembic/versions/1c72084fac9c_add_clinic_settings.py` — **ninth migration**, `down_revision =
  999215bea700`. Hand-added the three CHECKs (`id=1`, hours `close>open`, `slot>0`) and the seed
  `INSERT` (autogenerate emits neither). Applies, reverses, and **reseeds** on re-upgrade — verified.
- `app/schemas/clinic_settings.py` — Read + Update; `timezone` validated as a real IANA zone
  (constructing `ZoneInfo`) → 422 on a typo.
- `app/routers/clinic_settings.py` — `GET` (`get_current_staff`) + `PATCH` (`require_role("admin")`,
  audited `entity="clinic_settings"`); cross-field `close>open` re-checked on the merged row.
- `app/services/clinic.py` — **fifth `services/` module.** `clinic_day_bounds(day, tz)` → the UTC
  window of a clinic-local calendar day. `list_appointments` now uses it instead of
  `datetime.combine(..., tzinfo=utc)`.
- Tests: `test_clinic_settings.py` (GET defaults, admin PATCH, **receptionist 403**, invalid tz 422,
  `close<=open` 422, out-of-range 422, audit), `test_clinic.py` (`clinic_day_bounds` IST/UTC offset
  math, pure-logic), and `test_appointments.py::test_day_bounds_use_clinic_timezone` (**the bug**: an
  appt at `1 Aug 19:30 UTC` = `2 Aug 01:00 IST` shows on the 2 Aug clinic day, not 1 Aug). The
  appointments fixture now pins the clinic tz to UTC so the existing UTC-based day/range tests stay
  valid, restoring it after. 130 → **143**.

### Built — frontend
- `package.json` — `date-fns` + `date-fns-tz` added.
- `lib/use-clinic-settings.ts` — `useClinicSettings()` (returns the settings with the old hardcoded
  values as the **loading fallback**, so no grid renders empty) + `updateClinicSettings`.
- `lib/week.ts` — the constants became defaults; `daySlots`/`slotForStart`/`todayIso` take
  settings/tz params; **new** `clinicDay`, `slotInstant`, `fmtTimeInZone` do day/slot/time math in the
  clinic zone via `date-fns-tz` (was browser-local `getHours()`/`new Date(y,m,d)`).
- `app/calendar/{week,day}-view.tsx`, `app/today-dashboard.tsx` — read the hook; grid rows from
  configured hours/slot; times/"today" in the clinic zone.
- `app/patients/[id]/visits/new/visit-form.tsx` — follow-up duration defaults to `slot_minutes`
  (placeholder-driven; blank = configured slot).
- `app/settings/clinic/` (page + `clinic-settings-form.tsx`) — admin edits hours/slot/tz; non-admins
  read-only. `app/role-nav.tsx` — new admin **Clinic settings** link.

### Bug hit + fixed during build (worth remembering)
1. **Seeded row got permanently drifted** by an early failed test run whose snapshot-based restore
   captured an already-mutated value. Fixed by making the settings fixture restore to **fixed seed
   defaults** (not a snapshot), so a mid-test failure is self-healing; reset the DB row by hand once.
2. **`react-hooks/set-state-in-effect`** on the settings form (seeding the edit draft from the loaded
   settings in a `useEffect`). Fixed with the **"adjust state during render"** idiom (a key compare,
   no effect) — the same rule that bit 0.3/2.3/2.4.

### No new backend dep / migration is the only schema change
`zoneinfo` is stdlib on 3.12. One migration (the ninth).

### Verified
- Migration: `\d clinic_settings` shows the 3 CHECKs + the seeded row; **reversible + reseeds**.
- **143 backend tests pass** in-container.
- Frontend `lint` + `build` green; `/settings/clinic` registered; **Docker frontend image rebuilds
  with the new deps** (`npm ci`).
- **Live:** GET defaults; admin PATCH sticks; **receptionist PATCH 403**; invalid tz/hours 422; and
  the headline — **the same appointment instant falls on 2 Aug under an IST clinic and 1 Aug under a
  UTC clinic** (the zone drives the day). Audit rows written. Settings restored after.
- **Through Caddy:** `/api/clinic-settings` no token → 401; `/settings/clinic` signed-out → 307 →
  /login.

### What was NOT browser-clicked (honest note)
The tz day-bounds math and the settings API are proven live. The **calendar/dashboard rendering in
the clinic zone and the settings form** are wired + type-checked (build passes) but not clicked in a
browser; auth was faked for the live run. **Handed to the user for the visual click-through** —
especially: change the timezone in `/settings/clinic` and confirm the calendar times shift, and edit
the hours and confirm the week grid's rows change.

### PHASE 4 COMPLETE
The clinical core end to end: treatment catalogue, the treatment/visit/procedure models, visit
recording with auto-created treatments, the visit screen, treatment lifecycle, inline follow-ups, the
nested treatment history, the open-treatments dashboard, and now configurable clinic settings + a
real timezone. Next: **Phase 5 — billing** (invoices per visit, payments, today's collections).

### Suggested commit
`feat: add clinic settings and timezone`

---

## 2026-07-20 — Step 4.8: dashboard — open treatments with no next appointment

**Status:** complete — a clinic-wide read query + a dashboard section, verified (130 backend tests
pass; lint + build + Docker image green; every discriminating state transition proven live). For
commit. **No migration** — every column and FK already existed. **This finishes Phase 4's feature
work**, and it's the report BUILD_PLAN §3 calls "the single most valuable in the app."

### Why this matters
An `in_progress` treatment with no upcoming appointment is a patient mid-course whom nobody booked
back in — revenue walking out the door. The pieces were all in place: treatments carry a status
(4.2/4.5) and 4.6's inline follow-up links appointments to treatments via `appointment.treatment_id`.

### Scope decisions (confirmed with user)
- **Flag = `in_progress` AND no future non-cancelled appointment** on the treatment. A *past* sitting
  or a *cancelled* future booking does NOT cover it — the "zero appointments" shortcut would wrongly
  clear those. Cancelled excluded like the booking rules (`status != 'cancelled'`).
- **New read `GET /treatments/needs-follow-up`** (any active staff, clinic-wide, no `patient_id`),
  returning each row's `patient_name` (joined) + `last_visit_date` (max visit).
- **On the dashboard (`/`), above today's schedule** — highest-value first. Not a `/reports` page
  (Phase 6).
- **Any dentist's future appointment counts** (single-dentist clinic).

### Built — backend (no migration)
- `app/schemas/treatment.py` — `TreatmentNeedsFollowUp` (+ `patient_name`, nullable `last_visit_date`)
  and `NeedsFollowUpResponse`.
- `app/routers/treatments.py` — `GET /treatments/needs-follow-up`, declared **before**
  `GET /{treatment_id}` (else "needs-follow-up" parses as a UUID → 422). Query: `in_progress`,
  `~exists()` correlated subquery for a future non-cancelled appointment, join `Patient` for the
  name, `func.max(Visit.visit_date)` scalar subquery for last-seen, ordered longest-unseen-first
  (NULLs top). "Now" = `datetime.now(timezone.utc)`.
- `tests/test_treatments.py` — +9: no-appt→flagged, future-appt→cleared, **past-only→still flagged**,
  **cancelled-future→still flagged**, completed→never flagged, `patient_name` + latest
  `last_visit_date`, null last-visit, auth required, and **route-not-shadowed-by-`/{id}`**. Fixture
  now cleans visits + appointments (FK order). 121 → **130**.

### Built — frontend
- `lib/use-treatments.ts` — `useNeedsFollowUp()` (clinic-wide, `refetch`) + `TreatmentNeedsFollowUp`
  type.
- `app/needs-follow-up.tsx` (**new**) — an amber-bordered table (patient → profile link, treatment +
  tooth, "last seen" via `formatVisitDate` or "no visits yet"). Empty state phrased as reassurance:
  "All open treatments have a follow-up booked."
- `app/page.tsx` — renders `<NeedsFollowUp/>` **above** `<TodayDashboard/>`. `today-dashboard.tsx`
  untouched (the two sections are independent).

### No new deps / backend model / migration / env / CI

### Verified
- **130 backend tests pass** in-container against real Postgres.
- Frontend **`lint` + `build` green**; `/` still dynamic; Docker frontend image rebuilds.
- **Live against the compose Postgres** — every state transition of the report: open+unbooked →
  **flagged** (with patient name + last-seen) → book a **future** follow-up → **drops off** → **cancel
  it → reappears** (the case that proves "zero appointments" would be wrong) → only a **past**
  appointment → **still flagged** → **complete** the treatment → **drops off**; a treatment with no
  visits reports `last_visit_date: null`. Cleaned up.
- **Through Caddy:** `/api/treatments/needs-follow-up` no token → **401**; `/` signed-out → **307 →
  /login**.

### What was NOT browser-clicked (honest note)
Same caveat as 4.4–4.7: the query is proven live end to end and the section is wired + type-checked,
but the dashboard **wasn't clicked in a browser** (auth faked). **Handed to the user for the visual
click-through** — the amber section at the top of `/`, and confirming a treatment drops off it after
booking a follow-up from the visit screen (the 4.6 → 4.8 loop).

### Carried forward (Phase 4 infra, not features)
- **Clinic settings** — hours + slot size, hardcoded in `lib/week.ts` (`DAY_START_HOUR`,
  `DAY_END_HOUR`, `SLOT_MIN`); the follow-up duration default and the week grid both use them.
- **Clinic timezone** — the UTC-everywhere caveat (3.3). "Future" in this report, `visit_date`, and
  the calendar day bounds are all UTC; the clinic is IST. Needs a clinic-timezone setting.
- **Decide with the user:** close these two out (a short "Phase 4 wrap") before **Phase 5 (billing)**,
  or carry them forward. They are the only Phase 4 items left.

### Suggested commit
`feat: flag treatments missing follow-ups`

---

## 2026-07-20 — Step 4.7: patient profile — treatments with visits nested

**Status:** complete — pure frontend, one file, verified (121 backend tests still pass; lint + build
+ Docker image green; the grouping data path proven live). For commit. **No backend, no endpoint, no
migration.** This makes the profile show the clinical model the way it actually is — a treatment and
its sittings together (BUILD_PLAN §3, §7).

### Scope decisions (confirmed with user)
- **Group client-side.** `usePatientVisits` already returns every visit carrying `treatment_id` plus
  its treatment summary + procedures; `usePatientTreatments` gives the treatments (open-first). Bucket
  visits under their treatment in the browser — no nested endpoint, which would just duplicate
  `GET /visits?treatment_id=`.
- **One merged Treatments section**, each treatment expandable. Replaces the old flat Treatments list
  (4.5) **and** the separate Visit history card (4.4) — so a visit shows **once**, under its thread.
  Open treatments expanded by default; completed ones collapsed.
- **Show every visit, even bare ones** — a visit with no notes/procedures still renders its date +
  "No notes recorded"; a sitting that happened must not vanish.

### Built (all in `app/patients/[id]/patient-profile.tsx`)
- `TreatmentsSection` — builds a `Map<treatment_id, Visit[]>` from the visits list (preserving the
  hook's newest-first order per treatment), merges the loading/error state of **both** hooks, and
  renders one card per treatment. A **dev-only** `console.warn` flags a visit whose treatment isn't
  in the list (can't happen; keeps it debuggable) rather than dropping it.
- `TreatmentCard` — title, tooth, `TreatmentStatus`, visit count, the 4.5 Close/Reopen button
  (unchanged logic), and a native `▸/▾` expand toggle (`aria-expanded`, seeded open for
  `in_progress`). Expanded → the treatment's visits, or "No visits recorded yet."
- `VisitRow` — slimmed: the treatment title/status moved to the parent card, so a row is now just
  date + complaint + notes + procedures, with a "No notes recorded." fallback.
- **Removed:** the standalone `VisitHistory` card. Its data now lives under each treatment.

### Reused (no new hooks/endpoint)
`usePatientTreatments`, `usePatientVisits`, `closeTreatment`/`reopenTreatment`, `TreatmentStatus`,
`formatVisitDate`, the `MutationResult` handling, `Card`/`Button`.

### No new deps / backend / migration / env / CI
Native `<button>` toggle + client-side grouping. Pure frontend, like 4.6.

### Verified
- **121 backend tests still pass** (regression check — no backend change).
- Frontend **`lint` + `build` green**; `/patients/[id]` still dynamic; Docker frontend image rebuilds.
- **Live against the compose Postgres** (built the render shapes, checked the grouping the client
  does): a **3-sitting open RCT** buckets all three visits **newest-first**; a **completed
  single-visit cleaning** groups its one visit; a **bare visit** (no notes/procedures) is present and
  will show "No notes recorded"; treatments come back **open-first**; **every visit carries a
  treatment_id** and there are **no orphans**. Cleaned up.

### What was NOT browser-clicked (honest note)
Same caveat as 4.4–4.6: the grouping/expand is wired + type-checked and the data paths are proven
live, but the **expand/collapse interaction wasn't clicked in a browser** (auth faked). **Handed to
the user for the visual click-through** — worth watching: an open RCT expanded by default showing its
sittings, a completed treatment collapsed, and Close flipping a card + refetching.

### Carried forward → 4.8
- **Dashboard: open treatments with no next appointment** — "the single most valuable report in the
  app" (BUILD_PLAN §3). The pieces are in place: treatments have a status, and 4.6's follow-ups link
  appointments to treatments via `appointment.treatment_id`, so the query is "in_progress treatments
  with no future appointment on that treatment_id". Likely the first *new read endpoint* since 4.4.
- Still open in Phase 4: **clinic settings** (hours + slot size) and the **clinic timezone**.

### Suggested commit
`feat: show treatment history`

---

## 2026-07-20 — Step 4.6: inline follow-up scheduler from the visit screen

**Status:** complete — pure frontend on top of existing APIs, verified (121 backend tests still pass;
lint + build + Docker image green; the two-write flow incl. partial failure proven live). For commit.
**No backend change, no migration.** **The first booking-from-UI path**, and the first use of
`appointment.treatment_id` (the FK added in 4.2) from the browser.

### Why this matters (BUILD_PLAN §3)
The follow-up must be bookable **from inside the visit screen, in the same flow** — "not a separate
'now go to the calendar' trip. That's the difference between it getting used and not." A forgotten
follow-up is revenue walking out the door, which 4.8's dashboard exists to catch.

### Scope decisions (confirmed with user)
- **Record visit first, then book the follow-up** with the returned `treatment_id` — two sequential
  writes, not one combined endpoint (4.3 kept booking out of `POST /visits`). If the booking fails,
  **the visit stays saved** and only the booking is retried.
- **Native date + time + duration inputs** (consistent with the calendar's native date input).
- **Default `dentist_id` = the recorder**; the existing double-booking 409 is surfaced inline.
- **Optional, off by default**, and **hidden when "treatment complete" is ticked** (a finished
  treatment needs no next sitting). Skipping = the 4.8 "open, unbooked" state.

### Built (all frontend)
- `lib/use-visits.ts` — `recordVisit` now returns **`RecordVisitResult`** (`{status:"ok",visit}` |
  forbidden | conflict | error) instead of a bare `MutationResult`. The follow-up needs the created
  visit's `treatment_id`, which for a first visit is server-assigned.
- `lib/use-appointments.ts` (**new**) — `bookAppointment(body)` → `POST /appointments`, mapping 409
  (slot taken) / 404 (patient) distinctly. **First appointment-create path from the UI** (the
  calendar only reschedules). Types the `AppointmentCreate` body.
- `app/patients/[id]/visits/new/visit-form.tsx` — a **Follow-up** card (only when not "complete"):
  a "Book a follow-up" checkbox + date/time/duration/reason. `submit` now:
  1. records the visit (durable write);
  2. if requested, builds an ISO `start_time` (browser-local, timezone caveat) and books the
     appointment linked to the treatment, dentist = recorder;
  3. on a booking failure, keeps `savedTreatmentId` and shows an amber notice — the next submit only
     **retries the booking**, never re-records the visit. Ticking "complete" clears the follow-up.

### No new deps / backend / migration / env / CI
Native date/time inputs; existing `POST /appointments`. First pure-frontend step since 3.6.

### Verified
- **121 backend tests still pass** (regression check — no backend change).
- Frontend **`lint` + `build` green**; Docker frontend image rebuilds.
- **Live against the compose Postgres** (the form's two-write flow, reproduced over HTTP):
  visit + follow-up → appointment created **linked to the treatment**, dentist = recorder, correct
  start_time → **partial failure**: booking onto a taken slot returns **409 while the visit count
  still goes 1→2** (the visit is durable) → **retry onto a free slot succeeds without re-recording**
  → record without a follow-up leaves an open treatment with **0 linked appointments** (the 4.8
  state) → a "complete" visit books nothing → the follow-ups appear in `GET /appointments?date=`
  carrying their `treatment_id`. Cleaned up.

### What was NOT browser-clicked (honest note)
Same caveat as 4.4/4.5: the live run reproduced the form's two writes over real HTTP against the real
DB, but the **date/time controls, the "book follow-up" toggle, and the partial-failure retry UI were
not clicked in a browser**, and auth was faked. The build type-checks the wiring. **Handed to the
user for the visual click-through** — the partial-failure retry (record a visit, aim the follow-up at
a taken slot, confirm the visit persisted and the booking can be retried) is the bit worth watching.

### Carried forward → 4.7
- **Patient profile → Treatments tab, visits nested** — expand 4.5's compact treatments list into
  treatments each expandable to their sittings. The booked follow-ups will show on the calendar and,
  in **4.8**, drive the "open treatments with no next appointment" dashboard (this step's
  treatment-linked appointments are exactly what that query keys on).
- Still open in Phase 4: **clinic settings** (hours + slot size — the follow-up duration defaults to
  the hardcoded `SLOT_MIN`) and the **clinic timezone** (`start_time` is built browser-local).

### Suggested commit
`feat: schedule follow-ups from visit record`

---

## 2026-07-20 — Step 4.5: treatment lifecycle (close / reopen)

**Status:** complete — a fourth service + two write routes + a compact profile UI, verified (121
backend tests pass; lint + build + Docker image green; the lifecycle proven live end to end incl.
closing the 4.4 gap; guards checked through Caddy). For commit. **No migration.** **The treatments
router's first write routes.**

### Scope decisions (confirmed with user)
- **Two dedicated endpoints** — `POST /treatments/{id}/close` and `/reopen`, mirroring patient
  archive/unarchive and appointment status (3.5). Not a `PATCH {status}`.
- **`require_role("dentist", "admin")`** — closing a course of treatment is a clinical judgement,
  same reasoning as visit-write (BUILD_PLAN §2). Reads stay any-active-staff.
- **UI: a compact Treatments section on the profile** (status + Close/Reopen). 4.7 expands it into
  the nested tab.
- **Reopen always allowed from `completed`** — no "newer treatment exists" guard.

### Built — backend (no migration)
- `app/services/treatments.py` — **fourth `services/` module.** `close_treatment` /
  `reopen_treatment` enforce `in_progress ⇄ completed` and keep `status`/`closed_at` consistent as a
  pair (mirroring `visits._apply_status`). Raise **`IllegalTreatmentTransition`** (a domain
  exception, not `HTTPException`) — the router owns status codes, per the 4.3 standing decision.
- `app/routers/treatments.py` — added `POST /{id}/close` + `/reopen` (both
  `require_role("dentist","admin")`) via a shared `_transition` helper: load-or-404, apply, map the
  domain exception → 409, audit (`action="close"|"reopen"`, `details={from,to}`), single commit. The
  reads are unchanged. Refactored the inline get-404 into a shared `_get_or_404`.
- `tests/test_treatments.py` — +7: close→completed+`closed_at`+audit; reopen→in_progress+cleared;
  **double-close 409**, **reopen-open 409**; 404s; audit `{from,to}`; and the **role split**
  (receptionist 403 on both writes, 200 on reads). Renamed `test_no_write_routes` →
  `test_no_create_or_replace_routes` (the /close,/reopen sub-paths ARE writes now; it still asserts
  bare POST/PATCH 405). Fixture now also cleans lifecycle audit rows. 114 → **121**.

### Built — frontend
- `lib/use-treatments.ts` — `closeTreatment(id)` / `reopenTreatment(id)` posting to the endpoints,
  returning the shared `MutationResult` (403 → "forbidden", 409 → "conflict" for a stale button).
- `app/patients/[id]/patient-profile.tsx` — a compact **Treatments** section (via
  `usePatientTreatments`, all statuses, open-first) above the visit history. Each row: title, tooth,
  status pill (reused `TreatmentStatus`), and a **Close/Reopen** button for dentists/admins. Both the
  treatments and visits hooks were **lifted into the parent** so a lifecycle change refetches *both*
  (closing a treatment changes the status shown against its visits). A 409 shows a note and refetches.

### Reused (no new versions)
`visits._apply_status` discipline, the appointment `set_status` audited-transition shape,
`require_role` + `record_audit`, `usePatientTreatments` + the `MutationResult` union +
`TreatmentStatus`.

### No new deps / migration / env / CI
`status` + `closed_at` already exist (4.2) — behaviour on existing columns, like the 3.5 appointment
status workflow needed no migration.

### Verified
- **121 backend tests pass** in-container against real Postgres.
- Frontend **`lint` + `build` green**; Docker frontend image rebuilds.
- **Live against the compose Postgres:** open a treatment → **close without a visit** (completed +
  `closed_at`) → **close again 409** → **a visit against the closed treatment 409 (the 4.4 gap)** →
  **reopen** (in_progress, `closed_at` cleared) → **reopen again 409** → **a visit against the
  reopened treatment now succeeds** (gap closed end to end) → **receptionist 403 on close/reopen, 200
  on reads** → audit shows `close`/`reopen` with `{from,to}`. Cleaned up.
- **Through Caddy:** `POST /api/treatments/{id}/close` and `/reopen` no token → **401**.

### What was NOT browser-clicked (honest note)
Same caveat as 4.4: the live run drove the **real API over HTTP against the real database** and the
guards were checked through Caddy, but the **profile's Close/Reopen buttons were not clicked in a
browser** and auth was faked (the role split was still exercised via `require_role`). The build
type-checks the wiring. **Handed to the user for a visual click-through.**

### Carried forward → 4.6
- **Inline follow-up scheduler from the visit screen** — book the next sitting from inside the visit
  form (BUILD_PLAN §3: "in the same flow, not a separate trip to the calendar"), linking the new
  appointment to the treatment via `appointment.treatment_id` (the FK added in 4.2).
- Still open in Phase 4: **clinic settings** (hours + slot size) and the **clinic timezone**. Then
  4.7 the nested Treatments tab (this step's compact list is its seed), 4.8 the open-treatments
  dashboard.

### Suggested commit
`feat: add treatment lifecycle`

---

## 2026-07-20 — Step 4.4: visit record screen

**Status:** complete — a small read-only backend addition + the visit form + profile history,
verified (114 backend tests pass; lint + build + Docker image green; the form's whole data path
proven live; guards checked through Caddy). For commit. **No migration.** **This is the screen Phase
4 exists for** — the first UI that writes clinical data.

### Scope decisions (confirmed with user)
- **Route `/patients/{id}/visits/new`**, reached from a **Record visit** button on the profile. The
  patient is known first, and keeping patient context means the **medical-notes banner stays on
  screen while recording** — exactly when "diabetic, on blood thinners" matters.
- **Treatment choice is a radio group** (open treatments + "Start new treatment"), mirroring the
  API's exactly-one-of rule so an invalid request can't be built in the UI.
- **Added `GET /treatments?patient_id=`** — the picker needed it and no such endpoint existed.
  Read-only; treatment writes stay absent until 4.5.
- **Full form** — complaint, notes, catalogue procedures with tooth refs, and the finished toggle.
  Anything less can't record a real visit or be invoiced in Phase 5.
- **No inline follow-up** (4.6), **no lifecycle controls** (4.5), **no nested Treatments tab** (4.7).

### Built — backend (read-only, no migration)
- `app/schemas/treatment.py` — `TreatmentRead` + `TreatmentListResponse`. (`TreatmentSummary` in
  `schemas/visit.py` stays as the trimmed shape nested inside a visit.)
- `app/routers/treatments.py` — `GET /treatments?patient_id=&status=` (patient_id **required**;
  `status` is a `Literal` → 422; **open-first then newest** via a `case()` sort key) and
  `GET /treatments/{id}` (404). Both `get_current_staff`, unaudited. Registered in `main.py`.
- `tests/test_treatments.py` — 10 tests: patient scoping, status filter, **open-first ordering
  asserted specifically** (the closed one is deliberately the newest, so a plain date sort would
  fail it), newest-within-group, required `patient_id` → 422, unknown status → 422, get/404, empty
  list, and **`test_no_write_routes`** (POST/PATCH → 405). 104 → **114**.

### Built — frontend
- `lib/use-treatments.ts` — `usePatientTreatments(patientId, {openOnly})`, cloning the existing hook
  pattern (module `apiUrl`, auth headers, refetch nonce).
- `lib/use-visits.ts` — `usePatientVisits`, `recordVisit(body)`, `formatVisitDate`. **`VisitCreateBody`
  is a discriminated union** (`{treatment_id}` xor `{treatment}`) so the invalid body is a *type*
  error, not just a runtime 422. Maps 403 → "forbidden" (not a dentist) and 409 → "conflict"
  (treatment already completed), and surfaces the API's `detail` for 404/422.
- `components/medical-notes-banner.tsx` — **extracted** from `patient-profile.tsx` so the profile and
  the visit form render the identical banner (a safety warning is the last thing to let drift).
- `app/patients/[id]/visits/new/page.tsx` + `visit-form.tsx` — the form: treatment radio group
  (+ title/tooth fields when new), complaint + clinical notes (native `<textarea>` styled to match
  `Input`), a procedure row builder (`<select>` of active catalogue items + optional tooth + price
  for context via `formatPrice`), and the **"This treatment is now complete"** checkbox driving
  `treatment_status`. Submit is disabled while in flight (a double-submit would record two visits);
  on success it routes back to the profile. Dentist gate via `useCurrentStaff()`.
- `app/patients/[id]/patient-profile.tsx` — **Record visit** button (dentist/admin, hidden when
  archived) + a flat **visit history** (date, treatment title, status, notes, procedure names).

### Reused (wrote no new versions)
`useTreatmentItems` + `formatPrice` + the `MutationResult` union (4.1), `usePatient` (2.4),
`useCurrentStaff` (1.4), `components/ui/{button,card,input}`.

### Bug hit + fixed during build (worth remembering)
**`<Button asChild>` doesn't exist in this project.** `components/ui/button.tsx` wraps
**`@base-ui/react/button`**, not Radix — Base UI composes via a `render` prop, so `asChild` is
silently ignored. Fixed by applying **`buttonVariants()`** to the `Link`'s `className`, which also
avoids nesting a button inside a link. Recorded as a standing decision; it will recur whenever a
link needs to look like a button.

### No new deps / migration / env / CI
Native `<select>`, `<textarea>`, `<input type="checkbox">` — consistent with the native date input
from 3.3. Nothing added to `package.json`.

### Verified
- **114 backend tests pass** in-container against real Postgres.
- Frontend **`lint` + `build` green**; `/patients/[id]/visits/new` registered as a **dynamic route
  (`ƒ`)**; Docker frontend image rebuilds clean.
- **Live against the compose Postgres** — the form's exact data path, end to end: picker empty for a
  new patient → **cleaning recorded with "complete" ticked → treatment auto-created AND closed**, and
  **still zero open treatments** afterwards → **RCT sitting 1** left open → picker now offers it →
  **ordering puts the open RCT above the newer completed cleaning** → **sitting 2 continues the same
  treatment** (2 visits, 1 treatment) → history reads back with procedure names and tooth refs →
  both/neither treatment forms **422** → **receptionist: GET 200 on visits and treatments, POST 403**.
  Cleaned up.
- **Through Caddy:** `/patients/{id}/visits/new` signed-out → **307 → /login**; `/api/treatments`
  with no token → **401**; `/api/health` → 200.

### What was NOT browser-clicked (honest note)
The live run drove the **real API over HTTP against the real database** with the exact bodies the
form builds, and the route guard was checked through Caddy — but the **form itself was not clicked
in a browser**, and auth was faked rather than using a real Supabase token (same caveat as 4.3;
the role split was still exercised through `require_role`). The build type-checks the wiring.
**Handed to the user for a visual click-through**, as with 3.4's drag gesture.

### Carried forward → 4.5
- **Treatment lifecycle**: close a treatment without recording a visit, and **reopen a completed
  one**. The 409 on "that treatment is already completed" currently has no in-app remedy — 4.5 is
  where it gets one, and where `GET /treatments` likely gains its first write route.
- Still open in Phase 4: **clinic settings** (hours + slot size) and the **clinic timezone**
  (`visit_date` renders in the browser's zone, same caveat as 3.3). Then 4.6 inline follow-ups,
  4.7 the nested Treatments tab, 4.8 the open-treatments dashboard.

### Suggested commit
`feat: add visit record screen`

---

## 2026-07-20 — Step 4.3: visit recording API

**Status:** complete — schemas + service + router + tests, verified against the real Docker Postgres
(104 tests pass; the full RCT thread, the auto-close case, the role split and the transactional
guarantee all proven live). For commit. **No migration** — 4.2 created every table this writes to.
**The app now holds real clinical content**, and this is the **second role-split resource**.

### Scope decisions (confirmed with user)
- **One endpoint, `treatment_id` optional.** `POST /visits` takes **either** `treatment_id`
  (continue a thread) **or** a `treatment` stub (start one) — exactly one, else 422. One sitting =
  one request = one transaction. The alternative (create the treatment first, then the visit) was
  rejected: two round-trips that can half-fail produce exactly the orphan treatment 4.8 flags.
- **`treatment_status` is explicit on the request**, not inferred from the procedures performed.
  The dentist answers "is this finished?" once; the server sets `status` + `closed_at`.
- **Writes = dentist/admin, reads = any staff** (BUILD_PLAN §2).
- **No follow-up scheduling** — that's 4.6.

### Built — backend (no migration)
- `app/schemas/visit.py` — `TreatmentStub`, `ProcedureIn`, `VisitCreate` (with a
  **`@model_validator`** enforcing exactly-one-of `treatment_id`/`treatment`), `VisitUpdate`
  (notes/complaint/date only — **deliberately cannot re-thread** a visit onto another treatment or
  patient), `ProcedureRead` (catalogue name resolved), `TreatmentSummary`, `VisitRead` (visit +
  thread + procedures in one response), `VisitListResponse`. `treatment_status` is a `Literal`, so
  an unknown value is a schema 422 — same choice as `AppointmentStatusUpdate` (3.5).
- `app/services/visits.py` — **third `services/` module.** `resolve_treatment()` holds the whole
  auto-create/auto-close rule and returns `(treatment, created)` so the router can audit an
  auto-creation. Raises **domain exceptions** (`TreatmentNotFound`, `TreatmentPatientMismatch`,
  `TreatmentAlreadyClosed`), never `HTTPException` — unit-testable without HTTP, and 4.6 reuses it.
  `flush()`, never `commit()`: the caller owns the transaction. `_apply_status` keeps `status` and
  `closed_at` consistent as a pair.
- `app/routers/visits.py` — `POST` (201), `GET /{id}`, `GET ?patient_id=|?treatment_id=` (exactly
  one, else 422; newest first), `PATCH /{id}`. `_validate_items` checks every `treatment_item_id`
  **up front** so a bad id is a clean 404 with nothing written, rather than a half-built visit and a
  500 from the FK. **Retired (inactive) items are still accepted** — a procedure genuinely performed
  with a since-retired item must stay recordable. `dentist_id` defaults to the recording staff member.
  Registered in `main.py`.
- `tests/test_visits.py` — 19 tests. Headliners: **auto-create**, **auto-create+auto-close** (the
  "cleaning — done" case), **second sitting continues the thread**, **closing on the final sitting**,
  **unknown item writes nothing** (transactional guarantee, asserts no orphan visit *or* treatment),
  **receptionist 403 on write / 200 on read**. Plus the 422 guards (neither/both treatment forms,
  bad status, no/both list filters), 404s, cross-patient 409, closed-treatment 409, procedure
  name round-trip, dentist defaulting, explicit `visit_date`, and both audit rows. 85 → **104**.

### No new deps / migration / env / CI

### Verified
- **104 tests pass** in-container against real Postgres, first run.
- **Live against the compose Postgres** (real HTTP through the app, real DB):
  - **Single-visit cleaning** → treatment created **and** `closed_at` set in one call.
  - **RCT**: sitting 1 opened the thread, sitting 2 continued it (2 visits, one treatment, still
    open), sitting 3 closed it; a 4th sitting → **409**.
  - Patient history read back the way 4.7 will render it.
  - **Unknown item → 404 with visit count unchanged and no orphan treatment.**
  - **Receptionist: GET 200, POST 403, PATCH 403.**
  - Audit: 4 `visit` rows + 2 `treatment` rows, both auto-created ones carrying
    `auto_created_by_visit: true`. Cleaned up fully.

### Note on the live check
The live run drove the real app over HTTP against the real database, but **faked the auth
dependency** rather than minting a Supabase token (that needs credentials from the gitignored
`.env`). The role split was still exercised through `require_role` by swapping the acting staff
member. Earlier steps used a real ES256 token through Caddy; worth doing that again at the 4.4
checkpoint when there's a UI to click through.

### Carried forward → 4.4
- **The visit record screen**, which submits exactly the `POST /visits` shape above: a patient, a
  treatment picker (existing open threads) *or* a new-treatment title, procedures from the
  catalogue, notes, and the "is this finished?" toggle that sets `treatment_status`.
- Still open in Phase 4: **clinic settings** (hours + slot size) and the **clinic timezone**. Visit
  timestamps are UTC like everything else, so the 3.3 caveat applies to `visit_date` too.
- Lifecycle endpoints (reopen a completed treatment, close one without recording a visit) are
  **4.5** — the 409 on a closed treatment currently has no in-app remedy, which is expected.

### Suggested commit
`feat: add visit recording endpoints`

---

## 2026-07-20 — Step 4.2: treatment + visit + procedure_performed models

**Status:** complete — three models + one migration + tests, verified against the real Docker
Postgres (schema inspected, migration reversible, 85 tests pass, the RCT thread built and read back
live). For commit. **The domain rule that justifies this whole project is now schema**, and the
oldest deferral in the codebase is paid off.

### Scope decisions (confirmed with user)
- **Models + migration + model tests only.** No schemas, no routers, no UI — the visit recording API
  is 4.3, the screen is 4.4, lifecycle transitions are 4.5. Matches the roadmap line exactly.
- **`appointment.treatment_id` gets its real FK here** — deferred since 3.1 because `treatment`
  didn't exist. Stays nullable; **no `ondelete`** (consistent with 3.1: nothing is ever hard-deleted,
  so cascades would never fire, and restrict-by-default is the right medico-legal answer).
- **The deferral test is inverted, not deleted** — `test_treatment_id_has_no_fk_yet` became
  `test_treatment_id_fk_is_enforced`, so the change stays visible and deliberate in the diff.

### Built
- `app/models/treatment.py` — `Treatment`: the **thread**. `patient_id` (FK, NOT NULL, indexed),
  `title`, nullable `tooth_ref`, `status` (default `in_progress`, plain Text — **no CHECK/enum**,
  same call as `appointment.status`; transitions land in 4.5), `started_at`, nullable `closed_at`,
  timestamps. **No cost/estimate/acceptance columns** — the guard-rail against treatment-plan creep.
- `app/models/visit.py` — `Visit`: one sitting. **`treatment_id` NOT NULL** (the load-bearing
  decision — see the standing-decisions row), `patient_id` NOT NULL + denormalised, `appointment_id`
  **nullable** (walk-ins), `dentist_id` nullable, `visit_date`, `complaint`, `clinical_notes`.
- `app/models/procedure_performed.py` — `ProcedurePerformed`: `visit_id` + `treatment_item_id`
  (the 4.1 catalogue link) + nullable per-procedure `tooth_ref`. **No price column** — open for 5.2.
- `app/models/appointment.py` — `treatment_id` gains `ForeignKey("treatment.id")`; docstring updated.
- `app/models/__init__.py` — the three new models registered.
- `alembic/versions/999215bea700_add_treatment_visit_procedure_performed.py` — autogenerated,
  `down_revision = 73aeddd50693`. Three `create_table`s + the appointment FK. Indexes on
  `treatment.patient_id`, `visit.patient_id`, `visit.treatment_id`, `procedure_performed.visit_id`.
- `tests/test_treatment_models.py` — 10 tests: shape, full FK introspection, nullability
  (`treatment_id` required / `appointment_id` not), defaults, **one treatment threading three
  visits** (the RCT case), orphan + bogus-treatment rejection, walk-in visit, procedures linking to
  the catalogue, catalogue FK enforced, appointment↔visit link.
- `tests/test_appointment.py` — the two deferral assertions inverted; cleanup fixture reordered for
  the new FK. 73 → **85 tests**.

### Bug hit + fixed during build (worth remembering)
1. **Autogenerate emitted `op.create_foreign_key(None, ...)`** for the appointment FK. Upgrades fine
   (Postgres invents a name) but `op.drop_constraint(None, ...)` can't drop an unnamed constraint —
   the migration would have been **silently irreversible**. Caught by actually running the
   downgrade. Named it `appointment_treatment_id_fkey`. Recorded as a standing decision.
2. **Test teardown hit `ForeignKeyViolation`s** even though the cleanup list was correctly ordered:
   `db.delete()` only *stages* the row, and a single trailing `db.commit()` lets SQLAlchemy pick its
   own flush order, which ignores that list. Fix: **commit after each delete**. Applied to both
   suites. (The 7 errors were all teardown, never assertions — worth reading the traceback rather
   than reordering the list on instinct.)

### No new deps / env / CI
`ForeignKey`/`Text`/`TIMESTAMP` already in use. CI's Postgres + `alembic upgrade head` + pytest
cover the new migration and tests automatically.

### Verified (against the real db)
- Autogenerate detected exactly the four intended changes. `\d treatment` / `\d visit` /
  `\d procedure_performed` show the exact columns, nullability, defaults (`status='in_progress'`),
  indexes, and every FK. `\d appointment` now shows **`appointment_treatment_id_fkey`** with
  `treatment_id` still nullable.
- **Reversible:** `downgrade -1` drops all three tables **and** the appointment FK (back to a bare
  nullable UUID — the 3.1 shape); `upgrade head` recreates. Image rebuilt before applying (the
  stale-image footgun).
- **85 tests pass** in-container against real Postgres (73 prior + 12).
- **Live against the compose Postgres:** built a real RCT thread — patient → treatment → **3 visits**
  (one scheduled via an appointment carrying `treatment_id`, two walk-ins) → 2 procedures priced from
  a catalogue item — and read it back sitting-by-sitting. Guards all bite: bogus `visit.treatment_id`
  rejected, **null `visit.treatment_id` rejected**, bogus `appointment.treatment_id` rejected (the
  3.1 deferral demonstrably closed), and **deleting a treatment that has visits is blocked**. Cleaned
  up fully.

### Carried forward → 4.3
- **Visit recording API**, which must **auto-create a treatment when the work is new and auto-close
  it for single-visit work** — that's what keeps `visit.treatment_id` NOT NULL invisible to the user.
- Still open elsewhere in Phase 4: **clinic settings** (hours + slot size, hardcoded in
  `lib/week.ts`) and the **clinic timezone** (the UTC-day caveat from 3.3). New: the
  **price-snapshot question for 5.2**.

### Housekeeping note (not touched)
There's a stray `backend;C` directory in the project root — an artifact of a malformed shell command
in some earlier session, not referenced by anything. Left alone; delete at your discretion.

### Suggested commit
`feat: add treatment and visit models`

---

## 2026-07-20 — Step 4.1: treatment catalogue (PHASE 4 BEGINS)

**Status:** complete — model + migration + role-split API + admin Settings screen, verified (73
tests pass; `numeric(10,2)` confirmed in the DB; migration reversible; admin-vs-receptionist proven
live). For commit. **Two firsts: the project's first money column, and the first real use of
`require_role`.**

### Scope decisions (confirmed with user)
- **Full vertical slice** — model + migration + API + the admin screen (the roadmap line is "list +
  Settings CRUD").
- **Read: any active staff · Write: admin only.** Reads use `get_current_staff` (visits in 4.3 and
  invoices in 5.2 need the list); writes use `require_role("admin")` per BUILD_PLAN §2.
- **Deactivate, never delete**; `default_price` **required**, `Numeric(10,2)`, `>= 0`.

### Built — backend
- `app/models/treatment_item.py` — `TreatmentItem`: uuid PK, `name` (Text, **unique + indexed**),
  `default_price` (**`Numeric(10,2)`**), `active` (default true), `created_at`/`updated_at`.
  Registered in `app/models/__init__.py`.
- `alembic/versions/73aeddd50693_add_treatment_item.py` — autogenerated, reviewed clean.
  `down_revision = feae714ecef5`. Creates the table + `ix_treatment_item_name` (unique).
- `app/schemas/treatment_item.py` — Create/Update/Read/ListResponse. Prices are **`Decimal`** with
  `max_digits=10, decimal_places=2, ge=0`. No `active` on create/update (activation is its own
  endpoint pair, like patient archive/unarchive).
- `app/routers/treatment_items.py` (`prefix="/treatment-items"`, registered in `main.py`):
  `GET ""` (+`include_inactive`) and `GET /{id}` → `get_current_staff`; `POST`, `PATCH`,
  `POST /{id}/deactivate`, `POST /{id}/activate` → `require_role("admin")`. Mutations audited
  (`entity="treatment_item"`). A unique-name violation is translated to a **409** rather than a 500.
- `tests/test_treatment_items.py` — 8 tests incl. the headline **`test_non_admin_cannot_write`**
  (receptionist: GET 200, every mutation 403), duplicate → 409, **exact Decimal round-trip**
  (1999.99 / 2500.05), deactivate hidden-but-fetchable, activate restores. 65 → **73**.

### Built — frontend
- `lib/use-treatment-items.ts` — list hook (+`refetch` nonce) and `createItem`/`updateItem`/
  `setItemActive`, each returning `"ok" | "forbidden" | "conflict" | {error}` so 403 and 409 show
  distinctly. Prices handled as **strings** (never parsed to float for arithmetic); `formatPrice`
  uses `Intl.NumberFormat("en-IN", INR)` for display only.
- `app/settings/treatments/page.tsx` + `treatment-list.tsx` — the catalogue table (name, price,
  state, actions), an add form, inline edit, Retire/Restore, and a "Show retired" toggle.
  **Admin gate** via `useCurrentStaff()` → non-admins get a read-only view + a short note. First
  screen under `app/settings/`.
- `app/role-nav.tsx` — the admin placeholder is now **Treatments → `/settings/treatments`**.

### No new deps
`Numeric`/`Decimal` are SQLAlchemy/Pydantic/stdlib built-ins.

### Verified
- Migration: `feae714ecef5 -> 73aeddd50693`; `\d treatment_item` shows **`default_price |
  numeric(10,2)`** (not double precision), unique `ix_treatment_item_name`, `active` default true.
  **Reversible** (downgrade drops it, upgrade recreates). Image rebuilt before applying.
- **73 tests pass** in-container against real Postgres.
- Frontend `lint` + `build` green; `/settings/treatments` is a new route; Docker image rebuilds.
- **Live against the compose Postgres:** admin created 5 real items (prices exact: `300.00`,
  `1200.50`, `1999.99`); duplicate name → **409**; **receptionist GET 200 but POST/PATCH/deactivate
  all 403**; deactivate hid the item from the default list yet it remained under
  `include_inactive=true`. The 5 items were left in place for the visual check.
- **Through Caddy:** `/settings/treatments` signed-out → **307 → /login**; `/api/treatment-items`
  no token → **401**.

### Carried forward → 4.2
- `treatment` + `visit` + `procedure_performed` models, and **`appointment.treatment_id` finally
  gets its real FK** (deferred since 3.1). `procedure_performed` will FK to `treatment_item`.
- Still open elsewhere in Phase 4: **clinic settings** (hours + slot size, hardcoded in
  `lib/week.ts`) and the **clinic timezone** (the UTC-day caveat from 3.3).

### Suggested commit
`feat: add treatment catalogue`

---

## 2026-07-19 — Step 3.6: dashboard v1 — today's schedule + arrivals (PHASE 3 COMPLETE)

**Status:** complete — pure frontend, verified (65 backend tests still pass; lint+build+Docker build
green; `/` guard + today's data confirmed live). For commit. **This finishes Phase 3.**

### Scope decisions (confirmed with user)
- **`/` becomes the dashboard** (it was a leftover landing page). Signing in lands on today's
  schedule; RoleNav's "Dashboard" placeholder now links to `/`.
- **Content = today's schedule + arrivals summary** — a table of today's appointments plus count
  tiles per status. "Arrivals" is meaningful now that 3.5 made `arrived` real.
- **HealthCard kept** (user's call) but moved to the **bottom**, de-emphasised, so clinical content
  leads.
- **No status controls on the dashboard** — the day view owns them (one place, no duplication). The
  dashboard links to the calendar instead.

### Built (all frontend — no backend change, no migration, no new deps)
- `app/today-dashboard.tsx` (`"use client"`) — arrivals summary (total + a tile per status, using
  `statusStyle` so summary and table agree) and today's schedule table (time range, patient →
  `/patients/{id}`, dentist, coloured status, reason). loading / error / **empty** states, plus a
  "View calendar →" link. Counts derived client-side from the same list — no extra request.
- `app/page.tsx` — now the dashboard shell: still an async server component (reads the user for the
  email/sign-out header), widened to the `max-w-3xl` pattern used by `/patients` and `/calendar`,
  renders a date heading, `RoleNav`, `TodayDashboard`, then `HealthCard` last.
- `app/role-nav.tsx` — Dashboard item gets `href: "/"`.

### Reused (deliberately wrote no new versions)
`lib/use-day-appointments.ts` (hook + `refetch`), `lib/appointment-status.ts`
(`statusLabel`/`statusStyle`/`STATUSES`), `lib/week.ts` (`todayIso`).

### Verified
- Frontend `lint` + `build` green; `/` stays dynamic (`ƒ`) since it reads the session server-side.
  Docker frontend image rebuilds clean.
- **Backend untouched — 65 tests still pass** (regression check).
- **Through Caddy:** `/` signed-out → **307 → /login**. Today's data present (4 appointments, one
  each `booked` / `arrived` / `cancelled` / `no_show`) so the summary + colours are exercised.
- Stack left up for the user's visual check.

### Timezone (unchanged, still carried forward)
"Today" is the browser's local date; the API bounds the day in UTC. Same caveat as 3.3/3.4 — the
fix needs the Phase-4 clinic-timezone setting. The page heading's date is server-rendered (a label
only); the schedule uses the shared `todayIso()`.

### PHASE 3 COMPLETE
Appointments: model, booking API with DB-enforced double-booking prevention, day + week calendars
with drag-drop rescheduling, the status lifecycle, and a dashboard. The front-desk loop works.

### Carried forward → Phase 4 (4.1)
`treatment_item` list + Settings CRUD, then the clinical core (treatments, visits, inline
follow-ups). Also still open for Phase 4: **clinic settings** (hours, slot size — currently
hardcoded in `lib/week.ts`) and the **clinic timezone**. And `appointment.treatment_id` gets its
**real FK** in 4.2.

### Suggested commit
`feat: add dashboard`

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
