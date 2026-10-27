# Acceptance plan: production demonstrations for competitive intelligence and learning

These are the real production demonstrations needed before calling the system working. Each one says:

- what is run;
- who runs it;
- the exact read that proves it;
- the pass condition.

Rules for every demonstration:

- Reads use the operator credential, so they are the owner's or the post-deploy acceptance's to perform. This reconciliation used none.
- Nothing here publishes, buys or spends beyond the existing ceilings.

**Preconditions:**

- The combined candidate plus PRODFIX, PRODFIX2 and INTELREC are reviewed and deployed.
- `etsy.probe` is green.

## §1 Watchlist registration and URL health

- **Read:** `GET /api/audit?action=mjs.benchmark_health&limit=1`.
- **Pass:** four results, one per registry shop (MJs, MadelineMaeCo, ZKBDESIGNER, TheEasyDesign). Each is `healthy` or `moved`, resolved by exact shop name. No `wrong_shop`.

## §1b The spec/05 seed shops and the production panel

- **Read:** the `Benchmark` registry rows (operator DB read, or `GET /api/audit?action=intel.panel_discovery&limit=3`).
- **Pass:** a recorded answer to two questions:
  - which panel shops are observed (the `second_market_benchmark` gate reads open, so at least one non-US shop is);
  - whether HanJanCrochet joined as the second-market benchmark, or was refused with the reason Etsy's record gave.
- **Not required:** IvyLoop, LoveandStitchDesigns and FireflyCrochets are not monitored unless the owner decides they rejoin the watchlist (OWNER_REPORT §1.5).

## §2 First observation of each new shop

- **Wait for:** the first 6-hourly `intel.watchlist_scan`. Or run it once with `force: true` from the operator queue.
- **Read:** `GET /api/audit?action=intel.watchlist_scan&limit=3`.
- **Pass:**
  - every non-anchor alias has state `ok`, `listings_seen > 0` and a timestamp;
  - an outage, if any, is named per shop and does not stop the others.
- **Then read** `intel.watchlist_compare`: `GET /api/audit?action=intel.watchlist_compare&limit=1` and the `intel.watchlist_compare` operating reading.
- **Pass:**
  - all four aliases are present;
  - figures carry a grade, a source and an as-of time;
  - `ai_use` is UNKNOWN for all four;
  - no shop name or listing title appears in the record.

## §3 Laura uses the intelligence

- **Read:** `GET /api/audit?action=laura.executive_tick&limit=20` (or the Laura timeline).
- **Pass:**
  - a priority with `rule=provider` and `subject=intelligence` exists whenever a validated gap or an outage exists;
  - it delegates `intel.opportunity_review`;
  - `GET /api/audit?action=intel.opportunity_review&limit=5` shows one decision per gap: `routed` (with `radar.score` job ids), `progressed`, `route_refused`, `deferred_by_lesson`, `needs_original_design` or `stopped_after_failures`;
  - no job the review queued is a paid job type (`creative.tournament`, `creative.grid_tournament`, `creative.expedition`, `assets.*_photography`, `intel.gallery_analysis`);
  - Laura's `intelligence` provider reads UNKNOWN (never OK) while a watchlist shop is unread, unconfigured or refused.

## §4 A competitor-derived original reaches engineering and certification

- **First, read** `GET /api/audit?action=creative.winner_intake&limit=50`. It explains why no `cir.draft` has run since job 24731. Resolve the cause (REMEDIATION G2).
- **Pass:**
  - one concept whose provenance cites a mission event or a watchlist gap gets `ENGINEERING`;
  - then `cir.draft` DONE, then `gate.certify` DONE (certified);
  - the coverage gap advances to `engineering` and then `certified`.

## §5 Visual production, marketing and growth for that release

- **Read:** `/api/jobs` filtered to `assets.*` / `marketing.schedule` for the slug.
- **Pass:**
  - the assets are built through Product Truth;
  - content is drafted (SHADOW: drafts only);
  - no stale-artefact or systemic halt blocks it (PRODFIX).

## §6 Etsy ops (owner-gated go-live)

- **Owner:** grants publication or activation for the certified release in the Command Center.
- **Pass:** `store.publish` creates the draft or listing under the grant, and the readback matches.

## §7 Measurement

- **Read:** `listing.outcomes` readings and `commerce.orders_ingest`.
- **Pass:** impressions and visits at or above `MIN_VISITS` (200), or an order, for the competitor-derived listing. Below the floor it reads UNMEASURED, never 0.

## §8 Learning changes a later decision

- **Read:** the lesson bus (`lessons`, `acted_on_by`), the `radar.score` audit (`lesson_adjustment`), and the `intel.opportunity_review` decisions.
- **Pass:** a lesson published from a measured outcome (or from two failed attempts) is acted on by a later decision, and that decision differs from what it would have been without the lesson.
- **Then show the next opportunity:** the next scan or comparison opens or reprioritises a gap from that lesson.

## §9 Winner Amplification (after G5 is built and orders exist)

- **Pass:**
  - a family with 5 or more orders is detected;
  - `commerce.replication` investigates it;
  - the next declared member is delegated through `radar.score` and certified, or the family records `needs_original_design` (an original paid design is the G14 owner decision);
  - an attempt counts as failed only when it was scored and not promoted;
  - pricing and merchandising are tested;
  - follow-on sales are measured against contribution (#45).

## §10 Reliability spot checks

- **Duplicate suppression:** two consecutive scans of an unchanged shop add no `BenchmarkListing` rows and no mission events.
- **Outage:** a shop whose read fails shows `source_outage`, Laura sees it after 2 failures, there is no dead letter, and the shop is re-read only after its backoff (6 h, 12 h, … capped at 7 days).
- **Restart:** after a redeploy, watchlist state (`intel:watchlist:*` memory) persists and scans resume on interval.
- **Spend:**
  - month spend stays under the ceiling;
  - the watchlist jobs write no `CostEntry`;
  - the watchlist scan and review start no paid job: `paid_work_withheld` in the `intel.watchlist_scan` audit lists what the per-shop mission asked for and did not get.
- **Product Truth:** no lesson raises a hard floor or bypasses certification (the `improve.invariants` refusals audited).

## What the offline tests already show

`tests/test_w4_intelrec_watchlist.py` runs offline, on fixtures, and is **not production evidence**. It covers:

- §2 and §3 (Laura delegation);
- §8 (the lesson defers a later decision);
- §10 (duplicates, outage, backoff, restart, spend, idempotent retry);
- the review fixes: outcome classification (H-1), UNKNOWN summary (M-1), no paid job types queued (M-2/M-3), parked gaps (L-4), STALE and UNKNOWN grading (L-1/L-2/L-3).

`tests/test_w4_intelrec_amplify.py` (offline) covers §9's classification and `needs_original_design`.

§1, §4–§7 and §9 can only be shown in production.
