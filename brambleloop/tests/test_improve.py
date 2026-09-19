"""The Improvement Department, and the way a self-improving system goes wrong.

v1.4.3 requirements 90-104. A system that optimises its own metrics has one dominant failure
mode, and it is not laziness: every number this company reports is produced by a check, so the
cheapest way to improve any of them is to loosen the check that produces it. The improvement is
real, the measurement is real, and the company is worse.

From inside the loop that is invisible — weakening a gate and fixing a defect look identical: a
change, followed by a better number. So most of these tests are about the refusal.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import bus, cells, governance, tiers  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/improve.sqlite")
    db.create_all()
    return db


# ---- the boundary ---------------------------------------------------------


def test_a_gate_may_never_be_loosened_to_improve_the_number_it_produces():
    """#102, and the hazard the whole department is built around.

    "Relax asset truth so more assets pass" raises the pass rate immediately, permanently and
    measurably. Nothing downstream would notice, because the metric it damaged is the metric
    it reports.
    """
    for hypothesis, touches in (
        ("lower the threshold on the thumbnail check so more assets pass", ("asset_truth",)),
        ("disable reverse compilation on small patterns to speed up certification",
         ("reverse_compilation",)),
        ("relax the claim gates so size claims stop blocking listings", ("claim_gates",)),
        ("bypass the spend ceiling during a seasonal push", ("spend_ceilings",)),
        ("soften the creative jury so more concepts survive", ("creative_jury",)),
    ):
        boundary = governance.check(hypothesis, touches=touches)
        assert boundary.ok is False, hypothesis
        assert "weaken a policy gate" in boundary.rule
        assert "look identical" in boundary.reason

    # And ordinary tuning of something unprotected is allowed, or the department is useless.
    fine = governance.check(
        "cache the twin between compile and reverse compile to cut runtime per product",
        touches=("runtime_cache",))
    assert fine.ok is True


def test_a_paraphrase_does_not_get_a_weakening_past_the_boundary():
    """Found by writing the same hypothesis with the words in a different order.

    The phrase list caught "lower the threshold on the thumbnail check" and missed "lower the
    thumbnail threshold" — the same sentence, reordered. A detector a paraphrase defeats
    fails exactly when somebody is rewriting a hypothesis to get it through, which is the
    only occasion it matters.
    """
    for hypothesis in ("lower the thumbnail threshold so more assets pass",
                       "widen the size tolerance so more patterns certify",
                       "drop the reverse compilation requirement for small patterns"):
        boundary = governance.check(hypothesis, touches=("asset_truth",))
        assert boundary.ok is False, hypothesis
        assert "weaken a policy gate" in boundary.rule


def test_a_verb_that_does_not_govern_the_gate_is_not_a_weakening():
    """The first fix for the paraphrase hole refused a hypothesis that *strengthens* a gate.

    "tightening the thumbnail check should reduce defects reaching release" pairs a weakening
    verb with a gate object in one sentence, and the verb is acting on the defects. Same-
    sentence co-occurrence was too crude; the verb has to govern the object.
    """
    for hypothesis in (
        "tightening the thumbnail check should reduce defects reaching release",
        "adding a frame-level contrast check should reduce defects further",
        "a stricter claim gate should lower the number of unsupported size statements",
    ):
        assert governance.check(hypothesis, touches=("asset_truth",)).ok is True, hypothesis


def test_a_hypothesis_cannot_avoid_the_check_by_declaring_nothing():
    """The obvious evasion, closed.

    If an undeclared surface were allowed, "loosen the validation a little" with no `touches`
    would sail through and the protected list would be advisory.
    """
    evasive = governance.check("relax the validation a little to see if throughput improves")
    assert evasive.ok is False
    assert "undeclared surface" in evasive.reason


def test_fabricating_the_evidence_is_refused_above_everything_else():
    """The worst version, and the one that would flatter every other number at once."""
    for hypothesis in ("seed customers to establish a conversion baseline",
                       "backfill revenue from the shadow runs to unblock the ladder",
                       "use sample data as evidence for the demand rung"):
        boundary = governance.check(hypothesis, touches=("confidence_ladder",))
        assert boundary.ok is False
        assert "fabricate evidence" in boundary.rule
        assert "only worth what produced it" in boundary.reason


def test_the_system_cannot_widen_its_own_authority():
    """A system that can grant itself an owner-only power has no owner."""
    for action in ("publish the seasonal listings automatically once quality passes",
                   "complete KYC using the stored details",
                   "graduate the phase to production when the gates are green",
                   "connect Etsy without waiting"):
        boundary = governance.check_owner_authority(action)
        assert boundary.ok is False
        assert "owner authority" in boundary.rule

    assert governance.check_owner_authority("rewrite the listing draft prompt").ok is True


def test_irreversible_and_unaffordable_changes_are_refused():
    """#93 and #99. An improvement with no way back is a decision, not an experiment."""
    assert governance.check("rewrite the compiler in one pass",
                            touches=("x",), reversible=False).ok is False
    over = governance.check("run a large evaluation sweep", touches=("x",),
                            spend_cad=40.0, spend_authorised_cad=5.0)
    assert over.ok is False
    assert "improvement budget" in over.rule


# ---- the loop -------------------------------------------------------------


def test_the_baseline_is_taken_before_the_change_or_there_is_no_baseline():
    """#92. A result compared against a number measured afterwards is compared with itself.

    That is not a subtle bias — it makes every promotion a success and the loop decorative.
    """
    db = _db()

    # With no prior measurement, a result is a baseline rather than a win.
    first = cells.propose(
        db, cell="quality",
        hypothesis="tightening the thumbnail check should reduce defects reaching release",
        expected_effect="fewer post-release defects", rollback_ref="git:aaa")
    assert cells.test_result(db, first, 3.0) == cells.REJECTED

    # That measurement became the baseline, so the next attempt has something to beat.
    second = cells.propose(
        db, cell="quality",
        hypothesis="adding a frame-level contrast check should reduce defects further",
        expected_effect="fewer post-release defects", rollback_ref="git:bbb",
        touches=("weights",))
    assert cells.test_result(db, second, 1.0) == cells.TESTING
    assert cells.promote(db, second) == cells.PROMOTED


def test_a_result_that_is_not_better_cannot_be_promoted():
    """And 'better' respects the direction of the metric."""
    db = _db()
    cells.record_capability(db, "runtime", 4.0)

    worse = cells.propose(
        db, cell="runtime",
        hypothesis="claiming jobs in larger batches should reduce dead letters per day",
        expected_effect="fewer dead letters", rollback_ref="git:ccc")
    assert cells.test_result(db, worse, 6.0) == cells.REJECTED

    try:
        cells.promote(db, worse)
    except cells.ImprovementRefused as e:
        assert "beat a baseline" in str(e)
    else:
        raise AssertionError("a rejected change was promoted")

    # Lower is better for dead letters; higher is better for survival. Both are respected.
    cells.record_capability(db, "product_creativity", 0.2)
    up = cells.propose(
        db, cell="product_creativity",
        hypothesis="briefing concepts from a form vocabulary should raise tournament survival",
        expected_effect="higher survival at equal spread", rollback_ref="git:ddd")
    assert cells.test_result(db, up, 0.35) == cells.TESTING


def test_a_promotion_without_a_rollback_path_cannot_be_proposed():
    """#93 requires the way back to exist before the change does."""
    db = _db()
    try:
        cells.propose(db, cell="runtime",
                      hypothesis="switching the queue backend should cut dead letters",
                      expected_effect="fewer dead letters", rollback_ref="")
    except cells.ImprovementRefused as e:
        assert "rollback" in str(e)
    else:
        raise AssertionError("a change with no way back was accepted")


def test_a_degrading_promotion_reverts_itself_rather_than_waiting_for_agreement():
    """#93. A regression that waits to be agreed is a regression that stays over a weekend."""
    db = _db()
    cells.record_capability(db, "runtime", 8.0)
    improvement = cells.propose(
        db, cell="runtime",
        hypothesis="a longer lease should reduce dead letters from slow jobs",
        expected_effect="fewer dead letters", rollback_ref="git:eee",
        touches=("cadence",))
    cells.test_result(db, improvement, 2.0)
    # A lease length is a cadence, which #178 grades as tooling: routing and timing changes
    # alter cost and reliability together, so the tier asks for a regression test the row
    # cannot be asked about and the caller has to carry.
    cells.promote(db, improvement, evidence=(tiers.REGRESSION_TEST,))

    held = cells.monitor(db, improvement, 2.05)
    assert held["action"] == "held"

    reverted = cells.monitor(db, improvement, 5.0)
    assert reverted["action"] == "reverted"
    assert reverted["rollback_ref"] == "git:eee"

    # And the post-promotion observation is kept as history, degraded or not.
    history = cells.capability_history(db, "runtime")
    assert [h["value"] for h in history][-1] == 5.0


def test_every_cell_owns_a_metric_that_comes_from_rows():
    """#91. 'Measurably better' needs the measurement to be checkable by a sceptic.

    A rating a cell assigns itself is not a measurement, so every cell names both the number
    and where it comes from.
    """
    assert len(cells.CELLS) == 12
    for cell in cells.CELLS:
        assert cell.metric and cell.measure
        assert cell.what_it_means
        assert isinstance(cell.higher_is_better, bool)
    departments = {c.department for c in cells.CELLS}
    assert {"Creativity", "Pattern Engineering", "QA", "Market Radar", "Pricing",
            "Finance", "Runtime"} <= departments


def test_the_retrospective_reports_what_regressed_and_what_was_never_measured():
    """#100. A retrospective that lists only wins is a newsletter."""
    db = _db()
    cells.record_capability(db, "runtime", 2.0)
    cells.record_capability(db, "runtime", 6.0)          # worse: lower is better
    cells.record_capability(db, "quality", 5.0)
    cells.record_capability(db, "quality", 2.0)          # better

    report = cells.retrospective(db)
    assert report["capability_movement"]["runtime"]["direction"] == "regressed"
    assert report["capability_movement"]["quality"]["direction"] == "improved"
    assert report["bottleneck"] == "runtime"
    assert len(report["unmeasured_cells"]) == 10
    assert "unclaimable rather than unproven" in report["honest_note"]


# ---- the lesson bus -------------------------------------------------------


def test_a_lesson_is_routed_by_its_subject_rather_than_by_a_distribution_list():
    """#97, and the spec's own example.

    Customers prefer low-sew construction, so Market Radar, Creativity and Pattern
    Engineering all need it. A list somebody maintains is a list somebody forgets.
    """
    db = _db()
    lesson = bus.publish(
        db, origin_cell="customer_experience", subject="construction_preference",
        statement="buyers abandon patterns that require seaming more than two panels",
        evidence_ref="support:themes:2026-09", confidence="observed")

    assert set(bus.route_for("construction_preference")) == {
        "product_creativity", "pattern_engineering", "market_radar"}
    assert [x["id"] for x in bus.inbox(db, "pattern_engineering")] == [lesson]
    assert bus.inbox(db, "finance") == []

    # A subject with no audience is refused: a lesson nobody receives changes nothing.
    try:
        bus.publish(db, origin_cell="quality", subject="miscellaneous",
                    statement="something happened that seemed worth writing down")
    except bus.LessonRefused as e:
        assert "no routing" in str(e)
    else:
        raise AssertionError("an unroutable lesson was published")


def test_compounding_is_measured_by_what_acted_on_a_lesson_not_by_how_many_exist():
    """#101. Filing is not learning.

    The test of accumulated knowledge is that a later decision used one, so the bus records
    who acted and surfaces what has sat untouched.
    """
    db = _db()
    lesson = bus.publish(
        db, origin_cell="customer_experience", subject="construction_preference",
        statement="buyers abandon patterns that require seaming more than two panels")

    before = bus.compounding(db)
    assert before["routed"] == 1 and before["acted_on"] == 0
    assert "filing rather than compounding" in before["note"]

    bus.acted_on(db, lesson, "pattern_engineering",
                 how="seamless constructions now score higher in the brief")
    after = bus.compounding(db)
    assert after["acted_on"] == 1
    assert after["action_rate"] == 1.0
    assert bus.inbox(db, "pattern_engineering") == []

    # A cell that was never sent the lesson cannot claim to have acted on it.
    try:
        bus.acted_on(db, lesson, "finance", how="we read it")
    except bus.LessonRefused as e:
        assert "not routed" in str(e)
    else:
        raise AssertionError("an unrouted cell claimed a lesson")


def test_the_governance_boundary_is_stated_where_the_owner_can_read_it():
    """A boundary only the code knows is one the owner cannot hold anybody to."""
    described = governance.describe()
    assert "weaken a protected gate" in described["may_never"]
    assert "fabricate evidence, reviews, customers or revenue" in described["may_never"]
    assert "shadow_mode" in described["protected_gates"]
    assert "confidence_ladder" in described["protected_gates"]
    assert "cheapest way to improve any of them" in described["why"]


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
