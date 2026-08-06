# DEPLOYMENT OPTIONS

**Step 7.1 — the research spike.** What it costs, in ₹, to put this app in front of a real clinic,
and what each option costs in *effort* once it is there.

**This document does not decide anything.** It compares. The decision is step 7.2, and the last
section lists exactly what 7.2 has to answer. A recommendation is offered at the end, clearly
marked as one input to that decision.

> **Priced 2026-08-06.** Every ₹ figure below traces to a source link and was read on that date.
> Cloud pricing moves — Hetzner raised cloud prices on 15 June 2026 and the old "Hetzner is
> absurdly cheap" reputation is already out of date. **Re-check the actual figure at the moment
> you put a card in (step 7.3), not from this table.**

**Conversion used throughout:** **$1 = ₹95** and **€1 = ₹110** (USD/INR 95.24 and EUR/INR 109.91 on
2026-08-06 — [Fed H.10](https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm),
[exchangerates.org.uk](https://www.exchangerates.org.uk/EUR-INR-spot-exchange-rates-history-2026.html)).
Rounded to whole rupees. Taxes (GST on Indian billing, EU VAT on Hetzner) are **not** included.

---

## 0. Two owner inputs that changed this document

Both arrived from the clinic owner while this was being written, and both **shrink the problem
considerably**. They are recorded here because they invalidate the assumptions most hosting advice
(and the first draft of this file) is built on.

1. **X-rays and images will NOT be stored in the cloud.** The clinic will keep them manually, as
   they do today. **The entire "where do the file bytes live" cost line drops to ₹0.**
2. **The clinic sees about 3 patients a day, with 2 logins** (receptionist and dentist) — not the
   ~20/day a general-purpose estimate would assume.

The second number is the important one. It is roughly **6× smaller** than a typical small-clinic
assumption, and it moves the free database tiers from *"a 12–18 month decision"* to *"a decision
that lasts about a decade"* (§1). **Most of the money in this document is compute, and there is not
much of it.**

> **One thing for 7.2 to confirm, not assume:** the app still *has* the 5.6 upload feature
> (`patient_file`, the Files tab). "Handled manually" may mean the feature simply goes unused, or
> that the occasional scanned document still gets attached. Either way the code stays and the local
> disk covers it — but it is worth being explicit rather than discovering it later.

---

## 1. What we are actually hosting

Every number in this section was **measured on the running dev stack on 2026-08-06**, not estimated.
This matters: almost every "which VPS should I buy" article assumes a heavier app than this one.

### Footprint

The stack is four containers ([docker-compose.yml](../docker-compose.yml)): Caddy → a Next.js
standalone server + a uvicorn/FastAPI backend, plus Postgres.

| Container | RAM at idle | Image size |
|---|---|---|
| caddy (`caddy:2-alpine`) | 12.4 MB | 88.7 MB |
| frontend (Next standalone, `node:24-alpine`) | 48.0 MB | 288 MB |
| backend (uvicorn, `python:3.12-slim`) | 108.6 MB | 343 MB |
| db (`postgres:16-alpine`) | 32.4 MB | 420 MB |
| **Total** | **≈ 201 MB** | **≈ 1.14 GB** |

**201 MB at idle for the whole stack including the database** — and only ~169 MB if Postgres moves
to a managed host. Load is 2 logins and 3 patients a day. This will never be CPU-bound. **A 1 GB box
is genuinely sufficient**, not a compromise.

> **The one caveat that decides box size:** `npm run build` for Next.js is far heavier than running
> it and **will OOM on a 1 GB machine**. Build images in GitHub Actions and pull them — CI already
> exists ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) — or add swap. This is the single
> most likely "why did my cheap VPS fall over" surprise, and it happens at deploy time, not runtime.

### Data growth, at 3 patients/day

Measured against the seeded demo clinic (47 patients · 46 visits · 41 invoices · 79 invoice lines ·
75 procedures · 41 tooth conditions):

- **User data: 2,552 kB.** An empty Postgres database is 7,519 kB of catalogues before any of ours.
- Normalising on the thing that recurs: **≈ 55 kB per visit**, including its invoice, lines,
  procedures and chart rows.

At **3 patients/day × ~25 days = 75 visits/month**:

| Horizon | Database | Against a 500 MB free tier |
|---|---|---|
| Year 1 | ~50 MB | 10% used |
| Year 3 | ~150 MB | 30% used |
| Year 5 | ~250 MB | 50% used |
| Year 10 | ~500 MB | the limit, finally |

> 55 kB/visit is measured at small scale where Postgres page and index overhead dominates, so these
> are **conservative (over-stated)**. Treat them as a ceiling.

**This is the headline finding: a 500 MB free Postgres tier is roughly a ten-year decision at this
clinic's volume.** Capacity is simply not a constraint. That reframes the whole comparison — the
free tiers are ruled in or out by their *backup and uptime terms*, never by their size.

### Request volume

2 staff, 3 patients/day. Even generously — say each login makes ~800 page and API requests a day —
that is **~48,000 requests/month**. Every platform limit surveyed here is 20× that or more.
**Request volume is a non-issue and should carry no weight in the decision.**

### Files

**₹0.** Images are handled manually (§0). Whatever incidental documents get attached fit in the
droplet's 25 GB disk many times over, via the existing `LocalStorage`.

---

## 2. The decisions, and the one that is already made

Two decisions now (the third collapsed when images left the cloud):

1. **Where the app runs** — VPS + Docker, or PaaS.
2. **Where Postgres lives** — managed, or self-hosted alongside the app.

**Auth is not a decision.** Supabase Auth is already wired and stays
([TECH_STACK.md](TECH_STACK.md)). But it has a consequence people miss — see §6.

**File storage is no longer a decision either**, and if that ever changes it is cheap to revisit:
`services/storage.py` isolates it behind a `Storage` protocol with a `LocalStorage` implementation
([storage.py:22](../backend/app/services/storage.py#L22)), so switching means writing one class with
three methods and changing config — **no call sites move**.

---

## 3. Where the app runs

### VPS + Docker

| Option | Spec | $/€ per month | ₹/month | India region? |
|---|---|---|---|---|
| [Hetzner CX23](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) | 2 vCPU · 4 GB · 40 GB NVMe · 20 TB traffic | €5.49 | **₹604** | ❌ **none** |
| [DigitalOcean Basic 1 GB](https://www.digitalocean.com/pricing/droplets) | 1 vCPU · 1 GB · 25 GB · 1 TB | $6 | **₹570** | ✅ Bangalore (BLR1) |
| [DigitalOcean Basic 2 GB](https://www.digitalocean.com/pricing/droplets) | 1 vCPU · 2 GB · 50 GB · 2 TB | $12 | **₹1,140** | ✅ Bangalore (BLR1) |
| [Lightsail 1 GB](https://aws.amazon.com/lightsail/pricing/) | 2 vCPU · 1 GB · 40 GB · 1 TB\* | $7 | **₹665** | ✅ Mumbai |
| [Lightsail 2 GB](https://aws.amazon.com/lightsail/pricing/) | 2 vCPU · 2 GB · 60 GB · 1.5 TB\* | $12 | **₹1,140** | ✅ Mumbai |

\* Mumbai bundles include **half** the advertised transfer allowance. Still ~1,000× our need.

**Hetzner is no longer the runaway winner.** The 15 June 2026 adjustment raised CX23 from €3.99 to
€5.49. At ₹604 it is still cheap — but **DigitalOcean's 1 GB droplet is ₹570, actually cheaper, and
in Bangalore.** Hetzner has no Indian datacenter at all (Germany, Finland, Singapore, USA), which is
what rules it out if §6 goes the residency way. **There is no longer a cost argument for going
offshore.**

**Effort, all VPS options alike:** ~6–10 hours setup (droplet, SSH hardening, Docker, prod compose,
Caddy + TLS, DNS, deploy) and **~1–2 hours/month** maintenance — OS patching, disk and backup checks;
Caddy renews certificates itself. This is the honest ops cost, and it is also the "learning" the
project is explicitly for.

**Restore story:** yours. Provider snapshots (DO backups are 20% of droplet cost, ~₹114/month on the
1 GB) restore the *whole machine* — coarse but real. A database restore means your own `pg_dump` on
cron plus a tested `psql` restore. **This is the work 8.3 gates real patient data on**, and on a VPS
nobody does it for you.

### PaaS

| Option | What we'd pay for | $/month | ₹/month | India region? |
|---|---|---|---|---|
| [Render](https://render.com/pricing) | 2 × Starter web ($7 ea) + Starter Postgres ($7) | $21 | **₹1,995** | ❌ (closest Singapore) |
| [Railway](https://www.srvrlss.io/provider/railway/) | Hobby $5 + usage @ $10/GB-RAM/mo | ~$5–10 | **₹475–950** | ❌ |
| [Fly.io](https://fly.io/docs/reference/regions/) | 2 × shared-cpu-1x 1 GB (~$5.70 ea) + Postgres | ~$17–20 | **₹1,615–1,900** | ✅ **Mumbai (`bom`)** |

> **The PaaS trap:** these platforms bill **per service**, and this app is **two** services
> (frontend + backend) plus a database. Every "$7/month" headline is really ~$21 here. Render's free
> tier does not rescue it — free web services **spin down after 15 minutes** (≈1 minute cold start,
> unacceptable at a front desk) and **free Postgres is deleted after 30 days.**

**Fly.io is the only PaaS with an Indian region.** Its India egress is $0.12/GB, the highest rate in
this document — but on our traffic that is a rupee or two.

**Effort:** ~2–4 hours setup, **~0–0.5 hours/month** maintenance. No OS to patch. For a solo
maintainer supporting his mother's clinic from another city, that is worth more than the table
suggests.

### Vercel — checked on request, and it is disqualified on terms

Vercel is where a Next.js app "should" go, and the free-tier headroom is real: **Hobby includes 1
million function invocations, 100 GB data transfer and 4 CPU-hours/month**
([Vercel limits](https://vercel.com/docs/limits)). Against our ~48,000 requests/month (§1) that is
roughly **20× more than needed**. On volume, the instinct is right.

**Three things stop it, in descending order of seriousness:**

1. **🚫 The Hobby plan forbids commercial use.** Vercel's terms restrict Hobby to "personal or
   non-commercial use", and define commercial usage as any deployment serving "the financial gain of
   anyone involved". **A dental practice running its patient and billing system is squarely
   commercial.** Vercel also reserves the right to "disable or remove any Project or website
   deployment on the Hobby plan with or without notice". The failure mode is not a bill — it is the
   clinic's patient records going dark on a Tuesday morning with no warning and no appeal.
   ([Terms of Service](https://vercel.com/legal/terms), [Fair Use Guidelines](https://vercel.com/docs/limits/fair-use-guidelines))
2. **It hosts half our app.** Vercel runs the Next.js frontend natively, but the backend is a
   containerised long-running **uvicorn/FastAPI** app with a SQLAlchemy engine and connection
   pooling, plus Alembic migrations. That does not lift into Vercel's serverless functions without
   a real rearchitecture — and it breaks the project's "local and prod differ by **config**, not
   architecture" rule. Realistically Vercel hosts the frontend and you **still pay to host the
   backend somewhere else**, so it adds a platform rather than replacing one.
3. **India residency needs Pro anyway.** The Mumbai region (`bom1`) exists but
   [regional pricing](https://vercel.com/docs/pricing/regional-pricing/bom1) makes it a Pro
   feature.

**Vercel Pro is $20/developer/month ≈ ₹1,900/month** — more than a Bangalore droplet that runs the
*entire* stack, while still leaving the backend homeless.

**Verdict: not recommended, and not because of the limits.** The 1M-request instinct was sound; the
terms of service are the blocker, and they are the kind you cannot engineer around. Worth knowing
definitively rather than wondering.

---

## 4. Where Postgres lives

| Option | Included | $/month | ₹/month | India region? | Backups |
|---|---|---|---|---|---|
| [Supabase Free](https://supabase.com/pricing) | 500 MB DB, 1 GB files, 5 GB egress | $0 | **₹0** | ✅ Mumbai | ❌ **none** |
| [Supabase Pro](https://supabase.com/pricing) | 8 GB DB, 100 GB files, 250 GB egress | $25 | **₹2,375** | ✅ Mumbai | ✅ 7-day |
| [Neon Free](https://neon.com/pricing) | 0.5 GB, 100 CU-hours | $0 | **₹0** | ❌ (Singapore) | 6-hour history |
| [Neon Launch](https://neon.com/pricing) | $0.35/GB-mo + $0.106/CU-hour | usage | ~₹400–900 | ❌ | 7-day |
| [DO Managed Postgres](https://www.digitalocean.com/pricing) | 1 GiB cluster | $15.15 | **₹1,439** | ✅ Bangalore | ✅ daily, 7-day |
| [RDS Mumbai `db.t4g.micro`](https://aws.amazon.com/rds/pricing/) | 2 vCPU · 1 GB + storage | ~$16.58 | **₹1,575** | ✅ Mumbai | ✅ configurable |
| **Self-hosted in prod compose** | on the app's own VPS | $0 | **₹0** | ✅ follows the VPS | ❌ **yours to build** |

**Three findings that matter more than the prices:**

1. **Neon has no Mumbai region** — Singapore is closest. With Hetzner, that is two of the roadmap's
   named candidates eliminated by residency before cost is even considered.
2. **Capacity is irrelevant here.** At ~50 MB/year (§1), the 500 MB free tiers last about a decade
   and the paid 8 GB tiers last centuries. **Nobody should pay for database size at this clinic.**
   The only things worth paying for are **backups** and **not being paused**.
3. **Supabase Free has no backups and pauses a project after one week of inactivity.** The pause is
   survivable for a clinic open six days a week — until Diwali or any week it shuts. The missing
   backups are the harder problem: 8.3 gates real patient data on a *tested restore*, and Free gives
   you nothing to restore from but your own `pg_dump`.

> ### ⚠️ Self-hosting Postgres deviates from the agreed stack
> `CLAUDE.md` specifies **managed** Postgres (Supabase/Neon). Running Postgres in the prod compose
> file is listed because a costing document that omits the obvious cheapest option is not honest —
> it is **₹0 marginal** and the container already exists.
>
> **It is not recommended, and 7.2 must accept or reject it explicitly rather than let it happen by
> default.** You would take on backups, WAL archiving, restore testing and version upgrades, and the
> database would die with the droplet. It is also the biggest ops-learning item in the project. The
> counter-argument is medico-legal, not technical: the data is real patients', and the failure mode
> is losing it. **Given Supabase Free is ₹0 and India-resident, self-hosting now buys nothing but
> risk** — it saves no money at all.

---

## 5. Where the file bytes live

**Decided by the owner: nowhere. Images stay manual (§0). ₹0/month.**

Retained for the record, in case that reverses: at any plausible volume this was going to cost
**₹40–475/month** (S3 Mumbai ~₹39, Lightsail object storage ~₹95, DO Spaces flat ₹475), i.e. less
than one droplet size step. It was never going to be the deciding number, and the `Storage` protocol
means adopting it later is one class plus config.

---

## 6. Data residency — costed both ways

A legal and prudential question, not a technical one, and worth deciding deliberately rather than
inheriting whatever region a signup form defaults to.

### What the law actually says

**The DPDP Act 2023 does not impose general data localisation.** Under §16 and Rule 15 of the DPDP
Rules 2025 (operationalised from 13 November 2025), cross-border transfer is **permitted by
default**, restricted only to countries the government places on a **negative list** — and no such
list has been published. ([Vidhi Legal Policy](https://vidhilegalpolicy.in/blog/cross-border-data-transfers-and-data-localization-mandate-under-the-data-protection-regime/),
[Lexology](https://www.lexology.com/library/detail.aspx?g=7bdb68c9-5e94-4c9d-8b81-9aa7a523d2eb))

Health-specific rules are thinner than they look. The **EHR Standards 2016** (MoHFW) are notified
*guidelines*. **DISHA**, which would have regulated storage of digital health data directly, was
**proposed and never enacted**. ([MoHFW EHR Standards](https://mohfw.gov.in/sites/default/files/17739294021483341357.pdf))

**So: keeping patient data outside India is not, today, unlawful for a private dental clinic.**

### Why you might still choose India

- Sector rules **can** override DPDP where stricter, and health data is the likeliest candidate for
  a future notification. A negative list can appear with little notice, and migrating a live
  database of real patient records costs far more than choosing the region once.
- DPDP treats health data as sensitive and expects a defensible answer to "where is it?".
- Latency: Davangere → Bangalore/Mumbai is ~20–40 ms; → Frankfurt is ~150 ms+. Small, but felt all
  day in a form-heavy app.
- It is simply easier to explain to a patient, a regulator, or an insurer.

### The price of choosing India

| | Cheapest global | Cheapest India-resident | Difference |
|---|---|---|---|
| Compute | Hetzner CX23 — ₹604 | **DO 1 GB Bangalore — ₹570** | **−₹34** |
| Postgres | Neon Free — ₹0 | **Supabase Free Mumbai — ₹0** | **₹0** |
| Files | ₹0 (manual) | ₹0 (manual) | ₹0 |

**The residency premium is now zero — in fact it is slightly negative.** The India-resident option
is cheaper than the offshore one on compute, and identical (free) on the database.

This is a direct consequence of the two owner inputs in §0. In the first draft of this document —
written before the 3-patients/day figure and the manual-images decision — residency cost about
₹1,500–2,000/month, because the volume assumption pushed past the free database tiers and forced
Supabase Pro. At the real volume that pressure disappears, and with it the entire argument for going
offshore. **There is no longer a trade-off to make here.**

### The Supabase Auth consequence

Supabase Auth is **already** in production use and already holds staff emails and password hashes in
whatever region that project was created in. Two consequences for 7.2:

- **Check which region the existing Supabase project is in.** If it is not Mumbai, part of the
  system is already offshore. (It holds staff credentials, not patient records — a much lower stake
  — but "where is our data?" should have one answer, not two.)
- **The free-tier pause already threatens login.** If that project idles a week and pauses, **nobody
  can sign in on Monday** — regardless of where Postgres lives. That risk exists today and is
  independent of every other choice here. A likely cheap mitigation: **UptimeRobot is already
  planned for 8.1**, and a monitor hitting an endpoint that touches the database should keep the
  project active. *Verify this actually counts as activity before relying on it.*

---

## 7. Three assembled stacks, end to end

Domain included at **₹85/month** (~₹1,000/year). GST excluded.

### A — Cheapest, offshore · **₹689/month**

Hetzner CX23 (₹604) + Postgres self-hosted in prod compose (₹0) + domain (₹85).

- ✅ Most ops learning; everything in one place.
- ❌ **No Indian region exists on Hetzner.** ❌ Deviates from the managed-Postgres rule. ❌ Restore
  is entirely hand-built. ❌ One machine is a single point of failure for both app and database.
- ❌ **And it is not even the cheapest** — stack B beats it on price *and* residency.
- Setup ~8–12 h · maintenance ~2 h/month.

### B — India-resident, free database · **₹655/month** ⭐

DigitalOcean Bangalore **1 GB** (₹570) + **Supabase Free (Mumbai)** for Postgres (₹0) + domain (₹85).
Images manual (₹0).

- ✅ **Cheapest option in this document**, and fully India-resident. ✅ Honours the managed-Postgres
  rule. ✅ 500 MB lasts ~10 years at 3 patients/day. ✅ Same vendor and region as the auth already in
  use. ✅ Comfortably inside [BUILD_PLAN.md §12](BUILD_PLAN.md)'s ₹500–1,200 estimate.
- ❌ **No managed backups** — nightly `pg_dump` is yours to write and, per 8.3, to test.
  ❌ Pause-after-a-week risk (see §6 for the UptimeRobot mitigation). ❌ 1 GB means builds must run
  in CI, not on the box.
- Setup ~6–8 h · maintenance ~1 h/month.

### C — India-resident, managed backups · **₹3,600/month**

DigitalOcean Bangalore 2 GB (₹1,140) + **Supabase Pro (Mumbai)** (₹2,375) + domain (₹85).

- ✅ Everything B has, plus 7-day managed backups, no pause risk, and generous headroom.
- ❌ **5.5× stack B for capacity that will not be touched for a decade.** The ₹2,375 buys backups
  and uptime terms, *not* size — worth being clear-eyed that this is what is being purchased.
- Setup ~6–8 h · maintenance ~1 h/month.

### Against the original estimate

[BUILD_PLAN.md §12](BUILD_PLAN.md) budgeted **~₹500–1,200/month**. **Verdict: it holds.** Stack B
lands at ₹655, inside the range, while being India-resident and on managed Postgres — an outcome the
estimate did not obviously expect. Only the fully-managed-backups path (C) breaks it, and that is a
deliberate purchase rather than a floor. **No change to §12 is needed**, though it is worth adding a
line that managed backups roughly quintuple the bill.

---

## 8. Recommendation — input to 7.2, not the decision

**Recommended: Stack B — DigitalOcean Bangalore 1 GB droplet + Supabase Free (Mumbai), ~₹655/month.**

Reasoning, in the order I weight it:

1. **At this clinic's real volume, capacity costs nothing.** 75 visits/month against a 500 MB tier is
   a ten-year runway (§1). Paying for database size here would be paying for nothing.
2. **India residency is free** — DigitalOcean Bangalore undercuts Hetzner, and Supabase's Mumbai
   region is on the free tier. When the compliant option is also the cheapest, take it; the
   alternative is a migration of live patient records later.
3. **It consolidates on Supabase, which is already in the system** as the auth provider. One vendor,
   one region, one dashboard, one place to rehearse a restore.
4. **It leaves the budget intact for the thing that actually matters.** The ₹2,375/month not spent on
   Supabase Pro is available the moment backups justify it — and that is a one-click upgrade, not a
   migration.

**Two explicit upgrade triggers to write into 7.2**, so this is a starting point rather than a
decision that quietly rots:

- **Upgrade to Supabase Pro when** the database passes ~350 MB (≈70% of the free tier, roughly year
  7), **or** the first time a hand-rolled `pg_dump` restore fails a rehearsal — whichever comes
  first. The second is far likelier than the first.
- **Upgrade the droplet to 2 GB when** the box actually needs to build images itself, or if Postgres
  is ever brought back on-box.

**What I would not do:**

- **Do not run stack A.** It is offshore, deviates from the managed-Postgres rule, and — now that the
  volume is known — is *more expensive* than stack B. It has no remaining argument.
- **Do not use Vercel** (§3). The free-tier headroom is genuinely there, but the Hobby plan forbids
  commercial use and Vercel can pull a deployment without notice. That is not a risk to take with a
  clinic's records, and Pro costs more than a droplet while still not hosting the backend.
- **Do not self-host Postgres.** It saves ₹0 against Supabase Free and adds every backup and upgrade
  obligation to your own plate.
- **Do not buy a bigger droplet or any object storage.** 169 MB idle without Postgres, and images
  are manual.

**The honest caveat:** stack B's weak point is backups, and Phase 8.3 will not let real patient data
in until a restore has been rehearsed. Budget the work — a nightly `pg_dump`, an off-box copy, and a
tested restore — as **real work in Phase 8, not a checkbox**. That is the price of the ₹655.

---

## 9. What step 7.2 must decide

- [ ] **Residency** — India-only, or is offshore acceptable? *(On these numbers India is free, so
      this should be quick.)*
- [ ] **Which stack** — A, B, C, or a mix.
- [ ] **Managed vs self-hosted Postgres** — and if self-hosted, an **explicit** override of the
      `CLAUDE.md` managed-Postgres rule, recorded in the LOG as a standing decision.
- [ ] **Where the existing Supabase Auth project lives**, and whether to move or upgrade it.
- [ ] **Confirm the file-upload feature's fate** (§0) — unused, or still used for the occasional
      scanned document? Decides whether `LocalStorage` needs any attention at all in Phase 7.
- [ ] **Where images get built** — GitHub Actions (recommended; CI exists) or on the box. A 1 GB box
      cannot run `npm run build`.
- [ ] **Record the upgrade triggers** (§8) so stack B is a starting point, not a permanent default.

---

## Sources

Priced 2026-08-06.

- [Hetzner — price adjustment 15 June 2026](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) · [Hetzner Cloud](https://www.hetzner.com/cloud/) · [new CX plans](https://www.hetzner.com/pressroom/new-cx-plans/)
- [DigitalOcean — Droplet pricing](https://www.digitalocean.com/pricing/droplets) · [Spaces pricing](https://www.digitalocean.com/pricing/spaces-object-storage) · [Spaces in Bangalore](https://www.digitalocean.com/blog/spaces-blr) · [regional availability](https://docs.digitalocean.com/platform/regional-availability/)
- [AWS Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) · [RDS pricing](https://aws.amazon.com/rds/pricing/) · [S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Render pricing](https://render.com/pricing) · [Render regions](https://render.com/docs/regions)
- [Railway pricing](https://www.srvrlss.io/provider/railway/) · [Fly.io regions](https://fly.io/docs/reference/regions/)
- [Vercel limits](https://vercel.com/docs/limits) · [Vercel Terms of Service](https://vercel.com/legal/terms) · [Fair Use Guidelines](https://vercel.com/docs/limits/fair-use-guidelines) · [Hobby plan](https://vercel.com/docs/plans/hobby) · [bom1 regional pricing](https://vercel.com/docs/pricing/regional-pricing/bom1)
- [Supabase pricing](https://supabase.com/pricing) · [Supabase regions](https://supabase.com/docs/guides/platform/regions)
- [Neon pricing](https://neon.com/pricing) · [Neon regions](https://neon.com/docs/introduction/regions)
- DPDP: [Vidhi Legal Policy](https://vidhilegalpolicy.in/blog/cross-border-data-transfers-and-data-localization-mandate-under-the-data-protection-regime/) · [Lexology — localisation and cross-border transfers](https://www.lexology.com/library/detail.aspx?g=7bdb68c9-5e94-4c9d-8b81-9aa7a523d2eb) · [MoHFW EHR Standards 2016](https://mohfw.gov.in/sites/default/files/17739294021483341357.pdf)
- FX: [Federal Reserve H.10](https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm) · [exchangerates.org.uk EUR/INR](https://www.exchangerates.org.uk/EUR-INR-spot-exchange-rates-history-2026.html)

**Not verified by me:** prices are as published on the pages above on 2026-08-06. Free-tier terms,
regional availability and per-service billing rules change, and signup can surface limits a pricing
page does not. Fly.io's managed-Postgres line is the least certain figure here (quoted as a range),
and the UptimeRobot-keeps-Supabase-awake mitigation in §6 is reasoning, not something I tested. Good
enough to *decide* on in 7.2 — **confirm the exact figures in 7.3, before paying.**
