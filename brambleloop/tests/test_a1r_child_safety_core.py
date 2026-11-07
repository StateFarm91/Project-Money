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
    # (A1R-1: the seam notes are free text the classifier now reads, and the kneeler's say
    # to stuff it -- so the control clears them too: no stuffing anywhere.)
    flat = dataclasses.replace(quilted, materials=[Material(name="worsted acrylic",
                                                            yarn_weight="worsted")],
                               designer_notes=None,
                               assembly=[dataclasses.replace(x, note=None)
                                         for x in quilted.assembly])
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


def _assets_build_full(cir, db=None, path=None) -> dict:
    """A1R-7: assets.build through the Worker, reporting status, outputs, attempts, the hold
    rows and the open owner decision items -- not a substring of an error."""
    from sqlalchemy import select

    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Job, OwnerAction, PatternVersion, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    if db is None:
        db, path = _store()
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == cir.slug))
        if p is None:
            p = Product(slug=cir.slug, title=cir.title)
            s.add(p)
            s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True))
    job = JobQueue(db).enqueue("publishing", "assets.build",
                               {"slug": cir.slug, "version": cir.version}, priority=0)
    fresh = Database(f"sqlite:///{path}")
    w = Worker(fresh, "a1r", job_types=["assets.build"])
    while w.run_once():
        pass
    with fresh.session() as s:
        row = s.get(Job, job.id)
        holds = [a.detail for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "childrens.decision_required")) if (a.detail or {}).get(
                "slug") == cir.slug]
        actions = [a.requirement_key for a in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False))  # noqa: E712
            if a.requirement_key == f"childrens-decision:{cir.slug}"]
        return {"status": row.status, "outputs": dict(row.outputs or {}),
                "attempts": row.attempts, "error": str(row.last_error or ""),
                "holds": holds, "actions": actions, "db": fresh, "path": path}


def _held(out) -> bool:
    from brambleloop.core.models import JobStatus

    return (out["status"] == JobStatus.DONE and out["outputs"].get("held") is True
            and out["outputs"].get("gate") == "childrens_decision"
            and len(out["holds"]) >= 1 and len(out["actions"]) == 1)


def _rendered(out) -> bool:
    from brambleloop.core.models import JobStatus

    return out["status"] == JobStatus.DONE and not out["outputs"].get("held") \
        and not out["holds"] and not out["actions"]


def _one_piece_ball(title="Juniper Friend", filling="polyester fibrefill"):
    """A1R-1 (i): ONE magic-ring piece that widens and decreases back to close, stuffed, no
    seams -- the literal stuffed ball (the ring pillow is two pieces and a stuffed seam)."""
    from brambleloop.cir.model import CIR, Component, Material, Op, Row

    pillow = inventory._engineered("heart-row-ring-pillow")
    counts = [6, 12, 18, 24, 24, 24, 24, 18, 12, 6]
    rows = []
    for i, n in enumerate(counts):
        prev = counts[i - 1] if i else 0
        if i == 0:
            ops = [Op("sc", 6)]
        elif n > prev:
            ops = [Op("inc", n - prev)] + ([Op("sc", 2 * prev - n)] if 2 * prev > n else [])
        elif n < prev:
            ops = [Op("dec", prev - n)] + ([Op("sc", 2 * n - prev)] if 2 * n > prev else [])
        else:
            ops = [Op("sc", n)]
        rows.append(Row(index=i + 1, ops=ops, declared_count=n, turning_chain=0))
    yarn = [m for m in pillow.materials if m.yarn_weight][:1]
    return CIR(slug="juniper-friend-b411", title=title, version="1.0.0",
               construction="joined_rounds", risk_class="C", colors=dict(pillow.colors),
               gauge=pillow.gauge, materials=yarn + [Material(name=filling)],
               components=[Component(name="body", construction="joined_rounds", rows=rows,
                                     foundation=6, foundation_kind="magic_ring")])


def _unflagged_pillow(filling):
    """A1R-1 (ii): seams but no stuff_before_closing flag; the filling named another way."""
    pillow = inventory._engineered("heart-row-ring-pillow")
    yarn = [m for m in pillow.materials if m.yarn_weight]
    return dataclasses.replace(
        pillow, slug="juniper-cushion-b411", title="Juniper Friend",
        assembly=[dataclasses.replace(x, stuff_before_closing=False, note="Whipstitch closed.")
                  for x in pillow.assembly],
        materials=yarn + [Material(name=filling)])


def test_a1r1_a_one_piece_ball_and_every_filling_spelling_is_a_closed_stuffed_form():
    """A1R-1 HIGH: classify from the construction -- a piece that closes on itself, or a seam
    -- with a stuffing VOCABULARY, any non-yarn material and the notes. Through the Worker
    the one-piece ball and an unflagged 'Fiber-Fill' cushion are named holds."""
    ball = _one_piece_ball()
    assert L.closed_stuffed_form(ball), L.stuffed_form_reasons(ball)
    assert any("closes on itself" in r for r in L.stuffed_form_reasons(ball))
    for filling in ("Fiber-Fill", "fibre-fill", "polyester filling", "toy fill", "fiberfil",
                    "kapok", "poly pellets", "wool roving", "foam insert", "Fіbrefill",
                    "an unnamed notion"):
        assert L.closed_stuffed_form(_unflagged_pillow(filling)), filling
    # a stuffing material that DOES carry a yarn weight (roving, a bulky "fill" yarn): the
    # vocabulary, not the missing weight, is what reads it
    for filling in ("wool roving", "chunky fibre-fill"):
        pill = _unflagged_pillow("x")
        weighted = dataclasses.replace(pill, materials=[m for m in pill.materials
                                                        if m.yarn_weight]
                                       + [Material(name=filling, yarn_weight="bulky")])
        assert L.closed_stuffed_form(weighted), filling
    notes_only = dataclasses.replace(
        _unflagged_pillow("x"), materials=[m for m in _unflagged_pillow("x").materials
                                           if m.yarn_weight],
        designer_notes="Stuff firmly with toy filling before closing the last round.")
    assert L.closed_stuffed_form(notes_only)
    # not stuffed: flat pieces, and an open vessel worked in rounds
    for slug in ("market-basket-small", "autumn-oak-mosaic-throw", "harvest-table-runner",
                 "cottage-wall-hanging", "snowfall-advent-garland"):
        assert not L.closed_stuffed_form(inventory._engineered(slug)), slug
    from brambleloop.cir.compiler import compile_cir

    assert compile_cir(ball).ok
    assert _held(_assets_build_full(ball))
    assert _held(_assets_build_full(_unflagged_pillow("Fiber-Fill")))


def test_a1r2_greek_cherokee_and_cyrillic_capitals_fold_before_case_through_the_worker():
    """A1R-2 MED: look-alike capitals are mapped before case folding. On a NON-stuffed
    basket the word layer is the only layer: each title is a named hold."""
    from brambleloop.products.text_fold import fold

    for t, want in (("Βaby Basket", "baby basket"), ("ΒΑΒΥ", "baby"),
                    ("Νursery", "nursery"), ("Ᏼaby", "baby"), ("Үoung", "young"),
                    ("Ьaby", "baby"), ("Μommy", "mommy"), ("Ηat", "hat"), ("Κid", "kid")):
        assert fold(t) == want, (t, fold(t))
    basket = inventory._engineered("market-basket-small")
    assert not L.closed_stuffed_form(basket)
    for title in ("Βaby Basket", "Ᏼaby Basket", "ΝURSERY Basket"):
        out = _assets_build_full(dataclasses.replace(basket, slug="nb-4c2a", title=title))
        assert _held(out), (title, out["status"], out["outputs"], out["error"])
    assert _rendered(_assets_build_full(dataclasses.replace(basket, slug="nb-4c2b",
                                                            title="Market Basket")))


def test_a1r3_one_fold_reads_drafting_rendering_survey_and_motifs():
    """A1R-3 MED: the drafting routes' fold_title is the shared fold (plus dash folding)."""
    from brambleloop.creative import fallback_constructions as FC
    from brambleloop.products.text_fold import fold

    for t in ("Βaby Basket", "Bаby\u200b Basket", "Ｂaby Basket", "Café Basket"):
        assert FC.fold_title(t) == fold(t), (t, FC.fold_title(t), fold(t))
    assert FC.fold_title("Fair\u2011Isle Basket") == "fair-isle basket"


def test_a1r4_a_hold_is_named_permanent_owner_visible_and_blocks_no_other_product():
    """A1R-4 MED: the hold is a ChildrensDecisionRequired (permanent), the job is DONE on its
    first attempt with held output, an audited hold row and ONE owner decision item; a
    second run adds no second item; a plain product in the same store renders."""
    from brambleloop.publish.pdf import ChildrensDecisionRequired
    from brambleloop.core.resilience import PermanentError

    assert issubclass(ChildrensDecisionRequired, PermanentError)
    first = _assets_build_full(_one_piece_ball())
    assert _held(first) and first["attempts"] == 1, first
    again = _assets_build_full(dataclasses.replace(_one_piece_ball(), version="1.0.1"),
                               db=first["db"], path=first["path"])
    assert _held(again) and len(again["holds"]) == 2 and again["actions"] == first["actions"]
    other = _assets_build_full(inventory._engineered("market-basket-small"),
                               db=first["db"], path=first["path"])
    assert other["status"].value == "done" and not other["outputs"].get("held")


def test_a1r5_small_parts_for_every_assigned_product_and_unknown_blocks():
    """A1R-5: a NON-stuffed assigned product with a sewn-on piece that fits is held; a piece
    in the UNKNOWN band is held (mutant M10); a missing gauge is UNKNOWN, never clear."""
    from brambleloop.gates import small_parts as SP

    basket = inventory._engineered("market-basket-small")
    disc = _one_piece_ball().components[0]
    small = dataclasses.replace(disc, name="tab", rows=disc.rows[:2])      # 12 sts disc
    seam = dataclasses.replace(inventory._engineered("heart-row-ring-pillow").assembly[0],
                               piece_a="tab", piece_b="basket", stuff_before_closing=False,
                               note=None, at_round=None, stitches_from_centre=None)
    with_tab = dataclasses.replace(basket, components=list(basket.components) + [small],
                                   assembly=[seam])
    assert not L.closed_stuffed_form(dataclasses.replace(with_tab, assembly=[]))
    blocks = SP.blocking(with_tab)
    assert blocks and "tab" in blocks[0], blocks
    try:
        pdf._refuse_an_undecided_childrens_title(with_tab, ("toys", "fixture assignment"))
    except pdf.ChildrensDecisionRequired as exc:
        assert exc.reason == "small_parts"
    else:
        raise AssertionError("an assigned non-stuffed product with a fitting piece rendered")
    # UNKNOWN band (M10): a piece whose narrow side is within tolerance above the cylinder
    width_sts = None
    for n in range(1, 400):
        d = n * (100.0 / basket.gauge.stitches_per_10cm) / 3.141592653589793
        if SP.verdict(d, d) == SP.UNKNOWN:
            width_sts = n
            break
    assert width_sts, "no stitch count lands in the UNKNOWN band at this gauge"
    band = dataclasses.replace(disc, name="tab", rows=[
        dataclasses.replace(r, declared_count=min(r.declared_count, width_sts))
        for r in disc.rows[:2]] + [dataclasses.replace(disc.rows[1], index=3,
                                                       declared_count=width_sts)])
    unknown = dataclasses.replace(with_tab, components=list(basket.components) + [band])
    assert any(SP.UNKNOWN in b for b in SP.blocking(unknown)), SP.blocking(unknown)
    # no gauge: every sewn-on piece is UNKNOWN
    nogauge = dataclasses.replace(with_tab, gauge=None)
    assert SP.blocking(nogauge) and SP.UNKNOWN in SP.blocking(nogauge)[0]


def test_a1r6_decisions_carry_who_and_when_and_the_listing_reads_the_held_decision():
    from brambleloop.publish import listing_package as LP

    assert set(L.NOT_MERCHANDISED_DECISIONS) == set(L.NOT_MERCHANDISED_TO_A_CHILD)
    for rec in L.NOT_MERCHANDISED_DECISIONS.values():
        assert rec["decided_by"] and rec["decided_on"] and rec["decision_log"] \
            and rec["reason"]
    log = (ROOT / "DECISION_LOG.md").read_text()
    assert "D-A1R-STUFFED-EXEMPTIONS" in log
    ball = _one_piece_ball()
    ident = LP._identity(ball.slug, ball.to_dict())
    assert ident["childrens_decision"][0] == L.UNDECIDED, ident
    # a slug whose RAW decision is the implicit candidate exemption, drafted as a stuffed
    # form: the listing must report what the renderer holds on (UNDECIDED), not the raw one
    slug = "market-basket-small"
    assert L.childrens_decision(slug)[0] == L.NOT_FOR_CHILDREN
    stuffed = dataclasses.replace(ball, slug=slug)
    ident = LP._identity(slug, stuffed.to_dict())
    assert ident["childrens_decision"][0] == L.UNDECIDED, ident


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
        out = _assets_build_full(cir)
        assert _held(out), (name, out["status"], out["outputs"], out["error"])
    # A1R-7: the controls RENDER (DONE, no hold), not merely "fail for another reason"
    assert _rendered(_assets_build_full(inventory._engineered("spring-garden-kneeler")))
    assert _rendered(_assets_build_full(inventory._engineered("market-basket-small")))


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



# ---- A1N (review F3 HIGH, F5 MED): infant product nouns, age sizes, and the two UNKNOWNs ----

# Each title is read by exactly one new entry (word, phrase or size), so removing any one
# entry from launch0 fails here (mutant "infant word list removed").
INFANT_TITLES = {
    "Pacifier Clip": "pacifier", "Pacifiers Clip": "pacifiers", "Paci Clip": "paci",
    "Pacis Holder": "pacis", "Binky Leash": "binky", "Binkies Leash": "binkies",
    "Soother Holder": "soother", "Soothers Holder": "soothers", "Teether": "teether",
    "Teethers Set": "teethers", "Teething Ring": "teething", "Teething-Rings": "teething",
    "Rattle": "rattle", "Rattles Set": "rattles", "Bib": "bib", "Bibs Set": "bibs",
    "Bassinet Cover": "bassinet", "Bassinets Cover": "bassinets",
    "Bassinette Cover": "bassinette", "Bassinettes Cover": "bassinettes",
    "Stroller Blanket": "stroller", "Strollers Blanket": "strollers", "Pram Blanket": "pram",
    "Prams Blanket": "prams", "Pushchair Blanket": "pushchair",
    "Pushchairs Blanket": "pushchairs", "Babyshower Gift": "babyshower",
    "Babyshowers Gift": "babyshowers", "Lovie": "lovie", "Lovies Set": "lovies",
    "Loveys Set": "loveys", "Littleone Blanket": "littleone",
    "Littleones Blanket": "littleones", "Toy": "toy", "Toys Set": "toys",
    "Toy Storage Basket": "toy", "Doll": "doll", "Dolls Set": "dolls", "Plushie": "plushie",
    "Plushies Set": "plushies", "Plushy Pal": "plushy", "Infants Blanket": "infants",
    "Newborns Blanket": "newborns", "Toddlers Blanket": "toddlers", "Preemie Hat": "preemie",
    "Preemies Hat": "preemies", "Little One Blanket": "little one",
    "Little-Ones Blanket": "little ones", "Lil One Blanket": "lil one",
    "Lil Ones Blanket": "lil ones", "Hat 12M": "12m", "0-3M Cardigan": "0-3m",
    "Sweater 6 mo": "6mo", "Cardigan 18mos": "18mos", "Cardigan 24 mth": "24mth",
    "Cardigan 9mths": "9mths", "Hat 1 month": "1month", "Hat 3-6 months": "3-6months",
    "Hat 0–3 M": "0-3m", "Dress Size 2T": "2t", "Ｂlanket １２M": "12m",
}


def _plain_basket(slug="a1n-probe-basket", title="Market Basket"):
    """review p7: a NON-stuffed basket (no seam, yarn only) under a new slug -- no candidate
    decides it, so the title words are the only layer that can hold it."""
    basket = inventory._engineered("market-basket-small")
    cir = dataclasses.replace(basket, slug=slug, title=title)
    assert not L.closed_stuffed_form(cir), L.stuffed_form_reasons(cir)
    assert L.childrens_decision_for(cir)[0] == L.UNDECIDED
    return cir


def test_a1n_infant_product_nouns_and_age_sizes_are_child_audience_words():
    assert len(INFANT_TITLES) >= 60
    assert _refused(_plain_basket()) is None, "control: a plain basket title renders"
    for title, word in INFANT_TITLES.items():
        assert word in L.child_words_in(title), (title, L.child_words_in(title))
        assert word in L.child_words_in("Market Basket", title.lower().replace(" ", "-")), \
            ("slug", title)
        why = _refused(_plain_basket(title=title))
        assert why and "reads as a children's product" in why and word in why, (title, why)
    # "Baby Shower Gift" reads through the existing "baby"
    assert L.child_words_in("Baby Shower Gift") == ("baby",)
    # not child sizes: millimetres, centimetres and metres-with-unit words stay plain
    for title in ("Market Basket 5mm", "Basket 12 mm Hook", "Storage Basket 30 cm",
                  "Mosaic Throw", "Hexagon Coaster Set", "Tomato Basket", "Stormy Basket",
                  "Dollar Store Basket", "Bibliophile Tote", "Toyota Seat Cover"):
        assert L.child_words_in(title) == (), (title, L.child_words_in(title))
    # the survey still has no unassigned children's title in the shipped catalogue
    assert L.childrens_titles_without_an_assignment() == []


def test_a1n_review_p7_infant_titles_are_held_through_the_worker_with_no_pdf():
    """review p7, through the real Worker: a non-stuffed basket under a new slug, retitled
    to each infant product name, is a named children's-decision hold with no document."""
    names = ("Pacifier Clip", "Teething Ring", "Teether", "Rattle", "Soother Holder",
             "Binky Leash", "Bib", "Bassinet Cover", "Stroller Blanket",
             "Little One Blanket", "Lovie", "Toy", "Doll", "Plushie", "Babyshower Gift",
             "Baby Shower Gift", "12M")
    db = path = None
    for i, title in enumerate(names):
        cir = _plain_basket(slug=f"a1n-p7-{i:02d}", title=title)
        out = _assets_build_full(cir, db=db, path=path)
        db, path = out["db"], out["path"]
        assert _held(out), (title, out["status"], out["outputs"], out["error"])
        assert not any("pdf" in str(k).lower() or str(v).lower().endswith(".pdf")
                       for k, v in out["outputs"].items()), (title, out["outputs"])
        assert any("children's product" in str(h) or "childrens" in str(h).lower()
                   for h in out["holds"]), (title, out["holds"])
    # control: the same basket, plainly titled, in the same store, renders
    assert _rendered(_assets_build_full(_plain_basket(slug="a1n-p7-control"),
                                        db=db, path=path))


class _Unreadable:
    """An assembly list that cannot be read (review p8)."""

    def __iter__(self):
        raise RuntimeError("unreadable assembly")

    def __bool__(self):
        return True


def test_a1n_n6_an_unreadable_construction_is_unknown_and_held():
    """review F5 / N6: stuffed_form_reasons on an unreadable construction is UNKNOWN, and the
    renderer holds it (undecided) even with a plain title."""
    cir = _plain_basket(slug="a1n-n6-unreadable")
    object.__setattr__(cir, "assembly", _Unreadable())
    reasons = L.stuffed_form_reasons(cir)
    assert reasons and "UNKNOWN" in reasons[0] and "unreadable" in reasons[0], reasons
    assert L.closed_stuffed_form(cir)
    try:
        pdf._refuse_an_undecided_childrens_title(cir, None)
    except pdf.ChildrensDecisionRequired as exc:
        assert exc.reason == "undecided", exc.reason
    else:
        raise AssertionError("an unreadable construction rendered")


def test_a1n_n10_an_exception_measuring_pieces_is_unknown_and_holds_an_assignment():
    """review F5 / N10: an exception from separable_pieces is UNKNOWN in small_parts.blocking
    and holds an assigned product (small_parts) -- never an empty, passing list."""
    cir = _plain_basket(slug="a1n-n10-unmeasurable")
    saved = SP.separable_pieces

    def boom(_cir):
        raise RuntimeError("unmeasurable")

    SP.separable_pieces = boom
    try:
        blocks = SP.blocking(cir)
        assert blocks and SP.UNKNOWN in blocks[0] and "unmeasurable" in blocks[0], blocks
        try:
            pdf._refuse_an_undecided_childrens_title(cir, ("toys", "fixture assignment"))
        except pdf.ChildrensDecisionRequired as exc:
            assert exc.reason == "small_parts", exc.reason
        else:
            raise AssertionError("an assigned product with unmeasurable pieces rendered")
    finally:
        SP.separable_pieces = saved
    assert SP.blocking(cir) == [], "control: the plain basket has no sewn-on piece"



# ---- B-N1 (HIGH), B-N3, B-N4: review 6713597156 on fc26887b ----

# Each title is read by the one new entry named (word, phrase or compound stem).
BN1_TITLES = {
    "Dummy Clip": "dummy", "Dummy Holder": "dummy", "Dummies Set": "dummies",
    "Diaper Cover": "diaper", "Diapers Set": "diapers", "Nappy Cover": "nappy",
    "Nappies Set": "nappies", "Bootie": "bootie", "Booties": "booties",
    "Swaddle": "swaddle", "Swaddles Set": "swaddles", "Sleepsack": "sleepsack",
    "Sleepsacks Set": "sleepsacks", "Sleep Sack": "sleep sack", "Sleep Sacks": "sleep sacks",
    "Onesie": "onesie", "Onesies Set": "onesies", "Romper": "romper",
    "Rompers Set": "rompers", "Burp Cloth": "burp", "Layette Set": "layette",
    "Layettes Set": "layettes", "Christening Gown": "christening", "Carseat Canopy": "carseat",
    "Carseats Canopy": "carseats", "Car Seat Canopy": "car seat",
    "Car Seats Canopy": "car seats", "Moses Basket": "moses", "Taggie Blanket": "taggie",
    "Taggies Set": "taggies", "Blankie": "blankie", "Blankies Set": "blankies",
    "Stuffie": "stuffie", "Stuffies Set": "stuffies", "Childrens Hat": "childrens",
    "Kid's Hat": "kid s", "Kid\u2019s Hat": "kid s", "Cocoon Photo Prop": "cocoon",
    "Cocoons Set": "cocoons", "Newborn-style Photo Props": "photo props",
    "Photo Prop Hat": "photo prop",
    # run-together compounds: CamelCase split, and a child stem at the start of a word
    "PacifierClip": "pacifier", "Teethingring": "teething", "Babyblanket": "baby",
    "Infantcap": "infant", "Newbornhat": "newborn", "Nurserybasket": "nursery",
    "Toddlerhat": "toddler", "Childrenshat": "children", "Teetherset": "teether",
    "Binkyleash": "binky", "Sootherclip": "soother", "Bassinetcover": "bassinet",
    "Strollerblanket": "stroller", "Pushchaircover": "pushchair", "Preemiehat": "preemie",
    "Plushiepal": "plushie", "Loveyblanket": "lovey", "Loviebear": "lovie",
    "Littleoneblanket": "littleone", "Diapercover": "diaper", "Nappycover": "nappy",
    "Nappiesset": "nappies", "Swaddleset": "swaddle", "Sleepsackset": "sleepsack",
    "Onesieset": "onesie", "Layetteset": "layette", "Christeninggown": "christening",
    "Carseatcover": "carseat", "Blankiebear": "blankie", "Stuffiepal": "stuffie",
    "Taggieblanket": "taggie", "Amigurumibear": "amigurumi", "Babiesset": "babies",
}


def test_bn1_the_review_titles_are_child_audience_words_and_held():
    for title, word in BN1_TITLES.items():
        assert word in L.child_words_in(title), (title, L.child_words_in(title))
        why = _refused(_plain_basket(slug="bn1-probe", title=title))
        assert why and "reads as a children's product" in why and word in why, (title, why)
    # every compound stem and every new entry is pinned by a title above
    pinned = set(BN1_TITLES.values())
    for stem in L.CHILD_COMPOUND_STEMS:
        assert stem in pinned or any(t.lower().startswith(stem) and t.lower() != stem
                                     for t in BN1_TITLES), stem
    # ambiguous short words are not compound stems: these stay plain
    for title in ("Toyota Seat Cover", "Bibliophile Tote", "Dollar Store Basket",
                  "Cotton Market Bag", "Cribbage Board Cover", "Kid Mohair Scarf",
                  "Market Basket", "Mosaic Throw"):
        assert L.child_words_in(title) == (), (title, L.child_words_in(title))


def test_bn3_toy_beside_a_pet_word_is_a_pet_product_and_any_other_toy_still_holds():
    for title in ("Dog Toy", "Cat Toys", "Toy Poodle Sweater", "Puppy Toy Set",
                  "Pet Toy Basket", "Kitten Toys"):
        assert L.child_words_in(title) == (), (title, L.child_words_in(title))
        assert _refused(_plain_basket(slug="bn3-pet", title=title)) is None, title
    for title, want in (("Toy Box", ("toy",)), ("Dog Toy and Toy Box", ("toy",)),
                        ("Baby Dog Toy", ("baby",)), ("Toy Storage Basket", ("toy",)),
                        ("Dog Toys Plushie", ("plushie",))):
        assert L.child_words_in(title) == want, (title, L.child_words_in(title))
        assert _refused(_plain_basket(slug="bn3-held", title=title)), title


def test_bn4_the_renderer_reads_the_slug_as_well_as_the_title():
    """B-N4 (mutant B15): a plain title under a child-word slug is held by the renderer."""
    why = _refused(_plain_basket(slug="pacifier-clip-bn4", title="Market Clip"))
    assert why and "reads as a children's product" in why and "pacifier" in why, why
    assert _refused(_plain_basket(slug="market-clip-bn4", title="Market Clip")) is None


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
