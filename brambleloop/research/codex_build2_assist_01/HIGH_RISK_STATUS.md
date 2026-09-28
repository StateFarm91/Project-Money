# High-risk status map

Claude head: 2e66b3a44cf87fb6d99d10f136148899b4177877. Independent finding labels, never requirement certification. Full evidence and caveats: [RECONCILIATION.md](RECONCILIATION.md).

| Owner priority | Finding verdicts |
|---|---|
| C-65 reopened rows / false closure | CB2-P01: FIXED; CB2-P02: STILL PRESENT; CB2-P03: FIXED |
| Orders refunds, late/partial updates | CB2-O01: STILL PRESENT |
| Unpaid/canceled receipts | CB2-O02: STILL PRESENT |
| Historical sale-version attribution | CB2-O03: STILL PRESENT |
| Transaction crash/recovery | CB2-O05: STILL PRESENT |
| Acquisition attribution | CB2-O06: STILL PRESENT |
| Negative contribution | CB2-O07: STILL PRESENT |
| Growth repeated steering | CB2-G01: FIXED |
| Priority-band escape | CB2-G02: STILL PRESENT |
| Growth ↔ Platform scoped rebuild | CB2-G03: FIXED; CB2-P10: STILL PRESENT |
| Test-seeded fields without producers | CB2-G04: STILL PRESENT; CB2-X04: STILL PRESENT |
| Improve rollback durability | CB2-M01: CHANGED — REAUDIT REQUIRED |
| Stale replay represented as fresh | CB2-M03: CHANGED — REAUDIT REQUIRED |
| Multi-worker replay assumptions | CB2-M02: CHANGED — REAUDIT REQUIRED; CB2-P09: BLOCKED FROM DETERMINING |
| Intel A→B→B policy bypass | CB2-I01: CHANGED — REAUDIT REQUIRED |
| Proxy top-decile/strength | CB2-I02: CHANGED — REAUDIT REQUIRED |
| Swatch vs finished-product evidence | CB2-I03: CHANGED — REAUDIT REQUIRED |
| Physical photo bytes/rights/review/publication/impact | CB2-I04: CHANGED — REAUDIT REQUIRED; CB2-I05: CHANGED — REAUDIT REQUIRED |
| Seller geography vs buyer market | CB2-I06: CHANGED — REAUDIT REQUIRED |
| Drift recovery when evidence disappears | CB2-I07: CHANGED — REAUDIT REQUIRED |
| Design judgement producer | CB2-D01: CHANGED — REAUDIT REQUIRED |
| Exact originating-gap provenance | CB2-D03: STILL PRESENT |
| Artifact mutation retains stale approval | CB2-P06: STILL PRESENT; CB2-D08: STILL PRESENT |
| Execution-time protected gates | CB2-G11: BLOCKED FROM DETERMINING; CB2-M10: CHANGED — REAUDIT REQUIRED; CB2-X03: CHANGED — REAUDIT REQUIRED |
