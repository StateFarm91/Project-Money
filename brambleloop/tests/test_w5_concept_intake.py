"""W5-CONCEPT: an evidence-backed opportunity becomes a radar concept (a row, not code).

Runs the real handlers -- `radar.concept_intake`, `radar.score`, `cir.draft`, `radar.scan` --
through the worker with a real JobContext on a scratch database. Every research source,
finding, competitor listing, order and taste judgement here is a TEST FIXTURE; none is an
observation, a customer or a judgement anybody made.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, Customer, Job, JobStatus, Order,
)
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar.opportunity import POOL, ConceptSeed, score_pool, select_portfolio  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402

TODAY = date.today()
SLUG = "tide-line-table-runner"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/intake.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, job_type: str, inputs: dict | None = None, key: str = "") -> dict:
    """Enqueue (or pick up the queued) job of this type and run exactly it."""
    q = JobQueue(db)
    if inputs is not None:
        agent = {"radar.concept_intake": "market_radar", "radar.score": "market_radar",
                 "radar.scan": "market_radar", "cir.draft": "crochet_engineer"}[job_type]
        q.enqueue(agent, job_type, inputs, priority=0,
                  idempotency_key=key or f"t:{job_type}:{id(inputs)}")
    with db.session() as s:
        job_id = s.scalar(select(Job.id).where(Job.job_type == job_type,
                                               Job.status == JobStatus.PENDING)
                          .order_by(Job.id).limit(1))
    assert job_id is not None, f"no pending {job_type}"
    assert Worker(db, "w5-test", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job_id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _jobs(db, job_type: str) -> list[Job]:
    with db.session() as s:
        return [j for j in s.scalars(select(Job).where(Job.job_type == job_type))]


def _actions(db, prefix: str = "") -> list[AuditLog]:
    with db.session() as s:
        return [r for r in s.scalars(select(AuditLog).order_by(AuditLog.id))
                if r.action.startswith(prefix)]


def _rows(db) -> list[intake.RadarConcept]:
    intake._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(intake.RadarConcept).order_by(intake.RadarConcept.id)))
        s.expunge_all()
        return rows


def _benchmarks(db, n: int = 4) -> None:
    """Fixture competitor listings so the anti-clone half of #87 is measurable."""
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key=MJS_KEY, listing_ref=f"fixture-runner-{i}",
                                   title=f"Chunky Farmhouse Table Runner Crochet Pattern {i}",
                                   pod="kitchen_bath", audit_state="audited", detail={}))


def _answered_task(db, *, trigger: str = "test:coastal-runner", confidence: str = "medium",
                   read_days_ago: int = 5) -> tuple[int, str]:
    """A research task answered by one fact-grade finding on one dated, fetched source."""
    t = research.open_question(
        db, question="Is there durable buyer demand for coastal table runners in Canada?",
        trigger=trigger, decision_ref="radar.concept_intake:test",
        domain="competitor_positioning", query_terms=["runner"],
        evidence_needed="fixture listing census", stop_condition="a fact answers it",
        if_unresolved="record it unresolved")
    tid = t["task"]
    research.add_source(db, tid, source="fixture census", citation="https://example.invalid/c",
                        retrieval="fetched", read_on=TODAY - timedelta(days=read_days_ago))
    f1 = research.add_finding(db, tid, statement="fixture: runners sell steadily year round",
                              claim_class="fact", rests_on=["S1"], confidence=confidence)
    research.answer(db, tid, outcome="fixture: durable", confidence=confidence,
                    effect={"kind": "constraint_established",
                            "statement": "fixture: demand is durable"},
                    conclusion={"alternatives": [], "constraints": ["fixture constraint"],
                                "unresolved": [], "next_test": {}, "applicability": None})
    return tid, f1


def _proposal(**over) -> dict:
    p = {
        "slug": SLUG, "title": "Tide Line Table Runner", "category": "runner",
        "price_cad": 7.5, "maker_hours": [4.0, 9.0], "design_hours": 8.0,
        "rationale": ("fixture research shows runners sell steadily year round in Canada and "
                      "no profiled shop sells a coastal stepped-stripe runner"),
        "evergreen": True,
        "concept": {
            "premise": ("A long table runner whose rows step like receding tide lines across "
                        "driftwood grey and sea glass"),
            "pod": "kitchen_bath", "form": "runner", "construction": "flat_rows",
            "motif": "tide lines", "palette_story": "driftwood grey and sea glass",
            "recipient": "host", "occasion": "housewarming", "feeling": "serene",
            "function": "dresses a dining table for guests"},
        "brief": {"thumbnail_storyboard": ("long grey runner on oak table with stepped sea "
                                           "glass tide line rows"),
                  "silhouette_qualifiers": ["motif_composition"]},
        "evidence": ["F1", "S1"],
        # Smuggled taste fields are stripped: only the vision judge's record may set them.
        "thumbnail_reads_small": True,
    }
    for k, v in over.items():
        if k == "concept":
            p["concept"] = {**p["concept"], **v}
        else:
            p[k] = v
    return p


def _fixture_judgement():
    """Stand in for the vision judge's recorded verdict (image_vision is CLOSED)."""
    from brambleloop.creative import intake as creative_intake

    real = creative_intake.judgement_for
    creative_intake.judgement_for = lambda db, key: (
        {"thumbnail_reads_small": True, "craft_impression": 4.2, "sources": ["fixture"]}
        if key == SLUG else real(db, key))
    return lambda: setattr(creative_intake, "judgement_for", real)


# ---- the happy path ------------------------------------------------------------------------


def test_an_evidence_backed_opportunity_becomes_a_concept_is_scored_and_reaches_cir_draft():
    db = _db()
    _benchmarks(db)
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())

    out = _run(db, "radar.concept_intake", {})
    assert out["approved"] == [SLUG], out
    assert out["network_calls"] == 0 and out["spend_cad"] == 0.0
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].state == intake.APPROVED
    row = rows[0]
    assert row.source_ref == f"research_task:{tid}"
    # Attributed to the evidence, with source dates and a computed quality / uncertainty.
    assert {i["ref"] for i in row.evidence} == {"F1", "S1"}
    assert all(i["date"] for i in row.evidence)
    assert 0.4 <= row.quality <= 1.0
    assert row.seed["risk_class"] == "A" and row.seed["make_lane"] == "SHORT"
    assert 0 < row.seed["whitespace"] <= 1.0, "whitespace is the measured distance"
    assert "thumbnail_reads_small" not in row.concept, "a proposal cannot set taste"
    acts = [a.action for a in _actions(db, "concept.intake")]
    assert acts == [intake.PROPOSED_ACTION, intake.APPROVED_ACTION, intake.HANDOFF_ACTION]

    # The successor job is the ordinary radar.score, keyed like radar.scan.
    score_jobs = _jobs(db, "radar.score")
    assert [j.idempotency_key for j in score_jobs] == [f"score:{SLUG}:{TODAY.isoformat()}"]

    # Without a vision judgement the pre-engineering gate WAITS -- never engineered.
    waited = _run(db, "radar.score", None)
    assert waited["promoted"] is False and waited["gate"]["decision"] == "waiting", waited
    assert not _jobs(db, "cir.draft")

    # With the judge's (fixture) verdict on record, the same scoring promotes it.
    restore = _fixture_judgement()
    try:
        scored = _run(db, "radar.score", {"slug": SLUG}, key="rescore")
    finally:
        restore()
    assert scored["promoted"] is True, scored
    assert scored["score"] >= pipeline.PROMOTION_THRESHOLD
    assert scored["evidence"]["discount"] == 1.0          # the same #38 discount path
    drafts = _jobs(db, "cir.draft")
    assert [j.idempotency_key for j in drafts] == [f"draft:{SLUG}"]
    assert drafts[0].inputs["premise"].startswith("A long table runner")

    drafted = _run(db, "cir.draft", None)
    assert drafted["drafted"] is True, drafted
    compiles = _jobs(db, "cir.compile")
    assert compiles and compiles[0].inputs["cir"]["slug"] == SLUG
    prov = compiles[0].inputs["cir"]["provenance"]
    assert prov and prov["concept_key"] == SLUG


def test_radar_scan_scores_the_approved_concept_with_the_pool():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {})
    pool = intake.pool_with_intake(db)
    assert len(pool) == len(POOL) + 1 and pool[-1].slug == SLUG
    assert pool[-1].origin == f"radar.intake:research_task:{tid}"
    out = _run(db, "radar.scan", {"as_of": TODAY.isoformat()})
    assert out["pool_size"] == len(POOL) + 1


# ---- refusals ------------------------------------------------------------------------------


def test_a_duplicate_is_refused():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    # A POOL slug, and a recolour of the approved concept under a new name.
    intake.attach_proposal(db, tid, _proposal(slug="harvest-table-runner",
                                              title="Harvest Table Runner"))
    intake.attach_proposal(db, tid, _proposal(
        slug="ebb-tide-table-runner", title="Ebb Tide Runner",
        concept={"palette_story": "navy and cream"}))
    out = _run(db, "radar.concept_intake", {})
    assert out["approved"] == [SLUG], out
    refused = {r["slug"]: r["reasons"] for r in out["refused"]}
    assert any("duplicate" in r and "POOL" in r for r in refused["harvest-table-runner"])
    assert any("duplicate" in r and "novelty floor" in r
               for r in refused["ebb-tide-table-runner"]), refused
    assert len(_jobs(db, "radar.score")) == 1, "a refused concept is never scored"
    assert len(_actions(db, intake.REFUSED_ACTION)) == 2


def test_a_competitor_title_is_refused_as_a_copy():
    db = _db()
    _benchmarks(db)
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(
        title="Chunky Farmhouse Table Runner"))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert any("copy" in r for r in out["refused"][0]["reasons"]), out


def test_an_unsupported_construction_is_refused_with_its_reason():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(
        slug="driftwood-rope-basket", title="Driftwood Rope Basket", category="basket",
        concept={"form": "basket", "construction": "in_the_round", "pod": "home_decor",
                 "function": "holds rolled towels by the bath"}))
    intake.attach_proposal(db, tid, _proposal(
        slug="tide-line-cable-runner", title="Tide Cable Runner",
        concept={"construction": "cable_panel", "motif": "rope cables"}))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    reasons = {r["slug"]: " ".join(r["reasons"]) for r in out["refused"]}
    assert "unsupported construction 'in_the_round'" in reasons["driftwood-rope-basket"]
    assert "B-059" in reasons["driftwood-rope-basket"]
    assert "unsupported construction 'cable_panel'" in reasons["tide-line-cable-runner"]
    assert not _jobs(db, "radar.score")
    # Every supported category has a real template row, so the draft is not the default.
    assert set(intake.SUPPORTED_FORMS) <= set(pipeline._GEOMETRY)


def test_a_concept_without_evidence_is_refused():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(evidence=[]))
    intake.attach_proposal(db, tid, _proposal(slug="sea-glass-runner",
                                              title="Sea Glass Runner", evidence=["F9"]))
    # An open (unanswered) task is not an approved opportunity.
    t = research.open_question(
        db, question="Do Canadian buyers want coastal placemats this spring?",
        trigger="test:open", decision_ref="radar.concept_intake:test",
        domain="competitor_positioning", evidence_needed="x", stop_condition="y",
        if_unresolved="z")
    intake.attach_proposal(db, t["task"], _proposal(slug="sea-glass-placemats",
                                                    title="Sea Glass Placemats",
                                                    evidence=["S1"]))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"], out
    reasons = {r["slug"]: " ".join(intake_reasons for intake_reasons in r["reasons"])
               for r in out["refused"]}
    assert "without recorded evidence" in reasons[SLUG]
    assert "evidence must be recorded, not asserted" in reasons["sea-glass-runner"]
    assert "not answered" in reasons["sea-glass-placemats"]
    assert not _jobs(db, "radar.score")


def test_low_quality_evidence_is_refused():
    db = _db()
    tid, _ = _answered_task(db, confidence="low")
    intake.attach_proposal(db, tid, _proposal())
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert any("below 0.4" in r for r in out["refused"][0]["reasons"]), out


def test_a_childrens_prohibited_subject_is_refused_before_any_cir():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(
        slug="cloud-crib-bumper", title="Cloud Crib Bumper", category="baby",
        concept={"form": "rectangle_throw", "recipient": "new_parent", "occasion": "new_baby",
                 "function": "pads a crib bumper rail", "pod": "blankets"}))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert any("children's policy" in r for r in out["refused"][0]["reasons"]), out


# ---- idempotency ---------------------------------------------------------------------------


def test_unchanged_input_is_not_reprocessed_and_a_change_is():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    first = _run(db, "radar.concept_intake", {}, key="a")
    assert first["approved"] == [SLUG]
    audits = len(_actions(db, "concept.intake"))
    second = _run(db, "radar.concept_intake", {}, key="b")
    assert second["unchanged"] == 1 and second["work_done"] == 0, second
    assert len(_actions(db, "concept.intake")) == audits
    assert len(_rows(db)) == 1
    # A changed proposal is evaluated once; the earlier approval is superseded.
    intake.attach_proposal(db, tid, _proposal(price_cad=8.0))
    third = _run(db, "radar.concept_intake", {}, key="c")
    assert third["approved"] == [SLUG], third
    states = [r.state for r in _rows(db)]
    assert states == [intake.SUPERSEDED, intake.APPROVED]
    assert len(intake.approved_seeds(db)) == 1


# ---- product families ----------------------------------------------------------------------


def test_a_proven_family_proposes_coordinated_variations_without_duplicates():
    db = _db()
    family = "nordic-forest"
    members = [s.slug for s in POOL if s.family == family and not s.is_bundle]
    from brambleloop.creative import family_engine

    report = {"families": [{
        "family": family, "members": [{"slug": m, "version": "1.0.0", "orders": 3}
                                      for m in members],
        "next_members": [], "amplification": {"orders": 12}}]}
    real = family_engine.family_report
    family_engine.family_report = lambda db: report
    try:
        with db.session() as s:
            c = Customer(customer_ref="fixture-customer")
            s.add(c)
            s.flush()
            for i in range(12):
                s.add(Order(customer_id=c.id, external_ref=f"fixture-order-{i}",
                            product_slug=members[i % len(members)],
                            at=datetime.now(timezone.utc) - timedelta(days=3 + i)))
        first = _run(db, "radar.concept_intake", {}, key="f1")
        second = _run(db, "radar.concept_intake", {}, key="f2")
    finally:
        family_engine.family_report = real
    assert len(first["approved"]) + len(first["refused"]) == intake.MAX_FAMILY_VARIATIONS
    assert first["approved"], first
    for slug in first["approved"]:
        seed = intake.seed_for(db, slug)
        assert seed.family == family and seed.origin == f"radar.intake:family:{family}"
        assert seed.category in intake.SUPPORTED_FORMS
        assert seed.category not in {s.category for s in POOL if s.family == family}
    # The second pass proposes the next categories, never the same ones again.
    slugs = [r.slug for r in _rows(db)]
    assert len(slugs) == len(set(slugs)), slugs
    assert not set(second["approved"]) & set(first["approved"]), (first, second)
    assert {r.slug for r in _rows(db)} >= set(first["approved"]) | set(second["approved"])


def test_a_family_without_proven_orders_proposes_nothing():
    db = _db()
    from brambleloop.creative import family_engine

    rep = family_engine.family_report(db)
    assert not intake.family_candidates(db, today=TODAY)
    assert all(not isinstance(f.get("amplification"), dict) for f in rep["families"])


# ---- the static POOL is unchanged ----------------------------------------------------------


def test_the_static_pool_behaviour_is_unchanged():
    db = _db()
    assert intake.pool_with_intake(db) == list(POOL)
    assert intake.pool_with_intake(None) == list(POOL)
    assert all(s.origin is None for s in POOL)
    a = select_portfolio(score_pool(today=TODAY), today=TODAY)
    b = select_portfolio(score_pool(intake.pool_with_intake(db), today=TODAY), today=TODAY)
    assert [c.slug for c in a.selected] == [c.slug for c in b.selected]
    assert [c.score for c in a.selected] == [c.score for c in b.selected]
    for s in POOL:
        assert pipeline._seed_for(s.slug) is s and pipeline._seed_for(s.slug, db) is s
    assert pipeline._seed_for("no-such-concept", db) is None
    # The payload radar.scan hands radar.score carries no new key for a POOL concept.
    assert "origin" not in score_pool(today=TODAY)[0].to_dict()
    assert ConceptSeed.__dataclass_fields__["origin"].default is None


def test_the_intake_runs_on_the_cadence_table_without_a_chat_session():
    entry = [c for c in CADENCES if c[2] == "radar.concept_intake"]
    assert entry and entry[0][1] == "market_radar"
    reg = Registry(_db())
    reg.authorize("market_radar", "radar.concept_intake")
    from brambleloop.runtime.pipeline import WORK_KEYS

    assert WORK_KEYS["radar.concept_intake"] == ("work_done",)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
