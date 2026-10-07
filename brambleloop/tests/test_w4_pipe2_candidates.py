"""W4-PIPE2: the moment-first creative candidates engineered as pattern software."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import moment_candidates as mc  # noqa: E402

FAILED: list[str] = []
TODAY = date(2026, 10, 7)

# The only certification errors an engineered candidate may carry: physical evidence a
# maker supplies (an uncalibrated stitch, or a class C stuffed form needing a full make).
PHYSICAL = {"reading-nook-cable-wrap": {"UNCALIBRATED_PRIMITIVE"},
            "heart-row-ring-pillow": {"PHYSICAL_TEST_REQUIRED"},
            "spring-garden-kneeler": {"PHYSICAL_TEST_REQUIRED"}}


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


def test_every_candidate_is_pattern_software():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.creative import emotional_brief as eb
    from brambleloop.gates.certificate import certify
    from brambleloop.publish.eligibility import name_truth

    queue = eb.gate_candidates(today=TODAY)["engineering_queue"]
    assert mc.ENGINEERED, "nothing engineered"
    check("engineered_in_queue_order",
          list(mc.ENGINEERED) == [s for s in queue if s in mc.ENGINEERED], queue)
    check("seven_engineered_plus_pipe_pencil_roll",
          set(mc.ENGINEERED) | {"teacher-chevron-pencil-roll"} == set(queue), queue)
    for slug, make in mc.ENGINEERED.items():
        cir = make()
        result = compile_cir(cir)
        check(f"compiles_clean:{slug}", result.ok and not result.warnings,
              [str(f) for f in result.findings][:3])
        cert = certify(cir)
        errors = {f.code for f in cert.findings if str(f.severity).upper().endswith("ERROR")}
        allowed = PHYSICAL.get(slug, set())
        check(f"certifies_or_waits_only_on_a_maker:{slug}",
              (cert.granted and not allowed) or (errors == allowed and not cert.granted),
              sorted(errors))
        check(f"name_true:{slug}", name_truth(cir) == [], name_truth(cir))
        check(f"prerelease:{slug}", cir.version.startswith("0."), cir.version)
        check(f"original_no_benchmark_consulted:{slug}",
              cir.provenance is not None and cir.provenance.benchmarks_consulted == ())
        check(f"size_from_twin:{slug}", "digital twin" in (cir.finished_size_note or ""))
        check(f"declared_class_is_effective:{slug}",
              not any(f.code == "RISK_CLASS_RAISED_BY_MATRIX" for f in cert.findings))
        check(f"brief_departures_written:{slug}", bool(mc.ENGINEERING_NOTES.get(slug)))


def test_forms_the_titles_name_are_built():
    from brambleloop.products import launch0

    for slug, make in mc.ENGINEERED.items():
        cir = make()
        promise = launch0.assembly_promise(cir)
        check(f"assembly_promise_backed:{slug}", promise.get("backed", True), promise)
    sock = mc.first_christmas_stocking()
    check("stocking_worked_in_the_round",
          sock.components[0].construction == "joined_rounds")
    check("stocking_has_heel_and_loop",
          {c.name for c in sock.components} == {"stocking", "heel", "hanging_tab"})
    wrap = mc.reading_nook_cable_wrap()
    check("wrap_has_real_cable_crossings",
          any(getattr(o, "stitch", "") == "cable2x2" for _c, r in wrap.iter_rows()
              for n in r.ops for o in getattr(n, "ops", [n])))
    garland = mc.snowfall_advent_garland()
    check("garland_makes_24_mittens",
          next(c for c in garland.components if c.name == "mitten").make == 24)
    for cir in (mc.heart_row_ring_pillow(), mc.spring_garden_kneeler()):
        check(f"stuffing_is_in_the_materials:{cir.slug}",
              any("fibrefill" in m.name for m in cir.materials))


def test_the_tulip_trellis_motif_is_sound():
    from brambleloop.products import motifs

    check("tulip_trellis_in_library", "tulip-trellis" in motifs.LIBRARY)
    check("library_still_sound", motifs.check_library() == [], motifs.check_library())


def test_concept_board_is_deterministic_and_reaches_the_taste_gate():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.db import Database
    from brambleloop.creative import intake

    cir = mc.first_christmas_stocking()
    png = mc.board_png(cir)
    assert png, "no board bytes"
    check("board_is_deterministic", png == mc.board_png(cir))
    check("board_is_a_png", png[:8] == b"\x89PNG\r\n\x1a\n")

    db = Database("sqlite://")
    db.create_all()
    slug = cir.slug
    check("no_board_reads_empty", intake.board_for(db, slug) == ""
          and intake.board_digest_for(db, slug) == "")
    import tempfile
    store = ArtifactStore(root=Path(tempfile.mkdtemp(prefix="pipe2-store-")))
    rec = mc.file_board(db, cir, store)
    check("board_found_by_intake", intake.board_for(db, slug) == rec["image_ref"])
    check("board_digest_bound", intake.board_digest_for(db, slug) == rec["image"]["sha256"])
    reg = mc.register_for_taste_gate(db, slug, today=TODAY)
    check("registered_waiting", reg.get("registered") and reg["decision"] == intake.WAITING, reg)
    out = intake.regate_held(SimpleNamespace(db=db), today=TODAY)
    held = {h["slug"]: h["waiting_on"] for h in out["held"]}
    check("regate_holds_it_at_needs_taste", slug in held, out)
    check("waits_only_on_vision_not_on_a_board",
          held.get(slug) == ["vision_model (no vision probe has succeeded)"], held.get(slug))
    check("nothing_judged_or_queued", out["presented"] == [] and out["queued"] == [], out)


def test_the_pipeline_board_carries_them():
    from brambleloop.products import pipeline_board as pb

    for slug in mc.ENGINEERED:
        check(f"registered_on_board:{slug}", slug in pb.CREATIVE_ENGINEERED
              and slug in pb.CREATIVE_SEARCH)
    by = {c.slug: c for c in pb.creative_candidates()}
    assert by, "no creative candidates"
    for slug in ("first-christmas-stocking", "spring-garden-kneeler"):
        c = by[slug]
        pb._advance(c, None, {}, None, False)
        check(f"design_and_product_pass:{slug}",
              c.stages["DESIGN"]["status"] == pb.PASS
              and c.stages["PRODUCT"]["status"] == pb.PASS, c.to_dict()["stages"])
    check("stocking_clears_product_truth",
          by["first-christmas-stocking"].stages["PRODUCT_TRUTH"]["status"] == pb.PASS)
    k = by["spring-garden-kneeler"].stages["PRODUCT_TRUTH"]
    check("class_c_waits_on_a_maker_not_a_rename",
          k["status"] == pb.FAIL and k["clearer"] == "OWNER", k)


if __name__ == "__main__":
    test_every_candidate_is_pattern_software()
    test_forms_the_titles_name_are_built()
    test_the_tulip_trellis_motif_is_sound()
    test_concept_board_is_deterministic_and_reaches_the_taste_gate()
    test_the_pipeline_board_carries_them()
    print(f"{'FAIL' if FAILED else 'OK'} test_w4_pipe2_candidates ({len(FAILED)} failed)")
    sys.exit(1 if FAILED else 0)
