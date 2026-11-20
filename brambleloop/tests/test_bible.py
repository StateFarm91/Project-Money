"""The styling half of the canonical identity, and the rule that it is checked rather than asked for.

#73 names four things the reference pack must carry beyond the face: makeup range,
expression range, wardrobe rules and lighting language, plus rejected drift examples. The
pack carried none of them, and the rules that existed lived in `brief.py` as prompt
language -- asked for, never verified.

What these tests protect is the difference. A rule nobody checks is a preference; the
identity gate would pass exactly the right woman in glamour makeup under coloured light,
because every dimension it measures would still match.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import bible  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _reading(**overrides) -> dict:
    answers = {k: True for k in bible.QUESTIONS}
    answers.update(overrides)
    return {"judged": True, "answers": answers, "notes": ""}


def test_the_pack_carries_every_part_the_requirement_names():
    """#73 lists four. Three of four is a bible with a hole in it."""
    assert set(bible.AXES) == {"makeup", "expression", "wardrobe", "lighting"}
    for name, axis in bible.AXES.items():
        assert axis["range"] and axis["outside"], name
        # Each part is checkable, not merely described. A range with no question behind it
        # is the prompt language this module exists to replace.
        assert axis["questions"], name


def test_a_frame_within_every_range_clears():
    verdict = bible.gate(_reading())
    assert verdict["verdict"] == "clear"
    assert verdict["outside"] == [] and verdict["unjudged"] == []


def test_each_axis_blocks_on_its_own_and_is_named():
    """An averaged styling score lets correct makeup pay for coloured gels."""
    for key, axis in bible.AXIS_OF.items():
        verdict = bible.gate(_reading(**{key: False}))
        assert verdict["verdict"] == "blocked", key
        assert verdict["outside"] == [axis], key
        assert key in verdict["axes"][axis]["breached"]


def test_glamour_styling_on_exactly_the_right_woman_is_still_refused():
    """The case the identity gate cannot see.

    Every dimension `identity.drift_check` measures -- face, hair, eyes, bust, torso --
    would match perfectly in a frame of her in heavy editorial makeup, rim-lit, wearing a
    printed dress that competes with the crochet. #202 is the requirement that says such a
    frame is wrong, and before this module nothing in the release path could tell.
    """
    verdict = bible.gate(_reading(
        makeup_is_daytime_natural=False,
        no_glamour_lighting_effects=False,
        nothing_competes_with_the_product=False))
    assert verdict["verdict"] == "blocked"
    assert verdict["outside"] == ["lighting", "makeup", "wardrobe"]


def test_a_question_nobody_could_answer_is_not_within_range():
    reading = _reading()
    reading["answers"].pop("stitch_texture_is_modelled")
    verdict = bible.gate(reading)
    assert verdict["verdict"] == "unjudged"
    assert verdict["unjudged"] == ["lighting"]
    assert "not within range" in verdict["why"]


def test_a_judge_that_did_not_answer_is_not_a_pass():
    verdict = bible.gate({"judged": False, "error": "provider refused", "answers": {}})
    assert verdict["verdict"] == "unjudged"
    assert verdict["outside"] == []


def test_only_real_booleans_are_read_as_answers():
    """A string "true" answers a different question, and coercing it invents an opinion."""
    class _Provider:
        model = "test-model"
        cost_per_1k_input_cad = 0.0
        cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, images, max_tokens=0):
            class R:
                text = ('{"makeup_is_daytime_natural": "true", '
                        '"face_is_not_restructured": true, "notes": "x"}')
                input_tokens = output_tokens = 0
            return R()

    reading = bible.judge("frame.png", provider=_Provider())
    assert reading["answers"] == {"face_is_not_restructured": True}
    assert bible.gate(reading)["verdict"] == "unjudged"


def test_what_is_asked_for_and_what_is_checked_are_the_same_four_parts():
    """Two copies of one standard drift apart; the direction is generated from the axes."""
    direction = bible.direction()
    for axis in bible.AXES.values():
        assert axis["range"] in direction


def test_rejected_drift_is_read_from_the_record_and_is_empty_when_nothing_was_refused():
    """Inventing plausible failures would be the fabricated evidence this company refuses.

    It would also be useless. The examples worth keeping are the refusals that actually
    happened here, with the measurement that caused each one.
    """
    out = bible.rejected_drift(_db())
    assert out["examples"] == [] and out["count"] == 0
    assert "not composed" in out["read_from"]
    assert "fact about the record" in out["note"]


def test_a_pack_build_that_could_not_be_frozen_becomes_a_rejected_example():
    from brambleloop.agents.registry import Registry
    from brambleloop.visual import reference_pack

    db = _db()
    Registry(db).audit("creative_director", reference_pack.PACK_ACTION, detail={
        "built": True, "pack_version": "v16-the-one-with-an-unreadable-chest",
        "candidate_fingerprint": "abc",
        "reference_frames": [], "identity": {}})

    out = bible.rejected_drift(db)
    assert out["count"] == 1
    example = out["examples"][0]
    assert example["kind"] == "pack_build_refused"
    assert example["pack_version"] == "v16-the-one-with-an-unreadable-chest"
    assert example["why_refused"]


def test_the_canonical_pack_is_never_listed_as_drift():
    """The one thing this list must not do.

    A rejected-drift list that names the approved identity as drift would be worse than no
    list, so which build became canonical is read out of the freeze record rather than
    guessed from which build is newest.
    """
    from brambleloop.agents.registry import Registry

    db = _db()
    Registry(db).audit("creative_director", "model.frozen",
                       detail={"freeze": {"pack_version": "v15-the-approved-one"}})
    assert bible.frozen_from(db) == "v15-the-approved-one"
    assert bible.rejected_drift(db)["canonical_pack_version"] == "v15-the-approved-one"


def test_a_field_the_owner_has_not_answered_yet_is_not_a_list_of_rejections():
    """Declining is a decision, and reading an open field as rejected invents one."""
    import ast

    source = (ROOT / "src/brambleloop/visual/bible.py").read_text()
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_declined_finalists")
    guarded = any(isinstance(n, ast.Attribute) and n.attr == "owner_candidate_supplied"
                  for n in ast.walk(fn))
    assert guarded, "the finalists are listed as rejected without the owner having answered"


def test_changing_the_rules_is_a_version_event():
    assert bible.BIBLE_VERSION
    assert bible.gate(_reading())["bible_version"] == bible.BIBLE_VERSION
    assert "brand-version event" in bible.state()["changing_it"]


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
