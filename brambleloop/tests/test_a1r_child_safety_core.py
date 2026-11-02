"""A1-R (P0-SAFETY-CHILDREN, architectural correction; owner directive 2026-11-02).

Children's safety is a construction-classification gate with an audited-decision requirement:
* any closed stuffed form (a stuffed seam, or a stuffing material in a CIR closed by a seam) is
  held by the renderer until an explicit decision exists, whatever its title says and whatever
  its optional placement fields say;
* the implicit "the candidate declares no sub-category" exemption is not a decision for one;
  the catalogue's two stuffed pieces carry written, reasoned NOT_MERCHANDISED entries;
* title words are a second layer, read through one fold (NFKC, invisible characters,
  look-alike letters) by the drafting routes, the renderer and the survey alike;
* small parts: within the stated tolerance of the 31.7 mm cylinder is UNKNOWN, never a pass,
  and blocks a children's assignment until physical evidence is recorded.

Guard tests use hand-built CIRs (no toy route is imported); the real-path tests run
handle_cir_draft and assets.build through the real Worker on a durable SQLite file.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_a1r_child_safety_core.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.model import Material  # noqa: E402
from brambleloop.gates import small_parts as SP  # noqa: E402
from brambleloop.products import inventory  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import pdf  # noqa: E402


def _refused(cir) -> str | None:
    try:
        pdf._refuse_an_undecided_childrens_title(cir, L.childrens_assignment(cir.slug))
    except ValueError as exc:
        return str(exc)
    return None


def _stuffed_ball():
    """The ring pillow's CIR -- a stuffed disc-and-body form -- under a neutral identity."""
    return dataclasses.replace(inventory._engineered("heart-row-ring-pillow"),
                               slug="juniper-friend-80c61c2e", title="Juniper Friend")


def test_every_closed_stuffed_form_is_held_whatever_its_title_or_placement():
    ball = _stuffed_ball()
    # 1. a stuffed seam
    assert L.closed_stuffed_form(ball) and "closed stuffed form" in (_refused(ball) or "")
    # 2. the same with every placement field cleared (ears/bases placed by at_round or not at all)
    bare = dataclasses.replace(ball, assembly=[dataclasses.replace(
        s, stitches_from_centre=None, at_round=None) for s in ball.assembly])
    assert L.closed_stuffed_form(bare) and _refused(bare), "placement fields decided it"
    # 3. stuffing material and a closed seam, without the stuffed-seam flag
    quilted = dataclasses.replace(
        inventory._engineered("spring-garden-kneeler"), slug="woodland-keepsake-1",
        title="Woodland Keepsake")
    quilted = dataclasses.replace(quilted, assembly=[dataclasses.replace(
        s, stuff_before_closing=False) for s in quilted.assembly])
    assert L.closed_stuffed_form(quilted) and _refused(quilted)
    # 4. an empty title and a design slug
    blank = dataclasses.replace(ball, slug="design-96cff5a5", title="")
    assert _refused(blank)
    # not stuffed: a flat panel with no stuffing and no stuffed seam is not a closed form
    flat = dataclasses.replace(quilted, materials=[Material(name="worsted acrylic")])
    assert not L.closed_stuffed_form(flat) and _refused(flat) is None


def test_the_implicit_candidate_exemption_is_not_a_decision_for_a_stuffed_form():
    implicit = next((slug for slug, why in L._decided_not_for_children().items()
                     if slug not in L.NOT_MERCHANDISED_TO_A_CHILD), None)
    assert implicit, "a candidate variant with the implicit exemption"
    toy_under_it = dataclasses.replace(_stuffed_ball(), slug=implicit, title="Teddy Bear")
    assert L.childrens_decision(implicit)[0] == L.NOT_FOR_CHILDREN
    assert L.childrens_decision_for(toy_under_it)[0] == L.UNDECIDED
    assert _refused(toy_under_it)
    # the catalogue's stuffed pieces carry written decisions and render as before
    for slug in ("heart-row-ring-pillow", "spring-garden-kneeler"):
        cir = inventory._engineered(slug)
        assert L.closed_stuffed_form(cir) and slug in L.NOT_MERCHANDISED_TO_A_CHILD
        assert len(L.NOT_MERCHANDISED_TO_A_CHILD[slug].split()) >= 8
        assert _refused(cir) is None, slug
    assert L.childrens_titles_without_an_assignment() == []
    # A1-7: the survey reads the construction too -- without its written decision, the
    # kneeler (no child word in its title) is reported, as the renderer would hold it
    saved = L.NOT_MERCHANDISED_TO_A_CHILD.pop("spring-garden-kneeler")
    try:
        assert [r["slug"] for r in L.childrens_titles_without_an_assignment()] == [
            "spring-garden-kneeler"]
    finally:
        L.NOT_MERCHANDISED_TO_A_CHILD["spring-garden-kneeler"] = saved


def test_title_words_are_read_through_one_fold_everywhere():
    plain = dataclasses.replace(inventory._engineered("spring-garden-kneeler"),
                                slug="probe-basket", title="Storage Basket", assembly=[],
                                materials=[Material(name="worsted acrylic")])
    assert _refused(plain) is None
    spellings = ("Bаby Basket", "Ba​by Basket", "Ｂaby Basket",
                 "\U0001d401aby Basket", "Ba­by Basket", "ʙaby Basket",
                 "Babу Basket", "BABY Basket")
    assert len(spellings) == 8
    for title in spellings:
        cir = dataclasses.replace(plain, title=title)
        assert L.child_words_in(title) == ("baby",), title
        assert _refused(cir) and "baby" in _refused(cir), title


def test_small_parts_near_the_cylinder_is_unknown_and_blocks_an_assignment():
    assert SP.verdict(31.0, 50.0) == SP.FITS
    assert SP.verdict(33.0, 50.0) == SP.UNKNOWN          # 1.3 mm over the width: unknown
    assert SP.verdict(31.0, 60.0) == SP.UNKNOWN          # 2.9 mm over the depth: unknown
    assert SP.verdict(36.0, 50.0) == SP.CLEAR            # 4.3 mm over the width
    assert SP.verdict(31.0, 61.5) == SP.CLEAR
    assert SP.SMALL_PARTS_TOLERANCE_MM > 0 and SP.CYLINDER_MM == 31.7
    ball = _stuffed_ball()
    pieces = SP.separable_pieces(ball)
    assert pieces, "the sewn-on base disc is a separable piece"
    tiny = dataclasses.replace(ball, gauge=dataclasses.replace(
        ball.gauge, stitches_per_10cm=ball.gauge.stitches_per_10cm * 6,
        rows_per_10cm=ball.gauge.rows_per_10cm * 6))
    assert SP.blocking(tiny), SP.separable_pieces(tiny)
    try:
        pdf._refuse_an_undecided_childrens_title(tiny, ("toy", "under_3"))
    except ValueError as exc:
        assert "small-parts" in str(exc)
    else:
        raise AssertionError("an assigned stuffed form with a small part rendered")
    SP.SMALL_PARTS_EVIDENCE[tiny.slug] = "fixture: measured sample record"
    try:
        pdf._refuse_an_undecided_childrens_title(tiny, ("toy", "under_3"))
    finally:
        SP.SMALL_PARTS_EVIDENCE.pop(tiny.slug)


# ---- the real path: the Worker on a durable SQLite file ----------------------------------

def _store():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    path = f"{tempfile.mkdtemp(prefix='a1r_')}/a1r.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db, path


def _assets_build(cir) -> tuple[str, str]:
    """Certify-free: a release row holding this CIR, then assets.build through the Worker."""
    from sqlalchemy import select

    from brambleloop.core.db import Database
    from brambleloop.core.models import Job, PatternVersion, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db, path = _store()
    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True))
    JobQueue(db).enqueue("publishing", "assets.build",
                         {"slug": cir.slug, "version": cir.version}, priority=0)
    fresh = Database(f"sqlite:///{path}")
    Worker(fresh, "a1r", job_types=["assets.build"]).run_once()
    with fresh.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "assets.build"))
        return str(job.status), str(job.last_error or "")


def test_assets_build_through_the_worker_holds_stuffed_forms_and_renders_the_catalogue():
    cases = {"neutral stuffed ball": _stuffed_ball(),
             "placement cleared": dataclasses.replace(_stuffed_ball(), assembly=[
                 dataclasses.replace(s, stitches_from_centre=None, at_round=None)
                 for s in _stuffed_ball().assembly]),
             "cyrillic": dataclasses.replace(_stuffed_ball(), title="Bаby Friend"),
             "fullwidth": dataclasses.replace(_stuffed_ball(), title="Ｂear Friend"),
             "math bold": dataclasses.replace(_stuffed_ball(), title="\U0001d401ear"),
             "zero width": dataclasses.replace(_stuffed_ball(), title="Ba​by Friend")}
    assert len(cases) == 6
    for name, cir in cases.items():
        status, error = _assets_build(cir)
        assert "children" in error or "closed stuffed form" in error, (name, status, error)
    status, error = _assets_build(inventory._engineered("spring-garden-kneeler"))
    assert "children" not in error and "stuffed" not in error, (status, error)


def test_handle_cir_draft_drafts_a_cushion_that_is_then_held_until_decided():
    """A radar fallback cushion (panel_pair: stuffed over the pad) drafted through the real
    Worker is a closed stuffed form; its document is held until someone decides."""
    import dataclasses as dc

    from sqlalchemy import select

    from brambleloop.cir.model import CIR
    from brambleloop.core.db import Database
    from brambleloop.core.models import Job, PatternVersion, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline
    from brambleloop.runtime.worker import Worker

    db, path = _store()
    seed = pipeline._seed_for("wedding-ring-cushion") or pipeline._seed_for("nordic-forest-basket")
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    inputs = {k: v for k, v in dc.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    inputs.update(category="pillow", title="Juniper Cushion")
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", inputs, priority=0)
    fresh = Database(f"sqlite:///{path}")
    assert Worker(fresh, "a1r-draft", job_types=["cir.draft"]).run_once()
    with fresh.session() as s:
        draft = s.scalar(select(Job).where(Job.job_type == "cir.draft"))
        compile_job = s.scalar(select(Job).where(Job.job_type == "cir.compile"))
        assert draft.outputs.get("drafted") is True, draft.outputs
        cir = CIR.from_dict(compile_job.inputs["cir"])
    assert L.closed_stuffed_form(cir)
    assert _refused(cir) and "closed stuffed form" in _refused(cir)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:700])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
