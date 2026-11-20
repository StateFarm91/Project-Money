# W4-CCGAP2: closing the Command Center gaps CC_GAP_c131f07.md §4 left open

Branch `claude/w4-CCGAP2` from `origin/claude/w4-INTEG2` @ 85ec5d0. This is queue item (3). Everything here is read-only.

| Gap (CC_GAP §4) | Before | After | Evidence |
|---|---|---|---|
| **FU-7** "provider gave no reason" on DEGRADED cards (store_foundation, autonomy, search_evidence, Operations departments): honest, but nothing the owner could act on | `providers.validate` filled in the bare placeholder | `providers.derived_reason` says which of the card's **own items** are not OK, for example "provider gave no reason; from its items: 4 of 6 not OK: seo (DEGRADED), finance (UNKNOWN), a (BLOCKED), +1 more". Nothing is invented, and it still says the provider gave no reason. With no not-OK item, or no items at all, it says exactly that. `tabs.agents_card` still drops the placeholder when it has reasons of its own. | `test_w4_ccgap2::test_reasonless_degraded_card_names_its_not_ok_items`, `::test_agents_card_does_not_append_the_derived_placeholder_to_its_own_reasons`; existing `test_w4_ccgap_views` (placeholder never shown beside real reasons) |
| **FU-5** Laura's "Needs you" was a separate number (10 in CC_VERIFY while Approvals said 14) | `len(owner_queue.facts)`: cards were capped at 10, P0/P1 incidents were added in, and "nothing is open" counted as 1 | It now uses `count = decisions_open =` the Approvals `open` count from the same inbox. P0/P1 incidents are reported separately as `p0_p1_incidents`, and the Laura header links them to Operations. | `::test_laura_needs_you_equals_the_approvals_count`; existing `test_w3_laura_cc_talk` (`needs_you.count >= 1` with open gates) |

Other §4 items:

- **FU-8 (warm-up), snapshots and timestamps.** Already closed, or left as-is on purpose. §4 itself says so.
- **No production-data check.** Owner/deploy-gated; production writes are not allowed here.
- **pypdfium2.** Guarded by an existing static test.

## Tests

All through `testslot.sh`: `tests/test_w4_ccgap2.py` (new), `tests/test_w4_ccgap_views.py`, `tests/test_w3_laura_cc_talk.py`.
