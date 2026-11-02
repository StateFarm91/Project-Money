# Independent security and correctness review OPUS2U: Secondary's fixes for OPUS2Q (and OPUS2T-1/-2/-3 status), 2026-11-02

Reviewer: an independent, adversarial, read-only Claude Code session.
- The review was read-only. No branch or existing worktree was modified, and this report is the only file written.
- Scratch worktrees (`git worktree add --detach`) were made under the scratchpad as `opus2u-<sha>` for fed859b7, 8ed2dd15, 493b76cf, 2f9c413d, e6e6fb94, d3a485a1 and 7493c723.
- Each mutation was applied and then restored by the runner. `git status --porcelain` printed 0 lines in every mutated worktree afterwards.
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
- Suites ran one at a time.

| # | Subject | Branch | Head | Delta reviewed |
|---|---|---|---|---|
| 1 | PR #3 multiplicity reader (OPUS2Q-1, -6, -7) | opus2/p0-revenue-workforce | 8ed2dd15 | fed859b7..8ed2dd15 |
| 1m | same, merged | opus2/p0-revenue-workforce-b4merge | 493b76cf | 04277d26..493b76cf (first parent) |
| 1t | P0-NAME-OBJECT-MISMATCH (OPUS2T-1/-2/-3) | same | fed859b7 (under 8ed2dd15) | status only |
| 2 | PR #9 colourwork claim reader (OPUS2Q-2, -3, -6) | opus2/p0-cir-colourwork | e6e6fb94 | 2f9c413d..e6e6fb94 |
| 3 | PR #11 stocking (OPUS2Q-4, -5, -6) | opus2/p0-stocking | 7493c723 | d3a485a1..7493c723 |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Multiplicity reader (8ed2dd15) | **DO NOT SHIP** | **OPUS2Q-1 is closed for every word named.** All 18 brief words and every OPUS2Q-1 repro have `claimed=None` and no markers: Multicolour, Multipurpose, Multi-Use, Polyester, Polymer, Triangle, Quadrant, Octopus, Decorative, Sextant, Tripod, Quaint, Novelty, Settle, Ballet, Doublet, Trivet, Quartz, plus Multicolored, Multi-Season, Tent Stitch, Fanny/Hip/Ice Pack, Twined, Tiny Bits, Diet, Son Shine. Each one drafts as a tote and is backed by `title_promise` on both the one-piece tote and the Cloudline blanket. Roots are matched as whole-token morphemes (`fullmatch` of root + suffix). **What it breaks:** the fix overcorrects and introduces a **new refused→backed regression**. "Coaster Pack", "Ornament Pack", "Scrunchie Pack", "Dishcloth Pack", "Poly Pack", "Tote Multiple", "Multiples", "Multi Bowl" and "Multi-Pouch" were unbacked on fed859b7. They are now backed on a one-piece CIR, and "Coaster Pack" drafts as one flat panel (OPUS2U-1, MED). The Q-6 product test covers root × suffix only, not inflections, and 7 mutants survive (OPUS2U-6). Several Q-7 items are still open (OPUS2U-5). |
| 1m | Merge 493b76cf | **Faithful** | `diff <(git diff 04277d26..493b76cf) <(git diff fed859b7..8ed2dd15)` prints nothing. `launch0.py`, `fallback_constructions.py` and `test_opus2_draft_constructions.py` are identical between 8ed2dd15 and 493b76cf. The catalogue probe output is byte-identical between the two heads. |
| 1t | OPUS2T-1 / -2 / -3 | **All three OPEN** | 8ed2dd15 does not touch `fallback_constructions.py`. The `plan()` that fed859b7 introduced is unchanged on 8ed2dd15 and 493b76cf. Every repro still drafts with `name_truth=[]` (OPUS2U-2). |
| 2 | Colourwork claim reader (e6e6fb94) | **DO NOT SHIP** | **OPUS2Q-2 is closed for the forms named.** "C2CBlanket", "C2Cs", "C2Cgraph", "C2Cing", "CrochetC2C", "crochetc2c", "learnc2c", "Basket5Colour", "Blanket2Tone", "crochet2colour" and "crochetcornertocorner" are all claims again, as title and as tag. Letters are now split from digits. **What it breaks:** the fix introduces **two new regressions** (OPUS2U-3, MED). (a) The digit C2C form moved out of the variant table into `c2c\|\bc 2 c` on the unsplit text. As a result "C2 C", "C 2C", "C2-C" and "C-2C" were claims on 2f9c413d and are now backed with 0 findings. (b) The thin-space join deletes U+2009/U+200A/U+202F/U+205F/U+3000 between *words* as well as inside them. So "Pixel Crochet" and "Duplicate Stitch" become "pixelcrochet" and "duplicatestitch", which no longer match variants that need a literal space. Both were claims on 2f9c413d and are now backed. **OPUS2Q-3 is only partly closed:** look-alikes are still a list, not a skeleton table or a mixed-script refusal, and many still bypass (OPUS2U-4). |
| 3 | Stocking (7493c723) | **SHIP** | **Q-4 closed.** The guard now takes the CIE76 ΔE of the first two palette hexes and requires ≥ 10. A hex written twice in different cases (ΔE 0), two names for one hex, #EFE6D2/#EFE6D3 (0.51), #000/#1A1A1A (9.26) and #FFF/#E6E6E6 (8.71) are refused. #244A3A/#B23A3A (71.5) builds. The Lab conversion (sRGB linearisation, D65 matrix, Xn/Zn, the f() knee) is correct. A malformed hex ("#FFF", " #244A3A", "red") raises `ValueError`, which fails closed. **Q-5 closed:** "Stripe(d) Cuff" is removed from both the plan fold and the guard, and "Striped/Stripe Cuff … Stocking" is refused. NBSP, fullwidth and upper-case "Contrast Cuff" are folded the same way in `plan` and in the guard. Residuals are LOW test gaps only (OPUS2U-7). |

**Catalogue (all subjects).** `cat.py` enumerates BUILDERS (11), PROPOSED_BUILDERS (3), `launch0()` (8 rows) and `excluded_from_launch0()` (18 rows), 40 entries in all. For each it records `title_promise` and the full `product_truth` / exclusion row.
- Output is byte-identical for fed859b7 = 8ed2dd15 = 493b76cf, for 2f9c413d = e6e6fb94, and for d3a485a1 = 7493c723.
- On every head all 14 builder CIRs are backed and `launch0_is_all_gate_clean()` is True.
- **No CIR is newly unbacked or newly refused.**

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2U-1 | **MED** | 1 | **A new refused→backed regression: a singular object + "Pack", and "Multiple(s)", now back a one-piece CIR.** OPUS2Q-1(c) removed the bare `packs?` marker. In its place came an allowlist of pack phrases (variety, value, bulk, party, gift, starter, combo, sampler, bundle, or a count root + pack), plus `multi-` only before 11 listed nouns. Two consequences follow. **(a) Packs:** "Coaster Pack", "Ornament Pack", "Scrunchie Pack", "Dishcloth Pack", "Tote Pack" and "Poly Pack" are now `claimed=None` with no markers. `title_promise` backs them on a one-piece tote and on the Cloudline blanket, and `handle_cir_draft` drafts home_decor "Coaster Pack" as one `panel` with `name_truth=[]`. All were unbacked on fed859b7. **(b) Multi:** "Multiple"/"Multiples" ("Tote Multiple", "Coaster Multiples"), "Multi Bowl" and "Multi-Pouch" lost the marker they had through the prefix rule. They are backed now. "Multiple Totes" is still caught, but only by the plural `totes`. The direction is wrong for a publish and first-customer gate: an unknown "X Pack" is UNKNOWN and should not pass. *Fix:* invert the pack rule. Keep a closed allowlist of single-object pack compounds (fanny, hip, sling, back, day, waist, ice, heat, hydration, rain pack). Treat any other "<noun> pack" as a plural marker. Add `multiples?` to `_PLURAL_WORDS`. Read `multi[- ]?<any noun>` as plural unless the noun is a colour, use, purpose, season or similar quality word. Pin "Coaster Pack", "Ornament Pack" and "Tote Multiples" as unbacked. | `tp.py < titles.txt` on fed859b7 vs 8ed2dd15; `draft.py "home_decor\|Coaster Pack"` on 493b76cf |
| OPUS2U-2 | **HIGH** (carried, open) | 1t | **OPUS2T-1, -2 and -3 are all still open.** 8ed2dd15 does not touch `creative/fallback_constructions.py`, and 493b76cf carries the same file. Drafted on 493b76cf through `handle_cir_draft`: **T-1:** pillow "Teddy Bear" gives front + back, and shawl "Teddy Bear" gives a triangle shawl; `plan` returns panel_pair under wedding too. **T-2:** basket "Teddy Bear Pattern" gives a basket, and blanket "Teddy Bear (Cream)" gives a panel. `plan` also drafts "Crochet Teddy Bear Pattern", "Teddy Bear for Beginners" and "Bear Cub" as a flat panel or a basket, and "Drawstring Pouch Pattern" as a basket. **T-3:** basket "Sleepy Fox" and basket "Blanket" each give a basket, and `plan` also drafts "Cat" and "Teddies". All have `name_truth=[]`. | `plan.py t2.txt`; `draft.py "pillow\|Teddy Bear" "shawl\|Teddy Bear" "basket\|Teddy Bear Pattern" "blanket\|Teddy Bear (Cream)" "basket\|Sleepy Fox" "basket\|Blanket"` |
| OPUS2U-3 | **MED** | 2 | **Two new claim regressions in the colourwork reader. Both were claims on 2f9c413d and are now backed with 0 findings, as title and as tag, on plain fabric.** **(a) Spaced or hyphenated digit C2C:** "C2 C", "C 2C", "C2-C" and "C-2C". The old variant `c ?(?:2\|to) ?c\b` was replaced by `c ?to ?c\b` plus `c2c\|\bc 2 c` on the *unsplit* text, so a single space or hyphen on one side defeats it. **(b) Thin space between two words:** the new pre-fold `re.sub` deletes U+2009/U+200A/U+202F/U+205F/U+3000 whenever letters stand on both sides. That joins separate words: "Pixel Crochet" becomes "pixelcrochet", which misses `pixel crochet`, and "Duplicate Stitch" misses `duplicate stitch`. U+202F (narrow NBSP) and U+3000 (IME ideographic space) do appear between words in pasted text. Mutant U2r (restoring the old C2C variant) **survives**, so nothing pins (a). *Fix:* match the digit form on `split` as `c ?2 ?c` (with `\b` only before the leading c, or glued anywhere). Instead of deleting thin spaces, map every Zs character to U+0020 and match each claim both with spaces and with spaces removed. Pin "C2 C", "C-2C", "Pixel Crochet" and "Duplicate Stitch". | `cw.py < cw.txt`, `cw.py < cw2.txt` on 2f9c413d vs e6e6fb94 |
| OPUS2U-4 | LOW | 2 | **OPUS2Q-3 is only partly closed. The confusables are still a list, and the thin-space join is order-dependent.** These still hide a claim on plain fabric (title and tag, 0 findings): small capitals not added, "Graᴘhghan" (U+1D18), "ɢraphghan" (U+0262), "Grapʜhghan" (U+029C), "ꜰair Isle" (U+A730), "Jacquarᴅ" (U+1D05), "ᴊacquard" (U+1D0A), "Colourᴡork" (U+1D21); Greek capitals that `.lower()` turns into non-Latin letters before the map, "ΜOSAIC" (U+039C), "IΝTARSIA" (U+039D, which also maps ν→v), "TAPΕSTRY" (U+0395), "GRAPΗGHAN" (U+0397); non-ASCII digits "C٢C" (U+0662), "C२C", "Basket٥Colour"; and the glued "CrochetCtoC", "crochetctoc", "CtoCs". **Thin spaces:** "Mo  saic" (two in a row), "Mo​ saic" (a Cf before the thin space; the lookbehind runs before Cf is dropped), "Mö saic" (a mark before it), and U+2004–U+2008 and U+00A0 inside a word. Of the 13 new look-alike entries, 6 are unpinned (U2j–U2o survive). *Fix:* fold through the UTS #39 skeleton (confusables.txt), map digits by `unicodedata.digit`, and drop the Zs/Cf/Mn handling inside the fold after NFKD. Or refuse any non-ASCII letter that survives the fold within a claim-length window. | `cw.py < cw.txt`, `cw2.txt` |
| OPUS2U-5 | LOW | 1 | **Some Q-7 items remain open, and the docstring overstates the Roman range.** **Closed:** Elevensome, Twelvepack, Dozensome, Thousands, Millions, Billion, XIII/XX/XXIV, Duology, Tetralogy, Pentalogy, Hexalogy, Octalogy, Diptych(s), Triptych, Twinset(s), Tercet(s). **Still drafted as one tote and backed:** Quadrilogy, Septology, Quins, Quints, Trine, Triune, Grandmother, Mom, Mum, Mama, Grandson. **Also backed:** Nonuplets and Decuplets (no nonu/decu roots); Trifectas (`fecta` has no -s); number words above twelve with -some/-pack (Thirteensome, Twentysome, Hundredpack, Thousandsome); "twentyfour"; Thirty; Several; Many. **Roman range:** `_roman` says "II..XXXIX", but `x{0,2}` stops at XXIX, so "Tote XXXIX" is backed. | `tp.py < titles.txt` |
| OPUS2U-6 | LOW (test gaps) | 1, 2 | **Surviving mutants. Q-6's "root × suffix × inflection" test is root × suffix only.** **Subject 1:** U1c ("ter" dropped from `_SHORT_ROOTS`), U1m (`logies` dropped), U1n (`ptychs?` → `ptych`), U1o (`cets?` → `cet`), U1v ("coaster" dropped from the multi- nouns), U1x (`poly(?:ptych\|ad)` → `polyptych`) and U1ab (bare `s` added as a count suffix, the false-positive direction: "Tens", "Tris", "Quads" become counts). U1y (quintuple dropped from `_TAKES_ED`) is equivalent, because `quintu`+`pled` reads it. **Subject 2:** U2j–U2o (ᴇ ᴛ ʀ ᴜ ɴ ᴍ removed), U2r (see OPUS2U-3) and U2f (digit→letter split removed). U2f is equivalent for the current variants. | mutations table |
| OPUS2U-7 | LOW (test gaps) | 3 | **The threshold and "contrasting" in the guard are unpinned.** Mutants U3a (ΔE threshold 10 → 1) and U3c (10 → 70) survive, because the only pins are ΔE 0, 0.51 and 71.5. U3h ("contrasting" dropped from the guard) survives, and "Contrasting Cuff Holiday Stocking" is admitted by `plan`. U3f (sRGB linearisation removed) survives. *Fix:* pin a pair just below and just above 10 (#000000/#1A1A1A = 9.26; #0000FF/#0000E0 = 13.27). Also pin a one-colour "Contrasting Cuff" stocking. | mutations table |
| OPUS2U-8 | INFO | 1, 3 | **New fail-closed readings, and intended loosenings.** **Subject 1:** the wider Roman reading makes "XX Blanket" (20) and "Xiv" (14) counts, and "Hex Pack" and "Dec Pack" are markers. The removed test entries are "Tote Pack" and "Poly Tote", from the `marked` pins. They are now one-piece pins on purpose (OPUS2Q-1); this is the only weakened assertion. "Tote Sons" is now backed, since "son" was dropped; "Mother/Father Son" is still caught through mother/father. "Duplicate Stitch Blanket" is read as claimed=2 (pre-existing; it is also refused as intarsia by the colourwork reader). **Subject 3:** an 8-digit hex (#RRGGBBAA) is accepted with the alpha ignored. CIE76 overstates blue differences (#0000FF/#0000E0 = 13.3 passes). Both are acceptable. | `tp.py`, `stk.py` |

**Removed or weakened assertions:**
- fed859b7..8ed2dd15: "Tote Pack" and "Poly Tote" were moved out of the plural pins. This is intended by OPUS2Q-1, but see OPUS2U-1 for the pack class.
- 2f9c413d..e6e6fb94: none.
- d3a485a1..7493c723: "Stripe Cuff Holiday Stocking" moved from admitted to refused, which is stricter.

## Mutations (each applied once, then restored; worktrees clean afterwards)

| ID | Subject | Mutation | Result |
|---|---|---|---|
| U1a | 1 | `_SHORT_ROOTS` exclusion disabled | killed |
| U1b / U1c / U1d | 1 | "ten" / "ter" / "bi" removed from `_SHORT_ROOTS` | killed / **survives** / killed |
| U1e | 1 | `_TAKES_ED` restriction removed (any -d/-ed) | killed |
| U1f | 1 | "son" re-added | killed |
| U1g / U1h | 1 | bare multi/poly prefix / bare `packs?` re-added | killed / killed |
| U1i / U1j / U1k | 1 | `\bpacks\b` / variety-pack phrase / root-pack phrase removed | killed / killed / killed |
| U1l / U1m / U1n / U1o | 1 | `logy\|logies` / `logies` / `ptychs?`→`ptych` / `cets?`→`cet` | killed / **survives** / **survives** / **survives** |
| U1p / U1q / U1r | 1 | old Roman list / `len<2` guard removed / subtractive rule removed | killed / killed / killed |
| U1s / U1t | 1 | large numbers exact (no inflection) / "billion" removed | killed / killed |
| U1u / U1v / U1w / U1x | 1 | multi- nouns: "tote" / "coaster" / "set" removed; `polyad` removed | killed / **survives** / killed / **survives** |
| U1y | 1 | "quintuple" removed from `_TAKES_ED` | survives (equivalent: quintu+pled) |
| U1z / U1aa | 1 | `_SHORT_EXCLUDED` → `ts?` / `e?t` | killed / killed |
| U1ab | 1 | bare `s` added to `_COUNT_SUFFIX` (false-positive mutant) | **survives** |
| U2a / U2b / U2c | 2 | `c2c` / `\bc 2 c` / glued corner removed from the new regex | killed / killed / killed |
| U2d | 2 | variants matched on `folded`, not `split` | killed |
| U2e / U2f | 2 | letter→digit split removed / digit→letter split removed | killed / survives (equivalent for current variants) |
| U2g | 2 | Cn no longer dropped | killed |
| U2h / U2i | 2 | thin-space join removed / U+3000 removed from it | killed / killed |
| U2j–U2o | 2 | look-alike ᴇ / ᴛ / ʀ / ᴜ / ɴ / ᴍ removed | **all survive** |
| U2p / U2s | 2 | look-alike һ / ᴏ removed | killed / killed |
| U2q | 2 | `c ?to ?c\b` removed | killed |
| U2r | 2 | old `c ?(?:2\|to) ?c\b` variant restored (fixes OPUS2U-3a) | **survives** (no pin) |
| U3a / U3b / U3c | 3 | ΔE threshold 1.0 / 0.4 / 70 | **survives** / killed / **survives** |
| U3d / U3e | 3 | guard → exact hex set / case-folded hex set | killed / killed |
| U3f | 3 | sRGB linearisation removed | **survives** |
| U3g | 3 | stripe/striped re-admitted in `plan` | killed |
| U3h / U3i | 3 | "contrasting" dropped from guard / guard disabled | **survives** / killed |

## Suites (one at a time, from `brambleloop/`; all rc 0, 0 FAIL)

| Head | Suites (ok) |
|---|---|
| 8ed2dd15 | test_opus2_draft_constructions (24), test_launch0 (52), test_first_customer_gate (12 passing), test_compiler (9), test_twin (8), test_reverse (18), test_vacuity (8) |
| 493b76cf | test_opus2_draft_constructions (24), test_launch0 (52), test_first_customer_gate (12 passing) |
| e6e6fb94 | test_opus2_cir_colourwork (21), test_launch0 (52), test_first_customer_gate (12 passing), test_pattern_truth (11), test_search_truth (32 passing), test_w4_seo_packages (6) |
| 7493c723 | test_opus2_stocking (9), test_opus2_pet_bed (7), test_opus2_draft_constructions (18), test_fallback_draft_provenance (1) |

## Commands

```
git -C /home/user/Project-Money fetch origin
git worktree add --detach $S/opus2u-<sha> <sha>     # fed859b7 8ed2dd15 493b76cf 2f9c413d e6e6fb94 d3a485a1 7493c723
git diff fed859b7..8ed2dd15; git diff 2f9c413d..e6e6fb94; git diff d3a485a1..7493c723
diff <(git diff 04277d26..493b76cf) <(git diff fed859b7..8ed2dd15)          # identical
git diff --stat 8ed2dd15 493b76cf -- launch0.py fallback_constructions.py test_opus2_draft_constructions.py   # empty
git diff <range> -- brambleloop/tests | grep -E '^-[^-]'
python opus2u-probes/cat.py                     # 40-entry catalogue, per head, diffed
python opus2u-probes/tp.py < titles.txt         # multiplicity + plan(bag) + title_promise (tote, blanket), 170 titles
python opus2t-probes/plan.py t2.txt; python opus2t-probes/draft.py "<cat>|<title>" ...   # OPUS2T repros
python opus2u-probes/cw.py < cw.txt / cw2.txt   # colourwork claims, title and tag, 2f9c413d vs e6e6fb94
python opus2u-probes/stk.py                     # stocking plan + contrast guard over 16 palettes
bash opus2u-probes/m1.sh m2.sh m2b.sh m3.sh     # mutation runner (mut.py: apply once, run suite, restore)
PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py
```

Python: /home/user/bl-runs/venv-integ4/bin/python. The probe scripts are in the scratchpad under `opus2u-probes/` and were not committed.
