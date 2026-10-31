# Independent security and integrity review: PHYSFIX-PHOTO delta 9 (`b8d3dee0`)

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `b8d3dee0`. It includes `claude/w4-PHYSFIX` at `e3335a51`, which merges `claude/w4-INTEG8-next` at `0b270ae8`.
- **Delta:** `git diff 33cbfc53..b8d3dee0`. The non-merge code commits are:
  - `4eacedd` (R30–R33);
  - `e3335a5` (combined-tree fixes).

  The other commits in the range (`0b270ae`, `276a95a`, `7746cd4`, `191cbc9`) change only records and docs.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_33cbfc5.md` (R30–R34).
- **Reviewer:** independent. I opened no pull request and pushed only this report and one probe file, to `claude/w4-SECREVIEW-PHYSFIX-b8d3dee`.
- **Date:** 2026-10-31 (UTC).

## Verdict: **DO NOT SHIP**, because of R35 (Medium). The fix is a few lines and fails closed.

R30 is closed in every ordering the brief lists, within one incident's lifetime and across the product's other open halts:

- three or more failures;
- failures interleaved with passing makes;
- two open halts on one product;
- legacy single-release incidents;
- atomic withholding.

It is **not** closed across incident lifetimes. A size-halt signature is reused once its incident is resolved, so a new failure opens a fresh incident with a fresh `measured_releases` list. The lift's "not a release any size halt measured" check reads only *open* incidents. As a result, a passing make of a release that an earlier, already-lifted halt measured wrong (and permanently withheld) is accepted as the evidence for lifting the new halt. I reproduced this end to end (§2, probe P5). It is the same class of defect as R30, the "first failed release escapes the re-release check" problem, moved one step out. The owner prompt states the opposite, so I hold it to the bar that made R30 Medium.

| ID | Severity | Finding | Status |
|---|---|---|---|
| R30 | Medium | a restated halt overwrote `measured_release` | **closed within an incident** (P1–P4, author tests); see R35 |
| **R35** | **Medium** | the lift's "re-released version" check ignores releases measured wrong by *resolved* size halts. A make of a release that an earlier halt measured wrong and withheld lifts a new halt | **open, blocks** |
| R31 | Low → Info | same-geometry confirmation | **closed** as designed. I accept the integrator's decision (§3). Two residual Info notes: R37, R38 |
| R32 | Low | shared mutable `Gauge` | **closed for `vessels`**. `products/texture.py` still aliases module-level `WORSTED`/`CHUNKY` into every CIR (R39, Low, nothing mutates it today) |
| R33 | Info | lift in two sessions | **closed**: one session; an injected mid-withholding failure rolls everything back (P4) |
| R36 | Low | on PostgreSQL, a lift and a concurrent repeat failure of the same signature can lose the appended release (no row lock) | open; does not block |
| R37 | Info | a sample recorded before this delta has no `design_digest`, so R31's refuse-only confirmation is silently skipped for it | does not block |
| R38 | Info | the R31 digest set is this incident's only. Evidence with another *open* halt's failed geometry is not flagged when lifting this incident. That halt still holds, and its own lift asks | does not block |
| b2gates | — | unique `_db()` names | **legitimate**: cause reproduced (§5). No assertion changed |

## 1. R30 verification

The code is in `runtime/release.py` (`_halt_release_on_size`, `measured_releases`, `lift_size_halt`).

**Append-only.** `_halt_release_on_size` reads the open incident with the same signature in the same session and starts from `measured_releases(existing.detail)`. It appends the new entry and passes the whole list to `open_or_restate`. `_restate` does `merged.update(detail)`, so the list it receives replaces the stored one; since that list is always the old list plus one, nothing is dropped. The single `measured_release` field is now pinned to `releases[0]`.

**No other writer.** In `src/`, the only writers of a `physical-size:` incident's `detail` are `_halt_release_on_size` and the lift's resolution. No route, reconcile or triage rewrites it. The lift's resolution copies `failed` into `withheld_releases`. I found no path that truncates or prunes the list *while the incident is open*.

**Probes.** File: `tests/test_secreview_physfix_b8d3dee_probes.py`, run against `b8d3dee0`.

| Probe | Ordering | Result |
|---|---|---|
| P1 | three failures (1.2.0, 1.3.0, 1.4.0, same geometry), each followed by a passing make of that same release | list is `[1.2.0, 1.3.0, 1.4.0]`. A later make of each one is refused even with `same_design_confirmed=True`. A lift on a changed-geometry 1.5.0 withholds all three, with three `gate.release_withheld` rows. **pass** |
| P2 | two open halts on one product (different geometry, so different signatures) | lifting I1 on I2's failed release is refused, naming it. Lifting I1 on a fix leaves I2 open and the product still halted. **pass** |
| P3 | legacy incident (only `measured_release`, no list), then a repeat failure | the list becomes `[legacy, new]`. **pass** |
| P4 | `withholding.record_in` raises on the second of two releases | the incident stays unresolved, no durable audit row is written and no release is withheld. **pass (atomic)** |
| P5 | I1 is lifted (A=1.2.0 withheld), then the fix 1.3.1 fails (I2), then a passing make of A | **I2 lifts on A's make** → R35 |

## 2. R35 (Medium): a release measured wrong by a resolved halt is accepted as lift evidence

**Mechanism.** `open_or_restate` matches only unresolved incidents, so once I1 is lifted, any later failure opens a new incident. That includes a failure under I1's own signature. In `lift_size_halt`, `failed` is this incident's list, and `others` selects `Incident.resolved == False`. Releases recorded in resolved incidents' `withheld_releases`, or withheld with `withholding.PHYSICAL_SIZE_FAILED`, are never consulted.

**Reproduction** (P5; `cd brambleloop && PYTHONPATH=src:tests python tests/test_secreview_physfix_b8d3dee_probes.py`):

1. Certify `market-basket-medium@1.2.0` (A). A full make by tester-1 measures 40 cm wide, which opens size halt I1.
2. Certify `_geometry_changed_medium("1.3.1")` (F). tester-2 makes it at the stated size. The owner lifts I1 on that make, which withholds A permanently.
3. A full make of F by tester `t` measures 40 cm wide, which opens I2 (product halted again).
4. A full make of **A** by tester `t1` passes at the stated size.
5. `lift_size_halt(incident_id=I2, physical_test_id=<step 4>, actor="owner:cc:s", stepped_up=True, …)`

   Observed: `{'version': '1.2.0', 'lifted': True, 'withheld': ['market-basket-medium@1.3.1'], 'same_geometry': False}`. After the lift, `publication_halted` is False.

**Why it matters.**

- The halt is lifted product-wide on evidence about a release that can never publish. A was measured wrong once and is permanently withheld, so its make says nothing about any publishable version.
- `same_geometry` is False even though A's geometry is exactly the one I1 measured wrong. So the owner is not even shown the R31 flag.
- The owner prompt (`_route_conflict_to_owner`) tells the owner the lift "accepts only a full make … of a version no size halt measured". That statement is false here.
- The owner's step-up still gates the action, so this is not a software self-lift. But one of the two invariants the R28 decision promises fails open. That is the same reasoning that made R30 Medium.
- No failed release becomes publishable. A and F both stay withheld. What is broken is the evidence rule.

**Fix (small, fails closed).** In the lift, add both of these to the refused set:

- releases from every *resolved* `physical-size:` incident of the product (`withheld_releases` / `measured_releases`);
- every version of the product withheld with `PHYSICAL_SIZE_FAILED`.

Do the same for the R31 digest set. Add P5 as an asserting test.

## 3. R31: the confirmation path, and the integrator decision

**Path.**

- At intake, `handle_physical_record` stamps `measured.design_digest`.
- The lift computes `same_geometry` against this incident's `design_digest_for_audit` and each listed release's digest.
- `same_geometry` only adds a refusal unless the owner passes `same_design_confirmed`.
- At the HTTP route the flag is `body.get("same_design_confirmed") is True`, so a string `"true"` does not confirm. It sits behind the action's step-up.
- The outcome is recorded in the resolution (`same_design_confirmed`) and in the audit row (`same_geometry`).
- The digest never permits anything: the version and hash checks run regardless (P1 shows confirmation does not rescue a failed release).

The author's test `test_a_lift_on_the_failed_geometry_needs_the_owner_to_confirm_it` covers the refusal and then the confirmed lift. The path is sound.

**Integrator decision** ("a later version sharing geometry with a withheld one is not blocked from certifying; the owner's confirmation at lift covers it"). **I accept it; it is not a defect.**

- The size halt is product-wide and owner-lifted. A same-geometry relabel can only become lift evidence through an explicit, step-up, audited owner confirmation that the earlier measurement was wrong.
- After that, blocking the geometry would override the owner's recorded judgement with a digest, which the R28 decision deliberately removed.
- A *new* failure of that geometry re-halts the whole product.

Residual notes, both Info and neither blocking:

- **R37.** Samples recorded before this delta have no `design_digest`, so R31 is skipped for them. Such rows predate R28's lift action in practice.
- **R38.** The R31 digest set does not include other open halts' failed geometry (P2 note). That other halt still blocks, and its own lift asks for confirmation.

The owner prompt shows "Same geometry as a failed release: YES" but does not name the `same_design_confirmed` field. Only the refusal text names it. That is a UX note.

## 4. R32: shared builder state

- **`products/vessels.py` is fixed.** It uses `replace(COTTON_GAUGE)` / `replace(COASTER_GAUGE)` and stores `dict(vars(...))` in provenance. The author test `test_the_basket_builder_never_shares_its_gauge` passes.
- **`nordic_forest.py`** already copied its gauge.
- **`moment_candidates.py`** gets a new `Gauge` from `gauge_for()` on each call.
- **`garments.py`** passes `g.gauge` from the per-call `GradedSize`.
- **R39 (Low): `products/texture.py` is unchanged.** Lines 135, 223 and 294 pass the module-level `CHUNKY` / `WORSTED` (a mutable `@dataclass Gauge`) into every CIR they build. A grep of `src/` finds no in-place write to any `cir.gauge` attribute (`reengineer` uses `replace`), so this is latent, exactly as R32 was. Fix: `replace(...)` as in vessels. This does not block.

## 5. The b2gates fix

**Claimed cause: confirmed.**

- `Database` sets `PRAGMA journal_mode=WAL` (`core/db.py:113`).
- The old `_db()` named files `d{len(os.listdir(_TMP))}.sqlite`. When an engine is disposed or garbage-collected, SQLite checkpoints and deletes that file's `-wal`/`-shm`, so the directory count falls and a later call can produce the name of a database that still exists.
- I reproduced this with the real `Database`. Three databases, all disposed, then three more gave the names `['d1','d4','d7','d4','d6','d9']`. The second `d4` reopens the earlier file with its rows.

**No assertion weakened.** The b2gates diff touches `_db()` only (docstring plus `uuid4` name). No assertion line changed.

`suite_final_segment.txt` adds `tests/test_physfix.py` in sorted position. That is declaration only.

## 6. R36 (Low): concurrent lift and repeat failure on PostgreSQL

`lift_size_halt` and `_halt_release_on_size` both read the incident with a plain `SELECT` and rewrite `detail` whole. No `FOR UPDATE` is taken, and `signature` is not unique. Under PostgreSQL READ COMMITTED, a repeat failure that reads the open incident before a lift commits, and writes after it, appends its release to an incident that is already resolved:

- no halt is open;
- that release is not withheld.

The opposite order lets the lift overwrite `detail` and drop the appended release.

SQLite WAL is not affected, because the upgrading writer gets `SQLITE_BUSY_SNAPSHOT`. The window is milliseconds and needs an owner action racing a tester record, so this does not block.

Fix: `with_for_update()` on the incident read in both functions, or a re-read under lock before writing.

## 7. Whole branch

I scanned `git diff origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO` for anything at Medium or above beyond R35. I found none:

- No code path except `lift_size_halt` resolves a `physical-size:` incident.
- The lift is reachable only through `physical_size.lift`, behind step-up, with an `owner:cc:` actor check.
- Withholding is `PERMANENT` and `carry_permanent` survives re-certification (author test plus P1).

**R35 is the only blocker.**

## 8. Test runs

Every file was run alone, one at a time, at `b8d3dee0` (`cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`). Two early attempts overlapped by mistake. I stopped both and discarded their results; the table below is from one clean sequential run.

| File | Result |
|---|---|
| `test_physfix` | rc=0, 78s: 44/44 passed |
| `test_physfix_size_lift_http` | rc=0, 5s: 1/1 passed |
| `test_secreview_physfix_adversarial` | rc=0, 8s: 12/12 passed |
| `test_secreview_physfix_42eac69_probes` | rc=0, 7s: 8/8 passed |
| `test_secreview_physfix_89eef1e_probes` | rc=0, 5s: 8/8 passed |
| `test_secreview_physfix_b8d3dee_probes` | rc=0, 14s: P5 FINDING: I2 lifted on a make of 1.2.0 (withheld by I1) -> {'incident': 2, 'physical_test_id': 4, 'slug': 'm |
| `test_w4_b2gates:1` | rc=0, 85s: 12/12 passing |
| `test_w4_b2gates:2` | rc=0, 83s: 12/12 passing |
| `test_w4_b2gates:3` | rc=0, 84s: 12/12 passing |
| `test_w4_resume_runner` | rc=0, 126s: OK   test_without_the_flags_nothing_changes (0.2s) |
| `test_risk_matrix` | rc=0, 99s: OK   test_the_parked_sample_request_is_a_tester_spend_approval_not_owner_crochet |
| `test_physfix_photo_first` | rc=0, 6s: 8/8 passed |
| `test_w4_launchfix` | rc=0, 24s: 32 passed, 0 failed |
| `test_vacuity` | rc=0, 8s: OK   test_the_scan_sees_the_suite |
| `test_first_customer_gate` | rc=0, 17s: 12 passing, 0 failing |
| `test_gates` | rc=0, 3s: OK   test_unsupported_size_claim_is_blocked |
| `test_executor` | rc=0, 21s: OK   test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row |

All exit 0. `test_w4_b2gates` passed 12/12 on all three runs. The b8d3dee probe file exits 0 by design: it prints `FINDING` for P5 (R35) and does not assert, so it can sit in a suite until R35 is fixed. Then P5 should be turned into an asserting test.

