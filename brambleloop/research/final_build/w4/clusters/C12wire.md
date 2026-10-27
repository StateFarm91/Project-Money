# C12 runtime wiring

Branch `claude/w4-C12wire`, cut from `claude/w4-C12` ccde9980. The three C12 modules are now
on the schedule, wired through the normal path. They are handled in the new
`runtime/c12_ops.py`, which is imported at the bottom of `runtime/pipeline.py`.

| job type | agent | cadence | what it does | class |
|---|---|---|---|---|
| `listing.search_visibility_aging` | listing | daily | Calls `search_visibility.aging`. Writes a reading, and opens or resolves one de-duplicated P2 incident per overdue fix. | OBSERVE |
| `listing.window_captures` | listing | daily | Calls `listing_lifecycle.due_captures` for every listing with a verified activation. Writes a reading only. | OBSERVE |
| `etsy.dashboard_harvest` | orchestrator | daily | Calls `etsy_dashboard.harvest` on stored orders and the census. Opens or closes de-duplicated owner tasks and writes a reading. | OBSERVE |

Each job is registered in every place the normal path requires:

- `CADENCES`
- `agents/registry` allowed job types
- `autonomy/charters` (all three resolve to `store_commerce`)
- `pipeline.WORK_KEYS` (`work_done`)
- `authority/classes` (OBSERVE, ungated)
- `swarm/orchestrate.JOB_BANDS` (housekeeping)
- the regenerated `autonomy_map.json` (cadences 126 → 129, handlers 156 → 159)

None of the handlers calls Etsy, spends, or publishes. The owner-entry HTTP routes are left
to the integrator, as agreed.

## Tests

`tests/test_w4_c12_wiring.py` has 4 tests. They fail before this change, because
`runtime.c12_ops` did not exist, and pass after.

These suites also pass: `test_v11_autonomy_timeline` (the committed map matches the
generator), `test_w4_c3`, `test_w4_credhealth`, `test_v11_wiring` and `test_vacuity`.
