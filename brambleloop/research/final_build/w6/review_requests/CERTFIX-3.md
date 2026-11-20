# CERTFIX-3 — review request

- Branch: `certfix/3`, cut from `claude/w6-INTEG8-wip` at `511a8c6` (Batch 18).
- Fix commit: `a3334a5` (code, tests, kits, decisions). This file is committed on top of it; the
  SHA of the tip is the commit that adds this file.
- Failures taken from `origin/cert-results/b098fcce` and `origin/cert-results/dde3ea62`.
- Interpreter: python 3.13, venv from `requirements.lock` + `requirements-test.lock`, each suite run as
  `PYTHONPATH=src python tests/<suite>.py`, 4 in parallel, on the tree at `a3334a5`.
- NOT merged, NOT deployed. No PR opened. No Railway variables or secrets read.

## Per-suite results (on `a3334a5`)

| Suite | Result |
|---|---|
| test_cert_design | 14 OK / 0 FAIL |
| test_opus2_size_claims | 13 OK / 0 FAIL |
| test_s1_fix_size_families | 14 OK / 0 FAIL |
| test_s1_product_truth_2 | 11 OK / 0 FAIL |
| test_physfix | 48 / 48 (after the coaster kit rebuild; the first run showed the coaster kit was stale too, masked behind the basket) |
| test_provenance_write_path | 19 OK / 0 FAIL |
| test_shadow | SHADOW_RESULT |
| test_ws4_stage_a_withdrawal | 13 OK / 0 FAIL |
| test_codex_v1_blind_comparison | 43 OK / 0 FAIL (already passing on 511a8c6; nothing changed) |
| test_codex_v1_craft_enum | 13 OK / 0 FAIL (already passing on 511a8c6; nothing changed) |
| test_codex_v1_spend_guard | 62 OK / 0 FAIL (already passing on 511a8c6; nothing changed) |
| test_vacuity | 8 OK / 0 FAIL |
| test_w4_resume_runner | 40 OK / 0 FAIL |
| test_compiler / test_twin / test_reverse | 9 / 8 / 18 OK, 0 FAIL |
| Neighbours run because the fixes touch them | test_garment_design 25, test_garments 15, test_eng_garment 28, test_benchmark_garment 12, test_a1r_child_safety_core 12, test_childrens 40, test_eng_colourwork 20, test_eng_families 16, test_eng_plush 25, test_eng_supply 17, test_pdf_premium 27, test_pdf_standard 23, test_deliverable 14, test_s1_product_truth_3 16, test_ws4_7_issuer 34, test_ws4_stage_a_activation 16, test_w3_decision_index 2: all 0 FAIL |

The full 1000-suite certification was NOT re-run here. The other Batch 18 failures (cert_wiring,
r5_research_*, swarm_runtime, w4 contracts/drift/licences, etc.) were not in scope and are not claimed fixed,
except test_w3_decision_index, which passes because the index was regenerated with the new decisions.

## What each fix is (decisions D-CERTFIX3-* in DECISION_LOG.md)

1. **test_cert_design** — two causes. (a) `products/garments.drop_shoulder_flat` sleeve->body and
   neckband->body seams never said "through both loops ... bury the tails": the notes now say it (writer fix;
   JOINS_VALIDATED unchanged). (b) The next refusal was CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN: `acorn-drop` is
   a *teen* concept but was graded CYC 2-16, so sizes 2-12 are child garments with sewn-on sleeves, held by
   D-ENG-GARMENT-4 ("a seamed child garment still needs physical evidence"). The gate is untouched. A teen now
   grades at CYC youth 14 and 16 only (`garment_design.TEEN_SIZES`); a child recipient is still 2-16 and held
   where the gate holds it. Reviewer: decide whether 14/16 is the right teen range.
2. **test_opus2_size_claims** — the At-a-glance SIZES row printed "9 sizes; this document is size XL",
   a real promise the size gate is right to refuse. It now prints "size XL of 9 in the size chart (see Sizes
   and fit)", the reference wording the gate already exempts. Gate unchanged.
3. **test_s1_fix_size_families / test_s1_product_truth_2** — decision: under the colourwork family pairs
   the refusal is correct *for a colourwork claim*, and no (colourwork_tapestry, wall_decor) proof exists or was
   added. But `size_truth.TAPESTRY` (S1F-LOW) already defines a bare "tapestry" in wall decor as the object (a
   wall hanging with its own size band) and "tapestry crochet" as the technique. So a wall-decor title whose ONLY
   colourwork word is that object noun routes as S1 drafted it; "Tapestry Crochet ...", "Charted ...",
   "Colourwork ...", or any library motif word ("Wave/Chevron Tapestry ...") is still held with the wall-decor
   reason (`colourwork.wall_object_only`). The same suite's second failure, "Baby Lovey" (refused for the wrong
   reason since ENG-PLUSH), is fixed in `baby.lovey_route`: a lovey naming no head is refused as the band-less
   lovey object instead of being drafted as a bear the title never named; audience words are no longer read as
   head features ("Baby Bunny Lovey" drafts).
4. **test_physfix** — the committed tester-kit PDFs were stale since ENG-PDF-PREMIUM changed the renderer
   (basket 13 -> 15 pages, coaster 13 -> 14). Both rebuilt with `python -m brambleloop.quality.tester_kit`;
   content hashes unchanged; `BASKET_KIT_FOR_OWNER_APPROVAL.md` digests updated (they were already stale).
   **Owner-visible:** if a printed basket kit was already approved from the old digests, the kit bytes changed.
5. **test_provenance_write_path / test_shadow** — since ENG-SUPPLY (`2d5f2eb`), every worker enqueues
   `supply.admit` when a chain ends, so these single-product harnesses drafted the whole Launch-0 catalogue (6
   products in the provenance chain; in shadow the registry's own coaster was re-seeded, re-certified and its
   listing re-drafted, hence `'draft'`). Assertions unchanged; the harness workers now leave `supply.admit`
   queued (`job_types` excludes it). Production behaviour unchanged. Reviewer: the alternative was a code rule
   that supply never re-seeds a slug@version whose certificate was refused; not taken, because the seed is the
   release registry's authoritative CIR, not the refused edit.
6. **test_ws4_stage_a_withdrawal** — a clock bomb exposed a real bug. The fixture policy is valid from
   2026-11-20; before today it read NOT_YET (not stopped). Today it reads NONE "deployment is not Mode T", and
   `standing_withdrawal.stopped` counted every NONE as stopped, i.e. a missing issuer heartbeat would have
   authorised automatic withdrawal of SP-activated listings. That one NONE (`standing_policy.NOT_MODE_T_WHY`)
   still refuses issuance but no longer counts as stopped. **Remaining clock dependence:** these tests use the
   real clock; on 2027-01-18 the fixture becomes ISSUE_PAUSED (still not stopped, fine) and on 2027-02-17 DEAD
   (stopped), when they will fail again unless the fixture is pinned to `NOW`. Not changed here.
7. **test_codex_v1_*** — already passing at 511a8c6 (fixed on the branch after dde3ea62); verified, untouched.

## Not done / honest gaps
- No full certification run; test_shadow's remaining slow tests are as listed above.
- No end-to-end colourwork proof for wall hangings (still held, by decision).
