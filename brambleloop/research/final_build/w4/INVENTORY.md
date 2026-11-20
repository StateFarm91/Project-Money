# W5-INVENTORY: exact product inventory, flow health and the Production view

Branch `claude/w5-INVENTORY` (from `claude/w4-INTEG8-next` b0133916).

## What was built

| Piece | File |
|---|---|
| Inventory state machine (derived, no stored status) | `src/brambleloop/products/production_inventory.py` |
| Flow health, department activity and next work | `src/brambleloop/ops/flow_health.py` |
| Command Center Production provider | `src/brambleloop/app/command_center/production.py` |
| Route `GET /api/cc/production` (owner session, read-only) | `src/brambleloop/app/command_center/api.py` |
| SPA view, tab, API client, service-worker shell (v28) | `static/js/views/production.js`, `routes.js`, `api.js`, `sw.js` |
| Retention decision for `pricing.refused` | `src/brambleloop/ops/retention.py` |
| Tests | `tests/test_w5_inventory.py` |

The existing `products/inventory.py` (W4-PIPE, a repo-static inventory) and `products/lifecycle.py`
(F-672, a coarse stage enum) are left alone. This module is the owner's 15-state inventory,
computed from the database.

## State derivation rules

Each product/version row is evaluated top-down. The first rule that decides wins, so every row
has exactly one state. A row is every `(slug, version)` on `PatternVersion`, `Listing`,
`PhysicalTest` or a versioned job, plus one versionless row for a slug with none. Unversioned
jobs (`radar.score`, `cir.draft`) attach to the slug's newest version.

1. **Published**: `Listing.state` is one of `published`, `active` or `published_manually` (the W-ADOPT state).
2. **Rejected (owner)**: an active owner veto (`intel.mission_runtime.active_veto`).
3. **Research candidate / Rejected (research)**: there is no build record (no `cir.draft`,
   `cir.revise`, `cir.compile`, `PatternVersion` or `Listing`). If the latest `radar.score`
   was not promoted, a pre-engineering gate `waiting` keeps it a candidate with a policy hold;
   otherwise it is Rejected with the gate's reason. A retired concept alias is also Rejected.
4. **Research approved**: `radar.score` promoted, or any build record exists, but no draft has been queued.
5. **Pattern in development**: a CIR draft exists and no `cir.compile` has completed.
6. **Pattern technically validated**: the latest `cir.compile` returned `compiled: true`, and
   the version is not yet certified. `compiled: false` gives **Revision required**. A
   `gate.certify` halted by an incident is a policy hold.
7. **Independent review passed**: `PatternVersion.certified` with a `release_hash`. The
   certificate includes the independent reverse-compile in US and UK terms. **Revision
   required** if a `quality.reverified` `cir.twin` or `cir.reverse` check on this release
   failed, or the withholding record blocks the build (teardown QA).
8. **Premium PDF completed**: `runtime.pipeline._certified_pdf_hashes(slug, version, release)`
   returns hashes. This is the reader `store.publish` uses, so a PDF from another release does not count.
9. **Visual package completed**: the newest `assets.listing_images_built` from this release's
   build. `assets.listing_images_blocked` gives **Revision required**.
10. **Listing package completed**: the newest `listing.seo_drafted` and a `Listing` bound to this
    release. `listing.seo_blocked` or a `withdrawn` listing gives **Revision required**.
11. **Owner approval pending**: every product gate passes, the physical sample is passed or not
    required, but the phase or the owner's grant refuses.
12. **Ready for publication**: every required gate passes (below).
13. **Revision required** and **Rejected**: as above. A row that throws during derivation is
    Revision required with `derivation_error`. It is never dropped and never shown as healthy.

### Physical sample: an attribute, not a step (owner clarification, 2026-10-27)

`physical_sample.status` is one of `not_required`, `pending`, `passed`, `failed` or `unknown`
(unknown means not yet certified). It is recorded beside the furthest internal state:

- **Internal** work is never blocked by a missing sample photo. That covers development,
  validation, review, the PDF, visuals and the listing package.
- **Private Etsy draft** (`tiers.private_draft`) needs the product gates, the phase and the
  owner's draft grant. It does not need a sample.
- **Public publication** (`tiers.public`) needs everything above, plus the sample where the
  certificate requires one.

A product awaiting its sample stays at "Listing package completed" with a `physical` hold. It
is never "Owner approval pending" or "Ready for publication", and it never counts toward them.
"Physical sample pending/passed" are tallied from the attribute (`physical_counts`) and shown
beside the state counts. A sample that was made and **failed** is Revision required.

### Ready for publication: the gate functions publication uses, never re-implemented

All of these must hold:

1. **Product gates**:
   - `recorded` mode (the default; read-only; used by the CC view): the newest
     `store.release_gates` verdict, which is the stored output of
     `release_gates.for_publish` from `store.publish`, and the newest `listing.parity`
     verdict (`_listing_parity`). Both must come from the same `store.publish` job for this
     version, with no historical `as_of`. They must be younger than 24 h and newer than the
     product's last completed chain job. Otherwise the result is UNKNOWN.
   - `live` mode: `for_publish(read_only=True)`, which is exactly `store.publish`'s
     `_release_gates`, plus `publication_authority._parity` (the same assessment without
     escalations) and `refuse_if_experiment`. This mode can write certificate rows (as
     `store.publish` does), so the CC view never uses it.
2. No `DraftIntent` row of any state, and no `incomplete_on_etsy` listing (review H1).
3. Physical sample `passed` or `not_required`.
4. The effective phase allows publication (`core.phase.effective`, record_incident off).
5. A valid sealed owner grant for this exact release (`ops.publication_authority.resolve`,
   which also applies the kill switch).

A crashed reader is a closed gate, and UNKNOWN is never a pass.

**Evidence per state**: stages reached, with job ids, input digests, PDF hashes, release and
content hashes, listing and audit ids. It also carries `cost_to_date_cad` (CostEntry rows by
product or by the row's jobs, de-duplicated) and quality scores (radar score, SEO score,
search share).

## Flow health (`ops/flow_health.py`)

- **STALLED**:
  - a stage's latest DONE job says it hands off (`HANDOFFS`: promoted, drafted, compiled,
    granted, `pdf_sha256`, priced and not stopped, `ok`, not held), no successor job exists
    for the slug/version/release, and the row has not advanced past that point; or
  - a job has been PENDING or FAILED-retrying longer than 6 h, or RUNNING longer than 2 h; or
  - a defect dead letter (`queue.durable.classify_dead_letter`) has no later success.
- **LOOPING**:
  - `same_input_digest`: three or more DONE runs of one job type on the same input digest
    within 7 d. Volatile keys are dropped from the digest, including the rebuild token and
    `as_of`.
  - `compile_revise_cycle`: more completed `cir.revise` runs on one version than
    `engineering_ops.MAX_REVISIONS` (1). Ported from FABLE-P0 `stage_register`: each revision
    changes the CIR, so the digest rule cannot see this loop.
- **HELD**: the inventory's holds (owner, physical, paid_approval, policy). `paid_approval`
  is an open OwnerAction naming the product with a cost or an UNKNOWN cost. A refused dead
  letter is also a hold: `store.publish` refused in shadow is an owner hold.
- **Department activity** for each agent and department (`charters.department_of`), over 24 h
  and 7 d:
  - jobs started, completed and failed; dead letters split into defect and refused;
  - useful versus no-op, judged by `runtime.pipeline.did_no_work(outputs, job_type)`, the one
    judge with `WORK_KEYS`;
  - cost from CostEntry;
  - busy and idle seconds, and the last finish time;
  - the next cadence window, using `Scheduler.tick` arithmetic and skipping suspended types.

## Command Center Production view

`GET /api/cc/production` is behind the existing `/api/cc/*` default-deny owner gate. The
operator bearer token is refused, and reads are cached for 60 s.

The view has these sections:

- state count tiles, with the physical attribute marked "beside state";
- readiness tiers;
- stalls and loops;
- products;
- agents working now;
- recent useful outputs (PDFs, listing packages, certified versions);
- costs and failures by department;
- next scheduled work;
- the products in each state.

The view is read-only, which is tested: a GET changes no table's row count. The API-route
fingerprint (`7f715ba78ff283a8`) is unchanged because the pin does not walk the `/api/cc`
sub-router, so no CONTRACT_CHANGES row is needed.

## Readback projection, for W-READBACK

`products.production_inventory.production_summary(db, *, now=None)` returns counts only:

- `by_state` and `physical_sample` counts;
- `ready_for_publication` and `private_draft_ready`;
- `stalled`, `looping` and `held_by_reason`;
- `useful_vs_noop` for 24 h and 7 d.

It contains no slug, title, cost, error text, customer data or hash (this is tested). To plug
it in, add one line in W-READBACK's `ops/production_evidence.py`:

```python
from ..products.production_inventory import production_summary
SECTIONS["production_inventory"] = production_summary
```

The signature `(db, *, now)` matches. It returns `readable: True`, and an exception becomes
`_unreadable`, never a pass. `app/main.py` and `/api/verify` are untouched.

## Retention (ported idea from FABLE-P0)

Every audit action the inventory reads has a decision in `ops.retention.KNOWN_READ_ACTIONS`.

- **lifetime_total**: the actions states are derived from (`assets.built`,
  `listing_images_*`, `listing.seo_*`, `store.release_gates`, `launch.held`). Pruning them
  would move a product to an earlier state.
- **windowed**: `quality.reverified` (rewritten daily) and `listing.parity` (rewritten on
  every publish attempt). A pruned parity verdict reads UNKNOWN, which is never Ready.
- **latest (new)**: `pricing.refused`. It only annotates a hold and never sets a state.

## Chain breaks found while deriving states

1. **A refused price is a dead end.** `pricing.position` stops with `stopped: true` and
   nothing reads `pricing.refused` (before this branch, no reader existed). `chain.rebuild`
   re-drives the transition once, and pricing refuses again ("already attempted"). The product
   stays at Visual package completed until a code change bumps `CHAIN_VERSION`. Nothing raises
   an owner action or a fix job. The inventory now shows it as a policy hold.
2. **Blocked listing images have the same shape.** `assets.build` returns `ok: false` and
   enqueues nothing. `chain.rebuild` documents that only a `CHAIN_VERSION` bump re-drives it.
   This is shown as Revision required (visual), with no automatic successor.
3. **`listing.parity` is not version-bound.** It is audited under the slug alone, with no
   version in its detail. A verdict for one version could be read as another's. The inventory
   binds it to a version through the audit row's `store.publish` job, and an unbound parity row
   counts as no verdict (tested: `g-unbound`).
4. **A missed-window hold without a pivot has no successor.** `launch.plan` holds and
   enqueues nothing unless the decision is `PIVOT_EVERGREEN`. It is shown as a policy hold.
   Nothing re-plans it when the window reopens, apart from the next rebuild.

## Independent review d0e523b: fixes

The review asked for these to be fixed before shipping. Each fix has a regression test.

- **H1: any draft intent blocks.** Previously only `CREATING` and `RECONCILE_REQUIRED` intents
  closed the gate. Now every `DraftIntent` row for the version closes it, as
  `draft_intent.refuse_if_existing` does in `store.publish`. A listing in
  `incomplete_on_etsy` adds its own reason. Test: `x-created` (a `CREATED` intent).
- **M1: crashing safety readers fail closed.** If the draft-intent table, `active_veto` or
  `withholding.reasons` cannot be read, the row gets a closed-gate reason. Internal stages
  still derive, but the row can never reach Ready or Owner approval pending.
- **M2: recorded verdicts are bounded.** A verdict older than `VERDICT_TTL` (24 h) is
  UNKNOWN, and so is one from a `store.publish` job that carried a historical `as_of`.
  Control test: an old chain with a fresh verdict is still Ready.
  *Consequence:* in shadow, nothing re-runs `store.publish`. After 24 h a product reads
  "Listing package completed" with "re-evaluation required" instead of "Owner approval
  pending". That is the fail-closed reading; `live` mode computes a current verdict.
- **M3: the latest sample decides.** The latest completed physical test, ordered by
  `completed_at` then id, decides pass or fail. A result with no `completed_at` is not a
  completed test. A pass followed by a failure reads failed (Revision required); a failure
  followed by a pass reads passed.
- **M4: verdict rows come from one job.** The `store.release_gates` and `listing.parity` rows
  must come from the same `store.publish` job for this version. An unbound gates row reads
  "not yet evaluated".
- **Surviving mutants, now killed.**
  - M7: a parity row with no `blocks_release` key closes the gate (`g-nokey`).
  - M9: `live` mode is tested both ways, with blocking and passing `for_publish` and parity.
    The mode is kept for operator use; the CC view never uses it.
  - M12: a crashed row is Revision required, and nothing is Ready in any tier.
  I re-applied all three mutants: each now fails the suite.
- **Read-only check.** It is now a SQLAlchemy statement spy as well as row counts. A GET may
  only write the owner session's `last_seen_at`. `derive`, `production_summary` and `build`
  write nothing.
- **Channel eligibility.** The owner cancelled `channel_policy`, so no placeholder was kept.
- **Not changed (review LOW/INFO).** A pruned failing `quality.reverified` row lets a product
  advance, because that action is windowed and `for_publish` does not read it. The fix belongs
  in `quality_ops` (record a withholding on failure), not in this reader.

## Tests

`tests/test_w5_inventory.py` has 11 tests:

- every state derived from seeded records;
- `published_manually` counted as Published;
- Ready refused for each open gate: release gates blocking, parity blocking, a stale verdict,
  no parity, never evaluated, an unbound parity row, an unsettled draft intent, the phase
  alone, the grant alone, and a crashing grant reader;
- the physical sample as an attribute:
  - PDF, visual and listing package are reachable without a sample;
  - a product awaiting its sample is never Ready and is still private-draft-ready;
  - a failed sample is Revision required;
- the dashboard showing the sample beside the state;
- stall and loop detection, including the revise cycle;
- the useful versus no-op split by the handlers' own outcome labels;
- CC auth and read-only behaviour;
- the PWA wiring;
- the projection carrying no private data;
- the review fixes on a fresh database: the TTL control, the latest sample deciding, the
  crashing safety readers, the crashed row, and live mode.
