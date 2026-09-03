# ALTERNATIVE OPTIONS — running the clinic app locally instead of deploying it

**A research spike, requested 2026-08-12.** Can this app be packaged to run on the receptionist's and
the dentist's own computers — sharing data, updating itself, costing nothing — instead of being
deployed to a rented server?

> **This document decides nothing and changes nothing.** It does not touch the Phase 7 plan or the
> stack chosen in [`DEPLOYMENT_DECISION.md`](DEPLOYMENT_DECISION.md). It exists so the local option
> is judged on facts rather than on the instinct that "local must be cheaper".
>
> **Researched 2026-08-12.** Vendor terms and prices move — re-check anything here before acting on
> it. Sources are listed at the end.

---

## 0. The short answer

**Yes, it can run locally — and one of the four ways is genuinely cheap and nearly free of code
changes. But two beliefs behind the question turn out to be false, and they matter more than the
money:**

1. **"Local means no internet needed" is false.** The app's login goes through **Supabase Auth**,
   which is a cloud service. Verifying a token works offline; *issuing* one does not. With no
   internet, everyone already signed in keeps working for **about an hour** and then cannot log back
   in. Running the app on your own PC does not change that. Making it truly offline means replacing
   the auth system — a real project, not a config change (§5).
2. **"Packaging it as an app" and "sharing data between two computers" are different problems, and
   the second is the hard one.** Two packaged copies on two PCs, each with its own database, are two
   separate clinics. Packaging solves nothing about sharing (§4.3).

**The realistic local option is not a packaged app at all** — it is **one PC acting as the clinic's
server, with the other machine using it through a browser over the office network.** That needs
**three config values changed and one image rebuilt**. Everything else in this document is
substantially harder for substantially less benefit.

**What it actually saves: about ₹600/month (~₹7,200/year).** What it costs: the clinic's records
living on one hard drive in the room, with backups that are entirely your responsibility, no access
from outside the clinic, and every update becoming a house call.

---

## 1. What we are actually trying to run

Any local plan has to carry this, unchanged, or change it deliberately:

| Piece | What it is | Why it matters here |
|---|---|---|
| **Frontend** | Next.js standalone server (Node 24) | A **server**, not a static site. Something must run it. |
| **Backend** | FastAPI / uvicorn (Python 3.12) | Long-running process, SQLAlchemy pool, Alembic migrations. |
| **Database** | PostgreSQL 16 | Not SQLite. Uses Postgres-specific features we depend on (§4.4). |
| **Proxy** | Caddy | Single entry point; already env-configurable. |
| **Auth** | **Supabase Auth (cloud)** | **The one piece that is not ours and not local.** |

**Measured footprint** (from [`DEPLOYMENT_OPTIONS.md`](DEPLOYMENT_OPTIONS.md) §1): **~201 MB RAM
idle** for all four containers, ~1.14 GB of images, and **~50 MB of database growth per year** at
this clinic's 3 patients/day. This is a small app. Any PC bought in the last eight years can host it
without noticing.

**Two things the codebase already got right**, which make the local option cheaper than it would
otherwise be:

- **`SITE_ADDRESS` is already an env var** in the [Caddyfile](../Caddyfile) — the entry address was
  designed to be config, not code.
- **Caddy already publishes port 80 to the host** ([docker-compose.yml](../docker-compose.yml)), so
  the app is *already* reachable from other machines on the network. Nobody has tried it, but
  nothing is blocking it.

**One thing that will bite:** `NEXT_PUBLIC_API_URL` is a **build argument**, inlined into the
browser bundle at `npm run build` — it is not read at runtime. It is currently hardcoded to
`http://localhost/api` in compose. A browser on the *dentist's* PC would send its API calls to its
own machine and fail. **The frontend image must be rebuilt with the server's LAN address.** This is
already recorded as a standing gotcha in [`LOG.md`](LOG.md); it is config, not architecture, but it
is not optional.

---

## 2. The four problems every local plan must solve

Judge each option below on these, not on the monthly figure:

1. **Sharing** — the receptionist books an appointment; the dentist must see it *immediately*, from
   a different machine. This is the whole reason a clinic needs software rather than a spreadsheet.
2. **Login** — Supabase Auth is a cloud dependency (§5).
3. **Updates** — with no deploy pipeline, how does a fix reach two machines in another city?
4. **Backups and survival** — if the machine holding the database dies on a Tuesday, what happens to
   eleven years of patient records? On a VPS this is partly someone else's problem. On a PC under
   the reception desk it is entirely yours.

---

## 3. Option L1 — one PC is the clinic server, the other uses a browser ⭐

**The recommended local option, and the only one I would actually build.**

The receptionist's PC runs the existing Docker Compose stack. The dentist's PC opens a browser and
goes to `http://clinic` (or the server's LAN IP). Both see the same live database, because there is
only one database. **No packaging, no sync, no rearchitecture.**

### What it actually takes

| Change | Effort |
|---|---|
| Rebuild the frontend image with `NEXT_PUBLIC_API_URL` = the server's LAN address | 10 min |
| Set `SITE_ADDRESS` and `CORS_ORIGINS` to match | 5 min |
| Give the server PC a **fixed** LAN IP (DHCP reservation on the router) | 15 min |
| Start Docker Desktop on login; set the stack to `restart: unless-stopped` | 15 min |
| Nightly `pg_dump` + copy off the machine (§7) | 1–2 h, once |
| **Total** | **half a day** |

### Cost

**₹0/month in services.** Not literally free — see §7 — but there is nothing to pay a vendor.

### What is good about it

- **It works today.** This is the same stack, same code, same tests, same behaviour. Nothing is
  reimplemented, so nothing new can be wrong.
- **All the correctness guarantees survive** — including the GiST constraint that stops two PCs
  double-booking the same slot (§4.4). One database means one source of truth.
- **Genuinely fast.** Everything is on the office LAN; no round trip to Mumbai.
- **Data never leaves the clinic**, which is the easiest possible answer to "where is our data?"
- **Reversible.** If it goes badly, deploying to the droplet later is the plan you already have.

### What is bad about it, honestly

- **The receptionist's PC becomes infrastructure.** It must be on whenever the dentist needs the
  app. Somebody will shut it down to save power, or Windows will reboot it for updates mid-morning.
- **One disk holds the whole clinic.** No RAID, no snapshots, no vendor. **This is the real risk**,
  and it is the reason §7 is not optional.
- **No access from outside the clinic.** The owner cannot look at the day's figures from home. The
  usual fix — Tailscale — has a **trap**: its free plan is **non-commercial only**, exactly like the
  Vercel Hobby problem found in 7.1. Paid Tailscale is **$8/user/month (~₹760)**, which alone costs
  more than the entire cloud stack. Free alternatives exist (self-hosted **Headscale**, WireGuard on
  the router, a Cloudflare Tunnel) but each is real setup work.
- **Every update is a remote-access session**, not a `git push`.
- **Login still needs internet** (§5).

> **Docker Desktop licensing — checked, and it is fine.** Docker Desktop is free for commercial use
> by organisations with **fewer than 250 employees and under $10M revenue**. A two-person dental
> clinic is comfortably inside that. Worth knowing, because it is exactly the kind of licence trap
> that killed Vercel in 7.1.

### Variant: a dedicated mini PC instead of the reception desktop

Puts the server on its own always-on box (an Intel N100 mini PC, ~8–12 W, roughly ₹12,000–18,000 in
India) so no one turns it off and Windows updates do not take the clinic down.

- **One-off ~₹15,000**, plus electricity of roughly **₹55–70/month** at 10 W and ₹8/kWh.
- Removes the "someone shut the PC down" failure mode entirely — the single biggest weakness of L1.
- **Payback against the ₹655/month cloud stack is a little over two years**, before counting your
  own time.
- Add a small UPS (~₹3,000–5,000) or an unplanned power cut becomes an unplanned database recovery.

---

## 4. The options that sound better than they are

### 4.1 Package it as a desktop app (Electron / Tauri)

The literal reading of the question: an installable `.exe` on each machine.

**Technically possible.** Tauri v2 supports a "sidecar" — bundling a Python/FastAPI server inside a
desktop app — and there are working reference templates doing exactly Next.js + FastAPI. Tauri is
far lighter than Electron (~10 MB vs ~100 MB) because it uses the OS webview instead of shipping
Chromium.

**But it does not solve the actual problem, and it adds several:**

- **It does not solve sharing.** Two installs = two databases = two clinics. You still need §4.3 or
  §4.4 on top, which is where all the difficulty lives. **Packaging is orthogonal to the thing you
  actually want.**
- **You would have to bundle PostgreSQL too**, or migrate to SQLite — and the migration is not
  cosmetic (§4.4).
- **It is a second product to maintain.** Windows installers, code signing, per-OS builds, an update
  server (self-hosted Tauri updaters exist, or a static JSON on GitHub Releases). All of that, for
  two users in one building.
- **Docker Desktop is already "the package".** It installs the whole stack in one step and updates
  with `docker compose pull`. Building a bespoke installer to replace something that already works
  is effort with no user-visible return.

**Verdict: not worth it.** The only thing it buys over L1 is a desktop icon.

### 4.2 Put the database on a shared network folder

The instinct is: put the data file on a shared drive and let both PCs open it.

**Do not do this. It corrupts data.** SQLite's own documentation is explicit that file locking is
buggy on many network filesystems, and that two clients writing the same database over SMB can
corrupt it — SMB opportunistic locking makes the first client cache the whole file locally. Their
own guidance is to avoid a database accessed directly and simultaneously from several computers over
a network, and to use a client/server engine instead — which is exactly what L1 is.

Postgres does not even offer this; its data directory is not shareable at all.

**Verdict: the one option here that can actually destroy patient records.** Ruled out.

### 4.3 Two independent copies that sync (local-first / CRDT)

The most attractive-sounding option: both PCs hold a full local database, work offline, and
reconcile automatically. Real technology — **PowerSync**, **ElectricSQL**, **cr-sqlite**, Yjs/Automerge.

**Why it does not fit *this* app:**

- **It is a rewrite, not an integration.** These tools sync a local SQLite database to clients.
  This app's rules live in **server-side Python** — visit auto-close, invoice generation, the
  treatment state machine, role guards. A local-first architecture moves that logic into the client
  or into sync rules. That is most of Phases 3–6, rebuilt.
- **Most of them still need a central service**, which reintroduces the cost and the internet
  dependency the exercise was meant to remove. PowerSync's free tier is 2 GB/month synced; its Open
  Edition can be self-hosted — but self-hosted onto *what*? Something must be always-on and reachable
  by both machines, which is L1 again with extra steps.
- **It breaks a guarantee this app deliberately relies on** — see §4.4.

**Verdict: the right architecture for a different app.** Genuinely interesting if this were being
designed from scratch for multi-site offline use. It is not a retrofit.

### 4.4 The specific thing that rules out eventual consistency

This is the sharpest technical finding in this document, so it gets its own section.

**Double-booking is prevented by a PostgreSQL `EXCLUDE USING gist` constraint** (`appointment_no_overlap`,
from step 3.2). It was chosen deliberately, and the reasoning is recorded in [`LOG.md`](LOG.md):
*"the DB is the real guarantee — it survives two racing PCs."*

**That guarantee cannot exist across two databases that sync afterwards.** If the receptionist books
11:00 with Dr. A on one machine while the dentist books the same slot on another, both succeed
locally — each database is internally consistent — and the clash only appears when they reconcile.
By then both patients have been told to come in. Conflict resolution in these systems is typically
**last-writer-wins**, which here means *silently discarding one of the two appointments*.

Any peer-to-peer design (§4.3), and any design where each PC has its own database, **downgrades a
hard guarantee into a cleanup problem.** `BUILD_PLAN.md` §11 lists double-booking prevention as a
non-negotiable, and it is right to: two PCs racing is not a hypothetical at a front desk, it is
Tuesday.

**One shared database (L1) keeps the guarantee. Everything else trades it away.**

---

## 5. The login problem — the reason "local" ≠ "offline"

**Supabase Auth is a cloud service, and the app cannot issue a login without it.**

The mechanics, confirmed against [`backend/app/auth.py`](../backend/app/auth.py) and Supabase's docs:

- The backend verifies tokens **locally** using public keys (JWKS) it caches in memory. Verification
  needs no network — it is just cryptography.
- But **signing in, and refreshing an expired session, both go to Supabase.** Access tokens expire
  in about **an hour** by default.

**So with the internet down:** anyone already signed in keeps working for up to an hour, then is
locked out. **A local install does not change this.** If the clinic's line drops — the exact scenario
`BUILD_PLAN.md` §11 warns about for a tier-2 town — running on your own PC does not save you.

### If you genuinely want offline login

Three paths, in increasing order of sanity:

1. **Self-host the full Supabase stack** — 10+ containers, and the documented requirement is **4 GB
   RAM minimum, 8 GB recommended**. That is 20–40× this app's entire footprint, to serve two users.
   Absurd here.
2. **Self-host a small auth server instead** — **Authelia** (under ~30 MB RAM), **Pocket ID**
   (passkeys, ~256 MB), Authentik, Zitadel. This is the credible route. **It does not break the
   "never hand-write auth" rule** — you are still running someone else's audited auth server, just on
   your own hardware. But it means migrating the auth integration, and `staff_user.id` is currently
   *literally the Supabase Auth UUID*, so identities would have to be remapped.
3. **Extend the token lifetime** so a short outage is survivable. A stopgap, and it weakens
   revocation — a longer window where a compromised token stays valid.

**None of this is in scope now.** It is recorded so that "let's go local so we don't need internet"
is understood to be a **project**, not a setting.

---

## 6. Updates

| | Cloud (chosen plan) | L1 (LAN server) | Packaged app |
|---|---|---|---|
| How a fix ships | `git push` → CI builds → droplet pulls | Remote in, `git pull`, `docker compose up -d --build` | Build installers, sign, publish, each PC downloads |
| Can you do it from another city? | Yes, automatically | Only with remote access set up first | Yes, once the update server exists |
| Who must be present | Nobody | Somebody, unless remote access works | Nobody |
| Migrations | A deliberate step (8.4) | Manual, by you, on the box | Must run inside the app on every install |

**The honest point:** you do not live in Davangere. Cloud updates are automatic; **local updates
require getting into that building or into that machine.** Set up remote access *before* you need it,
or the first urgent fix becomes a travel plan.

---

## 7. Backups — where "free" stops being free

**On the cloud plan this is already a known weak point.** On the local plan it is *the* weak point,
because there is no vendor and no second copy of anything.

A local setup needs, at minimum:

- **A nightly `pg_dump`**, scheduled (Windows Task Scheduler or a container on a timer).
- **A copy that leaves the machine.** A dump sitting on the same disk as the database is not a
  backup. **rclone to Google Drive's free 15 GB** is the obvious ₹0 answer and is well-trodden — at
  ~50 MB/year of data, a compressed dump is single-digit megabytes, so 15 GB is effectively
  unlimited here. Encrypt it: these are patient records.
- **A restore you have actually rehearsed.** `BUILD_PLAN.md` §11 says it best: untested backups are
  decoration. This is true regardless of where the app runs.
- **A UPS**, if the box is always on. Power cuts and Postgres are a bad combination.

**This work is the same in both worlds** — Phase 8.2/8.3 already budgets it for the cloud plan
(Supabase Free has no managed backups either). **The difference is the blast radius when it fails:**
cloud means losing the app but not the machine; local means one dead SSD takes the clinic's records
with it.

---

## 8. What it actually costs, both ways

Cloud figures from [`DEPLOYMENT_DECISION.md`](DEPLOYMENT_DECISION.md). Electricity at ₹8/kWh.

| | Cloud (stack B) | L1 on the reception PC | L1 on a mini PC |
|---|---|---|---|
| Server | ₹570/mo | ₹0 | ~₹15,000 one-off |
| Database | ₹0 (Supabase Free) | ₹0 | ₹0 |
| Domain | ₹85/mo | ₹0 (not needed on a LAN) | ₹0 |
| Electricity | ₹0 | ~₹0 (PC is on anyway) | ~₹60/mo |
| UPS | ₹0 | — | ~₹4,000 one-off |
| Backup storage | ₹0–475/mo | ₹0 (Google Drive free) | ₹0 |
| Remote access | ₹0 (it's on the internet) | ₹0–760/mo ⚠️ | ₹0–760/mo ⚠️ |
| **Running total** | **₹655/mo** | **~₹0/mo** | **~₹60/mo + ₹19,000 once** |

⚠️ **Remote access is the line that can quietly destroy the saving.** Tailscale's free plan is
non-commercial only; its paid plan at ~₹760/month costs more than the whole cloud stack. Free routes
exist (Headscale, router WireGuard, Cloudflare Tunnel) but are your setup and your maintenance.

**Best case, the local option saves ~₹655/month — about ₹7,860/year.**

**What that saving does not include:**

- **Your time.** Half a day to set up, plus every update, plus every "the app won't open" phone call.
  At any professional rate, a handful of those a year exceeds ₹7,860.
- **The risk premium.** One disk, in a room, in a town you do not live in.
- **The thing you cannot buy back:** if that machine dies and the last good backup was three weeks
  ago, ₹7,860/year was not the relevant number.

---

## 9. Straight comparison

| | Cloud (stack B) | L1 — LAN server | Packaged app + sync |
|---|---|---|---|
| Cost/month | ₹655 | ~₹0–60 | ~₹0–60 |
| Code changes | none | **3 config values + rebuild** | **major rewrite** |
| Works if the clinic's internet drops | ❌ | ⚠️ ~1 h, then login fails | ✅ (if auth replaced) |
| Works if the clinic's power drops | ✅ | ❌ (unless UPS) | ❌ |
| Owner can check figures from home | ✅ | ⚠️ needs a VPN | ❌ |
| Double-booking guarantee holds | ✅ | ✅ | ❌ **(§4.4)** |
| You can fix it from another city | ✅ | ⚠️ | ✅ |
| Survives a dead disk | ✅ | ❌ backups only | ❌ backups only |
| Data physically in the clinic | ❌ (Mumbai/Bangalore) | ✅ | ✅ |
| Effort to build | ~6–8 h (already planned) | ~4 h | weeks |

---

## 10. What I would actually recommend

**Stay with the cloud plan for go-live — but not because local is a bad idea.**

The reasoning, honestly:

1. **The saving is real but small**, and it is not free — it converts ₹655/month into your time and
   a concentrated risk on one disk in a building you are not in.
2. **The single biggest advantage people expect from local — working without internet — does not
   exist** until the auth system is replaced (§5). Today, a local install still needs the internet to
   let anyone log in. That inverts the main argument for going local.
3. **You do not live in Davangere.** Cloud updates itself; a PC under the reception desk does not.
4. **The cloud plan is already researched, decided, and budgeted.** Switching now restarts Phase 7.

**But keep L1 in your pocket, because it is a genuinely good fallback**, and two things could make it
the right answer:

- **If the clinic's internet turns out to be as unreliable as `BUILD_PLAN.md` §11 fears**, the
  argument flips — but the fix is then *both* L1 **and** self-hosted auth (§5.2), and that is a real
  project. Worth measuring the connection during the parallel run before assuming it.
- **If ₹655/month genuinely matters**, L1 on the existing reception PC is a half-day of work and can
  be tried without giving anything up. **You could even run it as a rehearsal** — the same Docker
  Compose stack, on the LAN, with real staff, before paying for a droplet.

**A middle path worth considering later:** run L1 on the LAN as the working system, and replicate
nightly to a cheap cloud Postgres purely as an off-site backup. The clinic gets LAN speed and local
data; you get a copy that survives the building. That is ₹0–200/month and keeps the strongest
property of each — but it is more moving parts than the plain cloud deployment, so it should be
earned by a real problem, not adopted upfront.

---

## 11. If you decide to try L1, do it in this order

Not a plan — a checklist, so the option can be evaluated cheaply rather than committed to.

1. **Rebuild the frontend image** with `NEXT_PUBLIC_API_URL` pointing at the server's LAN address,
   and set `SITE_ADDRESS` + `CORS_ORIGINS` to match. Nothing works from a second machine until this
   is right, and the failure is confusing rather than obvious.
2. **Reserve a fixed IP** for the server PC on the clinic router, so the address never moves.
3. **Open the app from the dentist's PC** and run the whole clinic day: book, arrive, chairside,
   invoice, payment. `backend/scripts/e2e_check.py` covers the API; this is checking the *network*.
4. **Confirm Supabase login works over the LAN address**, not just `localhost`. This is the step most
   likely to surprise you.
5. **Set up the nightly dump + rclone off-box copy, then restore it once** into a scratch database
   and look at the rows. Do not skip this. It is the whole safety net.
6. **Decide about remote access** before you need it, not during an outage.
7. **Only then** consider a mini PC and a UPS — they remove the "someone turned it off" and "power
   cut" failure modes, and they are the difference between an experiment and something a clinic can
   rely on.

---

## Sources

Researched 2026-08-12. Prices and free-tier terms change — re-verify before acting.

- **Docker Desktop licensing:** [Docker Plans FAQ](https://www.docker.com/pricing/faq/) · [Docker subscription docs](https://github.com/jedevc/docker-docs/blob/master/subscription/index.md)
- **SQLite over network shares:** [SQLite — Use Over a Network](https://sqlite.org/useovernet.html) · [SQLite forum — locking on multi-user databases](https://sqlite.org/forum/info/a6675453ecd9af62d13d55fb38562a2e93c434c57f7994b34a4fae91506a3214)
- **Tauri + Python sidecar:** [Tauri v2 Python server sidecar example](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) · [Vue + Tauri + FastAPI template](https://github.com/AlanSynn/vue-tauri-fastapi-sidecar-template) · [Evil Martians — Rust + Tauri + sidecar](https://evilmartians.com/chronicles/making-desktop-apps-with-revved-up-potential-rust-tauri-sidecar)
- **Tauri auto-update:** [Tauri v2 Updater plugin](https://v2.tauri.app/plugin/updater/) · [self-hosted update server](https://github.com/HuakunShen/tauri-update-server)
- **Local-first sync:** [PowerSync — sync Postgres with SQLite](https://powersync.com/sync-postgres) · [ElectricSQL vs PowerSync](https://powersync.com/blog/electricsql-vs-powersync)
- **Postgres multi-master + conflict resolution:** [pgEdge — multi-master replication](https://www.pgedge.com/solutions/benefit/multi-master) · [pgEdge Spock](https://www.pgedge.com/blog/achieve-multiactive-data-replication-in-postgresql-with-spock) · [EDB PGD — conflicts](https://www.enterprisedb.com/docs/pgd/3.7/bdr/conflicts/)
- **Supabase Auth / JWT offline:** [Supabase — JWTs](https://supabase.com/docs/guides/auth/jwts) · [Supabase — JWT signing keys](https://supabase.com/docs/guides/auth/signing-keys)
- **Self-hosting Supabase:** [Supabase — self-hosting with Docker](https://supabase.com/docs/guides/self-hosting/docker) · [minimum requirements discussion](https://github.com/orgs/supabase/discussions/21132)
- **Lightweight self-hosted auth:** [Self-hosted auth solutions 2026](https://supertokens.com/blog/self-hosted-auth-solutions-in-2026) · [Best self-hosted SSO tools](https://selfhosting.sh/best/authentication-sso/)
- **Tailscale plans:** [Tailscale pricing](https://tailscale.com/pricing) · [free plans and discounts](https://tailscale.com/docs/account/manage-plans/free-plans-discounts)
- **Caddy local HTTPS:** [Caddy — Automatic HTTPS](https://caddyserver.com/docs/automatic-https) · [tls directive](https://caddyserver.com/docs/caddyfile/directives/tls)
- **Backups to free cloud storage:** [Automated PostgreSQL backups to Google Drive with rclone](https://theinfinity.dev/articles/postgresql-backup-rclone-guide) · [rclone on Windows Task Scheduler](https://jurgentreep.com/2020/09/24/how-to-schedule-a-task-for-rclone-in-windows/)
- **Mini PC power/cost:** [N100/N150 mini PC power consumption measurements](https://bishalkshah.com.np/blog/low-power-homelab-n100-mini-pc) · [Best mini PCs for home servers 2026](https://selfhosting.sh/hardware/best-mini-pc/)
- **On-premise vs cloud dental software:** [Curve Dental — cloud vs server FAQ](https://www.curvedental.com/blog/cloud-vs-server-dental-software-faq) · [Oryx — on-premise vs cloud](https://www.oryxdental.com/on-premise-vs-cloud-based-dental-practice-management/) · [Dentin Offline (India, offline-first)](https://dentinoffline.com/)

**Not verified by me:** every price and free-tier term above is as published on 2026-08-12 and was
not tested by signing up. The Tauri/PowerSync/Authelia capabilities are from documentation, not from
building with them. **Nothing in this document has been tried against this app** — including the L1
LAN setup, which is described from reading our own compose file and Caddyfile, not from running it on
a second machine.
