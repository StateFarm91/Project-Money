"""The nine per-dimension teardowns, and the ways a laboratory becomes a fan club.

v1.4.3 requirements 152-160, 164, 168. A teardown has three characteristic failures and none
of them is laziness.

It scores what it happened to look at and reports a mean, so a shallow teardown outranks a
thorough one. It admires a competitor and writes down "we should do that too", which is the
parity #163 already refuses arriving through a different door. And it produces a document that
nobody converts into a change, which is the failure #164 exists to name.

So most of these tests are about refusals, and the rest are about the funnel being honest
about how little of it has reached the far end.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.teardown import audits, pipeline, scorecard  # noqa: E402
from brambleloop.teardown.library import ContentRefused  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/teardown.sqlite")
    db.create_all()
    return db


def _benchmark(db, ref: str, category: str = "blankets") -> None:
    from brambleloop.core.models import BenchmarkProduct

    with db.session() as s:
        s.add(BenchmarkProduct(ref=ref, seller=ref.split("-")[0], category=category,
                               purchased_on="2026-09-19", paid_cad=9.0))


def _full(spec: audits.AuditSpec, *, quality: int = 3, overrides: dict | None = None) -> dict:
    """Every element answered at 'competent', so a test can vary one thing at a time."""
    answers: dict = {}
    for element in spec.elements:
        answers[element.key] = (True if element.kind == audits.PRESENCE else quality)
    answers.update(overrides or {})
    return answers


# ---- the schedules --------------------------------------------------------


def test_every_audit_is_a_closed_schedule_feeding_a_dimension_that_already_exists():
    """#152-#160. Nine requirements, nine schedules, and no second standard beside the first.

    An audit that invented its own dimension would produce a scorecard the composite standard
    could not read, which is two standards that disagree by next month.
    """
    assert len(audits.AUDITS) == 9
    assert {a.requirement for a in audits.AUDITS} == set(range(152, 161))
    for spec in audits.AUDITS:
        assert spec.dimension in scorecard.DIMENSIONS
        assert len(spec.elements) >= 7
        assert len(set(spec.element_keys)) == len(spec.elements)
        assert spec.note

    # The schedules come from the requirements' own enumerations, so they can be read side
    # by side with the document.
    assert "colour_independence" in audits.CHART_BENCHMARK.element_keys
    assert "written_correspondence" in audits.CHART_BENCHMARK.element_keys
    assert "troubleshooting" in audits.PDF_ARCHITECTURE.element_keys
    assert "rights_terms" in audits.PDF_ARCHITECTURE.element_keys
    assert "cognitive_load" in audits.INSTRUCTION_CLARITY.element_keys


def test_a_partial_schedule_is_refused_rather_than_averaged():
    """Scoring the easy elements and reporting the mean is the shallow teardown's whole trick."""
    partial = _full(audits.CHART_BENCHMARK)
    partial.pop("colour_independence")
    partial.pop("print_quality")
    try:
        audits.observe("chart_benchmark", "acme-granny", partial)
    except audits.AuditRefused as e:
        assert "incomplete" in str(e)
        assert "colour_independence" in str(e)
    else:
        raise AssertionError("a partial chart audit was scored")

    # And an element nobody agreed on cannot be added mid-teardown, or two teardowns of two
    # products stop being comparable.
    try:
        audits.observe("chart_benchmark", "acme-granny",
                       _full(audits.CHART_BENCHMARK, overrides={"vibes": 5}))
    except audits.AuditRefused as e:
        assert "not part of the chart_benchmark schedule" in str(e)
    else:
        raise AssertionError("an invented element was accepted")


def test_an_audit_the_product_never_promised_is_refused_not_scored_zero():
    """#157 applies where video exists. Scoring its absence would invent a weakness."""
    try:
        audits.observe("video_teardown", "acme-granny", _full(audits.VIDEO_TEARDOWN),
                       inferred={"has_video": False})
    except audits.AuditRefused as e:
        assert "manufacture a weakness out of a category difference" in str(e)
    else:
        raise AssertionError("a pattern with no video was scored on its video")

    ok = audits.observe("video_teardown", "acme-granny", _full(audits.VIDEO_TEARDOWN),
                        inferred={"has_video": True})
    assert len(ok.observations) == len(audits.VIDEO_TEARDOWN.elements)


def test_an_extreme_score_with_no_mechanism_is_refused_and_a_competent_one_is_not():
    """Only the extremes owe an essay, because thirty-four essays is a task nobody finishes."""
    try:
        audits.observe("instruction_clarity", "acme-granny",
                       _full(audits.INSTRUCTION_CLARITY, overrides={"repeat_notation": 5}))
    except audits.AuditRefused as e:
        assert "no mechanism" in str(e)
    else:
        raise AssertionError("a 5 was recorded with nothing to say for it")

    try:
        audits.observe("instruction_clarity", "acme-granny",
                       _full(audits.INSTRUCTION_CLARITY, overrides={"cognitive_load": 1}))
    except audits.AuditRefused as e:
        assert "no mechanism" in str(e)
    else:
        raise AssertionError("a trap was recorded with nothing to say for it")

    # Every element at 3 needs no mechanism at all, and that is the common case.
    plain = audits.observe("instruction_clarity", "acme-granny",
                           _full(audits.INSTRUCTION_CLARITY))
    assert plain.findings() == []
    assert plain.summary()["mean"] == 3.0


def test_a_mechanism_that_is_really_the_competitors_pattern_is_refused():
    """#167 again, at the new door. The boundary has to hold wherever text enters."""
    try:
        audits.observe("instruction_clarity", "acme-granny", _full(
            audits.INSTRUCTION_CLARITY,
            overrides={"repeat_notation": {
                "score": 5,
                "mechanism": "the repeat is written as rep from * to end of row 1",
                "advantage": "deterministic_validation"}}))
    except ContentRefused as e:
        assert "competitor's instructions" in str(e)
    else:
        raise AssertionError("a competitor's row instruction was stored as a mechanism")


def test_a_strength_with_no_answer_is_recorded_as_unanswered_rather_than_invented():
    """#163 made mechanical. The most useful finding is the one we cannot match yet."""
    audit = audits.observe("chart_benchmark", "acme-granny", _full(
        audits.CHART_BENCHMARK,
        overrides={
            "colour_independence": {
                "score": 5,
                "mechanism": "every chart cell carries a per-yarn letter as well as a fill",
                "advantage": "colour_independent_charts"},
            "schematics": {
                "score": 5,
                "mechanism": "a dimensioned schematic per size sits opposite the chart"},
        }))

    unmatched = {u["element"] for u in audit.unmatched_strengths}
    assert unmatched == {"schematics"}
    assert "unanswered rather than converted" in audit.unmatched_strengths[0]["why"]

    # The answered one converts into a beat requirement, never a match requirement.
    strong = {f.mechanism.split(" / ")[1].split(":")[0]: f for f in audit.findings()}
    assert "must exceed this on colour_independence, not match it" in \
        strong["colour_independence"].improvement

    # An advantage this company cannot evidence is refused outright.
    try:
        audits.observe("chart_benchmark", "acme-granny", _full(
            audits.CHART_BENCHMARK,
            overrides={"legibility": {"score": 4,
                                      "mechanism": "charts are delivered at print resolution",
                                      "advantage": "better_taste"}}))
    except scorecard.ScoreRefused as e:
        assert "not an advantage this company can evidence" in str(e)
    else:
        raise AssertionError("an aspiration was accepted as a differentiator")


def test_the_manifest_answers_what_filenames_can_settle():
    """#170 applied to #159: retyping what intake already worked out is how this stalls."""
    inferred = {"file_count": 6, "has_chart": True, "has_bonus": False,
                "has_print_edition": True}
    pre = audits.prefill("delivery_packaging", inferred)
    assert pre["charts_separate"]["score"] is True
    assert pre["bonus_files"]["score"] is False
    assert pre["file_count"]["files"] == 6

    # The analyst then answers only the rest — including the one presence element no
    # filename can settle, because "a Spanish edition exists" is not inferable from a folder.
    rest = {e.key: 3 for e in audits.DELIVERY_PACKAGING.elements
            if e.kind == audits.QUALITY}
    assert set(audits.DELIVERY_PACKAGING.element_keys) - set(rest) - set(pre) == \
        {"language_variants"}
    rest["language_variants"] = False
    audit = audits.observe("delivery_packaging", "acme-granny", rest, inferred=inferred)
    sources = {o.element: o.source for o in audit.observations}
    assert sources["charts_separate"] == "manifest"
    assert sources["organization"] == "analyst"
    assert audit.summary()["sections_absent"] == ["bonus_files", "language_variants"]


def test_the_summary_reports_the_weakest_element_as_well_as_the_mean():
    """A chart with excellent symbols and no legend is a bad chart however it averages."""
    audit = audits.observe("chart_benchmark", "acme-granny", _full(
        audits.CHART_BENCHMARK,
        overrides={"legends": {"score": 1,
                               "mechanism": "the legend is on page one and the chart on "
                                            "page four, so neither is usable alone"}}))
    summary = audit.summary()
    assert summary["weakest"] == "legends"
    assert summary["weakest_score"] == 1.0
    assert summary["mean"] > 2.5
    assert [t["element"] for t in summary["traps"]] == ["legends"]


# ---- the standard the audits imply ----------------------------------------


def test_the_publishing_standard_is_absent_rather_than_lenient_before_a_purchase():
    """An empty standard reads as all-clear, which is the most expensive way to be wrong."""
    db = _db()
    derived = audits.publishing_requirements(db)
    assert derived["derivable"] is False
    assert "an empty standard is not a lenient one" in derived["reason"]

    coverage = audits.coverage(db)
    assert coverage["runnable"] is False
    assert "nine schedules exist and are unrun" in coverage["reason"]


def test_the_publishing_standard_takes_the_best_benchmark_and_requires_beating_it():
    """#154 and #156: better than the best purchased experience, not the average of them."""
    db = _db()
    _benchmark(db, "acme-granny")
    _benchmark(db, "birch-throw")

    weaker = audits.observe("chart_benchmark", "acme-granny", _full(
        audits.CHART_BENCHMARK,
        overrides={"symbols": {"score": 4,
                               "mechanism": "a standard symbol set used consistently "
                                            "throughout the document",
                               "advantage": "reverse_compilation"}}))
    stronger = audits.observe("chart_benchmark", "birch-throw", _full(
        audits.CHART_BENCHMARK,
        overrides={"symbols": {"score": 5,
                               "mechanism": "the standard symbol set plus a per-row colour "
                                            "key repeated on every page",
                               "advantage": "colour_independent_charts"}}))
    audits.record(db, weaker)
    audits.record(db, stronger)

    derived = audits.publishing_requirements(db)
    assert derived["derivable"] is True
    symbols = [r for r in derived["requirements"] if r["element"] == "symbols"]
    assert len(symbols) == 1
    assert symbols[0]["benchmark"] == "birch-throw"
    assert symbols[0]["benchmark_score"] == 5.0
    assert symbols[0]["differentiator"]
    assert "Matching it is the parity" in derived["note"]

    # And the audits are visible as run against one benchmark's chart audit but not the rest.
    coverage = audits.coverage(db)
    assert coverage["runnable"] is True
    assert coverage["benchmarks"] == 2
    assert coverage["run"] == 2
    outstanding = {(o["benchmark"], o["audit"]) for o in coverage["outstanding"]}
    assert ("acme-granny", "beginner_experience") in outstanding
    # No manifest records video, so no benchmark is queued for a video teardown it never had.
    assert not any(a == "video_teardown" for _, a in outstanding)


def test_the_audits_feed_the_composite_standard_rather_than_a_second_one():
    """Two standards that disagree is worse than one standard that is wrong."""
    db = _db()
    _benchmark(db, "acme-granny")
    _benchmark(db, "birch-throw")
    audits.record(db, audits.observe("chart_benchmark", "acme-granny", _full(
        audits.CHART_BENCHMARK,
        overrides={"legibility": {"score": 5,
                                  "mechanism": "charts are vector and hold up at any zoom",
                                  "advantage": "colour_independent_charts"}})))
    audits.record(db, audits.observe("support_rights", "birch-throw", _full(
        audits.SUPPORT_RIGHTS,
        overrides={"update_policy": {"score": 5,
                                     "mechanism": "buyers are emailed whenever the pattern "
                                                  "version changes",
                                     "advantage": "version_aware_support"}})))

    composite = scorecard.composite_standard(db)
    assert set(composite["source_benchmarks"]) == {"acme-granny", "birch-throw"}
    assert composite["single_source"] is False
    assert "chart_quality" in composite["dimensions"]
    assert "support_experience" in composite["dimensions"]


# ---- #164: the pipeline ---------------------------------------------------


def test_a_finding_becomes_a_hypothesis_owned_by_a_cell_and_never_twice():
    """#164. A hand-off that is a convention stops being followed in the third week."""
    db = _db()
    _benchmark(db, "acme-granny")
    recorded = audits.record(db, audits.observe("beginner_experience", "acme-granny", _full(
        audits.BEGINNER_EXPERIENCE,
        overrides={"error_recovery": {"score": 5,
                                      "mechanism": "each section ends with what the work "
                                                   "should measure, so a mistake is caught "
                                                   "within one section",
                                      "advantage": "measured_yardage"}})))
    finding_id = recorded["findings_recorded"][0]

    promoted = pipeline.promote(db, finding_id, touches=("pattern_help_copy",),
                                rollback_ref="git:teardown-1")
    assert promoted["cell"] == "customer_experience"
    assert promoted["improvement"] > 0
    assert "acme-granny scores 5 on beginner_support" in promoted["hypothesis"]

    try:
        pipeline.promote(db, finding_id, touches=("pattern_help_copy",),
                         rollback_ref="git:teardown-1")
    except pipeline.PipelineRefused as e:
        assert "already promoted" in str(e)
    else:
        raise AssertionError("one observation was given two baselines")


def test_a_finding_cannot_smuggle_a_gate_weakening_past_the_improvement_boundary():
    """A competitor doing what we may not do is a finding about the competitor.

    This is the whole reason the pipeline routes through `improve.governance` rather than
    writing an Improvement row directly: "their listings claim sizes ours refuses" is a real
    observation and a forbidden hypothesis, and only the boundary can tell the difference.
    """
    db = _db()
    _benchmark(db, "acme-granny")
    finding = scorecard.finding(
        "acme-granny", "listing_promise_alignment", 4,
        "their listing states a size range the document does not grade all the way through",
        "relax the claim gates so Brambleloop listings can state the same size range")
    finding_id = scorecard.record(db, finding)

    try:
        pipeline.promote(db, finding_id, touches=("claim_gates",),
                         rollback_ref="git:teardown-2")
    except Exception as e:  # the boundary raises its own refusal type
        assert "weaken a policy gate" in str(e) or "gate" in str(e)
    else:
        raise AssertionError("a teardown finding weakened a claim gate")

    # And the finding is still unpromoted, so it stays visible as unresolved.
    assert pipeline.status(db)["unpromoted_findings"] == 1


def test_an_undeclared_surface_or_a_missing_way_back_is_refused_before_the_work():
    db = _db()
    _benchmark(db, "acme-granny")
    finding_id = scorecard.record(db, scorecard.finding(
        "acme-granny", "chart_quality", 5,
        "the legend repeats on every page of a multi-page chart",
        "repeat the legend on every chart page in the Brambleloop PDF generator"))

    try:
        pipeline.promote(db, finding_id, touches=(), rollback_ref="git:x")
    except pipeline.PipelineRefused as e:
        assert "name the surface" in str(e)
    else:
        raise AssertionError("an undeclared surface was accepted")

    try:
        pipeline.promote(db, finding_id, touches=("pdf_generator",), rollback_ref="")
    except pipeline.PipelineRefused as e:
        assert "rollback" in str(e)
    else:
        raise AssertionError("a change with no way back was accepted")


def test_the_funnel_counts_measured_improvements_rather_than_filed_findings():
    """#164 ends at 'promote only measurable improvements'. Filing is not improving."""
    db = _db()
    _benchmark(db, "acme-granny")
    from brambleloop.improve import cells

    finding_id = scorecard.record(db, scorecard.finding(
        "acme-granny", "delivery_packaging", 5,
        "the download opens on a one-page map of what every other file is for",
        "add a first-page bundle map to the Brambleloop delivery package"))

    before = pipeline.status(db)
    assert before["findings_recorded"] == 1
    assert before["improvements_promoted"] == 0
    assert "filing" in before["note"]

    promoted = pipeline.promote(db, finding_id, touches=("delivery_bundle",),
                                rollback_ref="git:teardown-3")
    mid = pipeline.status(db)
    assert mid["findings_promoted_to_hypothesis"] == 1
    # A hypothesis nobody has tested has changed nothing, and the funnel says so.
    assert mid["improvements_promoted"] == 0
    assert mid["hypotheses_tested"] == 0

    cells.record_capability(db, "customer_experience", 0.40)
    tested = cells.propose(
        db, cell="customer_experience",
        hypothesis="a first-page bundle map should reduce support cases per order",
        expected_effect="fewer support cases per order", rollback_ref="git:teardown-3b",
        touches=("copy",))
    assert cells.test_result(db, tested, 0.20) == cells.TESTING
    assert cells.promote(db, tested) == cells.PROMOTED

    # That promotion belongs to a cell, not to this finding, so the teardown funnel still
    # reports zero: crediting an unrelated win to a finding is how a funnel flatters itself.
    after = pipeline.status(db)
    assert after["improvements_promoted"] == 0
    assert after["hypotheses_by_state"] == {cells.PROPOSED: 1}
    assert promoted["improvement"] != tested


# ---- #168: the pre-launch challenge ---------------------------------------


def test_an_unrun_challenge_blocks_the_release_rather_than_passing_it():
    """A gate that waves things through when its evidence is missing is not a gate."""
    db = _db()
    result = pipeline.challenge(db, product_slug="hearthside-throw", category="blankets",
                                our_scores={d: 4 for d in pipeline.CRITICAL_DIMENSIONS})
    assert result["verdict"] == "unavailable"
    assert result["blocks_release"] is True
    assert "An unrun challenge is not a pass" in result["reason"]
    assert "benchmark purchases" in result["unblocked_by"]


def test_materially_inferior_on_a_critical_dimension_blocks_the_release():
    db = _db()
    _benchmark(db, "acme-granny", category="blankets")
    audits.record(db, audits.observe("chart_benchmark", "acme-granny", _full(
        audits.CHART_BENCHMARK,
        overrides={"legibility": {"score": 5,
                                  "mechanism": "charts are vector and hold up at any zoom",
                                  "advantage": "colour_independent_charts"}})))

    blocked = pipeline.challenge(
        db, product_slug="hearthside-throw", category="blankets",
        our_scores={"chart_quality": 3, "listing_promise_alignment": 5,
                    "delivery_packaging": 5, "instruction_clarity": 5,
                    "premium_presentation": 5, "support_experience": 5,
                    "perceived_value": 5})
    assert blocked["verdict"] == "blocked"
    assert blocked["blocks_release"] is True
    assert [b["dimension"] for b in blocked["blocking"]] == ["chart_quality"]
    assert "no declared tradeoff" in blocked["blocking"][0]["why"]

    # Level is not behind: the gate fires on a full point, which is a category a buyer names.
    passed = pipeline.challenge(
        db, product_slug="hearthside-throw", category="blankets",
        our_scores={"chart_quality": 5, "listing_promise_alignment": 5,
                    "delivery_packaging": 5, "instruction_clarity": 5,
                    "premium_presentation": 5, "support_experience": 5,
                    "perceived_value": 5})
    assert passed["verdict"] == "passed"
    assert passed["blocks_release"] is False


def test_a_critical_dimension_left_unscored_cannot_pass_the_challenge_by_omission():
    db = _db()
    _benchmark(db, "acme-granny", category="blankets")
    audits.record(db, audits.observe("support_rights", "acme-granny", _full(
        audits.SUPPORT_RIGHTS,
        overrides={"contact_path": {"score": 4,
                                    "mechanism": "a named person answers within one day, "
                                                 "stated on the first page",
                                    "advantage": "version_aware_support"}})))
    result = pipeline.challenge(db, product_slug="hearthside-throw", category="blankets",
                                our_scores={})
    assert result["blocks_release"] is True
    assert result["blocking"][0]["dimension"] == "support_experience"
    assert "passed by omission" in result["blocking"][0]["why"]


def test_a_deliberate_tradeoff_unblocks_the_gate_only_when_it_names_what_was_gained():
    """#163's rule again: a tradeoff justified by an aspiration is an excuse with a form."""
    db = _db()
    _benchmark(db, "acme-granny", category="blankets")
    audits.record(db, audits.observe("premium_experience", "acme-granny", _full(
        audits.PREMIUM_EXPERIENCE,
        overrides={"bonus_content": {"score": 5,
                                     "mechanism": "three bonus motif charts arrive with the "
                                                  "purchase without having been promised",
                                     "advantage": "measured_yardage"}})))

    try:
        pipeline.check_tradeoff("premium_presentation",
                                {"reason": "we chose a plainer document on purpose here",
                                 "gains": "stronger brand feeling"})
    except pipeline.PipelineRefused as e:
        assert "excuse with a form attached" in str(e)
    else:
        raise AssertionError("an aspiration excused a material gap")

    try:
        pipeline.check_tradeoff("premium_presentation",
                                {"reason": "deliberate", "gains": "reverse_compilation"})
    except pipeline.PipelineRefused as e:
        assert "what was traded" in str(e)
    else:
        raise AssertionError("'deliberate' with no reason excused a material gap")

    allowed = pipeline.challenge(
        db, product_slug="hearthside-throw", category="blankets",
        our_scores={"premium_presentation": 3, "listing_promise_alignment": 5,
                    "delivery_packaging": 5, "instruction_clarity": 5,
                    "chart_quality": 5, "support_experience": 5, "perceived_value": 5},
        tradeoffs={"premium_presentation": {
            "reason": "the first release spends its production budget on chart correctness "
                      "rather than on editorial polish",
            "gains": "reverse_compilation"}})
    assert allowed["blocks_release"] is False
    assert [r["dimension"] for r in allowed["behind_by_choice"]] == ["premium_presentation"]


def test_the_challenge_is_shaped_so_launch_readiness_can_block_on_it():
    """A report informs; a requirement blocks. #168 asks for the second one."""
    db = _db()
    requirement = pipeline.readiness_requirement(
        db, product_slug="hearthside-throw", category="blankets", our_scores={})
    assert requirement["key"] == "benchmark_challenge"
    assert requirement["ready"] is False
    assert requirement["blocked_by"] == "owner"
    assert requirement["evidence"]["verdict"] == "unavailable"


def test_every_dimension_has_an_accountable_improvement_cell():
    """An unowned finding is indistinguishable from one nobody recorded."""
    from brambleloop.improve import cells

    assert set(pipeline.CELL_FOR_DIMENSION) == set(scorecard.DIMENSIONS)
    known = {c.key for c in cells.CELLS}
    assert set(pipeline.CELL_FOR_DIMENSION.values()) <= known
    assert set(pipeline.CRITICAL_DIMENSIONS) <= set(scorecard.DIMENSIONS)


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
