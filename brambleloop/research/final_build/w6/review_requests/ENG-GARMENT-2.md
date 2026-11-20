# Review request: ENG-GARMENT-2 (clothing families)

Branch `eng/garment-2`, cut from `claude/w6-INTEG7-wip` at c6d4400. Not merged, not deployed, no PR opened.

## What was built

All seven families sit in one framework, `products/wearables.py` (an `Engine` registry). Three new modules support it:

- `gates/wearable_fit.py` holds the gates and the read-back grammar.
- `publish/wearable_writer.py` writes the multi-size pattern.
- `publish/wearable_pdf.py` renders the US and UK PDFs.

Every family meets the same bar:

- each size is graded from a sourced table, with stated ease;
- a deterministic CIR is built for each size;
- each size goes through `certificate.certify` (compile, twin, assembly, reverse, child safety);
- the family gates run on every size;
- the reverse compiler reads US and UK back;
- size truth holds per size;
- the US/UK PDFs have a size chart and a schematic and read back to the compiler;
- a registry entry is pinned by research proofs (intake, admit, draft, every size certified, US/UK PDF);
- routing drafts that family's research concepts automatically.

| # | Family (SHA) | Table and sizes | Proofs | Held by name |
|---|---|---|---|---|
| 1 | `hat_beanie` (c235874) | CYC head chart, new: Preemie to Man | adult, child, baby | pom-pom, earflap, brimmed hats |
| 2 | `baby_dress` (dress, pinafore) and `baby_romper` (efc1ef3) | CYC baby, 3m to 24m | dress, pinafore, romper | closures, straps, sleeves |
| 3 | `top_tee`, `top_tank` (7420e81) | woman XS to 5X; child tank 2 to 12 | tee, tank, kids tank | child tee (a sewn sleeve needs physical evidence) |
| 4 | `cardigan_vneck` (10724ae) | woman, child, baby | adult, child, baby | granny-square cardigan (no motif-join engine) |
| 5 | `sock`, `slipper` (406fd93) | CYC foot chart, new: child 10-13 to man 12-14 | 4 | baby sizes (the heel cup is a small part) |
| 6 | `shawl_triangle`, `shawl_wrap` (a452462) | woman neck-to-wrist: XS, M, L, 2X, 4X | 2 | crescent |
| 7 | `bag_tote`, `bag_market` (5a3b626) | ISO 216 sheet held: A5, A4, A3 | 2 | lined, mesh, zip |

The autonomy map, BUILD_STATE and DECISION_LOG entries (D-ENG-GARMENT2-1 to 6) are in bcb3bb8.

## Shared code touched

Please review these closely:

- **`cir/graded.py`:**
  - new HEAD, FOOT and SHEETS tables;
  - `STRETCH_EASE_LIMIT_CM`, which allows negative ease for head (5 cm at most) and foot circumference (3 cm at most);
  - `GradedDesign.primary`;
  - the strict-rise lists extended to the new primary measures.
- **`cir/assembly.py`:** `Footprint.side_cm`. A row-end edge whose rows begin or end with an increase or decrease is now measured along its slope. Unshaped edges are unchanged.
- **`creative/size_truth.py`:** the head and foot chart size names now bind as grades.
- **`gates/risk_matrix.py`:** the plausibility check now uses the family instrument for any wearables build.
- **Routing:** `construction_families` (`is_wearable`, `wearable_route`, the `granny_square_garment` hold) and `runtime/pipeline._draft_wearable`.

## Sources

- The CYC head and foot charts were read on 2026-11-20 by a fetch subagent. The woman-chart sock heights could not be read unambiguously, so they are recorded as UNSOURCED.
- The ISO 216 A-series dimensions come from the table on Wikipedia's ISO 216 page; the ISO catalogue page refused automated reads (403).
- The head-chart ages used for child safety are our own lower bounds, stated as such in the code.

## Tests (final run, 2026-11-20)

The OK counts below are the test lines that passed in each suite.

| Suite | Result |
|---|---|
| `test_eng_garment2` | 67 OK, 0 failed |
| `test_eng_garment` | 28 OK, 0 failed |
| `test_eng_families` | 16 OK, 0 failures |
| `test_compiler` | 9 OK |
| `test_twin` | 8 OK |
| `test_reverse` | 18 OK |
| `test_vacuity` | 8 OK |
| `test_w4_resume_runner` | 40 OK |

These suites also pass with 0 failures: `test_garments`, `test_garment_design` (25), `test_family`, `test_opus2_family_membership`, `test_benchmark_garment`, `test_cert_grading` (10), `test_assembly`, the three size-truth suites, `test_w4_f454_agents`, `test_w4_c12_wiring` and `test_motif_backlog`.

Two suites have pre-existing failures. Both fail identically with this branch's changes stashed:

- **`test_eng_plush`, 3 failures:** an amigurumi PDF reports "Rnd 16 has no stitch count".
- **`test_s1_fix_size_families`, 1 failure:** Baby Lovey.

## Not done

- Nothing has been physically made or photographed, and no listings exist.
- Tops have no neckband.
- The tee's sleeve width is twice the armhole depth, which is wide (boxy).
- The V-neck cardigan's back neck is left plain, with no band.
