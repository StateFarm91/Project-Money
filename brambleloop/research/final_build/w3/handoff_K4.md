# Handoff: wave-3 cluster lane K4 (launch verdict, demand capture and visibility view)

Base: `origin/claude/visual-investigation` @ 3f1a273. Branch: `claude/w3-K4`.
Cluster source: `CLOSURE_f0c2d12.md` row K4 (F-275 F-276 F-281 F-286 F-287 F-288 F-289 F-300).

## Key finding F-300, now closed

**Before:** a phase change did not require `readiness.ready`. A move from shadow to staging accepted a cited `launch.assessed` row even when that row said `ready=false`. From limited production up, the move only needed some *past* row that said ready (up to 7 days old).

**Now:** `core.phase.record_transition` evaluates the launch verdict live, at the moment of transition, for **every** move up past shadow. It uses `launch.readiness.transition_verdict`, which covers:
- the six questions;
- every other hard gate;
- the off-device autonomy proof (#195);
- the F-275 demand-capture plan.

The move is refused unless `ready is True`. It also fails closed: an evaluator that raises, or returns a non-dict, or returns a truthy value that is not `True`, refuses the move.

The compact verdict, including the evaluator's name, is sealed into the chained row as `readiness_at_transition`. Editing that field breaks the chain.

What did not change:
- **Owner authority** (`opsauth.check`), one-step-at-a-time, cited evidence refs (D4) and the chain checks all still run first, and unchanged. A malformed request never reaches the readiness evaluation.
- **Concurrency guard.** The evaluation runs outside the write session. The chain is re-read afterwards, and the move is refused if the recorded phase changed in the meantime.
- **Rollback.** A move down, including the rebase to shadow over a broken chain, **never** evaluates readiness.
- **The `phase` requirement is excluded**, and this is recorded on the verdict. It means "the phase allows publishing", which is what the transition itself decides.

## Rows

| Row | Status | Evidence (test in `tests/test_w3_k4_launch_verdict.py`) | Runtime consumer |
|---|---|---|---|
| F-300 | COMPLETE | `test_F300_*` (7 tests, including the real live evaluation refusing shadow→staging, every step, fail-closed, authority first, rollback never needing readiness, the verdict sealed in the chain, a phase change during evaluation) and `test_routes_*` | `app/phase_api.py` POST `/api/owner/phase/transition` → `core.phase.record_transition` → `launch.readiness.transition_verdict`. `launch.readiness` handler (`runtime/release.py`) records `questions` on `launch.assessed`. `launch/packet.py` renders them. |
| F-275 | COMPLETE | `test_F275_*` | `launch.demand.capture_plan`, a hard part of `transition_verdict` (it gates the phase change); visibility view |
| F-276 | COMPLETE | `test_F276_*` | `launch.demand.christmas_checkpoints` → visibility `seasonal_readiness` |
| F-281 | COMPLETE | `test_F281_*` | `launch.demand.learning_plan`. `record_due_reviews` is called by the daily `launch.readiness` handler and writes `launch.learning_review` rows. |
| F-286 | COMPLETE | `test_F286_*` | `launch.success.verdict` → visibility `launch_success` |
| F-287 | COMPLETE (owner route). Command Center card pending lane F wiring. | `test_F289_F287_*`, `test_routes_*` | GET `/api/owner/phase/visibility` (operator-only), `launch.visibility.summary` (provider contract) |
| F-288 | COMPLETE | `test_F288_*` (2) | `launch.recommendations.from_stats` → visibility `recommendations` |
| F-289 | COMPLETE | `test_F289_F287_*` | The ingest label had already been fixed (`finance.sources`). The visibility `traffic_sources` table shows four channels plus `unattributed`, never blended. |

## Files

New:
- `launch/demand.py`
- `launch/recommendations.py`
- `launch/success.py`
- `launch/visibility.py`
- `tests/test_w3_k4_launch_verdict.py` (16 tests)

Changed:
- `core/phase.py`
- `app/phase_api.py` (GET `/verdict` and `/visibility`)
- `launch/readiness.py` (`QUESTIONS`, `questions()`, `LaunchAssessment.questions`, `transition_verdict`, GRADUATION text)
- `launch/packet.py`
- `tests/phase_fixture.py` (`synthetic_readiness`)
- `tests/test_rc1_auth.py` and `tests/test_fb4_launch.py`: upward fixtures now pass the synthetic verdict. No assertion was weakened.

Small edits outside the owned set (neither file is in the brief's shared table):
- `runtime/release.py`: adds `questions` and `learning_reviews_recorded` to the `launch.assessed` detail.
- `app/security.py`: adds the two new GETs to `OPERATOR_GET_ROUTES`. This only tightens access.

## Tests run (no full suite)

| Test file | Result |
|---|---|
| `test_w3_k4_launch_verdict` | 16/16 |
| `test_rc1_auth` | 11/11 |
| `test_fb4_launch` | 9/9 |
| `test_route_auth_default_deny` | 7/7 |

I also ran 18 related test files one at a time; every one passed except `test_launch`:

- **Passed:** `rc1_own_packet`, `rc1_own_closer`, `access`, `cert_growth_ops`, `etsy_readback_observe` (37), `publish_execution_gate`, `cert_publish_gates`, `r2_product_client_grant`, `r2_product_listing_writes`, `draft_creation_durability` (6), `draft_intent_precreate_refusal`, `etsy`, `originality_runtime`, `search_hero_publish` (4), `cert_commerce` (14), `customer_data_auth` (9), `w3_final_master_gate`, `fb4_ops`, `storefront_fb4`.
- **`test_launch`:** `test_a_company_that_has_done_its_half_is_only_blocked_on_people` fails, but it fails the same way on the unmodified base 3f1a273, so this lane did not introduce it. The failing requirements are `listing_photography`, `opening_grid`, `storefront_preview` and `final_master_closure`.
- **One mid-run failure, explained.** `test_the_photography_requirement_reads_the_same_source_as_the_coverage_endpoint` failed once because I edited `readiness.py` while that run was in progress, so `inspect.getsource` read lines that had shifted. It passes on a re-run.

## Runtime proof

`research/final_build/w3/evidence/k4_runtime_proof.json`, produced on a fresh, hermetic SQLite database:
- The real GET `/verdict` shows each of the six questions failing, with named keys.
- POST shadow→staging returns **409**, naming the failing questions.
- The visibility summary is UNKNOWN, with its reason.

## WIRING REQUEST (lane F, `app/command_center/providers.py`)

Add `"visibility": ("brambleloop.launch.visibility", "summary"),` to `PROVIDERS`. It follows the `summary(db)` contract:
- returns `status`, `as_of`, `basis`, `items` and `sources`;
- when passed a bare Session it raises AttributeError, so the Command Center retries with the facade;
- `detail` carries the full view.

## Not verified / open

- **No live data.** Every section reads UNMEASURED or UNKNOWN until a real Etsy Stats export and live listings exist.
- **Thresholds are borrowed.** The CTR and conversion cut-offs are `growth.portfolio`'s category starting points; they were not tuned here.
- **Ads checkpoint.** The Christmas `ads_learning` checkpoint reads NOT_AUTHORISED while no owner ads ceiling exists.
