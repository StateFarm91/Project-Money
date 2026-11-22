"""CONCEPT-BOARDS: a concept held at board_missing carries a fixed reason code, and the
readback counts them with no free text."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.creative.intake import BOARD_WHY_CODES, board_why_code  # noqa: E402
from brambleloop.ops.production_evidence import _board_why_codes  # noqa: E402


def test_codes_map_make_board_reasons():
    assert board_why_code({"why": "no prototype to render: boom"}) == "prototype_refused"
    assert board_why_code({"why": "the prototype does not compile, so there is no fabric"}) \
        == "prototype_not_compiling"
    assert board_why_code({"why": "the design's verified hero could not be drawn: the hero "
                                  "did not verify: ['x']"}) == "hero_not_verified"
    assert board_why_code({"why": "the design's verified hero could not be drawn: refused"}) \
        == "hero_render_refused"
    assert board_why_code({"board_image": "artifact:x"}) == "not_stored"
    assert board_why_code({"why": "something new"}) == "other"
    for code in ("prototype_refused", "concept_incomplete", "other"):
        assert code in BOARD_WHY_CODES


def test_readback_counts_only_fixed_codes():
    held = [{"code": "board_missing", "board_why": "prototype_refused", "waiting_on": ["secret text"]},
            {"code": "board_missing", "board_why": "free text leak"},
            {"code": "board_missing"},
            {"code": "no_vision"}]
    out = _board_why_codes(held)
    assert out == {"prototype_refused": 1, "other": 2}
    assert "secret" not in str(out) and "leak" not in str(out)


if __name__ == "__main__":
    test_codes_map_make_board_reasons()
    test_readback_counts_only_fixed_codes()
    print("OK test_concept_board_why")
