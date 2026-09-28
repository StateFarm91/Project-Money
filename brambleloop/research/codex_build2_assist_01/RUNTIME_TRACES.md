# Runtime traces and proof limits

Pinned source: 2e66b3a44cf87fb6d99d10f136148899b4177877. Exact symbol links/hashes are in out/source_index_2e66b3a.json.

## Orders correctness — O01–O10

Entry: runtime.worker.CADENCES schedules commerce.orders_ingest every six hours; runtime.orders.handle_orders_ingest calls commerce.orders_ingest.ingest. Transactions scope plus recorded probe gate the reader. The tests use synthetic grant/probe rows to exercise this internal allowed branch; they do not establish real owner authorization or live credentials.

Producer: EtsyReceiptReader/receipt parsing → orders_ingest.lines → _record_line. Reader creation-watermark filtering can miss old modifications. lines ignores paid/canceled eligibility and reduces any refund to a Boolean.

State: cohorts.record_customer and record_order commit independently; record_order commits before buyer_trust.record_sale_version; ledger insertion is another session. Duplicate Order early-return stops missing OrderVersion repair. Existing ledger insertion can still repair on retry. Current catalogue version is used for historical transactions.

Consumers: commerce.order_readings (daily plus enqueued after new orders) → repeat/cohort, ladder, offer, discount, promotion/referral, trajectory and loop readings; pricing.position and portfolio.review consume directives. growth_ops benchmarks/ads plans and finance decisions consume Order/Ledger figures. Unknown attribution becomes organic and add-only loop deltas cannot reconcile reductions. These are downstream contamination paths; this lane directly reproduced stored source-of-truth failures, not every later commercial decision.

Effect: wrong revenues/refunds/contribution/first-customer/version state can invalidate pricing, reinvestment, growth and correction evidence. Final publication/spend/message remained blocked or unexecuted. C-78's report describes a candidate repair, not the code these tests executed.

Failure proof: direct production ingest with isolated SQLite; injected exception after actual Order commit, reopen same database, retry original production service. No replacement application algorithms. This proves a transaction recovery defect but is not a SIGKILL, multi-worker, Postgres or live Etsy contract test. Sale states/Money fixtures follow public reference/definitions URLs saved in raw result.

## Growth priority — G01/G02/G03/P10

Entry: hourly growth.steer → handle_growth_steer → steer reads seasonal daily OperatingReading/weekly/war-room evidence. _record style readings plus AuditLog growth.steered receipts preserve previously moved IDs. G01's third-run erasure is fixed; protected receipt retention is added in b9f7e3a.

Producer and durable state: admitted fast-lane slug yields delta=-20; steer writes Job.priority += delta. Test starts at the real seasonal_deadline band 25; the durable value becomes 5.

Consumer and effect: JobQueue.claim orders due work by stored priority minus bounded age credit. It claims chain.rebuild at 5 before waiting support.reply at customer band 10. Worker.run_once calls claim before lane_hold. No claimed handler is executed by this test. This demonstrates actual selection ahead of protected work, not just a dashboard value.

G03: handle_growth_steer emits chain.rebuild with slugs; current release handler resolves only those product targets, rejecting an unknown request. Named existing regression passes. P10 is different: attempt/request/fingerprint completion binding remains unresolved and C-80 owned.

## Closure — P01/P02/P03

Producer: registry status/parked_on plus executable proof metadata and gate readings. Classifier now honors explicit unparked PARTIAL before executor gate membership (60 controls).

State/consumer: matrix aggregates classifications; closed_out requires successful live gate reads (3 controls). No-DB computation remains indeterminate. It does not certify from a zero-OPEN total alone.

Residual proof limitation: proof_of still uses module existence/test naming and module reachability to set proven. There is no general requirement-specific producer/output/action binding or executed-test receipt. Changing the counter logic cannot substitute for that trace.

Platform limitation: _rel_of emits Windows separators, cadence matching expects forward slashes. Diagnostic normalization changes only the in-memory path adapter; every threshold and requirement file remains unchanged. Counts under that diagnostic are not a certified native run.

## Pending integrated and candidate contracts

Design now has a real judge_held producer; it records judge, slug and a truncated board location. Current judgement_for and verify_funnel do not bind approved bytes/payload. _gap_for chooses first gap in a pod rather than exact originating gap. _stage_evidence accepts slug-wide assets/certificates. These are source-reviewed defects, not new paid model results.

Improve replay/rollback/enforce and Intel physical-photo/strength/drift candidate modules remain unmerged. Their original e6c3976 producer/state/consumer/action specifications remain authoritative review inputs. Do not import a candidate test result into the current-head verdict.

No current shared application repair vacancy was proven. C-80 names Platform2; Git cannot establish current agent liveness. All implementation handoff remains with Opus.
