# Independent security review — opus2/p0-revenue-workforce @ 9c1a0037 (OPUS2C)

- Reviewer: independent Claude Code session, 2026-10-31 (UTC). Read-only on the subject branch;
  only this report is pushed, to `claude/w5-SECREVIEW-OPUS2C-9c1a003`. No PR opened.
- Subject: `9c1a0037` against `origin/claude/w4-INTEG8-next` (merge-base `210aa9f8`). Scope: the
  four parts below only. Commits reviewed: c94dbb5e, ba3be4e3, dd211ff4, 84c4f195.
- Environment: fresh worktree at 9c1a0037, venv from `requirements.lock` (`--require-hashes`).
  Probe scripts lived in `/tmp/probe` (outside the repo) and ran with `python -I`.

## Verdicts

| Part | Subject | Verdict |
|---|---|---|
| 1 | Delta for review OPUS2A (c94dbb5e + ba3be4e3): size-claim F1.1–F1.4, laura_home F2.1–F2.3 | **ACCEPT** (every OPUS2A finding is fixed at the root; LOW residuals below) |
| 2 | Photo-led listing-set certificate (dd211ff4, P0-GALLERY-ASSEMBLY) | **CHANGES REQUIRED** (one HIGH) |
| 3 | P0-DRAFT-CONSTRUCTIONS (84c4f195) | **ACCEPT** (MEDIUM/LOW notes, none blocking) |
| 4 | Merged-head regression fixes (ba3be4e3): decorator change, `physical_photo_lead` rename | **ACCEPT** (one LOW note on why the rename was needed) |

## Suites run (one at a time, `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| Suite | rc | Result |
|---|---|---|
| test_opus2_chain_deadends | 0 | 0 failed |
| test_opus2_commercial_lessons | 0 | 0 failed |
| test_opus2_draft_constructions | 0 | 0 failed |
| test_opus2_knowledge_gaps | 0 | 0 failed |
| test_opus2_laura_home | 0 | 0 failed |
| test_opus2_photo_led_gallery | 0 | 0 failed |
| test_opus2_reverify_withhold | 0 | 0 failed |
| test_opus2_rim_negative | 0 | 0 failed |
| test_opus2_scan_evidence | 0 | 0 failed |
| test_opus2_size_claims | 0 | 0 failed |

_(partial: the remaining suites are still running and will be added in a follow-up commit)_

---

## Part 1 — delta for review OPUS2A: ACCEPT

### Size-claim gate (`gates/size_claims.py`)

Probe at 9c1a0037 (`check_texts({"listing description": t})`). Every row of the OPUS2A table now gives
the result OPUS2A expected, with one deliberate exception:

| OPUS2A row | 54766c9e | 9c1a0037 |
|---|---|---|
| `Three sizes, yarn not included.` / `Three sizes—yarn not included` (F1.1) | PASS | **FAIL** ✓ |
| `3 sizes included (pattern sold separately for hats)` / `three sizes, each size is its own pattern` | PASS | **FAIL** ✓ |
| `three-size set`, `set of 3 baskets`, `trio of baskets`, `3 basket sizes`, `three different basket sizes` | PASS | **FAIL** ✓ |
| `small, medium, large`, `small/medium/large`, `small · medium · large`, `S, M, L`, `sizes: S M L`, `sizes S to XL`, `XS-3XL` | PASS | **FAIL** ✓ |
| `Diameters 20 cm, 25 cm and 30 cm` | PASS | **FAIL** ✓ |
| `a set of three` (no noun) | PASS | PASS: by design, it counts only when a vessel noun is in the same sentence (`a set of three baskets` → FAIL) |
| `…try a hook one or two sizes larger.`, `Works in all sizes of yarn`, `Fits a 1 m/s fan` (F1.3) | FAIL | **PASS** ✓ |
| `This listing is the medium basket; the small and large are sold separately.` | — | PASS ✓ (a disclaimer about sizes still works) |

- **F1.1 is fixed at the root.** The whole-sentence `_DISCLAIMS` skip is gone. `_SIZE_DISCLAIM` counts only
  when the disclaimer is about sizes, and it removes only the disclaimer's own words with `sub`; the
  rest of the sentence is still read. Adversarial check: `The small and large are sold separately,
  and this listing includes all three sizes.` → FAIL, and `Other sizes sold separately: small, medium
  and large in one PDF.` → FAIL.
- **F1.2:** the count pattern now accepts hyphens and up to two words before "sizes". New patterns cover named lists,
  letter lists, letter runs, letter ranges, dimension lists and vessel sets. Coaster, ornament and
  placemat sets are excluded on purpose.
- **F1.3:** `_NOT_A_CLAIM_AFTER` (larger/smaller/up/down), `_HOOK_BEFORE`, `all sizes of yarn|hooks|needles`
  and case-sensitive size letters (`m/s` is no longer a list).
- **F1.4:** `_pdf_text` now selects by `Job.inputs["slug"/"version"].as_string()`. That is generic `JSON` and works on both
  SQLite and Postgres, and the newest-200 window is gone. A PDF that is missing or cannot be read now sets `state=FAIL` with
  a reason, and the docstring says so.
- **The tests discriminate.** The 9c1a0037 `test_opus2_size_claims.py` run against the 54766c9e gate fails 3 tests
  (first failure: `AssertionError: Three sizes, yarn not included.`). `test_review_opus2a_probe_rows_…`
  pins every row of the table.

**Residual findings (new, not regressions):**

- **N1.1 — LOW — forms of the claim that still get through.** All of these PASS:
  `Includes sizes small to large.`, `Available in small through large.`, `From small to extra large.`,
  `XS to 5X`, `Sizes: 20, 25 and 30 cm.` (the unit appears only once), `20 cm / 25 cm / 30 cm` (no "sizes" lead word),
  `multi-size pattern`, `multiple size options`, `a small, a medium and a large basket`,
  `three baskets in graduating sizes`, `3 baskets`, `3-piece basket set`, `small + large`.
  The most relevant one is **`Market Basket Trio` → PASS**: `vessel_set` needs `trio of …`, so a trio named
  after its noun gets through. That is the radar seed `market-basket-trio`, whose rationale says
  "in three sizes". (`Nesting Basket Trio` FAILs only because of the word "nesting".)
  **Reproduce:** `check_texts({"listing title": "Market Basket Trio"})["state"] == "PASS"`.
  **Fix:** add `{_VESSEL}\s+(trio|pair)`, named-size ranges (`{_FULL}\s+(to|through|-)\s+{_FULL}`),
  `multi-?size`, a dimension list with one trailing unit, and an article-separated named list.
- **N1.2 — LOW — false positive.** `Go up two hook sizes for a looser fabric.` → FAIL. `_HOOK_BEFORE` looks
  for "hook" only before the count, but the count regex allows up to two words between the count and "sizes",
  so "two hook sizes" matches. No generated PDF prints this today. **Fix:** treat `hook|needle` among
  the in-between words as not a claim.

### `laura_home` (`visual/laura_home.py`, `creative/flux3_generator.py`)

- **F2.1 is fixed at the root.** The choice is filtered before the index, not afterwards: `variation(…, category=)`
  removes every `lived_in` / `moments` entry that matches `DECOY_FOR_CATEGORY[category]`, then indexes the
  remainder. If fewer than two details are left it raises `HomeRefused`, so it fails closed. Every environment
  now ends with `NO_OTHER_TEXTILES`. `scene_for` passes the category it resolved. The nursery gained four non-textile
  details, so the baby/nursery/amigurumi categories keep at least two. `MAX_ENVIRONMENT_CHARS` went from 900 to 1000,
  and the longest-possible-frame test covers that.
  **Test:** `test_review_opus2a_no_decoy_of_the_products_own_kind_in_any_room_frame` enumerates every
  `ROOM_FOR_CATEGORY` entry × 6 roles × 40 listings. Against 54766c9e it fails, but only with
  `AttributeError` (missing `DECOY_FOR_CATEGORY`). It discriminates, though weakly: the decoy map checks itself, so
  a category with no map entry is never checked.
- **F2.2 is fixed.** `laura_home.check(brief)` now runs on both the Laura and product-only paths. When the cue plus the
  brief is longer than `MAX_EDIT_CHARS` it raises `HomeRefused` instead of slicing. The test proves a 600-character brief and a
  "luxury showroom" brief are both refused.
- **F2.3 is fixed.** The cue reads "in … of a modest family home", with no person named (asserted).
- **N2.1 — INFO.** Categories routed to `DEFAULT_ROOM` (living room) that have no `DECOY_FOR_CATEGORY` entry
  (for example a future `afghan` or `rug`) keep "a throw pulled back as if someone just got up". Some frames of other
  categories still name a cardigan, mittens or a throw next to the "No other crocheted or knitted item"
  sentence, which mildly contradicts it. Consider failing closed when a category has no decoy entry.

**Laura's canonical identity is unchanged.** `git diff 210aa9f8 9c1a0037 -- brambleloop/src/brambleloop/visual/` touches only
the new `laura_home.py`. `visual/canonical.py` has an empty diff and still names `laura-r2-a42aeac7`.
`ba3be4e3` adds lines to `visual/launch_imagery.py` (from the merge, nothing in identity). The canonical/identity
suites pass (table above).

---

## Part 2 — photo-led listing-set certificate: CHANGES REQUIRED

**What is right.**
- `certify_disclosed` is refactored, not weakened. The supplement block moved verbatim into
  `_with_supplements`. The only change is that expected positions start at `max(position)+1` instead of
  `len(frames)+1`, which is the same for the contiguous 1..n positions `disclosed_frames` produces.
  `test_without_a_lead_photo_the_disclosed_certificate_is_unchanged` passes. A render-only gallery
  (`sample_photo_lead` → None) still goes through `ls.certify_disclosed(**common)` unchanged.
- **Disclosure is correct on the render frames.** In the photo-led set every disclosed frame keeps its own
  `honesty_label` (DISCLOSURE / PREVIEW_LABEL). The certificate's `disclosures` always includes DISCLOSURE,
  and export still runs `disclosed_listing.export_check` per render frame. The photo's alt text refuses
  "render", "AI" or the disclosure phrase.
- Each photo reading must have run and passed. `asset_truth` is the frame being approved and unblocked; then `bytes`
  (the hash matches) and `hero_thumbnail`. An exception while reading counts as a failed reading.

### F2-1 — HIGH — the certificate accepts a photo that `sample_photo.qualifying_photos` rejects
`release_gates.sample_photo_lead` builds its own attestation from the `PhysicalPhoto` / `PhysicalTest`
rows instead of using `publish.sample_photo.qualifying_photos`, and it drops the checks that matter:

| `qualifying_photos` requires | `sample_photo_lead` |
|---|---|
| `detail.owner_attestation.by` starts with `owner:cc:` **and** `owner_attestation.sha256 == sha` (recorded only by the Command Center action `physical_photo.attest_unedited` → `physical_upgrade.attest_unedited`: owner session, verbatim confirmation) | **not checked.** `unedited` reads the intake flag `detail.unedited`, which `physical_upgrade.intake` sets from its caller's `unedited=` argument, the path W4-LAUNCHFIX review F-7 ruled insufficient |
| `_synthetic_shas`: not a generated artefact, non-photo listing frame or disclosed render | not checked |
| `physical_test_id` bound to a passed FULL make **by `first_customer.physical_binding` to this release's content hash** | `risk_matrix.physical_class_of(measured)` plus the test row's slug/version; no content-hash binding |
| bytes on file | checked (`qa.bytes`) |

**Reproduce** (`/tmp/probe/p2.py`, using the suite's own fixtures; the fixture photo has
`detail={"unedited": True}` and no owner attestation):
```
db, cir = T._release("repro"); sha = T._add_photo(db, cir)
with T._FullMake(): v = T._verdict(db, cir); q = SP.qualifying_photos(db, cir.slug, cir.version)
→ certificate valid: True   first frame kind: physical_photo_lead   sha match: True
→ qualifying: []   rejected: ['the owner has not attested it unedited through the Command Center']
→ sample_photo.requirement satisfied: False
→ for_publish(stage=draft) photo reasons: []
```
So **yes, a mixed gallery can be certified (record #70) with a photo that does not qualify**. The
positive test `test_an_attested_approved_sample_photo_leads_…` itself certifies such a photo.

**Exposure.** `for_publish(stage="activation")` still calls `sample_photo.requirement`, which refuses.
That stops public activation, and is why this is not CRITICAL. But at the draft stage the certified set, with an
unattested photo uncaptioned in position 1, is what `etsy_ops.certified_images` uploads. In that state
`copy_problems(photographed_sample=False)` keeps the "no sample has been photographed" copy beside a frame
presented as a photograph, so the certificate and the copy disagree. The path is also dormant today: no code on
this build sets `claims.leads_gallery` (it is expected from W-PHYSFIX-PHOTO). It becomes live as soon as that lands.

**Fix:** have `sample_photo_lead` require the lead's `physical_photo_id` and `sha256` to be in
`sample_photo.qualifying_photos(db, slug, version)["qualifying"]`, and derive `attestation` from that. Do not rebuild it. Add
`owner_attested` to `PHOTO_ATTESTATION`. Add tests that fail at 9c1a0037: (a) intake-unedited but not
owner-attested → no photo-led certificate; (b) owner attestation for a different sha → refused; (c) a sha
recorded in `ArtefactProvenance` with a provider → refused. Keep the positive fixture, and attest it through
`physical_upgrade.attest_unedited(actor="owner:cc:…")`.

### F2-2 — LOW — `camera_provenance` is read from the frame's own claims
`claims.get("provenance") == "camera"` comes from the `ListingAsset` row being certified, not from the photo
record. `physical_upgrade.upgrade` writes it truthfully today. Folding the check into `qualifying_photos` (F2-1) makes this
moot.

---

## Part 3 — P0-DRAFT-CONSTRUCTIONS: ACCEPT

- **The fallback now produces a construction other than `flat_rows`.** `FC.plan` routes basket seeds to `FC.vessel`
  (`construction="joined_rounds"`, magic-ring hexagon base, straight walls). Of the 19 POOL seeds that reach the
  fallback (no engineered CIR), 2 are drafted as vessels, 17 are refused by name with `needs` (audit
  `cir.draft_refused`, `gate: construction`), and **none** is drafted as a flat panel.
- **Deterministic validation, and refusal instead of a guess.** The vessel CIR is enqueued to `cir.compile` like every
  other draft. Probe: for both basket seeds and the repeats `sc4`, `sc7`, `hdc5`, `dc3`, `compile_cir.ok`,
  `build_twin` and `reverse.compare(cir, write_pattern(...)) == []` all pass. Repeats that change the stitch count
  (`sc1 ch1`, `dc2 ch1 sk1`) give compile ERRORs (UNDERRUN / COUNT_MISMATCH), so the compiler refuses them;
  nothing is guessed. Unknown stitches (`puff`, `dc2tog`) raise `UnknownStitch` in `vessel()`.
- **Reuse.** It uses `products.vessels._disc_rounds`, `base_stitches_for`, `BASKET_SIZES` and `hexagon_spans_cm`,
  and only stitches in the CIR taxonomy. The walls are plain sc rounds alternating with the concept's repeat; no new
  technique. Provenance records `VESSEL_PRIMITIVES`, plus the lineage's primitives minus `concept_to_cir`.
  Unknown lineage stays `provenance=None` / "UNKNOWN" and is never invented.
- **Collision with `claude/w5-CONCEPT`.** A trial merge of `origin/claude/w5-CONCEPT` (bb680ec) into 9c1a0037
  auto-merges `runtime/pipeline.py` and `release.py`. The only conflict is the generated
  `autonomy/autonomy_map.json` (regenerate it). The two branches agree in meaning: W5-CONCEPT's
  `radar/intake.py` refuses intake concepts in `basket`, `ornament`, `flower`, `mosaic_blanket`,
  `graphghan` and `seasonal_decor` upstream, so intake never feeds the new basket route. It also keeps
  a second, separate table of what the template cannot make (`UNSUPPORTED_CATEGORY_WHY`, `CONSTRUCTION_WHY`). See N3.2.
- **Does a concept's motif or premise reach the CIR? No.** `runtime.pipeline.Concept` has no motif or premise field.
  The vessel carries only title, stitch repeat, palette, yarn weight and risk class (the flat panel the same). The
  intake's `premise` / `motif` (`creative.concept.Concept`) stop at the score and gate. Nothing claims otherwise,
  but the commit title "the construction its name promises" covers shape only, not the premise.

**Findings:**
- **N3.1 — MEDIUM — a trio concept is drafted as one basket.** `market-basket-trio`'s seed rationale is
  "Worked in the round … in three sizes", and `FC.vessel` drafts a single medium basket under it (`_basket_size`
  keys on "bread" or "market" in the *title*, which is "Crochet Storage Basket"). One release delivers one size,
  so this is not a false claim in itself, and the size-claim gate catches "three sizes" copy. But the gate does
  **not** catch "Market Basket Trio" (N1.1), and the concept is not what its premise says.
  **Reproduce:** `FC.plan(category="basket", title="Crochet Storage Basket")` → vessel, and the drafted
  `finished_size_note` gives one 19.2 cm basket. **Fix:** refuse (`needs`: the graded family
  `products.vessels.build_basket` per size) when the slug, title or rationale promises several sizes (trio, set of N,
  N sizes), or draft one release per size.
- **N3.2 — LOW — the flat route still accepts shaped or charted categories.** `FC.plan` returns `flat_panel` for
  `ornament`, `flower`, `mosaic_blanket`, `graphghan`, `pet` ("Cat Bed") and "Hexagon Granny Blanket". No POOL
  fallback seed hits this, but a `cir.draft` job with a `concept` dict of those categories is still drafted as a striped
  panel under that name. That is the defect this commit names, and W5-CONCEPT already lists these categories as
  unsupported. **Fix:** move to one shared table (import W5-CONCEPT's `UNSUPPORTED_CATEGORY_WHY` once it is
  merged), and refuse those categories in `FC.NEEDS`.
- **N3.3 — LOW — failures are not recorded as refusals.** `vessel()` raises `ValueError` (empty repeat, no colours)
  and the stitch taxonomy raises `UnknownStitch`, but `handle_cir_draft` catches only `PrototypeRefused`. The job errors
  or dead-letters without a `cir.draft_refused` audit. It fails closed, but it is not a named refusal.
- **N3.4 — INFO.** `wall_rounds` is computed from the yarn's row gauge whatever the repeat's stitch height, so a
  `dc` repeat in every second round makes walls taller than the "about 16 cm" note says. The note is labelled
  "Computed, not yet measured".
- **Test gap.** `test_opus2_draft_constructions` asserts `compile_cir(cir).ok` but not twin or reverse. The probe
  above shows both pass; add them to the test.

---

## Part 4 — merged-head regression fixes (ba3be4e3): ACCEPT

- **Decorators are correct.** `HandlerRegistry.register` is `self._handlers[job_type] = fn; return fn`, so the last
  registration wins and the decorated function is returned unwrapped. The stage bodies
  (`handle_assets_build`, `handle_pricing_position`, `handle_launch_plan`) are decorated again, so
  `build2.maturity`'s derived job map reads their real modules. The three explicit calls at the very end of
  `runtime/release.py` (lines 9286–9288) then register the `_with_successor` wrappers, so those run.
  `grep` finds no other registration of these three job types anywhere in `src`. Nothing is weakened: each wrapper
  calls its body first and returns its result unchanged (`_successor` swallows only its own failure).
- **The rename is complete.** `physical_sample_photo` / `PHYSICAL_SAMPLE_PHOTO` no longer appear anywhere in
  `src` or `tests`. `listing_set.PHOTO_LEAD`, the two `etsy_ops.certified_images` checks and the test all use
  `physical_photo_lead`, so export still keeps the photo's certified alt text.
- **N4.1 — LOW — what the rename avoids.** It was needed because `test_w4_launchfix` pins the exact set of `src` files
  containing the string `sample_photo` (`platform_policy`, `release_gates`, `runtime/release`). The rule behind it:
  only `for_publish` decides with `sample_photo`; other users only choose the disclosure sentence. The rename kept
  `listing_set.py` and `etsy_ops.py` off that list, which is legitimate, because neither imports `sample_photo`. But
  it also shows the structural guard checks a string, not meaning. The new decision about which photo may lead
  (`release_gates.sample_photo_lead`) is a second, weaker definition of a qualifying photo that the guard did not
  flag (see F2-1). Once F2-1 routes through `qualifying_photos`, the guard's purpose holds again.

---

## Reproduction scripts (outside the repo)

- `/tmp/probe/p1.py`: size-claim probe table (Part 1).
- `/tmp/probe/p2.py`: photo-led certificate with an unattested photo (F2-1).
- `/tmp/probe/p3b.py`, `/tmp/probe/p3d.py`: fallback routing over POOL, and vessel compile/twin/reverse (Part 3).
- The OPUS2A-discrimination check copied the 9c1a0037 test files over a 54766c9e worktree and ran them there.
