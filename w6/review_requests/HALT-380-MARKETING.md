VERDICT: TWO MARKETING DEFECTS REPRODUCED ON THE REAL CHAIN IN PRODUCTION'S SHAPE (12 products, about 9 marketing rows each, old chain, cir and release) AND FIXED, PLUS ONE LATENT DEFECT. But the 10:35Z readback cannot say whether HALT-380-VERIFY "changed nothing". It was taken 14 minutes after that deploy (10:21Z). That is inside the 12 h RETRY_AFTER that follows the first chain-9 attempt (chain moved at 19b, 02:06Z), so no attempt can yet have run on the new code. The rebuild order was already core first; the test proves it. Production rows were NOT read. Which of the 102 are earlier-plan pieces is inferred, not observed.

# Review request: eng/halt-380-marketing

**Branch:** `eng/halt-380-marketing`, cut from `claude/w6-release-19h3` (52aa7ae, which
records the deployed dc10a48d). Not merged, not deployed, no PR. Production is unchanged.
Main deploys only with the owner's per-SHA approval.

**Evidence basis.** The readback figures in the brief (10:35Z), `release/DEPLOYED_HISTORY.json`
and the code. I read no production rows, no token-gated readback and no Railway variable
values. Every finding below is reproduced on the real handlers: `cir.compile → gate.certify →
assets.build → pricing.position → listing.seo → launch.plan → marketing.schedule`, with the
real `ops.sentinel` and `chain.rebuild`.

## What the readback says, read exactly

| Figure | Reading |
|---|---|
| open 112 | 111 halting rows plus `stale-artefact:backlog`. The backlog row is the non-halting instrumentation backlog: it has no provenance row and no artefact class, which is the "unrecognised 1 / no_row 1". |
| marketing_asset 102, unversioned 103 | The 102 rows plus the backlog row. Marketing keys (`slug:channel:digest`) carry no version. |
| current 9 | pricing 2, listing_copy 2, seo 2, release_bundle 2, support_knowledge 1: the current-release core rows of 2 products. |
| moved chain 111, cir 94, release 94 | Every stale row has `chain:release` moved (8 → 9). Only marketing rows have cir and release moved too, so 94 of the 102 were written from an older release. All 9 core rows have only the chain moved. |
| stale 111 | None of the 111 reads RETIRED, so no superseded piece is among them yet. |

**Timeline (deploy history plus the code's retry rule):**
- `CHAIN_VERSION` first reads 9 at 19b c9e8549f (2026-11-21T02:06:32Z); 19a was still 8.
- The first chain-9 attempt runs its stage and 3 × 20 min verify checks, then opens
  `rebuild-incomplete`.
- `RETRY_AFTER` is 12 h, so the next attempt cannot start before about 14:00–15:00Z.
- HALT-380-VERIFY went live at 10:21:19Z (88fc059a) and the readback was at 10:35Z. **No
  post-deploy attempt can have run.** "Changed nothing" is expected at 10:35Z whether or not
  the fix works.
- The figures are consistent with the brief's "14 in RETRY_AFTER".

The attempt production will run next was therefore reproduced on the real chain.

## Reproduction: production's shape on the real chain

New suite `tests/test_halt_380_marketing.py`. The real catalogue is built once; the twelve
products are those of production's twelve that have a builder here, filled up from the
catalogue. Inside a moved chain:

- every product's marketing rows are recorded from an older release (cir and release moved);
- one earlier-plan piece per product is added beside the current plan, cycling through the
  unpublished states `drafted`, `held`, `approved` and `scheduled`, plus one **published**
  piece on the first product;
- the first two products' current-release core rows (pricing, listing_copy, seo,
  release_bundle, support_knowledge) stay under the old chain, like production's 9;
- everything else is current.

The suite asserts the shape before it starts: only marketing and the 2 × 5 core rows are
stale, at least 96 marketing rows, all with chain and cir moved. The systemic halt opens
(12 products).

### The brief's candidates

| Candidate | Finding |
|---|---|
| marketing.schedule never runs: refused on #172 because the 8 core artefacts are outstanding, and those are refused by something else | **Refuted on the real chain.** A targeted rebuild enqueues ONE stage, `pricing.position`, the earliest any stale class needs. That stage and the stages it enqueues write, in order: listing_copy, seo and pricing (`listing.seo` → `_persist_listing`), support_knowledge (`listing.seo`), the release bundle (`launch.plan`), and only then `marketing.schedule`. So marketing reads nothing non-marketing outstanding. The suite asserts from the rows' own job ids that every core row was written before the marketing.schedule job that rewrote that product's marketing, and that marketing.schedule was never refused on #172. If a core stage IS refused (pricing band, SEO block, withheld release, launch hold), the chain ends before marketing.schedule exists. That refusal is a real gate, and HALT-380-VERIFY already parks it with its reason. What refuses production's 2 products is **not known from the readback**: after their next attempt, `parked` and `outstanding_read` on their rows name it. |
| marketing.schedule runs and writes new digests, leaving the old rows stale and not superseded because the pieces are not drafts | **Confirmed as a code defect** (Defect 1). Whether production's pieces are in a non-draft state is **UNVERIFIED, and probably not**: every code path in the history of `ContentPiece` writes `drafted`. If they are drafts, HALT-380-VERIFY supersedes them on the next attempt. |
| something else | **Confirmed** (Defect 2, found by the reproduction): content the rebuild just retired kept refusing the product's marketing until the next sweep. Latent defect 3: a superseded piece back in the plan stayed superseded. |

### Defect 1: earlier-plan pieces in any unpublished, non-draft state never closed

`marketing.schedule` superseded only `drafted` pieces its plan no longer contains. A piece in
any other unpublished state kept its key and so read STALE for good: no stage rewrites a piece
the plan no longer contains. Every verify check named it outstanding.

On base, the production-shape run leaves exactly those products with their earlier-plan piece
outstanding, the same key, on every check: cloudline, harvest, mosaic-placemat, pet-snuggle,
pressed-flower, spooky, winter-village, hexagon and housewarming. Those are the `held`,
`approved` and `scheduled` ones; the `drafted` ones close.

### Defect 2: an open row of just-retired content refused the marketing rebuild

Found in the production-shape run. After the attempt superseded an earlier-plan piece, that
piece's `stale-artefact` row stays open until the next hourly sweep closes it as "retired, not
stale". In that window, pet-snuggle-mat's next `marketing.schedule` (a `parity-escalation`
chain) was refused "halted (#173)". Instrumented, the only halting row was the retired piece's
own row.

Two gaps in the marketing-rebuild exception caused it:
- `release_gates.staleness` waived a sentinel row only when its artefact reads FRESH or is
  outstanding marketing, so a RETIRED one counted as another halt;
- with nothing outstanding, the exception also required a pending `rebuild-incomplete` row.

The reason starts with #173, so it is the product's own staleness and HALT-380-VERIFY rightly
does not park it. The product simply could not draft content until the sweep ran.

### Defect 3 (latent): a superseded piece back in the plan stayed superseded

Its row was rewritten FRESH, but the piece kept `superseded`. When it next went stale, the
check would read it RETIRED, which would hide real staleness.

## Fixes

1. **`marketing.schedule` supersedes every piece its current plan no longer contains, unless
   it was published.**
   - Each superseded piece records `superseded_by {job, version, prior_state, reason, at}`.
   - Published content is never superseded or retired. It is listed in the audit as
     `published_out_of_plan`, its row stays STALE, and it keeps the product halted.
   - "Published" is read broadly (`artefacts.content_published`): the states published, live,
     sent, posted and scheduled_live, or any `published_at`, `published_url` or `published`
     on the piece's detail.
   - Nothing is deleted.
2. **`artefacts._vanished_lookup` never retires a superseded piece that carries any sign of
   publication.** Everything else in that rule is unchanged and fails closed.
3. **A superseded piece back in the current plan is restored to `drafted`**, with
   `restored_by` recorded.
4. **`release_gates.staleness`, for the marketing-rebuild flag only:**
   - a sentinel row whose artefact reads RETIRED is waived, as FRESH already was.
     `rebuild_graph.publication_gate` now also reports `retired`;
   - with nothing outstanding, the rebuild may proceed when every halting row is one the
     sweep will close (`halting_other` empty).

   `halted`, `reasons` and `blocks`, which publication reads, are unchanged. Any other
   halting row, an integrity failure, a product-creation policy change or non-marketing
   outstanding work still refuses.

**Not touched:**
- the binding rule;
- REBUILD_MAX_ATTEMPTS, RETRY_AFTER, the verify attempts and delay;
- the systemic thresholds and denominator;
- parking;
- `release_gates`' publish path, the kill switch, budgets and grants;
- child safety;
- the premium PDF standard and every certification gate.

No test was weakened or skipped.

## Tests

`tests/test_halt_380_marketing.py`, 4 tests (declared in `scripts/suite_final_segment.txt`,
because the real chain reads today):

- **Production shape, 12 products, real chain.** With the fix:
  - marketing.schedule is never refused for any of the twelve;
  - core rows are written before marketing in both core-stale products;
  - every product's last verify check leaves nothing outstanding except the published piece;
  - every unpublished earlier-plan piece is superseded with its prior state and reads RETIRED,
    and its row closes "retired, not stale";
  - the published piece stays `published`, STALE, listed and halting;
  - the systemic halt resolves on its own evidence;
  - the only open `rebuild-incomplete` row is the published-content product's.

  **On base: fails** (9 products keep their non-draft earlier-plan piece outstanding).
- **The waiver:**
  - a retired piece's open row, with live marketing outstanding, does not refuse the
    marketing rebuild, and publication is still halted;
  - with nothing outstanding and only that row open, the rebuild may proceed;
  - guards: a STALE pdf, and a non-staleness halt (`terms-divergence`), still refuse.

  **On base: fails** (`outstanding_only_marketing` is False).
- **Publication is never retired:** the published-state and published-detail readings, and a
  superseded piece with `published_at` reads STALE, not retired. Fails on base: the helper
  does not exist.
- **A superseded piece back in the plan:** restored to `drafted`, FRESH after the rebuild, and
  STALE (not retired) when the chain moves again. Fails on base: it stays `superseded`.

Results on the final tree are below (SQLite; dirty tree, so not a release-eligible runner
record).

**New suite:** `test_halt_380_marketing` 4/4. The three short tests passed in the full-suite
run; the production-shape test passed in a separate run after its second-sentinel check was
corrected. That check had expected the second sweep to enqueue nothing. The estate-wide chain
change lists other products' already-fresh rows again, which is pre-existing behaviour, so the
check now asserts the real condition: only the published piece reads stale. On base, all 4
fail, each for the reason given above.

**Passing on the final tree (25 suites, each run directly):**
- Named in the brief: `test_halt_380_verify` (4), `test_halt_380_h3` (6),
  `test_eng_halt_380` (6), `test_publish_unhalt` (10), `test_eng_stale_rebuild_loop` (20),
  `test_cert_rebuild_chain` (10), `test_vacuity` (8).
- Marketing suites: `test_growth` (13), `test_owned` (9), `test_video` (16), `test_launch`
  (28), `test_w4_fmbatch1_constellation` (2), `test_cert_growth_ops` (13), `test_w4_listready`
  (41, R4's marketing exception), `test_w4_prodfix` (8), `test_eng_recovery` (23).
- Gates and provenance: `test_cert_publish_gates` (18), `test_artefacts` (23),
  `test_rebuild_graph` (10), `test_eng_stale_round2` (24), `test_provenance_backfill` (12),
  `test_cert_provenance` (12).
- Core: `test_compiler` (9), `test_reverse` (18), `test_twin` (8).

Not re-run here: `test_w4_autonomy_idle_departments`. Its one known failure
(`test_a_wide_rebuild_fits_the_varchar_200_key_column`) is pre-existing and recorded in
HALT-380.md and HALT-380-VERIFY.md. The generated files (`autonomy_map.json`,
`decision_index.json`) are regenerated by the release commit, as for HALT-380-VERIFY.

**Not run here:** the PostgreSQL halves. No local toolchain exists.

## Post-deploy readback check (inferred vs observed)

Read after each product's next attempt, so after about 15:00Z for the first wave, and not
before:

- **The 10 marketing-only products.** `chain.rebuild_verified` should carry empty
  `outstanding`. `marketing.scheduled` should list the earlier plan under `superseded_drafts`
  (and any published copy under `published_out_of_plan`). The next sentinel should close
  those rows "retired, not stale". `stale_incidents.by_class.marketing_asset` should fall
  towards 0.
- **The 2 core-stale products.** `rebuild-incomplete` should either close, or carry `parked`
  naming the gate that refused the core stage. A park is a real gate: owner or department
  work, not a rebuild defect.
- **If marketing_asset stays near 102 after the retry window:** `outstanding_read` on the
  verify audit names what each row reads. Any `published_out_of_plan` entry is public copy
  waiting for a decision, and correctly holds its product.

## Open

1. `marketing.schedule`'s rebuild path rewrites the body of a planned piece even when it is
   published. That is pre-existing behaviour, unchanged here. It does not retire anything,
   but it edits public copy's local record; it should be reviewed separately.
2. The 12 h RETRY_AFTER means a fix to the rebuild loop is not observable for up to 12 h after
   deploy. A readback taken sooner cannot judge it. Each review request should state the
   earliest meaningful readback time.
