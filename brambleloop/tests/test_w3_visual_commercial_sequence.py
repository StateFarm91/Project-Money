"""Listing image sequence policy (wave 3, lane H2; owner D-FB-16 item 4).

Frame one sells the finished dream; diagrams and engineering renders are demoted to evidence
frames, never deleted; gate-failed assets appear nowhere; Product Truth is unchanged.
Local, deterministic, no network, no provider, no spend.
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
_TMP = tempfile.mkdtemp(prefix="w3_visual_commercial_seq_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.visual.rnd import pipeline as P  # noqa: E402
from brambleloop.visual.rnd import sequence as Q  # noqa: E402

CLS = "coasters_tabletop"


def a(i, kind, accepted=True, medium="DIGITAL_TWIN_RENDER", value=None, **kw):
    return {"id": i, "kind": kind, "medium": medium, "accepted": accepted,
            "objective": {"value": value}, **kw}


def _engineering_first():
    return [a("eng", "engineering_render", value=0.99), a("chart", "stitch_chart"),
            a("render", "finished_product", value=0.5),
            a("life", "lifestyle_scene", medium="PHYSICAL_PRODUCT_PHOTO", value=0.7),
            a("dims", "dimensions"), a("pdf", "download_contents"), a("yarn", "yarn_materials"),
            a("close", "detail_closeup"), a("trust", "verification"), a("skill", "skill_level"),
            a("colours", "colourways")]


def test_aspirational_hero_first_and_truth_evidence_kept():
    assets = _engineering_first()
    plan = Q.plan(CLS, assets)
    assert plan["status"] == Q.OK, plan
    f = plan["frames"]
    assert f[0]["slot"] == Q.HERO and f[0]["kind"] == "lifestyle_scene", f[0]
    assert f[0]["eligibility_job"] == "DESIRE"
    assert len(f) <= Q.MAX_FRAMES
    placed = {x["asset_id"] for x in f}
    # Every truth-evidence asset keeps a frame: the diagram and chart are demoted, not dropped.
    for ev in ("eng", "chart", "dims", "pdf", "yarn", "close", "trust", "skill", "colours"):
        assert ev in placed, (ev, f)
    assert plan["truth_evidence_kept"], plan
    eng = next(x for x in f if x["asset_id"] == "eng")
    assert eng["slot"] == "construction" and eng["role"] == "evidence" and eng["position"] > 1
    assert plan["demoted"] and plan["demoted"][0]["id"] == "eng", plan["demoted"]
    # Evidence follows the buyer-question order.
    slots = [x["slot"] for x in f[1:]]
    firsts = list(dict.fromkeys(slots))
    assert firsts == [s for s in Q.EVIDENCE_SLOTS if s in firsts], slots
    assert Q.check(f, supplied_evidence_ids={"eng", "chart", "dims", "pdf", "yarn"}) == []


def test_a_diagram_is_never_the_hero_even_alone_or_top_scored():
    plan = Q.plan(CLS, [a("eng", "engineering_render", value=1.0),
                        a("chart", "stitch_chart", value=1.0)])
    assert plan["status"] == Q.NO_HERO and plan["hero"] is None, plan
    assert all(x["slot"] != Q.HERO for x in plan["frames"]), plan["frames"]
    assert {x["asset_id"] for x in plan["frames"]} == {"eng", "chart"}
    ok, why = Q.hero_eligible(a("eng", "engineering_render", value=1.0))
    assert not ok and "evidence" in why
    bad = [{"position": 1, "slot": "construction", "kind": "engineering_render",
            "asset_id": "eng", "role": "evidence"}]
    assert Q.check(bad), "a diagram-first order must be flagged"


def test_gate_failed_assets_appear_nowhere_and_concepts_need_export_eligibility():
    assets = [a("life_bad", "lifestyle_scene", accepted=False, value=1.0,
                failures=["LAURA_IDENTITY:FAIL"]),
              a("concept", "lifestyle_scene", medium="AI_LIFESTYLE_CONCEPT", value=0.95),
              a("render", "finished_product", value=0.4), a("chart", "stitch_chart")]
    plan = Q.plan(CLS, assets)
    ids = {x["asset_id"] for x in plan["frames"]}
    assert "life_bad" not in ids, "a gate failure is excluded from every position"
    assert plan["excluded"][0]["id"] == "life_bad"
    assert plan["hero"]["id"] == "render", plan["hero"]
    assets[1]["export_allowed"] = True
    assert Q.plan(CLS, assets)["hero"]["id"] == "concept"


def test_every_class_has_a_policy_and_laura_is_not_forced():
    for cls in P.PRODUCT_CLASSES:
        pol = Q.policy(cls)
        assert pol["hero_preference"] and set(pol["hero_preference"]) <= Q.ASPIRATIONAL_KINDS
        assert pol["evidence_order"] == list(Q.EVIDENCE_SLOTS)
    assert Q.policy("fitted_garments")["laura"] == "preferred"
    assert Q.policy("fitted_garments")["hero_preference"][0] == "on_model"
    assert Q.policy("baskets_storage")["laura"] == "not_default"
    assert Q.policy("baskets_storage")["hero_preference"][0] != "on_model"
    assert not (Q.NEVER_HERO_KINDS & Q.ASPIRATIONAL_KINDS)


def test_real_disclosed_gallery_sequences_with_the_finished_render_as_hero():
    from brambleloop.visual.rnd import gates as G
    from brambleloop.visual.rnd import loop as L

    cir = L.catalogue(["hexagon_coasters"])[CLS][0]
    frames = G.produce(cir, P.defaults(CLS))
    judged = [G.judge_frame(cir, f, i + 1, CLS) for i, f in enumerate(frames)]
    assets = Q.from_disclosed_gallery(frames, judged)
    # Present them diagram-first to prove order comes from policy, not input.
    plan = Q.plan(CLS, list(reversed(assets)))
    assert plan["status"] == Q.OK, plan
    assert plan["frames"][0]["kind"] == "finished_product"
    assert [x["slot"] for x in plan["frames"]] == [Q.HERO, "clarity", "dimensions"], plan
    assert all(j["gates"]["product_truth"]["status"] == "PASS" for j in judged)


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
