# Independent security / truth review OPUS2T: a delta review of Secondary's (opus2) fixes for OPUS2P-13a, OPUS2P-1..9 and the registry toy hold

- Reviewer: an independent, adversarial, read-only Claude Code session.
- Date: 2026-11-02 (UTC).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
  The only network use was `git fetch origin`.
- All work ran in scratch worktrees (`opus2t-{rw,rwbase,am,base,reg}`) in the session scratchpad.
  After each mutation the change was reverted with `git checkout -- .`. `git status --porcelain`
  shows 0 lines in every worktree. Suites ran one at a time.

| # | Subject | Branch | Head | Delta reviewed |
|---|---|---|---|---|
| 1 | P0-NAME-OBJECT-MISMATCH (OPUS2P-13a) | origin/opus2/p0-revenue-workforce | fed859b7 | b185b528..fed859b7 |
| 2 | Amigurumi and pouch fixes for OPUS2P-1..9 | origin/opus2/p0-amigurumi | c5671087 | c0ecc55e..c5671087 |
| 3 | Registry toy hold | origin/opus2/p0-construction-registry | 66378ebf | `git show 66378ebf` (c5671087..66378ebf) |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Name-object mismatch (fed859b7) | **DO NOT SHIP as the P0 closure.** The change itself is safe to merge as a partial fix. | The three named cases are now refused under basket, blanket and accessory: "Teddy Bear", "Drawstring Pouch" and "Drawstring Bag". So are all toy and bag titles whose **last** word is in the new list. No radar seed or catalogue title changes route. The false positives are handled correctly: "Bear Paw Blanket", "Basket Weave Blanket", "Polar Bear Blanket", "Toy Basket" and "Bear Basket" still draft. But the requirement is not met in three ways. **(a)** Under `pillow` and `wedding`, "Teddy Bear" still drafts as a two-panel cushion, and under `shawl` it drafts as a triangle shawl. In each case `name_truth == []` (OPUS2T-1). **(b)** The head noun is taken to be the last word, so "Teddy Bear Pattern", "Crochet Teddy Bear Pattern", "Teddy Bear (Cream)" and "Bear Cub" draft as a basket or a flat panel, again with `name_truth == []` (OPUS2T-2). **(c)** The guard is a denylist, so an unknown head passes. "Sleepy Fox", "Cat", "Blanket" and "Teddies" under basket all draft as baskets (OPUS2T-3). |
| 2 | Amigurumi and pouch (c5671087) | **DO NOT SHIP** | **OPUS2P-1 is fixed by adding words, not by the construction, and the words are matched without the route's Unicode fold.** The route NFKC-folds the title, so it drafts "Ｂear", "Ｔeddy Ｂear", "Cosy Ｒabbit" and "𝐁ear". `child_words_in` reads the raw title and finds no child word, so `build_pattern_pdf` **renders a stuffed toy with no children's safety block**. This was reproduced end to end through `handle_cir_draft` (OPUS2T-4, HIGH). Every ASCII title the route drafts is refused by the renderer, as the commit claims. The other fixes: **P-2 is fixed**. Both toy joins are now measured by stitch count ("sound"), a 30-st base gives ERROR `ASSEMBLY_MISMATCH`, and mutants A3, A4 and A5 are killed. **P-3 is only partly fixed.** The 6 cm floor is on the body only and refuses lace and fingering. At sport, which is allowed, the bear ear is about 33 × 20 mm and the base disc is 31.8 mm across, and nothing computes whether any piece passes the 31.7 mm cylinder (OPUS2T-5, MED). **P-4, P-5, P-6a/b, P-7, P-8 and P-9 are fixed and pinned.** P-6c is still open (LOW). Launch-0 and catalogue digests are unchanged, except the two stuffed candidates that lose the "before blocking" line. No catalogue title becomes refused. |
| 3 | Registry toy hold (66378ebf) | **DO NOT SHIP** | **The hold reads the wrong strings, so it does not hold real toy briefs.** It checks `child_words_in(req.title, req.key)`. Real prospecting keys are `{prefix}{pod}-{form}-{i}` (`prospecting.py:931`), and the form of every amigurumi route is `toy` or `sphere`. A `…-toy-N` key therefore always contains "toy" and the hold never fires. `_draft_creative` then rewrites the CIR to `slug=design_slug(concept)` and `title=concept.title`, and neither contains "toy". The result is a bear drafted as "Juniper Friend" or "Woodland Keepsake", or with an empty title (slug `design-…`), and the PDF **renders it with no children's block** (OPUS2T-6, HIGH). The pinned case uses key `brief-juniper-friend`, which is not the production format, and mutant R2 (key only) survives. The hold is the right idea for the registry side, but it has to read the CIR's final slug and title, or the renderer has to key on the construction. **OPUS2R-1 HIGH is not addressed.** "Fox Plush" (motif bear) drafts a bear and "Giant Bear with Removable Hat" drafts a plain toy, both with `name_truth == []` (OPUS2T-7). |

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2T-1 | **HIGH** (Product Truth) | 1 | **The object check runs after the panel-pair and triangle branches, so "Teddy Bear" still drafts under the `pillow`, `wedding` and `shawl` categories.** `plan()` returns `PANEL_PAIR` for `category in PANEL_PAIR_CATEGORIES` and `TRIANGLE` for `category in TRIANGLE_CATEGORIES` before `_names_another_object` is reached. Drafted through `handle_cir_draft`: pillow "Teddy Bear" gives a front and back cushion; wedding "Teddy Bear" gives a front and back cushion; shawl "Teddy Bear" gives a triangle shawl. All three have `name_truth=[]`. Under `shawl`, every title in the 107-title probe drafts a triangle, including "Bunny", "Cat Bed", "Christmas Stocking" and "Drawstring Pouch". All three categories exist in the radar POOL. *Fix:* run the head-noun check before every family branch (after the bundle and size checks), or make it an allowlist of heads per family. | `plan.py titles.txt`; `draft.py "pillow\|Teddy Bear" "wedding\|Teddy Bear" "shawl\|Teddy Bear"` |
| OPUS2T-2 | **HIGH** (Product Truth) | 1 | **"Head noun = last word" is bypassed by any trailing word that is not an object.** The following draft as a basket under `basket` and as a flat panel under blanket, home_decor, accessory, pet, seasonal, scarf and runner: "Teddy Bear Pattern", "Teddy Bear Crochet Pattern", "Crochet Teddy Bear Pattern", "Teddy Bear (Cream)", "Teddy Bear for Beginners", "Teddy Bear in Cream", "Teddy Bear - Easy", "Teddy Bear v2", "Bear Cub". All have `name_truth=[]`. "Drawstring Pouch Pattern" also drafts as a basket under `basket`. `assembly_promise` only flags it later, because "pouch" happens to be an assembled form. "… Pattern" is ordinary marketplace title phrasing. *Fix:* strip a closed set of trailing non-object words (pattern, crochet, cream/colour words, for/in phrases, version tags) before taking the head, or refuse any title whose trailing word is not an allowlisted object head for the family. | `plan.py`, `draft.py "basket\|Teddy Bear Pattern" "blanket\|Teddy Bear Pattern"` |
| OPUS2T-3 | MED | 1 | **The object-head table is a denylist, so an unknown head is drafted.** Under `basket`, these are drafted as a basket: other toy animals ("Sleepy Fox", "Little Elephant", "Cat", "Owl", "Unicorn", "Puppy", "Kitten", "Dinosaur", "Octopus"), "Teddies" (plural not listed), "Bear Lovey", "Blanket", "Throw", "Scarf", "Cowl", "Rug", "Coaster", "Slippers", "Poncho", "Shrug", "Pencil Case", "Phone Case", "Wallet", "Cat Cave", "Dog Collar", "Bunting", "Wall Hanging", "Egg/Mug/Tea Cosy", "Cushion", "Pillow", "Stocking Pattern" and "Pouch-Style Pillow". `name_truth` catches only the assembled forms (cushion, cosy, pouch, wall hanging). "Sleepy Fox", "Blanket" and "Cat" pass with `name_truth=[]`. Under the flat route, "Cat", "Sleepy Fox", "Cowl", "Slippers" and similar titles draft as a flat panel. A basket's heads form a small closed set (basket, bin, bowl, caddy, hamper, planter, organiser and the like), so an allowlist would be total, which matches the OPUS2N-1 principle that UNKNOWN never passes. Two mutants survive. **N6** (no NFKC fold) survives because no fold case is pinned. **N7** (stocking heads dropped) survives because `_shaped_title` catches "Cosy Stocking" on the flat route, and no basket stocking case is pinned. | `plan.py`, `draft.py "basket\|Sleepy Fox" "basket\|Blanket"`; mutants N6, N7 |
| OPUS2T-4 | **HIGH** (child safety, blocking) | 2 | **A toy titled in full-width or mathematical letters is drafted, and its PDF renders with no children's block.** `amigurumi_route` reads `fold_title(title)`, which is NFKC, so "Ｂear" becomes "bear". `launch0.child_words_in` runs `re.findall(r"[a-z]+", text.lower())` on the raw title, so "Ｂear" becomes "ear" and no child word is found. Results with a neutral slug: "Ｂear", "Ｔeddy Ｂear", "Cosy Ｒabbit", "𝐁ear", "Ｂunny" and "Ball Ｂear" each draft a stuffed toy, and `pdf.build_pattern_pdf` renders it with no "Safety notes for a children's item". The same happens end to end through `handle_cir_draft` with the real amigurumi seed slug (`pocket-penguin-trio`): `PDF RENDERED`. Marketplace titles do use Unicode bold or full-width letters. The deeper cause is that OPUS2P-1 asked for the **construction** to trigger the gate, and the fix only adds title words (option b). Any path that builds an amigurumi CIR under a title or slug without these words is still invisible to the gate. OPUS2T-6 is one such path. *Fix:* (1) in `pdf._refuse_an_undecided_childrens_title`, also refuse when the CIR is a closed stuffed form (`gates.risk_matrix` `closed_3d_form`, any seam with `stuff_before_closing`, or a component built by `fallback_constructions.amigurumi`), whatever the title says; (2) NFKC-fold and dash-fold the text inside `child_words_in`, using the same `fold_title` the route uses. Pin "Ｂear" with a neutral slug, and pin a toy titled "Juniper Friend" built with `kind=`, as refused by the renderer. | `ami.py`; `draft_pdf.py "amigurumi\|Ｂear" "amigurumi\|Cosy Ｒabbit"` |
| OPUS2T-5 | MED | 2 | **The P-3 floor bounds the body, not the pieces, and the comment says so ("a stated design floor, not a safety standard").** The floor is a body diameter of at least 6 cm, which admits sport and heavier. At sport (18 sts/10 cm): bear ear about 33 × 20 mm flat, bunny ear about 22 × 50 mm, base disc 31.8 mm across. At DK: bear ear about 41 × 25 mm. Whether a separated ear or base enters the 31.7 mm cylinder (16 CFR 1501; SOR/2011-17 s.7) is not computed anywhere. By rough geometry, a flat 33 × 20 mm ear fits the cylinder's deep side, so this is UNKNOWN that leans toward failing. It is mitigated because the renderer refuses an undecided toy (for ASCII titles), and an assigned children's product goes through `intel.childrens.assess` (`small_parts_under_3` REFUSE). The requirement, though, was that no piece is under the cylinder or such weights are refused. Mutant **A8** (floor lowered to 4 cm, which admits fingering) survives, because only lace is pinned. *Fix:* compute each piece's smallest enclosing dimensions from its round counts and gauge, and refuse any weight at which any piece is under 31.7 mm (or under the cylinder envelope). Or restrict the route to worsted and heavier and pin the fingering, sport and DK refusals. | `ami.py` (weights table); mutant A8 |
| OPUS2T-6 | **HIGH** (child safety, blocking) | 3 | **The registry hold is defeated by the production key format and by the slug and title rewrite that follows it.** `_amigurumi` checks `child_words_in(req.title, req.key)`. In production, `req.key` is the tournament key `{prefix}{pod}-toy-{i}`, which always contains "toy". `_draft_creative` then writes `slug=design_slug(concept)` (slugified title plus digest) and `title=concept.title` onto the CIR, and that is what the PDF reads. Repro through `pipeline._draft_creative`, motif bear: key `t3-home_decor-toy-0`, title "Juniper Friend": DRAFTED, slug `juniper-friend-80c61c2e`, `child_words_in=()`, **PDF RENDERED, no children's block**. The same happens for "Woodland Keepsake", for "Ｂear Keepsake" (slug `ear-keepsake-…`), and for an empty title (CIR title "", slug `design-96cff5a5`; `req.title` fell back to the key). Keys of the form `…-sphere-N` are held correctly. The pinned case `brief-juniper-friend` has no form word in its key, so it does not represent production, and mutant R2 (hold reads the key only) survives. *Fix:* key the renderer on the construction (OPUS2T-4 fix 1), which makes this moot. Otherwise run the hold on the strings the CIR will carry (`concept.title` and `design_slug`), never on the tournament key. | `reg.py` |
| OPUS2T-7 | **HIGH** (carried, not addressed) | 3 | **OPUS2R-1 is still open.** The registry still calls `FC.amigurumi(…, kind=…)` and the other builders without running the family's title route. Reproduced on 66378ebf with motif bear: "Fox Plush" drafts a bear (`name_truth=[]`; the PDF refuses only because "plush" is now a child word). "Giant Bear with Removable Hat" drafts a plain ball-body bear (`name_truth=[]`). The new hold covers only the case of no child word. | `reg.py` |
| OPUS2T-8 | LOW | 2 | **Only part of P-2 generalises.** A round piece that `_counted_round` skips, but whose join `_count_join` cannot count (no `at_round` and no `stitches_from_centre`), falls to "one of the pieces has no measured footprint". That gives an unchecked join, then `partially_placed`, then **WARNING** `ASSEMBLY_PARTIAL`. Before the change it was WARNING `ASSEMBLY_UNMEASURABLE`. Both joins of today's toy are measured, so the shipped product is fine. A future toy variant would still be graded WARNING, not refused. The ear join also never checks that `at_round` exists on the body, or that `2 × stitches_from_centre` is at most that round's count (the builder raises on its own constants, but the gate does not see it). Mutant **A6** (count from the body's last round instead of `at_round`) survives. It is equivalent here, because the base is sewn to the last round. | mutants A6 |
| OPUS2T-9 | LOW | 2 | **P-6(c) is still open.** The pouch still prints "This pattern uses 2 colours, so there is an end to secure at every join and every change". The cord is a separate piece, and the pouch has no colour change. | `pouch.py` |
| OPUS2T-10 | INFO | 1, 2 | **Checked and true, and the merge notes.** (a) The new child words (toy, toys, plush, plushie, stuffie, softie, teddy, bear, bunny, rabbit) put **no** existing CIR into the undecided-children state. Checked across 28 distinct buildable CIRs (Launch-0 and proposed candidate variants, `builder.CATALOGUE`, Nordic Forest sizes, market baskets, the hexagon coaster, pipeline and moment-candidate engineered CIRs) and 34 radar seeds: the only hits are the two already-assigned "Baby" blankets, the same as on c0ecc55e. `test_launch0`, `test_childrens` and `test_w4_children` pass. (b) Once branches 1 and 2 are merged, titles such as "Polar Bear Blanket", "Bear Paw Blanket", "Toy Basket" and "Plush Throw" become render-refused until someone records a children's decision. That is conservative and acceptable. (c) "Pouch-Style Pillow" is refused under every non-basket category (pre-existing `_shaped_title` "pouch"). That refusal is conservative and acceptable. Under `basket` it drafts a basket (OPUS2T-3). (d) Catalogue assembly verdicts are identical on c0ecc55e and c5671087. Pattern text digests are identical except `heart-row-ring-pillow` and `spring-garden-kneeler`, which lose the stuffed-piece "before blocking" line (P-8). (e) The pouch now has an even eyelet count at every allowed weight (24/16/12/10/8/8/6, lace to bulky), refuses super bulky and jumbo, compiles with 0 errors, assembles, and has 0 reverse-read ERRORs. (f) Branches 1 and 2 both edit `plan()` and the area around `fallback_constructions.py`, so the merge will need the head-noun check placed after the amigurumi, pouch and tapestry routes and before every family branch. | `cat2.py`, `asmcat.py`, `pouch.py` |

## Mutations

Each mutant was applied in a scratch worktree, the named suite was run, and the change was reverted with `git checkout -- .`.

| ID | Subject | Mutant | Result |
|---|---|---|---|
| N1 | 1 | `_names_another_object` always None | killed (test_opus2_draft_constructions) |
| N2 | 1 | the basket-branch call removed | killed |
| N3 | 1 | the flat-branch call removed | killed |
| N4 | 1 | head = first word | killed |
| N5 | 1 | head = any word (presence, not position) | killed |
| N6 | 1 | no NFKC fold in the head check | **survives** (OPUS2T-3) |
| N7 | 1 | stocking heads dropped | **survives** (OPUS2T-3; the flat route catches it through `_shaped_title`) |
| A1 | 2 | all new `CHILD_AUDIENCE_WORDS` removed | killed (test_opus2_amigurumi) |
| A2 | 2 | only "rabbit" removed | killed |
| A3 | 2 | `_counted_round` always False (P-2 reverted) | killed (amigurumi); pouch suite unaffected |
| A4 | 2 | flattened ear not halved | killed |
| A5 | 2 | the count-join branch removed | killed |
| A6 | 2 | `at_round` count taken from the body's last round | **survives** (equivalent here; OPUS2T-8) |
| A7 | 2 | size floor 0 cm | killed |
| A8 | 2 | size floor 4 cm (admits fingering) | **survives** (OPUS2T-5) |
| A9 | 2 | repeated-word refusal removed | killed |
| A10 | 2 | repeated-word refusal only for two animals | killed |
| A11 | 2 | ear tail note removed | killed |
| A12 | 2 | "before blocking" line printed for stuffed pieces | killed |
| A13 | 2 | pouch step that allows an odd count restored | killed (test_opus2_drawstring_pouch) |
| A14 | 2 | `POUCH_MIN_EYELETS = 0` | killed |
| A15 | 2 | eyelet next-round note reverted | killed |
| A16 | 2 | thread note "same eyelet" restored | killed |
| A17 | 2 | the two pouch materials given one name | killed |
| A18 | 2 | tapestry per-round join note removed (P-9) | killed (test_opus2_tapestry_basket) |
| A19 | 2 | tapestry cut note one round early | killed |
| R1 | 3 | toy title hold removed | killed (test_opus2_research_to_development) |
| R2 | 3 | hold reads the key only | **survives** (OPUS2T-6: the pinned key has no form word) |
| R3 | 3 | hold also reads `req.form` (always "toy") | killed |

Not mutated, because no guard exists for them: a renderer gate keyed on the construction (OPUS2T-4),
a per-piece size check (OPUS2T-5), and a title route on registry builds (OPUS2T-7).

## Suites (each run alone, all exit 0)

| Head | Suites |
|---|---|
| fed859b7 | test_opus2_draft_constructions (0 failed); test_launch0 (OK) |
| c5671087 | test_opus2_amigurumi; test_opus2_drawstring_pouch; test_opus2_tapestry_basket; test_opus2_draft_constructions (0 failed each); test_launch0; test_childrens; test_vacuity (OK); test_w4_children (0 failed); **test_pdf_premium** (OK, run once, 2 min 5 s) |
| 66378ebf | test_opus2_research_to_development (0 failed); test_opus2_amigurumi (0 failed) |

**Removed or weakened assertions:** none. No `-` assertion lines appear in any test delta.
`test_opus2_research_to_development` changes `assert len(cases) == 3` to `== 4`, which adds a case.

## Commands

```
S=<scratchpad>; PY=/home/user/bl-runs/venv-integ4/bin/python
git -C /home/user/Project-Money fetch origin
git -C /home/user/Project-Money worktree add --detach $S/opus2t-{rw,rwbase,am,base,reg} {fed859b7,b185b528,c5671087,c0ecc55e,66378ebf}
git diff b185b528..fed859b7; git diff c0ecc55e..c5671087; git show 66378ebf
cd $S/opus2t-<wt>/brambleloop && PYTHONPATH=src:tests $PY tests/<suite>.py            # one at a time
$PY $S/opus2t-probes/plan.py $S/opus2t-probes/titles.txt   # 107 titles x 15 categories (rw, rwbase, am)
$PY $S/opus2t-probes/draft.py "<category>|<title>" ...      # handle_cir_draft end to end + name_truth (rw)
$PY $S/opus2t-probes/draft_pdf.py "amigurumi|Ｂear" ...     # end to end + build_pattern_pdf (am)
$PY $S/opus2t-probes/ami.py       # OPUS2T-4 renderer bypass; weights, joins, piece sizes (am)
$PY $S/opus2t-probes/reg.py       # OPUS2T-6/7 registry path with production key format (reg)
$PY $S/opus2t-probes/cat.py / cat2.py   # child-word survey over the catalogue and seeds
$PY $S/opus2t-probes/asmcat.py    # catalogue assembly verdicts and US+UK text digests (base vs am)
$PY $S/opus2t-probes/pouch.py     # pouch per weight; toy and pouch wording
python3 $S/opus2t-probes/mut.py $S/opus2t-<wt> $S/opus2t-probes/m{rw,am,reg}.json
```
