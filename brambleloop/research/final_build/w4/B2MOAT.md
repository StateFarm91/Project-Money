# W4-B2MOAT: #15, #44, #86 after image_vision opened

Date: 2026-10-12 (UTC). Branch `claude/w4-B2MOAT`, from `origin/claude/w4-INTEG2` 534f27a.
Domain: Build 2 gate elimination, item 6.

## Rows

| Row | State | Evidence |
|---|---|---|
| #15 First-Page SERP Laboratory | covered: **met in production** | `serp.captured` 2026-10-12T00:31Z captured 29 queries. The top thumbnails were judged through the vision path (snapshot 1: 3 judged; snapshot 2: 5 judged; none refused). Saved as `evidence_B2MOAT/prod_audit_serp_captured_2026-10-12.json`. |
| #86 Creativity Benchmark Memory | covered: **met in production**, except our own outcomes | `creative.benchmark_memory` 2026-10-12T00:23Z: state "measured" over 36 judged listings, with attributes stored and favourites as the market outcome. Brambleloop's own outcomes need live sales ("Store attributes and outcomes"). Under the owner's 2026-10-12 scope rule they are recorded as impossible-before-launch, not as zero. |
| #44 Brand Moat Beyond the Model | covered: **defect fixed** | See below. |

## The #44 defect

The vision recognisability judge ran inside `brand.moat.evidence`, which these paths call on
every request:
- `GET /api/launch`;
- the public dashboard;
- `GET /api/launch/packet`.

With `image_vision` open, an unauthenticated page load would have paid a judge per listing,
and nothing recorded the answer. Production `/api/launch` (2026-10-12) still showed all 8
listings recognisable by proxy only.

**Fix.** The daily `launch.readiness` job measures each listing's current hero frame and
records the result as `brand.recognisability_measured`. Read paths call
`assess(..., measure_vision=False)` and get `recorded_recognisability`. A record for an
older frame does not count for the current one.

## Item 7: Build 2 rows whose machinery is `build2/*`

None is company-executable here:
- **Owner-gated:** #1, #37, #189, #221, #222, #236 and #320 wait on `insights_access` or
  `acceptance_ruling`.
- **External:** #203 and #300 wait on `model_bearing_render`.
- **#195 production_window:** production `off_device_proof` (to 2026-10-12T03:29Z) has 4 of
  5 conditions met. The unmet one is `no_unexpected_dead_letters` = 20, spread across
  mjs.scan, ops.offsite_archive, ops.policy_watch, ops.sentinel and radar.score. Those dead
  letters belong to the FM-ops domain, which is not this lane. Recorded and skipped.

## Acceptance evidence

**New test:** `tests/test_w4_b2moat.py`, 3/3.

**Regression (testslot):**
- test_cert_rebuild_chain: 0 failing
- test_moat: OK
- test_fb4_launch: 9/9
- test_w4_b2_build2_ledger: ALL OK

**test_launch:** 15 failures ("hero: 340 px legibility"). The same 15 fail on a clean checkout
of INTEG2 534f27a, so they come from the image/render lane and are not caused by this change.

**Ledger** (`build2_ledger.py`, production reading 2026-10-12T03:35Z), on this branch alone:
PROVEN 218, OWNER 42, DATA 41, EXTERNAL 5, N/A 3, OPEN-DEFECT 11.

**Combined with `claude/w4-B2VISION`:** OPEN-DEFECT 1 (#61, which belongs to the image
worker).

## Checkpoint 2026-10-12 (controlled pause)

**Status: DONE.**
- Closed: #15, #44, #86.
- Merged INTEG2 16e36ae; the ledger was regenerated with build2_ledger.py: PROVEN 227,
  OPEN-DEFECT 1 (#61, the image worker's row).

**Tests after the merge:**
- test_w4_b2moat 3/3
- test_w4_b2_build2_ledger ALL OK
- test_cert_rebuild_chain 0 failures
- test_moat OK
- test_w4_b2vision 7/7

**Required regression set:**

| Test | Result |
|---|---|
| test_vacuity | 0 failures |
| test_cert_listing_frames | 0 failures |
| test_v11_autonomy_timeline | 0 failures |
| test_launch | 15 failures; identical on clean INTEG2 534f27a (the image worker's regression) |
| test_cost_governance_wave2 | 1 failure: `test_no_production_module_creates_a_directory_nothing_removes`, at `app/main.py:1179 tempfile.mkdtemp` |
| test_search_hero_publish | 1 failure: `test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict` |

The two single failures were not compared against clean INTEG2 before the pause. This
branch's main.py diff adds no mkdtemp; the only main.py change is `measure_vision=False`.

**Next step:** run test_cost_governance_wave2 and test_search_hero_publish on clean INTEG2
16e36ae to attribute those two failures.
