"""ENG-VIS-GALLERY: the generated-gallery gates, one condition at a time (fast, no chain).

* `eligibility.gallery_exception` (H2): passes only with every reading PASS, the computed
  honesty label, every EXCEPTION_PROVENANCE field from the record (references with sha256 and a
  CIR-derived reference), structural truth measured on the exact bytes, and the exact release.
  UNKNOWN / missing / fixture readings block. No Etsy AI-policy reading is required.
* `candidate_gates.exception_evidence`: emits the route's fields from the candidate record.
* `gallery_persist._status` / `frame_matrix`: UNMEASURED never counts as PASS.
* `shot_plans.flux_campaign_for`: seven distinct jobs per family; Laura where the family puts
  her; FIT and PROOF never generated.
* `gallery_budget`: the owner lowers the per-gallery cap; nobody raises it past code.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_vis_gallery_gates.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.gates.asset_truth import AssetClass  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402

SHA = "a" * 64
REL = "f" * 64


def _cand(job=el.LIFESTYLE):
    return el.Candidate(asset_id="x", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                        purpose=el.CONVERSION_CREATIVE, job=job,
                        position=1 if job == el.DESIRE else 2)


def _ev(job=el.LIFESTYLE, laura=True):
    label = el.honesty_label(AssetClass.AI_LIFESTYLE_CONCEPT, job)["label"]
    checks = {k: "PASS" for k in el.GALLERY_CHECKS + el.GALLERY_LAURA_CHECKS}
    return {"route": el.GALLERY_ROUTE, "label": label, "honesty_label": label,
            "presented_as": "ai_generated", "laura_present": laura, "sha256": SHA,
            "structural_sha256": SHA, "fidelity_release": REL, "checks": checks,
            "provenance": {"model": "flux-3", "release": REL, "prompt_version": "v1",
                           "receipt": "r" * 64, "disclosure": label,
                           "references": [{"sha256": "b" * 64, "kind": "pattern_derived"},
                                          {"sha256": "c" * 64, "kind": "laura_canonical"}]}}


def test_full_evidence_passes_for_every_gallery_job():
    for job in el.GALLERY_JOBS:
        assert el.gallery_exception(_cand(job), _ev(job)) == [], job
        assert el.verified_exception(_cand(job), _ev(job)) == [], job


def test_every_condition_blocks_alone():
    cases = {
        "label": lambda e: e.update(label="AI image"),
        "honesty_label": lambda e: e.update(honesty_label=None),
        "presented_as": lambda e: e.update(presented_as="photograph"),
        "structural_bytes": lambda e: e.update(structural_sha256="d" * 64),
        "structural_missing": lambda e: e.pop("structural_sha256"),
        "release": lambda e: e.update(fidelity_release="e" * 64),
        "no_cir_ref": lambda e: e["provenance"].update(references=[
            {"sha256": "c" * 64, "kind": "laura_canonical"}]),
        "ref_without_sha": lambda e: e["provenance"]["references"].append({"kind": "other"}),
        "disclosure_differs": lambda e: e["provenance"].update(disclosure="photo"),
    }
    for f in el.EXCEPTION_PROVENANCE:
        cases[f"prov_{f}"] = (lambda k: lambda e: e["provenance"].pop(k))(f)
    for name in el.GALLERY_CHECKS + el.GALLERY_LAURA_CHECKS:
        for bad in ("UNKNOWN", "FAIL", None):
            cases[f"{name}_{bad}"] = (lambda n, b: lambda e: e["checks"].update({n: b}))(
                name, bad)
    assert cases
    for name, mutate in cases.items():
        ev = copy.deepcopy(_ev())
        mutate(ev)
        assert el.gallery_exception(_cand(), ev), f"{name} did not block"


def test_proof_and_fit_are_never_generated_gallery_jobs():
    assert el.FIT not in el.GALLERY_JOBS and el.PROOF not in el.GALLERY_JOBS
    out = el.gallery_exception(_cand(el.SCALE), _ev(el.SCALE))
    assert out == []
    # FIT cannot even be a generated Candidate's job through may_export
    v = el.may_export(_cand(el.LIFESTYLE), [el.GateResult(g, el.PASSED) for g in el.GATES],
                      generated_evidence={**_ev(), "presented_as": "sample"})
    assert v["may_export"] is False


def test_no_laura_needs_no_laura_checks_but_laura_does():
    ev = _ev(laura=False)
    for k in el.GALLERY_LAURA_CHECKS:
        ev["checks"].pop(k)
    ev["checks"]["anatomy"] = "NOT_APPLICABLE"
    assert el.gallery_exception(_cand(), ev) == []
    ev["laura_present"] = True
    assert el.gallery_exception(_cand(), ev)


def test_no_etsy_ai_policy_gate_is_required_on_either_route():
    assert "etsy_policy" not in el.EXCEPTION_CHECKS
    assert "etsy_policy" not in el.GALLERY_CHECKS
    from brambleloop.visual import candidate_gates as CG

    pv = CG.publication_verdict({"sha256": SHA}, {}, None, False)
    assert CG.ETSY_POLICY_UNKNOWN not in pv["blockers"]


def test_may_export_with_gallery_evidence_and_four_gates():
    gates = [el.GateResult(g, el.PASSED) for g in el.GATES]
    assert el.may_export(_cand(el.DESIRE), gates, generated_evidence=_ev(el.DESIRE))[
        "may_export"] is True
    bad = _ev(el.DESIRE)
    bad["checks"]["motif_fidelity"] = "UNKNOWN"
    assert el.may_export(_cand(el.DESIRE), gates, generated_evidence=bad)["may_export"] is False
    # without the route the old F-852 refusal stands for a generated hero
    legacy = {k: v for k, v in _ev(el.DESIRE).items() if k != "route"}
    assert el.may_export(_cand(el.DESIRE), gates, generated_evidence=legacy)[
        "may_export"] is False


def test_exception_evidence_reads_the_record_not_constants():
    from brambleloop.visual import candidate_gates as CG

    label = el.honesty_label(CG.MEDIUM, el.DETAIL)["label"]
    checks = {"product_truth": {"status": "PASS", "sha256": SHA,
                                "fidelity": {"status": "PASS", "release_hash": REL}},
              "binding": {"status": "PASS", "release_hash": REL},
              "disclosure": {"status": "PASS", "label": label},
              "motif_fidelity": {"status": "PASS"}, "realism": {"status": "PASS"},
              "quality": {"status": "PASS"}, "anatomy": {"status": "NOT_APPLICABLE"}}
    cand = {"sha256": SHA, "model": "flux-3-pro", "prompt_version": "pv-7",
            "route": el.GALLERY_ROUTE, "provenance_kind": "ai_generated_autonomous",
            "references": [{"sha256": "b" * 64, "kind": "pattern_derived"}],
            "identity_evidence": {"request": {"request_sha256": "9" * 64}}}
    ev = CG.exception_evidence(cand, checks, el.DETAIL, False, other_publication_blockers=[])
    assert ev["route"] == el.GALLERY_ROUTE and ev["honesty_label"] == label
    assert ev["structural_sha256"] == SHA and ev["fidelity_release"] == REL
    p = ev["provenance"]
    assert (p["model"], p["prompt_version"], p["receipt"], p["release"]) == (
        "flux-3-pro", "pv-7", "9" * 64, REL)
    assert p["references"] == [{"sha256": "b" * 64, "kind": "pattern_derived"}]
    assert el.gallery_exception(_cand(el.DETAIL), {**ev, "laura_present": False}) == []
    # structural truth measured on other bytes is reported as such, and blocks
    checks2 = {**checks, "product_truth": {**checks["product_truth"], "sha256": "d" * 64}}
    ev2 = CG.exception_evidence(cand, checks2, el.DETAIL, False, other_publication_blockers=[])
    assert ev2["structural_sha256"] == "d" * 64
    assert el.gallery_exception(_cand(el.DETAIL), {**ev2, "laura_present": False})
    # a fixture-labelled PASS is UNKNOWN to the gate
    checks["motif_fidelity"] = {"status": "PASS", "fixture_only": True}
    ev = CG.exception_evidence(cand, checks, el.DETAIL, False, other_publication_blockers=[])
    assert ev["checks"]["motif_fidelity"] == "UNKNOWN"
    assert el.gallery_exception(_cand(el.DETAIL), ev)


def test_generated_hero_only_in_the_gallery_route():
    from brambleloop.visual import candidate_gates as CG

    assert CG.role("hero")["status"] == "FAIL"
    assert CG.role("hero", el.GALLERY_ROUTE)["status"] == "PASS"
    assert CG.role("hero", "other")["status"] == "FAIL"


def test_status_never_turns_unmeasured_into_pass():
    from brambleloop.visual import gallery_persist as GP

    assert GP._status({}, ("identity",))[0] == "UNMEASURED"
    assert GP._status({"identity": {"status": "UNKNOWN"}}, ("identity",))[0] == "UNMEASURED"
    assert GP._status({"identity": {"status": "PASS", "fixture_only": True}},
                      ("identity",))[0] == "UNMEASURED"
    assert GP._status({"identity": {"status": "PASS"}, "x": {"status": "UNKNOWN"}},
                      ("identity", "x"))[0] == "UNMEASURED"
    assert GP._status({"identity": {"status": "PASS"}, "x": {"status": "FAIL", "why": "w"}},
                      ("identity", "x"))[0] == "FAIL"
    assert GP._status({"a": {"status": "NOT_APPLICABLE"}}, ("a",))[0] == "NOT_APPLICABLE"
    assert GP._status({"a": {"status": "PASS"}}, ("a",))[0] == "PASS"
    assert GP._status({"a": {"status": "weird"}}, ("a",))[0] == "UNMEASURED"


def test_flux_campaign_seven_distinct_jobs_per_family():
    from brambleloop.visual import shot_plans as SP

    want = {"garment": "worn", "hat": "worn", "pillow": "soft", "amigurumi": "soft",
            "coaster": "small_goods", "basket": "small_goods", "blanket": "lived_with",
            "baby": "lived_with"}
    assert want
    for cat, fam in want.items():
        p = SP.flux_campaign_for(cat)
        assert p["family"] == fam, (cat, p["family"])
        assert SP.campaign_standard(p)["ok"], (cat, SP.campaign_standard(p))
        jobs = [r["job"] for r in p["roles"]]
        assert jobs == [j for j, _r in SP.FLUX_SLOTS]
        assert el.FIT not in jobs and el.PROOF not in jobs
        gen = [r for r in p["roles"] if r["generate"]]
        assert len(gen) == 6 and all(r["route"] == el.GALLERY_ROUTE for r in gen)
        assert [r["job"] for r in p["roles"] if not r["generate"]] == [el.CONTENTS]
        assert all(r["sources"][SP.DISCLOSED] == "not_in_route" for r in gen)
    worn = {r["job"]: r["laura"] for r in SP.flux_campaign_for("garment")["roles"]}
    assert worn[el.DESIRE] and worn[el.ANGLE] and worn[el.SCALE] and worn[el.LIFESTYLE]
    assert not worn[el.DETAIL] and not worn[el.COLOUR_CONTEXT]
    small = SP.flux_campaign_for("coaster")
    # D-OWNER-LAURA-ALL-FAMILIES: small goods were Laura-free; the owner ruled Laura is in
    # every family's lifestyle frame (her references show Laura at a table with the coasters).
    assert small["laura_in_campaign"]
    assert [r["job"] for r in small["roles"] if r["laura"]] == [el.LIFESTYLE]
    assert "construction" in [r for r in small["roles"] if r["job"] == el.ANGLE][0]["brief"]
    soft = {r["job"]: r["brief"] for r in SP.flux_campaign_for("pillow")["roles"]}
    assert "room" in soft[el.DESIRE] and "texture" in soft[el.DETAIL]


def test_owner_can_lower_the_gallery_cap_never_raise_it():
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.visual import gallery_budget as GB
    from brambleloop.visual import image_production as IP

    db = Database("sqlite:///" + tempfile.mkdtemp() + "/b.db", scratch=True)
    db.create_all()
    assert GB.effective_cap(db) == IP.MAX_SPEND_CAD_PER_GALLERY
    assert GB.set_owner_cap(db, 0.75, by="owner:test")["effective_cap_cad"] == 0.75
    assert IP._spend_plan("k", db)["max_spend_cad"] == 0.75
    for bad in (IP.MAX_SPEND_CAD_PER_GALLERY + 0.01, -1, "x"):
        try:
            GB.set_owner_cap(db, bad, by="owner:test")
            raise AssertionError(f"{bad!r} accepted")
        except GB.CapRefused:
            pass
    try:
        GB.set_owner_cap(db, 0.10, by="agent:publishing")
        raise AssertionError("a non-owner set the cap")
    except GB.CapRefused:
        pass
    assert GB.effective_cap(db) == 0.75
    GB.set_owner_cap(db, None, by="owner:test")
    assert GB.effective_cap(db) == IP.MAX_SPEND_CAD_PER_GALLERY
    # the route's call cap fits two anchors and six frames with bounded repairs; money is
    # unchanged
    route_key = IP.run_key("s", "1", "r", route="generated_gallery")
    assert IP._spend_plan(route_key, db)["call_count"] == IP.FLUX_MAX_GENERATION_CALLS
    assert IP._spend_plan(IP.run_key("s", "1", "r"), db)["call_count"] == \
        IP.MAX_GENERATION_CALLS
    assert IP.route_of_key(route_key) == "generated_gallery"
    assert IP.route_of_key(IP.run_key("s", "1", "r", ns="x")) == ""


def test_spend_guard_refuses_past_the_owner_cap():
    from brambleloop.visual import spend_plan

    plan = spend_plan.build(hypothesis="h", provider_model="m", call_count=20,
                            max_spend_cad=0.50, pass_criteria=["p"], fail_criteria=["f"])
    spend_plan.guard(plan, spent_cad=0.20, calls_made=1, next_cost_cad=0.25)
    try:
        spend_plan.guard(plan, spent_cad=0.30, calls_made=2, next_cost_cad=0.25)
        raise AssertionError("over the cap")
    except spend_plan.PlanRefused:
        pass


def test_frame_matrix_requires_the_release_cir_references_in_order():
    from types import SimpleNamespace

    from brambleloop.visual import gallery_persist as GP

    refs = [{"sha256": c * 64, "kind": "pattern_derived"} for c in "bcde"]
    row = SimpleNamespace(id=1, sha256=SHA, role="detail", model="m", references=refs,
                          prompt_version="p", provenance_kind="ai_generated_autonomous",
                          laura_present=False, technical_status="PASS", attempt=1,
                          checks={"_route": {"route": el.GALLERY_ROUTE}})
    want = [c * 64 for c in "bcde"]
    m = GP.frame_matrix(None, row, job=el.DETAIL, laura_expected=False, cir_references=want)
    assert m["gates"]["cir_references"]["status"] == "PASS"
    for other in (want[::-1], want[:3], [], None):
        m = GP.frame_matrix(None, row, job=el.DETAIL, laura_expected=False,
                            cir_references=other)
        assert m["gates"]["cir_references"]["status"] in ("FAIL", "UNMEASURED"), other
        assert m["ok"] is False
    # every other gate on this empty record is UNMEASURED, never PASS
    m = GP.frame_matrix(None, row, job=el.DETAIL, laura_expected=False, cir_references=want)
    assert m["ok"] is False
    assert m["gates"]["motif_fidelity"]["status"] == "UNMEASURED"
    # a Laura slot whose frame has no Laura FAILs identity
    m = GP.frame_matrix(None, row, job=el.LIFESTYLE, laura_expected=True, cir_references=want)
    assert m["gates"]["identity"]["status"] == "FAIL"


def test_evidence_never_counts_a_test_double_or_fixture_as_independent():
    from brambleloop.ops.production_evidence import _independent

    clean = {"identity": {"status": "PASS"}, "product_truth": {"status": "PASS",
                                                                "fidelity": {"status": "PASS"}}}
    assert _independent(clean) is True
    for bad in ({"identity": {"status": "PASS", "test_double": True}},
                {"identity": {"status": "PASS", "fixture_only": True}},
                {"product_truth": {"status": "PASS", "fidelity": {"test_double": "x"}}},
                {"product_truth": {"status": "PASS", "fidelity": {"fixture_only": True}}}):
        assert _independent({**clean, **bad}) is False, bad
    assert _independent(None) is False
    # underscore records (provenance, receipts) are not readings
    assert _independent({**clean, "_route": {"test_double": True}}) is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:2000])
    sys.exit(1 if fails else 0)
