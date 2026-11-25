"""19i30 GATE-EPISODE: our own ceiling (or a transient provider answer) never closes the
image_generation gate, and the capability redrive's "once" is per gate-closure episode.

Reproduces production 19i29 at 2026-11-25T18:41Z: FLUX 3 activated for probe and generation
with the owner's CA$5.00 daily ceiling, CA$4.95 of it already spent today; the last successful
probe is over PROBE_REUSE old, so the 6-hourly capability sweep re-probes, and the REAL owner
gate (`paid_provider_gate.authorize`) refuses the probe with `provider_daily_ceiling` before
any network I/O. Before 19i30 that refusal became the newest image.probe row and closed the
gate, blocking both hexagon-coaster runs at Laura lifestyle generation.

Nothing here reaches a network: the refusal is the real enforcement point refusing; the
transient case injects the generator the probe already accepts.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_image_gate_episode.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway import paid_provider_gate as PG  # noqa: E402
from brambleloop.visual import gallery  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import ImageProductionRun, ensure_tables  # noqa: E402

import _paid_activation as _paid  # noqa: E402

FLUX = "flux-3-image"
ENV = {images.key_var("bfl"): "test-credential-placeholder", images.PROVIDER_VAR: FLUX}
GATE_REASON = ("image_generation gate closed: a paid generator may not be called "
               "(no_probe_under_activation: flux-3-image activated, but no probe has yet "
               "succeeded under an activation still in force)")
SECRET = "test-credential-placeholder"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='gep_')}/gep.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    PG.ensure_tables(db)
    return db


def _production(db):
    """FLUX 3 activated (probe + generation, CA$5.00/day), a success 25 h old under that
    activation, and CA$4.95 billed today on FLUX 3 (seven 0.7071 calls)."""
    acts = {a["scope"]: a for a in _paid.activate(db, FLUX, PG.PROBE, PG.GENERATION,
                                                  daily=5.0, monthly=50.0, per_gallery=5.0)}
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION, artifact=FLUX,
                       at=now - timedelta(hours=25),
                       detail={"ok": True, "at": (now - timedelta(hours=25)).isoformat(),
                               "provider": FLUX, "activation_id": acts[PG.PROBE]["id"],
                               "reason": ""}))
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(7):
            s.add(PG.PaidProviderCall(
                activation_id=acts[PG.GENERATION]["id"], provider=FLUX, scope=PG.GENERATION,
                gallery="imgprod:other", run_key=f"job:{900 + i}", idem_key=f"spent{i}",
                fingerprint=f"fp{i}", purpose="image.generate", estimate_cad=0.7071,
                actual_cad=0.7071, status=PG.BILLED,
                at=max(day0, now - timedelta(minutes=30))))
    return acts


def test_production_state_the_ceiling_refused_probe_does_not_close_the_gate():
    db = _db()
    _production(db)
    assert images.usable(db), "fixture: the gate reads open before the sweep re-probes"
    rec = images.probe_if_due(db, env=ENV)
    # the REAL owner gate refused the re-probe with our own daily ceiling, nothing sent
    assert rec["ok"] is False and rec.get("state") == "provider_daily_ceiling", rec
    assert rec.get("inconclusive") is True and rec["outcome"] == "ceiling_refused", rec
    with db.session() as s:
        actions = [r.action for r in s.scalars(select(AuditLog).where(
            AuditLog.action.in_((images.PROBE_ACTION, images.PROBE_INCONCLUSIVE_ACTION)))
            .order_by(AuditLog.id))]
    assert actions == [images.PROBE_ACTION, images.PROBE_INCONCLUSIVE_ACTION], actions
    assert images.usable(db), "a ceiling refusal must not close image_generation"
    assert gallery.gates_now(db, keys=("image_generation",))["image_generation"] is True
    rb = images.gate_readback(db)
    assert rb["image_generation"] == "open", rb
    assert rb["latest_probe"] == {"outcome": "ceiling_refused", "at": rec["at"],
                                  "conclusive": False}, rb
    assert rb["probe_in_force"]["outcome"] == "ok", rb
    assert SECRET not in repr(rb)


def test_a_legacy_ceiling_refused_row_written_by_19i29_is_not_the_gates_evidence():
    """The row production holds now (written under PROBE_ACTION before 19i30) is skipped, so
    the gate reopens on deploy from the success still in force."""
    db = _db()
    acts = _production(db)
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION, artifact=FLUX,
                       detail={"at": datetime.now(timezone.utc).isoformat(), "ok": False,
                               "provider": FLUX, "activation_id": acts[PG.PROBE]["id"],
                               "state": "provider_daily_ceiling",
                               "reason": "[provider_daily_ceiling] flux-3-image has CA$4.9497"}))
    assert images.usable(db)
    assert images.probe_outcome(images.last_probe_attempt(db)) == "ceiling_refused"


def test_a_transient_provider_answer_does_not_close_the_gate():
    db = _db()
    _production(db)

    def busy(*a, **kw):
        raise TransientError('flux-3-image 503: {"detail":"over capacity"}')

    rec = images.probe(db, env=ENV, generator=busy)
    assert rec["ok"] is False and rec["outcome"] == "provider_transient", rec
    assert images.usable(db)


def test_a_real_provider_failure_or_a_lapsed_activation_still_closes_it():
    db = _db()
    acts = _production(db)

    def refused(*a, **kw):
        raise images.ImagesRefused("flux-3-image 401: unauthorized")

    rec = images.probe(db, env=ENV, generator=refused)
    assert rec["outcome"] == "provider_failure" and not rec.get("inconclusive"), rec
    assert not images.usable(db), "a real provider/auth failure closes the gate"
    assert images.gate_readback(db)["image_generation"] == "closed"

    db = _db()
    acts = _production(db)
    with db.session() as s:
        for a in acts.values():
            row = s.get(PG.PaidProviderActivation, a["id"])
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert not images.usable(db), "an expired activation closes the gate"
    rec = images.probe(db, env=ENV)
    assert rec["outcome"] == "activation_expired" and not rec.get("inconclusive"), rec


# ---- (b) the capability redrive, once per closure episode -----------------------------------

def _blocked(db, slug, at=None):
    key = IP.run_key(slug, "1.2.1", f"{slug}-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.2.1",
                                 release=f"{slug}-release", listing=slug,
                                 stage="lifestyle_generation", status="blocked",
                                 blocked_reason=GATE_REASON, stages={}))
    return key


def _reblock(db, key):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason = "blocked", GATE_REASON
        r.stage = "lifestyle_generation"
        r.updated_at = datetime.now(timezone.utc)


def _probe_row(db, ok):
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION, artifact=FLUX,
                       detail={"ok": ok, "at": datetime.now(timezone.utc).isoformat(),
                               "provider": FLUX, "reason": "" if ok else "flux-3-image 401"}))


class _Gate:
    open = True

    def __call__(self, db, keys=("image_generation",)):
        return {k: self.open for k in keys}


def _sweep(db, calls):
    def follow(inputs, key, *, session=None):
        calls.append(key)
        return object()
    return IP.redrive_capability_blocked(db, follow=follow)


def test_a_later_unrelated_closure_is_redriven_once_the_same_one_never_twice():
    db = _db()
    _probe_row(db, ok=False)                         # closure 1
    key = _blocked(db, "hexagon-coaster-set")
    gate, calls = _Gate(), []
    real = gallery.gates_now
    gallery.gates_now = gate
    try:
        out = _sweep(db, calls)
        assert [r["run_key"] for r in out["restarted"]] == [key], out
        _reblock(db, key)                            # same closure in force: once only
        out = _sweep(db, calls)
        assert not out["restarted"] and out["refused"][0]["code"] == "already_redriven", out
        _probe_row(db, ok=True)                      # gate reopened ...
        _probe_row(db, ok=False)                     # ... and closed again: a new episode
        _reblock(db, key)
        out = _sweep(db, calls)
        assert [r["run_key"] for r in out["restarted"]] == [key], out
        assert len(calls) == 2
        with db.session() as s:
            v = IP._redrive_verdict(s, s.scalar(select(ImageProductionRun)), None,
                                    datetime.now(timezone.utc), {})
        assert v["refused"] in IP.REDRIVE_REFUSALS
    finally:
        gallery.gates_now = real


def test_a_pre_19i30_redrive_from_an_earlier_closure_does_not_refuse_this_one():
    """The coasters: a capability redrive recorded before 19i30 (no episode tag, made before
    the closure that blocks them now) does not spend this closure's redrive."""
    db = _db()
    key = _blocked(db, "hexagon-coaster-set")
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.stages = {IP.RESTART_KEY: {"history": [{
            "epoch": 1, "by": IP.REDRIVE_BY,
            "at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            "reason": "image_generation opened after the run blocked on it"}]}}
    _probe_row(db, ok=False)                         # today's closure, after that redrive
    _reblock(db, key)
    gate, calls = _Gate(), []
    real = gallery.gates_now
    gallery.gates_now = gate
    try:
        out = _sweep(db, calls)
    finally:
        gallery.gates_now = real
    assert [r["run_key"] for r in out["restarted"]] == [key], out


def test_no_capability_restart_is_spent_while_the_daily_ceiling_has_no_headroom():
    db = _db()
    _production(db)
    key = _blocked(db, "hexagon-coaster-set")
    gate, calls = _Gate(), []
    real = gallery.gates_now
    gallery.gates_now = gate
    try:
        out = _sweep(db, calls)
    finally:
        gallery.gates_now = real
    assert calls == [] and out["waiting"][0]["code"] == IP.METHOD_REDRIVE_WAIT_DAILY, out
    assert IP.get_run(db, key)["state"] == "blocked"


def test_the_evidence_readback_shows_the_gate_and_its_latest_probe():
    from brambleloop.ops import production_evidence as PE

    db = _db()
    _production(db)
    images.probe_if_due(db, env=ENV)
    _blocked(db, "hexagon-coaster-set")
    g = PE._redrive_eligibility(db)["image_generation_gate"]
    assert g["readable"] and g["state"] == "open", g
    assert g["latest_probe"]["outcome"] == "ceiling_refused", g
    assert g["latest_probe"]["conclusive"] is False and g["probe_in_force"]["outcome"] == "ok"
    assert SECRET not in repr(g) and "CA$" not in repr(g)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
