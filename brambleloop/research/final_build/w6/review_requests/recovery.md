# ENG-RECOVERY: review request, slice 1 (P0: the factory makes nothing)

- Branch: `eng/recovery`.
- Base: `origin/claude/w6-INTEG2` @ `a35ad302`.
- The final SHA is the commit that adds this file; it is given in the issue #28 comment.
- Not deployed. Not merged. Nothing touches Railway, production, secrets, Etsy, spend,
  `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`.

Production evidence (Main, 2026-11-19T15:03Z, release 8bc96eef):

- original_product did 0/0/0 in 7 days.
- Concept supply stalled: `selection_all_drafted`, pool 34, drafted 16, undrafted 18.
- 19 job types are parked by the thrash breaker.
- Incident #380 has been open since 2026-10-11. 22 certifications are halted, and 14 products
  sit in `rebuild_incomplete_legacy_budget_pending`.
- 16 rebuild retries are held on `listing_image_rules` (#39).

## 1. Root cause: original_product did zero work

The chain is `radar.scan` → `radar.score` → `cir.draft` → `cir.compile` → `gate.certify`.

**Why it stopped**
- `select_portfolio` (`radar/opportunity.py`) ranks by score only. It never looks at
  whether a concept has already been drafted.
- So every 6-hourly `radar.scan` selected the same top 11 concepts, and all 11 had been
  drafted long ago.
- `radar.score` promoted them and called `ctx.enqueue("cir.draft", key="draft:<slug>")`.
  That is a permanent key, so it raised `DuplicateJob`, which `JobContext.enqueue` swallows.
  Nothing was queued.
- The 18 undrafted concepts never received a `radar.score`.
- W5-A7 only *recorded* the stall. Its test pinned "the same selection again".

**What it was not**
- No cap, budget, phase, `STAGE_A_ENABLED` or incident gate is on this path.
- The ×2 backoff on `plan.cycle` is irrelevant, because `signal_review` enqueues `radar.scan`
  on its own cadence.
- The `opportunity_validation` stage looked "healthy" largely because of these no-effect
  re-scores.

**Fix** (`runtime/pipeline.py` `handle_radar_scan`)
- The portfolio is selected from the concepts not yet drafted. This uses the same
  `flow_health.drafted_slugs` as the supply reading.
- If nothing undrafted is selectable on its own (for example, a lone bundle is held unless
  its members are selected with it), selection falls back to the full pool exactly as
  before. The supply reading then names the stall (`pool_exhausted` /
  `selection_all_drafted`).
- Every gate is unchanged:
  - the `PROMOTION_THRESHOLD`, risk class A/B and pre-engineering gate in `radar.score`;
  - intake approval, the funnel and the pre-engineering gate in `cir.draft`;
  - section-33 constraints, which are still audited as `radar.portfolio_constraints_unmet`.
- `radar.scanned` now records `drafted_excluded`.

**Expectation change**
- `test_w5_a7_supply_stall`'s "selection of only drafted concepts is recorded" now asserts
  the reverse: the second scan selects a disjoint, undrafted set, records no stall, and its
  scores queue new `cir.draft` jobs for exactly those concepts.

## 2. Root cause: the suspension classes

**How the breaker decides** (`swarm/orchestrate.py`)
- `thrash_sweep` runs hourly and records two kinds of entry:
  - **SUSPENDED**: three identical (call, result) observations of a DEAD or paid job.
  - **BACKOFF** (`_free_poll_backoff`): a cadence job whose last three DONE states are
    identical. The level rises once per new identical observation, with factor
    `min(32, 2^level)` and `until = now + period*factor`. The deadline never moves earlier.
- `suspended_job_types` is what `Scheduler.tick` skips. It lifts an entry when:
  - `gate_lifted`: a credential probe that was refused then has succeeded since;
  - `upstream_progressed`: BACKOFF only;
  - `_hypothesis_changed`: SUSPENDED only, when the handler source digest changed;
  - or the deadline expires.

**Why loops stayed at ×32 after a fix and redeploy**
- A BACKOFF never consulted the code at all. It was not keyed on commit or digest, so a
  fixed and redeployed loop stayed parked for up to 32 periods.
- When the deadline finally passed, the one run it got was compared with the old tail.
  If the fix had not yet taken effect on that run (for example `chain.rebuild` still finding
  every retry held by #39), the level climbed again.
- Every listed suspension in production is `kind: backoff`.
- The other root causes were upstream:
  - the #39 hold left `chain.rebuild` and `chain.successors` with nothing to do on every run;
  - paid types are correctly parked.

**Fix: a safe automatic re-arm** (`rearm_probe`, `rearmed_job_types`, `spending_job_type`,
`release_booted_at`)

A suspended BACKOFF or SUSPENDED loop is released for exactly one probe run when **all** of
these hold:
1. The running commit is known and differs from the `code_commit` the suspension was
   recorded under, **or** the recorded `handler_digest` differs from the running handler's.
   That second case is a recorded hypothesis change. Backoffs now record `handler_digest` too.
2. The job type does not spend. It counts as spending if any of these is true:
   - it is in `watchlist.paid_job_types()` or `queue.effects.EXTERNAL_EFFECT_JOB_TYPES`;
   - it is in a spending family: `creative.`, `assets.`, `visual.`, `marketing.ads`, `ads.`,
     `gateway.`, `culture.`, `intel.gallery`, `seasonal.`;
   - it has ever had `cost_cad > 0` or a `CostEntry` with `amount_cad > 0`;
   - the read failed. A failed read is treated as spending (UNKNOWN is never PASS).
3. The current release has a `release.boot_verdict` row (written at every boot by
   `ops.release_record.record_incident`) whose `running_commit` matches. The earliest such
   row is the release's boot time.
4. The suspension was recorded before that boot, and no job of that type has been created
   since that boot.

**Why this is bounded**
- "Once" is stateless and durable. The tick enqueues the cadence job, and from that moment
  rule 4 re-parks the type for the rest of the release.
- A restart of the same release is not a new release.
- The next sweep judges the probe:
  - a changed result lifts the backoff (`identical_tail` false → resolved);
  - an unchanged result re-records it under the new commit, so there is no further probe
    until the next release.
- An unknown commit, a commit with no boot record, or a suspension recorded under `unknown`
  grants nothing.

**Spending loops**
- Behaviour is unchanged: they keep `gate_lifted` and the digest-based
  `_hypothesis_changed`, as before.
- In the production list this keeps parked:
  - the `creative.*` types;
  - `assets.owned_photography` and `assets.model_photography`;
  - `marketing.ads_readiness`;
  - `intel.gallery_analysis` and `visual.rnd.cycle`;
  - any type with recorded spend.

**What should get one probe on the next deploy**
- These types, unless they have recorded spend: `chain.rebuild`, `chain.successors`,
  `listing.package`, `commerce.orders_ingest`, `improve.monitor`, `intel.children_portfolio`,
  `listing.cross_sell_graph`, `ops.policy_watch`, `plan.cycle`.
- `rearmed` in the `ops.thrash` output names them.
- No new audit action and no new job type, so there are no retention or autonomy_map
  changes.
- Readback consumers (`flow_health`, `slo`, `useful_work`, `scheduler_readback`) read
  `suspended_job_types`, so a re-armed type is simply not reported as parked.

## 3. Policy hold #39 (`listing_image_rules`)

**What it is**
- `ops.policy_watch` read a material digest change of Etsy's image-requirements article.
- `platform_policy.unreviewed_changes` lists it until `review_change` records the owner's
  review.
- `ops.policy_watch` opens `policy_changed:listing_image_rules` (P1, halts publication).

**Where it blocked internal work**
- In `release_gates.retry_hold_reason`, read by the sentinel's `rebuild_graph.enqueue`
  daily retry. Any unreviewed change whose `affects` included `publishing` held every
  product's rebuild retry. This is the production `retry_held 16`.
- It also left the 14 legacy `rebuild-incomplete` rows unable to start their fresh attempt
  budget, because a held slug gets no attempt and is never restated.
- It also stopped the marketing rebuild exception (`outstanding_only_marketing`).
- Because the stale artefacts were never remade, the staleness-only systemic halt could not
  converge, so `gate.certify` stayed halted.

**Fix** (the owner directive: a publication-side question holds publication only)
- `retry_hold_reason` holds the internal rebuild only for an unreviewed change whose
  `affects` includes `product_creation`. Today that means `children_and_baby` and
  `creativity_standards`, the rules about whether a thing may be *made* at all.
- The marketing rebuild (drafted, held content) is held by `product_creation` or `growth`
  changes.
- `listing_image_rules`, `seller_policy` and `search_guidance` no longer hold either.

**Publication is unchanged**
- `staleness()` still puts every unreviewed `publishing` change into `reasons` and `blocks`.
  `for_publish`, `for_marketing` and the listing-set issuance read those.
- `staleness()` also reports `policy_publication_only`.
- The sentinel's `ops.rebuild_propagated` detail adds `rebuild_policy_publication_only`.

**"The stricter rule"**
- Internal manufacturing runs under the codified, owner-reviewed reading
  (`gates.policy_knowledge.listing_image_rules`: own photographs first, mock-ups never first,
  generated hero never evidence, ≥2000 px, AI disclosure).
- Nothing the new text might relax is used. Nothing built under it can publish until the
  review is recorded.
- Certificates keep stamping `changed_unreviewed` via `policy_stamp`, so
  `certified_against_current_policy` is false until the review.
- No certification or safety gate was changed:
  - `gate.certify`'s incident halt is unchanged;
  - the policy incident has no `product_slug` and is not `systemic-halt:*`, so it never
    halted certification itself.

**Expectation change**
- `test_w4_prodfix::test_s2...` now holds on a `product_creation` source (`children_and_baby`).
  A publication-only source is proven *not* to hold in `test_eng_recovery`.

### OWNER ACTION REQUIRED (#39): batched, exact

- **Action.** In the Command Center, open Approvals and find the card
  **"Etsy policy changed: listing_image_rules"** (card id `policy:listing_image_rules`).
  1. Press **Preview** (`policy.review_preview`, source `listing_image_rules`). Read the
     changed reading against the one before it.
  2. Press **Review**. This is `policy.review` and requires step-up. Fill in:
     - `confirm`: exactly `reviewed and tested`;
     - `tested`: what you checked, for example "gallery rules in policy_knowledge still match
       the article: own photo first, mock-ups not first, 2000 px";
     - `expected_digest`: the `review_digest` shown by Preview.
- **Why it is required.** Only the owner can attest that a changed Etsy rule was read and the
  affected workflows re-tested. Code cannot decide what changed in the text.
- **Maximum cost.** CA$0.
- **Time.** About 10 minutes.
- **Consequence of waiting.**
  - With this branch: internal rebuild, re-certification, PDFs and galleries proceed, but
    **no product can publish** and the P1 `policy_changed:listing_image_rules` incident stays
    open.
  - Without this branch: every rebuild retry stays held as well.
- The card text now says: "Internal rebuilds and re-certification continue under the
  reviewed rules; publication stays held until you review it".

## 4. The 14 legacy products

- `legacy_incomplete` rows (no `attempts`, no `budget_reset`) leave that state only when a
  targeted `chain.rebuild` restates them or the sentinel closes them.
- Production held every one of their daily retries on #39, so none ever got the fresh
  budget. Point 3 removes that hold.
- The targeted `chain.rebuild` jobs come from `ops.sentinel`, a liveness type that is never
  backed off, and go straight into the queue. The `chain.rebuild` cadence backoff does not
  gate them.
- **Still open for slice 2:** a legacy row whose product currently has **no STALE verdict**
  (named keys read "no provenance row", UNPROVEN or retired) is never enqueued and never
  closed. Slice 2 gives such a row one explicit targeted rebuild of its named keys, under
  the bounded three-attempt budget. It neither closes the row without evidence nor lifts
  any halt.

## 5. Tests

New: `tests/test_eng_recovery.py` (offline). Each production state is a fixture:

- A suspended free loop (`chain.rebuild` and `chain.successors` at ×32, recorded under
  f34c25ae) re-arms once after a release change:
  - there is no probe before the boot record exists;
  - the `Scheduler.tick` enqueues exactly one job;
  - later windows and a restart of the same release add nothing;
  - the next release gets its own single probe.
- The probe is judged by the sweep, and an unchanged result re-parks the loop.
- Spending loops do not re-arm: the paid families, plus a job type with a recorded
  `CostEntry`.
- A SUSPENDED free loop re-arms; a SUSPENDED paid one does not.
- An unknown release, or a suspension recorded under `unknown`, never re-arms.
- A changed handler digest counts as a hypothesis change. A suspension recorded after this
  release booted gets no probe.
- `thrash_sweep` reports `rearmed`.
- The spending classifier is conservative.
- `listing_image_rules` pending:
  - `retry_hold_reason` is None;
  - `staleness()` still blocks and names it;
  - the daily retry is enqueued, while publication for the same product still refuses;
  - adding `children_and_baby` holds again.
- The policy card names the scope. The confirmation is `reviewed and tested`.
- Production supply numbers: the undrafted selection is disjoint from the drafted one.
- `test_w5_a7_supply_stall`: the real `radar.scan` and `radar.score` handlers queue new
  `cir.draft` jobs from the undrafted pool.

Changed after the first suite run:

- `ops.retention.KNOWN_READ_ACTIONS` now lists `release.boot_verdict` as `windowed`. The
  re-arm reads it by name.
- `ops.retention.unknown_read_actions()` returns `[]`.

### Suite results (venv from `requirements.lock` + `requirements-test.lock`, no PYTHONPATH)

**Run `20261119T160241Z-27083`**
- 57 suites (JOBS=4): the required list, every suite matching
  `thrash|suspension|backoff`, and every suite touching `retry_hold_reason`,
  `unreviewed_changes`, `radar.scan` or `policy_review`.
- Result: 915 passing, 5 suites failing:
  - Four failed because `release.boot_verdict` had no retention decision:
    `test_cost_governance_wave2`, `test_etsy_oauth_callback`,
    `test_w4_fmbatch1_retention_guard`, `test_w5_concept_intake`. Now fixed.
  - `test_w4_resume_runner` p09 failed on its nested-runner output under load. It passes
    alone on base `a35ad302`, and on this branch in run 3.

**Run 3**: the six suites above (`test_eng_recovery`, `test_cost_governance_wave2`,
`test_etsy_oauth_callback`, `test_w4_fmbatch1_retention_guard`, `test_w4_resume_runner`,
`test_w5_concept_intake`) → **179 passing, 0 suites failing**.

**Not run in this slice**
- A full re-run of all 57 suites after the retention fix. The fix only adds one entry to
  the retention table.
- A first run with 72 suites was killed by my own 50-minute timeout before the runner
  printed anything (`20261119T151217Z-1232`, interrupted). It produced no evidence, and I
  claim none from it.

### Mutation table

Each mutant was applied to a copy of the tree and must make the named suite fail.

| # | Mutant | Suite | Result |
|---|---|---|---|
| M1 | spending check removed from `rearm_probe` | test_eng_recovery | KILLED |
| M2 | once-per-release check removed | test_eng_recovery | KILLED |
| M3 | boot record matched for any commit | test_eng_recovery | KILLED |
| M4 | suspension recorded under `unknown` re-arms | test_eng_recovery | KILLED |
| M5 | `since >= booted` check removed | test_eng_recovery | KILLED |
| M6 | `suspended_job_types` ignores the re-arm | test_eng_recovery | KILLED |
| M7 | unknown running commit allowed in `rearm_probe` | test_eng_recovery | KILLED (after adding `test_rearm_probe_itself_refuses_an_unknown_running_commit`; it survived first because `release_booted_at` repeats the guard) |
| M8 | retry held on any publishing policy change again | test_eng_recovery | KILLED |
| M9 | product_creation changes no longer hold | test_eng_recovery | KILLED |
| M10 | publication no longer held by unreviewed policy | test_eng_recovery | KILLED |
| M11 | radar.scan ignores drafted state | test_w5_a7_supply_stall | KILLED |
| M12 | no fallback when nothing undrafted is selectable | test_w5_a7_supply_stall | KILLED |

## Slice 2: the legacy rebuild-incomplete rows (point 4)

**Cause**
- A pre-branch `rebuild-incomplete` row has no `attempts` and no `budget_reset`.
- If its product reads nothing STALE, the sentinel's propagation never reaches it, because
  propagation enqueues only for moved refs.
- It cannot close either. Its named keys read "no provenance row", UNPROVEN or retired, which
  is not positive evidence.
- So it sat in `rebuild_incomplete_legacy_budget_pending` for good.
- Separately, slice 1 removed the #39 hold that kept every daily retry from running.

**Fix** (`ops.sentinel`, `runtime/release.py`)
- Such a row gets exactly one targeted `chain.rebuild` of the keys it names.
- The job is keyed `rebuild:legacy-restart:<slug>:<row id>`, so it runs once per row.
- That attempt restates the row under the bounded budget (`_rebuild_incomplete` →
  `budget_reset`), or verifies and closes it through the existing evidence path.
- Nothing is closed here and no halt is lifted.
- A row already under the new budget, or a product with a STALE verdict, is left to the
  existing bounded retry.
- The sentinel output gains `rebuild_incomplete_legacy_restarted`.

**Test**
- `test_eng_recovery::test_a_legacy_row_with_nothing_stale_gets_exactly_one_targeted_rebuild`.
  It has three products: legacy with nothing stale, already on the new budget, and legacy
  with a STALE chart.
- Exactly one job is enqueued, for the first product only.
- A second sentinel run enqueues nothing.
- No row is resolved and every row still halts publication.

**Mutants**

| # | Mutant | Result |
|---|---|---|
| M13 | the legacy restart ignores STALE | KILLED |
| M14 | the legacy restart applies to non-legacy rows | KILLED |
| M15 | the legacy restart runs more than once per row | KILLED |

**Suites, run 4** (`test_eng_recovery`, `test_eng_stale_rebuild_loop`,
`test_eng_stale_round2`, `test_w4_prodfix`, `test_cert_rebuild_chain`,
`test_w4_fmbatch1_retention_guard`, `test_w4_readback_evidence`, `test_vacuity`,
`test_w3_tmp_hygiene`): **130 passing, 0 suites failing**.

**Limit, stated plainly**
- If a product has no stored release, the restart is refused with "no stored release" and
  the row stays legacy. That outcome is visible through `chain.rebuild_refused`.
- The 14 production products all have certified releases, so this should not apply to them.

---

## Fix round 1 (Main's review: DO NOT SHIP; H1, M1, L1, L3, L4, L5)

### H1: the spend classifier fails closed

**Defect.** `spending_job_type` was a deny-list. It called two paid loops free:
- `intel.serp_capture`: `score_thumbnails` → `providers.for_task(vision.TASK)`;
- `laura.executive_tick`: `_model_rank` → `laura_converse.call`.

So a deploy would have re-armed both.

**Fix** (`swarm/orchestrate.py`)
- `FREE_JOB_TYPES` is an explicit allow-list. A job type is free only if it is on the list
  **and** none of the old refusals applies (spending prefix, `paid_job_types()`,
  `EXTERNAL_EFFECT_JOB_TYPES`, recorded `cost_cad`/`CostEntry`, failed read).
- Every other job type is spending: new, renamed or never examined.
- The list holds 94 cadence loops. Each one is a registered handler that the static graph
  below proves cannot reach a paid entry point, and that no other rule already calls
  spending. Adding one is a reviewed decision about spend.

**Proof** (`tests/_spend_reach.py` plus three tests in `test_eng_recovery`)
- A conservative static call graph over `src/brambleloop`:
  - function-local imports are resolved;
  - a reference to a function counts as an edge (callbacks included);
  - a reference to a class is an edge to all of its methods;
  - `self.x` resolves within the class.
- Paid entry points:
  - by name on any receiver: `provider_for`, `for_task`;
  - by resolution: `paid_calls.guarded`, `laura_converse.call`, `images.generate`,
    `providers.for_task`, and both `provider_for`s;
  - every request site (`urlopen`, `Request(`, `_post(`, `.post(`, `http.client`) in a
    module that `test_cert_spend_hosts.DECLARED` declares, or in any `gateway` module, except
    the three reviewed free reads (`gateway/credentials.py`, `ops/provider_accounts.py`,
    `ops/adoptions.py`).
- `test_every_handler_that_can_reach_the_paid_gateway_is_classified_spending`:
  - every registered handler (all modules containing `@handlers.register`) that reaches an
    entry point is classified spending;
  - every allow-listed type is registered and unreachable;
  - not vacuous: the graph finds both review findings
    (`handle_serp_capture -> score_thumbnails`,
    `handle_executive_tick -> tick -> _model_rank -> laura_converse.call`) and five known
    paid loops.
- `test_the_paid_entry_points_cover_test_cert_spend_hosts_declared`:
  - DECLARED = request modules ∪ reviewed free reads;
  - each request module contributes an entry point, and each named entry point exists;
  - a new DECLARED module fails here until it is classified.
- `test_the_spend_classifier_fails_closed` and
  `test_a_paid_loop_the_deny_list_missed_does_not_rearm`: both findings stay parked across a
  release change, while `chain.rebuild` gets its probe.

**Stated limit.** The graph cannot follow a method called on an object injected from outside,
or `getattr` by string. As a cross-check, I listed every non-gateway function that calls
`.complete/.vision/.render/.generate/.messages/.chat` on any receiver and is reachable from
an allow-listed handler. Every hit was a local deterministic renderer or terms text
(`disclosed_render`, `contents_frame`, `customer_terms.render`), with no model call. The
allow-list is the runtime rule; the graph only has to agree with it.

### M1: supply no longer re-stalls invisibly

**Reproduced first** (real `radar.scan` and `radar.score`, real POOL, the 16 production
drafted slugs). The old branch:
- drafted 2, then 1, then 0, 0, 0;
- re-selected the same 10 every time;
- reported `stalled=False`.

**Verdicts for the 15 undrafted concepts**
- 9 are refused by #88 at `premise_thumbnail`: "is not a concept yet: it has no ['premise',
  'pod', 'form', 'construction', 'motif', 'palette_story', …]".
- `alpine-slouch-beanie` is at 0.5442, below the 0.55 threshold.
- 3 more are below the threshold.
- `boxy-summer-tee` and `cropped-cardigan` are risk class C.

**Fix** (`runtime/pipeline.py`)
- `promotion_verdict(db, seed, inputs, today)` is the decision `radar.score` makes, extracted
  unchanged and read-only:
  - steering, the evidence discount, the lesson nudge;
  - `PROMOTION_THRESHOLD`, risk A/B;
  - the established/bundle exemption;
  - `preengineering.gate_concept`.
- `radar.score` now calls it and writes the same records in the same order. `radar.scan`
  calls it through `promotable_now` before it selects. One rule, two callers; nothing is
  re-implemented or relaxed.
- Selection tiers: promotable undrafted → undrafted → full pool. The first tier from which
  section 33 can select wins.
- `_record_supply_stall` counts as supply only a selected concept that is undrafted **and**
  promotable. Reasons:
  - `pool_exhausted`;
  - `selection_unpromotable` (new): undrafted concepts remain, none promotable; each held
    concept's reason is recorded, including the failed gate checks;
  - `promotable_not_selectable`: promotable ones exist but section 33 cannot select them on
    their own;
  - `selection_all_drafted`: only when promotability was not judged.
- `flow_health.concept_supply_stall` shows `promotable_undrafted` and the `held` count.

**#88 is not weakened, and no repair was possible.**
- A POOL seed is a radar slot (category, price, season). It has no Concept fields.
- The only paths that make one a Concept are:
  - a creative tournament winner through `creative/intake.py` (`creative.*`, paid model
    work);
  - an approved `radar.intake` row.
- Deriving a premise from a slot is exactly what #83 forbids ("engineering something because
  it fills a slot").
- So the 9 stay held, now *visibly*.
- **Consequence:** after the 3 promotable drafts, original_product stalls again until
  creative or intake supplies concepts. The supply reading now says so.

**Test**
`test_w5_a7_supply_stall::test_the_production_drafted_set_drafts_what_can_be_drafted_then_names_the_stall`
uses the real POOL (34), the 16 drafted slugs and four scans:
- scan 1 drafts exactly the 3 promotable concepts (`bobble-floor-pillow`,
  `chunky-ribbed-scarf`, `cottage-wall-hanging`);
- scans 2 to 4 draft nothing, report `stalled=True`, `selection_unpromotable`,
  `promotable_undrafted=0`, and give held reasons that name `premise_thumbnail`, the threshold
  and Class C;
- no held concept gets a `cir.draft`;
- there is one reading per scan date;
- `flow_health.concept_supply_stall` shows the reason.

### L1
`radar.scan` returns and audits:
- `pool_size`: the full section-33 pool, 34;
- `selection_pool` and `selection_pool_size`: the tier the selection came from and its size;
- `drafted_excluded` and `unpromotable_excluded`.

### L4
`rearm_probe(..., boot_cache=)` takes one memo per pass of `suspended_job_types` or
`rearmed_job_types`. `test_the_boot_record_is_read_once_per_pass` checks one read over four
suspensions.

### L5: a real defect, found by the requested test

`test_a_legacy_row_completes_its_chain_while_the_image_rule_review_is_pending` runs on the
real chain on SQLite:
- `cloudline-baby-blanket` is built and certified;
- a pre-branch `rebuild-incomplete` row names its PDF and content keys, which read "no
  provenance row", as in production;
- #39 is pending throughout.

**First run: FAILED.**
- `marketing.schedule` refused the rebuild (`marketing.blocked`). Its reasons were the row's
  own halt and #39.
- The marketing rebuild exception (`outstanding_only_marketing`) required a non-empty
  `outstanding` list. A legacy row's keys are not STALE, so the list is empty and the
  exception never applied.
- Every retry would have been refused the same way, using up the three-attempt budget on the
  refusal the rebuild exists to cure.

**Fix** (`publish/release_gates.staleness`)
- The exception also applies when nothing is outstanding and this product's own
  `rebuild-incomplete` row is open and not exhausted (`_own_rebuild_pending`; a failed read
  is False).
- Any other halting row still refuses the marketing rebuild, and so does a growth or
  product-creation policy change or non-marketing outstanding work.
- `halted`, `reasons` and `blocks` (what `for_publish` and `for_marketing` publication read)
  are unchanged.
- The test then asserts:
  - no refusal;
  - nothing stale;
  - every named key has `chain.rebuild_completed`;
  - the row is resolved on that evidence, with no `held` and attempts < 3;
  - `staleness()` still blocks the product's publication on `listing_image_rules`.

### Mutation table (fix round 1)

**Method.** Each mutant was applied to a fresh copy of `src/` and `tests/`, then the named
test functions were run. Runner: `/tmp/claude-0/s/mutate.py`, a scratch file that is not
committed.

| # | Mutant | Test(s) | Result |
|---|---|---|---|
| M16 | classifier back to a deny-list (allow-list check removed) | fails_closed, deny_list_missed, every_handler_reach | KILLED |
| M17 | `intel.serp_capture` added to FREE_JOB_TYPES | every_handler_reach | KILLED |
| M18 | `laura.executive_tick` added to FREE_JOB_TYPES | every_handler_reach | KILLED |
| M19 | free-listed `plan.cycle` handler gains `providers.for_task(...)` | every_handler_reach | KILLED |
| M19b | free-listed `plan.cycle` reaches `laura_converse.call` through a helper | every_handler_reach | KILLED |
| M20 | `for_task` removed from the graph's name-based sinks only | every_handler_reach | SURVIVED (see below) |
| M20b | `for_task` removed from both the name sinks and the resolved keys | every_handler_reach | KILLED |
| M21 | a new DECLARED module that nobody classified | declared_cross_check | KILLED |
| M22 | radar.scan ignores promotability | production_drafted_set | KILLED |
| M23 | a gate-refused concept counts as promotable | production_drafted_set | KILLED |
| M24 | `selection_unpromotable` never recorded | production_drafted_set | KILLED |
| M25 | an unpromotable selection counted as supply | production_drafted_set | KILLED |
| M26 | L1: `pool_size` reports the sub-pool again | production_drafted_set | KILLED |
| M27 | L4: boot cache never filled | boot_record_once | KILLED |
| M28 | L5: empty-outstanding waiver removed (old rule) | waiver_bounded, legacy_row_e2e | KILLED |
| M29 | L5: waiver ignores an exhausted own row | waiver_bounded | SURVIVED (see below) |
| M30 | L5: waiver ignores other halting rows | waiver_bounded | KILLED |

**Survivors**

- **M20 is a redundant layer, not a hole.** `gw.for_task` is also resolved through the import
  alias to `gateway.providers.for_task`, which is a resolved paid entry point. Removing only
  the name-based layer still finds `intel.serp_capture`. Removing both (M20b) is killed.
- **M29 is a redundant guard.** An exhausted own `rebuild-incomplete` row is not waivable
  (`_waivable_staleness`), so it lands in `halting_other` and the waiver is refused there
  anyway. The exhaustion check in `_own_rebuild_pending` is defence in depth. It is kept, and
  stated here as not independently tested.

**Score:** 15 of 17 killed. The 2 survivors are redundant guards, explained above.
