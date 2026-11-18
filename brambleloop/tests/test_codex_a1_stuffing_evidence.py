"""Explicit stuffing is a hold even when geometry doesn't identify the closure."""
import dataclasses

import test_a1r_child_safety_core as harness
from brambleloop.cir.compiler import compile_cir
from brambleloop.products import inventory, launch0


def test_unseamed_opening_and_component_note_hold_in_real_worker():
    ball = harness._one_piece_ball()
    # Eighteen stitches remain; the pattern explicitly says to close the opening.
    part = dataclasses.replace(ball.components[0], rows=ball.components[0].rows[:-2],
                               note="Stuff firmly and close the opening.")
    filled = dataclasses.replace(ball, components=[part])
    assert compile_cir(filled).ok
    assert launch0.closed_stuffed_form(filled)
    assert harness._held(harness._assets_build_full(filled))
    # A note alone is evidence too, including a row note rather than a component note.
    row = dataclasses.replace(part.rows[-1], note="Fill with stuffing before closing.")
    part = dataclasses.replace(part, note=None, rows=part.rows[:-1] + [row])
    note_only = dataclasses.replace(filled, slug="codex-note-only",
        components=[part], materials=[m for m in filled.materials if m.yarn_weight])
    assert launch0.closed_stuffed_form(note_only)
    assert harness._held(harness._assets_build_full(note_only))
    # Action + object instruction without the literal word "stuffing" is still explicit.
    action_part = dataclasses.replace(part, rows=part.rows[:-1] + [
        dataclasses.replace(part.rows[-1], note=None)],
        note="Fill the body and close the opening.")
    action_only = dataclasses.replace(note_only, slug="codex-fill-body", components=[action_part])
    assert launch0.closed_stuffed_form(action_only)
    assert harness._held(harness._assets_build_full(action_only))
    # A plain basket is not held just because it has an unclosed round construction.
    basket = inventory._engineered("market-basket-small")
    assert not launch0.closed_stuffed_form(basket)
    assert harness._rendered(harness._assets_build_full(basket))


def test_existing_exemption_does_not_follow_a_slug_to_another_design():
    for slug in ("spring-garden-kneeler", "heart-row-ring-pillow"):
        original = inventory._engineered(slug)
        assert launch0.childrens_decision_for(original)[0] == launch0.NOT_FOR_CHILDREN
        for changed in (dataclasses.replace(harness._one_piece_ball(), slug=slug),
                        dataclasses.replace(original, version="9.9.9"),
                        dataclasses.replace(original, designer_notes="different instructions")):
            assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED
            assert harness._refused(changed), slug
    spoof = dataclasses.replace(harness._one_piece_ball(), slug="spring-garden-kneeler")
    assert harness._held(harness._assets_build_full(spoof))


if __name__ == "__main__":
    # Review U6 H2: run under the suite harness (one `OK name` line per test), without pytest.
    import _minipytest

    _minipytest.run_module(globals())
