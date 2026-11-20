# MASTER SPEC ERRATA — Brambleloop Final Master v1.0 (Audited)

Source: `spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf`, sha256
`526ed69c8cf9b50e8b5ed736301607b0d314f7e80126ebd5a2178e9689471a99`, 74 pages. Text extract
`research/final_build/master_v1.0.txt` (pypdf, 4,394 lines). Registry `master_registry.json`
(`parse_master.py`, pinned by `tests/test_final_master_registry.py`). Independently re-read in full by
Codex (`research/final_build/codex/FINAL_BUILD_CODEX_STATE.md`: "866 records 859 IDs; 631-650
absent, 514-520 duplicate qualified IDs retained") — two models, same result.

No requirement is invented, renumbered or discarded by any resolution below.

## E-1. F-631..F-650 do not exist — SOURCE numbering gap, not a parsing loss

Evidence:
- A page-by-page scan of the PDF itself (pypdf `extract_text` on all 74 pages, regex
  `F-6(3[1-9]|4\d|50)`) finds **zero** occurrences of any ID F-631..F-650 — not as definitions, ranges,
  cross-references or supersession targets. The text extract agrees.
- The Master's own version notes bound the gap: page 50, "v0.18 appends F-601 through F-630"; page 54,
  "v0.19 appends F-651 through F-700. All prior requirements remain in force."
- Section numbering skips at the same boundary: §64 "24/7 ACCEPTANCE TESTS" (v0.19) is followed by
  §67 "AUTONOMY, CONTINUOUS LEARNING & MULTI-MODEL TEAMWORK" (v0.20); §65–§66 never appear.
- v0.19's own range headings start at "F-651–F-660".

Cause: numbering in the source document (the author reserved or skipped a block between the v0.18
and v0.19 addenda). Not a pypdf, layout or parser defect.
Canonical resolution: **F-631..F-650 are unassigned.** They are recorded as `absent_ids` in the registry
and carry no requirement. Nothing waits on them.

## E-2. F-514..F-520 are defined twice with different meanings — SOURCE integration collision

Evidence (registry `source_lines`):
- v0.15 §59 "Registry additions" table defines F-501..F-520 (F-514 Outcome-Based Improvement …
  F-520 Sell-Learn-Improve Standard), master lines ~2790–2875.
- v0.16 §53 defines F-514..F-550 (F-514 Etsy Surface Inventory …), lines 2880–3103, and its opening
  states it "strengthens rather than replaces Build 2 and the existing F-001+ / F-501-F-513 Etsy
  requirements" — i.e. v0.16's author treated only F-501..F-513 as taken.
- v0.16 also restarts section numbering at §53 (v0.15 already used §52–§59).
- Neither addendum says it supersedes the other; the seven pairs do not conflict in substance
  (v0.15's are business-improvement principles, v0.16's are Etsy shop-OS mechanics).

Cause: when v0.16 was appended, its author started at F-514 without accounting for v0.15's
F-514..F-520 (historical integration, not parsing).
Canonical resolution (D-FB-2): **both sets are in force.** Registry carries them as
`F-5xx@v0.15` and `F-5xx@v0.16` (14 records for 7 IDs). Any reference to a bare F-514..F-520 must be
qualified; where a later section cites one without qualification, read it as the v0.16 Etsy meaning
when the context is Shop Manager, otherwise the v0.15 meaning, and flag it.

## E-3. "F-001..F-879" vs 866 parsed records — arithmetic, not missing content

- Highest ID defined: F-879 (v1.0 §90).
- IDs that exist: 879 − 20 (E-1) = **859 distinct IDs**.
- Records: 859 + 7 second definitions (E-2) = **866 records**.
- Every ID in 1..879 is accounted for as present or absent (test
  `test_every_declared_id_is_accounted_for_as_present_or_absent`). No parsed record swallowed a section
  heading or version note (`test_no_requirement_swallows_a_section_heading_or_version_note`).

Canonical resolution: the Final Master contains 859 distinct requirement IDs and 866 requirement
records. "879" is the top of the numbering, not a count.

## E-4. Related source irregularities (recorded, no action)

- v0.15/v0.16 duplicate section numbers §53–§59 (see E-2).
- Some ID ranges are expressed as headings ("F-651–F-660 · …") rather than per-row tables; the parser
  ignores range headings and reads the individual rows (all 50 v0.19 IDs present).
- v0.21 uses "F-731 · Title - text" and v0.19 "F-651 Title — text"; both formats parsed (rows checked
  by test for non-empty title and text).

## Owner action

None required. If the owner ever intends F-631..F-650 to carry content, it must come as a new
addendum; Final Build will not infer it.
