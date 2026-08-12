# CHECK REPORT — step 6.13

**A full end-to-end pass over the app, hunting bugs, bottlenecks and workflow friction.**
Run 2026-08-12, immediately after 6.12 introduced three role logins.

**Everything below marked FIXED is already applied and tested.** The owner asked for
find-and-fix in one pass; this document exists so the diff is reviewable *after* the fact,
and so anything vetoed can be reverted knowingly.

**State after the pass:** 362 backend tests pass (+7), the new
[`scripts/e2e_check.py`](../backend/scripts/e2e_check.py) runs **75/75**, lint and build green.

---

## How it was checked

1. **A permanent E2E harness** — [`backend/scripts/e2e_check.py`](../backend/scripts/e2e_check.py),
   75 checks walking one clinic day in order: patient → booking → arrival → chairside visit with
   the full OPD record → dental chart → second sitting → invoice → payments → lab out and back →
   recall → the role matrix → soft delete. It creates its own data and deletes it on the way out.
   **This is new.** The "42/42 checks" cited in the 6.9 and 6.11 log entries were throwaway scripts
   that no longer existed, so every step since has had to rebuild the harness before it could check
   anything. It is committed now.
2. **An edge-case probe** (temporary, deleted) — LIKE-wildcard injection, archived-patient activity,
   query-param combinations, pagination overlap, negative and overpayments, deactivated dentists
   still appearing in dropdowns, duplicate catalogue names, invalid FDI tooth numbers, transitions
   against cancelled appointments.
3. **A read of every screen's click-path** for each of the three roles, looking for dead ends —
   places where the UI invites an action the API will refuse.

---

## What was already right

Worth recording, because it is most of the app and it means the findings below are narrow:

- Double-booking is refused by the **GiST constraint**, not just the pre-check.
- Recording a visit **auto-closes its appointment**; a cancelled one correctly stays cancelled.
- The **chart is genuinely append-only** — re-marking a tooth supersedes, and the pre-treatment
  finding survives in history. This is the medico-legally important one and it holds.
- **Money is exact** — invoice totals, derived status, overpayment capped at `paid` with
  `outstanding` floored at 0.00.
- **Query params narrow** rather than silently returning everything — the 6.8 lesson stuck.
- **Deactivated dentists** drop out of the assignment dropdowns.
- **Invalid FDI tooth numbers** are rejected; deciduous teeth work; clearing a tooth to "sound"
  removes the row rather than storing a value.
- Bad date formats, `date` + `from`/`to` together, and missing params all 422 with readable messages.
- Pagination pages do not overlap.

---

## Findings

### 1. 🐞 BUG — the patient search treated `%` and `_` as wildcards · **FIXED**

**`backend/app/routers/patients.py`**

The search term went into an `ILIKE` pattern unescaped. `%` and `_` are SQL LIKE wildcards, so:

- typing **`%`** in the search box returned **every patient in the clinic**;
- **`_`** matched any single character, so a phone search like `98_1` silently matched numbers
  nobody asked for — and a receptionist would have no way to know the results were wrong.

Not SQL injection — SQLAlchemy still parameterises the value — but wrong results from a search box
are their own kind of bug at a front desk.

**Fix:** a `_escape_like()` helper escaping `\`, `%` and `_` (backslash first, or it re-escapes the
escapes), paired with `ilike(..., escape="\\")`. A literal `%` in a patient's name is now findable,
which it previously was only by accident.
**Test:** `test_search_treats_like_wildcards_literally`.

### 2. 🐞 BUG (consistency) — archived patients still accepted new appointments and visits · **FIXED**

**`backend/app/routers/appointments.py`, `backend/app/routers/visits.py`**

`patient_files.py` has refused uploads for archived patients **since 5.6**, with the rule stated
plainly: an archived record is retained but not actively edited. Booking and visit recording never
got the same rule, so the API accepted both. The UI already hides those buttons for archived
patients, so this was latent rather than live — but the failure mode is a patient archived by
mistake quietly accumulating appointments nobody intends to keep.

**Fix:** both now return **409** with a message naming the reason. It is a **soft block, not a dead
end** — unarchiving restores normal behaviour, and the E2E asserts exactly that.
**Test:** `test_archived_patient_refuses_new_activity`, plus four E2E checks.

> ⚠️ **This is the one change that alters API behaviour rather than fixing a defect**, so it is the
> one to veto if you disagree. It applies an existing decision uniformly rather than inventing a new
> one, which is why I applied it — but the call is yours.

### 3. 🐌 FRICTION — booking an appointment dropped you on *today's* calendar · **FIXED**

**`frontend/app/appointments/new/new-appointment-form.tsx`, `frontend/app/calendar/`**

After booking, the app redirected to `/calendar`, which always opens on **today**. Book something
for next Tuesday and you land on today, see nothing, and have to click "Next" four times to confirm
the booking actually landed. At a front desk, *not being able to see what you just did* is the kind
of small friction that erodes trust in a new system.

**Fix:** `/calendar?date=YYYY-MM-DD` now opens the day view on a specific day, and booking redirects
to the day it booked. The date comes from the `datetime-local` input's own value, so it is already
the clinic-local calendar day the user picked — no timezone conversion, which is what makes it
correct. A malformed `?date=` falls back to today rather than rendering an empty day. Follows the
existing `useSearchParams` + `Suspense` pattern from `/appointments/new` and `/lab/new`.

### 4. 🚧 DEAD END — the receptionist's "Record now" button led to a wall · **FIXED**

**`frontend/app/worklists.tsx`**

The dashboard's **Nothing recorded** card offers a "Record now" button on every appointment finished
without a write-up. Recording a visit is `require_role("dentist","admin")`, so a receptionist
clicking it landed on a form they cannot submit. **6.12 made this worse** — before three logins, the
one shared account was effectively dentist+admin and always could.

**Fix:** the button and its column are hidden for non-dentists; the **card stays**, because knowing
"three appointments have no clinical record" is exactly what the front desk chases the dentist
about. The hint text changes to say who needs to act.

---

## Considered and deliberately left alone

| Thing | Why it stays |
|---|---|
| **Overpayment is allowed** (₹999,999 against a ₹1,000 invoice succeeds) | Deliberate since 5.3 and reaffirmed in 6.8 — the UI warns, the API allows. Real front desks take round numbers and settle up. `outstanding` floors at 0 while `amount_paid` stays truthful. |
| **The visit form is long** (~1,050 lines, 18 clinical fields) | It mirrors the clinic's paper OPD card by design (6.10), and already has NAD/NRMH quick-fill chips plus a collapsed examination section. Restructuring it is a design change, not a fix — **raise it as its own step if she finds it slow in daily use.** |
| **Unbilled worklist includes visits of patients archived afterwards** | Arguably correct: treatment happened and should still be billed. Flagging it here so the decision is recorded rather than accidental. |
| **Dentists share one login** | 6.12's explicit model. Per-person attribution stays on the dentist dropdown. |

---

## Recommended next

Not done here — each is a step, not a fix:

1. **Run `e2e_check.py` at the end of every future step.** It is 30 seconds and it is now the
   cheapest regression net the project has.
2. **Add it to CI** once Phase 7 settles. It needs a database, which CI already provisions.
3. **Watch the visit form in real use.** It is the screen the dentist touches every sitting and the
   most likely source of a future "this is too slow" — worth a targeted step if it proves so.
