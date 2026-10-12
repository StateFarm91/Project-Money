# Independent Finance review
Reviewed exact finance source blobs from bdf2bd6 (implementation c9e038c), integrated by coordinator at0c3098a. Read-only; no finance/runtime test assertions modified.

## Confirmed high-priority defect 1: cross-period reconciliation erases unresolved exposure
books.py profit_and_loss filters expense ledger by requested period, but builds reconciled_listings from ALL payment listing-ledger rows without date or charge identity. Any later fee for a listing suppresses every prior CostEntry reservation for that listing. A renewal/later fee is not proof that an earlier initial-activation exposure was paid/reconciled.
Deterministic local exact-blob reproduction: create .27 modelled listing55 exposure40daysago; read that old two-day period -> operating_costs_cad .27. Ingest a distinct listing55 CAD1.50 fee dated today. Read SAME historical period -> operating_costs_cad0.0. The later actual expense is outside that period, so both figures disappear from the old period even though no matching initial-fee evidence was supplied.
Root cause: listing identity substituted for charge/event identity; no matching initial activation transaction/ref exists in the reconciliation state. Safe correction must retain unmatched exposure or explicitly link actual charge to reservation; period semantics must be stated, not global suppression.

## Confirmed high-priority defect 2: later actual fees evade today's activation ceiling
listing_costs.ingest_actual raises the original exposure.amount_cad to max(all-time actual fees) but leaves exposure.at unchanged. reserve then sums only CostEntry rows dated today; no current-period actual LedgerEntry sum enters its ceiling.
Same reproduction: old exposure at40daysago, today's actual listing fee CAD1.50. reserve another listing66 at.27 with daily ceiling1.00 ACCEPTS. Today's real fee already exceeds that ceiling, yet it is represented for budget purposes only in an old-dated row outside today's query.
This is independent of the same-listing concurrency control (which the candidate tests correctly exercise). Shared advisory/SQLite locks serialize writes but cannot repair wrong period/source accounting.

## Executed evidence
Executed exact `git show bdf2bd6:.../finance/listing_costs.py` and `books.py` blobs in temporary Python modules with existing root model dependencies, disposable in-memory SQLite. Output:
{"reviewed":"bdf2bd6","old_period_before":0.27,"old_period_after":0.0,"today_actual_listing_fee":1.5,"today_ceiling":1,"extra_reservation_accepted":true}
No network, external provider, production data, credentials, persistent finance mutation or paid calls. Reviewed-source boundaries explicit: finance modules exact bdf2bd6; ordinary core model dependencies from coordinator checkout. Reproducer temporary script remains workspace/finance_counterexample.py, outside repository scope.

## Positive evidence and limits
New modelled/unknown operating-cost labelling correctly prevents direct conversion of unobserved cost rows into observed cash claims; cash is explicitly a derived proxy, not bank balance. Same-listing reservation lock and external-entry replay deduplication are useful. Existing tests cover same-period actual replacement, not cross-period/different fee identity; the gaps above remain even with green candidate suites.
Actual CAD fee basis is measured by declared payment entry source; non-CAD assumed FX remains modelled. No independent live payment feed or PostgreSQL concurrency run performed. This review does not certify any requirement or assess entire finance system. Owner of effect-boundary recheck should also address both period/source defects before this candidate claims durable budget protection.

## Confirmed adjacent defect 3: unknown platform-fee cancellation masquerades as observed
Under an explicit controlled measured-sales premise, insert two LedgerEntry fee rows +1/-1 with fees_basis=unknown. Books consumes real rows, fee_basis_summary nets unknown to0, and all_observed returns true because it tests totals. Output: {"unknown_fee_rows":2,"fees_by_basis":{"measured":0.0,"modelled":0.0,"unknown":0.0},"all_figures_observed":true,"cash_reading":"derived_cash_proxy"}.
The new unobserved_operating_rows count protects operating-cost offsets but not platform-fee offsets. Preserve a nonmeasured fee-row count/flag independently of signed sums. This is an inherited adjacent semantic gap, not established as newly introduced by c9e038c. Reproducer patches only source_state to an explicit measured-sales premise; it is a conditional aggregation proof, not real production sales evidence. No broader audit performed.
