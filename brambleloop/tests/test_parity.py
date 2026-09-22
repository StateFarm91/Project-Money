"""The eight-part parity gate, and the ways a partial gate calls itself a whole one (#75).

The requirement names eight independent checks and says any failure blocks release. Four
existed and four did not, and the tempting move was to report the four and call it mostly
met. Eight checks where four are imaginary is a four-check gate with a better name, so most
of these tests are about the gate being unable to produce a verdict it has not earned.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.visual import parity  # noqa: E402


def _frame(role: str = "hero", **overrides) -> dict:
    out = {
        "role": role,
        "carries_model": True,
        "readable_at_grid": True,
        "identity": {"verdict": "pass"},
        "motif": {"verdict": "match"},
        "photographic_realism": {"verdict": "clear"},
        "inspection": {"described": True,
                       "semantic": {"finished_or_in_progress_agrees": True}},
        "conditioned_on": {"pack_version": 1},
    }
    out.update(overrides)
    return out


def _clean_set() -> list[dict]:
    return [_frame("hero"), _frame("detail", carries_model=False),
            _frame("chart", carries_model=False)]


def _benchmarked() -> dict:
    return {"materially_inferior": False, "why": "compared against 12 observed listings"}


def test_all_eight_are_judged_and_a_partial_set_cannot_produce_a_verdict():
    """The property the requirement actually asks for, asserted over the module."""
    out = parity.assess(_clean_set(), benchmark_quality=_benchmarked())
    assert set(out["dimensions"]) == set(parity.DIMENSIONS)
    assert len(parity.DIMENSIONS) == 8
    assert out["of"] == 8 and out["judged"] == 8
    assert out["verdict"] == parity.PASS
    assert out["blocks_release"] is False


def test_any_one_failure_blocks_and_the_other_seven_cannot_outvote_it():
    """No score, no majority. Seven passes and one failure is a blocked release."""
    for role_kw in (
        {"identity": {"verdict": "fail"}},
        {"motif": {"verdict": "mismatch"}},
        {"photographic_realism": {"verdict": "blocked"}},
        {"readable_at_grid": False},
        {"inspection": {"described": True,
                        "semantic": {"finished_or_in_progress_agrees": False}}},
    ):
        frames = [_frame("hero", **role_kw), _frame("detail", carries_model=False),
                  _frame("chart", carries_model=False)]
        out = parity.assess(frames, benchmark_quality=_benchmarked())
        assert out["verdict"] == parity.FAIL, (role_kw, out["dimensions"])
        assert out["blocks_release"] is True
        assert len(out["failed"]) >= 1
        # The other dimensions still report their own answer rather than being collapsed.
        assert out["judged"] == 8


def test_unjudged_blocks_exactly_as_a_failure_does_and_is_reported_apart_from_one():
    """The two need opposite next moves -- a different render, or the question asked --
    so they are never the same word, and neither is a pass."""
    out = parity.assess(_clean_set())          # no benchmark comparison supplied
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] == parity.UNJUDGED
    assert out["verdict"] == parity.UNJUDGED
    assert out["blocks_release"] is True
    assert out["failed"] == []
    assert parity.COMPETITIVE in out["unjudged"]
    assert "unjudged is not a pass" in out["why"]


def test_competitive_is_never_assumed_favourable():
    """The one dimension where silence is most tempting: assuming this company compares
    well is the answer nobody has evidence for."""
    out = parity.assess(_clean_set(), benchmark_quality=None)
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] == parity.UNJUDGED
    assert "nobody has evidence" in out["dimensions"][parity.COMPETITIVE]["why"]

    worse = parity.assess(_clean_set(), benchmark_quality={
        "materially_inferior": True, "why": "thinner styling than every observed listing"})
    assert worse["dimensions"][parity.COMPETITIVE]["verdict"] == parity.FAIL


def test_a_product_only_gallery_is_not_asked_about_identity():
    """A frame with no model has no identity to drift. Not asked is a different answer
    from passed, and it must not become a failure either."""
    frames = [_frame("hero", carries_model=False, identity=None, conditioned_on=None),
              _frame("chart", carries_model=False, identity=None, conditioned_on=None)]
    out = parity.assess(frames, benchmark_quality=_benchmarked())
    assert out["dimensions"][parity.IDENTITY]["verdict"] == parity.PASS
    assert "no identity to be wrong" in out["dimensions"][parity.IDENTITY]["why"]
    assert out["dimensions"][parity.BRAND]["verdict"] == parity.PASS


def test_brand_is_one_identity_across_the_set_rather_than_a_look():
    """Structural, and answered structurally: two model frames conditioned on different
    packs is two women in one gallery, which no vision model needs to be asked about."""
    frames = [_frame("hero", conditioned_on={"pack_version": 1}),
              _frame("fit", conditioned_on={"pack_version": 2}),
              _frame("chart", carries_model=False)]
    out = parity.assess(frames, benchmark_quality=_benchmarked())
    assert out["dimensions"][parity.BRAND]["verdict"] == parity.FAIL
    assert "more than one identity" in out["dimensions"][parity.BRAND]["why"]

    unrecorded = [_frame("hero", conditioned_on={}), _frame("chart", carries_model=False)]
    assert parity.assess(unrecorded, benchmark_quality=_benchmarked())[
        "dimensions"][parity.BRAND]["verdict"] == parity.UNJUDGED


def test_a_gallery_of_pretty_frames_with_no_evidence_frame_fails():
    """"Complete purposeful sequence" is not a count. A set of three hero shots is three
    frames doing one job, and the buyer still cannot see how it is built."""
    frames = [_frame("hero"), _frame("lifestyle"), _frame("fit")]
    out = parity.assess(frames, benchmark_quality=_benchmarked())
    assert out["dimensions"][parity.GALLERY]["verdict"] == parity.FAIL
    assert "engineering-evidence" in out["dimensions"][parity.GALLERY]["why"]

    filler = [_frame("hero"), _frame("decorative-extra"), _frame("chart",
                                                                carries_model=False)]
    assert parity.assess(filler, benchmark_quality=_benchmarked())[
        "dimensions"][parity.GALLERY]["verdict"] == parity.FAIL


def test_the_gate_refuses_to_answer_from_fewer_than_eight_dimensions():
    """The guard on the guard: if a dimension is ever dropped from the computation, the
    gate raises rather than quietly reporting a seven-part verdict as parity."""
    original = parity.DIMENSIONS
    try:
        parity.DIMENSIONS = original + ("a_ninth_thing",)
        try:
            parity.assess(_clean_set(), benchmark_quality=_benchmarked())
        except parity.ParityRefused as exc:
            assert "all eight" in str(exc)
        else:                                                # pragma: no cover
            raise AssertionError("a partial parity set produced a verdict")
    finally:
        parity.DIMENSIONS = original


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
