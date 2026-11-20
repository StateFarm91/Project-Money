"""The listing as a shopper meets it, which is never the listing as it was built.

Requirement 66. A listing is assembled at full size, one frame at a time, by somebody who
already knows what the product is. It is chosen at 170 pixels, in a grid of competitors, by
somebody who does not. Every check that runs only at build size runs in a context no shopper
is ever in.

The first three frames are the part worth getting right: they are a context rather than a
prefix. Most people do not scroll, so those three answer the buying question between them or
nothing does, and an excellent gallery below them is invisible.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.gates.asset_truth import AssetClass  # noqa: E402
from brambleloop.publish import eligibility as E  # noqa: E402
from brambleloop.publish import mobile as M  # noqa: E402


def _frame(position: int, job: str, asset_id: str, *,
           medium=AssetClass.INFOGRAPHIC, purpose=E.CUSTOMER_INFORMATION):
    return E.Candidate(asset_id=asset_id, medium=medium, purpose=purpose,
                       job=job, position=position)


def _good_frames():
    return [
        _frame(1, E.DESIRE, "hero", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
               purpose=E.CONVERSION_CREATIVE),
        _frame(2, E.SCALE, "size"),
        _frame(3, E.CONTENTS, "contents"),
        _frame(4, E.MATERIALS, "materials"),
    ]


def _renders(**kw):
    out = []
    for name in M.CONTEXTS:
        spec = M.CONTEXT_MEANS[name]
        out.append(M.ContextRender(context=name, render_ref=f"qa/{name}.png",
                                   frames_shown=spec["frames"] or 4, px=spec["px"],
                                   **kw))
    return out


# ---- the four contexts ----------------------------------------------------


def test_every_context_the_requirement_names_exists_in_order():
    assert M.CONTEXTS == (M.SEARCH_THUMBNAIL, M.PHONE_GALLERY, M.FIRST_THREE,
                          M.FULL_GALLERY)
    assert M.CONTEXT_MEANS[M.SEARCH_THUMBNAIL]["px"] < M.CONTEXT_MEANS[M.FULL_GALLERY]["px"]


def test_the_thumbnail_is_where_the_decision_is_made():
    assert "where the decision is made" in M.CONTEXT_MEANS[M.SEARCH_THUMBNAIL]["why"]
    assert "fewest shoppers reach" in M.CONTEXT_MEANS[M.FULL_GALLERY]["why"]


def test_an_invented_context_is_refused():
    try:
        M.ContextRender(context="desktop", render_ref="x.png", frames_shown=1, px=2000)
    except M.MobileRefused as e:
        assert "is not a context" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a context nobody shops in was accepted")


# ---- a pass with no render cannot be re-examined --------------------------


def test_a_context_with_no_stored_render_is_refused():
    try:
        M.ContextRender(context=M.SEARCH_THUMBNAIL, render_ref="  ", frames_shown=1, px=170)
    except M.MobileRefused as e:
        assert "underperforms three months later" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a QA pass was recorded with nothing to look at")


def test_an_unrendered_context_is_not_a_passing_one():
    out = M.qa(_good_frames(), [])
    assert out["complete"] is False
    assert out["not_rendered"] == list(M.CONTEXTS)
    assert "Not the same as passing it" in out["contexts"][M.SEARCH_THUMBNAIL]["problem"]


def test_every_context_rendered_completes_the_pass():
    out = M.qa(_good_frames(), _renders())
    assert out["complete"] is True and out["ok"] is True


def test_two_renders_of_one_context_let_somebody_pick():
    renders = _renders()
    renders.append(M.ContextRender(context=M.SEARCH_THUMBNAIL, render_ref="qa/other.png",
                                   frames_shown=1, px=170))
    try:
        M.qa(_good_frames(), renders)
    except M.MobileRefused as e:
        assert "picks which to look at" in str(e)
    else:  # pragma: no cover
        raise AssertionError("one context was rendered twice and QA accepted it")


def test_ink_in_the_title_safe_band_is_not_hard_to_read_but_invisible():
    out = M.qa(_good_frames(), _renders(ink_in_title_safe=0.12))
    assert out["ok"] is False
    assert "not visible" in out["contexts"][M.SEARCH_THUMBNAIL]["problem"]


# ---- the first three are a context, not a prefix --------------------------


def test_three_frames_answering_different_questions_pass():
    out = M.first_three(_good_frames())
    assert out["ok"] is True
    assert out["distinct_jobs"] == 3


def test_three_frames_all_doing_one_job_is_one_frame_shown_three_times():
    frames = [_frame(1, E.DESIRE, "a", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=E.CONVERSION_CREATIVE),
              _frame(2, E.DESIRE, "b", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=E.CONVERSION_CREATIVE),
              _frame(3, E.DESIRE, "c", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=E.CONVERSION_CREATIVE)]
    out = M.first_three(frames)
    assert out["ok"] is False
    assert any(p["kind"] == "all_one_job" for p in out["problems"])
    assert "one frame, shown three times" in out["problems"][0]["why"]


def test_nothing_selling_in_the_first_three_fails_at_the_depth_most_people_reach():
    frames = [_frame(1, E.SCALE, "a"), _frame(2, E.CONTENTS, "b"),
              _frame(3, E.MATERIALS, "c"),
              _frame(4, E.DESIRE, "hero", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=E.CONVERSION_CREATIVE)]
    out = M.first_three(frames)
    assert out["ok"] is False
    assert any(p["kind"] == "nothing_sells" for p in out["problems"])
    assert "nobody will reach it" in out["problems"][0]["why"]


def test_only_the_first_three_are_examined_however_long_the_gallery():
    frames = _good_frames() + [_frame(9, E.PROOF, "proof",
                                      medium=AssetClass.PHYSICAL_PRODUCT_PHOTO,
                                      purpose=E.PHYSICAL_PROOF)]
    out = M.first_three(frames)
    assert out["frames"] == ["hero", "size", "contents"]


def test_a_thin_gallery_is_reported_without_being_a_defect():
    frames = [_frame(1, E.DESIRE, "hero", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                     purpose=E.CONVERSION_CREATIVE),
              _frame(2, E.SCALE, "size")]
    out = M.first_three(frames)
    assert out["ok"] is True, "two good frames are not a failure"
    assert any(p["kind"] == "thin_gallery" for p in out["problems"])
    assert "the space is there and empty" in out["problems"][0]["why"]


def test_a_listing_with_no_frames_has_no_first_three():
    try:
        M.first_three([])
    except M.MobileRefused as e:
        assert "no first three" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an empty listing was evaluated")


def test_the_first_three_failing_fails_the_whole_qa():
    frames = [_frame(1, E.SCALE, "a"), _frame(2, E.CONTENTS, "b"),
              _frame(3, E.MATERIALS, "c")]
    out = M.qa(frames, _renders())
    assert out["complete"] is True
    assert out["ok"] is False


def test_the_scroll_count_is_stated_once_so_the_contexts_cannot_drift():
    assert M.CONTEXT_MEANS[M.PHONE_GALLERY]["frames"] == M.BEFORE_SCROLL
    assert M.CONTEXT_MEANS[M.FIRST_THREE]["frames"] == M.BEFORE_SCROLL


def test_state_names_the_context_the_builder_never_occupies():
    out = M.state()
    assert out["requirement"] == 66
    assert "context rather than a prefix" in out["note"]


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
