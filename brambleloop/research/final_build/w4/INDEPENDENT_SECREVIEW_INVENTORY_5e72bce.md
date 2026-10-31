# Independent delta review — W5-INVENTORY @ 5e72bce

- **Subject:** `git diff d0e523bb..5e72bce8` on `claude/w5-INVENTORY`. Three files: `production_inventory.py`, `test_w5_inventory.py` and `INVENTORY.md` (+327/−62).
- **Prior review:** `INDEPENDENT_SECREVIEW_INVENTORY_d0e523b.md` (H1, M1–M4, surviving mutants M7, M9, M12).
- **Date:** 2026-10-31 (UTC). I reviewed the code itself and used `INVENTORY.md` only as background.
- **Verdict: SHIP.** Every prior finding is fixed at the root. Each has a test that kills the original mutant. Nothing new fails open on a reachable path. The four new LOW items below are test-coverage gaps and a hardening note. None of them can produce a false Ready from data the system writes, so none blocks shipping.

## Suites (one at a time, `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| Suite | Result |
|---|---|
| `test_w5_inventory` | 11/11 PASS |
| `test_route_auth_default_deny` | 8/8 OK |
| `test_w4_fmbatch1_route_audit` | all OK, exit code 0 |
| `test_w4_fmbatch1_retention_guard` | all OK, exit code 0 |
| `test_vacuity` | all OK, exit code 0 |

The container had no dependencies. I installed them with `pip install --require-hashes -r requirements.lock`, then `requirements-test.lock`.

## 1. Prior findings: is each fixed at the root, and does a test discriminate?

I applied each mutant to `production_inventory.py` one at a time and ran `test_w5_inventory`. The runner is at the bottom of this file.

| Prior finding | Fix | Mutant | Result |
|---|---|---|---|
| H1 settled intent ignored | Any `DraftIntent` row closes the gate (mirrors `refuse_if_existing`). `incomplete_on_etsy` adds its own reason. | Exempt `CREATED` again | KILLED |
| | | Drop the `incomplete_on_etsy` reason | KILLED |
| | | Both together | KILLED (state assert: `x-created` Ready) |
| M1 intent reader fails open | `intents_unreadable` is set and turned into a closed reason | `closed.append` → `pass` | KILLED |
| M1 veto reader fails open | Closed reason on exception | Drop the append | KILLED |
| M1 withholding reader fails open | Closed reason on exception | Drop the append | KILLED |
| M1 (any reader) | `closed` feeds `extra` | `extra = []` | KILLED |
| M2 no age limit | `VERDICT_TTL = 24 h` | Remove the TTL | KILLED (`g-old`) |
| M2 replayed `as_of` accepted | `as_of` on the `store.publish` job → UNKNOWN | Remove the check | KILLED (`g-asof`) |
| M3 latest sample did not win | Latest completed test by `(completed_at, id)` decides | Earliest wins | KILLED |
| M3 undated "passed" counted | Undated results are not completed tests | Count undated | KILLED |
| M4 gates row not job-bound | Both rows keyed by `store.publish` job id and paired | Accept an unbound gates row | survived as an **equivalent** mutant: the pairing step still drops job `None`. `g-gunbound` covers the real behaviour. |
| Old M7 (parity, key missing → open) | `is not False` | `is True` | KILLED (`g-nokey`) |
| Old M9 (`live` always PASS) | Tested both ways | Always PASS | KILLED |
| Old M12 (crashed row → Ready) | Fallback is REVISION_REQUIRED, not ready in any tier | Fallback = READY | KILLED |
| Staleness relative to jobs (regression) | unchanged | Drop the `stale` check | KILLED |

## 2. Does the 24 h limit fail closed? **Yes.**

Probes on a fresh DB with the owner gates open (`probe.py` below):

| Case | Result |
|---|---|
| Verdict 24 h 1 m old | `listing_package_completed`, gates UNKNOWN, public not ready |
| Verdict 23 h old (control) | `ready_for_publication` |
| Same 23 h verdict, `now=+2h` | UNKNOWN |
| Gates in job A, parity in job B | UNKNOWN ("different store.publish jobs") |
| Gates row with no `blocks_release` key | FAIL |

Neither member of the pair may be undated:
- if both are undated, `oldest is None` gives UNKNOWN;
- if one is undated, `a.at < changed_at` raises, and the row falls back to Revision required.

`AuditLog.at` is also non-null with a default. The only way to inject `now` is `production_summary(now=)`. Its only caller is the CC builder, which passes nothing, so `now` is the wall clock. Live mode computes a fresh verdict, so the TTL does not apply to it.

## 3. Does the SQL write-spy catch writes? **Yes.**

Mutant N7 adds `UPDATE products SET title = title` inside `derive()` on the engine. That row-preserving UPDATE is invisible to the old row-count check. The spy catches it: `FAIL test_cc_production_requires_owner_session_and_is_read_only: ['UPDATE products SET title = title']`. The spy hooks `before_cursor_execute` on `DB.engine`, so it sees both ORM and Core statements.

## 4. Fail-open, writes, network: **PASS.**

- The diff adds no `enqueue`, HTTP or `urlopen` call, Etsy client or provider call, and no `session.add` or commit in `src/`. The only new `except` branches append closed-gate reasons.
- The `extra` closing reasons apply in both `recorded` and `live` mode.

## 5. `channel_policy` / `channel_eligibility`: **absent.**

`grep -rn` over `src/` and `tests/` `.py` files finds neither name. The only mention is the `INVENTORY.md` note that `channel_policy` was cancelled.

## New findings

### L1 (LOW, hardening) — a future-dated verdict passes the TTL

- **What happens:** `now - oldest > VERDICT_TTL` is negative for a verdict dated in the future, so it passes.
- **Reproduction:** `up_to(db, "p-future", "gates", job_at=NOW-48h, audit_at=NOW+365d)` → `('ready_for_publication', 'PASS', True)`.
- **Why LOW:** `AuditLog.at` defaults to `utcnow`, so this needs clock skew or a hand-inserted row.
- **Fix:** also treat `oldest > now + small skew (e.g. 5 min)` as UNKNOWN.

### L2 (LOW, test gap) — the same-job requirement is enforced but not tested

The code is correct: the split-job probe above returns UNKNOWN. But these mutants survive the suite:

| Mutant | Change |
|---|---|
| N3 | Take the latest gates row from any job |
| N4 | Pair the parity job with gates from any job |

**Fix:** add a fixture with gates in job A and parity in job B, and assert UNKNOWN with the "different store.publish jobs" reason.

### L3 (LOW, test gap) — surviving mutants of the new fixes

| Mutant | Why it is low impact |
|---|---|
| O-M7b: gates row `blocks_release is True` (missing key → open) | The code handles a missing key correctly (probe: FAIL), but only the parity side has a fixture. |
| N2: the TTL uses the newer of the pair (`max`) instead of `min` | The two rows of one job are written seconds apart. |
| N5: the `store.publish` job is not bound to the slug, only to the version | The audit `artifact == slug` still binds it. |

**Fix:** add a `g-gnokey` fixture, and optionally a pair with skewed timestamps.

### L4 (LOW, test precision) — the spy's GET exemption is wider than documented

`INVENTORY.md` says a GET may only write `cc_owner_sessions.last_seen_at`. The test, however, exempts any statement containing the text `cc_owner_sessions`, including an INSERT or DELETE on it.

**Fix:** match `^UPDATE cc_owner_sessions SET last_seen_at` exactly.

### INFO

- The 24 h TTL means that in shadow, products move from "Owner approval pending" to "Listing package completed" (re-evaluation required) a day after the last `store.publish`. `INVENTORY.md` states this. It is the intended fail-closed reading.
- The prior LOW about `quality.reverified` retention is unchanged by design (see `INVENTORY.md`).

## Reproduction harness (not committed; run from `brambleloop/` in a scratch worktree)

- **`mut.py`:** for each `(old, new)` pair, assert `old` occurs once in `production_inventory.py`, then replace it. Run `tests/test_w5_inventory.py`; a non-zero exit means KILLED. Then restore the original.
- **Mutants used:** the rows of the §1 table, plus N1 (TTL ×3: KILLED), N2–N5 (survived, see L2 and L3), N6 (drop stale: KILLED) and N7 (write in `derive`: KILLED by the spy).
- **`probe.py`:** imports `test_w5_inventory as T`. It seeds `T._fresh_db("probe")` with `T.up_to(..., job_at=, audit_at=)` for the §2 cases, then reads `pi.derive(db, now=...)` under `T._Patch()`.
