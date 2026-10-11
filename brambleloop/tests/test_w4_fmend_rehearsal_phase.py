"""W4-FMEND (F-848): the shadow rehearsal records the owner's phase transition, never forces it.

`store.publish` runs under `protected_phase`, which includes the owner's *recorded* phase
(`core.phase.effective`). Before this fix the rehearsal set only BRAMBLELOOP_PHASE, so its
past-shadow publish was always refused as SHADOW. `scripts/shadow_rehearsal.py::record_owner_phase`
now runs the real `launch.readiness` job and `core.phase.record_transition` (the function behind
the owner route) in the scratch database. These tests pin that:

* a fresh shop is not ready, so the transition is refused, the step is BLOCKED with the reason
  and a defect, and no transition row is written: the phase stays shadow;
* a wrong credential is refused even with a ready verdict;
* cited evidence is still enforced: a ready verdict alone reaches staging, but not
  limited_production while the cited `launch.assessed` row says not ready;
* with passing evidence and a ready verdict, the transition is recorded and the effective phase
  becomes limited_production.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_fmend_rehearsal_phase.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="fmend_phase_art_")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-FMEND harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

_spec = importlib.util.spec_from_file_location("shadow_rehearsal",
                                               ROOT / "scripts" / "shadow_rehearsal.py")
reh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reh)

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import phase as phase_mod  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402

TOKEN = reh.REHEARSAL_OPS_TOKEN


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmend_phase_')}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _env(token=TOKEN):
    os.environ["BRAMBLELOOP_PHASE"] = "limited_production"
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = token


def _transitions(db):
    return reh._audits(db, phase_mod.TRANSITION)


def _ready(db, to):
    return {"ready": True, "evaluated_at": "2026-10-11T00:00:00+00:00"}


def test_a_shop_that_is_not_ready_is_blocked_never_forced():
    db = _db()
    _env()
    rec = reh.Recorder()
    out = reh.record_owner_phase(rec, db)
    step = rec.steps[-1]
    assert out["ok"] is False and step["step"] == "owner_phase_transition"
    assert step["outcome"] == reh.BLOCKED, step
    assert step["db_proof"]["launch.readiness_job"]["status"] == "done", step["db_proof"]
    assert step["db_proof"]["launch.assessed"]["ready"] is False
    assert any(d["key"] == "owner_phase_transition_refused" for d in rec.defects)
    # The real precondition that refused it is named (here: no passing readiness, or no
    # rollback rehearsal to cite on a shop with no listed release).
    assert ("readiness" in step["observed"]["why"]
            or "evidence refs" in step["observed"]["why"]), step["observed"]
    assert _transitions(db) == [], "a refused move wrote a transition"
    assert phase_mod.effective(db, record_incident=False) == "shadow"


def test_a_wrong_credential_is_refused_even_when_ready():
    db = _db()
    _env()
    rec = reh.Recorder()
    out = reh.record_owner_phase(rec, db, authorization="not-the-rehearsal-credential-000000",
                                 readiness_verdict=_ready)
    assert out["ok"] is False and rec.steps[-1]["outcome"] == reh.BLOCKED
    assert "credential rejected" in out["why"], out["why"]
    assert _transitions(db) == []


def test_cited_evidence_is_still_enforced_past_staging():
    db = _db()
    _env()
    # A held rollback rehearsal exists; the real launch.readiness job then writes the latest
    # launch.assessed row, which on a fresh shop says not ready.
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                       artifact="x@1.0.0", detail={"ok": True}))
    rec = reh.Recorder()
    out = reh.record_owner_phase(rec, db, readiness_verdict=_ready)
    step = rec.steps[-1]
    assert out["ok"] is False and step["outcome"] == reh.BLOCKED, step
    assert [r["to"] for r in out["recorded"]] == ["staging"], out
    assert step["observed"]["refused_at"] == "limited_production"
    assert "does not pass" in step["observed"]["why"], step["observed"]["why"]
    assert phase_mod.effective(db, record_incident=False) == "staging"


def test_passing_evidence_and_a_ready_verdict_record_limited_production():
    db = _db()
    _env()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="launch.assessed", artifact="launch",
                       detail={"ready": True}))
        s.add(AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                       artifact="x@1.0.0", detail={"ok": True}))
    real = reh._run_job
    reh._run_job = lambda *a, **k: {"id": None, "status": "not run (test)", "last_error": ""}
    try:
        rec = reh.Recorder()
        out = reh.record_owner_phase(rec, db, readiness_verdict=_ready)
    finally:
        reh._run_job = real
    step = rec.steps[-1]
    assert out["ok"] is True and step["outcome"] == reh.PASS, step
    assert [r["to"] for r in out["recorded"]] == ["staging", "limited_production"]
    assert len(_transitions(db)) == 2
    assert phase_mod.effective(db, record_incident=False) == "limited_production"
    assert not rec.defects


def test_the_rehearsal_requires_the_phase_step():
    src = (ROOT / "scripts" / "shadow_rehearsal.py").read_text()
    assert '"owner_phase_transition", "owner_publication_grant"' in src
    assert "record_owner_phase(rec, db)" in src, "the rehearsal must use the live verdict"


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
