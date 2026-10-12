"""The Visual R&D objective is an INTERSECTION (wave 3, lane H2; owner D-FB-16 item 5).

Hard gates (Product Truth, structure, Laura identity, anatomy, realism, ...) can never be traded
for desirability, brand or sales; desirability/commercial only rank gate-passing candidates;
the internal judges are PROXY; UNKNOWN is never scored 0. Local, deterministic, no spend.
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
_TMP = tempfile.mkdtemp(prefix="w3_visual_commercial_obj_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual.rnd import hero as H  # noqa: E402
from brambleloop.visual.rnd import judges as J  # noqa: E402
from brambleloop.visual.rnd import models as M  # noqa: E402
from brambleloop.visual.rnd import objective as O  # noqa: E402
from brambleloop.visual.rnd import pipeline as P  # noqa: E402

_N = [0]


def fresh_db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/t{_N[0]}.sqlite")
    db.create_all()
    M.ensure_tables(db)
    return db


def passing(**over):
    g = {name: {"status": "PASS"} for name in O.HARD_GATES}
    g["laura_identity"] = {"status": "N/A"}
    g.update({k: {"status": v} for k, v in over.items()})
    return g


def comps(d=None, b=None, commercial=None):
    out = {"desirability": {"value": d, "basis": "PROXY"},
           "brand_consistency": {"value": b, "basis": "PROXY"}}
    if commercial is not None:
        out["commercial"] = {"value": commercial, "basis": "measured (marketplace export)"}
    return out


def test_no_score_can_buy_back_a_hard_gate():
    for gate in O.NON_TRADEABLE + ("disclosure", "mobile_thumbnail"):
        for status in ("FAIL", "UNKNOWN"):
            ev = O.evaluate({"gates": passing(**{gate: status}),
                             "components": comps(1.0, 1.0, commercial=1.0)})
            assert not ev["eligible"] and ev["value"] is None, (gate, status, ev)
            assert f"{gate.upper()}:{status}" in ev["failures"]
    # A perfect-scoring similar-woman frame loses to a modest true one ...
    sel = O.select([
        {"id": "similar_woman", "gates": passing(laura_identity="FAIL"),
         "components": comps(1.0, 1.0, commercial=1.0)},
        {"id": "true", "gates": passing(), "components": comps(0.3, 0.3)}])
    assert sel["winner"] == "true", sel
    assert sel["ineligible"][0]["id"] == "similar_woman"
    # ... and when every candidate fails a gate, nothing wins.
    assert O.select([{"id": "x", "gates": passing(product_truth="FAIL"),
                      "components": comps(1.0, 1.0)}])["winner"] is None
    # A missing gate is UNKNOWN, which blocks.
    g = passing()
    del g["anatomy"]
    assert not O.evaluate({"gates": g, "components": comps(1, 1)})["eligible"]


def test_gates_cannot_be_weighted():
    for name in ("laura_identity", "product_truth", "photorealism", "anatomy", "structure",
                 "identity_threshold", "skip_gate", "min_accept"):
        try:
            O.weights({name: 0.0})
        except O.ObjectiveRefused:
            continue
        raise AssertionError(f"weighting {name} was allowed")
    assert O.weights({"desirability": 0.5})["desirability"] == 0.5


def test_unknown_components_are_left_out_not_zero_and_measured_commerce_dominates():
    ev = O.evaluate({"gates": passing(), "components": comps(0.8, None)})
    assert ev["value"] == 0.8 and "brand_consistency" in ev["unknown"], ev
    assert ev["basis"] == "proxy"
    nothing = O.evaluate({"gates": passing(), "components": {}})
    assert nothing["eligible"] and nothing["value"] is None and nothing["basis"] == "unknown"
    proxy_hi = O.evaluate({"gates": passing(), "components": comps(0.9, 0.9, commercial=0.1)})
    proxy_lo = O.evaluate({"gates": passing(), "components": comps(0.4, 0.4, commercial=0.9)})
    assert proxy_hi["basis"] == "market" and proxy_lo["value"] > proxy_hi["value"], (
        proxy_hi, proxy_lo)


def test_judges_are_labelled_proxy_and_slots_stay_unknown():
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (400, 400), (244, 239, 232)).save(buf, format="PNG")
    png = buf.getvalue()
    r = J.judge_all(png)
    assert r["desirability"]["basis"] == J.PROXY and "PROXY" in r["desirability"]["label"]
    assert r["brand_consistency"]["basis"] == J.PROXY
    assert r["brand_consistency"]["metrics"]["palette_provenance"]
    assert r["blind_benchmark"]["value"] is None and r["blind_benchmark"]["reading"] == "UNKNOWN"
    assert r["photographic_quality"]["reading"] == "N/A"
    photo = J.photographic_quality(medium="PHYSICAL_PRODUCT_PHOTO")
    assert photo["value"] is None and photo["reading"] == "UNKNOWN"
    # A flat cream frame is on-palette but not desirable at thumbnail scale.
    assert r["desirability"]["value"] < 0.5 < r["brand_consistency"]["value"], r


def test_hero_selection_never_promotes_a_gate_failure():
    db = fresh_db()
    cls = "accessories"
    with M.session(db) as s:
        s.add(M.VisualHeroVariant(product_class=cls, treatment="owned_photo_hero",
                                  style_key=f"{cls}:owned_photo_hero:x", state=H.INCUMBENT,
                                  gates=passing(), accepted=True,
                                  objective={"components": comps(0.3, 0.3)}))
        s.add(M.VisualHeroVariant(product_class=cls, treatment="laura_on_model_lifestyle",
                                  style_key=f"{cls}:laura_on_model_lifestyle:y",
                                  state=H.CANDIDATE, gates=passing(laura_identity="FAIL"),
                                  accepted=False,
                                  objective={"components": comps(1.0, 1.0, commercial=1.0)}))
    d = H._select(db, cls, now=H._now())
    assert not d["promoted"] and d["ineligible"], d
    assert H.incumbent(db, cls)["treatment"] == "owned_photo_hero"
    lost = next(v for v in H.variants(db, cls) if v["treatment"] == "laura_on_model_lifestyle")
    assert lost["state"] == H.REJECTED and "LAURA_IDENTITY:FAIL" in lost["why"], lost


def test_paid_hero_challengers_are_queued_not_run_and_tunables_stay_guarded():
    db = fresh_db()
    out = H.challenge(db, "fitted_garments", cirs=[])
    assert "laura_on_model_lifestyle" in out["queued"] and "lifestyle_scene" in out["queued"]
    vs = H.variants(db, "fitted_garments")
    assert vs and all(v["state"] in (H.GATED_SPEND, H.UNAVAILABLE) for v in vs), vs
    assert H.incumbent(db, "fitted_garments") is None, "no free producer: hero is UNKNOWN"
    st = H.status(db, "fitted_garments")
    assert st["incumbent"] is None and st["incumbent_reading"].startswith("UNKNOWN")
    from sqlalchemy import select
    with db.session() as s:
        assert not list(s.scalars(select(M.VisualJudgement))), "nothing was generated"
    assert H.TREATMENTS
    for t in H.TREATMENTS.values():
        assert t["classes"], t
        for cls in t["classes"]:
            if t["params"]:
                assert P.check_change(cls, t["params"]) == [], (t, cls)


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
