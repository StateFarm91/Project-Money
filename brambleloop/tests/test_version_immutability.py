"""PT-03: a certified slug@version is immutable at runtime, through the gate.certify handler.

The audit certified the Launch-0 hexagon CIR, then certified the same JSON with a different
gauge (a different finished size and yardage) and the version unchanged: both were granted and
the stored PatternVersion row was silently replaced ('gate.recertified'), so a buyer holding
"1.1.0" and one downloading "1.1.0" next week would hold different patterns. The runtime now
refuses that with an audit record and an incident, and keeps the release it already certified.
No network, no model calls.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="version_immutability_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, PatternVersion, Phase  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401  (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _certify(db: Database, cir_json: dict, key: str) -> None:
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir_json},
                         idempotency_key=key, priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()


def _state(db: Database, slug: str):
    with db.session() as s:
        actions = [(a.action, a.artifact) for a in s.scalars(select(AuditLog).where(
            AuditLog.action.in_(["gate.certified", "gate.recertified", "gate.blocked",
                                 "gate.version_conflict"])))]
        versions = [(p.version, p.release_hash, json.dumps(p.cir_json, sort_keys=True))
                    for p in s.scalars(select(PatternVersion))]
        incidents = [(i.signature, i.severity, i.halts_publication)
                     for i in s.scalars(select(Incident).where(Incident.product_slug == slug))]
    return actions, versions, incidents


def test_changed_content_under_a_certified_version_is_refused():
    db = _db("content")
    cir = launch0.cir_for("hexagon_coasters")
    first = cir.to_dict()
    _certify(db, first, "a")
    actions, versions, _ = _state(db, cir.slug)
    assert ("gate.certified", f"{cir.slug}@{cir.version}") in actions, actions
    assert len(versions) == 1
    stored = versions[0]

    # The audit's change: a different gauge (so a different finished size and yardage), same
    # version string.
    changed = json.loads(json.dumps(first))
    changed["gauge"]["hook_mm"] = 4.5
    changed["gauge"]["stitches_per_10cm"] = 15.0
    assert changed["version"] == first["version"]
    _certify(db, changed, "b")
    actions, versions, incidents = _state(db, cir.slug)
    assert ("gate.version_conflict", f"{cir.slug}@{cir.version}") in actions, actions
    assert not any(a == "gate.recertified" for a, _ in actions), actions
    assert versions == [stored], "the certified release was replaced under the same version"
    assert any(sig == f"release.version_immutable:{cir.slug}@{cir.version}"
               and sev == "P2" and not halts for sig, sev, halts in incidents), incidents

    # The same change under a new version is a release, and is stored beside the first.
    changed["version"] = "9.9.0"
    _certify(db, changed, "c")
    _actions, versions, _ = _state(db, cir.slug)
    assert sorted(v for v, _h, _j in versions) == [cir.version, "9.9.0"]


def test_recertifying_identical_content_is_still_allowed():
    db = _db("identical")
    cir = launch0.cir_for("basket_small")
    _certify(db, cir.to_dict(), "a")
    _certify(db, cir.to_dict(), "b")
    actions, versions, incidents = _state(db, cir.slug)
    assert not any(a == "gate.version_conflict" for a, _ in actions), actions
    assert len(versions) == 1 and not any(s.startswith("release.version_immutable")
                                          for s, _sv, _h in incidents)


def test_a_claims_change_with_an_identical_design_is_refused():
    """PT-07's shape of defect: the CIR is byte-identical but the model now states different
    yardage. The version promised the old figures, so it cannot silently carry new ones."""
    import brambleloop.cir.twin as T

    db = _db("claims")
    cir = launch0.cir_for("hexagon_coasters")
    _certify(db, cir.to_dict(), "a")
    saved = dict(T._YARN_FACTOR)
    try:
        T._YARN_FACTOR["inc"] = saved["inc"] * 2
        _certify(db, cir.to_dict(), "b")
    finally:
        T._YARN_FACTOR.clear()
        T._YARN_FACTOR.update(saved)
    actions, versions, _ = _state(db, cir.slug)
    assert ("gate.version_conflict", f"{cir.slug}@{cir.version}") in actions, actions
    assert len(versions) == 1


if __name__ == "__main__":
    fails = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("OK  ", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    print("FAIL", name, repr(e)[:400])
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
