"""D-W4-F852-AMEND: the verified-exception route for generated product imagery.

F-852 is amended, not deleted. A generated frame exports only when every condition reads PASS;
any missing, UNKNOWN or FAIL condition blocks with its reason; F-853 compositing is mandatory
where feasible; F-856, F-858 and ASSET_CONCEPT_AS_HERO are unchanged; the deterministic and
owned-photo paths are unchanged. Offline, no spend.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.gates.asset_truth import AssetClass  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402

REL = "ab" * 32


def cand(job=el.LIFESTYLE, medium=AssetClass.AI_LIFESTYLE_CONCEPT, position=2,
         purpose=el.CONVERSION_CREATIVE):
    return el.Candidate(asset_id="x", medium=medium, purpose=purpose, job=job,
                        position=position)


def gates(outcome=el.PASSED):
    return [el.GateResult(g, outcome, "" if outcome != el.FAILED else "x") for g in el.GATES]


def evidence(job=el.LIFESTYLE, laura=True, scope="lifestyle"):
    label = el.honesty_label(AssetClass.AI_LIFESTYLE_CONCEPT, job)["label"]
    checks = {k: "PASS" for k in el.EXCEPTION_CHECKS + el.EXCEPTION_LAURA_CHECKS}
    return {"label": label, "presented_as": "ai_generated", "scope": scope,
            "laura_present": laura, "fidelity_release": REL, "checks": checks,
            "provenance": {"model": "flux-3-image",
                           "references": [{"sha256": "a" * 64}, {"sha256": "b" * 64}],
                           "release": REL, "prompt_version": "code-default:abc",
                           "receipt": "c" * 64, "disclosure": label}}


def export(ev, **kw):
    return el.may_export(cand(**kw), gates(), generated_evidence=ev)


def test_a_fully_verified_generated_frame_exports():
    out = export(evidence())
    assert out["may_export"] is True, out["blockers"]
    angle = el.may_export(cand(job=el.ANGLE), gates(), generated_evidence=evidence(el.ANGLE))
    assert angle["may_export"] is True, angle["blockers"]


def test_each_missing_unknown_or_failed_condition_blocks_with_its_reason():
    names = list(el.EXCEPTION_CHECKS) + list(el.EXCEPTION_LAURA_CHECKS)
    assert len(names) == 9
    for name in names:
        for bad in ("UNKNOWN", "FAIL", None):
            ev = evidence()
            if bad is None:
                del ev["checks"][name]
            else:
                ev["checks"][name] = bad
            out = export(ev)
            assert out["may_export"] is False, (name, bad)
            assert any(name in b and "UNKNOWN blocks" in b for b in out["blockers"]), \
                (name, bad, out["blockers"])
    assert len(el.EXCEPTION_PROVENANCE) == 6
    for key in el.EXCEPTION_PROVENANCE:
        ev = evidence()
        ev["provenance"][key] = None
        out = export(ev)
        assert not out["may_export"] and any("provenance incomplete" in b and key in b
                                             for b in out["blockers"]), key
    ev = evidence()
    ev["provenance"]["references"] = [{"kind": "x"}]
    assert not export(ev)["may_export"]
    ev = evidence()
    ev["fidelity_release"] = "cd" * 32
    assert any("exact release" in b for b in export(ev)["blockers"])
    for scope in ("", "hero", "lifestyle_hero"):
        ev = evidence()
        ev["scope"] = scope
        assert not export(ev)["may_export"], scope
    out = el.may_export(cand(job=el.LIFESTYLE), gates(), generated_evidence=evidence(
        scope="product_only"))
    assert any("may not do LIFESTYLE" in b for b in out["blockers"])
    # no evidence at all: refused, as before the amendment
    none = el.may_export(cand(), gates())
    assert not none["may_export"] and any("F-852" in b for b in none["blockers"])
    # every gate passed is still required on top
    failed = el.may_export(cand(), gates(el.NOT_RUN), generated_evidence=evidence())
    assert not failed["may_export"]
    assert not el.may_export(cand(), gates(), truth_verdict=el.FAILED,
                             generated_evidence=evidence())["may_export"]


def test_laura_gates_only_when_laura_appears():
    ev = evidence(laura=False)
    for k in el.EXCEPTION_LAURA_CHECKS:
        ev["checks"].pop(k)
    assert export(ev)["may_export"] is True
    ev["laura_present"] = True
    assert not export(ev)["may_export"]


def test_a_photo_label_or_presentation_is_refused():
    ev = evidence()
    ev["label"] = el.PHOTO_LABEL
    out = export(ev)
    assert not out["may_export"] and any("photograph" in b for b in out["blockers"])
    for presented in ("photo", "photograph", "proof", "physical_proof"):
        ev = evidence()
        ev["presented_as"] = presented
        assert any("never a photograph" in b for b in export(ev)["blockers"]), presented
    ev = evidence()
    ev["label"] = el.RENDER_LABEL
    assert any("disclosure" in b for b in export(ev)["blockers"])
    # a generated image can never claim PROOF (the medium cannot serve PHYSICAL_PROOF)
    try:
        cand(job=el.PROOF, purpose=el.PHYSICAL_PROOF)
        raise AssertionError("an AI concept was accepted as physical proof")
    except el.EligibilityRefused:
        pass


def test_owner_visual_approval_never_substitutes():
    ev = evidence()
    ev["checks"]["etsy_policy"] = "UNKNOWN"
    ev["owner_visual_approval"] = True
    ev["checks"]["owner_visual_approval"] = "PASS"
    assert not export(ev)["may_export"]


def test_f853_compositing_is_mandatory_where_feasible_and_roles_without_it_are_named():
    assert el.exception_roles_without_compositing() == [el.ANGLE, el.LIFESTYLE]
    for job in (el.DETAIL, el.SCALE, el.COLOUR_CONTEXT):
        scope = "detail" if job == el.DETAIL else "product_only"
        out = el.may_export(cand(job=job), gates(), generated_evidence=evidence(job, scope=scope))
        assert not out["may_export"] and any("F-853" in b for b in out["blockers"]), job
    assert all(why for _, why in el.COMPOSITING_FEASIBLE.values())


def test_hero_rule_and_unchanged_media_paths():
    # ASSET_CONCEPT_AS_HERO, unchanged: a generated hero never exports
    hero = el.may_export(cand(job=el.DESIRE, position=1), gates(),
                         generated_evidence=evidence(el.DESIRE))
    assert not hero["may_export"]
    from brambleloop.visual import candidate_gates as CG

    assert CG.role("hero")["status"] == "FAIL" and "ASSET_CONCEPT_AS_HERO" in CG.role("hero")["why"]
    # deterministic render and owned photograph: unchanged, evidence is ignored
    for medium, job in ((AssetClass.DIGITAL_TWIN_RENDER, el.DETAIL),
                        (AssetClass.PHYSICAL_PRODUCT_PHOTO, el.LIFESTYLE)):
        a = el.may_export(cand(job=job, medium=medium), gates())
        b = el.may_export(cand(job=job, medium=medium), gates(),
                          generated_evidence={"checks": {}})
        assert a["may_export"] is True and a == b, medium


def test_the_production_path_still_refuses_today_on_the_etsy_reading():
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    v = CG.evaluate(db, O.cand(role="lifestyle", release=O.RELEASE), judges=O.StubJudges(),
                    record_outfit_use=False)
    assert v["publishable"] is False
    assert any("etsy_policy is UNKNOWN" in b for b in v["publication"]["blockers"])
    assert any(CG.ETSY_POLICY_UNKNOWN == b for b in v["publication"]["blockers"])
    # the stub's Product Truth carries no fidelity reading: structural fidelity UNKNOWN blocks
    assert any("structural_fidelity is UNKNOWN" in b for b in v["publication"]["blockers"])


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
