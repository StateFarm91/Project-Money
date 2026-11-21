VERDICT: H3 CONFIRMED IN CODE (rebuild-incomplete rows are per product, but they are closed on per-release names, so a row naming a superseded release could never close). FIXED. The budget-reset alternative is REFUTED. Production rows not read; that production's 12 rows have this shape is inferred.

# Review request: eng/halt-380-h3

**Branch:** `eng/halt-380-h3`, cut from `claude/w6-release-19d1`. Not merged, not deployed, no
PR. Production 7b250d61 is unchanged.

**Evidence basis.** This session used the readback figures in its brief: 12 halting products
including `cloudline-baby-blanket` and `winter-village-graphghan`, which have RETIRED
releases; 9 products RETIRED; `rebuild_incomplete_budget_reset` = 2 for each of 5 products;
`open_rebuild_incomplete` 12, held 0. It did not read production's incident rows, the
token-gated evidence or any Railway variable. Each finding is a code fact proved by a test.
Whether a given production row has the shape below is **inferred, not observed**. The
post-deploy readback check at the end settles it.

## Findings

| # | Hypothesis | Result |
|---|---|---|
| H3-a | Rows of retired or superseded releases hold the halt | **Confirmed. The cause.** See below. |
| H3-b | A product whose CURRENT release is fresh, while an OLD release's names keep its row open | **Confirmed.** This is the same defect as H3-a. |
| H3-c | Rows keyed to releases that no longer exist | **Confirmed. Same defect, same fix.** A name whose version is not the newest certified one is obsolete, whether or not that version still has a row. |
| Alt | Budget resets re-open rows forever | **Refuted.** `reset_legacy_budget` fires only while `legacy_incomplete(detail)` holds, meaning no `attempts` and no `budget_reset`. The reset writes `budget_reset`, so it happens once per row. `legacy_report_count` 2 is the pre-branch count it preserved, not a loop. |
| Denominator | Retired products inflate `products` | **Not a cause.** `systemic_evidence` counts every `Product` row. Extra rows only raise the bar (12 / N ≥ 50%). Rows of retired legacy-duplicate *slugs* are already closed by U2. The threshold and denominator are unchanged. |
| stale-artefact | Per-release rows of old releases | **Already handled.** These rows are keyed per artefact, so per release. An old recorded artefact reads SUPERSEDED, and U1 closes retired and vanished ones. No change. |

### The defect

`rebuild-incomplete:<slug>` is **one row per product**. Its `detail.stale` lists the artefacts
whose rebuild was outstanding, as **per-release** keys such as `pdf:<slug>@1.0.0#pdf-us`.
The sentinel (`runtime/release.handle_stale_artefact_sentinel`) closed the row only when every
named key read FRESH or SUPERSEDED in the provenance sweep and nothing of the product read
STALE.

Once a product is re-engineered (1.0.0 → 2.0.0), its old release's artefacts read in one of
three ways:
- **retired**: UNPROVEN plus retired, for a legacy listing copy, SEO or certificate never
  recorded. This is not "settled".
- **no provenance row**: a PDF or chart that no longer exists. This is not "settled".
- SUPERSEDED, for a recorded artefact. This one already counted as settled.

Nothing rebuilds a superseded release, so a row naming a retired or vanished old artefact
could never close. The row halts its product (`release_gates.staleness`) and counts toward
`systemic_evidence`'s `rebuild-incomplete` family. Twelve such rows over at least 50% of the
catalogue keep incident 380 open for good, even when every current release is fresh.

The ENG-RECOVERY legacy restart and the U3 release targeted the same obsolete names. Those
rebuilds could never make them fresh either.

### The fix

- **`ops/artefacts.obsolete_release_key(key, slug, latest_version)`** returns a reason when a
  named key is a versioned artefact of *this* product whose version is not the newest
  certified one. It returns None, which fails closed, for:
  - an unversioned key (marketing);
  - a `collection` key;
  - another slug's key;
  - a product whose newest release cannot be ordered.
- **The sentinel** sets obsolete names aside and judges the row on the **current release**:
  - If the row names current-release keys, those are judged.
  - If it named only obsolete releases, every non-retired artefact of the product is judged.
    This is the existing review M-C positive-evidence rule for a row that names nothing.
  - Either way, the keys must be FRESH or SUPERSEDED, there must be at least one, and nothing
    of the product may read STALE.

  A closed row gets its own resolution, and the set-aside names are recorded in
  `detail.obsolete_release_names`. That field is also written on rows that stay open. The
  sentinel audit gains `rebuild_incomplete_obsolete_release_closed`. The legacy restart now
  targets current-release keys, not obsolete ones.
- **Not changed:**
  - the systemic rule (3 products and 50%) and its denominator;
  - `release_gates`, the kill switch, budgets and the publication grant;
  - stale-artefact rows.

  No row is closed on absence alone. A **genuinely stale current release still halts**, and so
  does an **unproven** one.

## Tests

The new suite is `tests/test_halt_380_h3.py`, 6 tests, all passing. On the base, 5 fail; 3 of
those fail for the substantive reason, the row staying open:

- **The key rule is narrow:** current, unversioned, collection, other-slug and unknown-newest
  keys are never obsolete.
- **A re-engineered product's row closes:** the row names a retired 1.0.0 listing copy and a
  vanished 1.0.0 PDF, and the 2.0.0 certificate is FRESH. It closes with the moved-past
  resolution. Fails on base: the row stays open.
- **Guard, stale:** the same product with a STALE 2.0.0 certificate stays open and halting.
- **Guard, unproven:** the same product with a 2.0.0 certificate that is only UNPROVEN stays
  open. This one passes both ways by design.
- **Mixed names:** a row naming old artefacts plus a missing 2.0.0 PDF stays open and is judged
  on the 2.0.0 name only. Fails on base: the base also lists the 1.0.0 names.
- **Production-shaped:** 6 products, 5 halting in `rebuild-incomplete`, which is systemic.
  - The 5 are `cloudline-baby-blanket`, `winter-village-graphghan` and two other re-engineered
    products naming only old releases (one a legacy row with no attempt budget), plus one live
    product with a genuinely stale current PDF.
  - After one sentinel pass, `escalate_systemic` resolves the halt.
  - The denominator is still 6, and the live product's own row stays open and halting.
  - Fails on base: the halt stays open.

Suite results are in the commit message and the section below.

## Post-deploy readback check (decides "inferred" vs "observed")

After deploy, the first `ops.sentinel` audit's `rebuild_incomplete_obsolete_release_closed`
lists the products this unblocked. Any row still open carries `obsolete_release_names`
(what was set aside) and `sentinel_read.verdicts` (what it is now judged on). Two outcomes:

- If incident 380 is still open, the remaining rows name **current-release** artefacts that
  are stale or unproven. That is real work for the rebuild loop, not this defect.
- If `obsolete_release_closed` is empty, H3 was not production's cause, and H1 or H2 should
  be preferred.
