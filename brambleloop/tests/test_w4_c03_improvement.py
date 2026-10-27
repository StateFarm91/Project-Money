"""W4-C03: method versions under the improvement loop, and challengers that run.

Rows (Final Master, quoted):
- F-707 "Agents may improve prompts, models, tools, workflows, product selection, patterns,
  Visual methods, Etsy/SEO, marketing, CX, finance, reliability and strategy only through
  versioned, testable, reversible changes with post-promotion monitoring."
- F-699 "teams continuously grow, adapt, upgrade prompts/tools/models/workflows and business
  strategy after launch, while preserving Product Truth, safety, policy, finance and owner
  authority."
The challenger run's `call` and `score` are fixtures; no model call; spends nothing real.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, OwnerAction  # noqa: E402
from brambleloop.improve import cells, methods  # noqa: E402

_n = [0]
H = ("render the owned photography with a named tiling pattern so the review can see and "
     "avoid the repetition it causes in close-up frames")


def _db() -> Database:
    _n[0] += 1
    tmp = tempfile.mkdtemp(prefix="c03_improve_")
    db = Database(f"sqlite:///{tmp}/d{_n[0]}.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db


# ---- F-707 ----------------------------------------------------------------------------------

def test_f707_every_registered_method_is_readable_from_its_source():
    for key, m in methods.METHODS.items():
        assert m.cell in cells.BY_KEY, key
        assert methods.running(m) is not None, (key, m.path, m.attr)
    assert methods.METHODS["gates.policy"].touches == ("policy",)       # gate tier: owner


def _fixture_method(tmp: Path, value: str) -> methods.Method:
    src = tmp / "fixture_method.py"
    src.write_text(f'"""fixture"""\nMETHOD_VERSION = {value!r}\n', encoding="utf-8")
    return methods.Method("visual.fixture", str(src), "METHOD_VERSION", "creative_assets",
                          ("code",), "a fixture Visual method")


def _promote(db, iid):
    from brambleloop.improve import tiers

    assert cells.test_result(db, iid, 0.05) == cells.TESTING     # lower block rate is better
    for kind in (tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST):
        cells.record_test(db, iid, kind=kind, ref=f"fixture:{kind}", passed=True,
                          recorded_by="evaluator")
    cells.approve(db, iid, approved_by="evaluator", why="fewer refused assets on the holdout")
    assert cells.promote(db, iid, promoted_by="evaluator") == cells.PROMOTED


def test_f707_a_hand_bump_is_an_incident_and_a_promoted_change_backs_it():
    db = _db()
    tmp = Path(tempfile.mkdtemp(prefix="c03_method_"))
    m = _fixture_method(tmp, "v1")
    saved = dict(methods.METHODS)
    methods.METHODS.clear()
    methods.METHODS[m.key] = m
    try:
        first = methods.audit(db)
        assert first["methods"][0]["state"] == "baseline" and not first["unversioned"]
        # Hand-bumped in code, with no improvement behind it.
        _fixture_method(tmp, "v2")
        out = methods.audit(db)
        assert out["unversioned"] == [m.key], out
        with db.session() as s:
            inc = s.scalar(select(Incident).where(Incident.signature.like("improve-method%")))
            assert inc is not None and not inc.resolved and "'v2'" in inc.summary
        assert methods.audit(db)["unversioned"] == [m.key]          # one incident, not two
        with db.session() as s:
            assert len(list(s.scalars(select(Incident)))) == 1
        # The versioned path: proposed (rollback to the running version), tested, promoted.
        cells.record_capability(db, "creative_assets", 0.10)
        iid = methods.propose_change(db, m.key, to_version="v3", hypothesis=H,
                                     expected_effect="fewer refused assets",
                                     proposed_by="creative_assets")
        with db.session() as s:
            from brambleloop.core.models import Improvement

            row = s.get(Improvement, iid)
            assert row.rollback_ref == f"method:{m.key}:v2"
            assert row.evidence["method_change"] == {
                "kind": "method_version", "method": m.key, "from": "v2", "to": "v3",
                "path": m.path, "attr": "METHOD_VERSION"}
        try:
            methods.propose_change(db, m.key, to_version="v2", hypothesis=H,
                                   expected_effect="x", proposed_by="creative_assets")
            raise AssertionError("a change names a new version")
        except methods.MethodRefused:
            pass
        _promote(db, iid)
        _fixture_method(tmp, "v3")                              # the code follows the promotion
        backed = methods.audit(db)
        assert backed["methods"][0]["state"] == "backed" and backed["resolved"] == [m.key]
        with db.session() as s:
            assert all(i.resolved for i in s.scalars(select(Incident)))
    finally:
        methods.METHODS.clear()
        methods.METHODS.update(saved)


def test_f707_the_sandbox_pass_runs_the_method_audit():
    from brambleloop.improve import runner

    db = _db()
    out = runner.run(db)
    assert out["methods"]["unversioned"] == [], out["methods"]


# ---- F-699 ----------------------------------------------------------------------------------

def _prompt_pair(db):
    from brambleloop.improve import league

    inc = league.register(db, kind="prompt", key="listing_copy.system",
                          payload="You write calm, exact listing copy.",
                          why_changed="the running listing copy prompt recorded as incumbent",
                          cost_per_call_cad=0.01, affected_departments=("store_commerce",),
                          incumbent=True)
    ch = league.register(db, kind="prompt", key="listing_copy.system",
                         payload="You write calm, exact listing copy; lead with the finished size.",
                         why_changed="challenger leads with the finished size buyers ask about",
                         cost_per_call_cad=0.01, affected_departments=("store_commerce",))
    return inc["id"], ch["id"]


ITEMS = [{"id": f"t{i}"} for i in range(20)]
HOLD = [{"id": f"h{i}"} for i in range(5)]


def _call(cfg, item):
    return {"output": {"text": cfg["payload"]}, "cost_cad": 0.01, "latency_s": 1.0}


def _score(item, output):
    return 0.95 if "finished size" in output["text"] else 0.80


def test_f699_a_challenger_runs_only_on_the_switch_an_owner_approval_and_a_reservation():
    from brambleloop.core.models import SpendReservation
    from brambleloop.improve import challenger_runs as CR, league

    db = _db()
    inc, ch = _prompt_pair(db)
    p = next(x for x in CR.plan(db) if x["config_id"] == ch)
    assert p["cost_cad"] == 0.5 and p["within_ceiling"] and p["incumbent"] == inc
    card = CR.request(db, ch)
    with db.session() as s:
        oa = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == card["requirement_key"]))
        assert oa.max_cost_cad == 0.5 and "CA$0.50" in oa.action
    os.environ.pop(CR.SWITCH, None)
    calls = []

    def call(cfg, item):
        calls.append(item["id"])
        return _call(cfg, item)

    assert CR.run(db, ch, items=ITEMS, holdout=HOLD, call=call, score=_score)["ran"] is False
    out = CR.run(db, ch, items=ITEMS, holdout=HOLD, call=call, score=_score, on=True)
    assert out["ran"] is False and "owner approval" in out["why"] and calls == []
    for bad in ({"amount_cad": 0.5, "approved_by": "laura", "why": "looks good to me"},
                {"amount_cad": 0.1, "approved_by": "owner", "why": "below the planned run"},
                {"amount_cad": 9.0, "approved_by": "owner", "why": "above the ceiling here"}):
        try:
            CR.approve(db, ch, **bad)
            raise AssertionError(bad)
        except CR.ChallengerRunRefused:
            pass
    CR.approve(db, ch, amount_cad=0.5, approved_by="owner", why="measure the size-first prompt")
    out = CR.run(db, ch, items=ITEMS, holdout=HOLD, call=call, score=_score, on=True)
    assert out["ran"] is True and abs(out["spent_cad"] - 0.5) < 1e-9, out
    assert len(calls) == 2 * (len(ITEMS) + len(HOLD))
    with db.session() as s:
        r = s.get(SpendReservation, out["reservation"])
        assert r.released_at is not None and abs(r.actual_cad - 0.5) < 1e-9
    # The league now has both runs on the same shared tasks and compares them.
    cyc = league.cycle(db)
    entry = next(c for c in cyc["compared"] if c["config_id"] == ch)
    assert entry["promote"] is True, entry
    # Planned only while unrun.
    assert not [x for x in CR.plan(db) if x["config_id"] == ch]


def test_f699_the_run_stops_at_its_claim():
    from brambleloop.improve import challenger_runs as CR, league

    db = _db()
    inc, ch = _prompt_pair(db)
    CR.approve(db, ch, amount_cad=0.5, approved_by="owner", why="measure the size-first prompt")

    def dear(cfg, item):
        return {"output": {"text": cfg["payload"]}, "cost_cad": 0.05, "latency_s": 1.0}

    out = CR.run(db, ch, items=ITEMS, holdout=HOLD, call=dear, score=_score, on=True)
    assert out["ran"] is False and "claim" in out["why"] and out["spent_cad"] <= 0.5 + 1e-9
    assert not league._runs(db).get(ch)                       # a partial run is not recorded


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
