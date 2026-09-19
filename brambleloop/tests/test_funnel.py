"""The staged selection tournament, and the four ways a funnel stops being one.

v1.4.3 requirement 3: do not fully engineer the first ideas. The mechanism is a funnel with a
shape -- roughly 75-100 concepts down to 5-10 releases -- and the shape is the part that
quietly disappears. A funnel that starts with twelve concepts is the first ideas with a
process wrapped around them, and a stage that advances everything is a queue with a name.
Both look identical in a report that counts only what came out of the end.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import funnel as F  # noqa: E402


def _keys(n: int, prefix: str = "c") -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def _run_to(stage_key: str, *, start: int = 90) -> F.Tournament:
    """Drive a healthy tournament as far as the named stage."""
    t = F.Tournament("christmas")
    alive = _keys(start)
    plan = {"ideation": 82, "research": 40, "proposition": 20, "prototype": 12,
            "release": 7}
    for stage in F.STAGE_ORDER:
        survivors = alive[:plan[stage]]
        killed = {k: "sameness" for k in alive[plan[stage]:]}
        F.advance(t, stage=stage, entrants=alive, survived=survivors, killed=killed)
        alive = survivors
        if stage == stage_key:
            break
    return t


def test_a_healthy_tournament_keeps_its_shape():
    t = _run_to("release")
    report = F.report(t)

    assert report["complete"] is True
    assert report["stages_off_target_shape"] == []
    assert report["started_with"] == 90
    assert report["survivors"] == 7


def test_a_stage_that_kills_nothing_is_refused():
    """A kill gate with no kills either had nothing to judge or was not applied."""
    t = F.Tournament("christmas")
    ideas = _keys(90)
    try:
        F.advance(t, stage="ideation", entrants=ideas, survived=ideas, killed={})
    except F.FunnelRefused as e:
        assert "killed nothing" in str(e)
    else:
        raise AssertionError("a stage passed everything and was counted as a gate")


def test_a_stage_below_its_floor_is_refused():
    """A prototype stage fed four concepts is choosing among four concepts."""
    t = F.Tournament("christmas")
    ideas = _keys(12)
    try:
        F.advance(t, stage="ideation", entrants=ideas, survived=ideas[:10],
                  killed={k: "sameness" for k in ideas[10:]})
    except F.FunnelRefused as e:
        assert "below its floor" in str(e)
    else:
        raise AssertionError("twelve concepts were accepted as a tournament")


def test_every_entrant_is_accounted_for():
    """A funnel is only honest if nothing can leave it quietly."""
    t = F.Tournament("christmas")
    ideas = _keys(90)
    try:
        F.advance(t, stage="ideation", entrants=ideas, survived=ideas[:80],
                  killed={k: "sameness" for k in ideas[85:]})
    except F.FunnelRefused as e:
        assert "does not account for every entrant" in str(e)
    else:
        raise AssertionError("five concepts vanished without being killed")


def test_a_kill_cause_outside_the_vocabulary_is_refused():
    """'Not strong enough' aggregates to nothing, and the aggregate is the point."""
    t = F.Tournament("christmas")
    ideas = _keys(90)
    try:
        F.advance(t, stage="ideation", entrants=ideas, survived=ideas[:85],
                  killed={k: "not strong enough" for k in ideas[85:]})
    except F.FunnelRefused as e:
        assert "aggregates to nothing" in str(e)
    else:
        raise AssertionError("an unclassified kill reason was recorded")


def test_a_stage_cannot_run_out_of_order():
    t = F.Tournament("christmas")
    ideas = _keys(90)
    try:
        F.advance(t, stage="prototype", entrants=ideas, survived=ideas[:12],
                  killed={k: "complexity" for k in ideas[12:]})
    except F.FunnelRefused as e:
        assert "has not happened" in str(e)
    else:
        raise AssertionError("the tournament skipped straight to prototyping")


def test_a_concept_cannot_join_the_funnel_late():
    """A concept that joins late has been chosen by somebody rather than by the tournament."""
    t = _run_to("ideation")
    alive = t.rounds[-1].survived
    smuggled = alive + ["favourite-idea"]
    try:
        F.advance(t, stage="research", entrants=smuggled, survived=alive[:40],
                  killed={k: "sameness" for k in smuggled[40:]})
    except F.FunnelRefused as e:
        assert "without surviving" in str(e)
    else:
        raise AssertionError("a late entrant was allowed into the tournament")


def test_engineering_before_the_prototype_stage_is_refused():
    """The requirement's opening sentence, made mechanical."""
    t = _run_to("research")
    try:
        F.may_engineer(t, "c0")
    except F.FunnelRefused as e:
        assert "Do not fully engineer the first ideas" in str(e)
    else:
        raise AssertionError("a concept was engineered before it had been chosen")


def test_engineering_a_concept_the_tournament_killed_is_refused():
    t = _run_to("prototype")
    killed = next(iter(t.rounds[-1].killed))
    try:
        F.may_engineer(t, killed)
    except F.FunnelRefused as e:
        assert "outside the tournament" in str(e)
    else:
        raise AssertionError("a killed concept was engineered anyway")


def test_a_survivor_of_the_prototype_stage_may_be_engineered():
    t = _run_to("prototype")
    F.may_engineer(t, t.rounds[-1].survived[0])


def test_the_report_names_the_dominant_cause_because_the_fixes_are_opposite():
    """A funnel dying mostly of sameness has a generation problem; one dying of margin has a
    brief problem, and those are not the same instruction."""
    t = F.Tournament("christmas")
    ideas = _keys(90)
    F.advance(t, stage="ideation", entrants=ideas, survived=ideas[:82],
              killed={k: "genericness" for k in ideas[82:]})
    alive = ideas[:82]
    killed = {k: "sameness" for k in alive[40:70]}
    killed.update({k: "margin" for k in alive[70:]})
    F.advance(t, stage="research", entrants=alive, survived=alive[:40], killed=killed)

    report = F.report(t)

    assert report["dominant_cause"] == "sameness"
    assert report["diagnosis"] == F.KILL_CAUSES["sameness"]
    assert report["complete"] is False
    assert "not a selection yet" in report["note"]


def test_a_stage_outside_its_target_shape_is_reported_rather_than_refused():
    """Passing 60 of 82 is a real tournament with a loose gate, which is information, not a
    reason to throw the round away."""
    t = F.Tournament("christmas")
    ideas = _keys(90)
    F.advance(t, stage="ideation", entrants=ideas, survived=ideas[:82],
              killed={k: "genericness" for k in ideas[82:]})
    alive = ideas[:82]
    F.advance(t, stage="research", entrants=alive, survived=alive[:60],
              killed={k: "sameness" for k in alive[60:]})

    report = F.report(t)

    assert "research" in report["stages_off_target_shape"]
    assert "ideation" not in report["stages_off_target_shape"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
