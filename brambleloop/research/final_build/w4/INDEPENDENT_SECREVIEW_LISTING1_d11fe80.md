# Independent security review — `claude/w4-LISTING1` at `d11fe80f`

- **Reviewed:** 2026-10-31 (UTC), by an independent reviewer. No pull request opened. Nothing pushed to the subject branch.
- **Subject:** `d11fe80f8c89e3dd1c2836b0cec3f4496a760228`.
- **Diffed against:** its merge-base with `origin/claude/w4-INTEG8-next`, which is `b01339168bb4616d81044bc12e2a8a9effb7f237`. The diff is 29 files, +1818 / −63.
- **Ruling under review:** D-W4-OWNER-BASKET-IDENTITY (2026-10-27).

## Verdict: **SHIP**

- No basket size can skip a launch gate.
- The children's-safety rules now follow the product that sells each CIR, which is correct.
- The release hash is unchanged.
- The listing package matches the chain evidence byte-for-byte on the title, tags, price and hashes, and it contains no nursery, baby, three-size or nesting claim.
- All 15 test changes are legitimate updates to the ruling, and none removes a safety assertion.
- The findings below are LOW or INFO hardening items. None of them blocks shipping.

## Environment note

The container had no `sqlalchemy`, so the first test run failed on import and was discarded. I installed `brambleloop/requirements.lock` (`python -m pip install -r requirements.lock`) and then ran everything below in a detached worktree at `d11fe80f`.

---

## 1. Gate integrity

All results below were reproduced with:

```
cd brambleloop && PYTHONPATH=src python -c "from brambleloop.products import launch0 as l0; ..."
```

| CIR | `candidate_for_cir` | `childrens_assignment` | `childrens_decision` | in `launch_scope_slugs()` | `legacy_status` |
|---|---|---|---|---|---|
| `market-basket-small` | `hexagonal-bread-basket` | `None` | `not_for_children` | True | in scope, not legacy |
| `market-basket-medium` | `nursery-nesting-baskets` | `('nursery_decor','under_3')` | `assigned` | True | in scope, not legacy |
| `market-basket-large` | `nursery-nesting-baskets` | `('nursery_decor','under_3')` | `assigned` | True | in scope, not legacy |

How each gate applies:

- **First-customer gate.**
  - `publish.eligibility.product_publication` runs `gates.first_customer.blocking` whenever `legacy["in_launch_scope"]` is true (`eligibility.py` ~L746).
  - All three sizes are in scope, so all three are gated.
  - `owner_review_required` is True for all three.
- **Eligibility (`legacy_status`).**
  - Medium and large stay in launch scope because `launch_scope_slugs()` iterates `LAUNCH0_SLUGS + HELD_FOR_VERIFICATION`.
  - So a re-certified medium cannot take the "legacy cleared by re-certification" route around the first-customer gate.
  - The code comment at `launch0.py:1092` names this exact risk, and the code closes it.
- **Children's product.**
  - `_cir_audience_map` now skips a reserve candidate's claim on a CIR that a launched candidate sells.
  - The small basket's decision is therefore an explicit `not_for_children` from `_decided_not_for_children`, not an omission. Because it is explicit, `publish.pdf` will not refuse it as "undecided".
  - Medium and large keep `under_3`, so `check_licence_and_safety_statements` still requires the full under-3 statement set for them.
  - **This is correct.** The CIR is titled "Crochet Hexagonal Bread Basket". The owner positioned the product for the kitchen and home and removed the nursery merchandising. A bread basket sold as kitchenware is not a children's product, and nothing in the CIR (stitches `sc` and `inc`, worsted cotton, no small parts) changes that.
  - `test_deliverable_qa` now asserts that the small basket's rendered PDF contains no "nursery", "baby", "infant", "children" or "cpsia". This is stronger than before.
- **Physical sample.**
  - The small basket's risk class is unchanged.
  - The first-customer gate's `check_gauge_and_size_claims` and its `full_physical_make` binding still read the content-bound evidence.
  - The content hash is unchanged (§4), so the existing tester kit still binds.
- **Brand and imagery gates.**
  - These are not keyed on `LAUNCH0_SLUGS` (checked with grep).
  - `check_imagery` and `check_listing_claims` run for every in-scope CIR.
- **Held family.**
  - It is not launched: it is absent from `LAUNCH0_SLUGS`, so `seed_launch0`, SEO, shot plans and the customer page all exclude it.
  - It stays inside the quarantine for every per-product gate.
  - See F-1 and F-2 for two residual gaps.

## 2. Truthfulness

**The listing package against the chain evidence.**

- I compared `manual_listings/market-basket-small-1.2.0/LISTING_PACKAGE.md` with `manual_listings/evidence_LISTING1_basket_after_identity_fix.json`.
- The title, all 13 tags, `price_cad` 6.5, `release_hash`, and the US and UK PDF sha256 values (`c5dbe661…00b1` and `fc3592b8…2d6d`) are identical in both.
- A regex sweep of every string in the evidence JSON for `nurser|baby|infant|child|nesting|three size|3 size|cpsia|under 3` returns no hits.
- In the package, those words appear only in history, explanation and policy sections ("is gone", "Previously…", and the policy note that the shop's baby blankets still need it). They never appear in buyer-facing copy.

**The regenerated buyer-facing text.**

- **Chain title:** "Hexagonal Bread Basket | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms". Every word is licensed by the CIR title or the deliverable.
- **Chain tags:** these are generic, e.g. "basket crochet", "crochet home decor" and "hexagon basket".
- **Strategy title, tags and description (`seo.strategy.plan()`):** these contain no forbidden words.
- **Measurements:** the stated sizes (16.0 cm across the points, 13.9 cm across the flats, "about 9 cm" tall) match the twin (16.0 / 13.9 / 8.7 cm).
- **Colour claims:** "wine bands near the rim" matches the CIR, where wine is on rows 14–15 and 17–18.
- **Alt text:** `visual.launch_imagery.assemble("hexagonal-bread-basket")` produces "Crochet Hexagonal Bread Basket … About 16 x 8.7 cm…", with no forbidden words.
- **Validator check on the small basket's facts:** `seo.truth.check_term` against `F.launch0_facts()[0]` (market-basket-small) refuses "nursery decor", "baby basket", "nesting baskets" and "3 sizes" with `TERM_UNTRACEABLE`.

**Are "kitchen" and "table" licensed by the CIR? No.** See F-3.

- They are licensed only at product level, through `PRODUCT_LICENCES["hexagonal-bread-basket"]`, which points at `candidate.what_it_is`. This same change wrote that text.
- The per-variant validator, which is CIR-derived, refuses both words.
- "Kitchen" is supported by the owner's ruling ("kitchen and home"). "Table" is a reasonable inference, but neither the owner nor the CIR states it.
- They appear only in the lane-G strategy title and tags. The chain output, and therefore the listing package, does not use them.

## 3. Test changes (15 files)

| File | Change | Verdict |
|---|---|---|
| `test_deliverable_qa.py` | The children's-statement loop now covers blanket, medium and large instead of blanket, small and large. It adds: the small basket's assignment is None, and its PDF has no nursery, baby, infant, children or CPSIA text. The safety-facts test moves to the medium basket. | Legitimate. Stronger: a new negative assertion, and medium and large keep the full statement check. |
| `test_launch0.py` | Adds assertions for: scope membership, the small basket's owner and `NOT_FOR_CHILDREN`, and medium and large still `under_3`. | Legitimate. Additive only. |
| `test_launch0_listing_truth.py` | The expected sources gain `hexagonal-bread-basket`. | Legitimate. |
| `test_r2_product_catalogue_depth.py` | 10 → 8 releases. Small maps to its own product. | Legitimate. This is arithmetic from the ruling. |
| `test_r2_product_seo_unicode.py` | Baseline tag "nursery decor" → "bread crochet". | Legitimate. This is a fixture for unicode evasion, and the evasion assertions are unchanged. |
| `test_v11_store_foundation.py` | `variant_count` 3 → 1. The `TITLE_PLAN_MISMATCH` owner finding is now asserted *absent* for the basket. | Legitimate. The owner decided the naming, and the plan and CIR titles now agree. The check itself is untouched in `src`; it simply no longer fires. |
| `test_w3_seo_learning.py` | Slug renamed. | Legitimate. |
| `test_w3_seo_strategy.py` | Asserts one variant, no nursery, baby, nesting or three-size text, and "kitchen" present. | Legitimate. It drops the old three-size assertions and adds negative truth assertions. |
| `test_w4_images.py` | The medium build is replaced by the small one. Asserts medium and large are *not* page candidates. | Legitimate. |
| `test_w4_l0_product_readiness.py` | 10 → 8 releases. | Legitimate. |
| `test_w4_launch_review.py` | 60 → 48 frames. The budget test raises `per_release` from 8 to 10, so 8 releases × 10 frames = 80 calls, still more than the CA$7.07 cap buys. | Legitimate. The cap-enforcement assertion is unchanged and still exercised beyond the cap. |
| `test_w4_launchready_engineered_cohort.py` | The cohort list is updated. The motif/brief set equality now includes `HELD_FOR_VERIFICATION`. | Legitimate. It still requires every engineered candidate to have a motif and a brief. |
| `test_w4_listready.py` | 9 → 7 seed runs, 9 → 7 drafts. Asserts medium and large are not seeded. | Legitimate. It adds a negative assertion. |
| `test_w4_product_catalogue_floor_proposal.py` | Slug renamed. | Legitimate. |
| `test_w4_visual2.py`, `test_w4_visual_certified_gallery.py` | Sizes 3 → 1, and SIZING not applicable. | Legitimate. SIZING applicability is still *measured* from the CIR, and the COLOUR_CONTEXT assertion is kept. |

**No safety assertion was removed or weakened.**

### Test runs

Each suite was run one at a time with `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`. All exited with rc=0:

- `test_launch0`
- `test_launch0_listing_truth`
- `test_childrens`
- `test_first_customer_gate` (12/12)
- `test_eligibility`
- `test_w4_children`
- `test_deliverable_qa`
- `test_r2_product_catalogue_depth`
- `test_r2_product_seo_unicode`
- `test_v11_store_foundation`
- `test_w3_seo_learning` (7/7)
- `test_w3_seo_strategy` (12/12)
- `test_w4_images` (8/8)
- `test_w4_l0_product_readiness`
- `test_w4_launch_review`
- `test_w4_launchready_engineered_cohort`
- `test_w4_listready`
- `test_w4_product_catalogue_floor_proposal`
- `test_w4_visual2` (8/8)
- `test_w4_visual_certified_gallery` (7/7)

`tests/test_decision_index.py` does not exist. I ran `tests/test_w3_decision_index.py`, which checks the index against the log, and it passed with rc=0.

## 4. Release hash stability

```
PYTHONPATH=src python -c "from brambleloop.products import launch0 as l0; \
  from brambleloop.creative.pattern_refs import release_hash_of; \
  from brambleloop.quality import tester_kit as tk; \
  print(release_hash_of(l0.cir_for('basket_small')), tk.content_hash())"
```

| Tree | `release_hash_of` | `tester_kit.content_hash()` |
|---|---|---|
| base `b0133916` | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` | — |
| subject `d11fe80f` | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` | `('1.2.0', '1ddde587…3991')` |

**Confirmed:** `market-basket-small@1.2.0` still certifies at `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`. The CIR slug, version and title ("Crochet Hexagonal Bread Basket") are unchanged.

---

## Findings

### F-1 — LOW — The held family is gated, but not refused by name

- **What:** `HELD_FOR_VERIFICATION` keeps medium and large inside every per-product gate. But no `publish.eligibility` reason code refuses a held CIR as such.
- **Consequence:** "Unlaunchable" today rests on two things: the first-customer gate (an uncalibrated twin, and no `full_physical_make` bound to the medium or large content) and the owner review. If a medium sample were ever logged and bound, `product_publication("market-basket-medium", …)` could return `publishable: True`. Nothing records the owner's "separately verified future release" decision in code.
- **Mitigation:** `owner_review_required` stays True. Also, no automated path (`seed_launch0`, SEO, shot plans, customer page) creates work for these sizes.
- **Not tested:** what title `listing.seo` would draft for a medium-only release from the nursery candidate. It may still say "3 Sizes".
- **Reproduce:** `legacy_status("market-basket-medium", {"granted": True, "gauge_standard": "x"})` returns `{'in_launch_scope': True, 'legacy': False, 'cleared': True, …}`. `grep -n HELD_FOR_VERIFICATION src/brambleloop/publish/` returns no hits.
- **Suggested fix:** add a `HELD_FOR_VERIFICATION` refusal code in `product_publication` for CIRs whose `candidate_for_cir` is in `l0.HELD_FOR_VERIFICATION`. Clear it only with an owner decision ID.

### F-2 — LOW — `gate_launch0` no longer reports medium and large

- **What:** `gates.first_customer.gate_launch0` iterates `LAUNCH0_SLUGS`, so its summary dropped from 10 variants to 8.
- **Consequence:** the held sizes are still gated at publication (F-1), but they no longer appear in the whole-launch first-customer report.
- **Reproduce:** `PYTHONPATH=src python -c "from brambleloop.gates import first_customer as fc; r=fc.gate_launch0(); print(r['variants_checked'])"` prints `8`, and `market-basket-medium` and `market-basket-large` are absent from the products.
- **Suggested fix:** iterate `LAUNCH0_SLUGS + HELD_FOR_VERIFICATION`, and report held entries as `held`.

### F-3 — LOW — "kitchen" and "table" are self-licensed, not CIR-licensed

- **What:** `PRODUCT_LICENCES["hexagonal-bread-basket"]` licenses both words from `candidate.what_it_is`, which this change also wrote. That is circular.
- **What the CIR supports:** "bread basket" only.
- **Owner's words:** "kitchen and home". "Kitchen" is owner-backed; "table" is an inference.
- **Where it matters:** only the lane-G strategy output ("Kitchen and Table Decor", plus the tags "kitchen decor" and "table decor"). The chain listing that the package ships does not use them.
- **Reproduce:** `T.check_term("table decor", F.launch0_facts()[0], competitors=[])` returns `TERM_UNTRACEABLE: 'table' … not traceable to any CIR attribute`. It passes only through `facts.for_product`.
- **Suggested fix:** cite the decision log (`D-W4-OWNER-BASKET-IDENTITY`) as the licence source for "kitchen", and either drop "table" or have the owner confirm it.

### F-4 — INFO — "storage basket" passes the truth validator for a bread basket

- **What:** `check_term("storage basket", <small facts>)` returns ok. This is pre-existing behaviour that this change did not introduce.
- **Why it is only INFO:** the shipped copy does not use the term. A fixture in `test_r2_product_seo_unicode` uses "Hexagonal Storage Basket".

### F-5 — INFO — The two title sources disagree

- **What:** the strategy title ("…Crochet Pattern | Kitchen and Table Decor | Worsted Cotton | PDF with Chart, US and UK Terms") differs from the chain title that the package ships.
- **Why it is only INFO:** the package states that it uses the chain output, and that a production readback takes precedence. That is consistent and honest.

## Ruling compliance

| Ruling clause | Status |
|---|---|
| Kitchen and home positioning | Met: Home & Table section, new brief, new copy. |
| First listing sells the small basket only | Met: one variant, `basket_small`. |
| Remove nursery, baby and three-size nesting claims (listing and PDF) | Met: verified in the evidence JSON, the regenerated strategy text, the alt text and the PDF assertion. |
| Preserve the larger basket family | Met: the candidate is unchanged and held, and medium and large are still gated and still `under_3`. |
| Keep CA$6.50 pending verification | Met: `proposed_cad=6.50`, evidence `price_cad 6.5`, and "pending final pricing verification" recorded. |
