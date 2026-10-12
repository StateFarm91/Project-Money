"""Visual R&D loop, end to end (wave 3, lane H; owner directive §9-§12).

A deterministic-renderer challenger runs through every gate, a promotion changes the next
generation's parameters and bytes, a production regression rolls it back, and marketplace
slow-loop evidence overturns an internal promotion and changes future behaviour. Local,
deterministic, no network, no provider, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w3_visual_rnd_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual.rnd import loop as L  # noqa: E402
from brambleloop.visual.rnd import pipeline as P  # noqa: E402
from brambleloop.visual.rnd import status as S  # noqa: E402

CLS = "coasters_tabletop"
_N = [0]
_CIRS = []


def cirs():
    if not _CIRS:
        _CIRS.extend(L.catalogue(["hexagon_coasters"])[CLS])
    return _CIRS


def fresh_db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/t{_N[0]}.sqlite")
    db.create_all()
    return db


def hero_sha(gen: dict) -> str:
    assert gen["galleries"], gen
    return gen["galleries"][0]["frames"][0]["sha256"]


def promoted_db():
    """A database in which the gap challenger has been tested and promoted."""
    db = fresh_db()
    before = L.generate(db, CLS, cirs=cirs())
    out = L.experiment(db, CLS, {"hero_gap_ratio": 0.06}, cirs=cirs())
    assert out["state"] == L.PROMOTED, out
    return db, before, out


def test_classes_cover_the_directive():
    want = {"baskets_storage", "coasters_tabletop", "blankets_home_textiles", "accessories",
            "fitted_garments", "loose_garments", "seasonal", "laura_on_model"}
    assert want <= set(P.PRODUCT_CLASSES)
    cat = L.catalogue()
    assert set(cat) >= {"baskets_storage", "coasters_tabletop", "blankets_home_textiles"}, cat
    assert P.classify("Merino Cable Beanie") == "accessories"
    assert P.classify("Oversized Poncho") == "loose_garments"
    assert P.classify("Christmas Coaster Ornament") == "seasonal"


def test_deterministic_challenger_runs_end_to_end_through_the_gates():
    db = fresh_db()
    report = L.cycle(db, builds=["hexagon_coasters"], classes=[CLS])
    entry = report["classes"][CLS]
    assert entry["generated"]["yield"] == 1.0, entry
    runs = entry["experiments"]
    assert runs and runs[0]["state"] == L.PROMOTED and runs[0]["changes"] == {
        "hero_gap_ratio": 0.06}, runs
    eid = runs[0]["experiment"]
    from sqlalchemy import select

    from brambleloop.visual.rnd import models as M
    with db.session() as s:
        rows = list(s.scalars(select(M.VisualJudgement).where(
            M.VisualJudgement.experiment_id == eid)))
        exp = s.get(M.VisualExperiment, eid)
        arms = {r.arm for r in rows}
        frames = [r for r in rows if not r.subject.endswith(":gallery")]
        assert arms == {"incumbent", "challenger"}, arms
        assert len(frames) == 6, len(frames)
        for r in frames:
            assert set(P.GATES) <= set(r.gates), r.gates
            assert r.gates["product_truth"]["status"] == "PASS"
            assert r.gates["structure"]["status"] == "PASS"
            assert r.gates["laura_identity"]["status"] == "N/A"
            assert r.gates["photorealism"]["status"] == "N/A"
            assert r.gates["blind_benchmark"]["status"] == "UNKNOWN"
            assert r.accepted and r.cost_cad == 0.0 and r.latency_s is not None
        res = exp.result
        assert res["quality_gain"] > res["required_margin"], res
        assert res["challenger"]["yield"] == 1.0 and exp.execution == P.DETERMINISTIC
    inc = P.ensure_incumbent(db, CLS)
    assert inc["generation"] == 2 and inc["params"]["hero_gap_ratio"] == 0.06, inc
    assert any(les["kind"] == "promoted" for les in L.lessons(db, CLS))
    # Paid work for the class was planned, not executed.
    assert entry["paid"]["state"] == L.GATED_SPEND, entry["paid"]


def test_promotion_changes_the_next_generations_parameters():
    db, before, _ = promoted_db()
    assert before["pipeline"]["params"]["hero_gap_ratio"] == 0.18
    after = L.generate(db, CLS, cirs=cirs())
    assert after["pipeline"]["params"]["hero_gap_ratio"] == 0.06
    assert after["pipeline"]["id"] != before["pipeline"]["id"]
    assert hero_sha(after) != hero_sha(before)
    assert after["quality"] > before["quality"] and after["yield"] == 1.0
    # The detail and scale frames did not change: only the hero layout was varied.
    assert before["galleries"][0]["frames"][1]["sha256"] == \
        after["galleries"][0]["frames"][1]["sha256"]


def test_gate_failures_reject_and_are_remembered():
    db = fresh_db()
    merged = L.experiment(db, CLS, {"hero_gap_ratio": 0.0}, cirs=cirs())
    assert merged["state"] == L.REJECTED, merged
    assert any("STRUCTURE:FAIL:object_count" in b for b in merged["verdict"]["blockers"]), merged
    # Film grain is "structure-preserving" to `presentation`, but the disclosed-render
    # contract refuses off-palette pixels: the verifier, not the producer, says no.
    grain = L.experiment(db, CLS, {"post_grain_sigma": 3.0}, cirs=cirs())
    assert grain["state"] == L.REJECTED
    assert grain["verdict"]["challenger"]["yield"] == 0.0, grain["verdict"]
    assert any("contract_palette" in f for f in grain["verdict"]["challenger"]["failures"])
    assert P.ensure_incumbent(db, CLS)["generation"] == 1
    again = L.experiment(db, CLS, {"hero_gap_ratio": 0.0}, cirs=cirs())
    assert again["state"] == L.MEMORY_SKIPPED, again
    diag = L.diagnose(db, CLS)
    nxt = L.propose(db, CLS, diag, catalogue=L.catalogue_fp(cirs()))
    assert nxt is not None and nxt != {"hero_gap_ratio": 0.0}, nxt


def test_regression_triggers_rollback():
    db, before, out = promoted_db()
    inc = P.ensure_incumbent(db, CLS)
    assert L.monitor(db, CLS)["action"] == "waiting"
    L.generate(db, CLS, cirs=cirs())
    assert L.monitor(db, CLS)["action"] == "retain"
    # A later production batch under the promoted version fails the structural verifier
    # (e.g. a new product the layout merges): recorded through the external-judgement door.
    subject = "hexagon-coaster-set@1.2.0"
    for view in ("hero", "scale", "detail"):
        L.record_judgement(db, CLS, subject=f"{subject}:{view}", pipeline_id=inc["id"],
                           gates={g: {"status": "PASS"} for g in P.GATES
                                  if g not in ("structure",)} | {
                               "structure": {"status": "FAIL", "failed": ["object_count"]},
                               "photorealism": {"status": "N/A"}},
                           source="test:production-batch-2")
    L.record_judgement(db, CLS, subject=f"{subject}:gallery", pipeline_id=inc["id"],
                       gates={"gallery_contract": {"status": "PASS"}}, score=0.0,
                       metrics={"frame_failures": ["STRUCTURE:FAIL"]}, source="test:batch-2")
    mon = L.monitor(db, CLS)
    assert mon["action"] == "rolled_back", mon
    restored = P.ensure_incumbent(db, CLS)
    assert restored["id"] == before["pipeline"]["id"] and \
        restored["params"]["hero_gap_ratio"] == 0.18
    states = {v["id"]: v["state"] for v in P.versions(db, CLS)}
    assert states[inc["id"]] == P.ROLLED_BACK
    from brambleloop.visual.rnd import models as M
    with db.session() as s:
        assert s.get(M.VisualExperiment, out["experiment"]).state == L.ROLLED_BACK
    assert any(les["kind"] == "rolled_back" for les in L.lessons(db, CLS))
    nxt = L.generate(db, CLS, cirs=cirs())
    assert hero_sha(nxt) == hero_sha(before), "rollback must restore the earlier bytes"


def test_marketplace_slow_loop_overturns_an_internal_promotion():
    db, before, out = promoted_db()
    inc = P.ensure_incumbent(db, CLS)
    parent = inc["parent_id"]
    # Too little evidence: nothing moves.
    L.record_market(db, pipeline_id=parent, impressions=150, clicks=12, source_ref="etsy:t1")
    L.record_market(db, pipeline_id=inc["id"], impressions=150, clicks=5, source_ref="etsy:t2")
    assert L.calibrate(db, CLS)["verdict"] == "insufficient_evidence"
    assert P.ensure_incumbent(db, CLS)["id"] == inc["id"]
    # Enough evidence: the internally better hero gets a significantly lower CTR.
    L.record_market(db, pipeline_id=parent, impressions=1850, clicks=118, favourites=40,
                    purchases=9, source_ref="etsy:stats-export-a")
    L.record_market(db, pipeline_id=inc["id"], impressions=1850, clicks=55, favourites=20,
                    purchases=3, source_ref="etsy:stats-export-b")
    cal = L.calibrate(db, CLS)
    assert cal["verdict"] == "overturned", cal
    now_inc = P.ensure_incumbent(db, CLS)
    assert now_inc["id"] == parent and now_inc["params"]["hero_gap_ratio"] == 0.18
    from brambleloop.visual.rnd import models as M
    with db.session() as s:
        assert s.get(M.VisualExperiment, out["experiment"]).state == L.OVERTURNED
    # Future behaviour changed: the parameter is struck from the internal search...
    diag = L.diagnose(db, CLS)
    assert "hero_gap_ratio" in diag["overturned_params"], diag
    nxt = L.propose(db, CLS, diag, catalogue=L.catalogue_fp(cirs()))
    assert nxt is None or "hero_gap_ratio" not in nxt, nxt
    # ...the same change is not re-tried even though the internal judge still prefers it...
    again = L.experiment(db, CLS, {"hero_gap_ratio": 0.06}, cirs=cirs())
    assert again["state"] == L.MEMORY_SKIPPED, again
    # ...and the next generation uses the restored version.
    assert hero_sha(L.generate(db, CLS, cirs=cirs())) == hero_sha(before)
    summ = S.summary(db)
    item = next(i for i in summ["items"] if i["product_class"] == CLS)
    assert item["overturned"] and item["hero_ctr"]["reading"] == "MEASURED", item["hero_ctr"]


def test_market_readings_are_validated():
    db, _, _ = promoted_db()
    inc = P.ensure_incumbent(db, CLS)
    for bad in ({"impressions": 10, "clicks": 11, "source_ref": "x"},
                {"impressions": -1, "source_ref": "x"},
                {"impressions": 10, "source_ref": ""}):
        try:
            L.record_market(db, pipeline_id=inc["id"], **bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_status_summary_after_real_runs():
    db, _, _ = promoted_db()
    L.generate(db, CLS, cirs=cirs())
    summ = S.summary(db)
    for key in ("status", "as_of", "basis", "items", "sources"):
        assert key in summ, key
    assert summ["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN")
    assert summ["basis"] == "measured"
    item = next(i for i in summ["items"] if i["product_class"] == CLS)
    assert item["pipeline"]["generation"] == 2 and item["promotions_total"] == 1
    assert item["accepted_image_yield"]["value"] == 1.0
    cpa = item["cost_per_accepted_image"]
    assert cpa["value"] == 0.0 and cpa["basis"].startswith("measured"), cpa
    assert item["hero_ctr"]["value"] is None and item["hero_ctr"]["reading"] == "UNKNOWN"
    assert item["benchmark_gap"]["reading"] == "UNKNOWN"
    assert item["latency_s_median"]["reading"] == "MEASURED"
    trend = item["structural_rejection_trend"]
    assert isinstance(trend, list) and trend, trend
    work = S.next_work(db)
    assert work and all(w["green"] and w["department"] == "visual" for w in work), work
    assert any(w["kind"] == "visual.rnd.monitor" for w in work), work
    L.monitor(db, CLS)
    assert not any(w["kind"] == "visual.rnd.monitor" for w in S.next_work(db)), \
        "a monitored batch is not re-queued"
    import json
    json.dumps(summ)


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
