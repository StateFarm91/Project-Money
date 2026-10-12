"""Visual R&D guard rails (wave 3, lane H): gates are never tunable, Laura identity is a hard
independent gate, paid challengers are queued and never executed, and the status provider
reports UNKNOWN rather than zeros. Fast: nothing here renders an image.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w3_visual_rnd_guard_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402
from brambleloop.visual import identity  # noqa: E402
from brambleloop.visual.rnd import loop as L  # noqa: E402
from brambleloop.visual.rnd import pipeline as P  # noqa: E402
from brambleloop.visual.rnd import status as S  # noqa: E402

_N = [0]

GATE_WEAKENING = (
    {"structure_pass_threshold": 0.5},
    {"laura_identity_id": "laura-v16-somebody-similar"},
    {"identity_tolerance": 0.4},
    {"face_match_min": 0.1},
    {"photoreal_min_score": 0.1},
    {"anatomy_check": 0},
    {"skip_gates": 1},
    {"disclosure_text": "photo"},
    {"product_truth": 0},
    {"min_sample": 1},
    {"spend_ceiling_cad": 500},
    {"benchmark_quarantine": 0},
    {"accept_unknown": 1},
    {"hero_gap_ratio": 0.06, "verifier_off_palette": 0.5},
)


def fresh_db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/g{_N[0]}.sqlite")
    db.create_all()
    return db


def test_tunable_surface_is_declared_and_safe():
    assert P.TUNABLES
    stages = {t.stage for t in P.TUNABLES.values()}
    assert {"renderer_layout", "post_processing", "encode", "provider_model", "lighting",
            "camera", "composition", "crop_thumbnail", "control",
            "laura_reproduction"} <= stages, stages
    for name in P.TUNABLES:
        assert P.check_change(next(iter(P.TUNABLES[name].classes)),
                              {name: P.TUNABLES[name].default}) == [], name
    # Laura reproduction varies HOW the canonical Laura is reproduced, never WHO.
    choices = P.TUNABLES["laura_reproduction"].choices
    assert choices and all(c.startswith("canonical_") for c in choices), choices
    # The tunable never names an identity: WHO she is comes only from the owner-authorised
    # canonical record (D-FB-14 today), which no promotion can change.
    assert canonical.IDENTITY_ID.startswith("laura-") and canonical.AUTHORISED_IDENTITY_CHANGES
    assert not any(canonical.IDENTITY_ID in c for c in choices), choices


def test_invariant_refuses_every_gate_weakening():
    db = fresh_db()
    before = P.ensure_incumbent(db, "coasters_tabletop")
    assert GATE_WEAKENING
    for change in GATE_WEAKENING:
        out = L.experiment(db, "coasters_tabletop", change, cirs=[])
        assert out["state"] == L.REFUSED, (change, out)
        assert out["refusals"], change
    for change in ({"hero_gap_ratio": 0.9}, {"lighting_preset": "neon"}, {"brand_new": 1},
                   {"hero_gap_ratio": 0.06, "HERO-GAP-RATIO": 0.07}):
        assert L.experiment(db, "coasters_tabletop", change, cirs=[])["state"] == L.REFUSED
    assert L.experiment(db, "baskets_storage", {"hero_gap_ratio": 0.06},
                        cirs=[])["state"] == L.REFUSED
    after = P.ensure_incumbent(db, "coasters_tabletop")
    assert after == before, "a refused change must not touch the running pipeline"
    versions = P.versions(db, "coasters_tabletop")
    assert len(versions) == 1, "no candidate version is created for a refused change"
    refused = [les for les in L.lessons(db, limit=200) if les["kind"] == "refused"]
    assert len(refused) >= len(GATE_WEAKENING), len(refused)
    # The gate list is code: no version carries one, so no promotion can drop a gate.
    assert "gates" not in after["params"] and "structure" in P.GATES and \
        "laura_identity" in P.GATES


def test_laura_identity_is_a_hard_independent_gate():
    db = fresh_db()
    all_match = {d: identity.MATCH for d in canonical.LOCKED_FACE_DIMENSIONS}
    good = {g: {"status": "PASS"} for g in P.GATES}
    similar = dict(all_match)
    similar[next(iter(canonical.LOCKED_FACE_DIMENSIONS))] = identity.DRIFT
    # A similar woman fails, even when the caller hands in a PASS for the identity gate.
    out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=good,
                             identity_scored=similar, source="test:vision-review")
    assert not out["accepted"], out
    assert out["gates"]["laura_identity"]["status"] == "FAIL"
    assert any(f.startswith("LAURA_IDENTITY:FAIL") for f in out["failures"]), out
    # No reading at all is not Laura either.
    out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=good,
                             identity_scored=None, source="test:vision-review")
    assert not out["accepted"] and out["gates"]["laura_identity"]["status"] == "UNKNOWN"
    # Laura, but anatomy unjudged: still not accepted (gates are independent).
    partial = {k: v for k, v in good.items() if k != "anatomy"}
    out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=partial,
                             identity_scored=all_match, source="test:vision-review")
    assert not out["accepted"] and any(f.startswith("ANATOMY:UNKNOWN") for f in out["failures"])
    # K12 (F-213/F-219/F-677/F-732) tightened this door: one judge's all-match reading with
    # caller-supplied PASS gates is no longer accepted. Identity needs a proven current
    # reference, a judge pair and the biometric floor (`visual.identity_gate`); product
    # truth needs deterministic evidence (`visual.final_image_gate`). The accepted path
    # with full evidence is tests/test_w3_k12_model_photography.py
    # ::test_f677_and_f732_rnd_door_overrides_caller_pass.
    out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=good,
                             identity_scored=all_match, source="test:vision-review")
    assert not out["accepted"], out
    assert out["gates"]["laura_identity"]["status"] == "UNKNOWN", out["gates"]
    assert out["gates"]["product_truth"]["status"] == "UNKNOWN", out["gates"]
    summ = S.summary(db)
    item = next(i for i in summ["items"] if i["product_class"] == "laura_on_model")
    # Four Laura-bearing frames judged; none is proven Laura and none passed every gate --
    # measured as 0.0 over four frames, not UNKNOWN.
    assert item["laura_identity_consistency"]["value"] == 0.0, item
    assert item["laura_identity_consistency"]["reading"] == "MEASURED", item
    assert item["accepted_image_yield"]["value"] == 0.0, item


def test_paid_challengers_are_planned_never_executed():
    db = fresh_db()
    plan = L.plan_paid(db, "laura_on_model")
    assert plan["state"] == L.GATED_SPEND and plan["new"], plan
    assert plan["cost_basis"].startswith(("estimated", "unknown")), plan
    again = L.plan_paid(db, "laura_on_model")
    assert again["experiment"] == plan["experiment"] and not again["new"]
    ran = L.execute_paid(db, plan["experiment"])
    assert ran["executed"] is False and ran["allowed"] is False, ran
    assert L.paid_execution_gate()["allowed"] is False
    # A paid stage mixed into a deterministic change is still only planned.
    mixed = L.experiment(db, "coasters_tabletop",
                         {"hero_gap_ratio": 0.06, "lighting_preset": "overcast_daylight"},
                         cirs=[])
    assert mixed["state"] == L.GATED_SPEND, mixed
    from sqlalchemy import select

    from brambleloop.visual.rnd import models as M
    with db.session() as s:
        assert not list(s.scalars(select(M.VisualJudgement))), "nothing was generated"
    assert P.ensure_incumbent(db, "coasters_tabletop")["generation"] == 1
    work = S.next_work(db)
    assert work, work
    assert all(w["green"] for w in work)
    assert not [w for w in work if "paid" in w["kind"] or "spend" in w["reason"].lower()]
    item = next(i for i in S.summary(db)["items"] if i["product_class"] == "laura_on_model")
    assert item["paid_challengers_gated"], item


def test_summary_never_reports_unknown_as_zero():
    empty = Database(f"sqlite:///{_TMP}/empty.sqlite")
    s = S.summary(empty)
    assert s["status"] == "UNKNOWN" and s["items"] == [] and s["sources"], s
    assert S.summary(object())["status"] == "UNKNOWN"
    work = S.next_work(empty)
    assert [w["kind"] for w in work] == ["visual.rnd.bootstrap"], work
    db = fresh_db()
    L.plan_paid(db, "accessories")
    s = S.summary(db)
    assert s["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN") and s["items"]
    for item in s["items"]:
        for key in ("hero_ctr", "listing_conversion", "refund_rate", "benchmark_gap",
                    "cost_per_accepted_image", "accepted_image_yield"):
            assert item[key]["value"] is None and item[key]["reading"] == "UNKNOWN", \
                (item["product_class"], key, item[key])
    json.dumps(s)


def test_renderer_layout_default_is_byte_identical_and_bounded():
    from brambleloop.visual import disclosed_render as D

    assert D._layout_params(None) == {} and D._layout_params({}) == {}
    assert D._layout_params({"hero_gap_ratio": 0.06}) == {"hero_gap_ratio": 0.06}
    for bad in ({"hero_gap_ratio": 0.9}, {"camera": 1}, {"hero_gap_ratio": True}):
        try:
            D._layout_params(bad)
        except D.RenderRefused:
            continue
        raise AssertionError(f"accepted {bad}")


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
