# W4-MJSCOUNT: MJs counters from one snapshot, scan-health detail, gallery cost forecast

Branch `claude/w4-MJSCOUNT` from `origin/claude/w4-INTEG2` 85ec5d0. Rows: F-191, F-192, F-193.
The ETSYCOMM lane owns the mjs.scan credential root cause; this branch does not touch it.

## Changes
- **F-191, MJs Scan Consistency.**
  - `intel/mission.snapshot()` derives every catalogue counter from one `BenchmarkListing` read: known,
    audited, gallery-audited, by pod, unclassified, image slots (judged / unjudged / given up) and the
    gap total.
  - It adds a `reconciliation` row with five identities and the list of failing ones. A failure is
    reported, never corrected.
  - `mission_report` uses the snapshot. `vision.image_counts()` is now the one image arithmetic, shared
    by `pending_count`, `plan` and the snapshot.
  - Defect fixed along the way: `vision.plan.pending_images` was `len(pending(limit=200))`, so it
    capped at 200 and disagreed with the catalogue-wide count. It now reads `pending_count`.
- **F-192, Scan Health Semantics.** The dashboard `_mission` row now shows the scan-health state with
  its problem text and check time, or "never checked".
- **F-193, Gallery Cost Forecast.** `vision.forecast()`, carried in `vision.plan()["forecast"]` and
  shown on `_mission`, reports:
  - the measured CA$ per image: `cost_entries` with purpose `gallery_observation` divided by images
    judged. It is UNKNOWN when either is zero, never 0;
  - the purpose's allocation share, the amount spent and the amount allowed;
  - images per run, from `spend_policy.work_that_fits`, which is the cadence's own sizing;
  - runs per day, from `CADENCES`;
  - the ETA in days and the cost to drain, labelled measured or estimated.

## Acceptance evidence (testslot, one file at a time)
- `tests/test_w4_mjscount.py` 5/5:
  - one snapshot, reconciling;
  - the backlog count no longer saturates at a page;
  - a broken identity is reported;
  - the forecast is measured or UNKNOWN;
  - the dashboard rows are present.
- Regression suites green: test_mission, test_cert_mjs, test_w4_mjs_findings, test_gallery_escalation.

## Board rows advanced
F-191, F-192 and F-193 move from engineering_open to implemented and tested on this branch. They are
not deployed.
