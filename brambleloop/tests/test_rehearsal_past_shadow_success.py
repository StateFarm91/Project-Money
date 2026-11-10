"""Review 6775786220 F1: the rehearsal's past-shadow publish PASS path runs in a test.

`scripts/shadow_rehearsal.run_past_shadow` is the only code that drives, in one sequence,
the simulated taxonomy -> the owner's recorded phase transition -> the sealed owner grant ->
grant consumption by the real `store.publish` handler -> the search certificate -> exactly
one draft on the fake Etsy. Every full rehearsal stops at the phase transition (readiness is
honestly not met), so that branch -- `outcome = PASS`, `draft_listing_id` -- ran in no test.

Here it runs on a certified release built by the real gate.certify -> assets.build ->
listing.seo handlers (tests/test_search_hero_publish.py's fixture, the same Launch-0 product
the rehearsal defaults to). Held, exactly as that fixture holds them and each with its own
tests: the readiness verdict (fmend's `_ready`; readiness is honestly not met on a fixture
shop), the creative parity gate (#75), the search-grid tournament (#126) and the Launch-0
first-customer scope gate. Everything else -- the taxonomy refresh, the transition with its
cited evidence, approve(), grant consumption, the search certificate, the Etsy client -- runs
for real against the loopback fake.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_rehearsal_past_shadow_success.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_search_hero_publish as SH  # noqa: E402  (sets its env and loopback-only sockets)

_spec = importlib.util.spec_from_file_location("shadow_rehearsal",
                                               ROOT / "scripts" / "shadow_rehearsal.py")
reh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reh)

from sqlalchemy import select  # noqa: E402

from brambleloop.core import phase as phase_mod  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing  # noqa: E402


def _ready(db, to):
    return {"ready": True, "evaluated_at": "2026-11-10T00:00:00+00:00"}


def _held_gates():
    """The three gates test_search_hero_publish holds (module docstring there), nothing more."""
    from brambleloop.creative import preengineering
    from brambleloop.publish import eligibility
    from brambleloop.runtime import pipeline

    saved = (pipeline._listing_parity, preengineering.release_grid_verdict,
             eligibility.product_publication)
    pipeline._listing_parity = lambda ctx: {"verdict": "pass", "blocks_release": False,
                                            "why": "held: #75 has its own tests",
                                            "dimensions": {}}
    preengineering.release_grid_verdict = lambda db, slug: {"cleared": True,
                                                            "why": "held: #126"}
    eligibility.product_publication = lambda *a, **k: {"reasons": [],
                                                       "held": "Launch-0 scope gate"}

    def restore():
        (pipeline._listing_parity, preengineering.release_grid_verdict,
         eligibility.product_publication) = saved
    return restore


def test_the_past_shadow_publish_pass_path_creates_exactly_one_draft_under_the_grant():
    path, version, rh = SH._chain()
    db = Database(f"sqlite:///{path}")
    with db.session() as s:          # the evidence the transition cites (fmend's pattern)
        s.add(AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                       artifact=f"{SH.SLUG}@{version}", detail={"ok": True}))
    real_phase, real_run_job = reh.record_owner_phase, reh._run_job

    def phase_with_ready_verdict(rec, db_):
        # only the launch.readiness job is not run (fmend's pattern); the transition itself,
        # its credential and its cited-evidence checks are real
        def run_job(db__, agent, job_type, inputs, phase):
            if job_type == "launch.readiness":
                with db__.session() as s:
                    s.add(AuditLog(actor="orchestrator", action="launch.assessed",
                                   artifact="launch", detail={"ready": True}))
                return {"id": None, "status": "not run (test)", "last_error": ""}
            return real_run_job(db__, agent, job_type, inputs, phase)
        reh._run_job = run_job
        try:
            return real_phase(rec, db_, readiness_verdict=_ready)
        finally:
            reh._run_job = real_run_job

    reh.record_owner_phase = phase_with_ready_verdict
    restore = _held_gates()
    try:
        rec = reh.Recorder()
        state = {"slug": SH.SLUG, "version": version, "release": rh,
                 "publish_inputs": {"slug": SH.SLUG, "version": version, "release": rh}}
        out = reh.run_past_shadow(rec, db, state)
    finally:
        restore()
        reh.record_owner_phase = real_phase
    by = {s["step"]: s for s in rec.steps}
    assert by["taxonomy[simulated]"]["outcome"] == reh.PASS, by["taxonomy[simulated]"]
    assert by["owner_phase_transition"]["outcome"] == reh.PASS, by["owner_phase_transition"]
    # the recorded owner transitions (the environment phase is restored when the simulated
    # phase ends, so `effective` reads shadow again afterwards, as it should)
    moves = [a["detail"].get("to") for a in reh._audits(db, phase_mod.TRANSITION)]
    assert moves[-2:] == ["staging", "limited_production"], moves
    assert by["owner_publication_grant"]["outcome"] == reh.PASS, by["owner_publication_grant"]
    pub = by["store.publish[past-shadow]"]
    assert pub["outcome"] == reh.PASS, pub
    assert pub["observed"]["status"] == "done" and pub["observed"]["create_requests"] == 1, pub
    assert len(pub["observed"]["fake_listings"]) == 1, pub["observed"]
    assert out["draft_listing_id"] and pub["db_proof"]["store.published"], (out, pub)
    assert not pub["db_proof"]["store.publish_refused"], pub["db_proof"]
    assert by["network[past-shadow]"]["outcome"] == reh.PASS, by["network[past-shadow]"]
    assert not [d for d in rec.defects if "publish" in d["key"]], rec.defects
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == SH.SLUG))
        assert str(listing.etsy_listing_id) == str(out["draft_listing_id"])
        # the grant reached the publish that ran (the client resolves it at every effect
        # boundary), not merely recorded
        from brambleloop.core.models import Job
        grant_id = by["owner_publication_grant"]["observed"]["approval_id"]
        job = s.get(Job, pub["observed"]["job"])
        assert job.inputs["owner_publication_approval_id"] == grant_id, job.inputs
        assert job.outputs.get("published") is True, job.outputs
    db.engine.dispose()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
