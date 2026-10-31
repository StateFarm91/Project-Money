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
    _agree_testers(db)
    return db


AGREED_TESTERS = ("tester-1", "tester-2", "tester-3", "t", "t1", "t2")


def _agree_testers(db, refs=AGREED_TESTERS) -> None:
    """SECREVIEW R12: a sample counts only from a tester with a recorded, independent,
    qualified agreement, so the fixtures' testers agree first, through the one intake."""
    from brambleloop.quality import tester_programme as tp

    for ref in refs:
        tp.record_agreement(db, handle_ref=ref, specialties=["home_decor"],
                            express_consent=True, consent_source="test fixture",
                            relationship="none",
                            qualification="https://www.ravelry.com/projects/tester/hexagon-basket")


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
    """A sample that agrees with the twin. It answers "followed exactly?" (SECREVIEW F2/F4:
    the intake refuses an unanswered record) and measures every piece of a component made more
    than once in its own checked field (F6)."""
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    out = {"slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
           "grams_by_color": _grams(cir, fraction), "ball_band_grams": BAND_GRAMS,
           "ball_band_metres": BAND_METRES, "measured_width_cm": twin.width_cm,
           "measured_height_cm": twin.height_cm, "instructions_followed": True}
    made = extra.get("made") or {c.name: int(c.make or 1) for c in cir.components}
    pieces = []
    for comp, count in made.items():
        if count > 1:
            t = build_twin(cir, result, component=comp)
            pieces += [{"component": comp, "width_cm": t.width_cm, "height_cm": t.height_cm}
                       for _ in range(int(count))]
    if pieces:
        out["piece_measurements"] = pieces
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
    assert whole, "the twin estimates no yarn: the per-colour check below would prove nothing"
    for colour in whole:
        assert abs(est[colour] * 4 - whole[colour]) <= 0.4, (est, whole)
    report = physical.SampleReport(
        product_slug=cir.slug, version=cir.version, tester_ref="t",
        grams_by_color=_grams(cir, 0.25), ball_band=physical.BallBand(BAND_GRAMS, BAND_METRES),
        scope="component", made={"coaster": 1}, measured_width_cm=twin.width_cm,
        lies_flat=True, instructions_followed=True)
    a = physical.assess(report, twin, cir, result)
    assert a.outcome == physical.PASS and abs(a.factor - 1.0) < 0.02, a.to_dict()


def test_a_swatch_is_gauge_evidence_only_and_never_yardage():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    job = _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "tester-1", "scope": "swatch",
        "instructions_followed": True,
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
            "instructions_followed": True,
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


def test_a_size_mismatch_halts_that_design_and_only_a_proven_correction_lifts_it():
    """SECREVIEW F1: the halt is bound to the design, not the version string.

    - the same design stays halted, under its own version and under a relabel;
    - a different design may certify, but certifying lifts nothing;
    - only a passed full make of the different design, measuring the stated size, resolves it.
    """
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              measured_width_cm=40.0))
    assert (job.outputs or {})["publication_halted"], job.outputs
    tracker = IncidentTracker(db)
    assert tracker.publication_halted(cir.slug)
    assert _certify(db, cir).get("halted_by_incident") is True
    relabel = _basket_medium()
    relabel.version = "1.3.0"                      # the same design under another version
    assert _certify(db, relabel).get("halted_by_incident") is True, "a relabel certified"
    assert tracker.publication_halted(cir.slug), "a relabel lifted the halt"

    # SECREVIEW R1: cosmetic edits are the same design -- none certifies past the halt.
    for edit in (lambda c: setattr(c, "title", c.title + " (revised)"),
                 lambda c: setattr(c, "title", c.title + " "),
                 lambda c: setattr(c, "designer_notes", (c.designer_notes or "") + " Enjoy!"),
                 lambda c: c.materials.reverse()):
        same = _basket_medium()
        same.version = "1.3.0"
        edit(same)
        assert _certify(db, same).get("halted_by_incident") is True, "a cosmetic edit certified"
    assert tracker.publication_halted(cir.slug)

    fixed = _geometry_changed_medium("1.3.1")       # a genuinely different made object
    result = _certify(db, fixed)
    assert not result.get("halted_by_incident") and result.get("granted"), result
    assert tracker.publication_halted(fixed.slug), "certification alone lifted the halt"
    from brambleloop.gates.first_customer import physical_binding

    assert physical_binding(db, fixed)["passed"] is False, "the old sample bound to the fix"
    # A swatch of the fix proves no size and lifts nothing.
    _run(db, "physical.record", {
        "slug": fixed.slug, "version": fixed.version, "tester_ref": "t2", "scope": "swatch",
        "instructions_followed": True, "grams_by_color": {"cream": 6.0},
        "ball_band_grams": BAND_GRAMS, "ball_band_metres": BAND_METRES,
        "swatch_stitches_per_10cm": fixed.gauge.stitches_per_10cm,
        "swatch_rows_per_10cm": fixed.gauge.rows_per_10cm})
    assert tracker.publication_halted(fixed.slug)
    # Its own passed full make at the stated size does.
    job = _run(db, "physical.record", _inputs(fixed, scope="full_make", holds_shape=True))
    assert (job.outputs or {}).get("size_halts_lifted"), job.outputs
    assert not tracker.publication_halted(fixed.slug)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature.like("physical-size:%")))
        assert inc.resolved and inc.detail.get("fixed_in_version") == "1.3.1", inc.detail


def _geometry_changed_medium(version: str):
    """The medium basket with one more straight wall round: a different made object."""
    import copy

    c = _basket_medium()
    c.version = version
    rows = c.components[0].rows
    extra = copy.deepcopy(rows[-1])
    extra.index = rows[-1].index + 1
    rows.append(extra)
    return c


def test_the_design_digest_is_geometry_only():
    """SECREVIEW R1: labels, notes, whitespace and list order are not the design; rows are."""
    base = physical.design_digest(_basket_medium())
    assert base
    for edit in (lambda c: setattr(c, "version", "9.9.9"),
                 lambda c: setattr(c, "title", c.title + " (revised)"),
                 lambda c: setattr(c, "title", c.title + " "),
                 lambda c: setattr(c, "designer_notes", (c.designer_notes or "") + " x"),
                 lambda c: c.materials.reverse(),
                 lambda c: setattr(c.components[0], "name", "bowl")):
        c = _basket_medium()
        edit(c)
        assert physical.design_digest(c) == base
    assert physical.design_digest(_geometry_changed_medium("1.2.0")) != base
    gauge = _basket_medium()
    gauge.gauge.stitches_per_10cm += 1.0
    assert physical.design_digest(gauge) != base


def _expanded(ops: list) -> list:
    out = []
    for o in ops:
        if "times" in o:
            for _ in range(int(o["times"])):
                out += _expanded(o["ops"])
        else:
            out += [{**o, "count": 1} for _ in range(int(o["count"]))]
    return out


def test_the_design_digest_reads_compiled_stitches_not_notation():
    """SECREVIEW R5: notation, case and number type are not the design; stitches are."""
    from brambleloop.cir.model import CIR

    base = physical.design_digest(_basket_medium())
    body = _basket_medium().to_dict()
    assert any("times" in o for c in body["components"] for r in c["rows"]
               for o in r["ops"]), "no repeat in the fixture: the expansion proves nothing"
    for comp in body["components"]:
        for row in comp["rows"]:
            row["ops"] = _expanded(row["ops"])
    assert physical.design_digest(CIR.from_dict(body)) == base, "notation moved the digest"
    body = _basket_medium().to_dict()
    body["gauge"]["yarn_weight"] = body["gauge"]["yarn_weight"].upper()
    for m in body["materials"]:
        m["yarn_weight"] = m["yarn_weight"].title()
    assert physical.design_digest(CIR.from_dict(body)) == base, "case moved the digest"
    a, b = _basket_medium().to_dict(), _basket_medium().to_dict()
    a["gauge"]["stitches_per_10cm"], b["gauge"]["stitches_per_10cm"] = 13, 13.0
    a["gauge"]["hook_mm"], b["gauge"]["hook_mm"] = 5, 5.0
    assert physical.design_digest(CIR.from_dict(a)) == physical.design_digest(
        CIR.from_dict(b)), "int vs float moved the digest"
    # The reverse: any change to the compiled stitches moves it.
    for mutate in (lambda d: d["components"][0]["rows"][-1]["ops"][0].update(loop="back"),
                   lambda d: d["components"][0]["rows"][-1]["ops"][0].update(stitch="hdc"),
                   lambda d: d["components"][0].update(make=2)):
        d = _basket_medium().to_dict()
        mutate(d)
        try:
            moved = physical.design_digest(CIR.from_dict(d))
        except Exception:  # noqa: BLE001 - an uncompilable mutation is also not "the same"
            moved = None
        assert moved != base, "a compiled-stitch change kept the digest"


def test_a_passing_sample_of_the_halted_design_never_lifts_its_own_halt():
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        measured_width_cm=40.0))
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              tester_ref="tester-2"))
    assert (job.outputs or {}).get("size_halts_lifted") == [], job.outputs
    assert IncidentTracker(db).publication_halted(cir.slug)
    # SECREVIEW R1: two makes of one geometry disagree, so the owner decides.
    assert str((job.outputs or {}).get("owner_review") or "").startswith(
        "physical_size_conflict:"), job.outputs
    # ...and a retitle of the same geometry is still the same design.
    retitled = _basket_medium()
    retitled.version = "1.3.0"
    retitled.title += " (revised)"
    assert _certify(db, retitled).get("halted_by_incident") is True
    job = _run(db, "physical.record", _inputs(retitled, scope="full_make", holds_shape=True,
                                              tester_ref="tester-3"))
    assert IncidentTracker(db).publication_halted(cir.slug), job.outputs


def test_a_piece_height_that_is_not_a_number_is_refused():
    """SECREVIEW R3: a given height is checked like the width, never skipped."""
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    good = _inputs(cir, scope="full_make", made={"coaster": 4}, lies_flat=True)
    for bad in ("8.3", -1, True):
        pieces = [dict(p) for p in good["piece_measurements"]]
        pieces[1]["height_cm"] = bad
        _run(db, "physical.record", dict(good, piece_measurements=pieces))
    assert _rows(db) == [], [r.measured.get("piece_measurements") for r in _rows(db)]


def test_followed_exactly_must_be_a_real_yes_or_no():
    """SECREVIEW F2/F4: "no" is no; blank, missing and unparseable answers are refused."""
    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        instructions_followed="no"))
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is False
    assert "SAMPLE_DEVIATED" in [f["code"] for f in rows[0].measured["findings"]]
    for bad in ("", None, "0", "nope", 1, "false-ish"):
        inputs = _inputs(cir, scope="full_make", holds_shape=True)
        if bad is None:
            inputs.pop("instructions_followed")
        else:
            inputs["instructions_followed"] = bad
        _run(db, "physical.record", inputs)
    assert len(_rows(db)) == 1, [r.measured.get("findings") for r in _rows(db)]
    from brambleloop.quality import tester_kit

    _, chash = tester_kit.content_hash("basket_small")
    for answer in ("", None):
        sheet = {"tester_ref": "t", "made_basket": "1", "followed": answer}
        assert "instructions_followed" not in tester_kit.intake_payload(
            sheet, content_hash=chash, key="basket_small")
    try:
        tester_kit.intake_payload({"tester_ref": "t", "followed": "nah"}, content_hash=chash)
    except ValueError:
        pass
    else:
        raise AssertionError("an unparseable sheet answer was guessed")


def test_a_swatch_never_proves_a_size_or_meets_the_first_customer_floor():
    """SECREVIEW F3: a swatch is gauge evidence only."""
    from brambleloop.gates.first_customer import (
        UNRESOLVED, check_gauge_and_size_claims, physical_binding,
    )

    for cir in (_coasters(), _basket()):
        db = _db()
        _certify(db, cir)
        job = _run(db, "physical.record", {
            "slug": cir.slug, "version": cir.version, "tester_ref": "t", "scope": "swatch",
            "instructions_followed": True, "grams_by_color": {"cream": 3.0},
            "ball_band_grams": BAND_GRAMS, "ball_band_metres": BAND_METRES,
            "swatch_stitches_per_10cm": cir.gauge.stitches_per_10cm,
            "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
        rows = _rows(db)
        assert rows and rows[0].passed is True, job.last_error
        assert rows[0].measured["size_proof"] is False
        binding = physical_binding(db, cir)
        assert binding["passed"] is True and binding["first_customer"]["met"] is False
        assert binding["size_coverage"]["proven"] == [], binding["size_coverage"]
        check = check_gauge_and_size_claims(cir, build_twin(cir, compile_cir(cir)), binding)
        assert check.state == UNRESOLVED and "gauge evidence" in check.detail, check.detail


def test_a_problem_written_in_notes_goes_to_the_owner():
    """SECREVIEW F5: any free-text note routes the sample to owner review."""
    db = _db()
    cir = _basket()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              notes="round 9 is wrong, ripped back twice"))
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is False, job.last_error
    assert rows[0].measured["outcome"] == physical.PARTIAL
    assert (job.outputs or {}).get("owner_review")


def test_every_coaster_is_measured_in_a_checked_field():
    """SECREVIEW F6: four coasters, four compared sizes; one wrong coaster fails the set."""
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    good = _inputs(cir, scope="full_make", made={"coaster": 4}, lies_flat=True)
    three = dict(good, piece_measurements=good["piece_measurements"][:3])
    _run(db, "physical.record", three)
    assert _rows(db) == [], "a set of four was accepted with three measured"
    wrong = [dict(p) for p in good["piece_measurements"]]
    wrong[2]["width_cm"] = wrong[2]["width_cm"] * 1.3
    _run(db, "physical.record", dict(good, piece_measurements=wrong))
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is False and rows[0].measured["size_agrees"] is False
    assert any("coaster 3" in f["message"] for f in rows[0].measured["findings"])
    _run(db, "physical.record", good)
    assert _rows(db)[-1].passed is True and _rows(db)[-1].measured["size_proof"] is True


def test_parts_made_says_whole_but_a_component_stays_partial():
    """SECREVIEW F7: the docstring and the behaviour agree."""
    cir = _coasters()
    scope, made, whole = physical.parts_made(cir, "component", {"coaster": 4})
    assert (scope, made, whole) == ("component", {"coaster": 4}, True)
    assert rm.scope_to_class("component", measured_finished_size=True) == rm.PARTIAL_PHYSICAL
    assert "always `partial_physical`" in physical.parts_made.__doc__


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


def test_the_basket_records_the_construction_review_observations():
    """CONSTRUCTION_REVIEW_basket_small_1.2.0 §5: wall-height method, base edge, rim corners,
    rim span and an optional round-11 height are structured fields, typed at intake."""
    from brambleloop.quality import tester_kit

    spec = tester_kit.KITS["basket_small"]
    apis = {a for _k, _l, a in spec["fields"]}
    assert apis >= {"inside_depth_cm", "base_edge", "wall_vertical_from_rnd", "corners_at_rim",
                    "rim_across_points_cm", "rnd11_height_cm"}, apis
    text = " ".join(_sheet_text(KIT_DIR / "market-basket-small-1.2.0-RECORD-SHEET.pdf").split())
    for needle in ("OUTSIDE: from the flat table to the top of the rim, at the middle of a flat "
                   "side", "crisp fold, or a rounded curve", "corners still visible at the rim"):
        assert needle in text, needle
    _, chash = tester_kit.content_hash("basket_small")
    payload = tester_kit.intake_payload(
        {"tester_ref": "t", "made_basket": "1", "base_edge": "rounded curve",
         "wall_vertical_from_rnd": "13", "corners_at_rim": "no", "rim_points": "15.2",
         "followed": "yes"}, content_hash=chash, key="basket_small")
    assert payload["base_edge"] == "rounded" and payload["wall_vertical_from_rnd"] == 13
    assert payload["corners_at_rim"] is False and payload["rim_across_points_cm"] == 15.2

    db = _db()
    cir = _basket()
    _certify(db, cir)
    obs = {"base_edge": "rounded", "wall_vertical_from_rnd": 13, "corners_at_rim": "no",
           "rim_across_points_cm": 15.2, "inside_depth_cm": 7.9, "rnd11_height_cm": 1.4}
    for bad in ({"base_edge": "rounded"}, {"base_edge": "wobbly"},
                {"rim_across_points_cm": "15"}, {"corners_at_rim": "maybe"},
                {"wall_vertical_from_rnd": 12.5}):
        _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True, **bad))
    assert _rows(db) == [], [r.measured.get("observations") for r in _rows(db)]
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True, **obs))
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is True, rows and rows[0].measured["findings"]
    stored = rows[0].measured["observations"]
    assert stored["base_edge"] == "rounded" and stored["corners_at_rim"] is False
    assert stored["wall_height_method"] == physical.WALL_HEIGHT_METHOD


def test_tester_terms_one_independent_qualified_tester_and_an_all_inclusive_ceiling():
    from brambleloop.quality import tester_kit, tester_programme as tp

    for key, spec in tester_kit.KITS.items():
        kit = spec["kit"]
        call = (KIT_DIR / spec["outreach"]).read_text()
        assert "ONE tester" in call and "1-3" not in call, key
        for needle in ("not the shop's owner", "household or family",
                       "no financial interest", "relationship", "joined rounds",
                       "fee-free transfer", f"CA${kit['tester_receives_cad']:.2f}"):
            assert needle in call, (key, needle)
        assert kit["testers"] == 1
        # The ceiling is all-inclusive and covers what the tester receives.
        assert kit["tester_receives_cad"] <= kit["max_cost_cad"], key
    basket = tester_kit.KIT
    assert round(2.795 * 20.0, 2) + 2 * 5.00 == basket["tester_receives_cad"] == 65.90
    assert basket["max_cost_cad"] == 66.00
    assert tp.outreach_markdown() == (KIT_DIR / "OUTREACH.md").read_text()
    fields = {f for f, _l, _r in tp.INTAKE_FIELDS}
    assert {"relationship", "qualification"} <= fields
    db = _db()
    # SECREVIEW R6: an allow-list. Every one of these is refused, including the relatives and
    # free text the old keyword denylist let through, and an agreement with no declaration.
    refused = ("I am the owner's sister", "my husband", "his wife", "my mom", "my brother",
               "my boyfriend", "my daughter", "cousin", "close friend", "coworker",
               "I live with Jacob", "contractor", "employee", "I hold shares",
               "partner", "household member", "", None)
    for rel in refused:
        try:
            tp.record_agreement(db, handle_ref="t", specialties=["home_decor"],
                                express_consent=True, consent_source="form",
                                relationship=rel, qualification="https://www.ravelry.com/projects/tester/hexagon-basket")
        except tp.TesterRefused:
            continue
        raise AssertionError(f"accepted a tester who is not independent: {rel!r}")
    for qual in ("", "   ", None):
        try:
            tp.record_agreement(db, handle_ref="t", specialties=["home_decor"],
                                express_consent=True, consent_source="form",
                                relationship="none", qualification=qual)
        except tp.TesterRefused:
            continue
        raise AssertionError(f"accepted a tester with no qualification evidence: {qual!r}")
    try:
        tp.record_agreement(db, handle_ref="t", specialties=["home_decor"],
                            express_consent=True, consent_source="form")
    except tp.TesterRefused:
        pass
    else:
        raise AssertionError("an agreement without the tester terms was recorded")
    for n, rel in enumerate(("none", "None.", "acquaintance (declared)",
                             "Acquaintance (declared)")):
        out = tp.record_agreement(db, handle_ref=f"ok{n}", specialties=["home_decor"],
                                  express_consent=True, consent_source="form",
                                  relationship=rel, qualification="https://www.ravelry.com/projects/tester/hexagon-basket")
        assert out["permission"]["independence"]["relationship"] in (
            "none", "acquaintance (declared)"), out


def test_a_non_finite_measurement_is_refused():
    """SECREVIEW R9: NaN compares False with every tolerance, so a NaN width or gauge would
    otherwise "agree" with any stated size. Every measured number must be finite."""
    nan, inf = float("nan"), float("inf")
    db = _db()
    cir = _basket()
    _certify(db, cir)
    for bad in ({"measured_width_cm": nan}, {"measured_flats_cm": inf},
                {"rim_across_points_cm": nan}, {"hours": nan},
                {"grams_by_color": {"cream": nan, "wine": 6.0}}):
        _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True, **bad))
    _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "t", "scope": "swatch",
        "instructions_followed": True, "grams_by_color": {"cream": 6.0},
        "ball_band_grams": BAND_GRAMS, "ball_band_metres": BAND_METRES,
        "swatch_stitches_per_10cm": nan, "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
    assert _rows(db) == [], [r.measured.get("findings") for r in _rows(db)]


def test_one_cost_figure_per_kit_everywhere_it_is_stated():
    """SECREVIEW R7: the owner card, the gate-clearance card, the approval doc and the tester
    call state one figure, and that figure covers what the call promises."""
    from brambleloop.build2 import gate_clearance
    from brambleloop.ops import owner_queue
    from brambleloop.quality import tester_kit

    kit = tester_kit.KIT
    assert kit["max_cost_cad"] == 66.00 and kit["tester_receives_cad"] == 65.90
    card = next(d for d in owner_queue.DECISIONS if d["id"] == "tester_outreach")
    assert card["max_cost_cad"] == kit["max_cost_cad"], card
    assert "CA$66.00" in card["decision"] and "59.65" not in card["decision"]
    assert gate_clearance.card_fields(None, "physical_proof", {})["max_cost_cad"] == \
        kit["max_cost_cad"]
    doc = (KIT_DIR / "BASKET_KIT_FOR_OWNER_APPROVAL.md").read_text()
    action = doc.split("## 9. OWNER ACTION REQUIRED")[1]
    assert "CA$66.00" in action and "59.65" not in action
    assert "CA$65.90" in (KIT_DIR / "OUTREACH.md").read_text()
    manifest = json.loads((KIT_DIR / "KIT_MANIFEST.json").read_text())
    assert manifest["max_cost_cad"] == kit["max_cost_cad"]
    coaster = tester_kit.COASTER_KIT
    assert coaster["max_cost_cad"] == 100.00 and coaster["tester_receives_cad"] == 99.96
    assert json.loads((KIT_DIR / "KIT_MANIFEST_hexagon-coaster-set.json").read_text())[
        "max_cost_cad"] == 100.00


def test_a_hold_rename_is_the_same_design_and_into_is_geometry():
    """SECREVIEW 3e542a1 R11/R14: hold names are labels; which row a row is worked into is
    geometry."""
    from brambleloop.cir.benchmarks import cardigan
    from brambleloop.cir.compiler import compile_cir as _compile
    from brambleloop.cir.model import CIR, Component, Hold, Op, Row

    def held(name):
        a = Component(name="panel", construction="flat", foundation=20,
                      foundation_kind="chain",
                      rows=[Row(index=1, ops=[Op("sc", 20)], declared_count=20),
                            Row(index=2, ops=[Op("sc", 14)], declared_count=14, skips=6)],
                      holds=[Hold(name=name, at_row=1, count=6, from_stitch=14)])
        b = Component(name="strap", construction="flat", foundation=0, foundation_kind="none",
                      rows=[Row(index=1, ops=[Op("sc", 6)], declared_count=6)], resumes=name)
        c = CIR.from_dict(cardigan("XS").to_dict())
        c.components, c.assembly = [a, b], []
        return c

    # SECREVIEW 81b3e45 R22/R23 interim: a design with holds has no design digest (None),
    # so neither a rename nor a real change can scope or lift a size halt -- it is
    # product-wide. The canonical hold encoding stays in `design_geometry` for the TODO.
    one, two = held("side"), held("other_hold")
    assert _compile(one).ok and _compile(two).ok
    assert physical.design_digest(one, _compile(one)) is None
    assert physical.design_digest(two, _compile(two)) is None
    g1 = physical.design_geometry(one, _compile(one))
    assert g1 == physical.design_geometry(two, _compile(two)), "a hold rename moved geometry"

    base = _basket_medium()
    rows = base.components[0].rows
    same_count = [r for r in rows if r.index >= 13]
    assert len(same_count) > 3, "no straight wall rounds: the into check proves nothing"
    changed = _basket_medium()
    target = next(r for r in changed.components[0].rows if r.index == 15)
    target.into = 13
    assert compile_cir(changed).ok, "the into fixture no longer compiles"
    assert physical.design_digest(changed) != physical.design_digest(base), \
        "working into another row kept the digest"


def test_designs_with_holds_are_halted_product_wide_until_holds_are_canonical():
    """SECREVIEW 81b3e45 R22/R23, fail-closed interim (TODO(physfix-holds) in
    `quality.physical.design_digest`): full graph canonicalisation of holds is future work.

    - every hold-bearing construction -- including the reviewer's R22 reorders (identical
      holding panels resumed by different straps; a chain of identical joining strips) and
      the R23 pair (a real change the multiset sort mapped onto another design) -- has no
      design digest, so no two of them share one;
    - a size halt raised on such a design is product-wide: it halts every certification of
      the product, whatever its geometry, and no passing make lifts it;
    - a design with no holds is unchanged: it has a digest, and a scoped halt still lets a
      different design certify.
    """
    from brambleloop.cir.benchmarks import cardigan
    from brambleloop.cir.compiler import compile_cir as _compile
    from brambleloop.cir.model import CIR, Component, Hold, Op, Row
    from brambleloop.gates.incidents import IncidentTracker, release_scope
    from brambleloop.ops.incident_lifecycle import open_or_restate

    def panel(name, holds):
        return Component(name=name, construction="flat", foundation=20,
                         foundation_kind="chain",
                         rows=[Row(index=1, ops=[Op("sc", 20)], declared_count=20),
                               Row(index=2, ops=[Op("sc", 8)], declared_count=8, skips=12),
                               Row(index=3, ops=[Op("sc", 8)], declared_count=8)],
                         holds=holds)

    def strap(name, hold, rows=1, holds=None):
        return Component(name=name, construction="flat", foundation=0,
                         foundation_kind="none",
                         rows=[Row(index=i, ops=[Op("sc", 6)], declared_count=6)
                               for i in range(1, rows + 1)], resumes=hold, holds=holds or [])

    def design(comps):
        c = CIR.from_dict(cardigan("XS").to_dict())
        c.components, c.assembly = comps, []
        r = _compile(c)
        assert r.ok, [f.code for f in r.findings if f.is_error]
        return c, r

    H = lambda n, f=8: Hold(name=n, at_row=1, count=6, from_stitch=f)  # noqa: E731
    P = lambda: panel("p", [H("a", 8), H("b", 14)])  # noqa: E731
    constructions = {
        "R18 hold order": [panel("p", [H("b", 14), H("a", 8)]), strap("s1", "a"),
                           strap("s2", "b")],
        "R22 P1": [panel("L", [H("hl")]), panel("R", [H("hr")]), strap("s1", "hl"),
                   strap("s2", "hr", rows=3)],
        "R22 P1 reordered": [panel("R", [H("hr")]), panel("L", [H("hl")]), strap("s1", "hl"),
                             strap("s2", "hr", rows=3)],
        "R22 P2": [panel("p", [H("h0")]), strap("A", "h0", holds=[H("ha", 0)]),
                   strap("B", "ha", holds=[H("hb", 0)]), strap("end", "hb", rows=3)],
        "R22 P2 reordered": [panel("p", [H("h0")]), strap("B", "ha", holds=[H("hb", 0)]),
                             strap("A", "h0", holds=[H("ha", 0)]), strap("end", "hb", rows=3)],
        "R23 D1": [P(), strap("X1", "a", holds=[H("xa", 0)]),
                   strap("X2", "b", holds=[H("xb", 0)]), strap("W", "xa", rows=3),
                   strap("T", "xb")],
        "R23 D2 reordered": [P(), strap("X2", "b", holds=[H("xb", 0)]),
                             strap("X1", "a", holds=[H("xa", 0)]), strap("W", "xb", rows=3),
                             strap("T", "xa")],
    }
    for label, comps in constructions.items():
        c, r = design(comps)
        assert physical.design_digest(c, r) is None, label

    # A halt raised on a hold-bearing design carries no digest, so it is product-wide.
    db = _db()
    slug = "held-design"
    with db.session() as s:
        open_or_restate(s, signature=f"physical-size:{slug}:x", severity="P1",
                        product_slug=slug, halts_publication=True, summary="size",
                        detail={"release_scope": {"slug": slug, "version": "1.0.0",
                                                  "content_hash": "c" * 64,
                                                  "design_digest": None}})
    tracker = IncidentTracker(db)
    inc = tracker.open_incidents(slug)[0]
    assert release_scope(inc) == {}
    for digest in (None, "", "d" * 64, physical.design_digest(_basket_medium())):
        assert tracker.publication_halted(slug, content_hash=digest), digest
    assert tracker.resolve_halts_disproved_by(slug, version="1.1.0", design_digest="d" * 64,
                                              physical_test_id=1) == []
    assert tracker.publication_halted(slug)

    # A design with no holds behaves exactly as before.
    flat = _basket_medium()
    assert not physical._has_holds(flat) and physical.design_digest(flat)
    with db.session() as s:
        open_or_restate(s, signature="physical-size:flat:y", severity="P1",
                        product_slug="flat", halts_publication=True, summary="size",
                        detail={"release_scope": {"slug": "flat", "version": "1.0.0",
                                                  "content_hash": "c" * 64,
                                                  "design_digest": physical.design_digest(flat)}})
    assert tracker.publication_halted("flat", content_hash=physical.design_digest(flat))
    other = _geometry_changed_medium("1.3.1")
    assert not tracker.publication_halted("flat", content_hash=physical.design_digest(other))


def test_an_owner_made_row_is_never_a_tester_in_the_roster_or_plan():
    """SECREVIEW e3fd0b0 R19: owner-made rows are non-evidence and never a tester (F-071)."""
    from brambleloop.quality import testers

    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", {**_inputs(cir, scope="full_make", holds_shape=True),
                                 "tester_ref": "owner", "owner_made": True})
    assert len(_rows(db)) == 1
    roster = testers.from_db(db)
    assert roster["count"] == 0, roster
    planned = testers.plan(db, [{"slug": cir.slug, "risk_class": "B",
                                 "specialty": "home_decor", "make_hours": 2.15,
                                 "needed_by": __import__("datetime").date(2026, 12, 1)}],
                           today=__import__("datetime").date(2026, 11, 1))
    assert all(t.get("ref") != "owner" for t in planned.get("testers") or []), planned
    assert all(a.get("tester") != "owner" for a in planned.get("assignments") or []), planned
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True))
    assert testers.from_db(db)["count"] == 1


def test_an_owner_make_under_a_testers_ref_is_filed_as_owner_and_never_counted():
    """SECREVIEW 81b3e45 R24: owner_made with a real tester's ref is filed under "owner" and
    never counts as that tester's delivered test (`growth_ops.creators_reading`)."""
    from brambleloop.runtime import growth_ops

    db = _db()
    cir = _basket()
    _certify(db, cir)
    for _ in range(2):
        _run(db, "physical.record", {**_inputs(cir, scope="full_make", holds_shape=True),
                                     "tester_ref": "tester-1", "owner_made": True})
    rows = _rows(db)
    assert len(rows) == 2 and {r.tester_ref for r in rows} == {"owner"}, rows
    reading = growth_ops.creators_reading(db)
    refs = [g.get("tester_ref") for g in reading.get("graduations") or []]
    assert "tester-1" not in refs and "owner" not in refs, reading.get("graduations")


def test_a_sample_is_evidence_only_from_an_independent_agreed_tester():
    """SECREVIEW 3e542a1 R12: no default "owner", no unknown or pre-allow-list tester; an
    explicit owner make is stored as non-evidence and satisfies nothing."""
    from brambleloop.build2 import executor
    from brambleloop.core.models import CreatorProfile
    from brambleloop.gates.first_customer import physical_binding

    db = _db()
    cir = _basket()
    _certify(db, cir)
    with db.session() as s:
        s.add(CreatorProfile(ref="legacy-1", specialties=["home_decor"], invited=1,
                             delivered=0, permissions=[{"kind": "tester_agreement",
                                                        "consent_version": "v0"}]))
    for ref in (None, "", "owner", "nobody-agreed", "legacy-1"):
        inputs = _inputs(cir, scope="full_make", holds_shape=True)
        if ref is None:
            inputs.pop("tester_ref")
        else:
            inputs["tester_ref"] = ref
        _run(db, "physical.record", inputs)
    assert _rows(db) == [], [r.tester_ref for r in _rows(db)]
    job = _run(db, "physical.record", {**_inputs(cir, scope="full_make", holds_shape=True),
                                       "tester_ref": "owner", "owner_made": True})
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].passed is False, job.last_error
    m = rows[0].measured
    assert m["owner_made"] is True and m["size_proof"] is False
    assert m["evidence_role"] == "owner_made_non_evidence"
    binding = physical_binding(db, cir)
    assert binding["passed"] is False and binding["first_customer"]["met"] is False
    assert physical.size_coverage(db, cir)["proven"] == []
    assert executor._physical_proof_available(db, None) is False
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True))
    rows = _rows(db)
    assert rows[-1].passed is True and rows[-1].measured["tester_agreement"]["ref"] == "tester-1"
    assert rows[-1].measured["tester_agreement"]["relationship"] == "none"
    assert executor._physical_proof_available(db, None) is True
    fresh = Database(f"sqlite:///{tempfile.mkdtemp()}/legacy.sqlite")
    fresh.create_all()
    with fresh.session() as s:
        s.add(CreatorProfile(ref="legacy-1", specialties=["home_decor"], invited=1,
                             delivered=0, permissions=[{"kind": "tester_agreement"}]))
    assert executor._tester_recruited(fresh, None) is False, "a pre-allow-list agreement counted"


def test_qualification_evidence_must_be_a_link_or_a_stored_photo():
    """SECREVIEW 3e542a1 R16."""
    from brambleloop.quality import tester_programme as tp

    for bad in (".", "yes", "https://x", "http://", "photo:abc", "ravelry.com"):
        assert tp.qualification_problems(bad), bad
    for good in ("https://www.ravelry.com/projects/me/basket", "http://example.org/p.jpg",
                 "photo:" + "a" * 64, "b" * 64):
        assert tp.qualification_problems(good) == [], good


def test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains():
    """SECREVIEW 3e542a1 R13/R15/R17."""
    from brambleloop.launch import readiness
    from brambleloop.quality import tester_kit

    for key, spec in tester_kit.KITS.items():
        kit = spec["kit"]
        real = kit["max_cost_cad"]
        try:
            kit["max_cost_cad"] = round(real * 10, 2)
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    tester_kit.build(Path(tmp), key)
                except ValueError as exc:
                    assert "above the approved" in str(exc), exc
                else:
                    raise AssertionError(f"{key}: a ceiling 10x the approval built")
        finally:
            kit["max_cost_cad"] = real
        assert real == tester_kit.APPROVED_CEILING_CAD[key]
    assert readiness.PHYSICAL_SAMPLE.max_cost_cad == tester_kit.KIT["max_cost_cad"]
    w4 = ROOT / "research/final_build/w4"
    for path in (w4 / "OWNER_ACTIONS.json", w4 / "OWNER_ACTIONS.md",
                 ROOT / "src/brambleloop/app/command_center/snapshots/OWNER_ACTIONS.json",
                 w4 / "GATE_CLEARANCE_BUSINESS.md", w4 / "GATE_CLEARANCE_BUSINESS.json",
                 # SECREVIEW e3fd0b0 R21: the listing package offered the old figure.
                 w4 / "manual_listings/market-basket-small-1.2.0/LISTING_PACKAGE.md"):
        text = path.read_text()
        assert "185.0" not in text and "CA$185" not in text, path
        assert "59.65" not in text, path
    doc = json.loads((w4 / "OWNER_ACTIONS.json").read_text())
    item = next(i for b in doc["batches"] for i in b["items"] if i["id"] == "tester_outreach")
    assert item["max_cost_cad"] == tester_kit.KIT["max_cost_cad"], item["max_cost_cad"]


def test_every_production_tester_intake_passes_the_tester_terms():
    """SECREVIEW R6: no production caller of record_agreement may skip the terms."""
    import ast

    callers = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "record_agreement"):
                kws = {k.arg for k in node.keywords}
                callers.append((str(path.relative_to(ROOT)), kws))
    assert callers, "no production caller found: the scan proved nothing"
    for where, kws in callers:
        assert {"relationship", "qualification"} <= kws, (where, kws)


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
             "swatch_rows": "16", "lies_flat": "no", "followed": "yes",
             "problems": "coaster 2 ruffles",
             **{f"c{n}_{k}": v for n in range(1, 5)
                for k, v in (("points", twin.width_cm), ("flats", twin.height_cm))}}
    payload = tester_kit.intake_payload(sheet, content_hash=chash, key="hexagon_coasters")
    assert payload["made"] == {"coaster": 4} and payload["lies_flat"] is False
    assert payload["size"] == "set_of_four" and payload["problem_notes"]
    assert len(payload["piece_measurements"]) == 4 and payload["instructions_followed"] is True
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
    # D-W4-OWNER-BASKET-IDENTITY (LISTING1, integrated in Batch 4): the small basket is its own
    # one-size listing, `hexagonal-bread-basket`, so its sample leaves nothing of THAT listing
    # unproven. The held three-size family keeps medium and large unproven.
    cov = physical.size_coverage(db, small)
    assert cov["listing"] == "hexagonal-bread-basket", cov
    assert cov["proven"] == ["small"] and cov["unproven"] == [], cov
    binding = physical_binding(db, small)
    check = check_gauge_and_size_claims(small, build_twin(small, compile_cir(small)), binding)
    assert check.state == PASS and "proven sizes of hexagonal-bread-basket: ['small']" in \
        check.detail and "not proven: none" in check.detail, check.detail
    medium = physical_binding(db, _basket("basket_medium"))
    assert medium["passed"] is False, medium
    assert medium["size_coverage"]["listing"] == "nursery-nesting-baskets", medium
    assert medium["size_coverage"]["proven"] == ["small"], medium
    assert medium["size_coverage"]["unproven"] == ["medium", "large"], medium


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
