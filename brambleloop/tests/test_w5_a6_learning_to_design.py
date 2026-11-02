"""A6 P0-LEARNING-INTO-DESIGN (consumer side): an approved `construction_preference` lesson
changes the construction `cir.draft` drafts, against the no-lesson baseline, and a
`lesson.acted_on` row records it (wiring #4, acceptance in P0_WIRING_50937469.md s4).

Every test here drives the real runtime on a real SQLite file: `creative.tournament` through
the handler registry (only the model is a fixture generator, as in test_cert_design_pipeline),
the recorded vision judgement, `mjs.seasonal_sentinel` re-presenting the winner, and the
queued `cir.draft` and `cir.compile` jobs through the Worker. A lesson changes a design only
through a declared parameter and only with an independent approval on file; its words never
become geometry.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w5_a6_learning_to_design.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_design_pipeline as D  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.core.models import JobStatus, Lesson  # noqa: E402
from brambleloop.creative.family import FORM_CONSTRUCTIONS  # noqa: E402
from brambleloop.creative.prospecting import ENGINE_ROUTE  # noqa: E402
from brambleloop.improve import bus, consume  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _winner(db) -> dict:
    """A carried, judged winner, queued for drafting by the real cadence."""
    D._stockings(db)
    _result, row = D._tournament(db)
    assert row["funnel"]["carried"] is True, row["funnel"]
    D._judge(db, row["concept"]["key"])
    D._handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert len(D._jobs(db, "cir.draft")) == 1
    return row["concept"]


def _draft(db) -> tuple[dict, CIR]:
    done = D._drain(db, "cir.draft")
    assert done[0]["status"] == JobStatus.DONE, done
    out = done[0]["outputs"]
    compiles = D._jobs(db, "cir.compile")
    assert out.get("drafted") is True and compiles, out
    return out, CIR.from_dict(compiles[-1].inputs["cir"])


def _other_construction(concept: dict) -> str:
    """A construction that builds the winner's form and drafts a different CIR construction."""
    here = ENGINE_ROUTE[concept["construction"]]
    for c in sorted(FORM_CONSTRUCTIONS[concept["form"]]):
        if ENGINE_ROUTE.get(c) not in (None, here) and not pipeline._names_a_construction(
                c.replace("_", " ")):
            return c
    for c in sorted(FORM_CONSTRUCTIONS[concept["form"]]):
        if ENGINE_ROUTE.get(c) not in (None, here):
            return c
    raise AssertionError(f"no alternative construction for {concept['form']}")


def _lesson(db, concept: dict, *, subject="construction_preference", words=None) -> int:
    """A construction preference whose statement names what the winner is."""
    form = concept["form"].replace("_", " ")
    motif = str(concept.get("motif") or "").split()[0]
    words = words or f"{motif} {form}"
    return bus.publish(db, origin_cell="market_radar", subject=subject,
                       statement=(f"buyers of {words} designs favour a different "
                                  f"construction in recorded tests and reviews"),
                       evidence_ref=f"fixture:{subject}:{words}")


def test_an_approved_construction_preference_changes_the_drafted_construction():
    """The acceptance: baseline vs lesson, same winner; the drafted CIR's construction
    differs, it compiles, and `lesson.acted_on` plus the lesson's acted_on_by record it."""
    base_db = D._db()
    concept = _winner(base_db)
    base_out, base_cir = _draft(base_db)
    assert consume.design_directives(base_db, concept["title"])["construction"] is None

    db = D._db()
    again = _winner(db)
    assert again["key"] == concept["key"] and again["construction"] == concept["construction"]
    want = _other_construction(concept)
    lid = _lesson(db, concept)
    consume.approve_for_design(db, lid, parameter="construction", value=want,
                               approved_by="owner",
                               why="recorded tests favour this construction for the form")
    out, cir = _draft(db)
    assert cir.construction == ENGINE_ROUTE[want] != base_cir.construction, (
        cir.construction, base_cir.construction)
    assert out["construction"] == cir.construction and out["learning"]["applied"] == [lid]
    compiled = D._drain(db, "cir.compile")
    assert compiled[-1]["outputs"].get("compiled") is True, compiled[-1]
    rows = [d for _i, a, d in D._rows(db, consume.DESIGN_APPLIED) if a == f"lessons:{lid}"]
    assert consume.DESIGN_APPLIED == "lesson.acted_on" and len(rows) == 1, rows
    assert rows[0]["change"] == {"parameter": "construction", "from": concept["construction"],
                                 "to": want} and rows[0]["subject"] == concept["key"]
    with db.session() as s:
        acted = [e["cell"] for e in (s.get(Lesson, lid).acted_on_by or [])]
    assert acted == [consume.DESIGN_CELL], acted
    # the baseline draft is unchanged by the lesson's existence elsewhere
    assert base_out.get("learning") is None


def test_an_unapproved_or_wrong_subject_lesson_changes_nothing():
    """A matching preference with no independent approval is reported and ignored; a
    defect lesson may not set a construction; the origin may not approve its own lesson."""
    db = D._db()
    concept = _winner(db)
    want = _other_construction(concept)
    lid = _lesson(db, concept)
    for who in ("market_radar", consume.DESIGN_CELL):
        try:
            consume.approve_for_design(db, lid, parameter="construction", value=want,
                                       approved_by=who, why="it says so in the lesson text")
        except consume.DesignApprovalRefused:
            pass
        else:
            raise AssertionError(f"{who} approved its own or its consumer's lesson")
    # defence in depth: a lesson whose recorded origin is the judging role itself is not
    # independently reviewed by that role (no cell publishes as one today)
    judged = _lesson(db, concept, words=f"{concept['form'].replace('_', ' ')} evaluator-made")
    with db.session() as s:
        s.get(Lesson, judged).origin_cell = "evaluator"
    try:
        consume.approve_for_design(db, judged, parameter="construction", value=want,
                                   approved_by="evaluator", why="it judged its own lesson here")
    except consume.DesignApprovalRefused:
        pass
    else:
        raise AssertionError("the origin of a lesson approved it")
    defect = _lesson(db, concept, subject="defect")
    try:
        consume.approve_for_design(db, defect, parameter="construction", value=want,
                                   approved_by="owner", why="a defect is not a preference")
    except consume.DesignApprovalRefused:
        pass
    else:
        raise AssertionError("a defect lesson was approved to set a construction")
    out, cir = _draft(db)
    assert cir.construction == ENGINE_ROUTE[concept["construction"]], cir.construction
    assert lid in out["learning"]["unapproved_ignored"], out
    assert not [r for r in D._rows(db, consume.DESIGN_APPLIED)]


def test_a_preference_never_overrides_a_construction_the_concept_names_or_its_form_refuses():
    """A concept whose own words name its construction keeps it; a preferred construction
    that cannot build the form is not applied; both say why."""
    assert pipeline._names_a_construction("Juniper Granny Square Pillow")
    assert not pipeline._names_a_construction("Juniper Holly Stocking")
    found = {"construction": "amigurumi_shaping"}
    to, why = pipeline._preferred_construction(found, form="scarf", current="flat_rows",
                                               own_words="Linden Scarf")
    assert to is None and "cannot build" in why
    to, why = pipeline._preferred_construction(
        {"construction": "in_the_round"}, form="stocking", current="flat_rows",
        own_words="a tapestry stocking")
    assert to is None and "name" in why
    to, _why = pipeline._preferred_construction(
        {"construction": "in_the_round"}, form="stocking", current="flat_rows",
        own_words="Holly Stocking")
    assert to == "in_the_round"


def test_conflicting_preferences_cancel_and_a_hold_refuses_the_draft_by_name():
    db = D._db()
    concept = _winner(db)
    a = _lesson(db, concept)
    b = _lesson(db, concept, words=f"{concept['form'].replace('_', ' ')} "
                                   f"{str(concept.get('motif') or '').split()[0]} gifts")
    alts = [c for c in sorted(FORM_CONSTRUCTIONS[concept["form"]])
            if ENGINE_ROUTE.get(c) and c != concept["construction"]][:2]
    for lid, value in zip((a, b), alts):
        consume.approve_for_design(db, lid, parameter="construction", value=value,
                                   approved_by="owner", why="recorded tests favour this one")
    found = consume.design_directives(db, f"{concept['title']} {concept['premise']}")
    assert found["construction"] is None and set(found["conflicts"]) == {a, b}, found
    hold = bus.publish(db, origin_cell="quality", subject="defect",
                       statement=(f"the {concept['form'].replace('_', ' ')} "
                                  f"{str(concept.get('motif') or '').split()[0]} prototype "
                                  f"failed its physical test in this construction"),
                       evidence_ref="fixture:hold")
    consume.approve_for_design(db, hold, parameter="hold_construction",
                               value=concept["construction"], approved_by="owner",
                               why="the physical test failed for this construction")
    done = D._drain(db, "cir.draft")
    out = done[0]["outputs"]
    assert out.get("drafted") is False and out.get("gate") == "learning.hold", out
    assert not D._jobs(db, "cir.compile")
    assert any(d.get("gate") == "learning.hold" for _i, _a, d in D._rows(db, "cir.draft_refused"))



def _radar_draft(db, slug):
    """A POOL seed drafted by the radar fallback through the Worker (the radar.score ->
    cir.draft path), with an established earlier version as in test_opus2_a1_children."""
    import dataclasses

    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.queue.durable import JobQueue

    seed = pipeline._seed_for(slug)
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", inputs, priority=0)
    return seed, _draft(db)


def test_an_approved_yarn_weight_lesson_changes_a_radar_fallback_draft():
    """On the radar fallback, an approved yarn-weight lesson changes the yarn (and the gauge
    derived from it) against the baseline, and is recorded once."""
    slug = "nordic-forest-basket"
    _seed, (_o, base) = _radar_draft(D._db(), slug)
    db = D._db()
    lid = bus.publish(db, origin_cell="quality", subject="defect",
                      statement=("the nordic forest basket walls slump in worsted; a "
                                 "heavier yarn holds the storage basket shape"),
                      evidence_ref="fixture:yarn")
    want = "bulky" if base.gauge.yarn_weight != "bulky" else "aran"
    consume.approve_for_design(db, lid, parameter="yarn_weight", value=want,
                               approved_by="owner",
                               why="the physical test showed slumping walls in the lighter yarn")
    _seed, (out, cir) = _radar_draft(db, slug)
    assert cir.gauge.yarn_weight == want != base.gauge.yarn_weight, (cir.gauge, base.gauge)
    assert cir.gauge.stitches_per_10cm != base.gauge.stitches_per_10cm
    assert out["learning"]["applied"] == [lid], out
    rows = [d for _i, a, d in D._rows(db, consume.DESIGN_APPLIED) if a == f"lessons:{lid}"]
    assert len(rows) == 1 and rows[0]["change"]["parameter"] == "yarn_weight", rows

def test_the_declared_constructions_are_the_drafting_vocabulary():
    from brambleloop.creative import concept as C
    from brambleloop.creative import fallback_constructions as FC

    assert consume.PREFERABLE_CONSTRUCTIONS == frozenset(C.CONSTRUCTIONS)
    families = {getattr(FC, n) for n in dir(FC) if n.isupper() and isinstance(
        getattr(FC, n), str) and getattr(FC, n) in consume.DESIGN_CONSTRUCTIONS}
    assert families and families <= consume.DESIGN_CONSTRUCTIONS
    assert frozenset(C.CONSTRUCTIONS) <= consume.DESIGN_CONSTRUCTIONS


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:900])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
