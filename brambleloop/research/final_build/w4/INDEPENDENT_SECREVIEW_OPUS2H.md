# Independent review OPUS2H: OPUS2EF2 fixes (subject 1) and the CIR colourwork proposal (subject 2)

Reviewer: an independent Claude Code session. Date: 2026-11-01 (UTC). This review is read-only.
Nothing on `opus2/*` or on any integrator branch was changed. Every probe and mutation ran in a
scratch worktree (`git worktree add`) and was reverted; `git status` was clean afterwards. No
publish, deploy, Railway or production action was taken, and nothing was spent.

| # | Subject | Commit | Base | Verdict |
|---|---|---|---|---|
| 1 | `opus2/p0-revenue-workforce`: fixes for OPUS2EF2 EF2-1, EF2-2, EF2-3 and EF2-3b | `13d67502` | `0e941757` (PR #3) | **ACCEPT** (LOW follow-ups H1-1 to H1-3) |
| 2 | `opus2/p0-cir-colourwork`: per-stitch colour (`Op.color`), a proposal | `5b0f8e0e` | merge-base `d230e8fd` with `origin/claude/w4-INTEG8-next` | **HOLD** (H2-1 HIGH; H2-2 and H2-3 MEDIUM) |

---

## Subject 1: `13d67502` against `0e941757`

### Per finding

| EF2 finding | Fixed at the root? | Evidence |
|---|---|---|
| EF2-1: strap parts back a count, and second objects or features are dropped | **Yes.** `launch0.finished_objects` merges components joined by `cir.assembly` (union-find) and counts each group once per its scarcest piece. `title_promise` now uses it for `makes` and reports the old piece sum as `pieces`. `plan()` refuses `_TOTE_NOT_PLAIN` (`& + and with pocket zip zipper lined lining reversible gusset flap button magnetic clasp`), and `_MULTIPLE_WORDS` now includes `bundle collection double family mother daughter twin matching`. | Every EF2-1 repro title is now `refused`, along with `Tote + Coaster` and `Market Tote & Purse` (table below). A drafted "Market Tote" renamed "Tote Bag Bundle", "…Collection", "…Set", "Tote Pair" or "2 Totes" gives `makes=1, pieces=3, backed=False`, and name_truth flags it. |
| EF2-2: the route narrowing is not pinned | **Yes.** "Lunch Bag", "Grocery Bag", "Project Bag" and "Bag" (category `bag`) are refused with `needs == NEEDS["bag"]`, so the test reaches the category refusal itself. | M1 and M2 (the mutations that survived in EF2) are now **killed**. |
| EF2-3: size and cosy words | **Yes.** `tiny` and `petite` map to small (60 sts, the same as "Small Tote"). `big` maps to large. `jumbo giant huge oversize(d) xl xxl extra large` are refused. Cosy: `& +`, `stripe(s)/striped`, `pom pom`, `tassel`, `colour block`, `two-tone`, `fair isle`, `mosaic`, `tapestry` and `basket` are refused. | "Egg Cosy & Basket", "Egg Cosy + Napkin", "Striped Egg Cosy", "Egg Cosy Pom Pom" and "Two-Tone Egg Cosy" are refused. "Egg Cosy", "Easter Egg Cosy", "Spring Egg Cosy", "Egg Cosies" and "Egg Cosy Set" still draft. |
| EF2-3b: material phrases treated as contents | **Partly** (H1-1). The contents exclusion `of (yarn|wool|cotton|…)` now keeps the claim when the next word is `rope cord cording t-shirt jersey twine macramé`. | "Two bowls of wool rope", "3 baskets of cotton cord" and "2 baskets of t-shirt yarn" are claims again (FAIL). **"2 baskets of cotton" and "Two baskets of wool" are still not claims (PASS)**, and neither is "3 baskets of cotton yarn". |

No Product Truth or size gate is relaxed. The size-gate change adds a negative lookahead inside an
existing negative lookahead, so the gate can only find more claims. `finished_objects` only lowers
`makes` relative to the old sum, so no title can become backed that was not backed before
(`finished_objects <= sum(make)`, because each group contributes the minimum of its members'
`make`).

**Catalogue regression check.** `title_promise` was computed for all 28 slugs in
`inventory.universe()` at `0e941757` and at `13d67502`. **No `backed` verdict changed, and no
product is unbacked on either commit.** `makes` dropped for six products, none of which has a
count claim in its title:

| Slug | makes before → after |
|---|---|
| bobble-floor-pillow | 2 → 1 |
| heart-row-ring-pillow | 3 → 2 |
| snowfall-advent-garland | 73 → 25 |
| spooky-garland | 6 → 1 |
| spring-garden-kneeler | 2 → 1 |
| valentine-heart-garland | 6 → 1 |

(`snowfall-advent-garland` stays at 25 and `heart-row-ring-pillow` at 2 because some of their
pieces are not named in `cir.assembly`. Unjoined pieces are counted as before, so this is not a
regression. See H1-4.)

### Repro titles: every EF2 title, re-run on `13d67502`

`PYTHONPATH=src:tests python /tmp/rv/ef2.py` (the script is reproduced in the appendix). The
family comes from `F.plan`; tote rows are drafted with `F.tote`.

| Title (category) | Result |
|---|---|
| Tote Bag Bundle, Tote Bag Collection, Double Tote, Tote Bag Family, Mother & Daughter Tote (bag) | refused: multiplicity word |
| Tote and Coaster, Market Tote with Pocket, Tote with Zipper, Lined Tote, Reversible Tote, Tote + Coaster, Market Tote & Purse (bag) | refused: `_TOTE_NOT_PLAIN` |
| Lunch Bag, Grocery Bag, Project Bag, Bag (bag) | refused: `NEEDS["bag"]` |
| Tiny Tote, Petite Market Tote, Small Tote | tote, small (60 sts) |
| Medium Tote | tote, medium (72) |
| Market Tote, Large Tote, Big Market Bag | tote, large (96) |
| Jumbo Tote, Extra Large Tote, XL Tote | refused: oversize |
| Egg Cosy & Basket, Egg Cosy + Napkin, Striped Egg Cosy, Egg Cosy Pom Pom, Two-Tone Egg Cosy (home_decor) | refused |
| Everyday Market Tote, Boho Tote, Farmers Market Tote, Beach Shopper, Tote Bag, Classic Tote Bag, Striped Market Tote, Mesh Market Bag | tote, `name_truth == []` (honest single objects; the drafted body really is two-colour) |

### Over-refusal probe

These honest single-object titles are refused. All of them fail closed (nothing is drafted
under a false name):

| Title | Why |
|---|---|
| "Mother's Day Tote" | `mother` is in `_MULTIPLE_WORDS` |
| "Black and White Tote" | `and` |
| "Tote Bag with Long Straps" | `with` |
| "Two Strap Tote" | the size-claims gate reads "Two Strap Tote" as several sizes |
| "Sunset Market Tote" | plan drafts it, then name_truth fails it: `PLURAL_MARKERS` is matched as a substring, and "sunset" contains "set". The straps no longer back the plural (H1-3). |

### Findings (subject 1)

**H1-1 LOW: EF2-3b is only partly closed.** The EF2 repro "2 baskets of cotton" still passes the
size gate. The material check fires only when a material noun follows the fibre word, so
"2 baskets of cotton", "Two baskets of wool" and "3 baskets of cotton yarn" are not claims,
while "2 baskets of jute" and "3 baskets of rope" are. This follows the second remedy EF2
offered, but it does not cover EF2's own example. The impact is narrow. *Fix:* treat
`of <fibre>` as contents only after a stash or container noun ("bags of yarn", "a basket full
of"). Otherwise keep the claim.
Repro: `Z.check_texts({"listing description": "2 baskets of cotton"})["state"] == "PASS"`.

**H1-2 LOW: conflicting size words are settled by table order, not refused.** "Tiny Large
Tote" and "Small Big Tote" draft small, and "Medium Large Tote" drafts medium. The code takes
the first `_TOTE_SIZE_WORDS` entry that matches. A title that names two different size keys
promises something no single draft is. *Fix:* collect every matching key and refuse when there
is more than one.

**H1-3 LOW (fails closed): `PLURAL_MARKERS` substring match.** "Sunset Market Tote" is drafted,
then fails name_truth with "the title says 'set'". Before this commit the straps backed it
(makes 3). Any product titled with "sunset", "closet", "corset" or "asset" is affected. *Fix:*
match with word boundaries (`\bset\b`). This is a one-line change and would also stop false
plural readings elsewhere.

**H1-4 INFO: the second-object refusal is enforced only in `plan()`.** A tote CIR renamed
"Tote and Coaster", "Double Tote" or "Mother & Daughter Tote" still gives
`title_promise.backed=True` and an empty `name_truth`, because `_COUNT_WORDS`/`PLURAL_MARKERS`
lack those words. Today every tote is titled through `plan()`, so this is defence in depth for
any later path that retitles after drafting (manual adoption, listing copy). Note also that
`finished_objects` counts pieces left out of `cir.assembly` as separate objects (snowfall
garland: 25). That preserves the old behaviour, but it means the root fix depends on builders
naming every join.

### Mutations (subject 1)

Each mutation was applied in a scratch worktree, then `test_opus2_draft_constructions` and
`test_opus2_size_claims` were run and the file was reverted with `git checkout`.

| # | Mutation | Result |
|---|---|---|
| M1 | put `bag` back in `_TOTE_WORDS` | **killed** (the EF2-1/2/3 test) |
| M2 | drop the bag-category refusal (`category != "bag"`) | **killed** |
| M3 | `title_promise` counts `sum(Component.make)` again | **killed** |
| M4 | `finished_objects` takes the max per group, not the min | **killed** (2 tests) |
| M5 | `_TOTE_NOT_PLAIN` never matches | **killed** |
| M6 | drop the new multiplicity words (bundle ... matching) | **killed** |
| M7 | drop `tiny`/`petite` | **killed** |
| M8 | drop `&`/`+` from `_COSY_NOT_PLAIN` | **killed** |
| M9 | drop stripes/pom pom from `_COSY_NOT_PLAIN` | **killed** |
| M10 | the oversize refusal never matches | **killed** |
| M11 | drop the EF2-3b material lookahead | **killed** (size_claims `test_review_opus2e_e2_the_gate_fails_closed_again`) |

11 of 11 were killed.

All mutations requested in the brief (`bag` back in `_TOTE_WORDS`; the bag-category refusal
dropped; `Component.make` counted again) are **killed**. EF2's survivors M1 and M10 are now
killed (here as M1 and M2).

### Tests (subject 1, `13d67502`)

| Suite | Result |
|---|---|
| test_opus2_draft_constructions | 18 OK, 0 failed (8 s) |
| test_opus2_size_claims | 13 OK, 0 failed (26 s) |
| test_fallback_draft_provenance | Ran 5 tests, OK |
| test_vacuity | 8 OK |

---

## Subject 2: `5b0f8e0e` (proposal) against `d230e8fd`

The proposal adds `Op.color` (None by default, omitted from `to_dict` when None); `ResolvedOp.color`; the
compiler errors `UNKNOWN_COLOR` (per op) and `STITCH_COLOUR_WITHOUT_ROW_COLOUR`; per-stitch cell
colour and per-yarn yardage in the twin; `write_op` appending "with <colour>"; reverse parsing of
"… with <colour>" with colour included in the structural compare; and `IN_ROW` events,
`tapestry_rows` and a "Colourwork rows …" sentence in the colour plan, which reaches the PDF
through `write_pattern` → `publish/pdf.py`. As a side effect, `launch0.per_stitch_colour_expressible()`
becomes True, because it detects the field.

### (a) Determinism: holds, with the gaps listed in (c)

- Compiler: each op colour is checked against `cir.colors`, and a stitch colour without a row
  main colour is an ERROR. Both are killed by mutation (C1, C2).
- Twin: cells take `op.color or row.color` and yardage is summed per yarn (C3, C4 and C8
  killed). The turning chain is charged to the row colour.
- Writer and reverse round-trip: `reverse.compare(cir, write_pattern(cir))` has no errors for
  the keys `rust`, `dusty-rose`, `colour_2` and `rust2`. Dropping " with rust" from the text, or
  swapping it to " with natural", is detected (C5 and C6 killed).
- `to_dict`/`from_dict`/`from_json` round-trip the colour, and a None colour is omitted (C7
  killed).

### (b) No Launch-0 release change: confirmed

The new test `test_no_existing_launch_design_changes_its_digest` computes `pinned` hashes but
**never compares them with anything** (H2-5). It only checks that a `color` key is absent. The
digests were therefore compared independently: for all 11 `launch0.BUILDERS` and all 26
buildable `inventory.universe()` slugs (37 CIRs), at `d230e8fd` and at `5b0f8e0e`, the
following were computed: the sha256 of `cir.to_json()`, `physical.design_digest`,
`pattern_refs.release_hash_of` (the certification content hash), the sha256 of
`writer.write_pattern`, `twin.yarn_metres_by_color`, and `fabric_truth.backed`.
**All 37 × 6 values are identical.** `test_physfix` (which pins digests) passes 46/46.

### (c) New failure modes: do they fail closed?

| Case | Result | Fails closed? |
|---|---|---|
| Op colour not in a non-empty colour table | `UNKNOWN_COLOR` ERROR | **Yes** |
| Op colour with no row main colour | `STITCH_COLOUR_WITHOUT_ROW_COLOUR` ERROR | **Yes** |
| Op colour with an **empty** colour table (`colors={}`, op colour "teal") | no finding; compiles; the twin invents a "teal" yarn. The writer's finishing colour plan is printed only when `len(cir.colors) > 1`, so no tapestry instruction is printed either | **No** (H2-4) |
| Colour on a non-stitch op: `[dc 3, ch 1 with rust, sk next st with rust] x 3` | compiles with no finding. Written as "sk next st with rust". Yarn: `rust: 0.0` m. 3 rust cells (from the chains) | **No** (H2-3) |
| Carried strand over a plain row, turned flat rows: rows 2 and 4 tapestry, row 3 plain | plan: `cut=0, carried=0, ends=4`, "Colourwork rows 2-4: … Do not cut at these changes." The contrast rests at the end of row 2, which is the opposite edge from where row 4 starts | **No** (H2-2) |
| Yarn carried inside a tapestry row (worked over) | not charged in yardage: only stitches worked in the colour count | **No** (part of H2-2) |
| Colour key with a space or capital ("Dusty Rose") | compiles, but the reverse compiler gives `REVERSE_PARSE` ERROR | Yes, but late (H2-6) |

### (d) PDF instructions come from the CIR

Yes, mechanically. `publish/pdf.py` renders `write_pattern` output, row text comes from
`write_op`, and the finishing sentence comes from `colour_changes.instruction(plan)`, derived
from the rows. Nothing is hand-written. **One exception:** `_tapestry_sentence` prints the
span `rows[0]-rows[-1]`, so tapestry rows `[2, 4]` print as "Colourwork rows 2-4". That claims
row 3, which is plain in the CIR, is colourwork (H2-2).

### Findings (subject 2)

**H2-1 HIGH: Product Truth is relaxed. One contrast stitch backs every colourwork technique
claim, including techniques the CIR still cannot express.**
`fabric_truth` sets `backed = (not claims) or max_colours_in_one_row >= 2`. Before this branch,
no CIR could put two colours in one row, so every claim of "mosaic", "overlay", "intarsia",
"fair isle", "graphghan", "tapestry" or "colourwork" failed closed by construction. The
`per_stitch_colour_expressible` docstring says that adding `Op.color` makes "the gates below
re-open without anybody editing a list". With this branch they re-open at a threshold of one
stitch.
Repro: rows 1-2 plain natural, then row 3 = `sc 11, sc 1 with rust` (one contrast stitch).
`fabric_truth` is `backed=True` for "Overlay Mosaic Basket", "Fair Isle Basket", "Intarsia
Basket", "Graphghan Basket" and "Tapestry Basket", even though
`cir_can_express_per_stitch_reach_down` is still **False**. Overlay mosaic is defined by
reach-down stitches, and per-stitch colour does not give it.
No Launch-0 product changes verdict today (all 37 are unchanged), because no builder emits
`Op.color` yet. But the purpose of the proposal is to unblock the radar fallback for colourwork
concepts ("Nordic Forest Mosaic Storage Basket"), and the first such draft would pass this gate
with any token stitch.
*Fix before acceptance:* make each claim technique-specific. Overlay and mosaic need reach-down,
which is not expressible, so they stay refused. Tapestry, fair isle and colourwork need a motif
of measurable extent: a minimum share of rows with two or more colours and a minimum contrast
run, both stated and pinned. Intarsia needs colour blocks without carried strands, so it stays
refused until a bobbin model exists. Add tests in which a one-stitch contrast is refused.

**H2-2 MEDIUM: the colour plan does not model the carried strand, so the PDF instruction and
the yardage are wrong when tapestry rows are not contiguous.**
`plan_component` sets `resting[colour] = end` for every in-row colour and never checks where
that colour rests when the next row that uses it begins. Plain rows in between are not
considered.
Repro (flat, turned):
1. row 1 plain;
2. row 2 = `sc 6, sc 6 with rust`;
3. row 3 plain;
4. row 4 = `sc 6 with rust, sc 6`.
After row 2, rust rests at edge 0. Row 3 runs edge 0 → 1, so row 4 starts at edge 1, the other
side of the piece from the rust. The plan reports `cut=0, carried=0, ends=4` and prints
"Colourwork rows 2-4: … Do not cut at these changes." The maker either carries rust across
plain row 3, which is unstated (and is visible through sc), or must cut, in which case the
ends count is wrong. The "2-4" range also invents a colourwork row 3. Separately, the
worked-over strand in a tapestry row travels the full row, but `_yardage` charges a colour only
for the stitches worked in it (rust 0.4 m in the repro). On a real tapestry piece this
understates the contrast yardage that the materials list prints.
*Fix:* track the edge where each in-row colour rests across every row, and treat a tapestry row
that starts away from a resting contrast as a cut (or as an explicit carry, with its own
sentence). List the tapestry rows exactly ("rows 2 and 4"). Charge carried yarn at
row width × a carry factor, and state that factor as an assumption.

**H2-3 MEDIUM: a colour on a non-stitch op is accepted.** `Op("sk", color=…)` and
`Op("ch", color=…)` compile with no finding. The text says "sk next st with rust", an
instruction with no meaning, and the twin records `rust: 0.0 m`. A skip uses no yarn, so a
colour on it is a modelling error. A chain in a different colour inside a row is possible, but
it changes what is carried. *Fix:* make it an ERROR when `stitches.get(op.stitch).produces == 0`
and the op has a colour, and decide whether to allow coloured chains (WARNING at least). Add
both cases to the colourwork suite.

**H2-4 MEDIUM-LOW: an empty colour table accepts any op colour.** The new check copies the
row check (`if cir.colors and colour not in cir.colors`). With `colors={}`, the op colour
"teal" compiles, and the twin and the materials list gain a "teal" yarn. Because the writer
prints the colour plan only when `len(cir.colors) > 1`, the tapestry instruction disappears as
well. *Fix:* when any op names a colour, require a colour table that contains it and the row's
main colour (ERROR otherwise). The legacy row-only path can stay as it is.

**H2-5 LOW (test quality): the digest test pins nothing.** `pinned[b] = sha256(...)` is built
and then only its length is asserted. Replace it with stored hex digests for the 11 builders,
or with a comparison against the CIR built by the base code. The independent comparison above
shows the claim is true today. The test would not catch a regression.

**H2-6 LOW: colour keys the writer cannot round-trip are accepted by the compiler.** The
reverse regex accepts only `[a-z0-9][a-z0-9_-]*` (and is case-insensitive). "Dusty Rose"
compiles but then fails the reverse compare with `REVERSE_PARSE`. That fails closed, but late
(at certification). *Fix:* validate op-colour keys against the same grammar in the compiler.

**INFO.** The `COORDINATION.json` diff also re-encodes `§` as `§` in an unrelated
`_protocol` string. This is harmless, but the integrator should expect it in the merge.

### (e) Recommendation: **HOLD**

The core plumbing is sound, deterministic and well mutated: 9 of 9 mutations were killed, and
no Launch-0 design, release hash or written pattern moves. It should not enter batch 5 as it
stands, because it re-opens a Product Truth gate (H2-1). Every colourwork technique claim
becomes backable by a single stitch, and that becomes reachable the moment a fallback or
builder emits `Op.color`. The colour plan that reaches the customer PDF can also give a wrong
carry instruction and understate yardage (H2-2). Accept it once:
1. H2-1 is fixed with technique-specific predicates and refusal tests.
2. H2-2 and H2-3 are fixed, with tests.
3. H2-5 pins real digests.

H2-4 and H2-6 can be fixed in the same pass. If the integrator wants the field merged before
then, an acceptable interim is to merge it with `fabric_truth` still refusing every colourwork
claim, for example by gating `backed` on a separate technique-predicate flag that defaults to
False.

### Mutations (subject 2)

Each mutation was applied in a scratch worktree, then `test_opus2_cir_colourwork` was run and
the file was reverted.

| # | Mutation | Result |
|---|---|---|
| C1 | drop the op `UNKNOWN_COLOR` check | killed |
| C2 | drop `STITCH_COLOUR_WITHOUT_ROW_COLOUR` | killed |
| C3 | twin yardage ignores the op colour | killed |
| C4 | twin cells ignore the op colour | killed |
| C5 | the reverse `_shape` ignores the colour | killed |
| C6 | the writer drops "with <colour>" | killed |
| C7 | `to_dict` keeps `color: null` | killed (2 tests) |
| C8 | `_flatten` drops `ResolvedOp.color` | killed |
| C9 | the colour plan ignores tapestry rows | killed |

No mutation covers H2-1 to H2-4, because the behaviour in question is untested. Those are
missing tests, not surviving mutants.

### Tests (subject 2, `5b0f8e0e`)

| Suite | Result |
|---|---|
| test_compiler | 9 OK, 0 failed |
| test_twin | 8 OK, 0 failed |
| test_reverse | 18 OK, 0 failed |
| test_opus2_cir_colourwork (new) | 7 OK, 0 failed |
| test_physfix | 46/46 passed (86 s) |
| test_vacuity | 8 OK |

Each suite was run one at a time as `cd brambleloop && PYTHONPATH=src:tests python tests/<f>.py`,
after `pip install -r requirements.txt` (the container lacked SQLAlchemy). `run_tests.sh` was
not run.

---

## Appendix: probe scripts

These scratch scripts were kept outside the repository, in `/tmp/rv/`, and are summarised here
so they can be reproduced:

- `tp.py`: `title_promise` for every `inventory.universe()` slug, diffed between `0e941757` and
  `13d67502`.
- `ef2.py`: `F.plan` and, for totes, `F.tote` + `title_promise` + `eligibility.name_truth`, on
  the title lists above, using the `everyday-market-tote` seed geometry as in
  `test_opus2_draft_constructions`.
- `cw.py`: the colourwork failure modes in (c), built on `_tapestry()` from
  `tests/test_opus2_cir_colourwork.py` and on small `joined_rounds`/`flat_rows` fixtures.
- `dg.py`: `to_json` sha, `design_digest`, `release_hash_of`, `write_pattern` sha, yarn per
  colour and `fabric_truth.backed` for the 11 Launch-0 builders and 26 universe slugs, diffed
  between `d230e8fd` and `5b0f8e0e`.
- `mut1.py` / `mut2.py`: string-replacement mutations, each followed by the suites and
  `git checkout -- <file>`.
