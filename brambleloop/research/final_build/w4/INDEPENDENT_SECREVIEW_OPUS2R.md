# INDEPENDENT SECREVIEW OPUS2R — research → Product Development (opus2/p0-construction-registry)

Reviewer: independent, read-only. Date: 2026-11-02 (UTC).
Branch: `origin/opus2/p0-construction-registry` at `21d4ceaf`. Scratch worktree (detached); removed when the review finished.
Commits reviewed: 83194fb7, d1ebb27f, 3a11d59a, 8b4076a9, 21d4ceaf. The amigurumi and pouch work is out of scope (that is OPUS2P).

## Verdict: **DO NOT SHIP** (as merged into live drafting)

What holds up:
- Hold is fail-closed. A request with anything unresolved is never built (`pipeline._draft_creative` checks first, and `build()` raises as a second check).
- Chart choice is deterministic. The hash rotation was added in d1ebb27f and removed again in 8b4076a9.
- Library charts are only admitted when `technique_backed("tapestry", ...)` computes that they are backed.
- `knowledge_gaps` only creates capped owner-approval `OwnerAction` rows. It does not spend.
- No test assertion was removed. All 7 named suites pass.

What blocks it: the new registry path calls the construction builders directly. That skips every title construction-intent allowlist in `FC.plan`: OPUS2N tapestry, `amigurumi_route`, `pouch_route`, the tote rules (OPUS2E) and `_several_sizes` (OPUS2C N3.1). The publish-time `name_truth` does not cover them either, because it does not include `motif_promise`. The result is that briefs whose titles promise things the CIR does not make compile cleanly and come out with `name_truth == []`.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| OPUS2R-1 | **HIGH** | **The registry path skips the title construction-intent allowlists, and `name_truth` passes the result.** `construction_registry.build` calls `FC.vessel/tapestry_basket/amigurumi/pouch/tote` directly, with params taken only from `concept.motif`. `concept.title` is never checked against `FC.plan` (`tapestry_route`, `amigurumi_route`, `pouch_route`, `_TOTE_NOT_PLAIN`/`_MULTIPLE_WORDS`/`_TOTE_SIZE_UNSUPPORTED`, `_several_sizes`). The radar path refuses every case below; the registry path drafts each one, it compiles, and `publish.eligibility.name_truth(cir) == []`. Clear Product Truth breaks: a **bear sold as "Bunny Plush Toy"**; **"Diamond Heart Tapestry Basket" with only a heart chart** (`motif_promise` fails, but `name_truth` does not call it outside Launch-0); "Round Heart Tapestry Basket with Lid" (no lid; OPUS2N-2 removed "round"); "Giant Bear with Removable Hat and Scarf"; "Tote Bag with Zip Pocket and Lining"; "Zippered Coin Purse Wallet" (drafted as a drawstring pouch); "Large Bear". | Probe `probe/probe.py` and `probe3.py` (below): cases A, C, D, G, H, M, Z → `DRAFTED … name_truth=[]`, while `FC.plan` on the same title gives `refused`. **Fix:** in `request_for`, run the family's title route (`tapestry_route`, `amigurumi_route`, `pouch_route`, the tote branch of `plan`, `_several_sizes`) on `concept.title`. Hold on REFUSED, and hold when the route's chart or kind differs from the brief's motif. Separately, consider adding `motif_promise` to `name_truth`. |
| OPUS2R-2 | **MED** | **The brief's `size` overrides the title's size word with no conflict check.** `tapestry_basket(size=...)` uses `size or <title word>`. A brief with `size: small` and the title "Large Heart Tapestry Basket" produces the 16.0 cm small basket under the name "Large". No gate reads the size word against the CIR (`size_claims.claims_in("Large …") == []`). For amigurumi, pouch and tote, `req.size` is accepted and then silently ignored (`_amigurumi` does not set it; `_plain` sets it only for vessels). | Probe F: `DRAFTED … note='… about 16.0 cm across the points …'`, title "Large …". Probe M: brief `size: large` → standard 29 cm-around bear titled "Large Bear". **Fix:** hold when the brief size and a title size word disagree, and hold when a size is given for a family that does not take one. |
| OPUS2R-3 | **MED** | **The tapestry wall-count change (d1ebb27f) lets the wall pull in or flare up to about 20% in one round, while the size note describes only the base.** `wall_count = round(base/width)*width` and `_adjust_round` does it in one round. For `fir-and-star` and `tulip-trellis` at small: base 60 → wall 48 (ratio 0.80, 12 decreases in one round). Diamond-lattice is about 0.90–0.94; diamond, check, heart and pumpkin are about 1.03–1.11. The note still says "about 16.0 cm across the points" (base spans), and no gate measures the opening. | `probe/geom.py` and `geom2.py`: `fir-and-star small [.., 54, 60, 48, 48, …]`. **Fix:** bound `wall_count/base_count`, for example to ±5%, by choosing the base count as a multiple of both the chart width and 6. Otherwise refuse, or state the opening in the note. |
| OPUS2R-4 | LOW | **A malformed brief raises out of the job instead of a named refusal.** `source_provenance(...)` is called before the `try` in `_draft_creative`, so a `PrototypeRefused` it raises (malformed `benchmarks_consulted`) escapes. The prototype path turns the same input into `cir.draft_refused`. It is fail-closed (nothing is drafted) but the job crashes. `dict(brief)` on a non-dict brief does the same. | Probe X: `EXC PrototypeRefused: benchmark source identities malformed`. **Fix:** move the provenance call inside the try, or catch `PrototypeRefused`. |
| OPUS2R-5 | LOW | **Library tapestry primitives break the imagery check, which wrongly refuses valid words.** `name_truth` passes `"fir-and-star:tapestry"` and `"tulip-trellis:tapestry"` to `title_conflicts`. `MOTIF_IMAGERY` has no such keys, so `carried_imagery` falls back to the words in the slug, and "tree", "forest" and "flower" are flagged even though `MOTIF_DECLARATIONS[...:tapestry]` backs them. This is fail-closed, but it contradicts the declarations. Separately, `LIBRARY_CHART_WORDS` maps "tulip"/"tulips" to tulip-trellis, but the tapestry declaration backs only flower/flowers/floral. | Probe R: "Forest Tree Tapestry Basket" → `imagery: … promises ['tree']`. Probe S: "Flower …" → `['flower']`. **Fix:** strip `:tapestry` before the imagery lookup, and align the word sets. |
| OPUS2R-6 | LOW | **Library chart provenance is recorded by slug only.** The CIR records `products.motifs:<slug>:tapestry`, but not the motif grid's `sha256` (the `Motif.sha256` property exists) or the widening transform. If the grid is edited later, nothing shows it. Originality is asserted at module level in `products/motifs.py`: original geometry, not traced from or derived from another designer's chart, with competitor research used as demand intelligence only. No sign of copied charts. | Read `products/motifs.py` lines 1–17 and `declared_primitives`. **Fix:** add the grid hash, for example `products.motifs:<slug>@<sha256[:12]>:tapestry`. |
| OPUS2R-7 | LOW | **Research-enrichment holds have no consumer, and gap counts are not deduplicated.** Only `knowledge_gaps` reads `cir.draft_held`, and only engine-decision holds. A held motif, palette or size is a dead end: it goes to the audit log only, nothing sends it back to research, and the intake coverage still says "engineering". Each held audit row adds 1 to `construction_refusals` (capped at 3 in `score`, so impact is bounded). This matches the existing refusal counting. | `grep -rn draft_held src` → pipeline.py and knowledge_gaps.py only. |
| OPUS2R-8 | INFO | Dead code and weak mutation coverage. The `tapestry_route` "unusable library chart" refusal (21d4ceaf) cannot trigger today, because every library slug is backed. Most of the new guards are not killed by any test (see mutations): one-chart, one-kind, two-colour, `_plain` motif hold, dimensions hold, `build()` second check, backed filter, band-height guard, radar motif primitive, allowlist words. | Mutations table. |
| OPUS2R-9 | INFO | `knowledge_gaps` with held briefs: it raises `OwnerAction` rows for approval only, with `MAX_OPEN=2`, a shared cap of 3, priced listings, suppression after the owner closes a request, and no purchase. It complies with the no-spend rule. Holds caused by an engine decision (mosaic reach-down) lead to a reference *purchase* recommendation, which cannot fix an engine gap. That is a semantic point only. | Read `assess()`. |
| OPUS2R-10 | INFO | Idempotency is fine. `cir.draft` is enqueued with `draft:{slug}`, and the registry compile key includes the fingerprint. No double draft was found. A held brief cannot be re-drafted after enrichment under the same slug, because the idempotency key is already used. That behaviour existed before these commits. | intake.py:806 and 1121. |

Removed or weakened test assertions: **none**. `git diff c0ecc55e 21d4ceaf -- brambleloop/tests | grep '^-.*assert'` printed nothing.

## Mutations (scratch worktree only; each one reverted with `git checkout --`; worktree confirmed clean)

| # | Mutation | Suite(s) | Result |
|---|---|---|---|
| M1 | pipeline `if req is not None and req.unresolved:` → `if False:` | r2d | KILLED |
| M2 | `build()` drops the `req.unresolved` check | r2d | SURVIVED (pipeline check covers it) |
| M3 | `_tapestry` `len(charts) != 1` → `< 1` | r2d | SURVIVED (and the `set.pop()` choice would then be hash-seed dependent) |
| M4 | `_tapestry` two-colour hold removed | r2d | SURVIVED |
| M5 | `_plain` motif hold removed | r2d | SURVIVED |
| M6 | `_amigurumi` `len(kinds) != 1` → `< 1` | r2d | SURVIVED |
| M7 | size hold removed | r2d | KILLED |
| M8 | dimensions hold removed | r2d | SURVIVED |
| M9 | ENGINE_BLOCKED hold removed | r2d | KILLED |
| M10 | `tapestry_charts` backed filter → `if True` | r2d, tapestry | SURVIVED |
| M11 | `tapestry_route` unusable-chart refusal removed | tapestry | SURVIVED (dead today) |
| M12 | kg counts enrichment holds too | r2d, kg | SURVIVED |
| M13 | `declared_primitives` → `()` | r2d | KILLED |
| M14 | band-height guard removed | r2d, tapestry | SURVIVED |
| M15 | radar-path library motif primitive removed | tapestry | SURVIVED |
| M16 | `*LIBRARY_CHART_WORDS` removed from the tapestry allowlist | tapestry | SURVIVED |
| M17 | kg ignores held rows | r2d | KILLED |

Score: 5 of 17 killed.

## Commands run

```
git -C /home/user/Project-Money worktree add --detach <scratch>/opus2r/wt origin/opus2/p0-construction-registry
git -C <wt> log --graph --oneline -14
git -C <wt> show --stat <sha>   # for 83194fb7 d1ebb27f 3a11d59a 8b4076a9 21d4ceaf
git -C <wt> show 8b4076a9; git -C <wt> show 21d4ceaf
git -C <wt> diff c0ecc55e 21d4ceaf -- brambleloop/src
git -C <wt> diff c0ecc55e 21d4ceaf -- brambleloop/tests | grep '^-.*assert'   # empty
# run one at a time, from <wt>/brambleloop:
PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/test_opus2_research_to_development.py  # 5 OK, 0 failed
PYTHONPATH=src:tests ... tests/test_opus2_tapestry_basket.py        # 7 OK
PYTHONPATH=src:tests ... tests/test_opus2_draft_constructions.py    # 18 OK
PYTHONPATH=src:tests ... tests/test_fallback_draft_provenance.py    # OK
PYTHONPATH=src:tests ... tests/test_opus2_knowledge_gaps.py         # 9 OK
PYTHONPATH=src:tests ... tests/test_launch0.py                      # 52 OK, exit 0
PYTHONPATH=src:tests ... tests/test_vacuity.py                      # 8 OK, exit 0
# probes (each one a single process, run one at a time):
PYTHONPATH=src:tests ... <scratch>/opus2r/probe/probe.py    # OPUS2R-1/2
PYTHONPATH=src:tests ... <scratch>/opus2r/probe/probe2.py   # OPUS2R-5, holds
PYTHONPATH=src:tests ... <scratch>/opus2r/probe/probe3.py   # OPUS2R-4, Z
PYTHONPATH=src:tests ... <scratch>/opus2r/probe/geom.py, geom2.py   # OPUS2R-3
python <scratch>/opus2r/probe/mut.py <wt> M1..M17   # each one runs a single suite at a time
git -C <wt> status --short    # clean
git -C /home/user/Project-Money worktree remove <scratch>/opus2r/wt
```

Nothing was deployed, published or spent. Railway and production were not touched. No existing branch or worktree was modified.
