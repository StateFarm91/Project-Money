"""A styled product image the company owns, and the rules that keep it honest.

Requirements 292 and 300 both ended at the same wall: a certified seasonal product with no
picture of the finished object. The capability exists now. What these tests protect is the
difference between having a picture and claiming to have made the thing in it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish import owned_photography as op  # noqa: E402
from brambleloop.visual import inspect as inspect_mod  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _subject(slug: str = "cloudline-baby-blanket"):
    cir = for_slug(slug)
    return cir, build_twin(cir, compile_cir(cir))


def _generator(tmp: Path):
    def generate(prompt, *, env=None, size="1024x1024", reference_urls=None):
        path = tmp / "asset.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"image_ref": str(path), "provider": "gpt-image-2", "cad": 0.04}
    return generate


def _inspector(**overrides):
    def inspect(image_ref, *, db=None, claim=None):
        out = {
            "image": image_ref, "described": True, "realism_judged": True,
            "description": {"finished_or_in_progress": "finished", "chart_or_diagram": False,
                            "human_present": False, "clarity": "clear", "object_count": "1",
                            "third_party_marks": []},
            "realism": {k: True for k in inspect_mod.REALISM_CHECKS},
            "realism_unjudged": [],
        }
        out.update(overrides)
        if claim:
            out["semantic"] = inspect_mod.compare(out["description"], claim)
        return out
    return inspect


def _motif(**overrides):
    """A motif judge that sees the chart's own pattern unless told otherwise."""
    answer = {"repeating_unit_shape": "diamond outline lattice", "repeats_across": 14,
              "colour_arrangement": "two colours alternating", "same_pattern_as_chart": True,
              "fabric_readable": True}
    answer.update(overrides)
    return lambda image_ref, chart_ref: answer


def _make(tmp: Path, **kw):
    cir, twin = _subject()
    return op.make(_db(), cir, twin, generator=_generator(tmp),
                   inspector=_inspector(**kw.pop("inspection", {})),
                   motif_judger=kw.pop("motif_judger", _motif()), **kw)


def test_the_prompt_is_derived_from_the_certified_pattern():
    """A prompt somebody typed is a second, unvalidated description of the product."""
    cir, twin = _subject()
    prompt = op.prompt_for(cir, twin, occasion="Christmas")
    for name in cir.colors:
        assert name in prompt, name
    assert f"{twin.width_cm:.0f} by {twin.height_cm:.0f} cm" in prompt
    assert "blanket" in prompt
    # The hex codes the twin renders with describe nothing to a generator or to a reader.
    assert "#" not in prompt
    # And nothing that would put somebody else's mark, or a person, in the frame.
    assert "no logos" in prompt and "No people" in prompt


def test_it_is_an_illustration_and_it_says_so_everywhere():
    """This company has not photographed a made item, and must never imply that it has."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp))
    assert record["generated"] is True
    assert record["disclosed_as_illustration"] is True
    assert "Not a photograph of a made item" in record["disclosure"]
    assert "fabricated proof" in record["never_a_photograph"]


def test_a_picture_that_does_not_show_what_the_pattern_says_is_not_usable():
    """The describer never sees the claim; the comparison is deterministic code."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp), inspection={"description": {
            "finished_or_in_progress": "in progress", "chart_or_diagram": False,
            "human_present": False, "clarity": "clear", "object_count": "1"}})
    assert record["verdict"] == "blocked"
    assert record["usable_as_listing_asset"] is False


def test_an_unmade_realism_check_is_not_a_pass():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp), inspection={
            "realism_judged": False, "realism": {},
            "realism_unjudged": sorted(inspect_mod.REALISM_CHECKS)})
    assert record["verdict"] == "unjudged"
    assert record["usable_as_listing_asset"] is False


def test_a_clean_render_whose_fabric_is_the_chart_is_a_listing_image():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp))
    assert record["verdict"] == "clear"
    assert record["image"]["url"].startswith("/api/model-tournament/image/")
    assert record["spent_cad"] == 0.04
    assert record["motif_verified"] is True
    assert record["usable_as_listing_asset"] is True


def test_the_checkerboard_that_started_this_is_blocked():
    """The live failure, as the test that keeps it failing.

    A clean, believable crocheted blanket in the right two colours, on the right surface,
    in the right light -- worked in a checkerboard, while the certified pattern makes a
    diamond lattice on a nine-stitch repeat. Everything else about it was right, which is
    why nothing caught it.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp), motif_judger=_motif(
            repeating_unit_shape="solid square", repeats_across=8))
    assert record["verdict"] == "clear", "the asset-truth checks still pass, as they did"
    assert record["motif_verified"] is False
    assert record["usable_as_listing_asset"] is False
    assert record["motif"]["verdict"] == "mismatch"


def test_fabric_nobody_could_see_blocks_too_and_says_what_it_needs():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = _make(Path(tmp), motif_judger=_motif(fabric_readable=False))
    assert record["motif"]["verdict"] == "unmeasurable"
    assert record["usable_as_listing_asset"] is False
    assert "closer" in record["motif"]["why"]


def test_the_prompt_states_the_patterns_own_motif():
    cir, twin = _subject()
    assert "diamond lattice" in op.prompt_for(cir, twin).lower()
    assert "9-stitch repeat" in op.prompt_for(cir, twin)


def test_a_product_whose_listing_needs_the_model_is_refused_for_the_true_reason():
    """A worn form is refused, and the refusal has to say which of two things is missing.

    It used to return one hardcoded sentence -- "she is built but not approved" -- and on
    2026-09-22 that became false while still being returned: the owner approved and froze
    the canonical identity, and a garment went on being refused for a reason that had
    expired. A refusal that states a condition instead of reading it is the same defect as
    a gate reading configuration rather than demonstrated capability, and worse in a
    message, because the message is what the next session believes.

    A product-first form waits on neither -- #204 says a clean product-only hero outsells
    a modelled one for exactly these forms.
    """
    import dataclasses
    import tempfile

    from brambleloop.visual import freeze, identity, model_registry

    cir, twin = _subject()
    # The same certified object under a garment's slug: the form is what decides, and a
    # cardigan's listing has to answer a question only a body can answer.
    garment = dataclasses.replace(cir, slug="winter-cardigan", title="Cardigan")
    assert op.needs_no_model(cir) is True
    assert op.needs_no_model(garment) is False

    # No canonical identity: blocked on the owner's decision.
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        record = op.make(db, garment, twin, generator=_generator(Path(tmp)),
                         inspector=_inspector())
    assert record["made"] is False
    assert record["waiting_on"] == "canonical_model"
    assert "no canonical identity has been approved" in record["why"]

    # Frozen: she exists and is enforced, so what is missing is the render path -- which
    # is this build's work rather than a decision, and the message must say so.
    model_registry.record_candidate(
        db, "brambleloop-canonical",
        fields={f: "described" for f in identity.IDENTITY_FIELDS},
        image_refs=[freeze.brief.approved_portrait()])
    model_registry.select_canonical(db, "brambleloop-canonical", owner_approved=True)

    with tempfile.TemporaryDirectory() as tmp:
        after = op.make(db, garment, twin, generator=_generator(Path(tmp)),
                        inspector=_inspector())
    assert after["made"] is False
    assert after["waiting_on"] == "model_bearing_render_path"
    assert "approved and frozen" in after["why"]
    assert "not approved" not in after["why"], "the expired reason came back"


def test_the_provider_is_named_rather_than_left_to_a_variable_nobody_set():
    """The first live run of this job died inside the gateway for exactly this.

    `images.generate` without a provider falls back to `BRAMBLELOOP_IMAGE_PROVIDER`, which
    nobody has set, so it resolved to None and the call failed with an AttributeError deep
    in the request builder. The benchmark already measured which model renders listing
    imagery; using its leader is what that measurement was for.
    """
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/publish/owned_photography.py").read_text())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "generate"]
    assert calls, "nothing generates an image here any more"
    for call in calls:
        assert "provider_key" in {kw.arg for kw in call.keywords}, ast.dump(call)[:120]

    # And with nothing able to render, it declines rather than crashing.
    cir, twin = _subject()
    record = op.make(_db(), cir, twin)
    assert record["made"] is False
    assert "no verified image provider" in record["why"]


def test_the_seasonal_cycle_reports_the_asset_rather_than_rendering_one():
    """A report that spent money every time somebody opened an endpoint would spend money
    to answer a question about the past -- and the endpoint sweep walks every GET route."""
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/seasonal/cycle.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("generate", "make"):
            raise AssertionError("the cycle renders an image while reporting")
    source = (ROOT / "src/brambleloop/seasonal/cycle.py").read_text()
    assert "last_asset" in source


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
