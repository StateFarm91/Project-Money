# A3 round 2 — review request

Branch: `eng/a3-photo-fix-2`. Fix commit: `fd6ee31`. The final SHA is the commit that adds
this file; see the commit log / final message.

## How the branch was built

1. Branched from `c628b978` (A3, independently reviewed SHIP).
2. Merged `origin/claude/w6-INTEG1` at `a1b4f5d` (`b052390`). Because `c628b978` is already an
   ancestor of INTEG1 (merged at `ce671ce`, reverted at `fb331ea`), the merge also brings in
   INTEG1's revert, which removes A3.
3. Reverted that revert (`ca496af`, "restore A3 on top of INTEG1"), which brings A3 back. Result: `src/`
   is A3 c628b978 plus INTEG1's later merges (S2 OpenAI provider, Etsy scopes display). No A3
   source line changed in this round.
4. One fixture fix (`fd6ee31`). There is no `REVIEW_REQUEST.md` at the repo root (`d355eda`, the
   draft that added one, was not included).

## Cause, per failing test

All 21 failures (16 in `test_etsy_readback_observe`, 5 in `test_k8_listing_estate`) come from
**one fixture**, `test_etsy_readback_observe._product`. `test_k8_listing_estate` imports it as
`rb._product`. **Verdict: (a), the fixture certificate was inconsistent.**

That fixture stored a "valid" `ListingSetCertificateRecord` whose frames were
`{"job": "hero", "purpose": "conversion", "medium": "render"}`. None of these is in the
certificate vocabulary: `eligibility.JOBS`, `eligibility.PURPOSES`, `AssetClass`.
`listing_set.CertifiedFrame.__post_init__` refuses this frame
(`ListingSetRefused: ...-frame-3: 'hero' is not a frame job`), so no issuance path can write it.

- Before A3, `etsy_ops.certified_frames` read `frames` as raw dicts and never parsed them, so
  the malformed certificate got through.
- A3 added `photo_certificate_current(s, db, slug, version, _certificate_from_record(rec).frames)`.
  `_certificate_from_record` builds a `CertifiedFrame` for each frame. It raised, and the
  fail-closed `except` turned that into "photo frame or evidence no longer matches the
  certificate". That is the right outcome: a certificate that cannot be parsed must not release
  bytes to Etsy.
- This is **not** case (b). The galleries in these suites are render-only with no photo. For
  those, `photo_certificate_current` returns True: `expected` is empty, and that case is covered
  directly by the debug run below. A3 does not reject render-only galleries, galleries with no
  photo, or certificates written before A3. It rejects only frames that no code path can produce.

Reproduced directly (before the fix): with A3's `_lock` held,
`photo_certificate_current(..., _certificate_from_record(rec).frames)` raised
`ListingSetRefused: 'hero' is not a frame job`.

## Fix

`tests/test_etsy_readback_observe.py::_product`: the frames now use real vocabulary for a
render-only gallery:

- position 1 is `DESIRE`, the others `DETAIL`
- purpose `CONVERSION_CREATIVE`
- medium `DIGITAL_TWIN_RENDER`
- `honesty_label = RENDER_LABEL`

Positions, sha256 values and the deliberately reversed storage order are unchanged, so every
ordering and byte assertion still tests the same thing. The fixture now also calls
`_certificate_from_record(record)`, so a malformed fixture fails at construction instead of
downstream. No assertion was removed or loosened, and no A3 check changed. The A3 guarantees
still hold, and their suites pass:

- owner-attested photo keeps authority across rebuilds (`test_cert_listing_frames` L2,
  `test_w6_fix_only_rebuild`)
- a stale or invalid certificate fails closed (`test_opus2_photo_asset_review`,
  `test_codex_a3_*`)
- the PG fence (`test_a3_postgres_photo_fence`, real PostgreSQL 16 cluster, not SKIP)

Not changed, but a note for the reviewer: the `except Exception` in `certified_frames` reports
an *unparseable* certificate with the same message as a *stale* photo. It still fails closed
either way. A separate message would have made this failure easier to diagnose, but changing
A3 behaviour was out of scope.

## Acceptance suites (`JOBS=4 SUITE_REGISTRY=0`, PG16, `/tmp/venv`)

| suite | ok | fail |
|---|---|---|
| test_etsy_readback_observe | 37 | 0 |
| test_k8_listing_estate | 9 | 0 |
| test_a3_postgres_photo_fence (real PG) | 3 | 0 |
| test_opus2_photo_asset_review | 34 | 0 |
| test_cert_listing_frames | 7 | 0 |
| test_codex_a3_disclosed_race | 2 | 0 |
| test_codex_a3_excluded_gap | 3 | 0 |
| test_w6_fix_only_rebuild | 21 | 0 |
| test_w4_launchfix | 32 | 0 |
| test_w4_listready | 41 | 0 |
| test_w4_pipe_board | 70 | 0 |
| test_v11_autonomy_timeline | 6 | 0 |
| test_w4_c12_wiring | 4 | 0 |
| **total** | **269** | **0** |

Before the fix, on the same tree: etsy_readback_observe 21 ok / 16 fail and k8_listing_estate
4 ok / 5 fail, both with "photo frame or evidence no longer matches the certificate".

## Wider sweep: every other test that builds galleries or certificates

Selection: `grep -lE "certificate|gallery|listing_set|frame" tests/test_*.py`, minus the 13
suites above. That gives **309 suites**, listed in `a3_round2_wide_suites.txt`. Run at
`fd6ee31` on a clean tree (run record `artifacts/suite_runs/20261118T171022Z-3751.json`):

**TOTAL PASSING: 4679 ; suites failing: 1 ; environment failures 0.**

- The 1 failing suite is `test_w3_spend_attribution::test_binding_ceiling_and_vocabulary_are_in_the_governance_reading`
  (`binding["unset"]["provider_ceilings"] is True`). It is **already failing**: it fails the same
  way on the unmodified INTEG1 base `a1b4f5d`, in a separate worktree. It concerns spend
  governance and provider ceilings, which A3 does not touch. Probably from the S2 OpenAI
  provider merge. Not fixed here (out of scope). It is flagged for INTEG1.
- Two other suites have fixtures with the same `"job": "hero"` shape:
  `test_storefront_fb4` (17 ok) and `test_ranking_readiness` (7 ok). Both pass unchanged,
  because their certificates never reach `certified_frames` or `photo_certificate_current`.
  Left as is: they are not broken, and editing them without cause is churn.
