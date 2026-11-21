"""eng/rebuild-outcomes: per-product outcome of the latest targeted rebuild attempt, in the
read-only evidence, fixed vocabulary only (slugs, job types, statuses, classes, action names,
counts, #NNN tags) -- never inputs, error text, reason text or artefact keys."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
SECRET = "sk-SECRET-token-9f8e7d"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/o.db")
    db.create_all()
    return db


def _job(s, jt, inputs, *, status=JobStatus.DONE, key=None, outputs=None, err=None, ago_h=1.0):
    j = Job(agent="listing", job_type=jt, inputs=inputs, outputs=outputs, status=status,
            idempotency_key=key, last_error=err, created_at=NOW - timedelta(hours=ago_h))
    s.add(j)
    s.flush()
    return j


def _audit(s, action, artifact, job, detail):
    s.add(AuditLog(actor="test", action=action, artifact=artifact, job_id=job.id,
                   detail=detail, at=NOW))


def _estate(db):
    """Two products. `cosy`: a sentinel attempt (older, superseded by a retry) whose retry
    enqueued pricing.position; pricing ran, listing.seo ran, launch.plan died; three verify
    checks, the last naming 2 marketing outstanding and 1 pricing completed; marketing.schedule
    was refused on #172; rebuild-incomplete open and parked on gate.blocked. `quiet`: its stage
    job was never written (not_found) and nothing verified yet."""
    with db.session() as s:
        old = _job(s, "chain.rebuild", {"product_slug": "cosy", "artefacts": ["pricing:x"],
                                        "change_id": "c1", "reason": SECRET},
                   key="rebuild:product:cosy:abc", outputs={"stage": "pricing.position",
                                                            "stage_job": None}, ago_h=30)
        att = _job(s, "chain.rebuild", {"product_slug": "cosy",
                                        "artefacts": ["pricing:cosy@1.0.0#p",
                                                      "marketing_asset:cosy:pin:aa"],
                                        "retry": "2026-11-21", "retry_of_key": old.idempotency_key,
                                        "reason": SECRET},
                   key="rebuild:product:cosy:abc:retry:2026-11-21", ago_h=4)
        stage = _job(s, "pricing.position", {"slug": "cosy", "version": "1.0.0",
                                             "note": SECRET}, ago_h=4)
        att.outputs = {"stage": "pricing.position", "stage_job": stage.id, "requested": [SECRET]}
        _job(s, "listing.seo", {"slug": "cosy", "version": "1.0.0"}, ago_h=3.9)
        _job(s, "pricing.position", {"slug": "other", "version": "1.0.0"}, ago_h=3.9)
        _job(s, "launch.plan", {"slug": "cosy", "version": "1.0.0"}, status=JobStatus.DEAD,
             err=f"KeyError: '{SECRET}'\nTraceback...", ago_h=3.8)
        mk = _job(s, "marketing.schedule", {"slug": "cosy", "version": "1.0.0"}, ago_h=3.7)
        _audit(s, "marketing.blocked", "cosy@1.0.0", mk,
               {"reasons": [f"rebuild outstanding (#172): {SECRET}", f"halted (#173) {SECRET}"]})
        _audit(s, "gate.blocked", "cosy@1.0.0", stage, {"reasons": [SECRET]})
        # an older attempt's refusal must not count for the latest attempt
        _audit(s, "chain.rebuild_refused", "cosy@1.0.0", old, {"why": SECRET})
        prev = att
        for n in (1, 2, 3):
            v = _job(s, "chain.rebuild", {"product_slug": "cosy", "artefacts": ["x"],
                                          "verify": n, "requested_by": att.id,
                                          "stage_job": stage.id},
                     key=f"rebuild-verify:cosy:{prev.id}:{n}", ago_h=4 - n * 0.3)
            prev = v
        _audit(s, "chain.rebuild_verified", "cosy@1.0.0", prev, {
            "completed": ["pricing:cosy@1.0.0#p"],
            "outstanding": ["marketing_asset:cosy:pin:aa", "marketing_asset:cosy:pin:bb"],
            "retired": {"visual_truth:cosy@1.0.0#9": SECRET}, "unbound": [],
            "outstanding_read": {"marketing_asset:cosy:pin:aa": f"stale: {SECRET}",
                                 "marketing_asset:cosy:pin:bb": "no provenance row"}})
        s.add(Incident(severity="P2", signature="rebuild-incomplete:cosy", product_slug="cosy",
                       halts_publication=True, summary=SECRET, report_count=2,
                       detail={"attempts": 2, "held": f"held {SECRET}",
                               "parked": {"gate": "gate.blocked", "reasons": [SECRET]}}))
        q = _job(s, "chain.rebuild", {"product_slug": "quiet", "artefacts": ["seo:quiet@1#s"]},
                 key="rebuild:hold-released:quiet:7:dd", status=JobStatus.DEAD,
                 err=f"RuntimeError: {SECRET}", outputs={"stage": "pricing.position",
                                                         "stage_job": 999999}, ago_h=2)
        # a whole-catalogue scan is not a targeted attempt
        _job(s, "chain.rebuild", {"cadence": "chain_rebuild"}, ago_h=0.5)
        _ = q


def test_latest_attempt_per_product_end_to_end():
    db = _db()
    _estate(db)
    o = pe.rebuild_outcomes(db, now=NOW)
    assert o["products"] == 2 and set(o["by_product"]) == {"cosy", "quiet"}, o
    c = o["by_product"]["cosy"]
    assert c["attempt"]["kind"] == "retry" and c["attempt"]["status"] == "done", c
    assert c["stage"] == {"enqueued": "pricing.position", "status": "done",
                          "error_class": None}, c
    assert c["chain"] == ["pricing.position:done", "listing.seo:done", "launch.plan:dead",
                          "marketing.schedule:done"], c
    assert c["chain_errors"] == {"launch.plan:KeyError": 1}, c
    assert c["verify"] == {"checks": 3, "by_status": {"done": 3}, "last_check": 3}, c
    assert c["by_class"] == {"completed": {"pricing": 1}, "outstanding": {"marketing_asset": 2},
                             "retired": {"visual_truth": 1}, "unbound": {}}, c
    assert c["outstanding_states"] == {"stale": 1, "no_row": 1}, c
    assert c["refusals"] == {"marketing.blocked": 1, "gate.blocked": 1}, c
    assert c["marketing_blocked_codes"] == ["#172", "#173"], c
    assert c["incident"] == {"open": True, "held": True, "attempts": 2,
                             "parked": "gate.blocked"}, c
    q = o["by_product"]["quiet"]
    assert q["attempt"]["kind"] == "hold_released" and q["attempt"]["status"] == "dead", q
    assert q["attempt"]["error_class"] == "RuntimeError", q
    assert q["stage"]["status"] == "not_found" and q["verify"]["checks"] == 0, q
    assert q["verified_pass_seen"] is False and q["incident"]["open"] is False, q


def test_privacy_no_text_inputs_or_keys_leave():
    db = _db()
    _estate(db)
    v = pe.factory_visibility(db, now=NOW)
    text = json.dumps(v)
    assert "rebuild_outcomes" in v and v["rebuild_outcomes"]["by_product"], v
    for bad in (SECRET, "Traceback", "#p", "pin:aa", "rebuild:product", "rebuild-verify",
                "requested_by", "inputs", "last_error", "held "):
        assert bad not in text, bad
    # and as served: the evidence's factory_visibility section carries the same reading
    ev = pe.evidence(db, now=NOW)
    fv = json.dumps(ev["factory_visibility"], default=str)
    assert "rebuild_outcomes" in fv and SECRET not in fv


def test_empty_and_unreadable():
    db = _db()
    assert pe.rebuild_outcomes(db, now=NOW) == {"window_days": 7, "products": 0,
                                                "by_product": {}}
    real = pe.rebuild_outcomes
    pe.rebuild_outcomes = lambda *a, **k: (_ for _ in ()).throw(ValueError(SECRET))
    try:
        v = pe.factory_visibility(db, now=NOW)
    finally:
        pe.rebuild_outcomes = real
    assert v["rebuild_outcomes"] == {"readable": False, "error_class": "ValueError"}, v


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
