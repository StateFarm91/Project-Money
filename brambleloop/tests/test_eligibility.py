"""What an asset is made of, what it is for, and why those are different questions.

Requirements 57, 58, 65, 69. The requirement's own sentence gives away the design: *a
technically correct chart cannot be promoted to hero merely because it rendered
successfully.* Rendering successfully is a fact about the medium. Being the hero is a
question about the purpose, and `AssetClass` only ever held the first.

Four tests here carry the substance: a chart cannot do DESIRE; two frames doing one job is
the defect rather than two similar images; a gate that never ran has not passed; and a
disclaimer is never permission.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.gates.asset_truth import AssetClass  # noqa: E402
from brambleloop.publish import eligibility as E  # noqa: E402


def _cand(**kw) -> E.Candidate:
    args = dict(asset_id="a1", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                purpose=E.CONVERSION_CREATIVE, job=E.DESIRE, position=1)
    args.update(kw)
    return E.Candidate(**args)


def _all_gates(outcome: str = E.PASSED) -> list[E.GateResult]:
    return [E.GateResult(gate=g, outcome=outcome,
                         why="" if outcome != E.FAILED else "something was wrong")
            for g in E.GATES]


# ---- two axes, not one (#57) ----------------------------------------------


def test_a_chart_cannot_become_the_hero_by_rendering_successfully():
    """The requirement's own example, encoded rather than described."""
    chart = _cand(asset_id="chart", medium=AssetClass.DIGITAL_TWIN_RENDER,
                  purpose=E.ENGINEERING_EVIDENCE, job=E.DESIRE)
    out = E.may_serve(chart)
    assert out["may_serve"] is False
    assert "not by ENGINEERING_EVIDENCE" in out["why"]


def test_the_same_medium_can_serve_a_different_purpose():
    """Purpose is orthogonal to medium: the twin render is fine doing DETAIL."""
    render = _cand(asset_id="detail", medium=AssetClass.DIGITAL_TWIN_RENDER,
                   purpose=E.ENGINEERING_EVIDENCE, job=E.DETAIL, position=3)
    assert E.may_serve(render)["may_serve"] is True


def test_an_ai_concept_is_not_physical_proof_whatever_it_is_labelled():
    try:
        _cand(medium=AssetClass.AI_LIFESTYLE_CONCEPT, purpose=E.PHYSICAL_PROOF, job=E.PROOF)
    except E.EligibilityRefused as e:
        assert "whatever it is labelled" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a concept image claimed to be proof")


def test_only_a_photograph_can_do_the_proof_job():
    assert E.JOB_PURPOSES[E.PROOF] == (E.PHYSICAL_PROOF,)
    assert E.PHYSICAL_PROOF in E.MEDIUM_PURPOSES[AssetClass.PHYSICAL_PRODUCT_PHOTO]
    for medium, purposes in E.MEDIUM_PURPOSES.items():
        if medium is AssetClass.PHYSICAL_PRODUCT_PHOTO:
            continue
        assert E.PHYSICAL_PROOF not in purposes, medium


def test_every_purpose_the_requirement_names_exists():
    for name in ("ENGINEERING_EVIDENCE", "CUSTOMER_INFORMATION", "CONVERSION_CREATIVE",
                 "PHYSICAL_PROOF"):
        assert name in E.PURPOSES


def test_an_invented_purpose_is_refused():
    try:
        _cand(purpose="LOOKS_NICE")
    except E.EligibilityRefused as e:
        assert "is not a purpose" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented purpose was accepted")


# ---- one job per frame (#65) ----------------------------------------------


def test_every_job_the_requirement_names_exists():
    for job in ("DESIRE", "SCALE", "DETAIL", "CONTENTS", "DIFFICULTY", "MATERIALS",
                "SIZING", "PATTERN_PREVIEW", "PROOF", "CROSS_SELL"):
        assert job in E.JOBS
    assert len(E.JOBS) == 10


def test_two_frames_doing_one_job_is_the_defect_not_two_similar_images():
    """Five genuinely different charts all doing DETAIL: every pixel comparison passes it."""
    frames = [
        _cand(asset_id="hero", position=1, job=E.DESIRE),
        _cand(asset_id="d1", position=2, job=E.DETAIL,
              medium=AssetClass.DIGITAL_TWIN_RENDER, purpose=E.ENGINEERING_EVIDENCE),
        _cand(asset_id="d2", position=3, job=E.DETAIL,
              medium=AssetClass.DIGITAL_TWIN_RENDER, purpose=E.ENGINEERING_EVIDENCE),
    ]
    out = E.check_set(frames)
    assert out["ok"] is False
    dup = [p for p in out["problems"] if p["kind"] == "duplicate_job"]
    assert dup and dup[0]["job"] == E.DETAIL
    assert "no comparison of the images themselves would find it" in dup[0]["why"]


def test_a_frame_whose_job_nothing_buys_is_refused():
    try:
        _cand(job="LOOKS_PRETTY")
    except E.EligibilityRefused as e:
        assert "removed rather than reordered" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a frame with no commercial job was accepted")


def test_frame_one_must_be_the_hero_doing_desire():
    out = E.may_serve(_cand(asset_id="size", position=1, job=E.SCALE,
                            medium=AssetClass.INFOGRAPHIC,
                            purpose=E.CUSTOMER_INFORMATION))
    assert out["may_serve"] is False
    assert "only frame most shoppers see" in out["why"]


def test_two_assets_claiming_one_position_is_a_collision():
    frames = [_cand(asset_id="a", position=1),
              _cand(asset_id="b", position=1, job=E.DESIRE)]
    out = E.check_set(frames)
    assert any(p["kind"] == "position_collision" for p in out["problems"])


def test_a_set_with_no_hero_is_a_problem():
    out = E.check_set([_cand(asset_id="s", position=2, job=E.SCALE,
                             medium=AssetClass.INFOGRAPHIC,
                             purpose=E.CUSTOMER_INFORMATION)])
    assert any(p["kind"] == "no_hero" for p in out["problems"])


def test_missing_jobs_are_listed_rather_than_refused():
    """A shop adding a frame per uncovered job is padding the gallery for a checklist."""
    out = E.check_set([_cand()])
    assert out["ok"] is True
    assert len(out["jobs_missing"]) == 9
    assert "padding the gallery" in out["note"]


def test_an_empty_set_is_refused():
    try:
        E.check_set([])
    except E.EligibilityRefused as e:
        assert "is not a set" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an empty listing set was accepted")


# ---- four gates, and one that did not run (#58) ---------------------------


def test_every_gate_the_requirement_names_exists():
    for gate in ("DATA_TRUTH", "LAYOUT_QA", "COMMERCIAL_QA", "POLICY_PROVENANCE"):
        assert gate in E.GATES
    assert len(E.GATES) == 4


def test_all_four_gates_passing_exports():
    out = E.may_export(_cand(), _all_gates())
    assert out["may_export"] is True
    assert out["blockers"] == []


def test_a_gate_that_never_ran_has_not_passed():
    """The commonest way an unchecked asset reaches a customer."""
    out = E.may_export(_cand(), _all_gates()[:3])
    assert out["may_export"] is False
    assert out["gates"][E.POLICY_PROVENANCE]["outcome"] == E.NOT_RUN
    assert "never wired up" in out["why"]


def test_no_gates_at_all_does_not_export():
    out = E.may_export(_cand(), [])
    assert out["may_export"] is False
    assert all(out["gates"][g]["outcome"] == E.NOT_RUN for g in E.GATES)


def test_one_failed_gate_prevents_export():
    results = _all_gates()[:3] + [E.GateResult(gate=E.POLICY_PROVENANCE, outcome=E.FAILED,
                                               why="the AI disclosure is missing")]
    out = E.may_export(_cand(), results)
    assert out["may_export"] is False
    assert "failed: POLICY_PROVENANCE" in out["why"]


def test_a_boolean_outcome_is_refused():
    try:
        E.GateResult(gate=E.DATA_TRUTH, outcome="ok")
    except E.EligibilityRefused as e:
        assert "indistinguishable from one that passed" in str(e)
    else:  # pragma: no cover
        raise AssertionError("'ok' was accepted as a gate outcome")


def test_a_failing_gate_must_say_why():
    try:
        E.GateResult(gate=E.DATA_TRUTH, outcome=E.FAILED)
    except E.EligibilityRefused as e:
        assert "did not say why" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a silent failure was accepted")


def test_two_verdicts_for_one_gate_let_somebody_choose():
    results = _all_gates() + [E.GateResult(gate=E.DATA_TRUTH, outcome=E.FAILED,
                                           why="a second opinion")]
    try:
        E.may_export(_cand(), results)
    except E.EligibilityRefused as e:
        assert "chooses which to read" in str(e)
    else:  # pragma: no cover
        raise AssertionError("one gate reported twice and export accepted it")


# ---- a label is not a licence (#69) ---------------------------------------


def test_the_label_is_computed_from_the_medium_rather_than_chosen():
    render = E.honesty_label(AssetClass.DIGITAL_TWIN_RENDER, E.DESIRE)
    photo = E.honesty_label(AssetClass.PHYSICAL_PRODUCT_PHOTO, E.DESIRE)
    assert render["required"] is True and "not a photograph" in render["label"]
    assert photo["required"] is False and photo["label"] == ""
    assert "the thing itself" in photo["why"]


def test_the_distinction_is_material_only_where_it_could_mislead():
    material = E.honesty_label(AssetClass.DIGITAL_TWIN_RENDER, E.DETAIL)
    not_material = E.honesty_label(AssetClass.DIGITAL_TWIN_RENDER, E.CONTENTS)
    assert material["required"] is True
    assert not_material["required"] is False
    assert "trains buyers to read nothing" in not_material["why"]


def test_a_disclaimer_does_not_make_a_failing_asset_exportable():
    """#69's own sentence: do not use a disclaimer as permission."""
    candidate = _cand(medium=AssetClass.DIGITAL_TWIN_RENDER, purpose=E.CONVERSION_CREATIVE,
                      job=E.DESIRE)
    label = E.honesty_label(candidate.medium, candidate.job)
    assert label["required"] is True and label["label"]

    out = E.may_export(candidate, _all_gates(), truth_verdict=E.FAILED)
    assert out["may_export"] is False
    assert "a disclaimer is not permission" in out["why"]


def test_the_truth_verdict_is_consulted_independently_of_the_label():
    candidate = _cand()
    with_label = E.may_export(candidate, _all_gates(), truth_verdict=E.PASSED)
    without = E.may_export(candidate, _all_gates(), truth_verdict=None)
    assert with_label["may_export"] is True and without["may_export"] is True
    refused = E.may_export(candidate, _all_gates(), truth_verdict=E.FAILED)
    assert refused["may_export"] is False


def test_the_label_says_out_loud_that_it_is_not_a_licence():
    out = E.honesty_label(AssetClass.AI_LIFESTYLE_CONCEPT, E.DESIRE)
    assert "never turns a failing asset into a passing one" in out["not_a_licence"]


def test_an_invented_job_has_no_label():
    try:
        E.honesty_label(AssetClass.DIGITAL_TWIN_RENDER, "VIBES")
    except E.EligibilityRefused as e:
        assert "is not a frame job" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a label was computed for a job that does not exist")


def test_state_names_both_axes_and_the_chart_case():
    out = E.state()
    assert set(out["requirements"]) == {57, 58, 65, 69}
    assert "rendering is a fact about the medium" in out["note"]
    assert any("chart-as-hero" in r for r in out["refuses"])


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
