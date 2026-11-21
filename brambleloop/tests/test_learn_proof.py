"""LEARN-PROOF: benchmark teardown lessons are stored records that change later outputs.

Each test runs the SAME input twice: once with the benchmark lessons absent from the learning
store, and once after `benchmark_lessons.ingest`. The difference is the proof that the lesson
was learned. Fixtures only: no competitor content, no sales, no spend. The amigurumi CIR is the
template test double (`tests/fixture_amigurumi.py`), never a catalogue product.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox
import dataclasses
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.learning import benchmark_lessons as B  # noqa: E402
from brambleloop.learning import progress  # noqa: E402
from brambleloop.publish import premium_standard as S  # noqa: E402

RELEASED = date(2026, 10, 27)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/learn.sqlite")
    db.create_all()
    B.reset_snapshot()
    return db


# ---- ingestion -----------------------------------------------------------------------------

def test_both_teardowns_ingest_as_fourteen_structured_records():
    db = _db()
    assert B.active(db) == {}
    out = B.ingest(db)
    assert out["lessons"] == 14 and len(out["created"]) == 14, out
    stored = B.active(db)
    assert sorted(stored) == sorted(f"{s}-L{n}" for s in ("HC", "MM") for n in range(1, 8))
    for key, rec in stored.items():
        lesson = B.BY_KEY[key]
        assert rec["department"] == lesson.department, key
        assert rec["lesson_class"] == lesson.lesson_class and rec["lesson_class"], key
        assert rec["effect"] == lesson.effect, key
        assert rec["source"] == B.SOURCES[lesson.source], key
        assert rec["source_sha256"] == B.SOURCE_SHA256[lesson.source], key
    assert stored["MM-L7"]["lesson_class"] == "missing_gauge->tension_complaints"
    assert stored["MM-L7"]["department"] == "quality"
    # Idempotent: the same teardowns are the same rows.
    again = B.ingest(db)
    assert again["created"] == [] and again["updated"] == [] and again["work_done"] == 0
    wired = {e for x in B.LESSONS for e in x.effects}
    assert wired == set(B.EFFECTS), wired
    # LEARN-PROOF-2: every one of the 14 lessons switches on at least one hook.
    assert [x.key for x in B.LESSONS if not x.effects] == []
    assert stored["MM-L3"]["effects"] == [B.PDF_HOOK_RANGE, B.YARN_CHENILLE]


def test_every_department_is_a_real_cell_and_every_effect_has_a_department():
    from brambleloop.improve.cells import BY_KEY

    assert set(B.DEPARTMENTS) <= set(BY_KEY), set(B.DEPARTMENTS) - set(BY_KEY)
    for effect in B.EFFECTS:
        assert B.EFFECT_DEPARTMENTS[effect], effect


def test_the_pinned_digests_match_the_teardowns_in_this_checkout():
    """The production image has no research/; the pins are its evidence, held here."""
    assert B.source_digests() == B.SOURCE_SHA256


def test_a_teardown_that_lost_its_lesson_refuses_ingestion():
    tmp = Path(tempfile.mkdtemp())
    for rel in B.SOURCES.values():
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
    hc = tmp / B.SOURCES["HC"]
    hc.write_text(hc.read_text(encoding="utf-8").replace("**L4,", "**Lfour,"), encoding="utf-8")
    try:
        B.source_digests(tmp)
    except B.IngestRefused as exc:
        assert "L4" in str(exc)
    else:
        raise AssertionError("a teardown without L4 still ingested")
    # A deployment without research/ falls back to the pinned digests.
    assert B.source_digests(Path(tempfile.mkdtemp())) == B.SOURCE_SHA256


def test_no_competitor_wording_is_stored():
    """Paraphrase only: no shop name, character name or title from the teardowns."""
    import re

    banned = (r"madelinemae", r"\bcara\b", r"capybara", r"highland cow", r"\bcanva\b",
              r"google drive")
    for lesson in B.LESSONS:
        low = lesson.statement.lower()
        assert not any(re.search(b, low) for b in banned), (lesson.key, lesson.statement)


# ---- (a) concept ranking -------------------------------------------------------------------

def _seed(slug, title, rationale="", category="amigurumi"):
    from brambleloop.radar.opportunity import ConceptSeed

    return ConceptSeed(slug=slug, title=title, category=category, risk_class="B",
                       price_cad=5.0, maker_hours=(2.0, 5.0), design_hours=10.0,
                       whitespace=0.5, rationale=rationale)


SEEDS = (
    _seed("plain-bear-amigurumi", "Bear Amigurumi", "A classic sewn bear in six pieces."),
    _seed("bramble-the-hedgehog", "Bramble the Hedgehog",
          "Low-sew: limbs are crocheted into the body as you go."),
    _seed("pip-the-otter", "Pip the Otter", "A character otter, sewn limbs."),
    _seed("no-sew-coaster", "No-Sew Coaster", "Low-sew coaster.", category="coaster"),
)


def test_concept_ranking_boosts_low_sew_character_named_amigurumi_only_after_the_lesson():
    db = _db()
    base = {"plain-bear-amigurumi": 0.700, "bramble-the-hedgehog": 0.680,
            "pip-the-otter": 0.690, "no-sew-coaster": 0.695}

    def order(nudges):
        return sorted(base, key=lambda k: -(base[k] + nudges.get(k, 0.0)))

    before = B.concept_rank_adjustments(db, SEEDS)
    assert before == {}, before
    assert order(before)[0] == "plain-bear-amigurumi"
    B.ingest(db)
    after = B.concept_rank_adjustments(db, SEEDS)
    assert after == {"bramble-the-hedgehog": 0.04, "pip-the-otter": 0.02}, after
    assert order(after)[0] == "bramble-the-hedgehog", order(after)
    # A non-amigurumi concept is never moved, low-sew or not.
    assert "no-sew-coaster" not in after
    assert B.concept_traits(SEEDS[1]) == ["low_sew", "character_named"]


def test_radar_scan_applies_the_ranking_lesson_and_records_it():
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, Job, JobStatus
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    def scan(db):
        Registry(db).seed_defaults()
        job = JobQueue(db).enqueue("market_radar", "radar.scan", {"as_of": "2026-11-21"},
                                   priority=0, idempotency_key=f"t:scan:{id(db)}")
        assert Worker(db, "learn-proof").run_once()
        with db.session() as s:
            row = s.get(Job, job.id)
            assert row.status == JobStatus.DONE, (row.status, row.last_error)
            audit = s.scalar(select(AuditLog).where(AuditLog.action == "radar.scanned")
                             .order_by(AuditLog.id.desc()))
            return dict(audit.detail or {})

    before_db = _db()
    before = scan(before_db)
    assert before["benchmark_lesson_nudges"] == {}
    assert B.readback(before_db)["departments"]["market_radar"]["applied"] == B.UNKNOWN

    after_db = _db()
    B.ingest(after_db)
    after = scan(after_db)
    moved = after["benchmark_lesson_nudges"]
    assert "no-sew-reindeer" in moved and moved["no-sew-reindeer"] > 0, moved
    rb = B.readback(after_db)["departments"]["market_radar"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["MM-L1"], rb
    assert rb["applications"] == len(moved) and rb["hook_runs"] >= 1, rb


# ---- (b) the PDF standard ------------------------------------------------------------------

def _ami_text():
    """The template's amigurumi proof (layout-only child-safety stub, as test_pdf_template)."""
    import fixture_amigurumi as F

    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish import pdf as P
    from brambleloop.publish import pdf_template as T

    orig = P.childrens_facts

    def stub(cir, twin, audience):
        fx = orig(cir, twin, audience)
        return dataclasses.replace(fx, finished_size_cm=(11.0, 16.0),
                                   fibres=fx.fibres or ("cotton",),
                                   fibre_read_from=fx.fibre_read_from or "test stub")
    P.childrens_facts = stub
    try:
        cir = F.pebble_friend()
        doc = T.build_template_pdf(cir, released_on=RELEASED, gallery=T.test_double_gallery(),
                                   childrens=F.CHILDRENS)
    finally:
        P.childrens_facts = orig
    result = compile_cir(cir)
    return cir, result, build_twin(cir, result), P.extracted_text(doc.pdf_bytes)


def test_the_pdf_standard_requires_eye_options_with_age_guidance_once_learned():
    cir, result, twin, text = _ami_text()
    before_ctx = S.context(cir, twin, result, "US", childrens=True, lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", childrens=True,
                          lessons=frozenset({B.PDF_EYE_OPTIONS}))
    assert before_ctx.family == S.AMIGURUMI
    before, after = S.audit_text(text, before_ctx), S.audit_text(text, after_ctx)
    assert "eye_options_age" not in before.required
    assert "eye_options_age" in after.required and "eye_options_age" not in after.failures
    # The same document without its eye panel: the base standard does not notice, the
    # learned standard refuses it.
    stripped = text.replace("EYE OPTIONS", "").replace("Embroidered eyes", "")
    assert "eye_options_age" not in S.audit_text(stripped, before_ctx).failures
    assert "eye_options_age" in S.audit_text(stripped, after_ctx).failures
    no_age = text.replace("under 3", "")
    assert "eye_options_age" in S.audit_text(no_age, after_ctx).failures


def test_the_pdf_standard_reads_the_stored_lessons_by_default():
    cir, result, twin, text = _ami_text()
    db = _db()
    assert "eye_options_age" not in S.context(cir, twin, result, "US", childrens=True).lessons \
        and not S.context(cir, twin, result, "US", childrens=True).lessons
    B.ingest(db)
    ctx = S.context(cir, twin, result, "US", childrens=True)
    assert ctx.lessons == frozenset(B.PDF_EFFECTS), ctx.lessons
    a = S.audit_text(text, ctx)
    assert "eye_options_age" in a.required and a.failures.get("eye_options_age") is None
    assert B.flush(db) >= 1
    rb = B.readback(db)["departments"]
    assert rb["pattern_engineering"]["applied"] >= 1, rb["pattern_engineering"]
    assert "MM-L4" in rb["pattern_engineering"]["lessons_applied"]
    # HC-L5 (eye options) and MM-L7's second effect (tension guidance in the gauge section).
    assert rb["quality"]["lessons_applied"] == ["HC-L5", "MM-L7"], rb["quality"]
    B.reset_snapshot()


def test_the_pdf_standard_requires_a_hook_range_for_chunky_yarn_once_learned():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.products import texture
    from brambleloop.publish import pdf

    B.reset_snapshot()
    cir = texture.build_ribbed_scarf()
    assert S.chunky_yarn(cir) == "chunky"
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    doc = pdf.build_pattern_pdf(cir, terminology="US", released_on=RELEASED, twin=twin)
    text = pdf.extracted_text(doc.pdf_bytes)
    assert "Hook range" in text
    before_ctx = S.context(cir, twin, result, "US", lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", lessons=frozenset({B.PDF_HOOK_RANGE}))
    assert "hook_range_chunky" not in S.audit_text(text, before_ctx).required
    after = S.audit_text(text, after_ctx)
    assert "hook_range_chunky" in after.required and "hook_range_chunky" not in after.failures
    lo, hi = S.chunky_hook_range(cir.gauge.hook_mm)
    assert lo < hi, (lo, hi)
    stripped = text.replace("Hook range", "").replace("hook range", "")
    assert "hook_range_chunky" not in S.audit_text(stripped, before_ctx).failures
    assert "hook_range_chunky" in S.audit_text(stripped, after_ctx).failures
    # A worsted product is not asked for it.
    from brambleloop.products import launch0

    worsted = launch0.cir_for("hexagon_coasters")
    assert S.chunky_yarn(worsted) is None


def test_chenille_is_a_chunky_class_whatever_its_weight_label():
    from brambleloop.cir.model import Material
    from brambleloop.products import texture

    cir = texture.build_ribbed_scarf()
    chen = dataclasses.replace(cir, materials=[Material(name="velvet chenille",
                                                        yarn_weight="worsted",
                                                        color_id="pine")])
    assert S.chunky_yarn(chen) == "chenille"
    assert "Chenille" in S.chunky_hook_range_text(chen)


# ---- (c) SEO: no sew / low sew only when true ----------------------------------------------

def _facts(cir):
    from brambleloop.seo.facts import ProductFacts

    vocab = {w: "test" for w in ("no", "low", "sew", "amigurumi", "pebble", "friend",
                                 "crochet", "pattern", "pdf", "toy")}
    return ProductFacts(slug=cir.slug, candidate="fixture", cir_title=cir.title,
                        kind="toy", category="amigurumi", nouns=["toy"], qualifiers=[],
                        techniques=["amigurumi"], difficulty="intermediate", colors=[],
                        colour_families=[], materials=[m.name for m in cir.materials],
                        stitches=["sc"], width_cm=None, height_cm=None, makes=1,
                        vocabulary=vocab, cir=cir, twin=None)


def _mm_l6(findings):
    return [f for f in findings if "MM-L6" in f]


def test_seo_uses_no_sew_only_when_the_certified_construction_is_low_sew():
    import fixture_amigurumi as F

    from brambleloop.cir.model import Seam
    from brambleloop.seo import truth

    sewn = F.pebble_friend()
    assert B.construction_sewing(sewn)["sewn"] >= 2
    title = "Pebble Friend amigurumi pattern, no sew, low sew"
    tags = ["amigurumi pattern", "no sew toy"]
    on = {B.SEO_LOW_SEW: ("MM-L6",)}
    before = truth.validate_listing(title, tags, _facts(sewn), competitors=[], lessons={})
    after = truth.validate_listing(title, tags, _facts(sewn), competitors=[], lessons=on)
    assert _mm_l6(before["blocking"]) == []
    found = _mm_l6(after["blocking"])
    assert len(found) == 3 and not after["ok"], found       # two title segments, one tag
    # The same listing on a construction that really is no-sew passes the learned rule.
    joined = dataclasses.replace(sewn, assembly=[
        dataclasses.replace(s, method="slst") for s in sewn.assembly])
    assert isinstance(joined.assembly[0], Seam) and B.construction_sewing(joined)["no_sew"]
    ok = truth.validate_listing(title, tags, _facts(joined), competitors=[], lessons=on)
    assert _mm_l6(ok["blocking"]) == []
    assert B.low_sew_modifiers(joined) == ["no sew", "low sew"]
    assert B.low_sew_modifiers(sewn) == []
    # One sewn seam is low-sew but not no-sew.
    one = dataclasses.replace(joined, assembly=[sewn.assembly[0]] + joined.assembly[1:])
    assert B.low_sew_modifiers(one) == ["low sew"]
    mixed = truth.validate_listing("Pebble Friend amigurumi pattern, low sew", ["no sew toy"],
                                   _facts(one), competitors=[], lessons=on)
    assert [f for f in _mm_l6(mixed["blocking"])] and \
        all("no sew" in f for f in _mm_l6(mixed["blocking"])), mixed["blocking"]


def test_seo_records_the_lesson_it_applied():
    import fixture_amigurumi as F

    from brambleloop.seo import truth

    db = _db()
    B.ingest(db)
    truth.validate_listing("Pebble Friend amigurumi pattern, no sew", [], _facts(
        F.pebble_friend()), competitors=[])
    B.flush(db)
    rb = B.readback(db)["departments"]["seo_search"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["MM-L6"], rb
    B.reset_snapshot()


# ---- (d) QA records the missing-gauge lesson class -----------------------------------------

def test_qa_records_the_missing_gauge_lesson_class_from_defects():
    from brambleloop.core.models import Incident
    from brambleloop.improve import mine

    def defects(db):
        with db.session() as s:
            s.add(Incident(severity="P2", product_slug="fixture-pebble-friend-amigurumi",
                           signature="tester:tension",
                           summary="Tester: the stitches were too tight with the stated hook"))
            s.add(Incident(severity="P3", signature="tester:colour",
                           summary="Tester: colour B ran out one round early"))

    before_db = _db()
    defects(before_db)
    before = mine.mine(before_db)
    assert before["lesson_classes"]["active"] is False
    assert B.defect_classes(before_db) == {}

    after_db = _db()
    defects(after_db)
    B.ingest(after_db)
    after = mine.mine(after_db)
    cls = after["lesson_classes"]
    assert cls["active"] is True
    assert [c["class"] for c in cls["classified"]] == ["missing_gauge->tension_complaints"]
    assert B.defect_classes(after_db) == {"missing_gauge->tension_complaints": 1}
    rb = B.readback(after_db)["departments"]["quality"]
    assert "MM-L7" in rb["lessons_applied"], rb
    B.reset_snapshot()


def test_defect_classifier_reads_gauge_codes_and_tension_complaints():
    assert B.defect_class("gauge_every_fabric: no gauge statement") == B.MISSING_GAUGE_CLASS
    assert B.defect_class("my toy came out too big") == B.MISSING_GAUGE_CLASS
    assert B.defect_class("colour B ran out") is None


# ---- readback ------------------------------------------------------------------------------

def test_readback_reports_applied_per_department_and_never_shows_unknown_as_zero():
    db = _db()
    rb = B.readback(db)
    assert rb["readable"] and rb["ingested"] == 0
    assert set(rb["departments"]) == set(B.DEPARTMENTS)
    for d, rec in rb["departments"].items():
        assert rec["applied"] == B.UNKNOWN and rec["why"], (d, rec)
    B.ingest(db)
    rb = B.readback(db)
    assert rb["ingested"] == 14
    unwired = [d for d in B.DEPARTMENTS
               if not any(x.effects for x in B.LESSONS if x.department == d)]
    assert unwired == [], unwired       # LEARN-PROOF-2: every department has a hook
    # Wired, ingested, never run: UNKNOWN with the reason, in every department.
    for d, rec in rb["departments"].items():
        assert rec["applied"] == B.UNKNOWN and "has not run" in rec["why"], (d, rec)
        assert rec["wired"] == rec["ingested"] >= 1, (d, rec)
    # Wired but not yet run: UNKNOWN too.
    assert rb["departments"]["seo_search"]["applied"] == B.UNKNOWN
    # A hook that ran and changed nothing is an honest zero.
    B.record(db, B.SEO_LOW_SEW, applied=False, subject="listing:x")
    assert B.readback(db)["departments"]["seo_search"]["applied"] == 0
    # The production readback carries it.
    row = progress.readback(db)["benchmark_lessons"]
    assert row["departments"]["seo_search"]["applied"] == 0
    assert row["departments"]["pricing"]["applied"] == B.UNKNOWN


def test_an_unreadable_store_is_unknown_never_zero():
    class Broken:
        engine = object()

        def session(self):
            raise RuntimeError("no database")

    rb = B.readback(Broken())
    assert rb["readable"] is False
    assert all(r["applied"] == B.UNKNOWN for r in rb["departments"].values())

# ==== LEARN-PROOF-2: the eight lessons LEARN-PROOF stored unhooked, and two second effects ====

def test_concept_ranking_learns_chenille_and_the_cosy_farm_cluster():
    """MM-L1 gains its chunky-chenille trait; HC-L2 (product_creativity) ranks the cosy farm
    animal cluster. Same seeds before and after ingestion."""
    seeds = (
        _seed("plain-bear-amigurumi", "Bear Amigurumi", "A classic sewn bear in six pieces."),
        _seed("chunky-chenille-whale", "Chunky Chenille Whale", "Plush chenille, sewn fins."),
        _seed("clover-the-lamb", "Clover the Lamb", "A cosy farm lamb, low-sew limbs."),
        _seed("sheep-coaster", "Sheep Coaster", "Farm animal coaster.", category="coaster"),
    )
    db = _db()
    base = {"plain-bear-amigurumi": 0.70, "chunky-chenille-whale": 0.69,
            "clover-the-lamb": 0.66, "sheep-coaster": 0.705}

    def order(n):
        return sorted(base, key=lambda k: -(base[k] + n.get(k, 0.0)))

    before = B.concept_rank_adjustments(db, seeds)
    assert before == {} and order(before)[0] == "sheep-coaster"
    B.ingest(db)
    after = B.concept_rank_adjustments(db, seeds)
    # whale: chunky_chenille (+0.02); lamb: low_sew + character_named (+0.04, MM-L1 cap) and
    # cosy_farm_animal (+0.02, HC-L2) = +0.06; the coaster is not amigurumi.
    assert after == {"chunky-chenille-whale": 0.02, "clover-the-lamb": 0.06}, after
    assert order(after)[0] == "clover-the-lamb", order(after)
    assert B.concept_traits(seeds[1]) == ["chunky_chenille"]
    assert B.cluster_traits(seeds[2]) == ["cosy_farm_animal"]
    rb = B.readback(db)["departments"]
    assert rb["product_creativity"]["lessons_applied"] == ["HC-L2"], rb["product_creativity"]
    assert rb["product_creativity"]["applications"] == 1
    assert rb["market_radar"]["applications"] == 2, rb["market_radar"]


def test_price_research_reads_the_effective_price_and_keeps_the_strike_price_apart():
    """HC-L1: the same Etsy search payload, captured before and after ingestion."""
    from sqlalchemy import select

    from brambleloop.core.models import SerpSnapshot
    from brambleloop.intel import serp
    from brambleloop.intel.purchase_selection import price_band

    listing = {"listing_id": 1, "shop_id": 2, "title": "Fixture lamb amigurumi pattern",
               "price": {"amount": 1154, "divisor": 100, "currency_code": "CAD"},
               "sale_price": {"amount": 288, "divisor": 100, "currency_code": "CAD"},
               "taxonomy_id": 1, "is_digital": True}
    plain = {"listing_id": 3, "shop_id": 4, "title": "Fixture bear amigurumi pattern",
             "price": {"amount": 600, "divisor": 100, "currency_code": "CAD"},
             "taxonomy_id": 1, "is_digital": True}

    class Reader:
        def search(self, query, **kw):
            return {"results": [dict(listing), dict(plain)], "count": 2}

        def images(self, listing_id):
            return []

    def capture(db):
        serp.capture(db, Reader(), "amigurumi pattern", detail_top=0)
        with db.session() as s:
            return list(s.scalars(select(SerpSnapshot)))[-1].rank_list

    before_db = _db()
    before = capture(before_db)
    assert [r["price"] for r in before] == [11.54, 6.0]
    assert "strike_price" not in before[0]
    after_db = _db()
    B.ingest(after_db)
    after = capture(after_db)
    assert [r["price"] for r in after] == [2.88, 6.0], after
    assert after[0]["strike_price"] == 11.54 and "strike_price" not in after[1]
    assert price_band(before[0]["price"]) != price_band(after[0]["price"])
    rb = B.readback(after_db)["departments"]["pricing"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["HC-L1"], rb
    # A payload with no effective price is unchanged: absent is never "no discount".
    assert B.effective_price(plain, 6.0, {B.PRICE_EFFECTIVE: ("HC-L1",)})["applied"] is False
    B.reset_snapshot()


def _engine(cir):
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish import pdf

    result = compile_cir(cir)
    twin = build_twin(cir, result)
    doc = pdf.build_pattern_pdf(cir, terminology="US", released_on=RELEASED, twin=twin)
    return result, twin, doc.pdf_bytes, pdf.extracted_text(doc.pdf_bytes)


def _chenille_scarf():
    from brambleloop.products import texture

    cir = texture.build_ribbed_scarf()
    mats = [dataclasses.replace(m, name=f"{m.name} (chenille)") if m.yarn_weight else m
            for m in cir.materials]
    return dataclasses.replace(cir, materials=mats)


def test_the_yarn_model_makes_chenille_a_class_with_a_shedding_and_care_note():
    """MM-L3's second effect: chenille carries gauge, hook range, tension and care."""
    B.reset_snapshot()
    cir = _chenille_scarf()
    assert S.chunky_yarn(cir) == "chenille"
    yc = S.yarn_class(cir)
    assert yc["class"] == "chenille" and yc["care"] == S.CHENILLE_CARE_NOTE
    assert yc["hook_range_mm"][0] < yc["hook_range_mm"][1] == cir.gauge.hook_mm
    assert yc["gauge"]["hook_mm"] == cir.gauge.hook_mm
    result, twin, _b, text = _engine(cir)
    assert "Chenille sheds" in text and "Care: hand wash cold" in text
    before_ctx = S.context(cir, twin, result, "US", lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", lessons=frozenset({B.YARN_CHENILLE}))
    assert "chenille_care" not in S.audit_text(text, before_ctx).required
    after = S.audit_text(text, after_ctx)
    assert "chenille_care" in after.required and "chenille_care" not in after.failures
    stripped = text.replace("Chenille sheds", "").replace("Care: hand wash cold", "")
    assert "chenille_care" not in S.audit_text(stripped, before_ctx).failures
    assert "chenille_care" in S.audit_text(stripped, after_ctx).failures
    # A chunky (not chenille) yarn is not asked for the chenille note.
    from brambleloop.products import texture

    chunky = texture.build_ribbed_scarf()
    assert "Chenille sheds" not in (S.chunky_hook_range_text(chunky) or "")


def test_the_gauge_section_must_carry_tension_guidance_once_the_qa_class_is_learned():
    """MM-L7's second effect: the missing-gauge -> tension class becomes a PDF requirement."""
    from brambleloop.products import launch0

    B.reset_snapshot()
    cir = launch0.cir_for("hexagon_coasters")
    result, twin, _b, text = _engine(cir)
    before_ctx = S.context(cir, twin, result, "US", lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", lessons=frozenset({B.PDF_TENSION}))
    assert "tension_guidance" not in S.audit_text(text, before_ctx).required
    after = S.audit_text(text, after_ctx)
    assert "tension_guidance" in after.required and "tension_guidance" not in after.failures
    stripped = text.replace("larger hook", "hook")
    assert "tension_guidance" not in S.audit_text(stripped, before_ctx).failures
    assert "tension_guidance" in S.audit_text(stripped, after_ctx).failures


def test_amigurumi_instructions_must_be_grouped_by_component_once_learned():
    """HC-L4: the pattern pages group by component, in the CIR's order."""
    cir, result, twin, text = _ami_text()
    assert len(cir.components) > 1
    before_ctx = S.context(cir, twin, result, "US", childrens=True, lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", childrens=True,
                          lessons=frozenset({B.PDF_COMPONENT_GROUPED}))
    assert "component_grouped" not in S.audit_text(text, before_ctx).required
    after = S.audit_text(text, after_ctx)
    assert "component_grouped" in after.required, after.required
    assert "component_grouped" not in after.failures, after.failures
    # The same pages with the last component's group heading gone.
    last = cir.components[-1].name.replace("_", " ")
    import re

    stripped = re.sub(rf"\b{re.escape(last)}\b", "piece", text, flags=re.I)
    assert "component_grouped" not in S.audit_text(stripped, before_ctx).failures
    assert "component_grouped" in S.audit_text(stripped, after_ctx).failures


def _joined_friend():
    import fixture_amigurumi as F

    sewn = F.pebble_friend()
    return dataclasses.replace(sewn, assembly=[
        dataclasses.replace(sewn.assembly[0], method="slst")] + list(sewn.assembly[1:]))


def test_the_techniques_appendix_explains_joining_as_you_go_once_learned():
    """MM-L2: a piece crocheted into a stated round. Both layouts print a 'Joining as you
    go' entry for it (whatever the snapshot, so bytes never depend on the process); the
    stored lesson makes the standard require it. Same document text before and after."""
    import fixture_amigurumi as F

    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish import technique_appendix as TA

    cir = _joined_friend()
    assert B.join_as_you_go_seams(cir)
    assert "Joining as you go" in [e.name for e in TA.entries(cir, "US")]
    assert "Joining as you go" not in [e.name for e in TA.entries(F.pebble_friend(), "US")]
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    name, how = TA.JOIN_AS_YOU_GO_HOW
    full = f"{TA.HEADING} " + " ".join(f"{e.name} {e.how}" for e in TA.entries(cir, "US"))
    stripped = full.replace(name, "").replace(" ".join(how.split())[:60], "")
    before_ctx = S.context(cir, twin, result, "US", childrens=True, lessons=frozenset())
    after_ctx = S.context(cir, twin, result, "US", childrens=True,
                          lessons=frozenset({B.PDF_JOIN_AS_YOU_GO}))
    assert "join_as_you_go" not in S.audit_text(full, before_ctx).required
    a = S.audit_text(full, after_ctx)
    assert "join_as_you_go" in a.required and "join_as_you_go" not in a.failures, a.failures
    assert "join_as_you_go" not in S.audit_text(stripped, before_ctx).failures
    assert "join_as_you_go" in S.audit_text(stripped, after_ctx).failures
    # A fully sewn toy is not asked for it.
    sewn = F.pebble_friend()
    r2 = compile_cir(sewn)
    ctx2 = S.context(sewn, build_twin(sewn, r2), r2, "US", childrens=True,
                     lessons=frozenset({B.PDF_JOIN_AS_YOU_GO}))
    assert "join_as_you_go" not in S.audit_text(full, ctx2).required


def test_the_delivered_file_must_be_the_pdf_itself_never_a_link_page():
    """HC-L6: the same upload bytes, before and after ingestion, through the Etsy upload."""
    import types

    from brambleloop.integrations import etsy

    link_page = (b"<!DOCTYPE html><html><body>Your pattern: <a href=\"https://example.invalid/"
                 b"f\">download</a></body></html>")
    from brambleloop.products import launch0

    _r, _t, real_pdf, _x = _engine(launch0.cir_for("hexagon_coasters"))
    sent = []
    fake = types.SimpleNamespace(
        _require=lambda authority: types.SimpleNamespace(shop_id="1"),
        _call=lambda *a, **k: (sent.append(k), types.SimpleNamespace(
            body={"listing_file_id": 9}))[1])

    def upload(data):
        return etsy.EtsyClient._attach_file(fake, "7", filename="pattern-us.pdf", data=data)

    B.reset_snapshot()
    assert etsy.digital_file_refusals("pattern-us.pdf", len(link_page)) == []
    assert upload(link_page) is True            # before: the link page would have gone up
    db = _db()
    B.ingest(db)
    try:
        upload(link_page)
    except etsy.EtsyRejected as exc:
        assert "HC-L6" in str(exc) and "link page" in str(exc)
    else:
        raise AssertionError("a link page was uploaded as the deliverable after HC-L6")
    assert upload(real_pdf) is True             # the certified PDF itself still goes up
    import hashlib

    on = {B.DELIVERY_PDF: ("HC-L6",)}
    assert B.delivery_refusals("p.pdf", real_pdf, effects=on,
                               certified_sha256=hashlib.sha256(real_pdf).hexdigest()) == []
    assert B.delivery_refusals("p.pdf", real_pdf, effects=on, certified_sha256="0" * 64)
    assert B.delivery_refusals("p.pdf", real_pdf[:200], effects=on)        # truncated
    B.flush(db)
    rb = B.readback(db)["departments"]["customer_experience"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["HC-L6"], rb
    B.reset_snapshot()


def test_listing_copy_may_not_promise_photos_and_titles_front_load_the_object():
    """HC-L3 (creative_assets, blocking) and HC-L7 (seo_search, advice): same listing."""
    import fixture_amigurumi as F

    from brambleloop.seo import truth

    title = "Easy toy pattern with step by step photos, amigurumi crochet pattern pdf"
    tags = ["amigurumi pattern", "photo tutorial"]
    facts = _facts(F.pebble_friend())
    on = {B.ASSET_NO_FAKE_PHOTO: ("HC-L3",), B.SEO_FRONT_LOAD: ("HC-L7",)}
    before = truth.validate_listing(title, tags, facts, competitors=[], lessons={})
    after = truth.validate_listing(title, tags, facts, competitors=[], lessons=on)
    hc3 = [f for f in after["blocking"] if "HC-L3" in f]
    assert not [f for f in before["blocking"] if "HC-L3" in f]
    assert len(hc3) == 2 and not after["ok"], hc3          # the title and one tag
    hc7 = [f for f in after["soft"] if "HC-L7" in f]
    assert not [f for f in before["soft"] if "HC-L7" in f]
    assert hc7 and all(f.startswith("TITLE_NOT_FRONT_LOADED") for f in hc7), hc7
    assert not any("HC-L7" in f for f in after["blocking"])  # advice, never a block
    good = truth.validate_listing("Pebble Friend amigurumi crochet pattern pdf",
                                  ["amigurumi pattern"], facts, competitors=[], lessons=on)
    assert not [f for f in good["blocking"] + good["soft"] if "HC-L" in f]


def test_a_toy_campaign_shows_scale_in_a_hand_once_learned():
    """MM-L5: the same campaign plan, before and after; a pillow is not changed."""
    from brambleloop.visual import shot_plans as SP

    def scale(category):
        return next(r["brief"] for r in SP.flux_campaign_for(category)["roles"]
                    if r["role"] == "size")

    B.reset_snapshot()
    before, pillow_before = scale("amigurumi"), scale("pillow")
    assert "hand" not in before
    db = _db()
    B.ingest(db)
    after = scale("amigurumi")
    assert after == B.HAND_SCALE_BRIEF and after != before
    assert scale("pillow") == pillow_before
    B.flush(db)
    rb = B.readback(db)["departments"]["creative_assets"]
    assert rb["lessons_applied"] == ["MM-L5"], rb
    B.reset_snapshot()


def test_production_readback_reports_every_department_and_unknown_is_never_zero():
    """After all hooks: each department is a number only where its hook ran."""
    db = _db()
    B.ingest(db)
    B.concept_rank_adjustments(db, SEEDS)
    rb = progress.readback(db)["benchmark_lessons"]["departments"]
    assert rb["market_radar"]["applied"] == 1
    assert rb["product_creativity"]["applied"] == 0      # ran, no farm animal in SEEDS
    for d in ("pricing", "customer_experience", "creative_assets", "seo_search",
              "pattern_engineering", "quality"):
        assert rb[d]["applied"] == B.UNKNOWN and rb[d]["applied"] != 0, (d, rb[d])
    B.reset_snapshot()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
