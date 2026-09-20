"""Choosing a generator by measuring it, and the ways a benchmark reports what it did not measure.

The owner's instruction is that quality decides and a modestly more expensive model that
materially outperforms is worth paying for. That makes the dangerous failure a benchmark
that quietly becomes a price comparison -- by having no results, by dropping samples to fit
a budget, or by scoring a partial rubric and averaging the gaps away.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import image_bench as B  # noqa: E402


def _result(model, **means):
    """A Result whose every render scored the same, so the mean is the given number."""
    r = B.Result(model=model)
    row = {d.key: means.get(d.key, 3) for d in B.RUBRIC}
    r.scores = [dict(row) for _ in range(5)]
    return r


# ---- what is decided before anything is rendered ----------------------------


def test_a_model_with_no_reference_conditioning_leaves_on_the_requirement():
    """"Most photorealistic available" is true of it and irrelevant: an identity lock is
    conditioning, not a better prompt, so #200 and #201 are unmeetable."""
    out = B.eligible()
    excluded = {e["model"] for e in out["excluded"]}
    assert "imagen-4-ultra" in excluded
    assert out["excluded_on"] == "a requirement, not a score"
    assert all(c["can_hold_an_identity"] for c in out["benchmarked"])


def test_published_capability_is_labelled_as_a_claim_rather_than_a_finding():
    for candidate in B.CANDIDATES:
        assert "Not a measurement" in candidate.to_dict()["claim_basis"]


def test_the_plan_is_answerable_before_any_credential_exists():
    plan = B.plan()
    assert plan["runnable"] is False
    assert "credentials" in plan["blocked_on"]
    assert plan["total_cad"] < B.BENCHMARK_CEILING_CAD
    assert plan["images_total"] == len(plan["models"]) * plan["images_per_model"]


def test_a_plan_over_the_ceiling_refuses_rather_than_trimming_samples():
    """A benchmark that drops samples to fit a budget measures a different thing from the
    one it reports."""
    original = B.BENCHMARK_CEILING_CAD
    raised = None
    try:
        B.BENCHMARK_CEILING_CAD = 0.5
        B.plan()
    except B.BenchmarkRefused as exc:
        raised = exc
    finally:
        B.BENCHMARK_CEILING_CAD = original
    assert raised is not None and "different thing" in str(raised)


# ---- the judge ---------------------------------------------------------------


def test_every_rubric_line_cites_a_requirement():
    """A rubric line with no requirement behind it is somebody's taste."""
    for dimension in B.RUBRIC + (B.IDENTITY_DIMENSION,):
        assert isinstance(dimension.requirement, int) and dimension.requirement > 0


def test_the_judge_is_never_told_which_model_rendered_the_image():
    prompt = B.score_prompt()
    for candidate in B.CANDIDATES:
        assert candidate.key not in prompt
        assert candidate.what not in prompt


def test_a_partial_judgement_is_refused_rather_than_averaged():
    """It would average into a total as though the model had done well on what nobody asked."""
    raised = None
    try:
        B.parse_scores('{"stitch_fidelity": 3}')
    except B.BenchmarkRefused as exc:
        raised = exc
    assert raised is not None and "not scored" in str(raised)


def test_a_score_outside_the_scale_is_refused():
    raised = None
    try:
        B.parse_scores('{"' + '": 3, "'.join(d.key for d in B.RUBRIC) + '": 9}')
    except B.BenchmarkRefused as exc:
        raised = exc
    assert raised is not None and "outside" in str(raised)


def test_a_complete_judgement_parses():
    body = "{" + ", ".join(f'"{d.key}": 3' for d in B.RUBRIC) + ', "notes": {}}'
    assert B.parse_scores(body) == {d.key: 3 for d in B.RUBRIC}


# ---- the decision ------------------------------------------------------------


def test_no_measurement_names_nobody_rather_than_falling_back_to_the_cheapest():
    """The decision the owner explicitly ruled out, and what a resultless benchmark becomes."""
    out = B.decide([])
    assert out["decided"] is False
    assert "cheapest candidate is the decision the owner ruled out" in out["why"]
    assert "winner" not in out


def test_a_model_that_cannot_render_crochet_is_out_at_any_price():
    """A generator that fails the fabric floor is not a candidate for a crochet shop."""
    out = B.decide([_result("flux-2-pro", stitch_fidelity=1, material_truth=1)])
    assert out["decided"] is False
    assert "fabric floor" in out["why"]


def test_quality_decides_when_the_margin_is_wide():
    cheap = _result("flux-2-pro", stitch_fidelity=2, material_truth=3,
                    finished_result_clarity=2, thumbnail_strength=2,
                    lifestyle_quality=2, product_is_the_subject=2,
                    physical_plausibility=2)
    dear = _result("nano-banana-2", stitch_fidelity=4, material_truth=4,
                   finished_result_clarity=4, thumbnail_strength=4,
                   lifestyle_quality=4, product_is_the_subject=4,
                   physical_plausibility=4)
    out = B.decide([cheap, dear])
    assert out["decided"] is True
    assert out["winner"] == "nano-banana-2", out
    assert "Quality decided and cost did not" in out["why"]


def test_cost_breaks_a_tie_and_only_a_tie():
    """Inside what five samples can separate, the difference is not a finding."""
    cheap = _result("flux-2-pro")
    dear = _result("nano-banana-2")
    out = B.decide([dear, cheap])
    assert out["decided"] is True
    assert out["winner"] == "flux-2-pro"
    assert "Cost broke the tie, and only then" in out["why"]


def test_the_deciding_margin_is_a_score_and_not_a_dollar_rule():
    """The dollars here are small enough that any dollar rule would dominate."""
    assert 0 < B.DECIDING_MARGIN < 1
    assert "score margin rather than" in B.state()["how_cost_is_used"]


# ---- what the trials actually test -------------------------------------------


def test_every_trial_renders_an_original_subject():
    """Benchmarking on a competitor's product would be commissioning a copy to see how good
    the copier is."""
    for trial in B.TRIALS:
        lowered = trial.prompt.lower()
        assert "mjs" not in lowered
        assert "competitor" not in lowered
        assert trial.requirement > 0


def test_the_trials_cover_fabric_hero_thumbnail_lifestyle_and_identity():
    requirements = {t.requirement for t in B.TRIALS}
    assert {79, 75, 66, 198, 201} <= requirements
    assert any(t.needs_reference for t in B.TRIALS), "nothing tests anti-drift"


def test_running_without_a_provider_reports_the_plan_rather_than_scores():
    db = Database("sqlite://")
    db.create_all()
    out = B.run(db, env={})
    assert out["ran"] is False
    assert "literature review with a score column" in out["reason"]
    assert out["plan"]["total_cad"] > 0


def test_the_state_says_plainly_that_nothing_has_been_measured():
    out = B.state()
    assert out["measured"] is False
    assert "owner action" in out["why_not_measured"]


def test_every_benchmark_candidate_can_actually_be_called():
    """A model can never win a benchmark the generator cannot then be pointed at."""
    from brambleloop.gateway import images

    for candidate in B.CANDIDATES:
        if candidate.can_hold_an_identity:
            assert candidate.key in images.BY_KEY, (
                f"{candidate.key} is benchmarked and has no provider entry, so winning would "
                f"leave nothing to configure")


def test_there_is_no_standing_recommendation_for_the_benchmark_to_confirm():
    """A named winner beside an unrun benchmark is the price list deciding again."""
    from brambleloop.core.db import Database
    from brambleloop.gateway import images

    db = Database("sqlite://")
    db.create_all()
    state = images.state(db, env={})
    assert state["recommended"] is None
    assert "cheapest candidate is not a default" in state["why_no_recommendation"]
    # And the arithmetic the owner's principle turns on is present for every candidate,
    # rather than for one that was picked first.
    assert len(state["estimate_per_candidate"]) >= 3


def test_the_whole_price_spread_is_smaller_than_the_decision():
    """The owner's instruction, checked as arithmetic: if the monthly difference between
    the cheapest and dearest eligible model is this small, cost cannot be the argument."""
    from brambleloop.core.db import Database
    from brambleloop.gateway import images

    db = Database("sqlite://")
    db.create_all()
    monthly = [v["monthly_cad"]
               for v in images.state(db, env={})["estimate_per_candidate"].values()]
    assert max(monthly) - min(monthly) < 10.0, (
        "the spread has grown enough that cost is a real argument; this test is the place "
        "to notice that rather than a report somebody writes afterwards")


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
