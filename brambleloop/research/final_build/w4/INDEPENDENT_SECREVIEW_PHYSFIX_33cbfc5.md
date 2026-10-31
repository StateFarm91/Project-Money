# Independent security and integrity review: PHYSFIX-PHOTO delta 8 (`33cbfc53`)

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `33cbfc53`, which includes `claude/w4-PHYSFIX` at `ad07b595`.
- **Delta:** `git diff 8da830dc..33cbfc53`. The non-merge commits are:
  - `6c21366` (R28 integrator decision: every size halt is product-wide, and only the owner lifts it);
  - `ab0bbbf` (the owner lift permanently withholds the failed release, plus the HTTP test);
  - `ad07b59` (test isolation for the shared `Gauge`).
- **Integrator decision under test:** I-B4-SIZE-HALT-PRODUCT-WIDE.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_8da830d.md` (R28).
- **Reviewer:** independent. I opened no pull request and pushed only this report.
- **Date:** 2026-10-31 (UTC).

## Verdict: **DO NOT SHIP**, because of R30 (Medium). The fix is small and fails closed.

**R28 is closed by construction.**

- No code path reads a design digest, content hash or release identity to scope, escape, resolve or lift a size halt.
- `IncidentTracker.publication_halted(slug)` is now `any(halts_publication)` over the product's open incidents.
- `release_scope`, `resolve_halts_disproved_by` and `_HOLD_DIGEST_INTERIM` have been removed from `src/`. One legacy fallback remains: `lift_size_halt` still reads `detail["release_scope"]`, but only to find which release to withhold, never to decide anything.
- The only code that resolves a `physical-size:` incident is `runtime.release.lift_size_halt`, and the only caller of that is the Command Center action `physical_size.lift`, behind step-up.

**R30 is a new hole in the lift itself, not in the halt.** The halt incident is keyed on the design digest, and a repeat failure restates it with `open_or_restate`. That call replaces `detail.measured_release` with the newest failing release. As a result:

- the first release a tester measured wrong drops out of the record;
- that release's own later passing make then satisfies the "re-released version" precondition;
- after the lift it is not withheld, it re-certifies, and `for_publish` gives no size reason against it.

I reproduced this end to end (§2). The owner step-up still gates the lift. But both safeguards the decision promises, "evidence must be a re-release" and "the failed measured release is durably withheld", fail open, and the owner prompt tells the owner the code has checked the first one. That meets the bar earlier rounds set for Medium.

| ID | Severity | Finding | Status |
|---|---|---|---|
| R28 | Medium | `make: N` versus N components moved the digest and escaped a scoped halt | **closed**: no digest scopes or lifts any halt |
| **R30** | **Medium** | a restated size halt overwrites `measured_release`, so the first failed release escapes the re-release check and the permanent withholding | **open, blocks** |
| R31 | Low | "re-released version" means only a different version string. A pure relabel (identical geometry) qualifies, and after the lift a later version that reverts to the failed geometry certifies freely | open; does not block (the owner decides; see the recommendation) |
| R32 | Low | the shared module-level `Gauge` in `products/vessels` (and `vars(COTTON_GAUGE)` stored in provenance) is aliased into every built CIR. No production path mutates it today | open; fix in the builder soon; does not block |
| R33 | Info | the lift's two sessions (validate, then write) are not one transaction. A concurrent double lift could write duplicate audit and withholding rows, which is harmless and idempotent | does not block |
| R34 | Info | the 42eac69/89eef1e probe files still pass and are still valid regressions, but most now hold trivially because every halt is product-wide. The 89eef1e digest-equality tests now guard audit display only | does not block |

## 1. Fail-open audit (R28 closure)

Every reader of a size halt is listed below. None reads a digest.

- **`pipeline.handle_certify`:** `tracker.publication_halted(cir.slug)`, product-wide, no argument. The `_incoming_design` helper has been removed.
- **`release.handle_physical_record`:** software never lifts a halt. `lifted` is always `[]`. A passing independent full make while any `physical-size:` halt is open routes to the owner (`physical_size_conflict:`). The digest is computed only for the incident signature and `design_digest_for_audit`.
- **`release_gates.for_publish`:** this covers publish, draft (`_release_gates(stage="draft")`) and `store.activate`. All three read open `halts_publication` incidents by `product_slug` (`staleness`, `_halting_other_than_staleness`), with no digest. They also read the new permanent withholding from the certificate and, independently, from the durable `gate.release_withheld` audit rows.
- **`retry_hold_reason`, `release_recovery`, briefing and executive loop:** all product-wide on `halts_publication`, and none resolves incidents.
- **Generic incident resolvers:**
  - `incident_lifecycle.reconcile`, `resolve_signatures` and `close_recovered_cadences`: none is ever called with a `physical-size` prefix.
  - The duplicate fold keeps one open row per signature, so the halt survives.
  - `incident.acknowledge` resolves nothing.
  - `ops.retention` does not prune incidents.
- **Withholding:**
  - `withholding.record(..., reason=None)` is refused for PERMANENT kinds.
  - `reconcile` and `current` only touch the veto and standards kinds.
  - Every `PatternVersion.certificate` writer is either `_persist_release`, which now calls `carry_permanent`, or `withholding.record_in`. The other `certificate =` writers are on `ListingSearchProfile`.

Result: **no path lifts or bypasses a size halt without the owner action.** The remaining problem is inside that action (R30).

## 2. R30 (Medium): restated halt loses the first failed release

**Cause.** `_halt_release_on_size` opens a P1 incident with signature `physical-size:<slug>:<design_digest[:16]>`. A second failing sample of the same design under another version, a relabel or a cosmetic retitle has the same digest, so it calls `open_or_restate` → `_restate`. That function does `merged.update(detail)`, and `detail.measured_release` (and `physical_test_id`) become the *latest* failing release. `lift_size_halt` then checks the evidence against, and withholds, only that latest release.

**Reproduction** (`/tmp/probe/probe_r30.py`; uses the `test_physfix` fixtures):

```python
import test_physfix as T
from brambleloop.gates.incidents import IncidentTracker
from brambleloop.runtime import release as R
db = T._db()
v1 = T._basket_medium(); T._certify(db, v1)                              # 1.2.0
T._run(db, "physical.record", T._inputs(v1, scope="full_make", holds_shape=True,
       measured_width_cm=40.0))                                          # fails -> halt, measured 1.2.0
relabel = T._basket_medium(); relabel.version = "1.3.0"
T._certify(db, relabel)                                                  # halted, but now "examined"
T._run(db, "physical.record", T._inputs(relabel, scope="full_make", holds_shape=True,
       tester_ref="tester-2", measured_width_cm=40.0,
       content_hash=R._content_hash_of(relabel)))                        # fails -> restates, measured 1.3.0
good = T._run(db, "physical.record", T._inputs(v1, scope="full_make", holds_shape=True,
       tester_ref="tester-3", content_hash=R._content_hash_of(v1))).outputs["physical_test_id"]
inc = [i for i in IncidentTracker(db).open_incidents(v1.slug)][0]
R.lift_size_halt(db, incident_id=inc.id, physical_test_id=good, actor="owner:cc:s",
                 stepped_up=True, reason="looks fine")
```

Observed at `33cbfc53`:

```
open size halts: [(1, '1.3.0')]
passing sample of 1.2.0 row 3 passed True
LIFTED: {..., 'version': '1.2.0', 'lifted': True, 'withheld': 'market-basket-medium@1.3.0'}
halted now: False
size-withheld reasons for 1.2.0 []
size-withheld reasons for 1.3.0 True
re-certify 1.2.0 granted: True halted: None
```

`market-basket-medium@1.2.0` was measured at the wrong size by tester-1, yet it:

- was accepted as the "re-released version" evidence;
- is not withheld;
- re-certifies, with `for_publish` raising no size reason.

The owner prompt (`_route_conflict_to_owner`) says "If 1.2.0 is a re-released version…", and the code's check then confirms it, so the owner is misled by the very safeguard meant to protect them.

**Fix (fails closed, no digest needed to decide):**

1. On restate, *append* to `detail.measured_releases` (a list of `{version, content_hash, physical_test_id}`) instead of overwriting it. Keep `measured_release` as the first entry, for legacy readers.
2. In `lift_size_halt`, refuse if the sample's `version` or `content_hash` matches *any* measured release.
3. Withhold *every* measured release, in the same transaction, with one durable `gate.release_withheld` row each.
4. Also refuse when another open `physical-size:` incident of the product measured the sample's version.
5. Add a regression test of exactly the sequence above.

## 3. Lift preconditions (item 2)

| Attempt | Result |
|---|---|
| Same version, different hash (retitle under the failed version) | refused (`row.version == halted.version`), but see R30 for a version that failed *second* |
| A different version that is a pure relabel (identical geometry) | **accepted**. `content_hash` is `_release_hash` over the whole CIR, which includes the version, so "different content hash" adds nothing to "different version" (R31) |
| Owner-made sample | refused (`owner_made`, `tester_ref == "owner"`, and `independent_agreement` returns None for owner) |
| Sample recorded before the halt | refused (`completed_at` is the server-side `assessed_at`, which an operator cannot set; checked `<= inc.at`) |
| Swatch or partial (component) make | refused (`evidence_class`, `whole_pattern`, `scope == swatch`, `passed`) |
| A tester with no independent, qualified agreement | refused (`independent_agreement`). Independence is evaluated at lift time, not at sample time (Info) |
| No owner session, or the ops bearer token | 401 (HTTP test) |
| Missing CSRF | 403 `CSRF` (my probe) |
| Stale timestamp | 400 `STALE_REQUEST` (my probe) |
| Replayed nonce, after a refused request or after a success | 409 `REPLAY`; the halt is unchanged (my probe) |
| Expired step-up | 403 `STEP_UP_REQUIRED` (HTTP test) |
| No reason | 409 (HTTP test) |
| Direct in-process call | `actor` must start with `owner:cc:` and `stepped_up is True`. The only caller is the CC route. This is defence in depth only, the same pattern as the other owner actions |

**Atomicity.** The resolution, the permanent withholding (`record_in`, same session), the durable audit row and the lift audit row are written in one session, so they commit together or not at all. The evidence was validated in an earlier session; the second session re-checks only `resolved` (R33, Info).

**Escapes from the withholding:**

- **Re-certifying the failed version under a new content hash:** blocked. `carry_permanent` carries the withholding over, the durable row is keyed `slug@version`, and the test covers it.
- **Retention:** the row survives, because the action is classed `lifetime_total` (covered by the test).
- **Clearing the kind:** refused.
- **Bumping the version with identical content:** **not blocked.** After a lift, a v1.4.0 with v1.2.0's geometry certifies and publishes. Nothing re-halts it until a new failing sample arrives (R31).

**Recommendation for R31 (optional, fails closed):** use `design_digest_for_audit` only to *refuse*, never to permit:

- refuse a lift whose evidence has the halted digest unless the owner sets an explicit `same_design_confirmed` flag;
- block certification of a version whose digest equals a withheld release's digest.

The digest can only add refusals here, so a digest instability (R1–R29) can never lift anything. At minimum, show "same geometry as the failed release: yes/no" in the owner prompt.

## 4. Withholding (item 3)

- `physical_size_failed` is in `PERMANENT` and in `BUILD_BLOCKING`, so `blocks_build` is True and the build/draft summary carries it.
- It cannot be cleared (`record_in` refuses `reason=None`).
- `for_publish` refuses it from the certificate or from the durable audit row.
- It never blocks the corrected release. It is keyed on the failed `slug@version` only, and the test asserts the corrected 1.3.1 certifies with no size reason.

Caveat: the draft and build stages read only the certificate summary, not the durable row. That is acceptable, because `for_publish` (publish and activate) reads both, and every certificate writer carries the kind over.

## 5. Shared mutable `Gauge` (item 5): R32, Low, fix soon, not blocking

- `products/vessels.py:30-31` binds `COTTON_GAUGE` and `COASTER_GAUGE` once at import. `build_basket` and `build_coasters` put the *same object* in every CIR they build (`gauge=COTTON_GAUGE`), and they also store `vars(COTTON_GAUGE)`, which is the live `__dict__`, inside the CIR's provenance metadata.
- A mutation of `cir.gauge.<field>`, or of that provenance dict, on any built basket therefore changes the gauge of every later basket built in the process, including its stated gauge, its stitch counts and its digest.
- **Production exposure today:** none found.
  - `grep` over `src/` shows no in-place assignment to any `*.gauge.<field>` and no `setattr` on a gauge.
  - `learn/gauge.py` uses `dataclasses.replace`, which makes a copy.
  - Worker jobs rebuild CIRs with `CIR.from_dict` (`model.py:406`, which creates a fresh `Gauge`).
  - The direct callers of the builders are `launch0.cir_for` and its maps, plus `teardown/proof_run`, and they read only.
- The risk is latent but real for a long-lived worker, because the first future in-place edit corrupts every later build silently, and only the test was fixed.
- **Fix in the builder** before more callers appear (a one-line change each): `gauge=replace(COTTON_GAUGE)` and `"gauge": dict(vars(COTTON_GAUGE))`, or make `Gauge` frozen. This does not block shipping.

## 6. Tests (item 4)

- **`test_physfix_size_lift_http`** really goes through `POST /api/cc/actions/physical_size.lift`. It uses `TestClient(main.app)`, a real login, CSRF, a nonce and a timestamp, with the step-up expired by editing `OwnerSession.stepup_until`. It asserts the 401, 403, 409 and 200 responses, the `cc.owner_action.physical_size.lift` audit row, the resolution and the withholding.
  - Missing cases: CSRF, stale timestamp and replay. I probed those and they pass.
  - Not covered by any test: R30.
- **Probe files:** both still pass and are still valid regressions (R34).

### Test runs (at `33cbfc53`, from the hash-pinned `requirements.lock` and `requirements-test.lock`)

RESULTS_PLACEHOLDER

## 7. Shipping

**One finding at Medium or above blocks shipping: R30.** Fix it as described in §2, by accumulating every measured release, refusing evidence of any of them and withholding all of them, and add the regression test. R31 to R34 do not block. R32 should be fixed in the builder in the next change.
