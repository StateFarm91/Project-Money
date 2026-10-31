# Independent security & integrity review — W5-CONCEPT at 933bf742

- **Subject:** `claude/w5-CONCEPT` @ `933bf742`, diffed against `b0133916`.
- **Reviewer:** an independent reviewer that did not write the change. It judged the code, not `CONCEPT_INTAKE.md`.
- **Date:** 2026-10-31 (UTC)
- **Method:** I read the code. I reproduced each finding with scratch scripts that import the subject's own test helpers. I ran 27 single-point mutations against the touched suites, and ran the requested suites one at a time with `nice -n 19`. Disk was fine before the runs: 30 G free.

## Verdict: **DO NOT SHIP** (yet)

The pipeline is mostly sound:
- Evidence must resolve to recorded findings and sources.
- The construction, children's, novelty and competitor-title refusals all work.
- An approval enqueues only `radar.score`.
- The static POOL behaviour is unchanged.
- The seed-shop "not accessible" path is honest.

Two defects break the brief's "no fabrication / gates" requirement. Both fixes are small:

- **F1 (HIGH):** an approved concept is never withdrawn when its evidence goes stale or expires. It stays in the scored pool and can still reach `cir.draft` on evidence intake itself now refuses.
- **F2 (MEDIUM):** `radar.score` judges an intake concept partly on taste fields carried by the job. With no vision judgement on record, a job-supplied `thumbnail_reads_small` got the concept past the pre-engineering gate to `cir.draft`. This contradicts the code comment "read here, never from the job".

Also: 12 of the 23 intake mutations survive (F4). Several key refusals have no test that kills them.

The gate holds today only because `image_vision` is CLOSED. Today nothing reaches `cir.draft` without a recorded vision judgement. `rescore_judged` exists to send a concept on as soon as one lands, so F1 and F2 should be fixed before that capability opens.

## Test runs (one at a time, `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| suite | result |
|---|---|
| test_w5_concept_intake | pass (0 failures, 14 s) |
| test_w4_intelrec_watchlist | pass (25 s) |
| test_radar | pass (3 s) |
| test_shadow | pass (1027 s) |
| test_vacuity | pass (11 s) |
| test_v11_autonomy_timeline | pass (0 failing, 128 s) |
| test_route_auth_default_deny | pass (8/8, 9 s) |

The container had no `sqlalchemy`, so the first attempt failed at import. I installed `requirements.lock` and `requirements-test.lock` with `--require-hashes` and re-ran.

## Findings

### F1 — HIGH — approval is never withdrawn when its evidence goes stale, expires or becomes unresolved; refused rows pile up daily
`radar/intake.py` `evaluate()` supersedes an earlier APPROVED row only when a newer proposal is approved. The fingerprint includes evidence `quality`, which `research_evidence` recomputes from `today` (freshness decay, then expiry). So each day past the freshness window:
- a new row is evaluated and REFUSED (quality below 0.40, then "expired (F-433)");
- the earlier APPROVED row stays APPROVED.

`approved_rows` and `pool_with_intake` keep feeding it to `radar.scan`, `queue_scores`, opportunity review and `rescore_judged`. That last one re-enqueues `radar.score`, and therefore `cir.draft`, as soon as a vision judgement is recorded. A task later re-marked unresolved behaves the same way.

**Reproduction:**
- Setup: the subject's `_answered_task` and `_proposal`, then `intake.run(today=TODAY+d)` for d = 0..185.
- Evidence: `fresh_for_days=90`, `quality=0.65`, task `expires_on` = TODAY+90.
- Days 0–84: one row, `approved`.
- From about day 85: one new `refused` row per day.
- End state: **91 rows**, and the original row is **still `approved`**. `approved_seeds(db)` still returns `tide-line-table-runner`.

Consequences:
- A stale-evidence concept stays in the scored pool, against the module's own F-433 rule.
- About `fresh_for_days` refused rows per proposal accumulate, and `radar_concepts` has no retention rule (`ops/retention.py` does not mention it).
- Each churned row uses one of the 10 per-run evaluation slots. Ten decaying proposals would starve all other candidates for about 90 days, including every family candidate, because those are listed after the research ones.

**Fix:**
- In `run`, when re-evaluation of the same `(source_ref, slug)` is refused, move the prior APPROVED row to `superseded` (or a new `withdrawn` state) and audit it.
- Or: in `approved_rows`, re-check that the row's research task is still ANSWERED, unexpired and not unresolved.
- Leave freshness out of the fingerprint (or round quality to coarse bands) so decay does not mint a row a day, and add a retention rule for refused or superseded rows.

### F2 — MEDIUM — `radar.score` uses taste fields from the job for intake concepts
`runtime/pipeline.py` `handle_radar_score` calls `intake.gate_inputs(ctx.db, seed.slug, {})` (with an empty dict) and then `c.update(...)`. The pop of `thumbnail_reads_small`, `craft_impression` and `concept` in `gate_inputs` therefore runs on the empty dict, never on the job inputs `c`.

When no judgement is on record, the job's own values survive into `preengineering.gate_concept(ctx.db, c)`. That includes a job-supplied `concept` dict, which `concept_from` prefers over the top-level fields. This contradicts the comment at that call site: "read here, never from the job".

**Reproduction:**
1. Approve the subject's runner concept and run its own `radar.score`: the gate returns `concept.gate_waiting`, and there are 0 `cir.draft` jobs.
2. Enqueue `radar.score` with `score_concept(seed).to_dict()` plus `thumbnail_reads_small=True, craft_impression=4.9`.
3. Result: `concept.gate_passed`, and **1 `cir.draft` job**, with no vision judgement recorded.

Today every `radar.score` producer is code-controlled (radar.scan, coverage handoff, queue_scores, the Laura follow-on with fixed inputs), and I found no API route that takes arbitrary job inputs. So this is a defence-in-depth gap rather than a live hole. POOL concepts already have the same exposure. Mutation M19 (removing the pop entirely) survives, which shows no test guards it.

**Fix:** `c = intake.gate_inputs(ctx.db, seed.slug, c)`.

### F3 — MEDIUM — a proposal can attach a strength score with a judge's name that no judge produced
`_clean` keeps every `preengineering.BRIEF_FIELDS` key in `brief`. That includes `strength_score`, `strength_score_source` and `benchmark_scores`. These are stored on the row and handed to the gate by `gate_inputs`. The #125 top-decile check (`_top_decile`) accepts a brief score whenever it names a judge. It only applies to the FLAGSHIP make lane, and the proposal chooses that lane through `maker_hours`.

**Reproduction:** a proposal with brief `{"strength_score": 9.9, "strength_score_source": "model_jury:opus", "benchmark_scores": [1]*10}` is approved, and `gate_inputs()` returns `strength_score=9.9, strength_score_source="model_jury:opus"`.

This is a judged value supplied as input, the same class as the taste fields that *are* stripped. It only matters once `image_vision` opens, because `_premise_thumbnail` holds the gate today.

**Fix:** strip `strength_score`, `strength_score_source` and `benchmark_scores` (and `board_image`, which should only come from the grid record) from proposal briefs.

### F4 — MEDIUM — tests do not discriminate several key refusals
Each mutation was a single-point change in the `/tmp/mut` worktree, run against `test_w5_concept_intake` (W*: against `test_w4_intelrec_watchlist`). The file was restored after each run, and the worktree was confirmed clean afterwards.

| killed | survived |
|---|---|
| M1 self-cited ref accepted · M2 unanswered task accepted · M6 quality floor removed · M7 construction verdict off · M8 children's prohibition off · M9 competitor-title copy off · M11 novelty floor off · M16 family cap 2→99 · M17 idempotency off · M18 supersession off · M20 gate skipped for intake · M21 approval also enqueues `cir.draft` · W2 not-accessible writes `last_ok_at` · W3 404 treated as outage · W4 seed shop dropped | **M3** expiry check off · **M4** missing-confidence refusal off · **M5** fact-grade requirement off · **M10** near-identical competitor listing (`_matches_a_listing`) off · **M12** POOL-slug duplicate off · **M13** POOL-title duplicate off · **M14** database-duplicate off · **M15** evaluation cap 10→10⁶ · **M19** `gate_inputs` taste strip off · **M22** family "already decided" skip off · **M23** `rescore_judged` without a judgement · **W1** `summary()` not DEGRADED for a limitation |

- M12–M14 survive one at a time because the duplicate test is caught by other, overlapping checks, so each check is untested on its own.
- W1 survives because the test scans at a fixed `now` of 2026-10-27, but `summary()` reads the real clock. After 48 h the other shops are `stale`, which makes the status DEGRADED regardless. That `DEGRADED` assertion has passed whatever the code does since 2026-10-29.
- The changed watchlist tests are legitimate. The counts moved by `+SEEDS` only because the fixture reader now serves the four seed shops. The exact-list assertions were extended, not loosened, and no assertion was weakened.

**Fix:** add one targeted test for each surviving mutation. For W1, pass `now` to `summary` or use a fresh scan.

### F5 — LOW — `release._seed_for` prefix match gives some intake slugs a POOL seed
`release._seed_for` returns the first POOL seed whose slug is a *prefix* of the requested slug, before it looks in the database. Intake refuses only *exact* POOL slugs. A research proposal slug such as `chunky-ribbed-scarf-harbour-fog` therefore passes intake, but release resolves it to POOL `chunky-ribbed-scarf`:
- `release._seed_for("chunky-ribbed-scarf-harbour-fog").slug == "chunky-ribbed-scarf"`, verified.
- Pricing, listing SEO, marketing and the launch plan would use that seed's category, price and season, under the provenance `radar.pool:chunky-ribbed-scarf`, while `pipeline` scores the intake seed.

Family variations are not affected: I checked every family × category and none is shadowed.

**Fix:** refuse proposal slugs that start with a POOL slug, or check exact database matches first in release.

### F6 — LOW — callers of `_seed_for` / `product_seed` that were not given `db`
These callers were not updated:
- `release.py:941` (pricing peers), `:2596` (`_collection_siblings`), `:2703` (member-collection trigger), `:2743` (`collection.assemble`);
- `pipeline.product_seed`, used by `brand/storefront.py:462`, `launch/readiness.py:869` and `pipeline.py:1078` (fallback product_class for teardown QA).

For an intake concept each of these returns `None`. Nothing breaks: the results degrade to "excluded from peers", "no siblings", "UNMEASURED strength" or "uncategorised", and the teardown check prefers `cir.category`. But intake products are invisible to storefront strength and readiness representatives. The author's own `release.py` fix covers only `_product_record`, `handle_pricing_position`, `handle_launch_plan` and `handle_marketing_schedule`.

### F7 — INFO
- **No production producer of research proposals.** `attach_proposal` has no caller in `src/`, only in tests. Only the family source is live. This is disclosed honestly at `CONCEPT_INTAKE.md:164`.
- **Generic-only titles skip the competitor-title check.** It runs only when the title has specific tokens (`if t_tok`). A title made entirely of `GENERIC_TOKENS` is never compared, even when it is identical. This is narrow: the novelty and POOL checks usually catch such titles.
- **Concurrent runs can collide.** `fingerprint` is `UNIQUE`, so two overlapping intake runs would raise IntegrityError rather than duplicate rows. That is safe, but there is no handler for it.
- **Watchlist state can be overwritten.** The `not_configured` and `credential_refused` paths in `scan_all` overwrite a `not_accessible` state. `summary()` then reports UNKNOWN, which is still honest.

## Answers to the brief

1. **No fabrication.**
   - Refs must be the task's own findings or sources. Self-citing is refused, and M1 is killed.
   - Unanswered and unresolved tasks, expired tasks and missing confidence are refused at evaluation time. Confidence is read from the task row, never from the proposal.
   - `risk_class`, `whitespace` and `make_lane` are derived (`"A"`, measured distance, hours), never taken from the proposal. Extra seed keys are dropped.
   - Taste fields are stripped from the *proposal*, but not from the *job* (F2), and brief strength scores pass (F3).
   - Evidence that later expires does not withdraw an approval (F1).
2. **Gates.** With `image_vision` CLOSED the gate holds intake concepts at WAITING (M20 killed), except through job-carried taste fields (F2). The checks themselves work, though several are untested on their own (F4):
   - children's prohibition, plus the block on an unreviewed policy change;
   - duplicate and novelty checks;
   - competitor title and near-identical listing.

   Approval enqueues only `radar.score` (M21 killed). `rescore_judged` also enqueues only `radar.score`, and only when a judgement exists and no `draft:<slug>` exists.
3. **Static POOL behaviour.** Unchanged: `_seed_for(slug)` with no `db` is identical, `pool_with_intake` equals `POOL` when there are no rows, and the suites pass. The new optional `db` argument breaks no caller (all default to `None`), but see F5 and F6 for callers that miss intake concepts.
4. **Loops and storms.**
   - The 10-evaluation and 2-variation caps hold; the family cap is tested (M16), the evaluation cap is not (M15).
   - Idempotency on unchanged input is correct, and supersession works for re-approval.
   - Growth of `radar_concepts` is bounded but churns daily under evidence decay, and nothing prunes the table (F1).
5. **Seed shops.** Honest:
   - A 404/410 or "not found exactly" is recorded as `not_accessible`, with a dated limitation and kept monitoring.
   - No `last_ok_at`, `listings_seen`, shop counters or `BenchmarkListing` rows are written (W2 and W3 killed).
   - The shop is reported DEGRADED, never OK, in code; the test does not discriminate (W1).
   - When accessible, seed shops use the same `observe.scan` path as the existing members. The comparison report stays alias-only (`_assert_no_content`), and no instructions, charts or photos are stored.
6. **Tests.** See F4.

## Required before SHIP
F1, F2, and tests that kill M3, M4, M5, M10, M15, M19 and W1. F3 and F5 are strongly recommended.

All seven requested suites pass at 933bf742. The defects above are not caught by them.
