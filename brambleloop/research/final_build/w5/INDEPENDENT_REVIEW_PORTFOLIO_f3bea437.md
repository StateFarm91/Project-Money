# Independent review: P0-PORTFOLIO-ACT, `origin/opus2/p0-portfolio-act` @ f3bea437

- Base: `claude/w6-INTEG1` @ f5c3976d. I reviewed `git diff f5c3976d f3bea437` in full: 4 files, +377/-7.
- Worktree: `/home/user/bl-runs/wt-rev-portfolio`, detached at f3bea437, clean. I never committed or pushed.
- Interpreter: `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with `PYTHONPATH=src`. Suites ran one at a time.
- Repro scripts are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev/`: `repro_seo_live.py` (log in `pact_repro.log`), `repro_pact_units.py` and `mut_pact.py`.

## Verdict: DO NOT SHIP f3bea437

The RETIRE/REWORK and QUALITY paths are safe. The SEO_PROBLEM path is not.

SEO_PROBLEM only fires on a listing with at least 300 impressions, so the listing is already live on Etsy. The rebuild:
- moves that live listing back to `draft` in the local record;
- puts back the price from the last run's inputs, overwriting the current one;
- drives the release chain to `store.publish` with no owner gate. This is the exact path FMBATCH1 F-1 made opt-in for taxonomy drift.

It also changes nothing on Etsy, because `store.publish` refuses a listing that already has an Etsy id. So the "fix" never reaches a buyer, and it damages the local record every week.

## Test results (f3bea437)

| suite | result |
|---|---|
| tests/test_p0_portfolio_act.py | 5/5 OK, "0 failed" |
| tests/test_portfolio.py | all OK |
| tests/test_w4_c12_wiring.py | all OK |
| tests/test_v11_autonomy_timeline.py | "PASS: 0 failing" (includes committed-map == generator) |

## Findings

### F1 HIGH: an SEO fix turns a live Etsy listing back into a local `draft`
- **Where:**
  - `growth/portfolio_act.py:110` enqueues `listing.seo` for an SKU that is live on Etsy. SEO_PROBLEM needs at least 300 impressions (`growth/portfolio.py:214`).
  - `runtime/release.py:2098` (`_persist_listing`) then sets `row.state = "draft"` unconditionally.
- **Effect:** every reader of `LIVE_ON_ETSY` now treats a live listing as not live. That includes readiness, the catalogue, verify checks, ledger evidence and `days_live` in the next `portfolio.review` (`pipeline.py`, `live_since`). The `published_manually` adoption marker is erased the same way. The next review then classifies the SKU on false exposure data.
- **Repro:** `repro_seo_live.py`
  1. Certify hexagon-coaster-set through the real Worker.
  2. Set its Listing to `state="published"`, `etsy_listing_id="1234567"`.
  3. Add a ListingOutcome with 4000 impressions and 4 visits.
  4. Run `portfolio.review`.
- **Result:** `job 14 listing.seo done key=seo-fix:hexagon-coaster-set:2026-W45` and then `listing after: draft 1234567`.

### F2 HIGH: an autonomous internal signal drives the chain to `store.publish` (a regression of FMBATCH1 F-1)
- **Where:**
  - `growth/portfolio_act.py:110-113`.
  - `listing.seo` enqueues `launch.plan` (`runtime/release.py` near line 1422).
  - `launch.plan` enqueues `marketing.schedule` and `store.publish` (`runtime/release.py:2253-2258`).
- **History:** `integrations/taxonomy_drift.py:48-53` records independent review FMBATCH1 F-1: "a re-queued listing.seo carries its rebuild token through launch.plan to store.publish ... so the re-queue is OFF unless `BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE=1`, and the rebuild is put to the owner as an action instead." This branch re-queues the same chain with no gate, no env switch and no owner card.
- **In SHADOW:** `store.publish` goes DEAD ("capability not enabled ... SHADOW"). Repro: `job 28 store.publish dead key=publish:hexagon-coaster-set:...:portfolio:20:c8`. That is one DEAD job per SEO fix, which is noise for dead-job monitoring.
- **Past SHADOW:** the `if already:` refusal (`runtime/pipeline.py:1990`) stops a second Etsy listing being created, so I found no Etsy write. The guarantee now rests on that one check instead of on design, against a decision already made in review.
- **Consequence:** the rebuild never updates Etsy, so the "SEO fix" is buyer-invisible by construction.

### F3 MEDIUM: the rebuild reuses stale inputs and reverts the live price
- **Where:**
  - `growth/portfolio_act.py:104` uses `_last_seo_inputs`, which returns the full inputs of the newest DONE `listing.seo` (`price_cad`, `frames`, `sizes`, `launch`, `positioning`, `pages` and so on).
  - `runtime/release.py:1155` builds the copy with `price_cad=float(i.get("price_cad"))`.
  - `runtime/release.py:2096` writes `row.price_cad = copy.price_cad`.
  - `frames` from the old inputs also win over `_stored_frames` (near `release.py:1170`).
- **Repro:** same script. Before the review, set `Listing.price_cad = 12.34` to stand for a later repricing. After the rebuild: `price after rebuild: 4.0`.
- The version is pinned to the current certified release (good), but nothing else in the inputs is refreshed.

### F4 MEDIUM: the cap starves SKUs whose slug sorts late, and the test comment claims the opposite
- **Where:** `growth/portfolio_act.py:88` iterates `sorted(items, key=slug)`. Neither the budget nor the per-week dedup (`:87`) remembers who was capped. `tests/test_p0_portfolio_act.py:178` says "next week they are first in line", but only asserts `len(acted) == 5`.
- **Repro:** `repro_pact_units.py`, with 7 SEO_PROBLEM SKUs over 4 weeks.
  - Every week, `sku-00`..`sku-04` are acted on and `sku-05` and `sku-06` are capped.
  - Output: `never acted after 4 weeks: ['sku-05', 'sku-06']`.
- **On the cap question:** the cap does bound work, and overflow is not re-queued (nothing is enqueued for capped SKUs). But the same SKUs are rebuilt every week, combining with F1 and F3, and the overflow is never served.

### F5 MEDIUM: RETIRE/REWORK cards pile up, one per SKU per week, while unanswered
- **Where:** `growth/portfolio_act.py:129` builds the key `portfolio.{kind}:{slug}:{week}`. The module docstring (`:12-14`) says `portfolio.rework:<slug>`.
- **Effect:** `owner_queue.ensure` dedups by key, so each new week opens a new card even while last week's card for the same decision is still open. A card the owner has answered ("don't retire") is also asked again every week, forever.
- **Repro:** `repro_pact_units.py`, one RETIRE SKU over 3 weeks. Result: `[('portfolio.retire:old-throw:2026-W45', False), ('...W46', False), ('...W47', False)]`.
- **Card content:** `max_cost_cad=0.0`, `minutes=10`, and the consequence is present. The action ("Decide whether to retire X") names no concrete step: where to record the decision, and what retiring does (e.g. deactivate on Etsy). That is borderline against the "exact action" rule. The cards never become jobs, which I confirmed.

### F6 LOW: the week token is truncated in downstream keys, so the chain runs once per release, not per week
- **Where:** `runtime/release.py:85` keeps `token[:12]`. `"portfolio:2026-W45"[:12] == "portfolio:20"`.
- **Repro:** `repro_pact_units.py` prints `chain_key W45 == W46: True publish:x:1.0:abc:portfolio:20:c8`.
- **Effect:** week 2+ still runs `listing.seo` (F1 and F3 again) but dedups `launch.plan`, `marketing.schedule` and `store.publish` against week 1. Not dangerous, but the docstring's weekly semantics do not hold.

### F7 LOW: dedup edges
- **Week source:** `week_of` uses `isocalendar()`, so the ISO year is correct at year boundaries (2026-12-31 gives 2026-W53). But `today` is `_scan_date`, which is `date.today()` (local time, not UTC per CLAUDE.md). It can also be overridden by `as_of`, and a `portfolio.review` with an `as_of` in another week bypasses dedup.
- **Concurrent reviews:** two reviews iterate the same sorted order, and the idempotency keys plus `owner_queue.ensure`'s lock make them converge. If their label sets differ, both can compute `budget = 5` and together act on more than 5 SKUs in one week. Minor.
- **`used` only checks the twin key:** for QUALITY, `used` reads only `quality-fix:cir.twin:` keys. If the twin job is pruned or deduped and the others are not, the cap count drifts. Minor.
- **LIKE patterns:** an underscore in a slug is a LIKE wildcard. Slugs are kebab-case, so I see no current impact.

### F8 LOW: test gaps, from mutation testing (`mut_pact.py`, 8 mutants, 6 killed)
- Killed: no same-week skip, no budget decrement, card key without week, fabricated SEO inputs, dropped `cir.reverse`, all-time dedup.
- **Survived: acting on the pre-guard label.** I replaced `_kind(c.label)` with `_kind(c.evidence['discard_verdict_withheld'] or c.label)`. No test runs a guard-withheld RETIRE through `portfolio.review`. The code is correct today, but the #13 interaction is unprotected.
- **Survived: `WEEKLY_CAP = 50`.** The tests read `PA.WEEKLY_CAP`, so the ceiling's value is not pinned.
- **Missing:** no test runs the enqueued `listing.seo` on a live listing. That is how F1, F2 and F3 escaped.

## Answers to the brief

- **Patterns / certification:** No. QUALITY enqueues the same four read-only re-verification checks `gate.quality` already queues daily (`runtime/quality_ops.py:239-246`). A failure can only withhold publication (`withholding.record_reverification`, fail-closed) or open an incident, and `_resolve` only closes that check's own incident. Nothing edits a CIR or certifies. `listing.seo` writes listing copy, not instructions. Note that QUALITY is redundant with the daily `gate.quality`, so it adds no new evidence.
- **Etsy:** no Etsy network write in SHADOW. The chain does reach `store.publish` (F2), which refuses in SHADOW, and past SHADOW on `already`. The local Listing mirror is corrupted (F1, F3).
- **Spend:** the author's "budget decrement" is the weekly-cap counter, not money. Spend is only possible inside `listing.seo` via `visual.exported_review` when the `image_vision` gate is open, through `gateway.routing` and its existing ceilings. `marketing.schedule` drafts and holds only. Cards cost $0. The cap bounds it at no more than 5 SEO rebuilds a week.
- **Dedup:** correct within a week and across ISO-year boundaries, and convergent under concurrent reviews. Edges are in F6 and F7. Cards are not deduped across weeks (F5).
- **Cap:** does bound work, with no re-queue loop. It starves late slugs (F4).
- **Labels:** correct. `act()` runs after the #13 guard loop, which rewrites `c.label` to OFFER_UNTESTED (`runtime/pipeline.py:3165-3215`), and OFFER_UNTESTED maps to no action. Untested (F8).
- **Owner cards:** cost, minutes and consequence are present. The action is generic, and there is a weekly duplicate (F5).
- **Job inputs:** QUALITY inputs `{slug, version, release_hash}` match what `_run_check` expects (the same as `gate.quality`). The SEO inputs are stale (F3), and the chain is unsafe (F1, F2).
- **autonomy_map.json:** generated by the tool. Running `python -m brambleloop.autonomy.map --write` on f3bea437 gives output identical to the committed file apart from `generated_at`, and `test_the_committed_map_matches_the_generator` passes.

## Required before SHIP
1. SEO_PROBLEM must not run `listing.seo` on a live listing as it stands. Either:
   - make it an owner card, as taxonomy_drift does; or
   - gate it behind an opt-in switch, have `_persist_listing` keep the live state, and stop the chain before `launch.plan`/`store.publish`.
2. Rebuild from fresh price and frames, not from the last inputs.
3. Make card keys per SKU, not per week, and stop re-asking a decided card unless the evidence changes.
4. Rotate the cap fairly, for example prioritise SKUs least recently acted on.
5. Add tests:
   - a guard-withheld RETIRE through the handler;
   - a pinned `WEEKLY_CAP` value;
   - an end-to-end SEO fix on a `published` listing, asserting the state and price are kept.
