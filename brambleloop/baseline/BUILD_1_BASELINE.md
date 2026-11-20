# Build 1 baseline — recoverable checkpoint

**Accepted as complete by the owner on 2026-09-18.** This directory is the recovery point for
Build 1 of Master Plan v1.2. Everything in it was measured against the running system, not
asserted.

Nothing here was published. No owner action was performed. No integration was connected, no
phase was changed, no advertising was bought and no customer activity was created. Every
production call made while assembling this baseline was a `GET`.

---

## The commit

| | |
|---|---|
| **Baseline commit** | `d5168c0cea93dde23f06592a36c5a253533b83e5` |
| **Remote branch** | `build-1-baseline` — pushed, verified present on `origin` |
| **Local annotated tag** | `build-1` (see *Tags* below — the tag is local only) |
| **Development branch** | `claude/repository-setup-nc9x6o` |
| **Repository** | `StateFarm91/Project-Money` |

### What production is actually running

Production serves `94a4ad09e3f5f52a92642587b79f24003590e522`, not `d5168c0`. Railway deploys
on push and the heartbeat's closing commit landed after the verification.

**There is no code difference.** `d5168c0..94a4ad0` touches exactly two files —
`brambleloop/BUILD_STATE.md` and `ops/LOCK` — and the source and test trees are byte
identical:

```
brambleloop/src    d5168c0 and 94a4ad0 both 3b04b990f890a085d3569b4ef78ba8a3c1f961d5
brambleloop/tests  d5168c0 and 94a4ad0 both 6b71e63498fd7f17fdca851298d5e4d25a8a65b9
```

Recovering `d5168c0` therefore restores exactly the code that was production-verified. If you
also want the closing record, recover `94a4ad0`; the running behaviour is the same.

### Tags

`git tag -a build-1` exists **locally only**. This environment's git transport rejects tag
pushes — `send-pack: unexpected disconnect` on four attempts with backoff, while branch and
commit pushes to the same remote succeed — and the GitHub API available here exposes no
ref-creation call. The durable remote checkpoint is therefore the **branch**
`build-1-baseline`, which is confirmed on `origin` at the right SHA.

To recreate the tag anywhere with normal git access:

```bash
git tag -a build-1 d5168c0cea93dde23f06592a36c5a253533b83e5
git push origin build-1
```

---

## Test evidence

| | |
|---|---|
| **Result** | **541 passing, 0 failing**, 26 suites |
| **Command** | `cd brambleloop && bash run_tests.sh` |
| **Measured at** | `d5168c0` |
| **Runtime** | ~350s (files run concurrently; `JOBS=1` forces the old sequential behaviour) |

23 of those tests assert the owner's acceptance gates line by line. All six gates (A–F) pass.

Recoverability is proved rather than claimed: the suite is re-run from a **clean worktree
checked out at `d5168c0`**, and `recovery_test_evidence.txt` in this directory is that run's
output. If that file is absent, the proof was not completed and this baseline should be
treated as unverified until it is.

---

## Decisions

`brambleloop/DECISION_LOG.md` at this commit holds **B-001 through B-099**, 99 rows, each with
the reasoning and whether a test pins it. They are not re-decidable without the owner.

---

## Coverage map

`brambleloop/BUILD_STATE.md` carries a section-by-section map of Master Plan v1.2 — sections
1–17 and 25–36, with no 18–24 in the plan — recording for each what exists and what any unmet
item waits on. Nothing in it waits on Claude.

---

## Database migration state

`schema.json` in this directory.

There is no migration directory to preserve. `Database.create_all()` derives the schema from
the models and is additive: it creates missing tables and adds missing columns and indexes,
returns what it changed so startup can audit it, and refuses a NOT NULL column with no default
rather than guessing a backfill. **The models at this commit are the migration state.**

| | |
|---|---|
| Tables | 21 |
| Columns | 201 |
| `schema_sha256` | `47f40fe398f4d447bdb48f14d01380610f60f76e585dc11ecc6968340d7b71c5` |

A future session can regenerate that hash from its own models and diff it against this file to
see exactly what a change did to the schema.

### What is *not* preserved here — read this before relying on the baseline

**The production Postgres contents are not backed up in this repository, and cannot be from
this environment.** Taking a dump needs `DATABASE_URL`, which is a secret held by Railway and
must never enter this repository. `core/backup.py` implements a backup plus a tested restore
drill, but nothing exposes it over the API, so it can only run where the credential already
is.

What that means concretely:

- **Re-derivable.** Products, pattern versions, certificates, listings, listing images,
  content pieces and collections are all regenerated from code by `plan.cycle` and
  `chain.rebuild`. Losing them costs compute, not information.
- **Not re-derivable.** The audit log, the job history, the owner-action queue and any
  recorded physical test are records of what happened. They cannot be rebuilt from code.

If durable history matters before Build 2 begins, the cheapest honest options are a Railway
Postgres backup taken by the owner, or exposing `core/backup.py` behind an authenticated
endpoint. Neither has been done, and this file says so rather than implying a completeness
that does not exist.

---

## Production configuration

Read from Railway at baseline time. **Names only — no values.** Never store secrets in this
repository.

| | |
|---|---|
| Project | `brambleloop` — `0d61d9ec-76ca-42e3-aa69-918728845b29` |
| Environment | `production` — `d618b2fe-70ec-4541-852f-0b656c2eedaf` |
| Service | `brambleloop-os` — `c14774b3-0df2-409e-9721-fd7045099c53` |
| Database | `Postgres` — `c40c71a5-5653-4c2e-9417-3fc0ffbf209e` |
| Domain | `brambleloop-os-production.up.railway.app` |
| Source | `StateFarm91/Project-Money`, branch `claude/repository-setup-nc9x6o`, root `brambleloop` |
| Builder | `RAILPACK`, build environment `V3`, runtime `V2` |
| Healthcheck | `/health` |
| Replicas | 1, `us-west2` |

Environment variables set on the service, by name:

```
BRAMBLELOOP_ARTIFACT_DIR
BRAMBLELOOP_EMBEDDED_WORKER
BRAMBLELOOP_PHASE            <- must remain "shadow"
BRAMBLELOOP_REQUIRE_POSTGRES
BRAMBLELOOP_RUNNER_START_DELAY
BRAMBLELOOP_SCHEDULER_INTERVAL
DATABASE_URL                 <- secret, held by Railway
PORT
```

There is also a stray service `Project-Money`
(`4dff24df-2186-4278-b01f-c11ec39a766f`) in the same project. It is not part of the system;
its deletion is owner housekeeping and has been declined from this session three times, which
is the correct default for an irreversible action.

---

## Production state at baseline

Full capture in `production_evidence.json`. Summary:

| | |
|---|---|
| `/api/verify` | **12 of 12 checks passing** |
| `/api/launch` | **`blocked on build: NONE`**; 8 of 16 requirements met |
| Remaining | 7 owner actions + 1 Etsy credential only the shop can produce |
| Certified patterns | 15 |
| Listings | 16, **all on chain 7** |
| Listing images | 94, all approved |
| Content pieces | 134 · Collections | 1 |
| Published | **0**, against **120** recorded publication refusals |
| Revenue / customers / orders | CA$0 / 0 / 0 |
| Advertising / model spend | CA$0 / CA$0, no provider configured |
| Open incidents | 0 |
| Chain / doc version | `CHAIN_VERSION` 7, `DOC_VERSION` 2 |
| Infrastructure cost | ~CA$7/month against the owner's CA$20 ceiling |

---

## Recovering this baseline

```bash
# The code, from the durable remote checkpoint
git fetch origin build-1-baseline
git checkout -b recovered-build-1 origin/build-1-baseline
git rev-parse HEAD        # must be d5168c0cea93dde23f06592a36c5a253533b83e5

# Prove it before trusting it
cd brambleloop && bash run_tests.sh        # expect: TOTAL PASSING: 541 ; suites failing: 0

# Confirm the schema matches what this baseline recorded
#   regenerate from the models and diff against baseline/schema.json

# To put it back in production, point the Railway service's branch at the recovered
# branch, or reset the development branch to this commit and push. The service deploys on
# push; /api/status reports the commit it is serving, so the deploy is checkable rather
# than inferred.
```

**Restoring the code does not restore the database.** See *What is not preserved* above.

---

## Standing constraints, unchanged by this baseline

- `BRAMBLELOOP_PHASE` stays `shadow`. Only the owner moves it.
- Do not publish to Etsy, message real customers, perform KYC or legal acceptance, connect
  banking, or incur consequential spend. Recurring infrastructure ceiling CA$20/month.
- Patterns are software releases: deterministic validation, never a model guessing
  instructions.
- Never claim an integration, deployment, pattern, listing, test, campaign, customer or
  revenue exists until verified.
- No fake reviews, buyers, favourites, sock-puppets, deceptive discounts or fabricated
  engagement, including our own metrics.
- Never copy competitor instructions, charts, photography or protected designs.
- Never store secrets in this repository.
