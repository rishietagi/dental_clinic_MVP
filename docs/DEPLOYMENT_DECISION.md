# DEPLOYMENT DECISION

**Step 7.2 — the decision.** Where this app will run, where its database will live, and what that
obliges us to build.

> **Decided 2026-08-12.** The single input is [`DEPLOYMENT_OPTIONS.md`](DEPLOYMENT_OPTIONS.md), the
> 7.1 research spike, **priced 2026-08-06**. This document decides; that one compares — read it for
> the sourcing behind any number here.
>
> ⚠️ **Prices below are 7.1's and were not re-checked today.** Cloud pricing moves (Hetzner raised
> prices mid-2026 and invalidated its own reputation). **Confirm the actual figure at the moment you
> put a card in — step 7.3 — not from this table.**

**Nothing here is built yet.** 7.2 is a decision, not an implementation. The prod compose file is
7.4, the domain is 7.5, the deploy pipeline is 7.6. The repo stays local-only until then.

---

## 1. The decision

| # | Question | Decision | ₹/month |
|---|---|---|---|
| 1 | **Stack** | **B** — DigitalOcean **Bangalore**, Basic **1 GB** droplet | **570** |
| 2 | **Postgres** | **Supabase Free**, **Mumbai** region — managed, as `CLAUDE.md` requires | **0** |
| 3 | **Residency** | **India-only**, app and database both | — |
| 4 | **Domain** | one `.in`/`.com`, registrar TBD in 7.5 (~₹1,000/yr) | **85** |
| 5 | **File storage** | **None.** Images stay manual; the 5.6 upload feature goes effectively unused | **0** |
| 6 | **Image builds** | **GitHub Actions**, pulled by the droplet — never built on the box | **0** |
| 7 | **Droplet backups** | **Declined** (DO's 20% add-on, ~₹114/mo) — the droplet is stateless | **0** |
| | | **Total** | **₹655** |

**Inside [`BUILD_PLAN.md`](BUILD_PLAN.md) §12's ₹500–1,200 estimate**, and fully India-resident.

**No rule is overridden by this.** The managed-Postgres requirement in `CLAUDE.md` is honoured;
auth stays Supabase; the tech stack table is unchanged. That is worth stating explicitly, because
the cheapest-looking option (self-hosting Postgres in the prod compose) *would* have required an
override — and it turned out to save nothing. See §4.

---

## 2. Why

In the order the reasons carry weight.

**1. At this clinic's real volume, capacity costs nothing.** 7.1 measured ~55 kB per visit against
the seeded demo clinic. At 3 patients/day (~75 visits/month) that is **~50 MB/year**, so a 500 MB
free tier is a **roughly ten-year decision**. Paying for database *size* here would be paying for
something we will not touch this decade. The free tiers are therefore ruled in or out by their
**backup and uptime terms only** — which is exactly what §3 is about.

**2. India residency is free — slightly negative, in fact.** DigitalOcean Bangalore at ₹570
*undercuts* Hetzner's ₹604, and Supabase's free tier includes a Mumbai region. The DPDP Act does
**not** mandate localisation (negative-list model, no list published; DISHA was never enacted), so
this is a prudential choice rather than a legal one — but when the more defensible option is also
the cheaper one, there is no trade-off left to make. It also avoids the thing that would actually
be expensive: migrating a live database of real patient records to India later, if a sector rule
ever lands.

**3. It consolidates on a vendor already in the system.** Supabase provides auth today. Choosing
Supabase for Postgres means one vendor, one region, one dashboard, and one place to rehearse a
restore — rather than a second account to reason about at 9am on a clinic day.

**4. It leaves the money that matters unspent.** The ₹2,375/month not going to Supabase Pro is
available the moment backups justify it, and that upgrade is **one click, not a migration** (§5).
Buying it now would be paying for a decade of headroom to avoid an obligation we have to be
capable of meeting anyway.

**5. The droplet holds nothing irreplaceable.** Postgres is Supabase's. Images are manual. So the
box is a pure compute layer, reproducible from git plus the prod compose file — which is what makes
declining DO's backup add-on reasonable rather than reckless.

---

## 3. What this choice obliges us to build

**This is the section that earns the ₹655.** Stack B is cheap because we take on work that Supabase
Pro would otherwise do. That work is real, it lands in Phase 8, and it is not a checkbox.

| Obligation | Where | Why it matters |
|---|---|---|
| Nightly `pg_dump`, compressed, retained N days | **8.2** | Supabase Free has **no managed backups**. Without this there is nothing to restore from. |
| **Off-box copy** of every dump | **8.2** | A dump on the same machine as the app is not a backup. Dumps are single-digit MB, so this is a ₹0–475/mo problem, not a real cost. |
| **Tested** restore + `docs/RUNBOOK.md` | **8.3** | **8.3 gates real patient data.** Untested backups are decoration. |
| Dead-man's-switch alert on the backup job | **8.1** | The actual failure mode of a hand-rolled cron is **silence** — it dies, nobody notices, and the discovery happens during the emergency. A job that must check in turns that into a Tuesday email. |
| Keep the Supabase project awake | **8.1** | Free projects **pause after ~1 week idle**. A clinic open six days a week is fine until Diwali or any week it shuts — then **nobody can sign in on Monday**, and this threatens *login* regardless of where Postgres lives. |

> **The pause mitigation is unverified.** The reasoning is that the UptimeRobot monitor already
> planned for 8.1, pointed at an endpoint that touches the database, counts as activity. That is
> reasoning, not a tested fact. **Verify it in 7.3** — do not discover it during a holiday.

**Also carried:** the droplet is a hand-configured machine we have chosen not to snapshot. That is
only true while it stays stateless. If anything durable ever lands on its disk — files, a local
Postgres, uploaded documents — **the backup decision in §1 row 7 is void** and must be re-taken.

---

## 4. What was rejected

One line each. The sourcing and the full argument are in
[`DEPLOYMENT_OPTIONS.md`](DEPLOYMENT_OPTIONS.md) — **do not re-litigate these from scratch.**

| Rejected | Why |
|---|---|
| **Stack A / Hetzner** (₹689) | No Indian datacenter at all, deviates from the managed-Postgres rule — **and it isn't even cheaper** than B. It has no remaining argument. |
| **Vercel** | 🚫 The **Hobby plan forbids commercial use**, and Vercel may pull a deployment **without notice** — the failure mode is the clinic going dark with no appeal. The 1M-request headroom was real (we need ~48k/mo); the *terms* are the blocker. Pro (~₹1,900) costs more than a droplet and still doesn't host the FastAPI backend. |
| **Neon** | No Mumbai region (Singapore is closest). Eliminated by residency before cost. |
| **PaaS** (Render/Railway/Fly) | They bill **per service** and this app is two plus a database, so every "$7/mo" headline is really ~$21. Only Fly has an Indian region. |
| **Self-hosted Postgres** | Saves **₹0** against Supabase Free while taking on backups, WAL archiving, restore testing and version upgrades — and the database would die with the droplet. It buys nothing but risk. |
| **Stack C** (₹3,600) | 5.5× stack B. The ₹2,375 buys **backups and uptime terms, not capacity** — and it stays one click away (§5). |
| **DO droplet backups** (₹114/mo) | The box is stateless (§2.5). Rebuildable from git + compose in about an hour. |
| **Cloud file storage** | Images are handled manually — the owner's call. `services/storage.py` isolates this behind a `Storage` protocol, so adopting it later is one class and a config change, **no call sites move**. |

---

## 5. Upgrade triggers

Written down so stack B is a **starting point, not a default that quietly rots**.

| Trigger | Action | Likelihood |
|---|---|---|
| The first time a `pg_dump` restore **fails a rehearsal** | → **Supabase Pro** (₹2,375/mo) | **The likely one.** Hand-rolled backup pipelines fail long before free tiers fill up. |
| Database passes **~350 MB** (70% of the free tier) | → **Supabase Pro** | ~year 7 at current volume. |
| The clinic shuts for **more than a week** (holidays), or a pause ever locks logins | → **Supabase Pro**, or a verified keep-awake monitor | Foreseeable — plan before the first long closure. |
| The box needs to **build images itself**, or Postgres comes back on-box | → **droplet 2 GB** (₹1,140/mo) | Avoidable by keeping builds in CI. |
| Anything durable lands on the **droplet's disk** | → re-take the droplet-backup decision (§3) | Only if file uploads start being used. |

Upgrading Supabase Free → Pro is a **plan change on an existing project**, not a data migration.
That is the property that makes deferring it safe.

---

## 6. Action items this creates

For **7.3** (provision), unless noted.

- [ ] **Find out which region the existing Supabase Auth project is in.** 7.1 §6 flagged this as
      unknown and it is the one open fact in the decision.
- [ ] **If it is not Mumbai, recreate it there — before go-live.** Decided in 7.2. It is nearly
      free today: prod starts with an empty database, there are 2 logins, and the local dev DB is
      disposable. It is expensive once real patient records exist.
      > **The wrinkle:** `staff_user.id` **is** the Supabase Auth user's UUID (the JWT `sub`) — see
      > [`LOG.md`](LOG.md) standing decisions. Recreating the auth project therefore changes the
      > admin's primary key, orphaning any row that references it. Harmless now, for exactly the
      > reasons above, and **precisely why this must happen before any real data exists.**
- [ ] **Create THREE login users, not one** (added by step 6.12): receptionist, dentist and admin.
      Create them in the Supabase dashboard, then copy each UUID into `.env`
      (`ADMIN_*` / `DENTIST_*` / `RECEPTION_*`) and run `python -m app.seed`, which upserts all
      three `staff_user` rows. The admin holds `["dentist","admin"]` — one login, both roles.
      **Only the admin account sees the practice's money** (Reports + today's collections).
- [ ] **Provision Supabase Postgres in Mumbai** and confirm the free tier's stated limits at signup —
      a pricing page and a signup flow do not always agree.
- [ ] **Verify the keep-awake mitigation** (§3) rather than assuming it.
- [ ] **Re-confirm every price before paying.** These are 2026-08-06 figures.
- [ ] *(7.4)* Prod compose must **pull** images built in GitHub Actions. A 1 GB box **will OOM** on
      `npm run build` — 7.1 names this the single most likely "why did my cheap VPS fall over"
      surprise, and it strikes at deploy time, not runtime.

---

## 7. What would reopen this decision

- **File uploads start being used in earnest** — X-rays or routine document scans. That reverses the
  ₹0 storage line, needs a cloud `Storage` implementation, and voids the droplet-backup decision.
- **A published DPDP negative list**, or any health-sector notification that mandates localisation.
  Today's residency choice already complies, so this would only *confirm* it — the point is that the
  reasoning in §2.2 is dated and rests on no list existing.
- **A second clinic, or materially more than 3 patients/day.** Every number here descends from that
  one figure. 7.1's lesson was that **the sizing assumption, not the price list, did all the work** —
  if the volume changes, re-cost before re-architecting.
- **A failed restore rehearsal** — see §5. Not a reopening of the stack so much as the trigger the
  stack was chosen with.

---

## 8. Honesty notes

- **Nothing in this document was empirically verified today.** It is a decision built on 7.1's
  sourced, dated research. The arithmetic was re-checked (₹570 + ₹0 + ₹85 = ₹655); the prices were
  not re-read.
- **The weak point of this choice is backups**, and it is a real one, not a formality. §3 is the
  honest price of the ₹655 and 8.3 will not let real patient data in until that work is done and
  rehearsed.
- **The Supabase Auth region is unknown as of this decision.** Everything else in §1 is settled.
