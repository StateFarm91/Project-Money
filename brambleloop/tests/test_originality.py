"""The IP firewall's publishable half: provenance, licences, ledgers, similarity, references.

Master v1.0 v0.23 s78-79, read through Final Build supersession S1: private reverse-engineering
of a purchased pattern is allowed; publishing its protected text or images, or a light
derivative of its design, is not. Every benchmark in these tests is synthetic -- a fixture
CIR, a fixture text written for this file, or Brambleloop's own pattern standing in for a
purchase -- and no competitor text is stored here or anywhere.

Failing checks here are findings, not flakes. Do not weaken them to get green.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir import benchmarks as B  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Provenance, Row  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    BenchmarkFingerprintRecord, BenchmarkLicence, BenchmarkListing, BenchmarkProduct,
    DesignDifferenceLedger,
)
from brambleloop.creative import preengineering as pe  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.intel import benchmarks as intel_benchmarks  # noqa: E402
from brambleloop.products import builder, garments, launch0  # noqa: E402
from brambleloop.teardown import intake, library, reader  # noqa: E402
from brambleloop.teardown import licence as L  # noqa: E402


def _db(path: str | None = None) -> Database:
    db = Database(f"sqlite:///{path}" if path else "sqlite://")
    db.create_all()
    return db


def _catalogue() -> list[CIR]:
    from brambleloop.runtime.pipeline import ENGINEERED, _engineered_cir

    out = [_engineered_cir(s) for s in list(builder.CATALOGUE) + list(ENGINEERED)]
    out += list(garments.every_graded_cir().values())
    out += [launch0.cir_for(k) for k in launch0.BUILDERS]
    return out


# ---------------------------------------------------------------------------
# F-783 / F-798: design provenance is required


def test_every_catalogue_cir_carries_complete_design_provenance():
    cirs = _catalogue()
    assert len(cirs) > 30
    for cir in cirs:
        assert cir.authored == "brambleloop", cir.slug
        assert O.provenance_gaps(cir.provenance) == [], (cir.slug, cir.provenance)
        assert cir.provenance.generated_by == "brambleloop", cir.slug
        assert tuple(cir.provenance.benchmarks_consulted) == (), cir.slug
        assert O.provenance_findings(cir) == [], cir.slug


def test_the_backfill_changes_no_design_only_the_record():
    """Stripping the provenance leaves exactly the design that existed before the backfill."""
    assert len(_catalogue()) >= 12
    for cir in _catalogue()[:12]:
        d = cir.to_dict()
        assert "provenance" in d
        bare = CIR.from_dict({k: v for k, v in d.items() if k != "provenance"})
        assert bare.provenance is None
        assert [c.rows for c in bare.components] == [c.rows for c in cir.components]
        assert bare.title == cir.title and bare.designer_notes == cir.designer_notes


def test_the_catalogue_builders_import_nothing_from_benchmarks_or_research():
    """What makes `benchmarks_consulted=()` true rather than asserted."""
    for name in ("builder", "nordic_forest", "texture", "vessels", "garments", "motifs"):
        tree = ast.parse((ROOT / "src/brambleloop/products" / f"{name}.py").read_text())
        for node in ast.walk(tree):  # vacuity-ok: ast.walk always yields at least the module node
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "benchmarks" not in mod and "research" not in mod, (name, mod)
            if isinstance(node, ast.Import):
                assert not any("research" in a.name for a in node.names), name


def test_a_brambleloop_release_without_provenance_is_refused():
    cir = fixtures.good_mosaic_panel()
    assert certify(cir).granted, "the fixture must certify when its record is complete"
    cir.provenance = None
    cert = certify(cir)
    assert not cert.granted
    assert [f.code for f in cert.errors] == ["PROVENANCE_MISSING"], cert.blocking_reasons


def test_an_incomplete_or_foreign_provenance_is_refused():
    cir = fixtures.good_mosaic_panel()
    cir.provenance = Provenance(concept_key="test-mosaic", brief_digest="", primitives_used=())
    codes = [f.code for f in certify(cir).errors]
    assert codes == ["PROVENANCE_INCOMPLETE"], codes
    cir.provenance = Provenance(concept_key="test-mosaic", brief_digest="x",
                                primitives_used=("p",), generated_by="some-llm-paraphrase")
    codes = [f.code for f in certify(cir).errors]
    assert codes == ["PROVENANCE_NOT_OURS"], codes


def test_a_benchmark_record_is_not_asked_for_design_provenance():
    assert O.provenance_findings(B.cardigan("M")) == []


def test_a_prototype_authored_design_carries_its_provenance():
    from brambleloop.creative import prototype as P
    from brambleloop.creative.concept import Concept

    c = Concept(key="heath-throw-x", title="Heath Throw", premise=(
        "A heathered throw whose ridged border frames a field of quiet texture for evenings"),
        pod="home", form="rectangle_throw", construction="flat_rows", motif="heather ridge",
        palette_story="moss and oat", recipient="self", occasion="everyday", feeling="rugged",
        function="keeps a reader warm on the sofa", make_lane="MEDIUM")
    cir = P.author(c)
    assert O.provenance_gaps(cir.provenance) == []
    assert cir.provenance.concept_key == "heath-throw-x"
    assert not cir.provenance.benchmarks_consulted


# ---------------------------------------------------------------------------
# F-786 / F-787 / F-788: licence records


def test_finished_item_rights_and_pattern_rights_are_separate_fields():
    lic = L.KNOWN_LICENCES["benchmark-2-mini-star-stitch-cardigan"]
    assert lic.pattern_rights == "personal_use"
    assert lic.finished_item_rights == "unstated"
    assert "images" in lic.notes and "text" in lic.notes
    for use in ("listing_image", "listing_copy", "generation_reference", "republish_pattern",
                "adapt_pattern_for_sale", "instruction_drafting"):
        assert not lic.permits(use)[0], use
    for use in ("private_analysis", "functional_reconstruction", "similarity_review"):
        assert lic.permits(use)[0], use


def test_a_public_source_can_never_grant_a_publishing_use():
    try:
        L.Licence(source_ref="blog-x", source_kind="public_web", terms_source="free post",
                  allowed_uses=("demand_research", "listing_copy"), prohibited_uses=(),
                  pattern_rights="none")
        raise AssertionError("a public source granted listing_copy")
    except ValueError:
        pass
    db = _db()
    rec = L.register_public_source(db, "blog-free-hat", url="https://example.invalid/hat")
    assert rec["pattern_rights"] == "none"
    assert not L.licence_for(db, "blog-free-hat").permits("republish_pattern")[0]
    assert L.licence_for(db, "blog-free-hat").permits("general_technique_research")[0]


def test_unknown_terms_read_conservatively_and_never_permissively():
    lic = L.licence_for(None, "never-recorded")
    assert lic.pattern_rights == "personal_use" and lic.finished_item_rights == "unknown"
    assert set(lic.prohibited_uses) == set(L.PUBLISHING_USES)
    assert lic.permits("private_analysis")[0]


def test_intake_captures_the_licence_and_it_survives_a_restart():
    tmp = tempfile.mkdtemp(prefix="licence-")
    path = f"{tmp}/l.sqlite"
    db = _db(path)
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=intel_benchmarks.MJS_KEY, listing_ref="77",
                               title="Fixture throw", pod="blankets", product_type="pattern",
                               price_cad=7.0, url="https://example.invalid/77", detail={}))
    env = {library.LIBRARY_ENV: f"{tmp}/lib"}
    out = intake.receive(db, "77", [("pattern.pdf", b"PDF")], env=env, mirror_files=False)
    assert out["licence"]["pattern_rights"] == "personal_use"
    assert "unstated" in out["licence"]["terms_source"]
    # A re-upload does not overwrite terms somebody recorded by hand.
    L.capture_purchase(db, "mjs-77", terms={"terms_source": "owner read the listing",
                                            "finished_item_rights": "permitted",
                                            "attribution": "credit the designer"})
    intake.receive(db, "77", [("pattern.pdf", b"PDF")], env=env, mirror_files=False)

    restarted = Database(f"sqlite:///{path}")      # a new process on the same database
    lic = L.licence_for(restarted, "mjs-77")
    assert lic.finished_item_rights == "permitted" and lic.pattern_rights == "personal_use"
    assert lic.terms_source == "owner read the listing"
    with restarted.session() as s:
        refs = {r.source_ref for r in s.scalars(select(BenchmarkLicence))}
    assert {"mjs-77", "benchmark-2-mini-star-stitch-cardigan"} <= refs


def test_the_library_refuses_a_use_the_licence_does_not_grant():
    tmp = tempfile.mkdtemp(prefix="libuse-")
    (Path(tmp) / "mjs-5").mkdir()
    (Path(tmp) / "mjs-5" / "p.pdf").write_bytes(b"x")
    env = {library.LIBRARY_ENV: tmp}
    db = _db()
    assert library.retrieve("mjs-5/p.pdf", "teardown_analyst", env=env, db=db) == b"x"
    try:
        library.retrieve("mjs-5/p.pdf", "teardown_analyst", env=env, db=db,
                         use="instruction_drafting")
        raise AssertionError("an analyst read a purchase for instruction drafting")
    except library.LibraryRefused as exc:
        assert "instruction_drafting" in str(exc)


# ---------------------------------------------------------------------------
# F-785: benchmark and seller images never condition a render


def _png(path: Path, payload: bytes = b"\x89PNG fixture") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_a_benchmark_or_seller_image_is_refused_as_a_generation_reference():
    tmp = Path(tempfile.mkdtemp(prefix="refs-"))
    lib = tmp / "lib"
    os.environ[library.LIBRARY_ENV] = str(lib)
    try:
        refused = [
            _png(lib / "mjs-9" / "cover.png"),                    # inside the quarantine
            _png(tmp / "seller_photos" / "a.png"),                 # seller photography
            _png(tmp / "work" / "seller-photo-3.png"),             # named as such
            _png(tmp / "bench" / "designer_photos" / "p1.png"),    # a benchmark designer's
            _png(tmp / "research" / "bench2" / "out" / "ref.png"),  # a benchmark reconstruction
        ]
        provider = I.BY_KEY["gpt-image-2"]
        assert refused, 'no refused references were built'
        for ref in refused:
            try:
                I._request_for(provider, "K", "a cardigan", [ref], "1024x1024")
                raise AssertionError(f"{ref} reached a request body")
            except I.ImagesRefused as exc:
                assert "F-785" in str(exc), exc
        ours = _png(tmp / "renders" / "twin-hero.png", b"our own twin render")
        url, _h, body = I._request_for(provider, "K", "a cardigan", [ours], "1024x1024")
        assert "/images/edits" in url and b"our own twin render" in body
    finally:
        os.environ.pop(library.LIBRARY_ENV, None)


def test_a_renamed_copy_of_a_purchased_file_is_refused_by_its_bytes():
    tmp = Path(tempfile.mkdtemp(prefix="refs-hash-"))
    payload = b"bytes of a purchased listing photo (fixture)"
    db = _db()
    import hashlib

    with db.session() as s:
        s.add(BenchmarkProduct(ref="mjs-1", seller="fixture", files=[
            {"name": "photo.png", "role": "photo", "bytes": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest()}]))
    innocent = _png(tmp / "renders" / "hero-final.png", payload)
    try:
        O.refuse_benchmark_reference(innocent, benchmark_hashes=O.benchmark_file_hashes(db))
        raise AssertionError("renamed benchmark bytes passed")
    except O.ReferenceRefused as exc:
        assert "byte-identical" in str(exc)
    try:
        I._request_for(I.BY_KEY["gpt-image-2"], "K", "x", [innocent], "1024x1024",
                       benchmark_hashes=O.benchmark_file_hashes(db))
        raise AssertionError("the request builder sent renamed benchmark bytes")
    except I.ImagesRefused:
        pass


# ---------------------------------------------------------------------------
# F-794 / F-791: the design-difference ledger and the meaningful-redesign gate

MATERIAL_LEDGER = [{
    "benchmark_ref": "synthetic-bench-a",
    "learned": "buyers praise a roomy fit but report the neckline gapes on smaller sizes",
    "changed": [
        {"aspect": "construction", "what": "worked top-down with a raglan yoke instead of "
                                           "flat panels seamed at the shoulder"},
        {"aspect": "fit", "what": "graded from a published body table with 8 cm positive "
                                  "ease at the chest", "magnitude_pct": 18},
        {"aspect": "stitch_system", "what": "a linen-stitch texture replaces the plain field"},
    ],
    "why_better": "no shoulder seams to sew, a neckline that sits on every size, and a "
                  "denser fabric that holds its shape",
    "independent_aspects": ["size table", "yoke increase plan", "edging"],
}]


def test_a_ledger_of_material_redesign_passes():
    v = O.redesign_verdict(MATERIAL_LEDGER, ["synthetic-bench-a"])
    assert v["passed"], v["reasons"]


def test_a_ledger_of_superficial_changes_is_refused():
    superficial = [{**MATERIAL_LEDGER[0], "changed": [
        {"aspect": "colour", "what": "sage instead of oat"},
        {"aspect": "yarn", "what": "cotton instead of acrylic"},
        {"aspect": "button_count", "what": "five buttons, not six"},
        {"aspect": "wording", "what": "instructions reworded"},
        {"aspect": "size_labels", "what": "S/M/L instead of 1/2/3"},
    ]}]
    v = O.redesign_verdict(superficial, ["synthetic-bench-a"])
    assert not v["passed"]
    assert "0 material change" in " ".join(v["reasons"])


def test_a_superficial_change_labelled_material_is_still_superficial():
    disguised = [{**MATERIAL_LEDGER[0], "changed": [
        {"aspect": "proportions", "what": "body 2 cm longer", "magnitude_pct": 4},
        {"aspect": "construction", "what": "two rows added", "rows_delta": 2},
        {"aspect": "features", "what": "different colour buttons"},
    ]}]
    v = O.redesign_verdict(disguised, ["synthetic-bench-a"])
    assert not v["passed"], v
    per = v["per_benchmark"]["synthetic-bench-a"]
    assert per["material"] == [] and "small_dimensions" in per["superficial"]
    assert "few_rows" in per["superficial"]


def test_every_consulted_benchmark_needs_its_own_entry():
    v = O.redesign_verdict(MATERIAL_LEDGER, ["synthetic-bench-a", "synthetic-bench-b"])
    assert not v["passed"] and "synthetic-bench-b" in " ".join(v["reasons"])


def test_certify_requires_the_ledger_when_provenance_lists_benchmarks():
    cir = fixtures.good_mosaic_panel()
    cir.provenance.benchmarks_consulted = ("synthetic-bench-a",)
    codes = [f.code for f in certify(cir).errors]
    assert codes == ["DESIGN_LEDGER_MISSING", "ORIGINALITY_EVIDENCE_UNKNOWN"], codes
    O.DECLARED_LEDGERS["test-mosaic"] = tuple(
        O.LedgerEntry.from_dict({**MATERIAL_LEDGER[0], "changed": [
            {"aspect": "colour", "what": "wine instead of red"}]}) for _ in [0])
    try:
        codes = [f.code for f in certify(cir).errors]
        assert codes == ["REDESIGN_NOT_MEANINGFUL", "ORIGINALITY_EVIDENCE_UNKNOWN"], codes
        O.DECLARED_LEDGERS["test-mosaic"] = tuple(
            O.LedgerEntry.from_dict(e) for e in MATERIAL_LEDGER)
        cert = certify(cir)
        # A material in-memory ledger cannot prove current corpus/licence checks.
        assert not cert.granted
        assert [f.code for f in cert.errors] == ["ORIGINALITY_EVIDENCE_UNKNOWN"]
    finally:
        O.DECLARED_LEDGERS.pop("test-mosaic", None)


GOOD_CONCEPT = dict(
    key="lantern-pocket-stocking-g", title="Lantern Pocket Stocking",
    premise=("A stocking whose cuff folds down into a row of lantern-shaped pockets that "
             "glow with contrasting yarn windows"),
    pod="stockings", form="stocking", construction="modular_panels", motif="lantern",
    palette_story="ember windows on pine", recipient="child", occasion="housewarming",
    feeling="celebratory", function="holds small notes and treats in each pocket",
    make_lane="LONG", thumbnail_reads_small=True, craft_impression=4.2)


def test_pre_engineering_refuses_a_competitor_informed_concept_without_a_real_redesign():
    from datetime import date

    brief = {"thumbnail_storyboard": "deep green stocking, cuff folded down showing six "
                                     "lantern pockets with glowing amber windows",
             "silhouette_qualifiers": ["modular_reveal"],
             "benchmarks_consulted": ["synthetic-bench-a"]}
    v = pe.gate_concept(None, {"concept": GOOD_CONCEPT, "brief": brief}, benchmark=[],
                        catalogue=[], today=date(2026, 9, 17))
    assert v["checks"]["redesign"]["status"] == pe.FAIL and "redesign" in v["failed"]
    assert not v["engineer"]
    v = pe.gate_concept(None, {"concept": GOOD_CONCEPT,
                               "brief": {**brief, "design_difference_ledger": MATERIAL_LEDGER}},
                        benchmark=[], catalogue=[], today=date(2026, 9, 17))
    assert v["checks"]["redesign"]["status"] == pe.PASS, v["checks"]["redesign"]
    assert "redesign" not in v["failed"]
    # Not competitor-informed: recorded as not applicable, never as passed.
    v = pe.gate_concept(None, {"concept": GOOD_CONCEPT, "brief": {
        k: brief[k] for k in ("thumbnail_storyboard", "silhouette_qualifiers")}},
        benchmark=[], catalogue=[], today=date(2026, 9, 17))
    assert v["checks"]["redesign"]["status"] == pe.NOT_APPLICABLE


def test_the_ledger_is_made_durable_when_the_gate_records_its_verdict():
    from datetime import date

    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    brief = {"thumbnail_storyboard": "deep green stocking, cuff folded down showing six "
                                     "lantern pockets with glowing amber windows",
             "silhouette_qualifiers": ["modular_reveal"],
             "benchmarks_consulted": ["synthetic-bench-a"],
             "design_difference_ledger": MATERIAL_LEDGER}
    v = pe.gate_concept(db, {"concept": GOOD_CONCEPT, "brief": brief}, benchmark=[],
                        catalogue=[], today=date(2026, 9, 17))
    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("creative_director", "cir.draft", {}), db=db, queue=q,
                     registry=Registry(db), phase=None)
    effects = pe.record(ctx, v, source="test")
    assert effects.get("ledger_recorded")
    with db.session() as s:
        row = s.scalar(select(DesignDifferenceLedger))
        assert row.concept_key == GOOD_CONCEPT["key"] and row.passed
        assert row.benchmark_ref == "synthetic-bench-a" and len(row.changed) == 3
    # And the gate reads it back from the database when the brief no longer carries it.
    again = pe.gate_concept(db, {"concept": GOOD_CONCEPT, "brief": {
        k: v2 for k, v2 in brief.items() if k != "design_difference_ledger"}},
        benchmark=[], catalogue=[], today=date(2026, 9, 17))
    assert again["checks"]["redesign"]["status"] == pe.PASS
    assert again["checks"]["redesign"]["detail"]["ledger_source"] == "database"


# ---------------------------------------------------------------------------
# F-795: similarity review before sale, against both purchased benchmarks


def _relabelled_benchmark_1() -> CIR:
    cir = B.cardigan("M")
    cir.authored, cir.slug, cir.title = "brambleloop", "meadow-cardigan-m", "Meadow Cardigan"
    return cir


def _synthetic_star_cardigan() -> CIR:
    """A fixture shaped like benchmark 2's garment architecture and numbers (size 2-3T),
    with none of its wording: what a light derivative looks like to the review."""
    def piece(name, n, loop="both"):
        return Component(name, "flat_rows", foundation=n, rows=[
            Row(i, [Op("sc", n, loop=loop)], declared_count=n, turning_chain=1)
            for i in (1, 2)])
    return CIR(
        slug="mini-hooded-cardigan", title="Mini Hooded Cardigan", version="1.0.0",
        construction="flat_rows", gauge=Gauge(18, 10),
        materials=[Material(name="dk acrylic", yarn_weight="dk")],
        components=[piece("hem_band", 58, "back"), piece("back_body", 58),
                    piece("yoke", 118), piece("neck_opening", 22), piece("front", 56),
                    piece("front_panel", 26), piece("hood", 42), piece("cuff", 24, "back"),
                    piece("collar", 10, "back"), piece("button_band", 5, "back")],
        provenance=Provenance("mini-hooded-cardigan", "fixture", ("tests",)))


def test_the_review_compares_against_both_purchased_benchmarks():
    review = O.similarity_review(fixtures.good_mosaic_panel())
    assert review["benchmarks_compared"] == ["benchmark-1-side-to-side-cardigan",
                                             "benchmark-2-mini-star-stitch-cardigan"]
    assert not review["escalate"]
    # Wording is unmeasured, never "clear", while no benchmark text has been fingerprinted.
    assert any(u.endswith(":wording") for u in review["unmeasured"])


def test_a_relabelled_benchmark_1_is_escalated_for_redesign():
    review = O.similarity_review(_relabelled_benchmark_1())
    esc = {e["benchmark"]: e["dimensions"] for e in review["escalated"]}
    assert "benchmark-1-side-to-side-cardigan" in esc
    assert {"features", "construction", "numeric"} <= set(esc["benchmark-1-side-to-side-cardigan"])


def test_a_light_derivative_of_benchmark_2_is_escalated_for_redesign():
    review = O.similarity_review(_synthetic_star_cardigan())
    esc = {e["benchmark"]: e["dimensions"] for e in review["escalated"]}
    assert set(esc) == {"benchmark-2-mini-star-stitch-cardigan"}, review["escalated"]
    assert {"numeric", "features", "construction"} <= set(
        esc["benchmark-2-mini-star-stitch-cardigan"])
    cert = certify(_synthetic_star_cardigan())
    assert not cert.granted
    assert any(f.code == "SIMILARITY_ESCALATED" and "benchmark-2" in f.message
               for f in cert.errors), cert.blocking_reasons


def test_no_catalogue_product_escalates_against_either_benchmark():
    assert _catalogue(), 'empty catalogue checks nothing'
    for cir in _catalogue():
        review = O.similarity_review(cir)
        assert not review["escalate"], (cir.slug, review["escalated"])


def test_an_unusual_numeric_run_in_the_text_escalates_but_an_arithmetic_one_does_not():
    cir = fixtures.good_mosaic_panel()
    yoke = " ".join(f"({n} sts)" for n in O.BENCHMARK_2.size_sequences["yoke_sts"][2:8])
    hits = O.compare(cir, O.BENCHMARK_2, pattern_text=f"Row 1: sc across {yoke}")
    assert hits["dimensions"]["numeric"]["verdict"] == "material", hits
    back = " ".join(f"({n} sts)" for n in O.BENCHMARK_2.size_sequences["back_sts"])
    plain = O.compare(cir, O.BENCHMARK_2, pattern_text=f"Row 1: sc across {back}")
    assert plain["dimensions"]["numeric"]["verdict"] == "clear", plain


SYNTHETIC_BENCHMARK_TEXT = (
    "Fixture benchmark prose written for this test file only. Begin with the lower band "
    "worked sideways until it reaches the width of the back, then turn it ninety degrees "
    "and pick up evenly along the long edge for the body, keeping the textured field "
    "between two plain borders and marking every fourth ridge with a removable marker so "
    "the pocket openings can be found again after blocking the finished pieces flat. ") * 3


def test_wording_overlap_is_measured_from_hashes_and_escalates():
    db = _db()
    O.record_fingerprint(db, "synthetic-bench-text", text=SYNTHETIC_BENCHMARK_TEXT)
    with db.session() as s:
        row = s.scalar(select(BenchmarkFingerprintRecord))
        stored = json.dumps([row.wording_shingles, row.title, row.features])
    # Hashes, never the words.
    for word in ("sideways", "removable", "blocking", "ninety"):
        assert word not in stored, word
    cir = fixtures.good_mosaic_panel()
    copied = O.similarity_review(cir, pattern_text=SYNTHETIC_BENCHMARK_TEXT[:600], db=db)
    assert {"benchmark": "synthetic-bench-text", "dimensions": ["wording"]} in copied["escalated"]
    ours = O.similarity_review(cir, pattern_text=(
        "Row 1: ch 41, sc in second chain from hook and in each chain across, turn. Row 2: "
        "ch 1, sc in each stitch across, changing colour at the end, turn."), db=db)
    assert not ours["escalate"], ours["escalated"]


def test_the_teardown_reader_fingerprints_wording_and_keeps_no_text():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import write_pattern
    from brambleloop.publish.pdf import build_pattern_pdf

    stand_in = builder.for_slug(reader.SELF_TEST_SLUG)   # our own pattern plays the purchase
    tmp = tempfile.mkdtemp(prefix="fp-")
    (Path(tmp) / "mjs-42").mkdir()
    (Path(tmp) / "mjs-42" / "p.pdf").write_bytes(build_pattern_pdf(stand_in).pdf_bytes)
    db = _db()
    out = reader.read("mjs-42/p.pdf", env={library.LIBRARY_ENV: tmp}, ref="mjs-42", db=db)
    assert out["wording_fingerprint"]["shingles"] > 20
    assert out["wording_fingerprint"]["holds_no_text"] is True
    # A product whose text is that document's is escalated on wording against it.
    text = write_pattern(stand_in, compile_cir(stand_in), "US")
    review = O.similarity_review(stand_in, pattern_text=text, db=db)
    assert any(e["benchmark"] == "mjs-42" and "wording" in e["dimensions"]
               for e in review["escalated"]), review["escalated"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}  -- {type(exc).__name__}: {str(exc)[:600]}")
            if os.environ.get("CERT_TRACE"):
                traceback.print_exc()
    print(f"\n  {len(tests) - failed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
