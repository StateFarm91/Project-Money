# W-VISNEXT: the remaining autonomous-visual engineering

- **Branch:** `claude/w4-VISNEXT`, from `origin/claude/w4-WRAPTEST` 31e5347 (FLUXAPI d3679fe,
  VISAUTO d767208, FIDELITY 298e3156), with `origin/claude/w4-INTEG3` 364ade0 merged first
  (checkpoint cd4ca168), so the branch sits on the deployed code (b931d17).
- **Scope:** offline and SHADOW. Nothing was deployed, published, or written to production.
  No paid call was made, no key was read, and no credential was changed. Every judge answer
  in the tests is a recorded fixture (`tests/fixtures/visnext/readings.json`). These fixtures
  are hand-written in the exact shape each prompt asks for, because no real reading exists yet.

## 0. INTEG3 merge

| Conflict | Resolution |
|---|---|
| `core/db.py` boot imports | Both kept: W-OWNERIMG's `visual.image_records` and REL2's `creative.prospecting`. |
| `autonomy/autonomy_map.json` | Regenerated from the live wiring with `python -m brambleloop.autonomy.map --write`: 133 handlers, 30 agents, 62 follow-on edges. `test_v11_autonomy_timeline` passes 7/7. |
| `test_w4_wraptest` failed-call billing | The assertion hard-coded the old rate, 0.13986. It now derives the 2k price from `gateway.images` and `core.fx`, because INTEG3 moved the rate to the Bank of Canada figure of 1.4154. The live CA$5 cap and the per-role limits are unchanged. |

## 1. Vision-judge adapters (OWNERIMG E2): `visual/vision_judges.py`

There is one transport: the existing judge interface, `read(prompt, images, *, system,
max_tokens)`. In production that is `fidelity.GatewayVisionJudge`, which works as follows:

- It is gated on `image_vision`.
- It reserves budget with `gateway.anthropic.check_budget` before the call.
- It bills the actual cost through `inspect._bill` after the call.
- If the gate is closed, the budget is refused, the provider fails, or the reply is not JSON,
  the check is UNKNOWN and nothing is sent. Tests:
  - `test_unfunded_or_closed_gate_is_unknown_and_calls_nothing`: the provider raises if it is
    called;
  - `test_open_gate_reserves_budget_before_the_call_and_bills_after`: the order is reserve, see,
    release with the actual cost; a refused budget means no call and UNKNOWN.

Each question is **blind**:

- It never states the expected answer.
- The outfit prompt is byte-identical whatever outfit is reserved (tested).
- No prompt names Laura, the palette or the product.

Each question is **structured**: the answer is a closed vocabulary, and it is compared in code.

| Adapter | Images | Compared against | Fails as |
|---|---|---|---|
| identity | Three canonical references (verified by sha256) plus the candidate. Two judges see opposite image orders. | `identity_gate.assess`, with the generator's conditioning receipt (byte counts measured here) and the judge pair. Readings the generator itself supplied are never used. | identity_drift (AUTO_REFUSE) |
| body_proportions | The same reading (one call per judge per image) | `identity._group_verdict` on the morphology group: at least 3 readable dimensions, bust and torso required | body_proportion_drift |
| outfit_consistency | The candidate. Each of the 5 slots is described as `visible`, `garment`, `colour` and `features`. | The reserved outfit, slot by slot, via `wardrobe.parse_garment`. Then the reference clothing, and other listings' outfits (visible-slot similarity ≥ `MAX_SIMILARITY`). | REFERENCE_CLOTHING_CARRYOVER, WARDROBE_REPETITION, or outfit_consistency on a slot mismatch |
| anatomy | The candidate | One person in a Laura frame; 5 fingers on every fully visible hand; no listed defect | anatomy |
| realism | The candidate. One defect question per `gallery.REALISM_CHECKS` entry, plus render/illustration and garbled text. | Any "yes" is FAIL; any "unclear" is UNKNOWN | realism |
| craft_texture | (already in `visual.fidelity`) | `fidelity.compare_craft` | WRONG_CRAFT_TEXTURE |
| anchor_consistency | The anchor and the candidate, **each described on its own** | Each other and the CIR: craft, edging, plain end bands, raised cables, colour count | INVENTED_EDGING, INVENTED_END_BAND_TREATMENT, WRONG_CRAFT_TEXTURE, WRONG_COLOUR_LAYOUT |

Pass rules (D-W4-VISNEXT-JUDGES):

- Identity and body proportions need two readings from **different** judges (a different
  transport name or model). The same judge twice counts as one reading.
- One judge can refuse but never pass.
- Identity also needs the biometric floor. `identity_gate.QUALIFIED_EMBEDDERS` is empty, so
  identity tops out at the REVIEW band, which reads UNKNOWN.
- `RealJudges(second_vision=...)` accepts a second judge. Production configures none today.

Wiring:

- `candidate_gates.RealJudges.identity`, `body_proportions`, `outfit_consistency`, `anatomy`
  and `realism` call the adapters.
- `product_truth` passes the blind consistency function and the region detector to
  `fidelity_reading`.
- No gate was relaxed: `evaluate`, `publication_verdict` and F-852 are unchanged.
- Tested end to end with recorded judges: all Laura gates are read; identity stays UNKNOWN;
  publication is still refused by F-852 (test
  `test_evaluate_with_recorded_judges_reads_every_laura_gate_and_publication_stays_refused`).

## 2. Lifestyle product-region detector

**What:** `vision_judges.locate_product`.

- The judge is asked for up to 4 rectangles that lie **entirely on the item's fabric**. It is
  not shown the palette.
- `validate_patches` checks the rectangles deterministically:
  - inside the image;
  - each at least 0.2 % of the image;
  - together at least 1 % of the image.
- `fidelity.verify_lifestyle` now accepts a list of boxes and measures the palette inside them.
  The judge locates the item; the code decides the colours.
- The detector is asked only after the release's anchor has PASSed. Without that the image
  cannot pass, so the call would spend money without deciding anything.

**Tested:**

- Patches on the product give PASS.
- A patch on an off-palette block gives FAIL `OFF_PALETTE_COLOUR`.
- No patch gives UNKNOWN.
- Bad rectangles are rejected.

**Why patches, not a bounding box:** a box around a wrap worn over a cardigan contains the
cardigan, so a correct product would FAIL. Interior patches avoid that.

**Limits:**

- The detector is unvalidated on real FLUX output, because no paid image exists.
- A judge that places a patch on a background of the same colour would let that pixel set
  pass. The patches only feed the palette check. The anchor PASS and the blind consistency
  reading are still required.
- The first paid lifestyle image must be recorded and checked before the region reading is
  trusted.

## 3. Restart of a blocked run (OWNERIMG E4)

`image_production.restartable`, `restart` and `reverify`, plus the CC route
`POST /api/cc/images/runs/restart`.

**Allowed:** a capability block, such as a closed gate, no generator, or a fidelity or vision
reading that was UNKNOWN. This includes an owner-card block whose only causes are UNKNOWN.

**Refused:**

- experiments;
- budget stops;
- any role whose best candidate FAILed (its attempts are spent);
- a run that is not blocked;
- more than `MAX_RESTARTS` = 3.

**Mechanics:**

- The next job carries `epoch` and the key `…:<stage>[:round]:e<epoch>`, so it never collides
  with the first pass.
- A job from an older epoch is skipped.
- Attempts, generation calls and spend carry over. Attempts are counted from candidate rows,
  so the per-role cap and the gallery spend plan still bind.
- A stored anchor or frame is **re-verified in place** with today's judges, and the previous
  verdict is kept in `checks._reverified.history`. It is not regenerated.
- Notifications carry the epoch, so a re-blocked run notifies again.

**Test:**

1. The run blocks at the fidelity gate with the vision gate closed (1 generation).
2. The run is restarted with funded recorded judges.
3. The anchor is re-read as PASS (still 1 attempt), and the run continues to
   `load_laura_references`.
4. A stale epoch-0 job is skipped.

## 4. Approved frames into ListingAsset, re-certified (OWNERIMG E5)

The steps are in `visual/gallery_persist.py`. `approve` calls them only after the state
becomes `approved_for_publication`.

1. Every generated frame on the card is re-verified with the production judges. Each one must
   still be technical PASS and publishable, with F-852, the Etsy policy and Laura's status all
   re-read. One refusal and nothing is written.
2. The frames are written as `ListingAsset` rows of class `AI_LIFESTYLE_CONCEPT`, labelled
   AI-generated and never a photograph, at their plan positions. A position that holds
   different bytes is never overwritten.
3. `release_gates.listing_set` re-judges the set, and its verdict is the answer. When the
   listing's imagery is the disclosed render set (D-FB-7), `listing_set` does not judge
   `ListingAsset` frames. The report then says `generated_frames_judged: False` and blocks,
   instead of letting the disclosed certificate appear to cover the generated frames.

**Tested:**

- A run that is not approved is refused.
- `approve` is refused by F-852.
- A run *forced* into `approved_for_publication` is still refused by the re-verification
  (F-852), and no row is written.
- Rows written directly are re-judged by `listing_set`, which refuses the generated frame
  (POLICY_PROVENANCE, the build gates not run, and F-852). No certificate is issued.

## 5. Command Center gallery card and wardrobe editor (OWNERIMG E6/E7)

**Gallery card:**

- `GET /api/cc/images/runs/card?run_key=…`, built by `image_production.gallery_card`.
- `GET /api/cc/images/candidates/{id}/image` serves the stored bytes unchanged, with
  `no-store`, `noindex` and "AI-generated candidate; never a photograph".
- `images.js` shows the actual images in a grid and three blocks that stay apart:
  1. **Visual approval.** `POST /images/runs/visual-approval` calls `record_visual_approval`.
     It is recorded only. No gate reads it, and the state does not change.
  2. **Technical certification.** The stored verdicts, the set check and campaign
     consistency. The owner cannot change them.
  3. **Publication authorization.** It is "available" only when no blocker remains. It goes
     through the existing step-up `images/runs/approve`, which re-checks every gate.
     `approve` now preserves the visual record.
- The card also shows "Restart at <stage>" when the run is restartable, or the reason it is
  not.

**Wardrobe editor:**

- `GET /api/cc/wardrobe` (`outfits.wardrobe_editor`) returns:
  - every outfit with its garments, listing, state, distinctness and reference;
  - the catalogue;
  - the reference clothing;
  - the similarity rule.
- `POST /api/cc/images/outfits/action` runs approve, reserve, release, replace or
  set_reference. Adding an outfit uses the existing `POST /images/outfits`.

**Outfit reference:** `outfits.set_approved_reference` accepts only a stored image of that
outfit with:

- outfit_consistency PASS;
- identity not FAIL;
- body proportions not FAIL.

It never accepts a canonical identity reference. It is passed to a generator as
`prior_candidate`/`outfit_reference` only if the generator declares
`accepts_outfit_reference`. `Flux3Generator` does not, because its FLUX stage builder does not
carry a supplementary clothing reference. That is a W-FLUXAPI follow-up. Today the reference is
recorded and shown, but not sent.

**Cache:** the service-worker cache was bumped to `cc-shell-v17`.

## 6. Learning: the taxonomy end to end, and the Learn path

`visual/image_learning.py`:

- `taxonomy` groups every recorded failure word under its owner:
  - the Product Truth codes;
  - the wardrobe codes;
  - the gate categories.
- Anything nobody owns is listed in `unclassified`, so it is visible.

**Tested end to end** through the real queue, the real fidelity verifier and the blind
adapters:

- A recorded judge that sees the reference clothing produces REFERENCE_CLOTHING_CARRYOVER ≥3
  (wardrobe) and outfit_consistency ≥3 (gate).
- The repair carries "REPLACE ALL clothing".
- `unclassified` is empty.
- A judge that sees another listing's outfit produces WARDROBE_REPETITION. The outfit is
  re-picked, and the old one is retired.

**The Learn path:**

- `propose_brief_challenger` turns repeated, prompt-negative-routable codes into an
  `improve.league` challenger (kind `prompt`, key `image_production:briefs`). It is never
  promoted here.
- `prompt_version` is unchanged afterwards (tested).
- An identical challenger is not registered twice.
- Per-attempt repairs remain bounded corrections, not learning.

## 7. WRAPTEST harness

- The CA$5 owner-approved live test is unchanged in behaviour and cost.
- Its `LiveJudges` keep their own Laura reading. Their Product Truth runs through
  `RealJudges`, so the anchor-consistency question is now the blind per-image description: one
  call, the same count as before.
- The offline fake network answers that prompt with a recorded description consistent with its
  `same` flag.
- Dry run and live rehearsal: `test_w4_wraptest` passes (112 checks). The harness still waits
  for `BRAMBLELOOP_IMAGE_KEY_BFL` and `ANTHROPIC_API_KEY` in the environment.

## 8. Tests (all through `testslot`, final code, every one exit 0)

| Suite | Result |
|---|---|
| test_w4_visnext (new) | 21/21 |
| test_w4_fidelity | 22/22 |
| test_w4_ownerimg | 35/35 |
| test_w4_wraptest | 112 checks, 0 failed |
| test_w4_flux3generator / fluxapi / fluxstages / fluxtexture | 9/9, 13/13, 16/16, 9/9 |
| test_w4_visref | 14/14 |
| test_v11_pwa_static / test_v11_cc_views / test_web_security / test_w4_ccnotify | 82/82, 14/14, 11 ok, 5/5 |
| test_vacuity / test_launch / test_cost_governance_wave2 | 8/8, 28/28, 39/39 |
| test_search_hero_publish / test_cert_listing_frames / test_v11_autonomy_timeline | 4/4, 7 ok, 7 ok |

## 9. Still blocked on the owner or on funding

1. **`image_vision` funding.** Every adapter reads UNKNOWN until it is funded. Each Laura frame
   costs at most about 8 calls: person ×2, outfit, anatomy, realism, craft, consistency and
   region, each about CA$0.03–0.06. All of them are reserved against the existing ceilings.
2. **A second, independent vision judge** (another model). Without one, body proportions can
   refuse but never pass. Choosing and qualifying that model is an engineering decision that
   follows funding.
3. **Identity PASS** needs a qualified face-embedding model (the biometric floor). Until then,
   every Laura frame is held in the REVIEW band. This is the honest state.
4. **F-852 policy** (VISREF E4) and **the Etsy listing-image policy reading** (VISGATE V1).
   Until both change, no generated frame is publishable, `persist_approved` writes nothing,
   and the LIFESTYLE role stays unfilled.
5. **The CA$5 WRAPTEST live run** needs both keys in the environment, and BFL credit is
   UNKNOWN. Its output is also the first real data for calibrating the fidelity thresholds and
   the region detector.
6. **Generated-frame lineage for `listing_set`.** A generated `ListingAsset` frame has no
   `visual_truth` provenance row, and the disclosed-render path does not judge `ListingAsset`
   frames. W-PRODREADY owns both. Both block (never pass) until then.
7. **A FLUX supplementary outfit reference** (W-FLUXAPI). The approved outfit reference is not
   yet sent to FLUX.

## 10. Follow-ups closed on this branch (coordinator, 2026-10-20)

### 10.1 (7) The approved outfit reference is carried to FLUX

- **Generator.** `Flux3Generator` declares `accepts_outfit_reference` and takes the orchestrator's `prior_candidate`/`outfit_reference` input. It sends that input only when its sha256 equals the outfit's `approved_reference`; anything else is `GeneratorRefused` before any call is made.
- **Stage.** The image goes to `image_stages.lifestyle` as the existing `outfit` supplementary reference. The request order is fixed: the three canonical Laura references, then the four product references, then `product_candidate`, then `outfit`. That makes 9 inputs, within FLUX 3's documented limit of 10.
- **Guards in `campaign_references`.** The request is refused when:
  - the canonical three are not first and in order;
  - the outfit reference is a canonical or retired identity reference;
  - the outfit reference comes before the canonical three.
- **Over the limit.** The existing lossless combined product sheet is used. If the request is still over the limit, it is refused and nothing is sent.
- **Receipt.** The receipt records the reference as `outfit_reference: {position, sha256}`, or None when none was sent.
- **Identity evidence.** The reference counts as a non-identity reference (by the receipt role), so it does not invalidate the identity trial. The same now applies to the anchor and the product references.
- **Tests:** `tests/test_w4_visnext_frames.py`.

### 10.2 (6) Generated ListingAsset frames

- **Provenance.** `gallery_persist.write_frames` records each written frame with:
  - an append-only audit row (`images.listing_asset_written`);
  - a `visual_truth` provenance row, keyed to the frame row and carrying the file sha256. Its lineage is backfilled and cites that audit row. It names the provider, model and cost, and records the evidence kind `ai_generated_autonomous` (#36) and `is_photograph: False`.
- **No matching record.** A frame whose bytes match no generated-candidate record is refused, and nothing is written.
- **Judging.** `release_gates.generated_frame_verdict` judges a generated frame (`claims.source == visual.image_production`) on its role, using its own record:
  - DATA_TRUTH from the candidate's stored technical verdict;
  - LAYOUT_QA from its measured quality;
  - COMMERCIAL_QA from the role, realism and anatomy checks;
  - POLICY_PROVENANCE from the provenance row.

  It is no longer judged on readings from `assets.build`, which never ran for it.
- **Both paths.**
  - `listing_set` uses this verdict for generated frames.
  - `disclosed_listing_set` evaluates generated frames instead of ignoring them. It reports them as `generated_frames`, and excludes refused ones from the certified set (`generated_excluded`). A generated frame that passed its gates would block the listing: the disclosed certificate does not cover a mixed set.
- **F-852.** `eligibility.may_export` still refuses every generated frame. The tests assert the F-852 refusal on both paths, and no certificate is issued. Nothing relaxes F-852 or the publication gates.

### 10.3 WRAPTEST

The harness's generator inherits the capability, but the experiment's freshly chosen outfit has no approved reference. An approved reference needs a stored image of that outfit that the vision judge read as matching, set explicitly. So the CA$5 run sends no ninth image, and it never feeds its own unverified hero back in as a clothing reference. That is the right behaviour for a one-shot experiment.

The offline rehearsal now asserts it (`live_no_outfit_reference_without_an_approved_one`). Cost and number of calls are unchanged.

Blockers 6 and 7 in §9 are closed by this section. What remains of 6 is the owner's F-852 policy decision.

## 11. Later queue on this branch (2026-10-20)

- **D-W4-F852-AMEND.** The verified-exception route is in `publish/eligibility.verified_exception` / `may_export`.
  - **Evidence** is built only from recorded checks, in `candidate_gates.exception_evidence` and
    `release_gates.generated_frame_verdict`.
  - **F-853** is encoded per role in `COMPOSITING_FEASIBLE`. The roles with no protected-compositing path are
    ANGLE and LIFESTYLE.
  - **Today it still refuses** every generated frame, because the Etsy policy reading is UNKNOWN.
  - **Board update** is proposed in `w4/OVERRIDES_PROPOSED_F852_AMEND.json`; it is not applied (F-867).
  - **Tests:** `tests/test_w4_f852_amend.py`.
- **Six-reference baseline** (the owner's method): `--baseline-six-ref` in the WRAPTEST harness,
  `experiment_wrap/baseline_six.py` and `image_stages.six_reference_lifestyle`. Tests: `tests/test_w4_baseline_six.py`.
- **Controlled experiments in production:**
  - code: `experiments/controlled.py`;
  - first definition: `exp-2026-10-20-wrap-7ref`;
  - Command Center routes: `/api/cc/experiments…`;
  - owner guide: `EXPERIMENTS.md`;
  - tests: `tests/test_w4_controlled_experiments.py`.
- **Manual versus automatic:** `MANUAL_VS_AUTO.md`. Stage A (the per-listing Laura identity anchor) and wiring
  stage D to "the accepted lifestyle frame" are **not built**, and are listed there.
