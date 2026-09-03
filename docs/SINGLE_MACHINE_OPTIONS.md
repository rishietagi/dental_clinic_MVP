# SINGLE-MACHINE OPTIONS — one PC, one user, no hosting bill

**Requested 2026-09-03, after a major scope change.** The clinic will now run the app on **one
computer** — the receptionist's desk. The dental assistant enters the dentist's treatment notes at
that same desk. There is no second machine, no multi-user access, and no appetite for a hosting bill.

**The two questions asked:**
1. Can this just go on **Vercel's free tier**?
2. If not, can it be **packaged into an app file** and handed to your mother to install?

> **This document decides nothing.** It supersedes nothing. It sits alongside
> [`DEPLOYMENT_DECISION.md`](DEPLOYMENT_DECISION.md) (the cloud plan) and
> [`ALTERNATIVE_OPTIONS.md`](ALTERNATIVE_OPTIONS.md) (the LAN research), both of which assumed **two**
> machines and are now partly out of date because of it.
>
> **Researched 2026-09-03.** Vendor terms move — re-verify before acting.

---

## 0. The short answer

**1. Vercel: no. Not "expensive" — not permitted, and it never was.**
The Hobby plan **forbids commercial use**, and Vercel defines commercial as any deployment serving
"the financial gain of anyone involved". A dental practice's patient and billing system is squarely
that. This was already found and written up in **step 7.1** and it has not changed: the free-tier
*limits* were never the problem, the *terms* are. It also only hosts half the app — the FastAPI
backend does not run there.

**2. Packaging: yes, and the scope change makes it genuinely viable for the first time.**
Everything that made packaging a bad idea in [`ALTERNATIVE_OPTIONS.md`](ALTERNATIVE_OPTIONS.md)
was about **sharing data between two machines**. That problem no longer exists. One machine, one
database, one user — the hard part is gone.

**But there is one blocker left, and it is the same one as before: login.**
Supabase Auth is a cloud service. The app cannot sign anyone in without internet, and a free
Supabase project **pauses after one week of inactivity** — meaning a week's holiday could lock your
mother out of her own clinic's records on a Monday morning. **A genuinely standalone app must
replace the login system.** That is real work, and it is the whole cost of this option.

**My recommendation: package it — but budget the auth swap as part of the job, not as a detail.**
Expect roughly **3–4.5 days of work**, then ₹0/month forever.

---

## 1. What changed, and why it matters so much

| | Before (Phase 7 plan) | Now |
|---|---|---|
| Machines | 2 (receptionist + dentist) | **1** |
| Concurrent users | 2 | **1** |
| Data sharing between PCs | Required | **Not needed** |
| Remote access | Wanted | Not asked for |
| Hosting budget | ₹655/month | **₹0** |

**Three hard problems evaporated with the second machine:**

- **Sharing** — the entire reason a server was needed. Gone.
- **The double-booking race** — the `EXCLUDE USING gist` constraint (step 3.2) exists because *"two
  PCs will race"* ([`BUILD_PLAN.md`](BUILD_PLAN.md) §11). With one machine there is no race. **The
  constraint stays and still works** — it just stops being the thing that dictates architecture.
- **Conflict resolution / sync** — which is what ruled out every local-first option in
  [`ALTERNATIVE_OPTIONS.md`](ALTERNATIVE_OPTIONS.md) §4.3–4.4. Irrelevant now.

**One new risk appears, and it is serious.** With one machine there is no second copy of anything.
If that PC's disk dies, the clinic's records die with it unless backups are real and rehearsed (§6).

---

## 2. Vercel — ruled out, again, on terms

This was researched in step 7.1 and re-confirmed today. Recording it here so the question is closed
rather than re-opened a third time.

| Why it fails | Detail |
|---|---|
| 🚫 **Hobby forbids commercial use** | Vercel restricts Hobby to personal, non-commercial use, and defines commercial usage as any deployment serving "the financial gain of anyone involved" — explicitly including work by a paid employee or consultant. A clinic's billing system qualifies. |
| 🚫 **They can pull it without notice** | Vercel reserves the right to disable or remove a Hobby deployment with or without notice. The failure mode is not a bill — it is the clinic's records going dark on a Tuesday, with no appeal. |
| ⚠️ **It only hosts half the app** | Vercel runs the Next.js frontend. The backend is a long-running containerised **uvicorn/FastAPI** process with a SQLAlchemy pool and Alembic migrations. That does not lift into serverless functions without a real rearchitecture — so you would still pay to host the backend elsewhere. |
| ⚠️ **And there is still no database** | Vercel is not a Postgres host. You would still need Supabase or similar. |

**Pro is ~$20/developer/month (~₹1,900)** — more than the entire Bangalore droplet plan that hosts
the *whole* stack, while still not hosting the backend.

**The headroom was never the issue.** Hobby includes 1M function invocations against our ~48,000
requests/month. On volume the instinct was right. The terms are the blocker, and they are the kind
you cannot engineer around.

---

## 3. Packaging — what it actually means for this stack

The app is four moving parts. A single-machine package must account for each.

| Part | What it is | In a packaged app |
|---|---|---|
| **Database** | PostgreSQL 16 | ✅ **Bundle it.** Postgres publishes a **zip archive of the binaries specifically for including in another application's installer** — no admin rights, no system-wide install. This is the fact that makes the whole option work. |
| **Backend** | FastAPI / uvicorn (Python 3.12) | ✅ **PyInstaller** compiles it to a single `.exe`. Well-trodden, with known gotchas (uvicorn needs explicit hidden-import hooks; SQLAlchemy drivers too). |
| **Frontend** | Next.js standalone (Node 24) | ✅ Ships as a Node server, or is wrapped in a desktop shell. |
| **Auth** | **Supabase Auth (cloud)** | ❌ **The blocker.** See §4. |

**Two shapes this can take:**

### 3a. The honest, boring one: a Windows installer that runs the stack locally

An installer (Inno Setup / NSIS) that drops the bundled Postgres, the backend `.exe` and the
frontend into `C:\ClinicApp`, registers a background service or a startup shortcut, and puts a
"Clinic" icon on the desktop that opens `http://localhost` in the default browser.

- **Least new technology.** No Rust, no Electron, no new framework in the stack.
- The app your mother uses is **exactly the app that passed 362 tests** — same code, same behaviour.
- Looks like a normal Windows program to her: install once, click the icon.

### 3b. The prettier one: Tauri v2 with a Python sidecar

Same idea, but wrapped in a real desktop window with its own icon and no visible browser. Tauri v2
supports bundling a Python/FastAPI "sidecar", and reference templates for exactly Next.js + FastAPI
exist. It is ~10 MB versus Electron's ~100 MB because it uses the OS webview rather than shipping
Chromium.

- ⚠️ **But Tauri cannot embed Postgres.** The Tauri maintainers say so directly: embedding Postgres
  is not feasible, and the intended path is SQLite. **Migrating Postgres → SQLite is not cosmetic
  for this app** — we would lose the `EXCLUDE USING gist` double-booking constraint, the
  `ARRAY(Text)` columns used for `investigations` and `roles`, and `Numeric` money handling would
  need care. That is a genuine rewrite of the data layer and its tests.
- **You can still use Tauri with bundled Postgres** by treating Postgres as another sidecar process
  — it just isn't the supported happy path, so it is more work than 3a for a nicer window.

**Recommendation: build 3a first.** It is the smaller job and it is reversible — the desktop shell
can be added later without touching the backend.

---

## 4. The login problem — the real cost of this option

**This is the one thing that stops it being a weekend job.**

The mechanics, confirmed against [`backend/app/auth.py`](../backend/app/auth.py):

- The backend verifies tokens **locally** with cached public keys (JWKS). No network needed. ✅
- But **signing in and refreshing a session both call Supabase.** Access tokens last about an hour.

**Three consequences for a standalone app:**

1. **No internet at the clinic = nobody can log in** after the current hour expires.
2. **A free Supabase project pauses after one week of inactivity.** Close for Diwali, come back
   Monday, **nobody can sign in.** For a hosted app that is an annoyance; for an app your mother
   installed on her own PC it is inexplicable — the computer is right there and working.
3. Shipping an installer means shipping **your** Supabase project keys to a machine you do not
   control.

### The fix: swap Supabase Auth for a local auth server

**This does not break the "never hand-write auth" rule** in [`CLAUDE.md`](../CLAUDE.md). You would
still run somebody else's audited authentication server — just on the clinic's own PC instead of
Supabase's cloud. Candidates found: **Authelia** (tiny — under ~30 MB RAM), **Pocket ID**
(passkey-first, ~256 MB), Authentik, Zitadel.

**What it touches:**

- `backend/app/auth.py` — the JWKS verification chain, pointed at the local issuer.
- The frontend's Supabase client calls (`lib/supabase/*.ts`, `proxy.ts`).
- ⚠️ **`staff_user.id` is literally the Supabase Auth UUID** — a standing decision since step 1.2.
  Changing auth provider means **remapping every staff identity**. Free right now, while the
  database holds nothing but seed data. **Expensive after real patients exist**, because
  `audit_log.actor_id`, `visit.dentist_id` and `appointment.dentist_id` all point at it.

> **This is the strongest argument for deciding soon rather than later.** The same trap was already
> flagged for the Mumbai region question in 7.2: identity changes are free today and painful after
> go-live.

**Simpler alternative worth considering, given one user on one physical machine:** the threat model
has genuinely changed. The old model was "two PCs, a shared login, data on the public internet". The
new one is "one PC, in a locked clinic, behind Windows' own login". It is legitimate to ask whether
the app needs its own login at all, or whether Windows account security plus a simple local
passphrase is proportionate. **That is a judgement call for you and your mother, not a technical
one** — but it could remove this entire work item, and it is worth deciding deliberately rather than
inheriting a cloud login because it happens to be what we built.

> **Note the knock-on for 6.12.** Three role logins were built two steps ago precisely so the
> receptionist and dentist could not see the practice's takings. **With one shared machine at the
> front desk, that separation weakens on its own** — whoever is sitting there is signed in. Worth
> deciding whether the admin/dentist/receptionist split still earns its keep, or whether the money
> screens simply sit behind a separate passphrase your mother knows.

---

## 5. What this costs to build

| Task | Effort |
|---|---|
| Bundle Postgres (zip binaries, `initdb` on first run, data dir under `%LOCALAPPDATA%`) | ~0.5 day |
| PyInstaller the backend, incl. Alembic migrations on startup | ~0.5 day |
| Bundle the Next.js standalone server; point `NEXT_PUBLIC_API_URL` at localhost | ~0.5 day |
| **Replace Supabase Auth with a local provider** (or remove the login — §4) | **1–2 days** |
| Installer + desktop icon + start-on-login | ~0.5 day |
| Backup script + a **rehearsed** restore (§6) | ~0.5 day |
| **Total** | **~3–4.5 days** |

**Then ₹0/month, forever.** No droplet, no domain, no Supabase, no renewal to forget.

**Against the cloud plan's ₹655/month (~₹7,860/year):** the packaged app pays for itself in under a
year of effort, and after that it is free. With one user and no sharing requirement, **the cloud
plan is now buying something the clinic no longer needs.**

---

## 6. The risk you are taking on, stated plainly

**Everything lives on one hard drive, in one building, in a city you do not live in.**

This is worse than it was under either previous plan, and it is the honest price of ₹0/month:

- **No vendor, no redundancy, no snapshots.** One dead SSD is the whole clinic.
- **No remote fix.** You cannot ssh into your mother's desktop. Every update and every "it won't
  open" is a phone call or a trip.
- **Windows will do Windows things** — updates, reboots, antivirus quarantining an unsigned `.exe`.
  (Unsigned installers also trigger SmartScreen warnings; a code-signing certificate costs money, or
  she clicks through the warning once.)

**Non-negotiable mitigations — this is the same standard [`BUILD_PLAN.md`](BUILD_PLAN.md) §11 already
sets, and 8.3 already gates real patient data on:**

1. **Automatic nightly `pg_dump`**, scheduled by the installer, not by hand.
2. **A copy that leaves the machine.** rclone to Google Drive's free 15 GB is the ₹0 answer — at
   ~50 MB/year, a compressed dump is single-digit megabytes, so 15 GB is effectively unlimited.
   **Encrypt it: these are patient records.**
3. **A restore you have actually rehearsed.** Untested backups are decoration.
4. **A UPS** (~₹3,000–5,000) — power cuts and an abruptly-killed Postgres are a bad combination.

**A second copy of the data is not optional here. It is the only thing standing between a hardware
failure and losing the practice's records.**

---

## 7. Comparison

| | Vercel free | Cloud (stack B) | **Packaged app** |
|---|---|---|---|
| Cost/month | ₹0 | ₹655 | **₹0** |
| **Allowed for a clinic?** | 🚫 **No — terms** | ✅ | ✅ |
| Hosts the whole app | ❌ frontend only | ✅ | ✅ |
| Work to get there | n/a | ~6–8 h (planned) | **~3–4.5 days** |
| Works with no internet | ❌ | ❌ | ✅ *(after the auth swap)* |
| Survives a dead disk | ✅ | ✅ | ❌ **backups only** |
| You can fix it remotely | ✅ | ✅ | ❌ |
| Updates | automatic | `git push` | a new installer she runs |
| Data physically in the clinic | ❌ | ❌ | ✅ |

---

## 8. What I would do

**Build the packaged app (3a), and treat the auth decision as the first step, not the last.**

Reasoning:

1. **The scope change removed the actual reason to host anything.** Sharing between machines was the
   requirement that justified a server. It is gone. Paying ₹655/month to serve one user on one PC is
   paying for capability the clinic will not use.
2. **Vercel is not an option and will not become one.** Closing that question for good.
3. **It is genuinely free forever**, which for a small clinic in Davangere is a real, permanent win
   — no renewal, no card on file, no service to be surprised by.
4. **The data stays in the clinic**, which is the simplest possible answer to the DPDP residency
   question that [`DEPLOYMENT_OPTIONS.md`](DEPLOYMENT_OPTIONS.md) §6 spent so long on.

**Two things to decide before any code is written:**

- **The auth question (§4).** Local auth server, or no app login at all given one physical machine?
  This shapes everything else, and **it is free to change now and expensive after real patient data
  exists** — because `staff_user.id` *is* the auth provider's UUID.
- **Whether you accept the single-disk risk**, and commit to §6's backup work as real work rather
  than a checkbox. If the honest answer is "backups will not happen reliably", then the ₹655/month
  cloud plan is genuinely the safer choice and worth the money.

**What I would not do:** ship this without the backup script and one rehearsed restore. Everything
else here is a convenience trade-off; that one is the difference between a clinic that loses a
Tuesday and a clinic that loses eleven years.

**What this does to the roadmap:** Phase 7 as written (7.3 provision Supabase → 7.6 CI deploy) is
about deploying to a rented server, and most of it stops applying. It would be replaced by a
packaging phase. **That is a bigger call than one step, so it should be made deliberately** — this
document is the input, not the decision.

---

## Sources

Researched 2026-09-03. Terms and prices change — re-verify before acting.

- **Vercel terms:** [Hobby plan](https://vercel.com/docs/plans/hobby) · [Is Vercel free? Yes on Hobby, no for commercial](https://zplatform.ai/guides/is-vercel-free/) · [Vercel pricing 2026](https://costbench.com/software/developer-tools/vercel/)
- **Bundling Postgres:** [PostgreSQL Windows downloads — zip archive for inclusion in another installer](https://www.postgresql.org/download/windows/) · [Portable PostgreSQL on Windows without installation](https://notepad.onghu.com/2025/portable-postgresql-on-windows-without-installation-pg18/) · [Installing without admin rights](https://www.geeksforgeeks.org/postgresql/postgresql-installing-postgresql-without-admin-rights-on-windows/)
- **PyInstaller + FastAPI:** [pyinstaller-fastapi reference repo](https://github.com/iancleary/pyinstaller-fastapi) · [uvicorn + PyInstaller hidden imports](https://github.com/Kludex/uvicorn/discussions/1820) · [Packaging Python with PyInstaller](https://til.simonwillison.net/python/packaging-pyinstaller)
- **Tauri:** [Tauri SQL plugin](https://v2.tauri.app/plugin/sql/) · [Embedding PostgreSQL in Tauri — not feasible, use SQLite](https://github.com/tauri-apps/tauri/discussions/5418) · [Tauri v2 Python sidecar example](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)
- **Supabase free tier:** [Supabase pricing 2026 — pauses after one week inactivity](https://uibakery.io/blog/supabase-pricing) · [Free tier limits 2026](https://automationatlas.io/answers/supabase-free-tier-limits-2026/) · [Supabase JWTs](https://supabase.com/docs/guides/auth/jwts)
- **Local auth servers:** [Self-hosted auth solutions 2026](https://supertokens.com/blog/self-hosted-auth-solutions-in-2026) · [Best self-hosted SSO tools](https://selfhosting.sh/best/authentication-sso/)

**Not verified by me:** every figure and term above is as published on 2026-09-03; none was tested by
signing up or building. **Nothing here has been built or tried against this app** — the packaging
effort estimates are from documentation and reference implementations, not from packaging this
codebase. The auth-swap estimate in particular is the least certain number in this document.
