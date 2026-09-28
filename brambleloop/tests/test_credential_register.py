"""The credential rotation register (F-160): exposed credentials stay owner cards until rotated.

Names and events only. The tests prove three things: the chat-exposed Anthropic key is seeded and
is raised as an owner card; a rotation with evidence retires the card; and the register refuses
to hold anything shaped like a credential value, so it can never become the leak it tracks.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import credential_register as C  # noqa: E402


def test_the_chat_exposed_anthropic_key_is_seeded_as_rotation_required():
    names = {e.name: e for e in C.REGISTER}
    assert "ANTHROPIC_API_KEY" in names
    e = names["ANTHROPIC_API_KEY"]
    assert e.status == C.ROTATION_REQUIRED and e.exposed_at == "2026-09-19"
    assert "Railway" in e.held_in


def test_every_unrotated_credential_is_an_owner_card_in_the_directive_format():
    reqs = C.owner_requests()
    assert [r.key for r in reqs] == [C.KEY_PREFIX + e.name for e in C.pending()]
    assert reqs, "the seeded exposure produced no card"
    card = reqs[0]
    assert card.key == "credential_rotation:ANTHROPIC_API_KEY"
    # The Execution Directive's fields: exact action, why, max cost, minutes, consequence.
    assert "Rotate ANTHROPIC_API_KEY" in card.action and "revoke" in card.action
    assert card.max_cost_cad == 0.0 and card.minutes > 0
    assert card.reason and card.consequence_of_delay


def test_a_rotation_with_evidence_retires_the_card_and_age_alone_never_does():
    seeded = C.REGISTER[0]
    old = dataclasses.replace(seeded, exposed_at="2020-01-01")
    assert C.owner_requests((old,)), "an old exposure aged out without being rotated"
    done = dataclasses.replace(seeded, rotated_at="2026-10-01",
                               rotation_evidence="new key authenticated in production")
    assert done.status == C.ROTATED
    assert C.owner_requests((done,)) == []
    assert C.validate((done,)) == []


def test_rotated_without_evidence_or_before_exposure_is_a_problem():
    seeded = C.REGISTER[0]
    assert C.validate((dataclasses.replace(seeded, rotated_at="2026-10-01"),))
    assert C.validate((dataclasses.replace(seeded, rotated_at="2026-01-01",
                                           rotation_evidence="x"),))
    assert C.validate((seeded, seeded)), "a duplicated name was accepted"


def test_the_register_refuses_an_entry_carrying_something_shaped_like_a_value():
    value = "sk-" + "ant-api03-" + "Q" * 40          # built at runtime; never a literal
    leaky = dataclasses.replace(C.REGISTER[0], exposure="the key was " + value)
    problems = C.validate((leaky,))
    assert problems and all(value not in p for p in problems), problems


def test_the_live_register_is_sound_and_has_no_field_that_could_hold_a_value():
    assert C.validate() == []
    fields = {f.name for f in dataclasses.fields(C.Exposure)}
    assert not fields & {"value", "secret", "token", "key_value"}, fields
    rep = C.report()
    assert rep["rotation_required"] == ["ANTHROPIC_API_KEY"] and rep["problems"] == []


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
