# Independent security and integrity review: W4-INTELREC

- **Date:** 2026-10-26 (UTC).
- **Reviewer:** an independent Claude Code session. It did not write the code under review, and this review fixes nothing.
- **Scope:** `git diff 67920948..f8379deb -- brambleloop/src brambleloop/tests` on `claude/w4-INTELREC` (4 commits: 876b4fe, fb66472, dd04c40, f8379de), plus `brambleloop/research/final_build/w4/intel/*`.
- **Method:**
  - I read the full diff, and the existing code it calls into: `intel/observe.py`, `intel/mission_runtime.py`, `intel/coverage.py`, `intel/benchmarks.py`, `intel/vision.py`, `runtime/release.py` (the tournament and gallery handlers), `laura/executive/loop.py`, `gateway/laura_converse.py`, `autonomy/charters.py`, `improve/bus.py` and `improve/consume.py`.
  - I ran the touched suites.
  - I wrote two offline probes, kept outside the repo, that exercise the suspected defects.
- **Constraints:** no production calls, no secrets, no deploys.

## Verdict

**Can this ship in a SHADOW release with Laura's switches OFF? CONDITIONAL: not as-is.**

| Question | Verdict | Basis |
|---|---|---|
| **Overall: ship in SHADOW with Laura's model switches OFF** | **CONDITIONAL** | Content, access, model-switch and test integrity all pass. Two integrity defects must be fixed before merge, because they write durable false state that would carry into production: **H-1** (budget refusals and unrelated runs are recorded as "observed" design failures, which permanently stop arenas) and **M-1** (Laura reads the watchlist OK when nothing has ever been observed). Everything else can follow in a later pass. |
| 1. Content and access | **PASS** | No new competitor text, imagery, instructions or URLs are stored beyond the existing rules. The comparison is alias-only and is asserted by `_assert_no_content`. Etsy is read only through the official API (`PublicReader`). Nothing tries to get past a 403. The `benchmark_health` browser path widens to three more shop URLs, but it is pre-existing, polite and records only status and final URL (I-3). |
| 2. Paid calls and spend | **PASS with caveats** | No new vision or model call site. Every paid path reached is the existing `creative.tournament`, behind `_ceiling_gate` plus `failover.job_gateway` (agent and monthly ceilings), and vision stays anchor-only. **But** the new jobs *originate* additional paid tournaments, and the "CA$0" labels understate this (M-2, M-3). This matters with CA$18.65 of headroom. |
| 3. Laura's authority | **PASS with caveat** | Probe P8: with `BRAMBLELOOP_LAURA_CEO_MODEL` unset, a tick with a DEGRADED intelligence provider makes **0 model calls** (`lc.available` refuses first). Nothing publishes, writes to Etsy, changes a budget or bypasses an owner gate or Product Truth. Caveat: the *deterministic* tick still delegates `intel.opportunity_review`, which can queue paid tournaments, while the constitution is told `cost_cad: 0.0` (M-2). |
| 4. Assertion integrity | **FAIL (fixable)** | AI-use stays `UNKNOWN` and hypothesis-only, which is good. But a settled job of any outcome, including a ceiling refusal, is booked as "produced no engineered product" and published as an `observed` lesson (H-1). An unobserved watchlist reads `OK` (M-1). Some unmeasured values render as 0 or as MEASURED (L-1, L-2, L-3). |
| 5. Tests | **PASS** | `test_cert_mjs` is not weakened. It now asserts that an impostor is refused by all four shops, and that MJs's URL is refused by the other three. My probe P2 checked the full 4×4 matrix: each shop accepts only its own URL. All touched suites pass. There are test gaps (I-2). |
| 6. Report honesty | **MOSTLY PASS** | Every job count in `OWNER_REPORT.md` matches `evidence/prod_job_counts…` exactly. The report is careful to call INTELREC undeployed and offline-only. Over-claims: the "16.8 % production-verified by record" figure rests on one listing-count reading reused across 17 rows (M-5); "watchlist jobs spend CA$0" (M-3); and three figures are not backed by `evidence/` (L-7). |
| 7. Runtime safety | **PASS with caveats** | The jobs are bounded (`REVIEW_LIMIT=3`, `MISSION_LIMIT=5`, per-gap `MAX_FAILED_ATTEMPTS=2`), idempotent per attempt and loop-free. `coverage.upsert` never reopens a NOT_PURSUING gap. Caveats: lesson-deferred gaps are re-decided daily forever (L-4), and there is no backoff on per-shop refusals (L-6). |

### Test runs

The venv was built from `requirements.lock` plus `requirements-test.lock`. Each suite ran under `nice -n 19`, one at a time.

| Suite | Result |
|---|---|
| `tests/test_w4_intelrec_watchlist.py` | 6/6 ok |
| `tests/test_w4_intelrec_amplify.py` | 3/3 ok |
| `tests/test_cert_mjs.py` | 19 OK, 0 failed |
| `tests/test_w3_laura_core_executive.py` | 7 OK, "PASS: 0 failing" |
| `tests/test_w4_agents.py` | 14 OK, 0 failed |
| `tests/test_w4_agents_secfix.py` | 13 OK, 0 failed |

### Probes

These are offline, against a temporary SQLite database, using the test file's own `Reader` fixture.

| Probe | What it showed |
|---|---|
| P1 | No credential: `scan_all` records `not_configured` for all three shops, and `summary()` returns **`OK`** with an empty reason. |
| P2 | `benchmarks.resolve` 4×4 matrix: `healthy` on the diagonal only, `wrong_shop` everywhere else. |
| P4 | A gap deferred by the lesson is re-decided `deferred_by_lesson` on day 0, 1 and 2. `bus.acted_on` dedupes per cell, so there is no acted-on inflation. |
| P5 | Two `DONE` design jobs whose outputs carry an intake draft move the gap to `not_pursuing`, with 2 "failed_attempts". |
| P6 | Reviews endpoint returns `[]`: `recurring_complaint_themes` is `{value: 0, grade: DERIVED}`. |
| P7 | After two failed scans: MadelineMaeCo `state=source_outage`, but `public_sales` and `listings_observed` are still graded `MEASURED`. The anchor's state is `never` and its failures 0, whatever `mjs.scan`'s health. |
| P8 | Laura switch unset, intelligence provider DEGRADED: `laura.executive_tick` gives `cognition: deterministic`, 0 calls to `laura_converse.call`, and `intel.opportunity_review` is enqueued. |

---

## Findings

Severity scale: **High** means durable false state or a control gap, and blocks merge. **Medium** should be fixed before production. **Low** and **Info** are hygiene.

### H-1. Any settled design job is recorded as a failed attempt, then published as an "observed" lesson that stops the arena

- **Severity:** High (assertion integrity, durable learning state).
- **Location:** `intel/watchlist.py:503-532` (`review`); `_lesson_statement` at `:481-483`. The test that encodes the behaviour is `tests/test_w4_intelrec_watchlist.py:181-196`.

**Scenario.**

1. `review()` treats every terminal job (`DONE`, `DEAD` or `CANCELLED`) older than `SETTLE` as a failure. It appends the job to `failed_attempts` without ever looking at what the job produced.
2. After two such jobs it does two things:
   - it publishes a lesson with `confidence="observed"`, stating "N original design attempts produced no engineered product";
   - it moves the gap to `NOT_PURSUING`.
3. Through `consume.matching`, that lesson then defers every later gap in the same pod.

Realistic paths that reach this, none of which is a design failure:

- **Ceiling refusal.** `handle_creative_tournament` returns `{"ran": False}` from `_ceiling_gate` with status `DONE`. With CA$18.65 left this month, this is the likely outcome.
- **No arenas.** `prospecting.arenas()` is empty, giving `ran: False` with status `DONE`.
- **Model outage.** A job in `MODEL_JOB_TYPES` that stays parked past 24 h "runs anyway and reports its own refusal".
- **Wrong arena (M-4).** The tournament ran in a different arena.
- **Real success.** The tournament *did* reach intake and queue `cir.draft`. Probe P5 marked the jobs DONE with an intake output, and the arena was still stopped.

**Effect.** Arenas that two watchlist shops corroborate are permanently abandoned on the strength of a lesson the system asserts it observed but never measured. This violates "never claim … until verified", and the state persists into production.

**Fix.**

- Count an attempt as failed only from a measured outcome. Examples: the tournament's own `ran`/`intake` output, the presence of a `cir.draft` job or `PatternVersion` for the pod after `design_started_on`, or the gap having advanced to `CONCEPTING`/`ENGINEERING`.
- Classify `ran: False` with a ceiling, refusal, park or no-arena reason as **not attempted**. It must not be a failure and must not count toward `MAX_FAILED_ATTEMPTS`.
- Publish the stop lesson as `confidence="inferred"` (or the bus equivalent) unless the outcome was measured.
- Change the offline test so that a DONE job with a successful intake does **not** count as a failure.

### M-1. Laura reads the intelligence provider as OK when no watchlist shop has ever been observed

- **Severity:** Medium (an UNKNOWN reported as a pass).
- **Location:** `intel/watchlist.py:397-424` (`summary`), `:215-229` (`scan_all`, the `not_configured` and `auth_refused` branches).

**Scenario.**

- **No Etsy key in the environment.** `scan_all` records `state="not_configured"` but does not increment `consecutive_failures`. `last_ok_at` is `None`, so the shop cannot be "stale" either. `summary()` returns `{"status": "OK", "reason": ""}` (probe P1).
- **Etsy has refused the read key.** The `auth_refused(last_probe(db))` branch returns without recording any per-shop state. It reads OK too.

Laura then never prioritises the outage. The owner report says Laura "sees an outage after 2 failures, and stale data after 48 h", but this case escapes both.

**Fix.** In `summary()`, treat each of the following as DEGRADED or UNKNOWN, with the reason named:

- any non-anchor member whose state is not `ok`;
- any member with no `last_ok_at` at all.

In the `auth_refused` branch, record `state="credential_refused"` per shop. Add a test that `summary()` is not OK straight after an unconfigured scan.

### M-2. Jobs Laura may delegate now originate paid work, while the constitution and SAFE_GENERATED see CA$0

- **Severity:** Medium (authority basis or spend control).
- **Locations:**
  - `intel/watchlist.py:557-563` (`review` queues `creative.tournament`);
  - `creative/family_engine.py` (`amplify` queues `creative.tournament`);
  - `autonomy/charters.py:36-37` (the SAFE_GENERATED reason for `intel.opportunity_review`, "spends nothing itself");
  - `autonomy/charters.py:86-87` (the SAFE_GENERATED reason for `creative.family_engine`, which still reads "creates no product; CA$0");
  - `laura/executive/loop.py` `_delegate` (`constitution.review(... "cost_cad": 0.0 ...)`).

**Scenario.**

1. With every Laura model switch OFF, the deterministic tick sees `intelligence` DEGRADED and delegates `intel.opportunity_review` once per UTC day (probe P8).
2. The review queues up to `REVIEW_LIMIT=3` `creative.tournament` jobs per run, at about CA$0.27 each at the cheap tier, plus intake.
3. Once orders exist, `creative.family_engine` (also Laura-generatable) does the same through `amplify`.

The constitution evaluated the delegation at CA$0. SAFE_GENERATED exists so that Laura can only generate non-spending work, and its stated basis for `creative.family_engine` is now false.

Spend stays inside the creative director's ceilings and the monthly ceiling, which are enforced in code. So nothing *exceeds* a limit. But a Laura-initiated chain consumes scarce headroom without the constitution or the owner seeing an estimate.

**Fix.** Choose one:

- (a) Make the review and amplification routes enqueue only non-spending steps (`radar.score`), and let the existing weekly tournament wheel pick the arena up.
- (b) Have `_delegate` pass the downstream cost estimate, for example `REVIEW_LIMIT` × `prospecting` cheap-tier estimate, so the constitution's spend check applies.

Either way:

- update both SAFE_GENERATED reasons to state that the job *queues* paid `creative.tournament` work inside the creative ceilings;
- add a test that asserts the constitution sees a non-zero estimate, or that no paid job type is queued.

### M-3. The watchlist scan fans out paid breakthrough tournaments per shop, but is labelled CA$0

- **Severity:** Medium (spend under-stated; tight headroom).
- **Location:**
  - `intel/watchlist.py:200-204` calls `mission_runtime.process(benchmark_key=member.key)`;
  - `intel/mission_runtime.py:689-704` (`_enqueue_breakthrough`, key `mjs.breakthrough:{benchmark_key}:{arena}:{week}`);
  - the "CA$0" claims: the `runtime/worker.py:927-931` comment ("Both CA$0 (official-API reads)"), the `intel_ops.handle_watchlist_scan` docstring ("GREEN") and `OWNER_REPORT.md` §5 ("The watchlist jobs spend CA$0").

**Scenario.**

- Before this change, only Mrs J's listings drove the mission. Now each of the three new shops does too.
- The breakthrough idempotency key includes `benchmark_key`, so the same arena can queue **one paid tournament per shop per week**, up to 4× the previous rate.
- A new shop's first scan is a baseline, so up to `MISSION_LIMIT=5` listings per shop per 6-hour run enter the mission.
- My fixture did not reach a proven arena, so no tournament was queued in the probe (P3). This finding is from code reading and is **PLAUSIBLE**, not demonstrated.
- The test `test_spend_limits_and_bounded_work` asserts `CostEntry` count is 0, but it never runs the jobs the scan or review queue. So the assertion is vacuous for downstream spend.

**Fix.**

- Key breakthrough tournaments per arena per week across the watchlist, not per shop. Alternatively, pass `enqueue=None` to the mission for non-anchor shops until the owner authorises the spend.
- Correct the three "CA$0" statements to "CA$0 itself; may queue `creative.tournament` inside the creative ceilings".
- Add a test that runs the queued work, or one that counts paid job types queued per scan.

### M-4. A tournament briefed for a watchlist gap may run in a different arena, and is still booked against the gap

- **Severity:** Medium (misdirected spend that feeds H-1). PLAUSIBLE.
- **Location:** `intel/watchlist.py:557-563`; `runtime/release.py:5150-5170` (the breakthrough branch); `creative/prospecting.py:213-247`.

**Scenario.**

1. `handle_creative_tournament` honours the brief's pod only if it is among the top-12 `prospecting.arenas()`. Those come from the seasonal benchmark matrix (proven-and-unserved departments).
2. A watchlist pod outside that list falls back to the weekly wheel, and `_ideation_arena` may also move the arena.
3. The run is paid for, then attributed to the gap as an "attempt".

**Fix.**

- Make the tournament refuse, without spending, when a `watchlist_gap_id` brief's pod is not a proven arena.
- Or have `review()` read the tournament's actual arena from its output, and count the run only when it matches.

### M-5. "16.8 % production-verified by record" rests on one listing-count reading reused across 17 rows

- **Severity:** Medium (report honesty).
- **Location:** `research/final_build/w4/intel/OWNER_REPORT.md` §0 row 12; `TRACEABILITY.json` (`valid_evidence.ok == true` on 17 rows).

**Scenario.** Every row marked valid evidence cites the same artefact: `/api/benchmark-selection`, "observed 442 listings". It is applied to:

- B2#217, mechanism decomposition;
- B2#225, `gateway/routing.py`;
- B2#302, capacity;
- B2#303, the market map;
- B2#319, mission report refusal;
- and others.

A count of observed listings evidences the catalogue scan (#207, #208, #212, #313). It does not evidence the output of those other requirements. The report hedges the figure with "0 % by acceptance readback", and the 16 versus 17 arithmetic is consistent: #320 is OWNER-GATED, not PROVEN. Even so, the 16.8 % headline over-states what the evidence shows.

**Fix.** In `intel_reconciliation.py`, accept a reading as valid evidence only for the requirements whose acceptance text it addresses. Reclassify the rest as "needs operator readback" and restate the percentage.

### L-1. Stale figures after an outage are still graded MEASURED, contradicting the comparison's own uncertainty note

- **Location:** `intel/watchlist.py:273-300`, `:313-314`.
- **Scenario.** A shop that read fine once and has since failed keeps its last `shop` counters and stored listings, graded `MEASURED` with `as_of=last_ok_at` (probe P7). The report's `uncertainty` field says "a shop whose observation is not ok has UNKNOWN figures, never zeros". The values are not zeros, but they are not UNKNOWN either, and nothing marks them stale.
- **Fix.** When `state != "ok"`, grade the figures `STALE`, carrying `as_of`, or `UNKNOWN`. Make the note match the code.

### L-2. Zero reviews read renders as 0 recurring complaint themes

- **Location:** `intel/watchlist.py:173-176`, `:298-300`.
- **Scenario.** If `getReviewsByShop` returns nothing, `complaint_themes` reports `measurable: False`, but the comparison stores `recurring_themes = 0`, graded `DERIVED` (probe P6). An unmeasurable value reads as a measured zero.
- **Fix.** Store `None` when `reviews_read == 0` or `measurable` is false, so that `_grade` yields UNKNOWN.

### L-3. The anchor's observation state comes from whether rows exist, not from scan health

- **Location:** `intel/watchlist.py:278`.
- **Scenario.** Watchlist state is never saved for Mrs J. Her row shows `ok` if any listing rows exist and `never` otherwise, whether or not `mjs.scan` is currently failing (probe P7).
- **Fix.** Read `observe`'s per-benchmark scan health for the anchor, or label the field `rows_present`.

### L-4. Lesson-deferred gaps are re-decided every day forever, and keep Laura DEGRADED

- **Location:** `intel/watchlist.py:411-412`, `:533-544`.
- **Scenario.** A deferred gap stays `UNCOVERED`. Each new UTC day `summary()` counts it as waiting, so Laura delegates the review, which defers again (probe P4).
  - It is bounded: one job per day, and `REVIEW_LIMIT` per run.
  - `bus.acted_on` dedupes, so acted-on counts are not inflated.
  - But Laura's intelligence provider never returns to OK, and each daily deferral counts as `work_done=1`, so the useful-work judge cannot flag it.
- **Fix.** Move a deferred gap to `NOT_PURSUING` with the lesson as its reason, or exclude deferred gaps from `waiting` until new evidence changes the gap's `validated_at`.

### L-5. Amplification counts a refused or parked follow-on as a failed attempt

- **Location:** `creative/family_engine.py`, `amplify` (`failed_attempts` increment).
- **Scenario.** This is the same class as H-1. A follow-on tournament refused at the ceiling counts toward `AMPLIFY_MAX_ATTEMPTS`, and the family is then held. The state is only a memory record, not a published lesson, and it stays inert until orders exist. It is therefore Low.
- **Fix.** Use the same outcome classification as H-1.

### L-6. Per-shop credential refusals have no backoff, and each scan resolves the shop three times

- **Location:** `intel/watchlist.py:159-162`, `:163-176`.
- **Scenario.**
  - The `scan_due` deferral applies only when `state == "ok"`. A shop in `credential_refused` or `source_outage` is read every 6 hours indefinitely. The global `auth_refused` guard covers the key-wide case only.
  - `resolve_shop` is called by `scan_member`, `observe.scan` and `scan_reviews`, so each scan makes three `findShops` calls.
  - This is official-API use within the same pattern as Mrs J, and nothing tries to get past a refusal. It is only polite-use hygiene.
- **Fix.** Back off exponentially on `consecutive_failures`, and pass the resolved shop through.

### L-7. Three report figures are not in `intel/evidence/`

- **Location:** `OWNER_REPORT.md`.
- **The three figures:**
  - "Month spend is CA$81.35 of CA$100 (`/api/verify`, 17:24Z)": there is no evidence file for `/api/verify`;
  - "Production runs **b2e49455**": the evidence files name 051dbee2, pre-SECPATCH;
  - "Etsy refuses that with 403" for the trending-patterns page.
- **Fix.** Add the captures to `evidence/`, or label these "from session notes, not captured here".

### I-1. A misplaced comment in `autonomy/departments.py`

- **Location:** `autonomy/departments.py:48-49`.
- **Detail.** The `research.sweep` comment was moved onto the `intel.opportunity_review` line. Cosmetic.

### I-2. Test gaps

There is no test for any of the following:

- `summary()` after an unconfigured scan, or after an auth-refused scan (M-1);
- whether MJs refuses the other watchlist shops' URLs. Probe P2 verified the full matrix is clean, so this is only coverage;
- the downstream cost of jobs the scan or review queue (M-3);
- a DONE design job that succeeded (H-1).

### I-3. The registry widening also widens `benchmark_health`

- **Location:** `intel/mission_runtime.py:1338`; `intel/benchmarks.py:376-392`.
- **Detail.** All four shops are now resolved daily. The official API is preferred. The rendered-page browser worker is used only if it is configured and has a successful probe. It is pre-existing, rate-bounded and self-identifying, and it records only status and final URL, never page content. That is not a scrape of competitor content. It is listed so the owner knows three more Etsy shop pages may be fetched by that path when it is enabled.

---

## Answers to the seven questions

1. **Content and access rules.**
   - **Storage.** No new storage beyond the existing rules:
     - listings go through the unchanged `observe.scan`;
     - review themes are deterministic keyword counts, never quoted (`observe.complaint_themes`);
     - the comparison is alias-only and checked by `_assert_no_content`;
     - AI-use is `UNKNOWN` with `hypothesis_only: True`.
   - **URLs.** The only new URLs are the owner-supplied shop URLs in `benchmarks.py` and `watchlist.py`, the same practice as for MJs.
   - **Access.** Etsy is accessed only through `etsy_public.PublicReader` (the official API v3), apart from the pre-existing `benchmark_health` browser path (I-3).
   - **Refusals.** Nothing tries to get past a 403. A key-wide refusal waits for `etsy.probe`. A per-shop refusal is recorded, but is retried without backoff (L-6).
2. **Paid calls and spend.**
   - No new paid call site, model or vision. Vision stays anchor-only: `intel.gallery_analysis` hard-codes `MJS_KEY`.
   - Every paid path reached is the existing `creative.tournament`, behind `_ceiling_gate` and `failover.job_gateway`.
   - New *origination* of paid work is under-declared: M-2, M-3 and M-4.
3. **Laura's authority.**
   - With the switch OFF there is no model call (probe P8, and `lc.available` checks `ceo_model_enabled()` first). Nothing here turns a switch on.
   - Nothing publishes, writes to Etsy, changes budgets, or bypasses owner gates, Product Truth, the pre-engineering gate or certification.
   - The delegated chain can start paid tournaments under a CA$0 constitution check (M-2).
4. **Assertion integrity.**
   - AI-use and "winner" are kept as hypotheses or measured counts: amplification needs `AMPLIFY_MIN_ORDERS`, and below it stays UNMEASURED.
   - Failures: an unmeasured design outcome becomes an `observed` lesson (H-1); UNKNOWN reads as OK (M-1); unmeasurable and stale values show as 0 or MEASURED (L-1, L-2, L-3).
5. **Tests.** `test_cert_mjs` was not weakened. It is generalised to `n = len(REGISTRY)`, with stricter cross-shop expectations, and the full refusal matrix holds (P2). All touched suites pass. Coverage gaps are listed in I-2.
6. **Report honesty.**
   - Every production job count in `OWNER_REPORT.md` matches the evidence capture.
   - INTELREC is correctly described as unreviewed, undeployed and offline-only, and the offline chain example is labelled "OFFLINE and not production evidence".
   - Over-claims: M-5 and M-3, plus unevidenced figures (L-7).
7. **Runtime safety.**
   - Bounded per run and per gap. Idempotency keys are per attempt.
   - `coverage.upsert` never resets state, so there is no reopen loop. Per-shop faults are isolated, and there is no retry loop inside a job.
   - Residual: the daily deferral cycle (L-4) and no backoff on refusals (L-6).

## Minimum to ship in SHADOW

1. **H-1:** classify design outcomes from what the job actually produced. A refusal or park is not an attempt, and a lesson is not `observed` unless its outcome was measured.
2. **M-1:** an unobserved, unconfigured or refused watchlist must not read OK.
3. Recommended in the same pass, because they are small: correct the CA$0 labels and SAFE_GENERATED reasons (M-2 and M-3, documentation part), and key breakthrough tournaments per arena rather than per shop (M-3).
