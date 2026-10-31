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
                   read_days_ago: int = 5,
                   question: str = "Is there durable buyer demand for coastal table runners "
                                   "in Canada?") -> tuple[int, str]:
    """A research task answered by one fact-grade finding on one dated, fetched source."""
    t = research.open_question(
        db, question=question,
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

    # The next intake pass with no judgement on record queues nothing more.
    # M23: the next DAY's pass (a fresh score key) with no judgement on record queues nothing.
    before = len(_jobs(db, "radar.score"))
    quiet = _run(db, "radar.concept_intake",
                 {"as_of": (TODAY + timedelta(days=1)).isoformat()}, key="quiet")
    assert quiet["rescored"] == [] and quiet["work_done"] == 0, quiet
    assert len(_jobs(db, "radar.score")) == before

    # Once the vision judge's (fixture) verdict is on record, the scheduled intake pass
    # re-scores it by itself, and the same scoring promotes it to cir.draft -- no session.
    assert SLUG not in {s.slug for s in POOL}, "the target is NOT one of the POOL seeds"
    restore = _fixture_judgement()
    try:
        tomorrow = (TODAY + timedelta(days=2)).isoformat()
        auto = _run(db, "radar.concept_intake", {"as_of": tomorrow}, key="judged")
        assert auto["rescored"] == [SLUG], auto
        assert [j.idempotency_key for j in _jobs(db, "radar.score")][-1] == \
            f"score:{SLUG}:{tomorrow}"
        scored = _run(db, "radar.score", None)

        assert scored["promoted"] is True, scored
        assert scored["score"] >= pipeline.PROMOTION_THRESHOLD
        assert scored["evidence"]["discount"] == 1.0          # the same #38 discount path
        drafts = _jobs(db, "cir.draft")
        assert [j.idempotency_key for j in drafts] == [f"draft:{SLUG}"]
        assert drafts[0].inputs["premise"].startswith("A long table runner")

        # The draft gate re-reads the judge's record (F2): it is still on record here.
        drafted = _run(db, "cir.draft", None)
        assert drafted["drafted"] is True, drafted
    finally:
        restore()
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


# ---- review 933bf74: one discriminating test per surviving mutant, and F1-F6 -------------


def _reasons(out: dict, slug: str = SLUG) -> str:
    return " ".join(next(r["reasons"] for r in out["refused"] if r["slug"] == slug))


def _set_task(db, tid: int, **fields) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        row = s.get(research.ResearchTask, tid)
        for k, v in fields.items():
            setattr(row, k, v)
            if k == "detail":
                flag_modified(row, "detail")


def test_m3_an_expired_task_is_refused_by_name():
    db = _db()
    tid, _ = _answered_task(db)
    _set_task(db, tid, expires_on=datetime.now(timezone.utc) - timedelta(days=1))
    intake.attach_proposal(db, tid, _proposal())
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert "expired on" in _reasons(out) and "F-433" in _reasons(out), out


def test_m4_a_task_with_no_recorded_confidence_is_refused_by_name():
    db = _db()
    tid, _ = _answered_task(db, confidence="")
    intake.attach_proposal(db, tid, _proposal())
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert "recorded no usable confidence" in _reasons(out), out


def test_m5_claims_without_a_fact_grade_item_are_refused_by_name():
    db = _db()
    tid, _ = _answered_task(db)
    # A second source read only as a search summary, and a claim resting on it. The task
    # still holds its fact (F1/S1); the proposal cites only the claim and its summary.
    with db.session() as s:
        row = s.get(research.ResearchTask, tid)
        state = row.state
    _set_task(db, tid, state=research.OPEN)
    research.add_source(db, tid, source="fixture summary", citation="https://example.invalid/s",
                        retrieval="search_summary", read_on=TODAY - timedelta(days=3))
    f2 = research.add_finding(db, tid, statement="fixture: a blog says runners trend",
                              claim_class="source_claim", rests_on=["S2"])
    _set_task(db, tid, state=state)
    intake.attach_proposal(db, tid, _proposal(evidence=[f2, "S2"]))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert "no cited evidence is fact-grade" in _reasons(out), out


def test_m10_a_concept_indistinguishable_from_an_observed_listing_is_refused():
    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=MJS_KEY, listing_ref="fixture-twin-1",
                               title="Serene Host Table Runner Pattern", pod="kitchen_bath",
                               audit_state="audited", detail={}))
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(concept={"occasion": "everyday"}))
    out = _run(db, "radar.concept_intake", {})
    assert not out["approved"]
    assert "indistinguishable from observed competitor listing fixture-twin-1" in \
        _reasons(out), out


def test_m12_a_pool_slug_is_refused_on_its_own():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(slug="pet-snuggle-mat",
                                              title="Harbour Fog Driftwood Runner"))
    out = _run(db, "radar.concept_intake", {})
    assert "'pet-snuggle-mat' is a radar POOL concept" in _reasons(out, "pet-snuggle-mat"), out


def test_m13_a_pool_title_is_refused_on_its_own():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(slug="harbour-fog-runner",
                                              title="Harvest Table Runner"))
    out = _run(db, "radar.concept_intake", {})
    assert "title 'Harvest Table Runner' is POOL concept 'harvest-table-runner'" in \
        _reasons(out, "harbour-fog-runner"), out


def test_m14_a_slug_another_source_already_holds_is_refused_on_its_own():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    assert _run(db, "radar.concept_intake", {}, key="a")["approved"] == [SLUG]
    tid2, _ = _answered_task(db, trigger="test:second-source",
                             question="Do Canadian hosts buy lighthouse themed table runners?")
    assert tid2 != tid
    intake.attach_proposal(db, tid2, _proposal(
        title="Lighthouse Beam Runner",
        concept={"motif": "lighthouse beams", "recipient": "grandparent",
                 "occasion": "winter_nesting", "function": "lights a long table at dusk",
                 "premise": "A runner whose rows sweep like a lighthouse beam across the "
                            "table in amber and slate"}))
    out = _run(db, "radar.concept_intake", {}, key="b")
    assert f"'{SLUG}' is already an approved database concept" in _reasons(out), out


def test_m15_a_run_evaluates_at_most_the_cap():
    db = _db()
    tid, _ = _answered_task(db)
    n = intake.MAX_EVALUATIONS_PER_RUN + 1
    for i in range(n):
        intake.attach_proposal(db, tid, _proposal(slug=f"cap-runner-{i}",
                                                  title=f"Cap Runner {i}", evidence=[]))
    first = _run(db, "radar.concept_intake", {}, key="a")
    assert first["candidates"] == n and first["work_done"] == intake.MAX_EVALUATIONS_PER_RUN
    second = _run(db, "radar.concept_intake", {}, key="b")
    assert second["work_done"] == 1 and second["unchanged"] == intake.MAX_EVALUATIONS_PER_RUN
    assert len(_rows(db)) == n


def test_m19_f2_job_supplied_taste_never_passes_the_gate():
    db = _db()
    _benchmarks(db)
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {})
    _run(db, "radar.score", None)                     # the intake's own: waits
    from brambleloop.radar.opportunity import score_concept

    forged = score_concept(intake.seed_for(db, SLUG), TODAY).to_dict()
    forged.update(thumbnail_reads_small=True, craft_impression=4.9,
                  concept={"key": SLUG, "thumbnail_reads_small": True},
                  brief={"strength_score": 9.9, "strength_score_source": "model_jury:opus"},
                  strength_score=9.9, strength_score_source="model_jury:opus")
    out = _run(db, "radar.score", forged, key="forged")
    assert out["promoted"] is False and out["gate"]["decision"] == "waiting", out
    assert not _jobs(db, "cir.draft")
    # The engineering entry holds the same line for a directly enqueued draft.
    direct = _run(db, "cir.draft", {"slug": SLUG, **{k: v for k, v in forged.items()
                                                     if k != "slug"}}, key="direct")
    assert direct["drafted"] is False and direct["gate"] == "waiting", direct
    assert not _jobs(db, "cir.compile")


def test_f3_a_proposal_cannot_carry_a_judged_strength_score_or_board():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(brief={
        "thumbnail_storyboard": "long grey runner on oak table with stepped sea glass rows",
        "silhouette_qualifiers": ["motif_composition"], "strength_score": 9.9,
        "strength_score_source": "model_jury:opus", "benchmark_scores": [1] * 10,
        "board_image": "file:///forged.png"}))
    assert _run(db, "radar.concept_intake", {})["approved"] == [SLUG]
    row = _rows(db)[0]
    gated = intake.gate_inputs(db, SLUG, {"slug": SLUG})
    for k in ("strength_score", "strength_score_source", "benchmark_scores", "board_image"):
        assert k not in row.brief and k not in gated, k
    assert row.brief["thumbnail_storyboard"].startswith("long grey runner")


def test_m22_a_decided_family_variation_is_not_proposed_again():
    db = _db()
    family = "nordic-forest"
    members = [s.slug for s in POOL if s.family == family and not s.is_bundle]
    from brambleloop.creative import family_engine

    report = {"families": [{"family": family, "next_members": [],
                            "members": [{"slug": m, "version": "1.0.0", "orders": 3}
                                        for m in members],
                            "amplification": {"orders": 12}}]}
    intake._ensure(db)
    with db.session() as s:
        s.add(intake.RadarConcept(slug=f"{family}-blanket", state=intake.REFUSED,
                                  source=intake.SOURCE_FAMILY, source_ref=f"family:{family}",
                                  fingerprint="0" * 64))
    real = family_engine.family_report
    family_engine.family_report = lambda db: report
    try:
        cands = intake.family_candidates(db, today=TODAY)
    finally:
        family_engine.family_report = real
    slugs = [c["proposal"]["slug"] for c in cands]
    assert slugs and f"{family}-blanket" not in slugs, slugs
    assert slugs[0] == f"{family}-baby", slugs


def test_f1_an_approval_is_withdrawn_when_its_evidence_expires_and_rows_do_not_churn():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    assert _run(db, "radar.concept_intake", {}, key="d0")["approved"] == [SLUG]
    # The task expires: out of the pool at once, withdrawn and audited on the next pass.
    _set_task(db, tid, expires_on=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert intake.approved_seeds(db) == [] and intake.seed_for(db, SLUG) is None
    out = _run(db, "radar.concept_intake", {}, key="d1")
    assert [w["slug"] for w in out["withdrawn"]] == [SLUG], out
    assert _actions(db, intake.WITHDRAWN_ACTION)[0].artifact == SLUG
    assert [r.state for r in _rows(db)] == [intake.WITHDRAWN]
    # Day after day of the same expired evidence mints no new row and uses no slot.
    for d in range(2, 12):
        again = _run(db, "radar.concept_intake",
                     {"as_of": (TODAY + timedelta(days=d)).isoformat()}, key=f"d{d}")
        assert again["work_done"] == 0 and again["unchanged"] == 1, again
    assert len(_rows(db)) == 1


def test_f1_freshness_decay_withdraws_without_minting_a_row_a_day():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    assert _run(db, "radar.concept_intake", {}, key="d0")["approved"] == [SLUG]
    for d in (60, 120, 121, 122, 150):
        _run(db, "radar.concept_intake",
             {"as_of": (TODAY + timedelta(days=d)).isoformat()}, key=f"d{d}")
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].state == intake.WITHDRAWN, [(r.state, r.reasons)
                                                                   for r in rows]
    assert not intake.approved_seeds(db)


def test_f1_an_unresolved_task_withdraws_its_approval():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {}, key="a")
    with db.session() as s:
        detail = dict(s.get(research.ResearchTask, tid).detail or {})
    detail["conclusion"] = {**detail["conclusion"], "status": "unresolved"}
    _set_task(db, tid, detail=detail)
    assert intake.seed_for(db, SLUG) is None
    out = _run(db, "radar.concept_intake", {}, key="b")
    assert [w["slug"] for w in out["withdrawn"]] == [SLUG]


def test_f1_a_refused_revision_withdraws_the_earlier_approval():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {}, key="a")
    intake.attach_proposal(db, tid, _proposal(concept={"construction": "cable_panel"}))
    out = _run(db, "radar.concept_intake", {}, key="b")
    assert out["refused"] and not out["approved"]
    assert [r.state for r in _rows(db)] == [intake.WITHDRAWN, intake.REFUSED]
    assert intake.seed_for(db, SLUG) is None


def test_f1_retention_prunes_old_decided_rows_but_keeps_the_newest_and_approvals():
    from brambleloop.ops import retention

    db = _db()
    intake._ensure(db)
    old = datetime.now(timezone.utc) - timedelta(days=intake.RETENTION_DAYS + 5)
    with db.session() as s:
        for i, state in enumerate((intake.REFUSED, intake.REFUSED, intake.SUPERSEDED,
                                   intake.REFUSED)):
            s.add(intake.RadarConcept(slug="old-runner", state=state, at=old,
                                      source=intake.SOURCE_RESEARCH,
                                      source_ref="research_task:1", fingerprint=f"{i:064d}"))
        s.add(intake.RadarConcept(slug="kept-runner", state=intake.APPROVED, at=old,
                                  source=intake.SOURCE_RESEARCH, source_ref="research_task:1",
                                  fingerprint="9" * 64))
    plan = retention.plan(db)
    assert plan["radar_concepts"]["deletable"] == 3
    done = intake.prune(db)
    assert done["removed"] == 3
    left = sorted((r.slug, r.state) for r in _rows(db))
    assert left == [("kept-runner", intake.APPROVED), ("old-runner", intake.REFUSED)]


def test_f5_a_pool_prefixed_slug_is_refused_and_release_matches_exactly():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(
        slug="chunky-ribbed-scarf-harbour-fog", title="Harbour Fog Long Scarf",
        category="scarf", concept={"form": "scarf", "function": "wraps against coastal wind",
                                   "pod": "hats"}))
    out = _run(db, "radar.concept_intake", {})
    assert "extends POOL slug 'chunky-ribbed-scarf'" in \
        _reasons(out, "chunky-ribbed-scarf-harbour-fog"), out
    assert release._seed_for("chunky-ribbed-scarf-harbour-fog") is None
    assert release._seed_for("chunky-ribbed-scarf").slug == "chunky-ribbed-scarf"
    # The one catalogue product the old prefix match served resolves by its declared alias.
    assert release._seed_for("nordic-forest-mosaic-throw-baby").slug == \
        "nordic-forest-mosaic-throw"


def test_f6_every_seed_reader_given_db_sees_an_intake_concept():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal(family="nordic-forest"))
    assert _run(db, "radar.concept_intake", {})["approved"] == [SLUG]
    assert pipeline.product_seed(SLUG) is None
    assert pipeline.product_seed(SLUG, db).slug == SLUG
    assert release._seed_for(SLUG, db).slug == SLUG
    assert "Tide Line Table Runner" in release._collection_siblings(
        "nordic-forest-mosaic-throw", db)
    assert "Tide Line Table Runner" not in release._collection_siblings(
        "nordic-forest-mosaic-throw")


# ---- review bb680ec: G1 (queued draft after withdrawal), G2 (prune), G3 (N8 N9 N10 N17 N18) --


def test_g1_a_queued_draft_does_not_outlive_its_withdrawn_approval():
    db = _db()
    _benchmarks(db)
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {})
    _run(db, "radar.score", None)                                   # waits: no judgement
    restore = _fixture_judgement()
    try:
        _run(db, "radar.concept_intake",
             {"as_of": (TODAY + timedelta(days=2)).isoformat()}, key="judged")
        assert _run(db, "radar.score", None)["promoted"] is True
        assert [j.idempotency_key for j in _jobs(db, "cir.draft")] == [f"draft:{SLUG}"]
        # Withdrawn between radar.score and cir.draft -- with the judgement still on record.
        _set_task(db, tid, expires_on=datetime.now(timezone.utc) - timedelta(minutes=1))
        out = _run(db, "radar.concept_intake", {}, key="withdraw")
        assert [w["slug"] for w in out["withdrawn"]] == [SLUG]
        drafted = _run(db, "cir.draft", None)
    finally:
        restore()
    assert drafted["drafted"] is False and drafted["gate"] == "radar.intake", drafted
    assert not _jobs(db, "cir.compile"), "a withdrawn concept was compiled"
    refusals = [a for a in _actions(db, "cir.draft_refused") if a.artifact == SLUG]
    assert refusals and refusals[-1].detail["gate"] == "radar.intake"
    assert refusals[-1].detail["state"] == intake.WITHDRAWN
    assert not [a for a in _actions(db, "cir.drafted")]
    # The database row alone is enough: a draft for the withdrawn slug that declares no
    # intake provenance (raw geometry, as a re-draft would carry) is refused the same way.
    bare = _run(db, "cir.draft", {"slug": SLUG, "title": "Tide Line Table Runner",
                                  "category": "runner", "stitch_repeat": [["sc", 3], ["dc", 1]],
                                  "width_stitches": 60, "rows": 16,
                                  "colors": {"forest": "#244A3A", "cream": "#FAF6EB"}},
                key="bare")
    assert bare["drafted"] is False and bare["gate"] == "radar.intake", bare
    assert not _jobs(db, "cir.compile")
    # A rebuild of an established design is never blocked by an intake row sharing its slug.
    intake._ensure(db)
    with db.session() as s:
        s.add(intake.RadarConcept(slug="hexagon-coaster-set", state=intake.REFUSED,
                                  source=intake.SOURCE_RESEARCH, source_ref=f"research_task:{tid}",
                                  fingerprint="h" * 64))
    rebuilt = _run(db, "cir.draft", {"slug": "hexagon-coaster-set"}, key="rebuild")
    assert rebuilt.get("engineered") is True, rebuilt


def test_g1_a_draft_declaring_intake_provenance_without_any_row_is_refused():
    db = _db()
    out = _run(db, "cir.draft", {"slug": "phantom-runner", "provenance":
                                 "radar.intake:research_task:99", "title": "Phantom Runner",
                                 "category": "runner", "stitch_repeat": [["sc", 3], ["dc", 1]],
                                 "width_stitches": 60, "rows": 16,
                                 "colors": {"forest": "#244A3A"}})
    assert out["drafted"] is False and out["gate"] == "radar.intake", out
    assert not _jobs(db, "cir.compile")


def test_g2_prune_keeps_a_non_newest_row_that_holds_a_current_fingerprint():
    from brambleloop.ops import retention

    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())                       # A: approved
    _run(db, "radar.concept_intake", {}, key="a")
    intake.attach_proposal(db, tid, _proposal(concept={"construction": "cable_panel"}))
    _run(db, "radar.concept_intake", {}, key="b")                      # B: refused, A withdrawn
    intake.attach_proposal(db, tid, _proposal())                       # back to A: unchanged
    assert _run(db, "radar.concept_intake", {}, key="c")["unchanged"] == 1
    later = datetime.now(timezone.utc) + timedelta(days=intake.RETENTION_DAYS + 110)
    assert retention.apply(db, now=later)["removed"]["radar_concepts"] == 0
    assert [r.state for r in _rows(db)] == [intake.WITHDRAWN, intake.REFUSED]
    again = _run(db, "radar.concept_intake", {}, key="d")
    assert again["unchanged"] == 1 and not again["approved"], again


def _old_rows(db, specs, *, days: int) -> None:
    intake._ensure(db)
    at = datetime.now(timezone.utc) - timedelta(days=days)
    with db.session() as s:
        for i, (slug, state) in enumerate(specs):
            s.add(intake.RadarConcept(slug=slug, state=state, at=at,
                                      source=intake.SOURCE_RESEARCH,
                                      source_ref="research_task:1",
                                      fingerprint=f"{days:03d}{i:061d}"))


def test_n8_prune_never_deletes_an_approved_row_even_when_it_is_not_the_newest():
    db = _db()
    _old_rows(db, [("lone-runner", intake.APPROVED), ("lone-runner", intake.PROPOSED)],
              days=intake.RETENTION_DAYS + 30)
    assert intake.prune(db)["removed"] == 0
    assert [r.state for r in _rows(db)] == [intake.APPROVED, intake.PROPOSED]


def test_n9_prune_keeps_decided_rows_younger_than_the_horizon():
    db = _db()
    _old_rows(db, [("young-runner", intake.REFUSED), ("young-runner", intake.REFUSED)],
              days=intake.RETENTION_DAYS - 10)
    assert intake.prune(db)["removed"] == 0 and len(_rows(db)) == 2
    _old_rows(db, [("aged-runner", intake.REFUSED), ("aged-runner", intake.REFUSED)],
              days=intake.RETENTION_DAYS + 10)
    assert intake.prune(db)["removed"] == 1 and len(_rows(db)) == 3


def test_n10_ops_retention_apply_prunes_the_table():
    from brambleloop.ops import retention

    db = _db()
    _old_rows(db, [("aged-runner", intake.REFUSED)] * 3, days=intake.RETENTION_DAYS + 10)
    dry = retention.apply(db, dry_run=True)
    assert dry["removed"]["radar_concepts"] == 2 and len(_rows(db)) == 3
    done = retention.apply(db)
    assert done["removed"]["radar_concepts"] == 2 and len(_rows(db)) == 1


def test_n17_a_family_that_loses_proven_demand_has_its_variation_withdrawn():
    db = _db()
    family = "nordic-forest"
    members = [s.slug for s in POOL if s.family == family and not s.is_bundle]
    from brambleloop.creative import family_engine

    report = {"families": [{"family": family, "next_members": [],
                            "members": [{"slug": m, "version": "1.0.0", "orders": 3}
                                        for m in members],
                            "amplification": {"orders": 12}}]}
    real = family_engine.family_report
    family_engine.family_report = lambda db: report
    try:
        with db.session() as s:
            c = Customer(customer_ref="fixture-customer-n17")
            s.add(c)
            s.flush()
            for i in range(12):
                s.add(Order(customer_id=c.id, external_ref=f"fixture-n17-{i}",
                            product_slug=members[i % len(members)],
                            at=datetime.now(timezone.utc) - timedelta(days=3 + i)))
        first = _run(db, "radar.concept_intake", {}, key="f1")
        assert first["approved"], first
        report["families"][0]["amplification"] = "UNMEASURED"
        second = _run(db, "radar.concept_intake", {}, key="f2")
    finally:
        family_engine.family_report = real
    gone = {w["slug"]: " ".join(w["reasons"]) for w in second["withdrawn"]}
    assert set(first["approved"]) <= set(gone), second
    assert all("no longer has proven demand" in r for r in gone.values()), gone
    assert not intake.approved_seeds(db)


def test_n18_gate_inputs_strips_judged_brief_fields_from_a_stored_row():
    db = _db()
    tid, _ = _answered_task(db)
    intake.attach_proposal(db, tid, _proposal())
    _run(db, "radar.concept_intake", {})
    # A row approved before _clean stripped them (933bf74) can still hold judged fields.
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        row = s.scalar(select(intake.RadarConcept).where(intake.RadarConcept.slug == SLUG))
        row.brief = {**row.brief, "strength_score": 9.9,
                     "strength_score_source": "model_jury:opus",
                     "benchmark_scores": [1] * 10, "board_image": "file:///forged.png"}
        flag_modified(row, "brief")
    gated = intake.gate_inputs(db, SLUG, {"slug": SLUG})
    for k in ("strength_score", "strength_score_source", "benchmark_scores", "board_image"):
        assert k not in gated, k
    assert gated["thumbnail_storyboard"].startswith("long grey runner")


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
