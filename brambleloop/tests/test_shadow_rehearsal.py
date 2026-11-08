"""F-848: the shadow rehearsal runs end to end and its evidence is honest about every step.

Runs `scripts/shadow_rehearsal.py` in fast mode (the same handlers through an in-process
Worker instead of booting the production start command; the committed evidence under
research/final_build/evidence/ is the production-mode run) on a fresh database, with the
network refused, and checks the evidence it writes. What it pins is honesty, not a green
rehearsal: a step may be BLOCKED by a real gate or defect, but then the rehearsal must say
it is not complete and name what blocked it. It never pins the past-shadow publish to PASS
or BLOCKED, because that outcome is the product of other work in flight.

Run: cd brambleloop && $PY tests/test_shadow_rehearsal.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

OUTCOMES = {"PASS", "REFUSED_AS_EXPECTED", "BLOCKED", "FAILED", "SKIPPED"}
REQUIRED = ["opportunity", "design", "boot", "cir.compile", "gate.certify", "assets.build", "listing.seo",
            "listing.package", "store.publish[shadow]", "owner_phase_transition", "owner_publication_grant",
            "store.publish[past-shadow]",
            "orders.ingest", "support.case", "ledger"]
_EV: dict = {}


def _rehearsal():
    spec = importlib.util.spec_from_file_location("shadow_rehearsal",
                                                  ROOT / "scripts" / "shadow_rehearsal.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def evidence() -> dict:
    if not _EV:
        out = Path(tempfile.mkdtemp(prefix="rehearsal_test_")) / "ev.json"
        ev = _rehearsal().rehearse("cloudline-baby-blanket", fast=True, out=out)
        written = json.loads(out.read_text())     # the evidence file is what is asserted on
        _EV.update(written)
        assert len(written["steps"]) == len(ev["steps"])
    return _EV


def _step(name):
    return next(s for s in evidence()["steps"] if s["step"] == name)


def test_every_required_step_has_an_outcome_and_db_proof():
    ev = evidence()
    names = [s["step"] for s in ev["steps"]]
    assert set(REQUIRED) <= set(names), sorted(set(REQUIRED) - set(names))
    assert all(s["outcome"] in OUTCOMES for s in ev["steps"])
    assert "rehearsal" not in names, _step("rehearsal")["db_proof"]   # it did not crash
    for s in ev["steps"]:
        if s["outcome"] in ("PASS", "REFUSED_AS_EXPECTED") and s["step"] != "boot":
            assert s["db_proof"], s["step"]
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    assert ev["head"] == head and ev["mode"] == "fast" and ev["requirement"] == "F-848"


def test_the_shadow_chain_certifies_builds_and_is_refused_at_publish():
    for name in ("cir.compile", "gate.certify", "assets.build", "listing.seo"):
        assert _step(name)["outcome"] == "PASS", _step(name)
    pub = _step("store.publish[shadow]")
    assert pub["outcome"] == "REFUSED_AS_EXPECTED", pub
    assert pub["db_proof"]["store.published"] == 0
    assert pub["db_proof"]["store.publish_refused"]
    assert _step("network[shadow]")["observed"]["guard_installed"] is True


def test_the_certified_release_reaches_an_honest_listing_package():
    """Owner goal L3 (F-848): the rehearsal drives the certified product to a listing package
    through the real listing.package job, bound to its release; its state is reported as it
    is (READY, or BLOCKED naming every blocker), never upgraded, and nothing is published."""
    pkg = _step("listing.package")
    assert pkg["outcome"] == "PASS", pkg
    proof = pkg["db_proof"]["operating_readings.listing_package"]
    assert proof and proof["publishes"] is False
    assert proof["release_hash"] == _step("gate.certify")["db_proof"]["pattern_versions"][
        "release_hash"], proof
    assert pkg["observed"]["package_state"] == proof["state"]
    if proof["state"] == "ready_for_owner_review":
        assert proof["blockers"] == []
    else:
        assert proof["state"] == "blocked" and proof["blockers"], proof
        assert all(b["source"] and b["why"] for b in proof["blockers"]), proof["blockers"]
    assert pkg["db_proof"]["listing.package audits"], "the job ran and audited its sweep"
    # the package precedes the publish refusal in the same run
    names = [s["step"] for s in evidence()["steps"]]
    assert names.index("listing.package") < names.index("store.publish[past-shadow]")


def test_the_listing_package_step_never_passes_a_dishonest_package():
    """The step's own verdict: PASS only for a package bound to this release, publishing
    nothing, READY with no blocker or BLOCKED with every blocker named."""
    m = _rehearsal()
    from brambleloop.publish import listing_package as LP

    state = {"slug": "s", "version": "1.0.0", "release": "r" * 64}
    good_blocked = {"state": LP.BLOCKED, "release_hash": "r" * 64, "publishes": False,
                    "blockers": [{"source": "release_gates.for_publish", "why": "x"}]}
    cases = [
        (good_blocked, "done", "PASS"),
        ({**good_blocked, "state": LP.READY, "blockers": []}, "done", "PASS"),
        ({**good_blocked, "release_hash": "o" * 64}, "done", "FAILED"),      # other release
        ({**good_blocked, "publishes": True}, "done", "FAILED"),            # would publish
        ({**good_blocked, "blockers": [{"source": "x", "why": " "}]}, "done", "FAILED"),
        ({**good_blocked, "blockers": []}, "done", "FAILED"),               # blocked, unnamed
        ({**good_blocked, "state": LP.READY}, "done", "FAILED"),            # ready + blockers
        (None, "done", "FAILED"),                                           # nothing recorded
        (good_blocked, "dead", "BLOCKED"),                                  # the job died
    ]
    saved = (m._run_job, LP.latest, m._audits)
    try:
        for pkg, status, want in cases:
            m._run_job = lambda *_a, _s=status, **_k: {"id": 1, "status": _s, "last_error": ""}
            LP.latest = lambda *_a, _p=pkg, **_k: None if _p is None else dict(_p)
            m._audits = lambda *_a, **_k: []
            rec = m.Recorder()
            m.record_listing_package(rec, None, dict(state))
            assert rec.steps[-1]["outcome"] == want, (pkg, status, rec.steps[-1])
        rec = m.Recorder()
        m.record_listing_package(rec, None, {**state, "release": None})
        assert rec.steps[-1]["outcome"] == "SKIPPED"
    finally:
        m._run_job, LP.latest, m._audits = saved


def test_the_past_shadow_outcome_is_honest_either_way():
    ev = evidence()
    pub = _step("store.publish[past-shadow]")
    if pub["outcome"] == "PASS":
        assert pub["db_proof"]["listings.etsy_listing_id"]
        assert len(pub["observed"]["fake_listings"]) == 1
        assert _step("owner_publication_grant")["outcome"] == "PASS"
    else:
        assert pub["outcome"] in ("BLOCKED", "FAILED", "SKIPPED")
        assert ev["complete"] is False
        assert "store.publish[past-shadow]" in ev["not_complete_because"]
        assert ev["blocking_defects"], "a blocked publish must name what blocked it"
        if isinstance(pub["observed"], dict):
            assert not pub["observed"].get("fake_listings"), "blocked yet a draft exists"
    # The simulated phase ran under the narrowed guard (only the fake's loopback port open).
    assert _step("network[past-shadow]")["outcome"] == "PASS"


def test_order_support_and_ledger_run_on_the_rehearsed_product():
    o = _step("orders.ingest")
    assert o["outcome"] == "PASS", o
    assert len(o["db_proof"]["orders"]) == 1
    assert _step("support.case")["outcome"] == "PASS", _step("support.case")
    assert _step("support.case")["db_proof"]["support_cases"]["sent"] is False
    led = _step("ledger")
    assert led["outcome"] == "PASS" and any(e["category"] == "sale"
                                            for e in led["db_proof"]["ledger"])


def test_complete_means_every_required_step_passed_or_refused_as_designed():
    ev = evidence()
    good = {"PASS", "REFUSED_AS_EXPECTED"}
    assert ev["complete"] == all(ev["outcomes"].get(k) in good for k in REQUIRED)
    assert set(ev["not_complete_because"]) == {k for k in REQUIRED
                                               if ev["outcomes"].get(k) not in good}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
