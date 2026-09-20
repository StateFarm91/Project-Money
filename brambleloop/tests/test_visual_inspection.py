"""Checks that were always named and never made, and the ways making them goes wrong.

`visual/gallery.py` has reported unmade realism checks as *unjudged* since it was written,
which was honest and useless: a listing that cannot ship and nobody can say why. The model
that could look at the picture arrived on 2026-09-19, filed under a gate named after a cloud
browser, and nobody noticed for a day.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import reference as REF  # noqa: E402
from brambleloop.visual import gallery, inspect as I  # noqa: E402


def _description(**over):
    base = {"object_shown": "a blanket", "object_count": 1,
            "finished_or_in_progress": "finished", "human_present": False,
            "text_present": False, "chart_or_diagram": False,
            "dominant_colours": "cream", "clarity": "clear"}
    base.update(over)
    return base


# ---- #61: does the picture say what the caption claims ----------------------


def test_the_model_is_never_shown_the_caption():
    """A grader shown the expected answer grades toward it, and "does this match" has an
    obvious polite answer. The requirement's own closing clause is about exactly this."""
    assert "caption" not in I.DESCRIBE_SYSTEM.lower()
    assert "claim" not in I.describe_prompt().lower()
    out = I.compare(_description(), {"shows_finished_object": True})
    assert "grades toward it" in out["method"]


def test_a_chart_cannot_be_the_finished_result_frame():
    out = I.compare(_description(chart_or_diagram=True), {"shows_finished_object": True})
    assert out["communicates"] is False
    assert any(p["check"] == "chart_as_hero" for p in out["problems"])


def test_work_in_progress_does_not_satisfy_a_finished_result_claim():
    out = I.compare(_description(finished_or_in_progress="in_progress"),
                    {"shows_finished_object": True})
    assert out["communicates"] is False
    assert out["problems"][0]["check"] == "finished_result"


def test_an_unreadable_frame_communicates_nothing_whatever_it_shows():
    out = I.compare(_description(clarity="unreadable"), {})
    assert out["communicates"] is False
    assert any(p["check"] == "clarity" for p in out["problems"])


def test_a_garment_claim_needs_somebody_wearing_it():
    out = I.compare(_description(human_present=False), {"shows_worn_garment": True})
    assert any(p["check"] == "worn_garment" for p in out["problems"])


def test_a_description_with_holes_is_refused():
    """A description that omits a field passes a caption check by not contradicting it."""
    raised = None
    try:
        I.parse_description('{"object_shown": "a hat"}')
    except I.InspectionRefused as exc:
        raised = exc
    assert raised is not None and "not answered" in str(raised)


def test_an_open_description_vocabulary_is_refused():
    raised = None
    try:
        I.parse_description('{"vibe": "lovely"}')
    except I.InspectionRefused as exc:
        raised = exc
    assert raised is not None and "vocabulary is closed" in str(raised)


# ---- #79: the ten physical-realism checks -----------------------------------


def test_unclear_leaves_a_check_unmade_rather_than_passing_it():
    """Defaulting an unmade check to True is how a release gate becomes a formality, and it
    is one line to write."""
    parsed = I.parse_realism('{"drape": true, "garment_fit": "unclear"}')
    assert parsed["checks"] == {"drape": True}
    assert "garment_fit" not in parsed["checks"]


def test_a_third_opinion_on_a_realism_check_is_refused():
    raised = None
    try:
        I.parse_realism('{"drape": "mostly"}')
    except I.InspectionRefused as exc:
        raised = exc
    assert raised is not None and "nobody can act on" in str(raised)


def test_a_check_outside_the_ten_is_refused():
    raised = None
    try:
        I.parse_realism('{"vibes_plausible": true}')
    except I.InspectionRefused as exc:
        raised = exc
    assert raised is not None and "not realism checks" in str(raised)


def test_applying_an_inspection_leaves_unmade_checks_unmade():
    frame = gallery.Frame(role="hero", position=1, generated=True)
    I.apply_to_frame(frame, {"realism": {"drape": True},
                             "description": {"clarity": "clear"}})
    assert frame.realism == {"drape": True}
    findings = gallery.check_frame(frame)
    assert any(f.get("unjudged") for f in findings), findings


def test_the_gate_has_three_outcomes_because_two_would_have_to_lie():
    blocked = I.gate({"realism": {"drape": False}, "realism_unjudged": []})
    assert blocked["verdict"] == "blocked"
    unjudged = I.gate({"realism": {"drape": True}, "realism_unjudged": ["garment_fit"]})
    assert unjudged["verdict"] == "unjudged"
    assert "Unmade is not passed" in unjudged["why"]
    clear = I.gate({"realism": {"drape": True}, "realism_unjudged": []})
    assert clear["verdict"] == "clear"


def test_a_failed_call_leaves_every_check_unmade_rather_than_green():
    class _Broken:
        model = "claude-sonnet-5"
        cost_per_1k_input_cad = 0.0
        cost_per_1k_output_cad = 0.0

        @staticmethod
        def key():
            return "k"

        def see(self, *a, **kw):
            from brambleloop.core.resilience import TransientError

            raise TransientError("provider said no")

    out = I.inspect_image("https://example.invalid/a.png", provider=_Broken())
    assert out["described"] is False and out["realism_judged"] is False
    assert sorted(out["realism_unjudged"]) == sorted(gallery.REALISM_CHECKS)
    assert I.gate(out)["verdict"] == "unjudged"


# ---- #116 / #278: what a competitor photograph may teach --------------------


def test_construction_is_learnable_and_depiction_is_not():
    """A crew neckline is a fact like a gauge; a gnome with a striped hat is a design."""
    assert REF.parse_reading('{"neckline": "crew", "edge_finish": "ribbed"}')
    raised = None
    try:
        REF.parse_reading('{"neckline": "a gnome face applique"}')
    except REF.ReferenceRefused as exc:
        raised = exc
    assert raised is not None and "how it is built" in str(raised)


def test_the_construction_vocabulary_has_nowhere_to_put_a_subject():
    raised = None
    try:
        REF.parse_reading('{"motif": "cardinal"}')
    except REF.ReferenceRefused as exc:
        raised = exc
    assert raised is not None and "where a subject arrives" in str(raised)
    for field in REF.CONSTRUCTION_FIELDS:
        assert field not in ("motif", "subject", "character", "scene")


def test_motif_density_is_a_quantity_and_never_a_description():
    """The field that describes a motif is the field that reproduces it."""
    assert set(REF.MOTIF_DENSITY) == {"none", "sparse", "scattered", "allover", "structural"}
    out = REF.primitives([{"detail_coverage": "allover repeat"}], [])
    assert out["primitives"]["motif_density"] == "allover"
    assert all(v in REF.MOTIF_DENSITY for k, v in out["primitives"].items()
               if k == "motif_density")


def test_a_primitive_nobody_could_read_is_absent_rather_than_neutral():
    """A neutral value keeps the brief's shape and loses its meaning."""
    out = REF.primitives([], [{"silhouette_class": "boxy"}])
    assert "silhouette" in out["primitives"]
    assert out["absent"]
    assert "keep the brief's shape" in out["why_absent"]


def test_containment_reuses_the_mechanism_word_list_rather_than_a_second_copy():
    """Two containment checks drift, and the one that drifts is the one on the competitor
    path, where being wrong is a rights problem rather than an aesthetic one."""
    from brambleloop.intel.mechanisms import DEPICTION_WORDS

    assert "culture.rights.check_free_of" in REF.state()["containment"]
    assert DEPICTION_WORDS, "the shared list is empty, so the check passes everything"


def test_a_brief_from_one_listing_is_an_instruction_to_make_that_product_again():
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs_off_the_hook_designs", listing_ref="1",
                               title="t", pod="garments"))
        s.add(BenchmarkObservation(benchmark_key="mjs_off_the_hook_designs",
                                   listing_ref="1", kind="gallery_image_observation",
                                   detail={"observation": {"setting": "studio"}}))
    out = REF.brief(db, "garments")
    assert out["usable"] is False
    assert "make that product again" in out["reason"]


def test_every_vision_call_site_routes_through_a_declared_task():
    """The reconciliation the owner's quality-first policy asked for, as a property.

    Four modules constructed a provider with a hardcoded cheap model and never consulted
    `routing.TASKS` at all -- so the declared tier for gallery observation said `standard`
    while the code that made the call used `cheap`, on the owner's second-highest spending
    priority. A table nothing reads is documentation.
    """
    from brambleloop.creative import reference
    from brambleloop.gateway import image_bench, routing
    from brambleloop.intel import vision

    for module in (I, reference, vision, image_bench):
        task = getattr(module, "TASK", None) or getattr(module, "JUDGE_TASK", None)
        assert task, f"{module.__name__} makes vision calls and declares no routed task"
        assert task in routing.TASKS, f"{module.__name__} routes through undeclared {task!r}"


def test_no_module_names_a_model_string_outside_the_routing_table():
    """A hardcoded model is a routing decision made where nobody looks for one."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "brambleloop"
    allowed = {"gateway/routing.py", "gateway/anthropic.py", "gateway/model_gateway.py"}
    offenders = []
    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root))
        if rel in allowed:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'["\']claude-(opus|sonnet|haiku)', line):
                offenders.append(f"{rel}:{number}")
    assert offenders == [], (
        f"{offenders} name a model directly. Routing belongs in routing.TASKS, where the "
        f"tier, the token budget and the ledger's purpose are decided together")


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
