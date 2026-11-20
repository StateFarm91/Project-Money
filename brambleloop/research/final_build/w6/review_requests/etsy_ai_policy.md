# ENG-ETSY-AI-FIX: review request (fix round for ENG-ETSY-AI-POLICY, verdict DO NOT SHIP)

- Branch: `eng/etsy-ai-policy`. Prior head `d821352e`; `origin/claude/w6-INTEG2` @ `93aabde0`
  merged in first (clean, no conflicts).
- The final SHA is the commit that adds this file; it is given in the issue #28 comment.
- Not deployed. Not merged. Nothing touches Railway, production, secrets, Etsy, spend,
  `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`. No human authorship or owner attestation is
  claimed anywhere.

## What changed, per review item

**H1: structural guard, not a blacklist** (`src/brambleloop/publish/etsy_ai_policy.py`)
- Closed allowlist `honest_statements()`: `platform_policy.DISCLOSURES`, `pdf.AI_DISCLOSURE`
  and both `sample_photo.disclosure_copy` variants. These are code-generated. The
  photographed-sample variant stays gated by `sample_photo.copy_problems`.
- The allowlisted sentences are removed exactly. The remaining free text is normalised:
  NFKC, casefold, accents, zero-width characters and soft hyphens, Cyrillic and Greek
  look-alikes, digits used as letters, `h a n d m a d e`, and `h.a-n_d` joiners.
- The text is then refused if it carries any of these claims:
  - first-person making
  - passive making by a person
  - hand-anything
  - homemade
  - human authorship
  - made with love
  - testing
  - sample or physical evidence
  - own creation
- The verb stems cover every inflection and UK spellings (trialled, colour, labour).
- A free-text testing claim is refused even when it is true. The allowlist is the only
  source of honest statements.
- Corpora in `tests/test_w6_etsy_ai_policy.py`:
  - Adversarial: 67 phrases, including all 12 from the review and the Unicode, spacing and
    leet tricks. All are refused.
  - False positive: 23 benign phrases, including "Download my pattern" and "Make a gauge
    swatch to test your tension". All pass.

**H2a: UNKNOWN holds publication**
- `etsy_ai_policy.publication_status(db)` stays UNKNOWN until a named person records an
  `etsy_ai_policy.reading` audit row:
  - status PERMITTED or PROHIBITED;
  - `read_by` filled in;
  - `read_on` on or after the rules' last edit (2026-11-11) and not in the future.
- Anonymous, stale, future-dated or unreadable readings stay UNKNOWN.
- UNKNOWN and PROHIBITED add their reason to `release_gates.for_publish`, which also returns
  an `etsy_ai_policy` field.
- `staleness()`, `retry_hold_reason()` and listing-set issuance are unchanged, so internal
  work continues. A test pins this.
- Nothing in code records a reading. That is owner exception B.

**H2b / H3: the disclosure is required on every package**
- `gates.policy.check_ai_disclosure(description, None)` now requires `ai_assisted_design`.
  Before this change, an unclassified package owed nothing.
- `check_listing` always calls it.
- Mutants that kill this (both now fail the suite):
  - `check_ai_disclosure -> []`
  - "unclassified owes nothing"

**H2c: #39 stays publication-only**
- This keeps eng/recovery's `policy_holds_manufacturing` / `policy_publication_only`
  behaviour.
- `test_policy_39_holds_publication_only` shows that `listing_image_rules`:
  - holds `staleness()`;
  - does not hold `retry_hold_reason`;
  - holds nothing in manufacturing.
- `test_eng_recovery` still passes.

**M4: wired into the listing-package gate**
- `gates.policy.check_authorship` is called from `check_listing` for the title, the
  description and every tag.
- That one gate is what all of these use: `runtime.release` (listing.seo),
  `gates.certificate`, `gates.first_customer` (first-listing doors), `runtime.quality_ops`
  and `commerce.listing_tests`.
- Owner-accepted live copy: `manual_adoption.truth_problems` refuses the baseline.
- `integrations.etsy.build_payload` is still guarded.

**M5: refusals become hold cards with reasons**
- `etsy_ai_policy.hold_card` raises an owner card through `owner_queue.ensure`:
  - key `authorship_copy_hold:<slug>@<version>`;
  - the reason names the phrase and the rule;
  - CA$0, 5 minutes;
  - it blocks publication of that copy only.
- `runtime.release` raises it whenever the policy findings include
  `POLICY_AUTHORSHIP_CLAIM`.
- The over-broad `my (pattern|design)` rule has been narrowed. "My pattern" passes;
  "my own design" and "my designs" are refused.

**M6: audit doc**
- The quotes and access dates are kept.
- A new per-page table says how each page was read: automated API, automated HTML, or 403 /
  404.
- The two API articles were re-fetched on 2026-11-19 and all 11 quotes string-matched
  verbatim.
- The HTML articles are marked as not re-verified.
- No page was read by a person or in a browser.

## Mutation results

`research/final_build/w6/review_requests/etsy_ai_policy_mutate.py` applies one mutant at a
time and runs `tests/test_w6_etsy_ai_policy.py` against it. The source is restored after
each run. Result: **18 of 18 killed, 0 survivors.**

| Mutant | Result |
|---|---|
| M1 `check_ai_disclosure` returns `[]` (review H3) | killed |
| M2 an unclassified package owes nothing | killed |
| M3 `check_authorship` returns `[]` | killed |
| M4 `check_listing` skips the description guard | killed |
| M5 `claims()` finds nothing | killed |
| M6 no Unicode folding | killed |
| M7 no joined form (`de-signed`) | killed |
| M8 no spaced-letter collapse | killed |
| M9 allowlist not removed | killed |
| M10 allowlist removes everything | killed |
| M11 status always PERMITTED | killed |
| M12 anonymous reading accepted | killed |
| M13 stale reading accepted | killed |
| M14 unreadable db is PERMITTED | killed |
| M15 `for_publish` ignores the AI status | killed |
| M16 `hold_card` writes nothing | killed |
| M17 owner-accepted copy unguarded | killed |
| M18 PROHIBITED releases publication | killed |

Not mutated: the `hold_card` call site in `runtime.release` (listing.seo). `hold_card` itself
is tested; the call site is covered only by inspection.

## Suites run (direct `python3 tests/<suite>.py`, 2026-11-20)

`run_tests.sh` stalled after enrolling in its job registry in this container, so the suites
were run directly.

Pass:
- test_w6_etsy_ai_policy (19/19), test_first_listing_doors, test_ws4_hold_cards (8/8),
  test_s1_product_truth_3
- test_eng_recovery, test_cert_commerce (14/14), test_certification, test_gates,
  test_launch0_listing_truth, test_physfix (48/48)
- test_w4_launchfix (32/32), test_w4_secreview_adopt_adversarial,
  test_etsy_readback_observe (37/37), test_shadow_rehearsal, test_w6_fix_only_rebuild
- The other 39 suites that name gates.policy / check_listing / for_publish / manual_adoption /
  build_payload passed in the first targeted run.

Fail, and the same on the base `93aabde0` (pre-existing, not caused by this branch):
- test_w4_listready `test_f4_...`
- test_w4_fmbatch1_drift (4 tests: `_profile` expects one search profile and finds six)

Not finished: test_product_run, which timed out at 2400 s running alongside two other heavy
suites.

E2E: see the #28 comment.

Test changes (fixtures, not weakened gates):
- test_gates and test_launch0_listing_truth copy now carries the design disclosure. Both
  are listing packages.
- test_certification checks the concept-stage draft with `package=False`, as
  `gates.certificate` does.
- test_first_listing_doors records a FIXTURE AI-policy reading, labelled as test data.
- test_w6_listing_chain_e2e adds the UNKNOWN hold to its observed blocker sets.
- test_w4_launchfix adds `etsy_ai_policy.py` to the `sample_photo` users. It reads only
  `disclosure_copy`.

## Known limits (honest)

- This is lexical. A claim phrased with no making, testing or sample vocabulary at all
  passes. An example is a sentence implying human authorship only through a person's name.
  The structural answer is that listing copy comes from templates. This guard is the
  backstop on free text, not a proof.
- The false-positive corpus is 23 phrases, not a census of every template. The suites that
  draft full listings (`test_first_listing_doors`, `test_w4_listready`,
  `test_s1_product_truth_3`) are the wider check that real generated copy passes.
- Publication is now held everywhere until a reading is recorded. This is intended:
  UNKNOWN is never PASS.
