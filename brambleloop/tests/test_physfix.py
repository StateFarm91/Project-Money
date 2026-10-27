"""W-PHYSFIX: the physical-sample path, which every first listing now depends on.

A reviewer found six defects in it (research/final_build/w4/PHYSICAL_SAMPLE_PACKAGES.md, G1-G5).
Each test here fails on the code before this fix and passes after it:

1. a sample is compared against the estimate for exactly the pieces made, so one coaster or a
   swatch is no longer refused, and two coasters of four can no longer pass as the whole set
   with a false factor of 0.50 that would halve DK-cotton yardage;
2. the swatch the cost code offers is a swatch the intake accepts;
3. flatness and shape are recorded, and a failure or a recorded problem goes to the owner as
   PARTIAL and never passes by itself;
4. a size outside tolerance halts publication of the release it measured;
5. both kits tell the tester to re-weigh after the swatch, print every step whole, and come
   from one reproducible builder;
6. a sample covers exactly one size, and the first-customer evidence says which sizes are
   physically proven.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, OwnerAction, PhysicalTest,
)
from brambleloop.gates import risk_matrix as rm  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.quality import physical  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402

KIT_DIR = ROOT / "research/final_build/w4/tester_kit"
BAND_GRAMS, BAND_METRES = 50.0, 77.0


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/physfix.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, job_type: str, inputs: dict) -> Job:
    job = JobQueue(db).enqueue("quality_director", job_type, inputs, priority=0)
    Worker(db, f"w-{job_type}", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _certify(db, cir) -> dict:
    job = _run(db, "gate.certify", {"cir": cir.to_dict()})
    return dict(job.outputs or {})


def _grams(cir, fraction: float = 1.0) -> dict:
    """Grams that are exactly `fraction` of the whole pattern's estimated yarn."""
    twin = build_twin(cir, compile_cir(cir))
    return {c: m * fraction / (BAND_METRES / BAND_GRAMS)
            for c, m in twin.yarn_metres_by_color.items()}


def _inputs(cir, fraction: float = 1.0, **extra) -> dict:
    twin = build_twin(cir, compile_cir(cir))
    out = {"slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
           "grams_by_color": _grams(cir, fraction), "ball_band_grams": BAND_GRAMS,
           "ball_band_metres": BAND_METRES, "measured_width_cm": twin.width_cm,
           "measured_height_cm": twin.height_cm}
    return {**out, **extra}


def _rows(db) -> list[PhysicalTest]:
    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _coasters():
    return launch0.cir_for("hexagon_coasters")


def _basket(size: str = "basket_small"):
    return launch0.cir_for(size)


# ---- 1. partial makes are compared against exactly the parts made ------------------------

def test_two_coasters_of_four_never_pass_as_the_whole_set():
    """The old intake passed this with factor 0.50 -- halving every DK-cotton yardage."""
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, 0.5, scope="full_make",
                                              made={"coaster": 2}, lies_flat=True))
    assert job.status in (JobStatus.FAILED, JobStatus.DEAD), job.status
    assert _rows(db) == [], "a partial set was stored as a whole-pattern make"
    # Nor with no `made` at all: a four-piece pattern must say what was made.
    job = _run(db, "physical.record", _inputs(cir, 0.5, scope="full_make", lies_flat=True))
    assert _rows(db) == [], job.last_error
    assert physical.calibration_from_db(db, cir) == 1.0


def test_two_coasters_recorded_as_a_component_give_the_true_factor_and_partial_class():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, 0.5, scope="component",
                                              made={"coaster": 2}, lies_flat=True))
    rows = _rows(db)
    assert len(rows) == 1, job.last_error
    m = rows[0].measured
    assert m["factor"] == 1.0, m["factor"]           # exactly the yarn two coasters use
    assert m["made"] == {"coaster": 2} and m["whole_pattern"] is False
    assert m["evidence_class"] == rm.PARTIAL_PHYSICAL
    assert rows[0].passed is True and m["outcome"] == physical.PASS
    assert physical.calibration_from_db(db, cir) == 1.0, "a true factor of 1.0 changes nothing"


def test_one_coaster_is_accepted_against_one_coasters_estimate():
    """The old intake refused it: one coaster is 0.25 of the set, under FACTOR_FLOOR."""
    cir = _coasters()
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    est = physical.estimate_for_parts(cir, result, {"coaster": 1})
    whole = twin.yarn_metres_by_color
    for colour in whole:
        assert abs(est[colour] * 4 - whole[colour]) <= 0.4, (est, whole)
    report = physical.SampleReport(
        product_slug=cir.slug, version=cir.version, tester_ref="t",
        grams_by_color=_grams(cir, 0.25), ball_band=physical.BallBand(BAND_GRAMS, BAND_METRES),
        scope="component", made={"coaster": 1}, measured_width_cm=twin.width_cm,
        lies_flat=True)
    a = physical.assess(report, twin, cir, result)
    assert a.outcome == physical.PASS and abs(a.factor - 1.0) < 0.02, a.to_dict()


def test_a_swatch_is_gauge_evidence_only_and_never_yardage():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    job = _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "tester-1", "scope": "swatch",
        "grams_by_color": {"cream": 6.0}, "ball_band_grams": BAND_GRAMS,
        "ball_band_metres": BAND_METRES, "hook_mm": 5.0,
        "swatch_stitches_per_10cm": cir.gauge.stitches_per_10cm,
        "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
    rows = _rows(db)
    assert len(rows) == 1, job.last_error
    m = rows[0].measured
    assert m["factor"] is None and m["estimated_metres"] == {}, m
    assert m["evidence_class"] == rm.PARTIAL_PHYSICAL and m["gauge_agrees"] is True
    assert rows[0].passed is True
    assert physical.calibration_from_db(db, cir) == 1.0, "a swatch calibrated yardage"


def test_a_swatch_off_gauge_fails_and_a_swatch_with_finished_sizes_is_refused():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    base = {"slug": cir.slug, "version": cir.version, "tester_ref": "t", "scope": "swatch",
            "grams_by_color": {"cream": 6.0}, "ball_band_grams": BAND_GRAMS,
            "ball_band_metres": BAND_METRES}
    _run(db, "physical.record", {**base, "swatch_stitches_per_10cm": 16.0,
                                 "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is False
    assert "SAMPLE_GAUGE_DISAGREES" in [f["code"] for f in rows[0].measured["findings"]]
    _run(db, "physical.record", {**base, "swatch_stitches_per_10cm": 12.5,
                                 "swatch_rows_per_10cm": 13.8, "measured_width_cm": 10.0})
    assert len(_rows(db)) == 1, "a swatch with a 'finished' size was stored"


def test_a_sample_with_no_scope_and_no_measurement_is_refused_not_guessed():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    inputs = _inputs(cir)
    for k in ("measured_width_cm", "measured_height_cm"):
        inputs.pop(k)
    _run(db, "physical.record", inputs)
    assert _rows(db) == []


# ---- 2. what is priced is what the intake accepts -----------------------------------------

def test_the_priced_partial_offer_is_a_make_the_intake_accepts():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    spec = rm.owner_action_spec(slug=cir.slug, version=cir.version, content_hash="ab" * 32,
                                required=rm.PARTIAL_PHYSICAL, effective_class="B",
                                make_hours=2.15, yarn_metres=52.1)
    assert spec["max_cost_cad"] == 32.40
    offer = spec["intake"]
    assert offer["scope"] == "swatch" and offer["evidence_class"] == rm.PARTIAL_PHYSICAL
    assert "finished measurements" not in spec["action"].split("scope swatch")[1].split(
        "no finished")[0], spec["action"]
    values = {"swatch_stitches_per_10cm": cir.gauge.stitches_per_10cm,
              "swatch_rows_per_10cm": cir.gauge.rows_per_10cm, "hook_mm": 5.0,
              "instructions_followed": True}
    payload = {"slug": cir.slug, "version": cir.version, "tester_ref": "t",
               "scope": offer["scope"], "grams_by_color": {"cream": 6.0},
               "ball_band_grams": BAND_GRAMS, "ball_band_metres": BAND_METRES,
               **{f: values[f] for f in offer["fields"]}}
    job = _run(db, "physical.record", payload)
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is True, job.last_error
    assert rm.satisfies(rows[0].measured["evidence_class"], rm.PARTIAL_PHYSICAL)
    full = rm.owner_action_spec(slug=cir.slug, version=cir.version, content_hash="ab" * 32,
                                required=rm.FULL_PHYSICAL_MAKE, effective_class="C",
                                make_hours=2.15, yarn_metres=52.1)
    assert full["intake"]["scope"] == "full_make"
    assert "lies flat" in full["action"] and "pieces" in full["action"]


# ---- 3. flatness, shape and recorded problems: PARTIAL, to the owner, never a pass --------

def _owner_reviews(db) -> list[OwnerAction]:
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("physical_review:%"))))
        for r in rows:
            s.expunge(r)
        return rows


def test_a_coaster_that_does_not_lie_flat_goes_to_the_owner_as_partial():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, 1.0, scope="full_make",
                                              made={"coaster": 4}, lies_flat=False,
                                              problem_notes="coaster 3 cups"))
    rows = _rows(db)
    assert len(rows) == 1, job.last_error
    assert rows[0].passed is False and rows[0].measured["outcome"] == physical.PARTIAL
    assert (job.outputs or {})["owner_review"], job.outputs
    reviews = _owner_reviews(db)
    assert len(reviews) == 1 and "PARTIAL" in reviews[0].action and not reviews[0].done
    from brambleloop.gates.first_customer import physical_binding

    assert physical_binding(db, cir)["passed"] is False, "a PARTIAL bound as evidence"
    assert physical.calibration_from_db(db, cir) == 1.0


def test_a_basket_that_collapses_or_a_recorded_problem_never_auto_passes():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=False))
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        problem_notes="round 14 unclear"))
    # A base that rocks is a problem even though a vessel's required answer is "holds shape".
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        lies_flat=False))
    rows = _rows(db)
    assert [r.passed for r in rows] == [False] * 3, [r.measured for r in rows]
    assert [r.measured["outcome"] for r in rows] == [physical.PARTIAL] * 3
    assert len(_owner_reviews(db)) == 3


def test_a_made_piece_without_its_shape_answer_is_refused():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", made={"coaster": 4}))
    assert _rows(db) == []


# ---- 4. a size outside tolerance halts publication of that release ------------------------

def _basket_medium():
    # As in test_physical: the generator's medium basket declares a weight its gauge cannot
    # make, so it is declared at the weight that holds its gauge for certification.
    from brambleloop.products.vessels import build_basket

    cir = build_basket("medium")
    for m in cir.materials:
        m.name, m.yarn_weight = "sport cotton", "sport"
    return cir


def test_a_size_mismatch_halts_that_release_and_only_a_corrected_content_lifts_it():
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              measured_width_cm=40.0))
    assert (job.outputs or {})["publication_halted"], job.outputs
    tracker = IncidentTracker(db)
    assert tracker.publication_halted(cir.slug)
    # The same content stays halted at certification.
    again = _certify(db, cir)
    assert again.get("halted_by_incident") is True, again
    # A corrected content (a new release) may be certified; it supersedes the halted one.
    fixed = _basket_medium()
    fixed.version = "1.3.0"
    fixed.title = fixed.title + " (revised)"
    result = _certify(db, fixed)
    assert not result.get("halted_by_incident") and result.get("granted"), result
    assert not tracker.publication_halted(fixed.slug), "superseded halt left open"
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature.like("physical-size:%")))
        assert inc.resolved and inc.detail.get("fixed_in_version") == "1.3.0", inc.detail
    # The corrected content carries none of the old sample: it needs its own.
    from brambleloop.gates.first_customer import physical_binding

    assert physical_binding(db, fixed)["passed"] is False


# ---- 5. the kits ---------------------------------------------------------------------------

def _sheet_text(path: Path) -> str:
    import pypdf

    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(
        path.read_bytes())).pages)


def test_both_kits_say_reweigh_after_the_swatch_and_print_every_step_whole():
    from brambleloop.quality import tester_kit

    for key, spec in tester_kit.KITS.items():
        steps = spec["protocol"]
        assert any("RE-WEIGH" in s for s in steps), key
        kit = spec["kit"]
        sheet = KIT_DIR / f"{kit['slug']}-{kit['version']}-RECORD-SHEET.pdf"
        text = " ".join(_sheet_text(sheet).split())
        for i, step in enumerate(steps, start=1):
            assert " ".join(f"{i}. {step}".split()) in text, (key, i, step)
        assert "covers exactly one size" in text


def test_the_basket_kit_asks_for_the_unedited_hero_and_carries_no_nursery_wording():
    from brambleloop.quality import tester_kit

    spec = tester_kit.KITS["basket_small"]
    text = " ".join(_sheet_text(KIT_DIR / "market-basket-small-1.2.0-RECORD-SHEET.pdf").split())
    manifest = (KIT_DIR / spec["manifest"]).read_text()
    for needle in ("UNEDITED", "listing's first photo", "sit flat", "hold its shape"):
        assert needle in text, needle
    for word in ("nursery", "baby", "infant", "child"):
        assert word not in text.lower() and word not in manifest.lower(), word
    assert {a for _k, _l, a in spec["fields"]} >= {"lies_flat", "holds_shape", "problem_notes"}


def test_both_kits_rebuild_byte_identical_from_the_one_builder():
    from brambleloop.quality import tester_kit

    for key, spec in tester_kit.KITS.items():
        committed = json.loads((KIT_DIR / spec["manifest"]).read_text())
        with tempfile.TemporaryDirectory() as tmp:
            built = tester_kit.build(Path(tmp), key)
            assert json.loads(json.dumps(built, default=str)) == committed, key
            for name, digest in built["files"].items():
                import hashlib

                assert hashlib.sha256((KIT_DIR / name).read_bytes()).hexdigest() == digest


def test_a_filled_coaster_sheet_reaches_the_intake_and_routes_not_flat_to_the_owner():
    from brambleloop.quality import tester_kit

    db = _db()
    cir = _coasters()
    _certify(db, cir)
    version, chash = tester_kit.content_hash("hexagon_coasters")
    twin = build_twin(cir, compile_cir(cir))
    g = _grams(cir)
    sheet = {"tester_ref": "t1", "made_coaster": "4", "grams_cream": g["cream"],
             "grams_wine": g["wine"], "ball_band_grams": BAND_GRAMS,
             "ball_band_metres": BAND_METRES, "hook_mm": "5", "swatch_sts": "14.5",
             "swatch_rows": "16", "width_cm": twin.width_cm, "height_cm": twin.height_cm,
             "lies_flat": "no", "followed": "yes", "problems": "coaster 2 ruffles"}
    payload = tester_kit.intake_payload(sheet, content_hash=chash, key="hexagon_coasters")
    assert payload["made"] == {"coaster": 4} and payload["lies_flat"] is False
    assert payload["size"] == "set_of_four" and payload["problem_notes"]
    job = _run(db, "physical.record", payload)
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].measured["outcome"] == physical.PARTIAL, job.last_error
    sheet["lies_flat"], sheet["problems"] = "yes", ""
    _run(db, "physical.record", tester_kit.intake_payload(
        sheet, content_hash=chash, key="hexagon_coasters"))
    assert _rows(db)[-1].passed is True and _rows(db)[-1].measured["outcome"] == physical.PASS


# ---- 6. a sample covers exactly one size ---------------------------------------------------

def test_a_sample_proves_one_size_and_the_first_customer_evidence_says_which():
    from brambleloop.gates.first_customer import (
        PASS, check_gauge_and_size_claims, physical_binding,
    )

    db = _db()
    small = _basket()
    _certify(db, small)
    job = _run(db, "physical.record", _inputs(small, scope="full_make", holds_shape=True,
                                              size="small"))
    assert (job.outputs or {})["covers_size"]["size"] == "small", job.outputs
    cov = physical.size_coverage(db, small)
    assert cov["listing"] == "nursery-nesting-baskets"
    assert cov["proven"] == ["small"] and cov["unproven"] == ["medium", "large"], cov
    binding = physical_binding(db, small)
    check = check_gauge_and_size_claims(small, build_twin(small, compile_cir(small)), binding)
    assert check.state == PASS and "not proven: ['medium', 'large']" in check.detail, check.detail
    medium = physical_binding(db, _basket("basket_medium"))
    assert medium["passed"] is False and medium["size_coverage"]["proven"] == ["small"]


def test_a_sample_claiming_another_or_several_sizes_is_refused():
    db = _db()
    small = _basket()
    _certify(db, small)
    for extra in ({"size": "medium"}, {"size": "small,medium"},
                  {"compatible_variants": [{"slug": "market-basket-medium",
                                            "version": "1.2.0"}]},
                  {"sizes": ["small", "medium"]}):
        _run(db, "physical.record", _inputs(small, scope="full_make", holds_shape=True,
                                            **extra))
    assert _rows(db) == [], [r.measured.get("covers_size") for r in _rows(db)]


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(exc)[:300])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
