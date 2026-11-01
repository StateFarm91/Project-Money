# INDEPENDENT SECREVIEW — PHYSFIX R40–R42 (commit 43021c1e)

- Commit under review: `43021c1e` on `claude/w4-PHYSFIX-R40`. Diffed against its parent, `e43eeafe`.
- Reviewer: an independent security and correctness review. Read-only: none of the code under review was changed.
- Date: 2026-11-01 (UTC)
- Scope: `runtime/release.py` (`_lock_size_signature`, `_halt_release_on_size`, `lift_size_halt`), `products/builder.py` (copies of the seams) and the two new tests in `tests/test_physfix.py`. Context: PHYSFIX.md §21 and decision I-B4-SIZE-HALT-PRODUCT-WIDE.

## Verdict: **SHIP**

R40 is closed at the root on PostgreSQL. R41 and R42 are closed. I found no fail-open path, no relaxed gate and no weakened test: the diff only adds lines to tests. Two coverage gaps are left, both Low. Neither is a defect in the code that ships, and my probes cover both.

## Findings

| ID | Severity | Summary |
|---|---|---|
| R43 | Low (test gap) | The suite has no test that a lift writes no duplicate rows. If the `entry["durable"]` dedupe is removed, a second lift writes a second durable `gate.release_withheld` row for every earlier failed release, and all 48 tests still pass. The code is correct today, as probe P1 shows. |
| R44 | Low (test gap) | Nothing in the suite would notice if the signature lock call were removed. The lock is a no-op on SQLite, and the new test only calls `_lock_size_signature` directly, so deleting the call from `_halt_release_on_size` leaves the suite green. The code is correct today: probe P2 shows the lock is taken before the `FOR UPDATE` read, with a stable signed int4 key. |
| R45 | Info | The `withheld` list that a lift returns, and its audit row, leave out any version whose durable row already existed but whose stored certificate record was missing and has just been repaired. The repair is still written. Only the report is incomplete. |
| R46 | Info (existing, now affects writes) | `failed_releases_ever` reads durable rows with `AuditLog.artifact.like(f"{slug}@%")` and has no exact `startswith` check. `_` or `%` in a slug would match another product's rows. Since (a), a match does more than refuse evidence: it can mark another product's version as already durable, so no durable row is written for this product, though the stored record still is. It can also add a stored withholding to a same-numbered version of this product, which over-withholds (fail-closed). No catalogue slug contains `_` or `%` (0 of 11), so nothing is exploitable today. Suggested fix: add `a.artifact.split("@",1)[0] == slug`, as `incident_lifecycle.reconcile` already does. |
| R47 | Info | A measured release with no `version` is skipped. Before this commit it was written as the useless `slug@None`, so this is not a regression. `_halt_release_on_size` always records a version (the default is `1.0.0`), so this only matters for a row that has been tampered with. Withholding is keyed by version, and the content hash is still refused as lift evidence. |

## Check 1: is R40 closed at the root?

**(a) The lift.** `by_version` now merges this incident's `failed` list with every record `failed_releases_ever` returns. Those records come from three places: durable rows, stored withholdings, and every `physical-size:` incident of the product, open or resolved, including `measured_releases`, the legacy fields and `withheld_releases`. I went through each route a failed release could take:

- **A folded duplicate.** `close_duplicates` resolves the duplicate and keeps its `detail.measured_releases`. The incident scan reads resolved rows too, so the release is withheld. The new test covers this, and mutation M1 fails it.
- **A resolved incident.** Only two routes resolve a size halt. The lift writes durable rows and `withheld_releases`. The fold is covered above. `reconcile` and `resolve_signatures` are never called with a `physical-size:` prefix or signature; I grepped every caller in `src/`.
- **A release with no version.** See R47. It is not reachable through the handler.
- **A re-certified release.** Withholding is keyed by `slug@version`. `carry_permanent` keeps `physical_size_failed` through a re-certification, and `release_gates` also reads `durable_reasons`. Probe P1 re-certifies a withheld release and it stays withheld.
- **A release that was never stored.** `record_in` returns `recorded: False`, but the durable row is still written. The gate reads durable rows, so the version is withheld if it is ever stored.

**(b) The lock.** `pg_advisory_xact_lock(734543621, k)` uses the two-int4 form, with `k` taken from the first 4 bytes of the signature's sha256, read as signed. Every other advisory lock in `src/` uses the single-bigint form: OWNER_QUEUE_LOCK 734543617, ledger 734543611, listing_costs 734543609, ads_readiness 284191002, anthropic, the lane lock 0x6C616E65, and the session-level `pg_try_advisory_lock` in etsy_exercise. PostgreSQL keeps the one-key and two-key spaces apart, so none of them can collide with the new lock. Two size signatures can share a 32-bit hash; that only serialises two unrelated failures, which is safe. The lock is taken in the same session and before the `FOR UPDATE` read. `db.session()` commits once at the end and `open_or_restate` only flushes, so the lock is held until the insert commits. Probe P2 checks the order and the key.

Two races are left, both safe. A concurrent first failure against a lift on the same signature waits on the row lock, re-evaluates `resolved == False` and inserts a new open halt, so the product stays halted. A failure on a different design opens its own halt. SQLite does not serialise any of this, and the R42 comments now say so. Production is PostgreSQL.

## Check 2: over-withholding and idempotency

- **Over-withholding.** Probe P1 checks that the passing re-release (1.3.1), a certified version that was never measured (1.4.0) and the second lift's evidence (1.6.0) are not withheld after two lifts. All three entry sources hold only versions that failed sizing; the exception is R46's LIKE wildcard, which does not apply to any current slug.
- **Idempotency.** After two lifts there is exactly one durable row per failed version (1.2.0, 1.2.9, 1.5.0), and the second lift reports only `1.5.0`. With the dedupe removed (mutation M4) the earlier versions get 2 rows each, and probe P1 catches it.

## Check 3: R41 and identity

`Seam` is a non-frozen `@dataclass` whose fields are all immutable (str, enum, int, bool, None), so the shallow `dataclasses.replace` is a full copy. Equality is by field, and the copies compare equal, as the new test asserts. I grepped `src/` and found no comparison of a seam by identity (`is`, or `id()`). `test_products_adversarial.py` passes.

## Check 4: mutation results

Every mutation was applied by `/tmp/rev/mutate.py`, which restores the file in a `finally` block. `git status` was clean after every run.

| Mutation | test_physfix.py (48 tests) | Reviewer probes |
|---|---|---|
| M1: revert (a) (`for r in failed:` only) | **FAIL**: test_a_folded_duplicate… (`withheld` = only 1.2.0) | **FAIL** P1 |
| M2: drop the `_lock_size_signature` call | pass (not caught, R44) | **FAIL** P2 (`[('read', None)]`, no lock) |
| M3: share the seams again (`list(design.assembly)`) | **FAIL**: test_the_catalogue_builder_never_shares_its_seams (cottage-wall-hanging) | n/a |
| M4: no durable dedupe | pass (not caught, R43) | **FAIL** P1 (two rows each for 1.2.0 and 1.2.9) |
| M5: no stored-record dedupe | pass | pass (harmless: `record_in` is idempotent apart from the reason text) |

## Check 5: fail-open, relaxed gates, weakened tests

- The diff removes no assertion and no test.
- No refusal condition in `lift_size_halt` changed. The only change is that the withholding loop now covers more versions.
- The lock is a no-op on SQLite, the same as the existing `FOR UPDATE`, and the comments now say so.

I found no new fail-open path.

## Test results

All test files were run one at a time from `brambleloop/` with `PYTHONPATH=src:tests python tests/<f>`, at commit 43021c1e.

| File | Result |
|---|---|
| test_physfix.py | 48/48 passed (exit 0) |
| test_secreview_physfix_adversarial.py | 12/12 passed (exit 0) |
| test_secreview_physfix_42eac69_probes.py | 8/8 passed (exit 0) |
| test_secreview_physfix_89eef1e_probes.py | 8/8 passed (exit 0) |
| test_physfix_size_lift_http.py | 1/1 passed (exit 0) |
| test_products_adversarial.py | all OK (exit 0) |
| test_vacuity.py | all OK (exit 0) |
| reviewer probes (P1, P2) | 2/2 passed |

## Repro

```
cd brambleloop && pip install -r requirements.txt
PYTHONPATH=src:tests python /tmp/rev/probes.py          # the probes in the appendix
python3 /tmp/rev/mutate.py M4_no_durable_dedupe tests/test_physfix.py   # R43: stays green
python3 /tmp/rev/mutate.py M2_drop_lock tests/test_physfix.py           # R44: stays green
```

Recommendation, not blocking: add probes P1 and P2 to `test_physfix.py` to close R43 and R44, and add the exact slug check from R46.

## Appendix: reviewer probes (`/tmp/rev/probes.py`)

```python
"""Reviewer probes for 43021c1e (not committed to the code under review)."""
import sys, collections
from unittest import mock
sys.argv = ["x"]
import test_physfix as T
from test_physfix import _db, _certify, _run, _inputs, _basket_medium, _geometry_changed_medium, _size_withheld
from sqlalchemy import select
from brambleloop.core.models import Incident, AuditLog
from brambleloop.publish import withholding
from brambleloop.runtime import release as R


def _folded_then_lifted():
    db = _db()
    T.test_a_folded_duplicate_halt_still_has_its_releases_withheld_after_a_lift.__wrapped__ if False else None
    # replay the commit's scenario, returning db
    from brambleloop.ops import incident_lifecycle
    a = _basket_medium(); _certify(db, a)
    a2 = _basket_medium(); a2.version = "1.2.9"; _certify(db, a2)
    _run(db, "physical.record", _inputs(a, scope="full_make", holds_shape=True, measured_width_cm=40.0))
    with db.session() as s:
        i1 = s.scalar(select(Incident).where(Incident.signature.like("physical-size:%")))
        sig, det, i1_id = i1.signature, dict(i1.detail), i1.id
        e = dict(det["measured_releases"][0]); e.update(version=a2.version, content_hash=R._content_hash_of(a2))
        s.add(Incident(severity="P1", signature=sig, summary="dup", product_slug=a.slug,
                       halts_publication=True, detail={**det, "measured_releases": [e]}))
    with db.session() as s:
        incident_lifecycle.hygiene(s)
    b = _geometry_changed_medium("1.3.1"); _certify(db, b)
    job = _run(db, "physical.record", _inputs(b, scope="full_make", holds_shape=True, tester_ref="tester-2",
                                              content_hash=R._content_hash_of(b)))
    out = R.lift_size_halt(db, incident_id=i1_id, physical_test_id=job.outputs["physical_test_id"],
                           actor="owner:cc:s", stepped_up=True, reason="re-made")
    return db, a, a2, b, out


def _durable_counts(db):
    with db.session() as s:
        return collections.Counter(r.artifact for r in s.scalars(select(AuditLog).where(
            AuditLog.action == withholding.DURABLE_AUDIT)))


def probe_repeat_lift_is_idempotent_and_never_over_withholds():
    db, a, a2, b, out1 = _folded_then_lifted()
    never = _geometry_changed_medium("1.4.0"); never.components[0].rows.append(
        __import__("copy").deepcopy(never.components[0].rows[-1])); never.components[0].rows[-1].index += 1
    _certify(db, never)
    assert not _size_withheld(db, b), "the passing re-release b was withheld (over-withholding)"
    assert not _size_withheld(db, never), "a never-measured release was withheld"
    # second, independent halt: c fails, then lift on d
    c = _geometry_changed_medium("1.5.0")
    for _ in range(2):
        c.components[0].rows.append(__import__("copy").deepcopy(c.components[0].rows[-1])); c.components[0].rows[-1].index += 1
    _certify(db, c)
    _run(db, "physical.record", _inputs(c, scope="full_make", holds_shape=True, measured_width_cm=40.0, tester_ref="tester-3"))
    with db.session() as s:
        opened = [i.id for i in s.scalars(select(Incident).where(Incident.signature.like("physical-size:%"),
                                                                 Incident.resolved == False))]
    assert len(opened) == 1, opened
    d = _geometry_changed_medium("1.6.0")
    for _ in range(3):
        d.components[0].rows.append(__import__("copy").deepcopy(d.components[0].rows[-1])); d.components[0].rows[-1].index += 1
    _certify(db, d)
    job = _run(db, "physical.record", _inputs(d, scope="full_make", holds_shape=True, tester_ref="t1",
                                              content_hash=R._content_hash_of(d)))
    out2 = R.lift_size_halt(db, incident_id=opened[0], physical_test_id=job.outputs["physical_test_id"],
                            actor="owner:cc:s", stepped_up=True, reason="re-made", same_design_confirmed=True)
    counts = _durable_counts(db)
    assert all(v == 1 for v in counts.values()), counts
    assert set(counts) == {f"{a.slug}@{v}" for v in ("1.2.0", "1.2.9", "1.5.0")}, counts
    assert out2["withheld"] == [f"{a.slug}@1.5.0"], out2
    for x in (a, a2, c):
        assert _size_withheld(db, x), x.version
    for x in (b, never, d):
        assert not _size_withheld(db, x), f"over-withheld {x.version}"
    # re-certification of a withheld release keeps it withheld
    _certify(db, a2)
    assert _size_withheld(db, a2), "re-certified a2 may publish"


def probe_lock_taken_before_the_incident_read_with_a_stable_int4_key():
    order = []
    real_lock = R._lock_size_signature
    from sqlalchemy.orm import Session
    real_scalar = Session.scalar
    def spy_lock(s, db, sig):
        order.append(("lock", sig)); return real_lock(s, db, sig)
    def spy_scalar(self, stmt, *a, **k):
        if "incidents" in str(stmt).lower() and "for update" in str(stmt.compile(dialect=__import__("sqlalchemy.dialects.postgresql", fromlist=["x"]).dialect())).lower():
            order.append(("read", None))
        return real_scalar(self, stmt, *a, **k)
    db = _db(); a = _basket_medium(); _certify(db, a)
    with mock.patch.object(R, "_lock_size_signature", spy_lock), mock.patch.object(Session, "scalar", spy_scalar):
        _run(db, "physical.record", _inputs(a, scope="full_make", holds_shape=True, measured_width_cm=40.0))
    kinds = [k for k, _ in order]
    assert "lock" in kinds and "read" in kinds and kinds.index("lock") < kinds.index("read"), order
    # PostgreSQL branch: stable signed int4 key, two-key form
    calls = []
    class FakeS:
        def execute(self, stmt, params): calls.append((str(stmt), params))
    with mock.patch("brambleloop.core.db.is_postgres", return_value=True):
        real_lock(FakeS(), db, "physical-size:x:abc"); real_lock(FakeS(), db, "physical-size:x:abc")
    assert calls[0] == calls[1] and "pg_advisory_xact_lock(:ns, :k)" in calls[0][0], calls
    k = calls[0][1]["k"]; assert -2**31 <= k < 2**31 and calls[0][1]["ns"] == 734543621, calls


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("probe_"):
            try: f(); print("OK  ", n)
            except Exception as e:  # noqa
                fails += 1; import traceback; print("FAIL", n, repr(e)[:400])
    sys.exit(1 if fails else 0)
```

## Appendix: mutation driver (`/tmp/rev/mutate.py`)

```python
import subprocess, sys, pathlib
ROOT = pathlib.Path("/home/user/Project-Money/brambleloop")
REL = ROOT/"src/brambleloop/runtime/release.py"; BLD = ROOT/"src/brambleloop/products/builder.py"
MUTS = {
 "M1_revert_a": (REL, "        for r in failed + others:\n            v = r.get(\"version\")", "        for r in failed:\n            v = r.get(\"version\")"),
 "M2_drop_lock": (REL, "        _lock_size_signature(s, ctx.db, signature)\n", "        pass\n"),
 "M3_share_seams": (BLD, "assembly=[replace(x) for x in design.assembly],", "assembly=list(design.assembly),"),
 "M4_no_durable_dedupe": (REL, "            if not entry[\"durable\"]:\n                s.add(", "            if True:\n                s.add("),
 "M5_no_stored_dedupe": (REL, "            if not held[\"recorded\"]:\n", "            if True:\n"),
}
TESTS = sys.argv[2:]
name = sys.argv[1]
p, old, new = MUTS[name]
src = p.read_text(); assert src.count(old) == 1, name
p.write_text(src.replace(old, new))
try:
    for t in TESTS:
        r = subprocess.run([sys.executable, *t.split()], cwd=ROOT, env={"PYTHONPATH": "src:tests", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
        print(name, t, "exit", r.returncode, "FAILS:", len(fails)); [print("   ", f[:250]) for f in fails]
finally:
    p.write_text(src)
```
