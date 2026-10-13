# VISROLE: role-appropriate independent visual review (D-W4-VISROLE)

- **Branch:** `claude/w4-VISROLE`, based on `origin/claude/w4-INTEG2` 056398c, which already
  contains VISFIX and B2CLOSE.
- **Scope:** shadow only. The vision provider is stubbed in every test, nothing is spent, and
  nothing is deployed.

## The defect (found by W-B2CLOSE in production)

- `release._review_frames` (#61) asked every listing frame the ten photographic realism checks
  in `gallery.REALISM_CHECKS`, such as `drape` and `hands_and_fingers`.
- Charts, size cards and infographics cannot answer those questions, so the reviewer said
  "unclear".
- An unmade check is never a pass. Every deterministic non-photo frame therefore stayed
  `unjudged` and blocked publication, for a reason unrelated to the frame.

## The fix

The code is in `visual/frame_role.py` and `release._review_frames`.

- **Classification comes from the frame plan only.** It reads (asset class, frame role); the
  model is never asked which kind of frame it is looking at.
  - The listing hero (DIGITAL_TWIN_RENDER) is a disclosed twin drawing, following D-FB-9.
  - The chart frame is a chart.
  - INFOGRAPHIC frames are infographics.
  - PATTERN_PREVIEW frames are pattern previews.
  - **Everything else is photographic.** That covers PHYSICAL_PRODUCT_PHOTO,
    AI_LIFESTYLE_CONCEPT, any frame with a model in it, and any combination not in the table.
- **A photographic frame is reviewed exactly as before.** It gets the full realism inspection,
  and an unclear realism check stays `unjudged` (C-80 / Codex P06).
- **A non-photo frame is described blind with no realism call.** It still gets the semantic
  comparison and, for the hero, product identification plus the 230 px grid reading. It must
  then pass five role checks:
  1. `data_matches_record`. Nothing from Asset Truth or the frame plan is flagged on this
     frame, and every record label is drawn: the size card's label and named scale reference,
     and every CIR colour on the materials card.
  2. `text_legible_340`. The headline is at least 11 px at 340 px (`MIN_LEGIBLE_TEXT_PX`), and
     no line is set below `layout_qa.MIN_TEXT_PT`.
  3. `scale_not_misleading`. No size or scale finding is on the frame, and the size card draws
     its scale.
  4. `no_third_party_marks`. The describer must say none are present. An answer of "unclear"
     counts as unanswered.
  5. `disclosure_present`. The image provenance (#36) must be a simulated render, never proof.
     The twin drawing must also draw "not a photograph" in its own pixels.
- **Outcomes:**
  - A failed role check blocks, as `FRAME_REVIEW_ROLE_CHECK_FAILED`.
  - An unanswered or missing role check is `unjudged`, which means not reviewed.
  - Semantic problems and third-party marks still block, as `FRAME_REVIEW_BLOCKED`.
  - Every other veto still applies on its own: Asset Truth, frame plan, layout QA, hero
    thumbnail, identity gate and provenance.
- **For the owner to tighten (see D-W4-VISROLE):** the 340 px floor applies to the headline
  only. Today's body and label lines land at 7 to 11.6 px at 340 px, and the smallest is
  recorded per frame.

## Tests (testslot, N=1, stub vision)

| Test | Result |
|---|---|
| tests/test_w4_visrole.py (new) | 8/8 |
| test_cert_listing_frames (updated to assert the role rule) | 6/6 |
| test_vacuity | 8/8 |
| test_launch | 28/28 |
| test_cost_governance_wave2 | 39/39 |
| test_search_hero_publish | 4/4 |
| test_v11_autonomy_timeline | 6/6 (map unchanged) |
| test_w4_b2close2 | 11/11 |
| test_cert_rebuild_chain | 10/10 |
| test_photoreal_calibration | 19/19 |
| test_w4_b2moat | 3/3 |
| test_w4_firstimg | 12/12 |
| test_w4_imgfix | 3/3 |
| test_w4_disclosedqa | 8/8 |
| test_w4_herotourney | 4/4 |
| test_w4_multipiece | 5/5 |
| test_w4_thumbfloors | 7/7 |
| test_w4_herovision | 6/6 |
| test_listing_parity_gate | 6/6 |
| test_cert_publish_gates | 18/18 |
| test_publish_execution_gate | 1/1 |
| test_blinded | 46/46 |
| test_w4_b2vision | 7/7 |
| test_w3_tmp_hygiene | 14 pass, **2 fail**. Both name files this branch does not touch: `scripts/w4_learn_loops_proof.py:35`, `tests/test_w4_fmgate_catalogue_filters.py:18` and `tests/test_w4_pl_continuity.py:32`. So the failure is identical on clean INTEG2 056398c. It is not in the required set. |

What `test_w4_visrole` covers:

- Classification comes from the plan, and an unknown frame is photographic.
- A non-photo frame is clear only when all five role checks pass.
- These each block:
  - a label mismatch, whether a wrong record label or a drawn label edited away from the
    record;
  - illegible text: a small headline, a line below the minimum, or no type at all;
  - a missing drawn disclosure;
  - a veto: an Asset Truth size finding, a frame-plan finding, a third-party mark, a chart the
    describer says is not a chart, or a size card with no scale.
- These are unjudged: an "unclear" marks answer, no description, no recorded layout, or a
  missing check.
- End to end through `_review_frames`: a photographic frame goes to the realism inspection and
  stays unjudged on an unclear `hands_and_fingers`. A size card never calls the realism
  inspection, and it is clear.

## Rows this affects

- **B2 #61 Visual Semantic QA.** B2CLOSE already closed this row in the ledger. This change
  fixes the production state behind it: non-photo listing frames could not clear. Once the
  next release deploys, they can clear on their merits, against role checks that fit them, and
  they can still fail. The semantic comparison and its vocabulary are unchanged.
- **F-027 / F-031 (first image shows what is sold; thumbnail).** The hero's identification and
  230 px grid reading are unchanged and still required. The hero no longer waits on photographic
  realism answers it could never get.
- **F-221 / F-229(B) / F-856 (photographic realism).** These now apply to photographic frames
  only, which is the D-FB-9 rule carried from the disclosed set to the stored listing frames.
  They are unchanged for every photograph and generated image.
- **F-278 (hero tournament).** Not affected. It uses the blinded grid, not `_review_frames`.
- **Closed by this branch:** none. Production evidence needs a deploy plus a funded
  `image_vision` run of `assets.build`.
