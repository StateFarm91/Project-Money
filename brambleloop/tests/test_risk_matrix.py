"""Risk-based physical evidence (F-072, F-073, F-078, F-080, F-081, F-086, F-117).

Which products need a tester's hands before a first customer, how much, bound to which text,
and what the owner is asked for when evidence is missing or invalidated. No test here creates
evidence it then believes: every PhysicalTest row is either written by the runtime handler
from a tester-style report or inserted explicitly as a fixture of a *recorded* sample.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction, PhysicalTest  # noqa: E402
from brambleloop.gates import risk_matrix as rm  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401  (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402


def _booted() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/risk.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _drain(db: Database) -> None:
    w = Worker(db, "risk-worker")
    for _ in range(400):
        if not w.run_once():
            break


def _certify(db: Database, cir) -> None:
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()})
    _drain(db)


def _audits(db, artifact: str, actions=("gate.certified", "gate.blocked")) -> list:
    with db.session() as s:
        return [(r.action, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.artifact == artifact,
                                   AuditLog.action.in_(actions)).order_by(AuditLog.id))]


def _class_c_sphere(title: str = "Test Sphere"):
    from brambleloop.creative.prototype import gauge_for
    from tests import fixtures

    cir = fixtures.good_sphere()
    cir.gauge = gauge_for("worsted")
    cir.risk_class = "C"
    cir.title = title
    return cir


def _launch0():
    from brambleloop.products import launch0

    out = {}
    for slug in launch0.LAUNCH0_SLUGS:
        for v in launch0.candidate(slug).variants:
            cir = launch0.cir_for(v.build)
            out[cir.slug] = cir
    return out


def _ev(content_hash: str, cls: str | None, *, ident: int = 1, slug="test-sphere",
        version: str = "1.0.0") -> dict:
    row = {"id": ident, "slug": slug, "version": version, "passed": True,
           "completed_at": datetime.now(timezone.utc), "content_hash": content_hash}
    if cls:
        row["evidence_class"] = cls
    return row


# ---- F-072: distinct evidence classes ---------------------------------------------------

def test_evidence_classes_are_distinct_and_only_a_full_make_contains_a_partial():
    keys = [c.key for c in rm.EVIDENCE_CLASSES]
    assert keys, "the hierarchy is declared"
    assert len(keys) == len(set(keys)) == 6
    for held in keys:  # vacuity-ok: keys asserted non-empty and exactly 6 above
        for need in keys:  # vacuity-ok: same 6 keys, asserted above
            expected = held == need or (held == rm.FULL_PHYSICAL_MAKE
                                        and need == rm.PARTIAL_PHYSICAL)
            assert rm.satisfies(held, need) is expected, (held, need)
    # A benchmark teardown never stands in for our own physical evidence (F-079).
    assert not rm.satisfies(rm.BENCHMARK_TEARDOWN, rm.PARTIAL_PHYSICAL)
    assert not rm.satisfies(rm.PARTIAL_PHYSICAL, rm.FULL_PHYSICAL_MAKE)


def test_a_swatch_never_licenses_a_made_by_a_tester_claim():
    refused = rm.claim_refusals("Made by a tester and swatch tested", {rm.PARTIAL_PHYSICAL})
    assert [r["phrase"] for r in refused] == ["made by a tester"], refused
    assert rm.claim_refusals("made by a tester", {rm.FULL_PHYSICAL_MAKE}) == []
    assert rm.claim_refusals("tech edited", {rm.BENCHMARK_TEARDOWN})


def test_scope_maps_to_a_class_and_a_full_make_must_be_measured():
    assert rm.scope_to_class("swatch", measured_finished_size=False) == rm.PARTIAL_PHYSICAL
    assert rm.scope_to_class("component", measured_finished_size=True) == rm.PARTIAL_PHYSICAL
    assert rm.scope_to_class(None, measured_finished_size=True) == rm.FULL_PHYSICAL_MAKE
    assert rm.scope_to_class(None, measured_finished_size=False) == rm.PARTIAL_PHYSICAL
    for bad in (("full_make", False), ("vibes", True)):
        try:
            rm.scope_to_class(bad[0], measured_finished_size=bad[1])
        except ValueError:
            continue
        raise AssertionError(f"{bad} was accepted")


# ---- F-073: the matrix is derived from the product --------------------------------------

def test_launch0_tiers_are_derived_from_features_not_typed():
    tiers = {slug: rm.matrix_for(cir) for slug, cir in _launch0().items()}
    assert tiers, "Launch-0 has variants"
    assert tiers["hexagon-coaster-set"]["effective"] == "A"
    assert tiers["hexagon-coaster-set"]["required_physical"] is None
    for size in ("small", "medium", "large"):
        t = tiers[f"market-basket-{size}"]
        assert t["effective"] == "B", t
        assert "dimensional_form" in [f["key"] for f in t["features"]]
        assert t["required_physical"] == rm.PARTIAL_PHYSICAL
    blanket = tiers["cloudline-baby-blanket"]
    assert blanket["declared"] == "A" and blanket["derived"] == "B", blanket
    assert blanket["raised_by_matrix"] and blanket["effective"] == "B"
    assert "high_yardage" in [f["key"] for f in blanket["features"]]


def test_a_closed_stuffed_form_is_class_c_and_a_declared_c_is_never_lowered():
    from brambleloop.cir.model import Seam

    sphere = _class_c_sphere()
    sphere.risk_class = "A"
    sphere.assembly = [Seam("whipstitch", "body", "body", stuff_before_closing=True)]
    m = rm.matrix_for(sphere)
    assert m["derived"] == "C" and m["effective"] == "C", m
    assert m["required_physical"] == rm.FULL_PHYSICAL_MAKE

    coaster = _launch0()["hexagon-coaster-set"]
    coaster.risk_class = "C"
    assert rm.matrix_for(coaster)["effective"] == "C"


def test_graded_garments_are_at_least_class_b():
    from brambleloop.products.garments import every_graded_cir

    graded = every_graded_cir()
    assert graded
    for slug, cir in list(graded.items())[:4]:
        m = rm.matrix_for(cir)
        keys = [f["key"] for f in m["features"]]
        assert "graded" in keys and "body_sized_wearable" in keys, (slug, keys)
        assert rm.RANK[m["effective"]] >= rm.RANK["B"], (slug, m)


# ---- F-080: no universal full make --------------------------------------------------------

def test_class_a_meets_the_automated_threshold_without_any_physical_test():
    cert = certify(_launch0()["hexagon-coaster-set"])
    assert cert.granted, cert.blocking_reasons
    matrix = cert.risk_matrix
    assert matrix["effective"] == "A"
    assert matrix["automated_threshold"]["qualifies"], matrix["automated_threshold"]
    assert matrix["requirement"]["met"] and matrix["requirement"]["required"] == "deterministic"
    assert not cert.physical_test_required


def test_class_b_certifies_but_its_live_sale_requirement_is_a_partial_test_not_a_full_make():
    cert = certify(_launch0()["market-basket-medium"])
    assert cert.granted, cert.blocking_reasons
    req = cert.risk_matrix["requirement"]
    assert req["required"] == rm.PARTIAL_PHYSICAL and req["met"] is False, req
    assert not cert.risk_matrix["automated_threshold"]["qualifies"]
    # Bound swatch of this exact content meets it.
    basket = _launch0()["market-basket-medium"]
    ok = certify(basket, physical_evidence=[_ev(cert.content_hash, rm.PARTIAL_PHYSICAL,
                                                slug=basket.slug, version=basket.version)])
    assert ok.risk_matrix["requirement"]["met"], ok.risk_matrix["requirement"]


# ---- F-081 / F-072: Class C needs a full make, a swatch does not stand in -----------------

def test_class_c_is_blocked_on_a_bound_swatch_and_granted_on_a_bound_full_make():
    cir = _class_c_sphere()
    first = certify(cir)
    assert not first.granted
    content = first.content_hash
    swatch = certify(cir, physical_evidence=[_ev(content, rm.PARTIAL_PHYSICAL)])
    assert not swatch.granted
    assert any("PHYSICAL_TEST_REQUIRED" in r and "partial" in r
               for r in swatch.blocking_reasons), swatch.blocking_reasons
    full = certify(cir, physical_evidence=[_ev(content, rm.FULL_PHYSICAL_MAKE)])
    assert full.granted, full.blocking_reasons
    assert full.risk_matrix["requirement"]["met"]


# ---- F-117: twin plausibility -------------------------------------------------------------

def test_a_stated_finished_size_outside_tolerance_of_the_twin_blocks_certification():
    coaster = _launch0()["hexagon-coaster-set"]
    assert certify(coaster).granted
    coaster.finished_size_note = "A hexagon about 14 cm across the points."
    cert = certify(coaster)
    assert not cert.granted
    assert any("TWIN_DIMENSION_IMPLAUSIBLE" in r for r in cert.blocking_reasons)
    assert rm.stated_dimensions("to fit chest 73.5 cm") == []
    assert rm.stated_dimensions("Finished chest 93 cm, length 57 cm") == [93.0, 57.0]


def test_every_launch0_and_garment_size_statement_is_inside_tolerance():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.products.garments import every_graded_cir

    cirs = {**_launch0(), **every_graded_cir()}
    checked = 0
    for slug, cir in cirs.items():
        r = compile_cir(cir)
        twins = {c.name: build_twin(cir, r, component=c.name) for c in cir.components}
        assert rm.plausibility_findings(cir, twins) == [], slug
        checked += bool(rm.stated_dimensions(cir.finished_size_note))
    assert checked >= 10, checked


# ---- F-078: binding through the runtime and the re-test request ---------------------------

def test_runtime_full_make_unblocks_class_c_and_a_material_change_queues_one_retest():
    db = _booted()
    cir = _class_c_sphere()
    _certify(db, cir)
    first = _audits(db, "test-sphere@1.0.0")
    assert first and first[-1][0] == "gate.blocked", first

    # The tester's report through the runtime handler, with a finished measurement.
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    grams = {c: m / 2.1 for c, m in twin.yarn_metres_by_color.items()}
    JobQueue(db).enqueue("quality_director", "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
        "scope": "full_make", "grams_by_color": grams, "ball_band_grams": 100.0,
        # What the tester measured on the finished object. The sphere's twin refuses a flat
        # width, so there is no size comparison; the class still comes from the scope.
        "ball_band_metres": 210.0, "measured_width_cm": 9.5, "measured_height_cm": 6.0})
    _drain(db)
    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest)))
    assert len(rows) == 1, rows
    assert rows[0].measured["evidence_class"] == rm.FULL_PHYSICAL_MAKE, rows[0].measured
    assert rows[0].passed, rows[0].measured

    _certify(db, cir)
    assert _audits(db, "test-sphere@1.0.0")[-1][0] == "gate.certified"
    with db.session() as s:
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("physical_evidence:%"))))

    # A material change under the same version invalidates the evidence: blocked, and one
    # re-test request in the Directive's format -- not two on a second run.
    changed = _class_c_sphere(title="Test Sphere Revised")
    _certify(db, changed)
    _certify(db, changed)
    last = _audits(db, "test-sphere@1.0.0")[-1]
    assert last[0] == "gate.blocked", last
    with db.session() as s:
        actions = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("physical_evidence:test-sphere@1.0.0:%"))))
        assert len(actions) == 1, [a.requirement_key for a in actions]
        a = actions[0]
        assert a.max_cost_cad > 0 and a.minutes == rm.OWNER_MINUTES
        assert "independent tester (not the owner)" in a.action
        assert "Re-test" in a.reason and a.consequence_of_delay and a.blocks
    assert _audits(db, "test-sphere@1.0.0", ("physical.retest_requested",))


def test_runtime_swatch_without_scope_is_recorded_partial_and_does_not_unblock_class_c():
    db = _booted()
    cir = _class_c_sphere()
    _certify(db, cir)
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    JobQueue(db).enqueue("quality_director", "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
        "grams_by_color": {c: m / 2.1 for c, m in twin.yarn_metres_by_color.items()},
        "ball_band_grams": 100.0, "ball_band_metres": 210.0})
    _drain(db)
    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest)))
    assert rows and rows[0].measured["evidence_class"] == rm.PARTIAL_PHYSICAL
    _certify(db, cir)
    last = _audits(db, "test-sphere@1.0.0")[-1]
    assert last[0] == "gate.blocked"
    assert any("partial" in r for r in last[1]["reasons"]), last


# ---- F-086: launch readiness carries the risk-based requirement ---------------------------

def test_readiness_states_the_risk_based_requirement_blocked_on_a_tester_with_a_spend_spec():
    from brambleloop.launch import readiness

    db = _booted()
    _certify(db, _launch0()["market-basket-medium"])
    _certify(db, _launch0()["hexagon-coaster-set"])
    rep = readiness.assess(db, phase="shadow")
    req = next(r for r in rep.requirements if r.key == "risk_based_physical_evidence")
    assert req.ready is False and req.blocked_by == readiness.BLOCKED_TESTER
    assert req.owner_request is None, "the owner is not the tester"
    rows = {r["slug"]: r for r in req.evidence["products"]}
    assert rows, req.evidence
    assert rows["hexagon-coaster-set"]["met"] is True
    basket = rows["market-basket-medium"]
    assert basket["met"] is False and basket["required"] == rm.PARTIAL_PHYSICAL
    spec = basket["owner_action_spec"]
    for k in ("action", "reason", "max_cost_cad", "minutes", "consequence_of_delay", "blocks",
              "cost_basis"):
        assert spec.get(k) not in (None, ""), k
    assert "ESTIMATED" in spec["cost_basis"]
    # The old calibration requirement is kept (the truth objective is not deleted).
    assert any(r.key == "physical_calibration" for r in rep.requirements)
    assert not any("crochet" in (o.action or "").lower() and "owner" not in o.action.lower()
                   for o in rep.owner_requests() if o.key == "physical_calibration")


# ---- first customer: a swatch where a full make is needed is UNRESOLVED -------------------

def test_first_customer_tier_requires_the_class_its_risk_needs():
    m_c = {"effective": "C", "required_physical": rm.FULL_PHYSICAL_MAKE}
    m_a = {"effective": "A", "required_physical": None}
    swatch = {"bound_classes": {1: rm.PARTIAL_PHYSICAL}}
    assert not rm.first_customer_requirement(m_c, swatch)["met"]
    assert rm.first_customer_requirement(m_a, swatch)["met"]
    assert not rm.first_customer_requirement(m_a, {"bound_classes": {}})["met"]

    from brambleloop.gates.first_customer import UNRESOLVED, check_gauge_and_size_claims

    cir = _class_c_sphere()
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    physical = {"passed": True, "bound": [1], "content_hash": "x" * 12,
                "bound_classes": {1: rm.PARTIAL_PHYSICAL},
                "first_customer": rm.first_customer_requirement(m_c, swatch)}
    assert check_gauge_and_size_claims(cir, twin, physical).state == UNRESOLVED


def test_the_parked_sample_request_is_a_tester_spend_approval_not_owner_crochet():
    """F-071 / F-086: the dormant calibration request names an independent tester, prices the
    tester (not just yarn), and routes the result through physical.record as a full make."""
    from brambleloop.launch import readiness as rd

    req = rd.PHYSICAL_SAMPLE
    assert not req.action.lower().startswith("crochet"), req.action
    assert "independent tester (not the owner)" in req.action
    assert "physical.record" in req.action and "full_make" in req.action
    assert req.max_cost_cad > 8 * rm.TESTER_FEE_CAD_PER_HOUR      # the tester is paid
    assert req.minutes == rm.OWNER_MINUTES                         # owner time: approval only


def test_a_full_make_request_is_never_priced_as_a_swatch():
    """The owner approves a ceiling; a Class C spec without a make-time estimate must not
    inherit the swatch's 1.5 hours."""
    kw = dict(slug="x", version="1.0.0", content_hash="ab" * 32, effective_class="C")
    full = rm.owner_action_spec(required=rm.FULL_PHYSICAL_MAKE, make_hours=None,
                                yarn_metres=None, **kw)
    swatch = rm.owner_action_spec(required=rm.PARTIAL_PHYSICAL, make_hours=None,
                                  yarn_metres=None, **kw)
    assert full["tester_hours"] == rm.FULL_MAKE_FALLBACK_HOURS
    assert full["max_cost_cad"] > swatch["max_cost_cad"]
    timed = rm.owner_action_spec(required=rm.FULL_PHYSICAL_MAKE, make_hours=6,
                                 yarn_metres=200, **kw)
    assert timed["tester_hours"] == 7.8 and "ESTIMATED" in timed["cost_basis"]


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
