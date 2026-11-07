# A7 supply status continuation

Source `claude/w5-A7-supply-stall` at `83fe31d25d1d6f85b6d03a276191642eca4d985d`; continuation `codex/a7-supply-continuation`. The original A7 implementation records an exhausted or fully-drafted selection as one stall reading per date. A later same-day scan could find new supply, but the readback and owner dashboard continued to show the previous stall for up to two days. Conversely a later renewed stall must not remain hidden.

The reader now compares the most recent successful, measured `radar.scan` output against the recorded stall. A healthy scan clears the current stall view; a later measured stall restores it, including its latest counts. Failed and unmeasured scans never prove recovery. Historical readings and audit rows remain unchanged. This does not itself create new supply or schedule a draft.

Python 3.11 tests: `test_w5_a7_supply_stall.py` 6/6, `test_w4_readback_evidence.py` 23/23, `test_w5_inventory.py` 11/11. The supply test runs actual handlers and Worker on persistent SQLite, exercises stall → recovery → stall within a day and reopens the database.

**Open cross-pipeline risk:** A7 assumes `draft:<slug>` job rows are permanent, while `ops.retention.job_plan` may delete older unreferenced completed jobs after 45 days. Successful `cir.drafted` audit is lifetime-protected and retains its job reference, but `cir.draft_refused` is windowed. Whether a previously refused/cancelled draft can eventually lose all references and free its key needs a durable, evidence-preserving test and an agreed cross-pipeline idempotency contract. This continuation does not change draft scheduling or claim that risk resolved. Independent review required before integration.
