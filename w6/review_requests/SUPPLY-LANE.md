# SUPPLY-LANE: new products certify while the publishing halt is open

- **Branch:** `eng/supply-lane`, cut from `claude/w6-release-19h4` (b42f89d = deployed 17f17c20).
- **Status:** NOT merged and NOT deployed. Production is unchanged, and no production row was
  read. No PR was opened, and nothing was pushed to `claude/repository-setup-nc9x6o`.
- **Decision:** D-ENG-SUPPLY-LANE (DECISION_LOG). BUILD_STATE has its entry at the top.
- **New suite:** `brambleloop/tests/test_supply_lane.py` (9 tests).

## The readback

On production 17f17c20:
- `certification_pipeline`: 16 products, 0 certified in 7 days;
- the autonomy loop: 11 of 12 stages, none in `original_product`;
- the systemic publishing halt #380 is open.

The owner's P0 rule: "Publication holds MUST NOT stop permitted research, QA, PDFs or internal
listings."

## The production-shaped state (tests/test_supply_lane.py)

- **16 existing products.** Every one is certified, and each has its listing work
  retry-waiting behind the hold. 12 of them carry an open `stale-artefact` halt.
- **The halt.** The real `incident_lifecycle.escalate_systemic` opens `systemic-halt:publication`
  from that evidence: staleness only, no integrity failure.
- **Launch-0** is exhausted.
- **The concept pool** is generated from synthetic watchlist scans: 103 evidence-backed concepts
  (112 candidates). Each arena with READY concepts has an answered research task.
- **Vision:** paid vision is open (owner activation + probe), with a FIXTURE vision judge.
- **Unaided:** only the scheduler's cadence jobs are enqueued (`radar.concept_pool`,
  `radar.concept_intake`, `mjs.seasonal_sentinel`, `supply.admit`), and the real worker drains
  whatever they cause. Nothing stubs a judgement or enqueues a chain job.

## Why production admits 0 new products: every reason found

Two of these were defects, and both are fixed:

| # | Reason | Reproduced on the base | Fix |
|---|---|---|---|
| 1 | **`gate.certify` was gated on publication holds.** It refused whenever `publication_halted(slug)` was true, and that includes the company-wide systemic row, which applies to every product. Every new release was refused as `halted_by_incident`, so QA waited on publishing. | With the halt open: 11 `gate.certify` runs, 0 certified. | `IncidentTracker.certification_halts` (below). |
| 2 | **Held publishing work took the engineering WIP.** Admission counted any live chain-stage job as WIP, including `listing.draft` / `assets.build` held behind the hold. | `capacity: 16 product chain(s) in flight at the work-in-progress limit 2`: nothing admitted. | Lanes (below). |
| 3 | **A fixed WIP of 2 with a trickle of 1 per run.** | A fixed constant: WIP 2, 1 per run, whatever the worker could do. | Capacity-based ceiling. |
| 4 | **Amigurumi concepts are never judged.** The radar board cannot be drawn: "'toy' has no finished size on file, so it cannot be prototyped", so these concepts wait on `image_vision` forever. The engine-demand list asks for amigurumi first. | Yes: 7 amigurumi held on `board_image` after 4 cycles. | **NOT fixed: open.** An honest toy board needs a toy renderer; `disclosed_render` draws flat and round pieces only. I did not fake one from a fabric swatch. Each concept stays held, with its reason, under `regated.radar_held`. |
| 5 | **Engine demand.** nursery, garment, flat_panel, hat and further animals have no certified engine. | Yes (unchanged). | Not a defect. They are recorded as engine demand and admitted on the first pass after their engine certifies. |

Rows 1 and 2 are the "supply wrongly gated on publication holds" that P0 forbids. Each is pinned
by a mutation test that restores the defect and shows the stall comes back.

## The fixes

### 1. Certification is QA

`gates/incidents.py`: `IncidentTracker.certification_halts`. It is used by
`runtime/pipeline.py::handle_certify` and by `release_recovery.retry_halted`.

- **Still stops certification:**
  - every halting incident that names the product, unchanged;
  - the systemic row, when its live evidence holds an integrity failure (a tampered authority
    chain);
  - the systemic row, when any other widespread family is present;
  - the systemic row, when the evidence cannot be read (fail closed).
- **Waived for certification:** the systemic row, only when its live evidence is staleness only.
  This is the existing `release_gates._staleness_only` rule that the rebuild gates already use.
  Evidence and rows are read in one session.
- **Under a staleness hold:** certification proceeds and is audited as
  `gate.certify_under_publication_hold`.
- **Publication is unchanged:** every publication gate still reads `publication_halted`, so
  nothing certified under the hold is published. Tested: no `store.publish` reached DONE, no
  `listing.package` published, and the halt is still open at the end.

### 2. Admission lanes

`products/supply.py`.

- **The engineering lane:** `cir.draft`, `cir.compile`, `cir.revise`, `cir.reengineer`,
  `gate.certify`. Every other chain stage is the publishing lane.
- **`held_for_publication`:** a product holds no engineering slot when all of these are true:
  - all of its live chain work is in the publishing lane;
  - a publication hold applies to the product;
  - none of that work is running.
- **Backlog:** that product's due publishing jobs are also left out of the stage-backlog refusal.
- **Unchanged:** running work, engineering work and un-held publishing work keep their slots.
- **Refill:** `after_chain_job` also refills when an engineering stage ends and only held
  publishing work is left.

### 3. Capacity-based WIP

- **Ceiling:** `workers × max(4, 3600 s ÷ measured draft+compile+certify seconds)`, capped by
  `MAX_WIP` 12. The env override can raise it to `HARD_MAX_WIP` 24, never past. While a stage is
  unmeasured, the floor of 4 per worker is used, labelled ESTIMATED.
- **Per run:** up to 4 admissions, bounded by the free slots and by the backlog headroom. The
  admitted products' expected engineering seconds must still fit under 2 h per worker.

### 4. factory_visibility.supply

Added to the read-only readback (`ops/production_evidence.supply_visibility`). It carries counts
and fixed vocabulary only:
- `pool_by_state` uses `concept_pool.STATES`; a state outside it is counted as `unrecognised`.
  When no pool row exists it is UNKNOWN (`None`), never 0.
- `in_flight_by_stage`: one count per `CHAIN_STAGE_JOBS` stage, each product counted at its
  earliest live stage;
- `engineering`: WIP limit, products holding a slot, held for publication, parked, open slots,
  and whether admission is refused;
- `offers_waiting`;
- `certified_24h`: releases and products.

No slug, title, reason text or payload is returned (tested).

## Every gate stays

- **Child safety:** a low-sew toy certified under the open hold is still withheld, exactly for
  `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN` and `PHYSICAL_TEST_REQUIRED`. It is not
  `halted_by_incident` (tested).
- **Halts:** a product's own halt and an integrity systemic halt still stop certification
  (tested). Unreadable evidence never waives the halt (tested).
- **Unchanged:** the pre-engineering gate and vision judge, engine demand, family diversity,
  cost ceilings and every publication gate. No threshold changed.

## Result (fixture, not a production measurement)

With the halt OPEN over 4 scheduler cycles:
- 8 new products certified, each with compile, twin and reverse in its certificate. Each entered
  through `supply.admitted`, and each is still publication-halted.
- More than 2 products were in engineering at once (sampled after every job).
- The suite asserts N > 2.
- On the base, the same state certifies 0.

## Tests

`tests/test_supply_lane.py`, 9 tests:
- the production state;
- the end-to-end proof with the halt open;
- two mutation tests (certify gated on the hold; held work holding slots), each re-creating the
  stall;
- own halt and integrity halt;
- child safety under the hold;
- lane slot rules (held vs running vs un-held);
- capacity-based WIP;
- factory_visibility vocabulary.

Test edits outside the new suite:
- `test_eng_supply`, `test_w4_listready`, `test_eng_demand_supply`: these pin the historical
  one-worker admission (WIP 2, one admission per run) through the existing
  `BRAMBLELOOP_SUPPLY_MAX_WIP` env override and `supply.MAX_ADMIT_PER_RUN = 1`. Their assertions
  are unchanged.
- `test_eng_supply::test_the_wip_ceiling_follows_the_worker_target_and_stays_bounded`: the table
  now expects the capacity-based defaults (1 worker → 4, 2 → 8, ≥3 → 12, hard max 24).

Targeted run: see "Suite run" below.

## Open / not verified

- **UNVERIFIED in production** until deployed. That the 16 production products' listing work is
  live chain-stage work is inferred from the readback ("14 retry-waiting"). No production row
  was read.
- **Amigurumi boards (row 4).** These concepts cannot be judged until a toy renderer exists, so
  the top engine-demand family adds no supply. The next engineering item is a disclosed toy
  render from the draft CIR's twin.
- **Vision activation.** The radar judge still needs the anthropic-vision activation and probe
  (NEW-PRODUCT-FLOW). If that is closed in production, research concepts wait on `image_vision`
  with their reason. Pool concepts whose family is gate-exempt are unaffected.
- **Judge cadence.** The vision judge runs on the daily `mjs.seasonal_sentinel`, up to 20 calls
  per run, so research supply is bounded at about 20 judged concepts per day.

## Suite run
