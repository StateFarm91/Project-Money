# Independent security review — opus2/p0-revenue-workforce @ 54766c9e (OPUS2A)

- Reviewer: independent Claude Code session, 2026-10-31 (UTC). Read-only on the subject branch;
  only this report is pushed, to `claude/w5-SECREVIEW-OPUS2A-54766c9`.
- Base: merge-base `327d1028` (claude/w4-INTEG8-next). Scope: the four parts listed below only.
- Environment: fresh worktree at 54766c9e, venv from `requirements.lock` (`--require-hashes`);
  `df` 30 GB free before starting. Probe scripts lived outside the repo (`/tmp/probe`) and ran with `-I`.

## Verdicts

| Part | Subject | Verdict |
|---|---|---|
| 1 | `gates/size_claims.py` + `for_publish` wiring (0343b6b0, f76d539c) | **CHANGES REQUIRED** |
| 2 | `visual/laura_home.py` + `flux3_generator` wiring (4f1efcc8, f93b1ec3) | **CHANGES REQUIRED** (one MEDIUM product-truth finding; identity, disclosure and spend are clean) |
| 3 | rim negative in `creative/pattern_refs.py` (f02426fa) | **ACCEPT** |
| 4 | `scripts/p0_acceptance.py` (fc7bd63e) | **ACCEPT** (two LOW hardening notes) |

## Suites run (one at a time, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

All 10 suites passed (rc=0), using the hash-locked venv:

| Suite | Result |
|---|---|
| test_opus2_size_claims | 0 failed |
| test_opus2_laura_home | 0 failed |
| test_opus2_rim_negative | 0 failed |
| test_gates | OK, rc=0 |
| test_first_customer_gate | 12 passing, 0 failing |
| test_eligibility | OK, rc=0 |
| test_w4_flux3generator | 9/9 passing |
| test_w3_b2_canonical_assets | OK, rc=0 |
| test_w3_laura_core_identity | 0 failing |
| test_w4_ownerimg | 35 passed, 0 failed |

(Under the bare system python, five of them stop with `ModuleNotFoundError: sqlalchemy`. That is a
missing install, not a defect in the code.) The suites passing does not cancel the findings below:
none of the bypass or decoy cases in this report is covered by a test.

---

## Part 1 — size-claim truth gate: CHANGES REQUIRED

**What is right.** The `for_publish` diff only adds code: it appends `size_claims.for_release`
reasons, and when the gate raises it adds a refusal reason (an exception fails closed). No
existing reason, gate or early return is removed or relaxed. Both publish callers
(`runtime/pipeline.py:2423`, `products/inventory.py:217`) go through `for_publish`. The reported
defect ("Nesting Baskets, three sizes" on a medium-only release) is refused, and so are
`3 sizes`, `S/M/L`, `two sizes`, `sizes included` and `small and large baskets`.

**Probe** (`check_texts({"listing description": text})`, run at 54766c9e):

| Text | Result | Expected |
|---|---|---|
| `Three sizes, yarn not included.` | **PASS** | FAIL |
| `Three sizes—yarn not included` | **PASS** | FAIL |
| `3 sizes included (pattern sold separately for hats)` | **PASS** | FAIL |
| `three sizes, each size is its own pattern` | **PASS** | FAIL |
| `three-size set` | **PASS** | FAIL |
| `set of 3 baskets` / `a set of three` / `trio of baskets` | **PASS** | FAIL |
| `3 basket sizes` / `three different basket sizes` | **PASS** | FAIL |
| `small, medium, large` (no "and") / `small/medium/large` / `small · medium · large` | **PASS** | FAIL |
| `S, M, L` / `sizes: S M L` / `sizes S to XL` / `XS-3XL` | **PASS** | FAIL |
| `Diameters 20 cm, 25 cm and 30 cm` | **PASS** | FAIL |
| `If your gauge is tight, try a hook one or two sizes larger.` | **FAIL** | PASS |
| `Works in all sizes of yarn` | **FAIL** | PASS |
| `Fits a 1 m/s fan` / `M/L` (a single "M/L" size) | **FAIL** | arguable |
| `A medium nesting-style basket.` | FAIL | by design ("nesting" is always a claim) |

### F1.1 — HIGH — a disclaimer anywhere in the sentence suppresses the whole sentence
`claims_in` skips the whole sentence when `_DISCLAIMS` matches anywhere in it. "not included" and
"sold separately" are ordinary listing words ("yarn not included", "hook sold separately"), so a
real multi-size promise in the same sentence gets through:
`check_texts({"listing description": "Nesting baskets in three sizes, yarn not included."})["state"] == "PASS"`.
Because `_SENTENCE` splits only on `[.!?\n]` followed by whitespace, a dash or comma keeps the
disclaimer in the same sentence. Seller copy is written by the listing agent's model and
can be edited by the owner, so this is the most likely way back into the original defect.
**Fix:** disclaim only when the disclaimer is about sizes, e.g. require "size(s)" / a size
word inside the disclaimer phrase ("other sizes sold separately", "small and large not included"),
or remove only the clause after a disclaimer rather than the whole sentence.

### F1.2 — MEDIUM — synonyms, hyphens, comma/slash word lists and ranges get through
The patterns cover explicit `N [modifier] sizes`, `small, medium and/& large`, abbreviated
slash tokens, `nesting` and `multiple|several|various|all sizes`. They miss `three-size`,
`set of 3` / `trio`, `3 basket sizes` (a noun between the count and "sizes"), `small, medium, large`
without "and", `small/medium/large`, `S, M, L`, size ranges (`S to XL`, `XS-3XL`) and lists of
dimensions. The docstring says the gate is narrow on purpose, which is reasonable for
incidental words, but "set of 3" and an unconjoined S/M/L list are the plain forms of the
claim the gate was built for. **Fix:** allow `\w+\s+` (one or two words) between the count and `sizes`,
accept `-` between the count and `size`, accept `,` and `/` between full size words with no
conjunction, add `set of N` / `trio|pair` + product noun (skipping known sets such as
coaster sets, which are counts of pieces, not sizes), and add a size-range pattern. Add every
row of the table above to `test_opus2_size_claims.py`.

### F1.3 — LOW — false positives on single-size crochet copy
`count` matches "one or two sizes larger" (standard gauge advice about the hook), and
`several_sizes` matches "all sizes of yarn". The current `publish/pdf.py` does not print either
phrase (grep found no hit), so nothing generated today is refused, but CIR prose or designer notes
that reach the PDF could be. `slash_sizes` also counts the token `m/s` and a single size labelled "M/L".
**Fix:** ignore `sizes? (larger|smaller|up|down)` and `hook sizes?`; require a garment/vessel
context for `all sizes`.

### F1.4 — LOW — an unreadable or missing PDF passes on the listing alone
When there is no completed `assets.build`, the PDF cannot be read, or the release's job is not
in the newest 200 `assets.build` DONE jobs (`_pdf_text` `.limit(200)`), the verdict is PASS on the
listing alone (pinned by `test_no_listing_is_unknown_without_a_reason_and_an_unread_pdf_is_reported`).
The comment in `for_publish` ("An unreadable verdict refuses, never passes") is true only of an
exception, not of an unread PDF. Other gates in `for_publish` refuse a release with no built
assets, so this is not a bypass on its own, but the 200-job window can silently skip the PDF
on a busy DB. **Fix:** filter the query by slug/version (JSON field or post-filter without
the limit), and either refuse on an unread PDF or correct the comment.

---

## Part 2 — Laura's home: CHANGES REQUIRED (one MEDIUM finding)

**Clean:**
- **Deterministic, inside a fixed architecture.** `variation` is a SHA-256 index over
  `laura-home-v1:{room}:{listing}:{role}`. The same frame reproduces exactly, and every frame carries
  `HOUSE`, the room's `structure` and `anchors` verbatim (probe: 50/50 kitchen frames contain the
  structure string). Only the angle, light, two lived-in details and the moment vary, each picked
  from closed code-held tuples. Nothing comes from a model, the network or a user.
- **Identity untouched.** No file under `visual/` other than the new `laura_home.py` changed;
  `visual/canonical.py` and `AUTHORISED_IDENTITY_CHANGES` are byte-identical to the base. The
  environment never describes Laura (no hair, face, body or age words; the angles name camera
  positions only). The identity-anchor role (Stage A) does not use the scene at all, and the three
  canonical references still lead every Laura request (`image_stages.lifestyle/variant` unchanged).
- **Disclosure and Product Truth gates unchanged.** `image_stages.py` and `flux_prompt.py` are
  untouched; the DISCLOSURE, REALISM and NEGATIVES prompt blocks still render. `FORBIDDEN` refuses
  "photographed sample" / "real sample" wording, so the home cannot claim a real photograph.
- **Spend.** The wiring only changes the `scene`/`edit` arguments of the existing
  `S.lifestyle` / `S.variant` calls. Every render still goes through `image_stages._run` with the same
  renderer, budget and purpose. No new provider call or path exists, and `laura_home` makes no
  network or model call. A `HomeRefused` (for example an environment over 900 chars) raises
  before any render, so it fails closed.

### F2.1 — MEDIUM — the scene adds a decoy of the product's own category to many frames
Rooms are chosen by product category, and several rooms' lived-in details and moments name an
object of that same category. The model is asked to render a second textile of the kind being
sold beside the certified product. Probe (`environment(room_for(cat)[0], listing=f"x{i}", role=r)`,
200 listings × 3 roles):

| Category | Room | Decoy detail | Frames |
|---|---|---|---|
| dishcloth | kitchen | "a folded tea towel over the oven handle" | 297/600 |
| amigurumi | nursery | "a soft toy on the glider seat" | 331/600 |
| baby | nursery | "a basket of folded baby clothes" | 303/600 |
| mittens / hat / scarf | entry | "a child's mittens on the bench" | 308/600 |
| garment | bedroom | "a cardigan over the end of the bed" | 273/600 |
| throw / blanket | living room | "a throw pulled back as if someone just got up" | 148/600 |
| mobile | nursery | "a mobile turning slowly above the crib" | 141/600 |

The Product Truth judge then has two candidate objects to match. The buyer may read the decoy as
part of what they get, or as the product: a second mobile or pair of mittens in the hero image
is a misleading-listing risk. This does not weaken an existing gate, but it adds new input
that works against it. **Fix:** when building the variation, drop any `lived_in` / `moments`
entry that names the listing's own category or a near synonym (a small `DECOY_FOR_CATEGORY` map),
or add "no other crocheted or knitted items in the scene besides the product" to the scene. Pin
the fix with a test that enumerates every category × room.

### F2.2 — LOW — `check()` is not applied to the brief, and the product-only brief is silently truncated
The module docstring says "A brief or environment carrying one is refused", but the flux3 wiring
calls `check` only on the code-built environment and cue (static constants), never on `brief`.
On the product-only path, `f"{room_cue}. {brief}"[:S.MAX_EDIT_CHARS]` leaves the brief at most
about 280 of the 400 characters and cuts it silently, which goes against the module's own
"refused, never truncated" rule. **Fix:** call `laura_home.check(brief)` and raise when
cue + brief exceeds `MAX_EDIT_CHARS`, instead of slicing.

### F2.3 — INFO — "Laura's family home" in the product-only cue
The product-only edit now names Laura. The prompt's subject line still says "The product
alone; no person." (`flux_prompt.py:272`), so this is mitigated. If a person does appear, though,
that frame is not identity-checked, because identity checks run only on `features_laura` frames. Consider
"in the kitchen of a modest family home" for the product-only cue.

---

## Part 3 — rim negative: ACCEPT

The change only lengthens one entry of `negatives()`, on the round-worked branch when
`edging_declared` is false. That makes the prompt stricter; no gate or check changes. It cannot
contradict a valid CIR: the stitch taxonomy (`cir/stitches.py`) has no crab stitch (rsc) and no
picot, and a CIR that names an edging/border/trim skips the entry. INFO only: the text now
says "vessel's top rim" for flat round pieces too (hexagon coaster); harmless, but
`facts["shape"] == vessel` could gate it. `test_opus2_rim_negative` passes.

## Part 4 — `scripts/p0_acceptance.py`: ACCEPT

Offline instrumentation only. It uses a scratch SQLite DB under the output dir
(`Database(..., scratch=True)`) and an artifact dir under the output dir. `run()` removes provider
credentials (`ETSY*`, `ANTHROPIC_API*`, `OPENAI*`, `BFL_*`, …) and replaces
`socket.socket.connect` / `socket.create_connection` with a refusal. Workers run in `Phase.SHADOW`,
and demonstration 13 checks that publishing is refused and that no `etsy_listing_id` exists. It
writes only `<dir>/p0_acceptance.json` and the scratch DB. Its `classification` block says
`deployed: NOT by this run`, `production_verified: NOT by this run … does not prove production
acceptance`, `business_outcome_proven: NO`. The committed evidence JSON
(17 OFFLINE_PASS, 1 NOT_DEMONSTRABLE_OFFLINE) carries the same block and contains no secrets.
It is not registered as a suite.

- **F4.1 — LOW:** `os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")` keeps an inherited
  `production` value. Workers are forced to SHADOW and sockets are closed, so there is no effect
  today, but use plain assignment.
- **F4.2 — LOW:** the socket block does not cover `socket.socket.connect_ex`, UDP `sendto`, or DNS
  (`getaddrinfo` still resolves). There are no credentials, so nothing can be authenticated or spent,
  but blocking `connect_ex` too would make the "every outbound socket refused" claim exact.
- **INFO:** the committed JSON records the author's scratch path `/tmp/claude-0/p0acc`; harmless.
