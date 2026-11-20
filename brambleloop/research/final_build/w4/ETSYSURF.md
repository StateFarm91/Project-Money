# W4-ETSYSURF: the bounded Etsy launch list, OpenAPI change watch, surface registry at runtime

Branch `claude/w4-ETSYSURF` from `origin/claude/w4-INTEG2` 534f27a. Rows: F-498, F-546, F-600, F-599
(partial), F-586, F-591 (evidence only).

## Changes
- **F-498.** `launch/readiness.etsy_first_sale_surfaces()` is now part of `assess()`. It covers every
  surface in `etsy_surfaces.first_sale_blockers()` (11 today), each with the state of its evidence
  (FRESH / STALE / NO_EVIDENCE / NO_COLLECTOR). The states come from its collector's latest recorded
  reading (the shop snapshot or the listing census), alongside the owner action that closes it and
  the shop checks that fail.
  - It is ready only when every surface is FRESH and every shop check passes. A surface no collector
    can observe is never assumed done.
  - It waits on the owner while a listed owner action is open, otherwise on the integration. It is
    never "build", so `buildable` is unchanged.
- **F-546.** The weekly `etsy.openapi_reverify` cadence already fetched Etsy's public OpenAPI document
  and ran `verify_absence`, with a P2 incident on drift (W4-FM2). This branch adds:
  - `document_fingerprint` to every reading;
  - `document_changed` against the previous reading (None when unknown);
  - a P3 incident `etsy.openapi_document_changed` when the document changes without moving any verdict.
    New features show up there first.
- **F-600.**
  - The new read-only `/api/etsy/surfaces` serves `coverage()`, `work_plan()` and the first-sale list.
  - The `/dashboard` command centre gains an "Etsy surfaces" block.
  - Out of scope: building more collectors per F-553/F-585.

## F-599 (partially blocked)
Criteria and status:
- Fetch the document on a schedule and compare `document_fingerprint` and `verify_absence`: **done**,
  weekly. That is stricter than the quarterly cadence asked for.
- Raise a review on change: **done** as an incident.
- "Opens an owner review task": **not built.**
  - Reason: CLAUDE.md permits owner interruptions only for KYC, legal acceptance, banking,
    consequential spend or physical actions. Reviewing an API document change is company work. The
    owner queue's own checks (`no_satisfied_owner_action_presented`, the queue's empty-state proof)
    would also flag a non-owner card.
  - Needs a ruling: keep the incident, or route the review to the owner anyway. The criterion is not
    changed here.
- Shop Manager UI navigation drift: no observer is possible. etsy.com returns 403 to this
  environment, so this part is external.

## F-586, F-591
The board itself says "none — at target maturity for launch". No code change; the surfaces' verdicts
are in `etsy_surfaces` and `/api/etsy/surfaces` exposes them. Recorded for the integrator to mark from
the board's own text.

## Acceptance evidence (testslot)
`tests/test_w4_etsysurf.py` covers:
- an unobserved shop lists every first-sale surface and waits on the owner;
- a fresh, passing shop still names what no collector observes;
- failing checks are named;
- the requirement is part of readiness and never "build";
- the API route;
- the weekly cadence exists;
- fingerprint and change detection, including the P3 incident;
- the dashboard block.

Regression suites green: test_w4_fm2_surface_reverify 8/8, test_etsy_readback_observe 37/0,
test_w3_k4_launch_verdict 16/0, test_route_auth_default_deny 7/7, test_customer_data_auth 9/9,
test_w4_owner_actions 6/0.

`test_launch` fails 4 tests on "hero: 340 px legibility". INTEG2 534f27a without this branch fails
**identically**, so this is a pre-existing visual-lane defect, not this branch. `test_w4_etsysurf` passes
8/8; also green: test_dashboard_spend, test_rc1_own_dashboard.
