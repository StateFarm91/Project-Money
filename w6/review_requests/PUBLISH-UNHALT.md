# Review request — eng/publish-unhalt

**Branch:** `eng/publish-unhalt`, cut from `claude/batch19-fixers` 8204c93. Not merged, not
deployed, no PR. Production is unchanged: 2f7da291, SHADOW.

**Trigger:** production readback shows FAIL `publishing_halt_clear` and WARN "no draft
candidate among 7 certified Launch-0 releases with a listing".

**Evidence basis.** This session did not read the token-gated `/api/readback/evidence`. It
read no Railway variable values and holds no operator token. Inputs were:
- public `/api/verify` (`publishing_halt_clear` false, `stale_artefacts_rebuilding` true);
- `/health` (commit 2f7da291);
- Railway deploy logs, which hold HTTP access lines only;
- the code at 2f7da291 and 8204c93, which share the same halt and rebuild code;
- BUILD_STATE's 2026-11-18/20 production diagnosis: 14 halted products, including
  `market-basket-trio` and `hexie-coaster-set`.

Each finding below is a code fact proved by a test. Where production holds a row of that
shape, this is inferred, not observed.

## How the halt works (for the reviewer)

`publishing_halt_clear` needs three things:
- a fresh truth sweep;
- `systemic` False;
- no open `systemic-halt:publication` row.

That row opens and closes on `incident_lifecycle.systemic_evidence`: one halting family over
at least 3 products and at least 50% of the catalogue. Its evidence is the products' own
`stale-artefact:*` and `rebuild-incomplete:*` rows, so the halt clears only when those rows
can close. While it is open, `release_gates.staleness` refuses every publication.
`listing_package` therefore reads BLOCKED (source `release_gates.for_publish`), and no release
can be a draft candidate.

## Code-level reasons the halt stays open

| # | Reason | Status |
|---|---|---|
| U1 | `artefacts.sweep` closed a `stale-artefact` row only on FRESH or SUPERSEDED. A row whose artefact now reads **retired** (legacy output of a superseded design), or that the sweep **no longer finds at all**, can never read either, so it halted its product for good. | **Fixed.** A retired row closes with the retirement reason. A vanished row closes only when the sweep has the full `expected` estate. With `expected=None`, absence proves nothing and the row stays open. |
| U2 | Retired legacy-duplicate slugs (`products.launch0.LEGACY_DUPLICATES`: `market-basket-trio`, `hexie-coaster-set`, both in production's 14 halted products). Only the *unrecorded* half of `artefacts.check` honoured retirement. Their recorded rows read STALE and blocking. `rebuild_graph.rebuild_set` planned rebuilds that `creative.preengineering` refuses. Their `rebuild-incomplete` rows could never be closed by a delivered rebuild. | **Fixed.** Recorded rows of a retired slug read UNPROVEN+retired, the same rule as the expected side. `rebuild_set` skips them and lists them in `retired_skipped`. The sentinel closes a retired slug's rebuild-incomplete row, naming the retirement. |
| U3 | An exhausted `rebuild-incomplete` hold whose recorded refusal was a #39 policy refusal (`listing_image_rules`, since released by D-OWNER-POLICY39-OVERRIDE) was never re-read. `retry_hold_reason` kept returning the hold, no retry ran, and the row could never close. | **Fixed.** `rebuild_graph.held_policy_cause_cleared` reads the watched source keys named in the hold's recorded refusal text (deterministic: `POLICY_SOURCES` keys). It releases the hold only when none of them is unreviewed, stale or unread now. On release the sentinel gives the row one fresh, recorded budget (`hold_released`) and one targeted rebuild. The row stays OPEN and halting; only the existing positive-evidence rules close it. A hold is released at most once per distinct hold text (`held_digest`). Attempts that failed before the release do not spend the new budget. An unreadable policy state releases nothing. |
| — | `truth.sweep` evaluates `systemic` before the sentinel closes rows, so the halt closes one cycle late (2 h at most). | Not a defect. Left as is. |
| — | Rows that are genuinely stale and still rebuilding. | Not a defect. The rebuild loop handles them (`stale_artefacts_rebuilding` PASS). |
| — | Exhausted holds with a non-policy cause (KeyError, no stored release, withheld). | Correct by design. They need that cause fixed and are already named in `stale_rebuilds.rebuild_incomplete_held_reasons`. Whether production has any is UNKNOWN here. |

## Reasons no Etsy draft candidate exists

`first_listing_readiness.draft_candidate` is: every gated packet section PASS, not on Etsy,
package READY, and the package bound to the release. **I checked this predicate and it is
right.** It does not require anything that can only exist after the draft. The causes are
upstream of it:

| Cause | Who clears it |
|---|---|
| Systemic halt, so `for_publish` refuses and the package is BLOCKED | Code (U1–U3), after deploy |
| `etsy_remote_state` UNVERIFIABLE: no sealed, clean live exercise less than 90 days old. No scheduled job runs one; the only door is the operator-authenticated `POST /api/etsy/exercise`. | **Owner**, OWNER_ACTIONS_P0.md P0-1 |
| `policy` section FAIL: the excerpt readings of the five etsy.com/legal pages are dated 2026-09-26, 56 days old against `MAX_AGE_DAYS = 30`. Etsy refuses software, so a person must read the pages. | **Owner**, P0-2. Confirm first; skip if page readings were recorded after 2026-10-22. |
| Seven-frame gallery (D-OWNER-GALLERY-COMPLETE), parity frame review, rollback rehearsal | Automatic: image admission under D-MAIN-IMAGE-ADMISSION / D-OWNER-APPROVE-ALL ceilings, then `launch.readiness`. Not owner items. |
| U5: the WARN named a count and no cause, so none of the above was visible from the CLI. | **Fixed.** `ops/readback._why_not_candidates` lists, per release, its FAIL/UNKNOWN sections, package state and blocker sources, plus the most common causes. It uses fixed-vocabulary fields only; anything else is dropped, never echoed. |

## Not touched

- The kill switch, the fee cap and the CA$6 budget, child safety, the publication and
  activation grant validation, the #39 rule itself, Product Truth and AI disclosure.
- No grant, attestation or waiver was written or forged.
- The systemic-halt rule (3 products and 50%) is unchanged.

## Tests

`tests/test_publish_unhalt.py`: 10 tests. 9 fail on 8204c93. The 10th,
`test_u1_a_genuinely_stale_row_stays_open`, is a guard that passes both ways by design. The
tests cover:
- U1: the retired close, the vanished close (and no close without the estate), and a stale
  row staying open;
- U2: retired reads, rows closing and nothing planned; the sentinel closing the retired
  product's row and leaving the live one; the systemic halt itself opening and then resolving
  with a resolution once the retired rows close, while the live product's own halt stays open;
- U3: release only after the cause clears, with the row still open and halting and one
  targeted rebuild; no release for non-policy or stale-source holds; no second release of the
  same hold; pre-release failures not counted;
- U5: the WARN text, with an injection string dropped.

Runner (targeted, filtered, dirty tree, so not release-eligible):
`JOBS=4 SUITE_REGISTRY=0 SUITES="test_publish_unhalt test_vacuity test_artefacts test_rebuild_graph test_eng_stale_rebuild_loop test_eng_stale_round2 test_eng_recovery test_w4_listready test_w3_k7_ops_truth test_w4_readback_evidence test_provenance_backfill test_w6_fix_only_rebuild test_first_listing_doors test_l0_physical_upgrade_provenance test_cert_provenance" bash run_tests.sh`.
The result is recorded in BUILD_STATE.

## Questions for the reviewer

1. U3 reads the cause from the recorded refusal *text*, using exact `POLICY_SOURCES` keys plus
   a `#39`/`policy` marker. It is deterministic, but it depends on the wording. Should holds
   also record the structured source list going forward? That is not done here; the text
   fallback is what production's existing rows carry.
2. U1's vanished-row close depends on `expected_from_db` enumerating the whole estate. Any
   artefact class it does not enumerate that has no provenance row would let a row close.
   Today every class that opens rows is enumerated or recorded.
