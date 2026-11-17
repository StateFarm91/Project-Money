# Independent review: P0-PORTFOLIO-ACT, `origin/opus2/p0-portfolio-act-fo` @ ee5dbeee

- **Branch:** `git branch -r --contains ee5dbeee` gives `origin/opus2/p0-portfolio-act-fo`.
- **Base:** ee5dbeee contains the fix-only primitive `claude/w6-fix-only-rebuild` @ 0f2de815, and 0f2de815 is an ancestor of `claude/w6-INTEG1` @ 5913931f.
- **Scope:** I reviewed `git diff 0f2de815 ee5dbeee` in full: 4 files, +610/-8.
  - `growth/portfolio_act.py` (new, 290 lines)
  - `runtime/pipeline.py` (+18/-8)
  - `autonomy/autonomy_map.json`
  - `tests/test_p0_portfolio_act.py` (new)
- **Trial merge:** worktree `/home/user/bl-runs/wt-rv-pf` at origin/claude/w6-INTEG1, then `git merge --no-commit ee5dbeee`. **No conflicts.** `pipeline.py` auto-merged. I committed nothing and pushed nothing, and the worktree has been removed.
- **Interpreter:** `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with `PYTHONPATH=src:tests`, every suite as a plain script.
- **Scripts:** repro and mutant scripts are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rvpf_ee5/` and `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/pfmut/`.

## Verdict: DO NOT SHIP ee5dbeee (one MEDIUM, small fix)

The safety properties the brief asks about all hold:
- no live listing, price or publication is changed;
- no spend;
- the chain stops before `launch.plan`;
- the primitive's contract is used, not re-implemented;
- every finding from f3bea437 is fixed.

What blocks it is owner-queue noise.

SEO_PROBLEM's "fix" is a deterministic re-run of `listing.seo` on the same inputs. On a real certified chain it produced a candidate **byte-identical** to the live copy (title, tags and description all equal). That candidate was then put to the owner as a `listing.live_update` card. After the owner declined it, the next week's review rebuilt it again and opened a **new** card offering the **same** candidate_sha. The same will happen every week while the verdict stands.

This brings back the f3bea437 F5 behaviour for the SEO path: a decided card is asked again every week. The branch fixed F5 for its own RETIRE/REWORK cards with a 90-day quiet period. It is also an owner interruption that is not a genuine OWNER ACTION REQUIRED, which CLAUDE.md forbids.

## Prior-finding status (review PORTFOLIO f3bea437)

No written report for the later d564a059 review exists:
- I grepped `origin/claude/w4-INTEG8-next` and `origin/claude/w6-INTEG1` under `brambleloop/research` for "d564a05".
- I checked the scratchpad.
- `COORDINATION.json` and `dispatch/events/opus2.jsonl` on INTEG8-next show only `review_requested` for d564a059 (and a queued item "PORTFOLIO-FO-QUEUED"), with no verdict.

So the table below is against f3bea437 only. d564a059 is not in `0f2de815..ee5dbeee`; ee5dbeee re-merges fix-only on top of it.

| # | f3bea437 finding | status at ee5dbeee | evidence |
|---|---|---|---|
| F1 HIGH | A live listing is reset to a local `draft` | **FIXED** (by the primitive) | The fix_only `listing.seo` on a live row returns from `_fix_only_candidate` before persistence. The e2e test (published listing, price 12.34, Etsy id) asserts state, price, copy and Etsy id are unchanged. Mutants M17 and M18 (live guards removed) are killed by the e2e test. |
| F2 HIGH | The chain is driven to `store.publish` | **FIXED** | `fix_only: True` (`portfolio_act.py:230-235`). `listing.seo` stops before `launch.plan`, and `launch.plan` refuses fix_only. The e2e test asserts no DOWNSTREAM job ran. M01 (fix_only False) is killed by the e2e and the unit test. |
| F3 MED | Stale inputs revert the live price | **FIXED** | Live: nothing is persisted. Draft: `keep_price`. pricing.position is not in this path. Version and release are pinned to the current certified release (`:231-232`; M09 killed, M10 equivalent). |
| F4 MED | The cap starves late-sorting slugs | **FIXED** | Rotation is least-recently-acted first (`:178`). M08 is killed by two tests. |
| F5 MED | Cards are per week, and a decided card is re-asked | **FIXED for RETIRE/REWORK; reintroduced for SEO via `listing.live_update`** (see N1) | Repro `repro_noop_card.py` |
| F6 LOW | Chain token truncated to 12 chars | **MOOT** | Under fix_only nothing downstream is keyed by `chain_key`. `listing.seo` itself is keyed `seo-fix:<slug>:<week>` (full week). `portfolio:2026-W45`[:12] == `portfolio:20`, so weeks would collide, but only on `launch.*` keys that are never created. |
| F7 LOW | Local date, concurrent-review cap race, LIKE `_`, twin-only count | **Partly open** | `_scan_date` still uses `date.today()` (`pipeline.py:352-354`). The cap still races across runs in the same week (M07 survives). The twin-only count is intentional and documented. LIKE `_` is still unescaped (slugs are kebab-case, so no impact). |
| F8 LOW | Test gaps (guard-withheld label, pinned cap, live e2e) | **FIXED** | M05 (pre-guard label) killed; M06 (cap 50) killed; the e2e live test exists and passes. |

## Findings

### N1 MEDIUM: the SEO "fix" offers the owner the unchanged live copy, and re-asks every week after a decline

**Where:**
- `growth/portfolio_act.py:207-238`. The SEO branch's once-per-week rule (`_history`, `:102-115`) looks only at `seo-fix:` Job keys. It never looks at the `listing.live_update:<slug>@<version>` card the primitive raises, or at whether the owner decided it.
- The primitive `runtime/release.py:2110-2198` (`_fix_only_candidate`) never compares the candidate with the live row. It raises the card even when they are identical.
- `owner_queue.ensure` (`ops/owner_queue.py:180-216`) inserts a new row whenever no open row exists.

**Repro 1** (`rvpf_ee5/repro_noop_card.py`, real certified chain via `test_w6_fix_only_rebuild.chain()`):
1. Set the listing to published with an Etsy id and add 4000 impressions and 4 visits.
2. Run `portfolio.review` and drain the queue.

Output:
```
candidate == live copy: {'title': True, 'tags': True, 'description': True} sha 1c08e356f2da172c
card open: True
```
3. Close the card WITHDRAWN ("keep the current copy"), run `portfolio.review` with `as_of` +7 days, and drain again.

Output:
```
week+1 live_update cards (id, done): [(1, True), (2, False)] same candidate re-offered: True
```

**Repro 2** (`rvpf_ee5/repro_reask.py`, unit level): after a withdrawn `listing.live_update` card, `act()` queues `seo-fix:coaster-seo:2026-W46`, then `W47`, then `W48`, with `skipped: []` each week.

**Scenario:** a live listing has low click-through. The deterministic generator returns the same copy, because the inputs have not changed. Every Monday the owner gets a 10-minute "compare and apply" card for a no-op. Declining it does nothing, and the shop's 5-a-week SEO budget is spent on these repeats. The rebuild is not justified by any deterministic defect in the copy: SEO_PROBLEM is an exposure ratio, not a copy-gate failure. A rebuild whose output equals the input is not a fix.

**Fix (small, in portfolio_act; no primitive change required):**
- Skip SEO for a SKU whose `listing.live_update:<slug>@<version>` card was decided within `DECIDED_QUIET_DAYS`, by reusing the card branch's `decided_at` logic. Restate in place, without rebuilding, when that card is open.
- Better still, and best fixed in the primitive (route to its owner): do not raise or keep a live_update card when the candidate equals the live row's title, tags and description. Record `no_change` instead.
- Add a test that declines the card and asserts no `seo-fix` job the next week.

### N2 LOW: the "skip when no earlier listing.seo" and "skip SEO without a certified release" paths are untested
- **Where:** `portfolio_act.py:213-225`.
- **Mutants:**
  - M04 survived: the inputs-None skip is removed and the inputs are fabricated from `{"slug": ...}`. The docstring promises "skipped by name and never invented", and nothing pins it.
  - M14 survived: the `rel is None` skip is turned into a fall-through, which would raise `TypeError` on `rel["slug"]` and fail the whole `portfolio.review` job. `test_no_certified_release_is_skipped_by_name` covers QUALITY only.
- **Fix:** add two short `PA.act` unit tests. One uses `_release(..., seo_history=False)` with SEO_PROBLEM and asserts it is skipped with "no earlier listing.seo" and that no `seo-fix` job exists. The other uses an uncertified SEO slug.

### N3 LOW: the owner card's cost field is not pinned
- **Where:** `portfolio_act.py:148`.
- M15 survived: `max_cost_cad: 0.0` was removed from `_card` and no test failed.
- The card does carry cost, minutes, consequence and an exact step (verified by reading), but a regression would pass silently. Assert the four fields in `test_cards_are_per_sku...`.

### N4 LOW: the weekly cap can be exceeded by a second review in the same week (F7, still open)
- **Where:** `portfolio_act.py:172-176`. `budget` is computed once per kind from the rows present at the start.
- Two `portfolio.review` runs in one ISO week with different label sets (an `as_of` re-run, or concurrent workers) can each act on up to 5 SKUs. Idempotency keys stop per-SKU duplicates but not the total. M07 (`budget = WEEKLY_CAP`, ignoring earlier runs) survived: no test runs two reviews with different SKUs in one week.
- The impact is bounded: at most 2x the work, still $0, still fix_only.

### N5 LOW: `act()` runs after the PortfolioReview row is committed and is not guarded
- **Where:** `runtime/pipeline.py:3227-3239`.
- An exception in `act()` fails `portfolio.review` after its `PortfolioReview` row was committed in a separate session. Possible causes are a `_last_seo_inputs` scan error and an enqueue error.
- A retry then writes a second PortfolioReview row, and the `portfolio.reviewed` audit is never written for the failed attempt.
- Either enqueue inside one transaction, or catch, audit and return `acted: {"error": ...}`. A failed act must not fail the classification.

### N6 INFO: `today` uses the local date, not UTC
- **Where:** `pipeline.py:352-354` (`date.today()`).
- This is pre-existing (F7), but week keys are now derived from it. Use `datetime.now(timezone.utc).date()`.

### Checked, no finding
- **Live listings, prices, publication:**
  - nothing in the delta writes `Listing`, `price`, `etsy_*` or `store.*`;
  - QUALITY enqueues the same four read-only checks `gate.quality` uses;
  - RETIRE/REWORK are cards only (the test asserts no job besides `portfolio.review`);
  - SEO goes only through `listing.seo` with `fix_only: True`, whose live path persists nothing and whose only enqueue (`launch.plan`) is skipped.
- **Spend:**
  - no paid call in the delta;
  - on the live path `_fix_only_candidate` returns before `exported_review`, the only possible paid call in `listing.seo`, which is image_vision-gated through `gateway.routing` and reuses filed reviews;
  - the V0 gate suite passes on the merge;
  - cards are CA$0.
- **Fix-only contract:**
  - `_fix_only_candidate(..., blocking=blocking)` is required and not bypassed;
  - the card is `listing.live_update:<slug>@<version>` naming candidate_sha;
  - refusal withdraws the card;
  - `_last_seo_inputs` applies `without_fix_only` (`taxonomy_drift.py:161-163`), so a portfolio run's inputs never leak the bound into a later drift re-certification;
  - `launch.plan` backstop;
  - pricing.position is not in this path.
  - Nothing is re-implemented and nothing the fix-only reviews fixed is reintroduced in code. N1 is a caller-level policy gap.
- **Idempotency / 12-char truncation:**
  - SEO jobs are keyed `seo-fix:<slug>:<YYYY-Www>` with the full week;
  - QUALITY jobs are keyed `quality-fix:<check>:<slug>:<week>`;
  - the `rebuild` token `portfolio:<week>` truncates to `portfolio:20` in `chain_key` for every week, but under fix_only no `chain_key`-keyed stage is ever enqueued, so there is no collision in practice.
  - **Latent risk:** if a future change lets a fix_only chain continue, all weeks' `launch:`/`publish:` keys collide on `portfolio:20` and only the first ever runs. Use a ≤12-char token such as `pf<YYYYWww>` (`pf2026W45`, 9 chars).
- **pytest:** neither `tests/test_p0_portfolio_act.py` nor the three companion suites import pytest. It runs as a plain script with its own `__main__` runner.
- **autonomy_map.json:** on the merged tree, the regenerated map is identical to the committed one apart from `generated_at`.

## Test table (merged tree, origin/claude/w6-INTEG1 + ee5dbeee, plain scripts)

| suite | result | time |
|---|---|---|
| tests/test_p0_portfolio_act.py | 10/10 OK, "0 failed", rc=0 | 1043s |
| tests/test_w6_fix_only_rebuild.py | "0 failure(s)", rc=0 | 1080s |
| tests/test_cert_rebuild_chain.py | "PASS: 0 failing", rc=0 | 523s |
| tests/test_w5_v0_paid_provider_gate.py | 52/52 passed, rc=0 | 243s |
| autonomy map generator vs committed | identical (excluding generated_at) | n/a |

The box was heavily loaded by other reviewers (load average about 15 on 4 cores), so the times are inflated.

## Mutant table

Mutants were run on a copy of the merged tree with `test_p0_portfolio_act.py`. The live e2e test was included only for M01 and the primitive (M16-M18) mutants. M00 is the unmutated baseline.

| id | mutation | result |
|---|---|---|
| M00 | baseline (no change) | passes (control) |
| M01 | SEO enqueue `fix_only: False` | KILLED (unit + e2e) |
| M02 | SEO same-week skip removed | KILLED |
| M03 | SEO budget decrement removed | KILLED |
| M04 | no-earlier-listing.seo skip removed; inputs fabricated | **SURVIVED** (N2) |
| M05 | act on the pre-guard label (`discard_verdict_withheld`) | KILLED |
| M06 | `WEEKLY_CAP = 50` | KILLED |
| M07 | cap ignores earlier runs in the same week | **SURVIVED** (N4) |
| M08 | rotation by slug only | KILLED |
| M09 | release hash not pinned to the current release | KILLED |
| M10 | version not pinned | SURVIVED (equivalent: `_last_seo_inputs` already filters by version) |
| M11 | 90-day decided quiet removed | KILLED |
| M12 | open card not restated (a new card is created) | KILLED |
| M13 | QUALITY same-week skip removed | KILLED |
| M14 | SEO `rel is None` skip falls through | **SURVIVED** (N2) |
| M15 | card `max_cost_cad` dropped | **SURVIVED** (N3) |
| M16 | primitive: `_fix_only_candidate` call disabled (`_persist_listing` live guard remains) | SURVIVED (defence in depth: `_persist_listing`'s live guard still keeps the row and card; the candidate_sha / refusal-withdraw behaviour belongs to the primitive's own suite, not this one) |
| M17 | primitive: `_fix_only_candidate` and the `_persist_listing` live guard both disabled | KILLED (e2e) |
| M18 | primitive: both guards, the listing.seo launch stop and the launch.plan backstop disabled | KILLED (e2e) |

**Score:** 18 mutants: 12 killed, 6 survived. Of the survivors, M10 is equivalent and M16 is defence in depth; M04, M07, M14 and M15 are real test gaps (N2-N4).

## Required before SHIP
1. **N1:**
   - Do not queue an SEO fix-only rebuild for a SKU whose `listing.live_update:<slug>@<version>` card is open, or whose card was decided within `DECIDED_QUIET_DAYS`.
   - Add a test: decline the card, run the next week, and assert no new `seo-fix` job and no new card.
   - Separately, route to the primitive's owner: suppress or record `no_change` when the candidate equals the live copy.
2. **N2/N3:** add tests for the SEO no-history skip, the SEO uncertified skip, and the card's cost, minutes and consequence fields.
3. **Optional:**
   - N4: count the week's acted work inside one locked transaction.
   - N5: guard `act()` so a failure does not fail or duplicate the review.
   - N6: use the UTC date.
   - Use a ≤12-char rebuild token.
