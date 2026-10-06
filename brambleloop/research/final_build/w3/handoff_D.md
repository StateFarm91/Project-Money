# handoff D (wave 3): Laura's Founder/CEO core

Branch `claude/w3-D`. Base `claude/v11-CANON` @ f0c2d12. `claude/visual-investigation` @ 931d4ff
merged in, as the integrator asked (it brings K3, E, G, A, I and D-FB-14). Phase stayed shadow.
There were no paid calls, no network, and no Etsy, Railway or customer effects.

## Interfaces (exported in the first commit, f64c4b2)

- **`brambleloop.laura.identity`** is the canonical identity API. It re-exports `laura.core.identity`:
  - `load(db)` / `current(db)` / `ensure(db)` return the verified record (version, sha256).
  - `genesis()`, `public_profile()` and `voice_lint(text, surface=)`.
  - `amend(db, changes, owner_decision_id=, actor=, reason=)` is owner only.
  - `summary(db)` is the provider contract.
  - Constants: `VISUAL_IDENTITY_ID` (= `visual.canonical.IDENTITY_ID`, now `laura-r2-a42aeac7`; the face is unchanged), `GENESIS_SHA256`, `AUTHORITY`, `CHARTER`, `CONSTITUTION`, `PUBLIC_VOICE`.
- **`brambleloop.laura.executive`**:
  - `tick(db, queue=None, now=None)` returns a report.
  - `summary(db)` is the Command Center provider.
  - `priorities(db, status=, limit=)`.
  - `history(db, limit=, kind=)` returns her decisions.
  - `observe(db)`, `results_wake(db, queue)`, `EXEC_JOB = "laura.executive_tick"`.
- **`brambleloop.laura.core.constitution`**:
  - `review(db, proposal)` returns allow, block or owner_action, with `blocked_by`.
  - `challenge(db, raised_by=finance|product_truth|security, reason=, scope=)`.
  - `resolve_challenge(...)` works only for the raising department or the owner.
  - `open_challenges(db)`.

## Requirements and status

| Requirement | Status | Where |
|---|---|---|
| Canonical identity record: name, Founder/CEO role, charter, authority limits, public voice spec, visual id, truthful-identity rule | COMPLETE | `laura/core/identity.py` |
| Immutable owner-controlled fields; changes only by a recorded owner decision | COMPLETE | Genesis hash is pinned. `laura_identity_versions` is hash-chained and refuses ORM update/delete. `amend` requires `actor="owner"`, a decision listed in `AUTHORISED_IDENTITY_AMENDMENTS` (empty), and that decision in DECISION_LOG. A face change also needs `visual.canonical`'s own list. A raw-SQL tamper raises `IdentityTampered`, which blocks her tick and her constitution. |
| Executive tick: Laura → COO → departments → results → Laura | COMPLETE | `laura/executive/loop.py`. Cadence `laura_executive` runs every 5 min. She is also woken when the COO closes a mission she delegated. |
| Reads company state | COMPLETE | `autonomy.status`, KPI snapshots, owner actions, incidents, defect dead letters, and the finance/slo/learn/seo/ads/visual_rnd providers. A missing provider means UNKNOWN "not built". |
| Durable priorities with reasons and evidence | COMPLETE | `laura_priorities` table. It holds working state, not history. |
| Delegation through the existing COO mission mechanism (GREEN/SAFE only; protected work becomes an owner action) | COMPLETE | `orchestrator._enqueue_mission` / `_raise_approval` are reused unchanged. |
| Honest review with did_no_work | COMPLETE | Reuses `orchestrator.reconcile_missions`. |
| Challenge weak work | COMPLETE | A no-op gets a department review challenge. A failure gets one rework. If that is weak too, it becomes a routed Lesson (no loop). |
| Durable history of real actions only | COMPLETE | Stored in **laura.memory**, operational tier, `decision/<hash>`, per the integrator ruling. It is written by `Principal.laura()` and sourced to the company_timeline event. Public/customer principals are refused. |
| Constitution: Finance / Product Truth / Security can block her; she cannot expand authority | COMPLETE | See the details below. |
| Model independence | COMPLETE | The tick is deterministic and calls no model. `cognition` (env `BRAMBLELOOP_LAURA_MODEL`) is only a label on her decisions. |
| Empty queue → safe useful work | COMPLETE | Takes the departments' own evidence-driven generator candidates, at most 2 per tick. |

How the constitution works:

- **Finance**: `check_spend` (writes `acct_challenges`), paused spend scopes, and Finance challenges.
- **Product Truth**: an unresolved incident that halts publication blocks store, growth, visual and product-design work.
- **Security**: a P0/P1 security-class incident or a Security challenge blocks everything except never-paused departments (F-889 rule). A disabled agent is never routed around.

## Files

- New: `laura/__init__.py` (identical to lane E's), `laura/identity.py`, `laura/core/{__init__,identity,models,constitution,history}.py`, `laura/executive/{__init__,loop,handlers,proof}.py`.
- Shared files lane D owns:
  - `core/db.py` (create_all import)
  - `agents/registry.py`: the `laura` agent (GREEN, CA$0, only `laura.executive_tick`; protected and truth-changing types forbidden), plus the K3 grant `cfo += listing.outcomes`
  - `runtime/worker.py` CADENCES: `laura_executive` 300 s; K3 `listing_outcomes` (cfo, daily)
  - `swarm/orchestrate.py` JOB_BANDS: laura tick and listing.outcomes
  - `autonomy/charters.py`: executive gets the `laura.` prefix and agent
  - `autonomy/handlers.py`: imports the laura handler, results wake, and a WORK_KEYS declaration for `listing.outcomes`

## Tests

PROOF_AND_TESTS_PLACEHOLDER
