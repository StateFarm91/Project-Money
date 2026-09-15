# DECISION_LOG

Consequential decisions, with reasoning, so future sessions do not re-litigate or repeat disproven assumptions.

| # | Date (UTC) | Decision | Why | Reversible? |
|---|---|---|---|---|
| D-001 | 2026-09-15 | Use `StateFarm91/Project-Money` as the single "operating system" repository (state, ledger, research, ops). Product code lives under `products/` unless a product genuinely needs its own repository (e.g. separate deploy target or public open-source distribution), in which case it is linked from `products/README.md`. | A future context must be able to understand the whole business from one place. Splitting repos early adds coordination cost with no benefit. | Yes |
| D-002 | 2026-09-15 | Competition start recorded as 2026-09-15T11:00:07Z. | Execution began in this session. | No (immutable) |
| D-003 | 2026-09-15 | Do not anchor on any prior idea; run a fresh 20+ candidate sweep with live web evidence before building anything. | Directive §4-6; the easiest way to lose is building something nobody wants. | n/a |
| D-004 | 2026-09-15 | Scale research fan-out down to fit the rate-limited compute budget: three lean researchers for the nine remaining lenses; merge, ranking and finalist deep-dives done inline with targeted searches; one adversarial review pass instead of three skeptics per finalist. | LL-001: the first fan-out hit the five-hour usage limit and stalled the mission for ~5 hours. Depth is still adequate for a Day-1 decision because finalist assumptions become experiments with real market feedback anyway. | Yes |
