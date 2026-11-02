# INDEPENDENT_SECREVIEW_INTEG5G — delta review of claude/w5-INTEG1 50937469..5ba84bf7

Reviewer: independent, read-only. Scratch worktree at 5ba84bf7 (detached), now removed. No deploy, no spend, no Railway.
Date: 2026-11-02 (UTC)

## Verdict: SHIP (certification of 5ba84bf7)

All 19 requested suites pass, run one at a time. No assertion was weakened. Each root cause matches its commit message, and each fix is the minimal correct one. One MED finding: the new "two colours" rule is looser than it should be. No current catalogue product is affected, so it does not block certification, but it should be tightened before generated titles or tags use the phrase.

## Findings

### INTEG5G-1 — MED — the "two colours" claim is backed by any second colour, of any amount, and by 3 or more colours
`launch0.technique_backed("two colours", motif)` returns True whenever `colours_used >= 2`, counted over every cell of the twin's colour grid. Before db463142 the variant mapped to "colourwork", whose motif rule refused all of these cases (though for the wrong reason). These now pass in `fabric_truth` (the CIR title and designer notes) and in `first_customer.colourwork_findings` (the listing title and tags):
- a single contrast stitch in an otherwise one-colour fabric: backed
- one trim or border row in a second colour: backed (arguably true)
- three-colour stripes claimed as "two colour": backed, which is false

Mitigation in place today: the SEO tag path also requires the `seo.facts` licence, which needs exactly 2 declared colours (`len(base.colors) == 2`). Every catalogue product with the tag `two color crochet` works exactly 2 colours, with a minority share of at least 21% (cloudline 44%, ornaments, nordic and placemats 50%, baskets and coasters 21–23%, key basket 43%). The CIR title and designer-notes path in `fabric_truth` has no such licence.

The rule also has no direct unit test. No suite asserts that the "two colours" claim is refused on one-colour fabric, a single stitch or 3+ colours. The only coverage is indirect, through test_w3_seo_strategy (positive) and the OPUS2J/K suites.

Recommendation: back the claim only when exactly 2 colours are worked AND the minority colour is at least 10% of worked stitches (the same floor as `COLOURWORK_MIN_MINORITY_SHARE`). Add negative tests for one colour, a single stitch, one trim row and 3 colours, plus a positive test for striped fabric. A minimum share is needed.

Repro (PYTHONPATH=src):
```
from brambleloop.products import launch0 as l0
one=[["A"]*20 for _ in range(30)]; single=[r[:] for r in one]; single[10][3]="B"
three=[["ABC"[(r//4)%3]]*20 for r in range(30)]
l0.technique_backed("two colours", l0.colourwork_motif(single))  # (True, ...)
l0.technique_backed("two colours", l0.colourwork_motif(three))   # (True, ...)
```

### INTEG5G-2 — LOW — the teardown reader's round-join exclusion also hides join-as-you-go assembly
`SECTION_CUE_EXCLUSIONS["assembly"]` removes `join(ing) [a|the|each|every] [new] round(s)` and `joining sl st|slip stitch|ss`. These phrases used to count as assembly and no longer do:
- "Joining Round"
- "Joining round (join-as-you-go)"
- "join the round of squares to the border"
- "make a joining sl st into the corner of the adjacent motif"
- "join the rounds of the two panels together"

These are real assembly sections in competitor join-as-you-go patterns. The reader is an intelligence and inventory tool, not a truth gate, so the impact is a missed section in a teardown. Real assembly phrases still count ("Joining the motifs", "join the motifs", "Seaming", "Assembly", "Putting it together").

Pre-existing and not a regression: "Sew the pieces together", "Whip stitch…" and "Mattress stitch…" were never cues.

Suggestion: narrow the exclusion to "join(ing) [with a] sl st to the first st" or "end of the round" forms, or exclude only when no motif, square or piece noun follows.

### INTEG5G-3 — LOW (pre-existing, not a regression) — gaps in claim detection
`colourwork_claims` does not detect any of these:
- "Two Colours Blanket" and "Two Colors Blanket": the plural fails the `\btwo colour\b` word boundary
- "2 Colour", "Two-Tone", "Bicolour"
- "C2C" and "Corner to Corner": a construction, not a colourwork technique, so arguably fine

On one-colour fabric these pass silently. The parent behaves the same. The technique words (tapestry, fair isle, colourwork, mosaic, intarsia) are unaffected and are still judged by their own rules. Mosaic, overlay, graphghan and intarsia stay refused on every grid probed.

### INTEG5G-4 — INFO — the PDF kicker change alters the bytes of every one-piece PDF
The kicker is "Final steps" when `cir.assembly` (the list of Seams) is empty, and "Assembly and finishing" otherwise. So a product with real seams keeps the assembly label, and none is mislabelled. "Final steps" is never a false statement.

I extracted the text of both regenerated tester-kit PDFs, old and new. The only difference is the kicker, at 2 places in each. Both manifest digests equal the sha256 of the new files. No suite pins PDF bytes. Any `pdf_sha256` stored at runtime will differ on re-render, which is expected.

### INTEG5G-5 — INFO — a stale docstring
The `culture/classify._outcome_unknown` docstring still names `gateway.anthropic._classify_failure`. Cosmetic only.

## Per-change judgement

- **CIR contract v2.** I computed the CIR fingerprint now: `6c88ab1543d4c5eb`. The same shape with `Op.color` removed hashes to `8265022276e81c44`, which is exactly the old pin. So `Op.color` is the only shape change since the pin. `model.py`'s diff since 0967c3ee adds only that field and two helpers. Only `quality_ops` and `engineering_ops` call `require("cir", …)`, and both are re-pinned to 2. `contracts.check()` returns []. The `ops/CONTRACT_CHANGES.md` row hash matches the fingerprint. The stale-pin probe in test_w4_contracts now covers v-1, v+1, 0 and an unknown contract. It is stronger than before, not weaker.
- **"two colours".** The root cause is right: the striped cloudline blanket's true tag was being refused. The fix over-corrects; see INTEG5G-1. One-colour fabric is still refused. The OPUS2J/K suites are unchanged and green.
- **PDF kicker and teardown reader.** The root cause is right and the label fix is correct. The reader exclusion is slightly over-broad; see INTEG5G-2. The new guard test is a pure addition.
- **Cloudline re-freeze.** `controlled.py` (the drift check) is unchanged. Only the detail and rules hashes changed. `definition_version` went 1 → 2, with a `refrozen` record giving the reason and the method. Owner authorization is bound to the definition sha256, so the earlier authorization no longer matches (none existed). Spend caps are counted per `definition_id`, so they are not reset. test_w4_visnext2 fails on the old hashes and passes 11/11 on the new ones, which shows the new hashes equal what the verifier computes. I did not compute the hashes independently outside the suite.
- **`_seed_for`.** The lookup is an exact set membership over `{size_slug(s) for s in nordic_forest.SIZES}`, and every slug in it resolves only to `CONCEPT_SLUG`. Undeclared slugs inherit nothing: the new test asserts that `-giant` returns None, and F5's harbour-fog assertion is kept. POOL exact match and the alias are still checked first. The generated slugs are byte-identical, so the release fingerprints are unmoved.
- **Provider boundary.** `providers.classify_failure` is a straight delegation to `anthropic._classify_failure`, so behaviour is identical.
- **Adopt guard.** The exempted line is a stage name emitted after a `PUBLISHED_LISTING_STATES` check, and the exception names its reason. Fine.
- **suite_final_segment.** 3 declarations added; nothing removed.

## Removed or changed test lines (git diff 50937469..5ba84bf7 -- brambleloop/tests | grep '^-')

1. test_w4_contracts: `("cir",0),("cir",2),…` became `cir_v-1, cir_v+1, 0, unknown`. Justified, and stronger: it now refuses v1 (stale) and v3.
2. test_w4_fmbatch1_contracts: `PINNED_CIR` 8265… → 6c88…. Justified: I verified it equals the fingerprint, and the change is declared in `CONTRACT_CHANGES.md`.
3. test_w4_launch_review: `market-basket-small@1.2.0` → `@1.3.0`. A version pin following PDF1's owner-decided release.
4. test_w4_listready (3 lines): the basket goes to 1.3.0 and the coaster to 1.2.1. Version pins only; the counts and order assertions are unchanged.

Everything else in the test diff is added assertions or tests: the teardown_reader guard, the concept_intake size-slug and `-giant` checks, and one adopt-guard allow entry, which is justified above.

## Suite results (5ba84bf7, one at a time, PYTHONPATH=src:tests, venv-integ4)

| suite | result |
|---|---|
| test_w4_contracts | PASS (8 OK) |
| test_w4_fmbatch1_contracts | PASS (5) |
| test_w4_fmbatch1_provider_boundary | PASS (5) |
| test_opus2_culture_sweep_timeout | PASS (8) |
| test_w3_seo_strategy | PASS (12) |
| test_opus2_cir_colourwork | PASS (17) |
| test_opus2_tapestry_basket | PASS (7) |
| test_first_customer_gate | PASS (12) |
| test_teardown_reader | PASS (13) |
| test_teardown_proof_run | PASS (7) |
| test_w4_visnext2 | PASS (11) |
| test_w4_listready | PASS (rc 0) |
| test_w4_launch_review | PASS (rc 0) |
| test_cert_publish_gates | PASS (0 failed) |
| test_cert_orders | PASS (0 failing) |
| test_w5_concept_intake | PASS (0 failures) |
| test_w4_adopt_manual_listing | PASS (rc 0) |
| test_w4_resume_runner | PASS (rc 0) |
| test_vacuity | PASS (rc 0) |

No Traceback or FAIL markers appeared in any output. No suite was UNKNOWN.

## Commands
```
git -C /home/user/Project-Money fetch origin claude/w5-INTEG1
git -C /home/user/Project-Money worktree add --detach <scratch>/integ5g 5ba84bf7
git log 50937469..5ba84bf7; git diff 50937469..5ba84bf7 -- brambleloop/src ops brambleloop/scripts brambleloop/tests
cd <wt>/brambleloop; for s in <19 suites>; do PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/$s.py; done   # sequential
probes: <scratch>/probes5g/p1.py (claims/backing), p2.py (catalogue colour shares), p3.py (assembly cues); kit PDF text diff via pypdf
git -C /home/user/Project-Money worktree remove --force <scratch>/integ5g
```
