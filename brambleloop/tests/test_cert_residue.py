"""Certification: the last executable OPEN rows of Build 2 (#4, #194).

Every test drives a registered handler through the real worker on a file database seeded
with real rows, and asserts the downstream effect. Network is refused at the socket: nothing
here may post, fetch or spend. Every observation seeded is a fixture, never a customer or a
platform.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _no_network(*_a, **_k):
    raise AssertionError("network refused: this certification runs on rows only")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]
socket.getaddrinfo = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, Worker, handlers  # noqa: E402
from brambleloop.swarm.orchestrate import JOB_BANDS  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cert_residue_')}/r.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _scheduled(job_type: str, agent: str) -> None:
    """The job type is on a cadence, granted to its agent, banded and handled."""
    assert any(jt == job_type and a == agent for _n, a, jt, _p in CADENCES), job_type
    spec = next(a for a in DEFAULT_AGENTS if a["name"] == agent)
    assert job_type in spec["allowed_job_types"], (agent, job_type)
    assert job_type in JOB_BANDS, job_type
    assert handlers.get(job_type) is not None, job_type


_N = [0]


def _run(db, job_type: str, agent: str, inputs: dict | None = None) -> dict:
    """Enqueue as the cadence would and run it through the real worker to DONE."""
    _N[0] += 1
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"residue:{job_type}:{_N[0]}")
    assert Worker(db, "cert-residue", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status is JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _rows(db, action: str) -> list[tuple[int, str, dict]]:
    with db.session() as s:
        return [(r.id, r.artifact or "", dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


# ---------------------------------------------------------------------------
# #4: pre-production demand validation runs on cadence and acts on a measured result


def _held_winner(db, key: str, premise: str) -> None:
    """A winner held at intake before engineering (the `waiting` decision)."""
    from brambleloop.creative import intake

    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=intake.INTAKE_ACTION, artifact=key,
                       detail={"decision": intake.WAITING, "source": "creative.tournament",
                               "concept": {"key": key, "title": key.replace("-", " ").title(),
                                           "premise": premise, "pod": "hats",
                                           "form": "hat", "construction": "in_the_round"},
                               "gate": {"waiting_on": ["image_vision"]}}))


def test_preproduction_prepares_refuses_to_post_records_unmeasured_and_acts_when_measured_4():
    """#4 through `growth.preproduction` on the worker. A held winner gets a concept post per
    channel that passes the module's own gate; posting is refused because the owned_surfaces
    gate is closed (recorded, nothing posted); interest is UNMEASURED by name because no
    platform has reported anything; and once a platform-written observation exists the
    concept is recorded as validated and reaches the next tournament's brief with its receipt.
    No number about interest is ever written by the system itself."""
    from brambleloop.commerce import preproduction as P
    from brambleloop.commerce import preproduction_cycle as C
    from brambleloop.creative import ideation

    _scheduled("growth.preproduction", "growth")
    db = _db()
    _held_winner(db, "lantern-brim-beanie",
                 "a folded brim that stands proud of the crown so it reads across a room")

    out = _run(db, "growth.preproduction", "growth")
    assert out["ran"] is True and out["concepts"] == 1
    posts = _rows(db, C.POST_ACTION)
    assert {d["channel"] for _i, _a, d in posts} == set(C.CHANNELS), posts
    for _i, artifact, d in posts:
        assert artifact == "lantern-brim-beanie" and d["posted"] is False
        assert P.check_post(d["body"]) == [], d["body"]
        assert d["detail"]["engineered"] is False
    assert out["prepared"] == len(C.CHANNELS) and out["refused"] == 0
    # The gate is closed: nothing is posted and the refusal is a row, not a silence.
    assert out["publish"]["state"] == "refused" and out["publish"]["posted"] == 0
    assert out["publish"]["gate"] == "owned_surfaces" and out["publish"]["open"] is False
    refusals = _rows(db, C.PUBLISH_REFUSED_ACTION)
    assert len(refusals) == 1 and refusals[0][2]["held"] == len(C.CHANNELS)
    # No platform has reported anything: UNMEASURED, by name, from record_interest.
    assert out["unmeasured"] == ["lantern-brim-beanie"]
    reading = _rows(db, C.INTEREST_ACTION)[-1][2]
    assert reading["reading"] == "UNMEASURED" and reading["measurable"] is False
    assert "fabricated engagement" in reading["why"]
    assert out["acted_on"] == [] and not _rows(db, C.VALIDATED_ACTION)
    assert ideation.preproduction_interest(db)["measured"] == []

    # Idempotent on a second daily run: nothing re-prepared, nothing re-recorded.
    again = _run(db, "growth.preproduction", "growth")
    assert again["prepared"] == 0
    assert len(_rows(db, C.POST_ACTION)) == len(C.CHANNELS)
    assert len(_rows(db, C.INTEREST_ACTION)) == 1

    # A platform reports interest (a fixture standing in for the ingest an owned surface
    # would bring). The cycle reads it, and acts: the concept is validated with its receipt
    # and the next field's brief carries it.
    with db.session() as s:
        s.add(AuditLog(actor="pinterest_ingest", action=C.OBSERVED_ACTION,
                       artifact="lantern-brim-beanie",
                       detail={"source": "pinterest analytics", "channel": "pinterest",
                               "observed": {"saves": 40, "comments": 3}}))
    third = _run(db, "growth.preproduction", "growth")
    assert third["unmeasured"] == []
    assert third["acted_on"] == [{"concept": "lantern-brim-beanie",
                                  "source": "pinterest analytics",
                                  "observed": {"saves": 40, "comments": 3}}]
    validated = _rows(db, C.VALIDATED_ACTION)
    assert len(validated) == 1 and validated[0][2]["source"] == "pinterest analytics"
    reading = _rows(db, C.INTEREST_ACTION)[-1][2]
    assert reading["reading"] == "measured" and reading["observed"]["saves"] == 40
    brief = ideation.preproduction_interest(db)
    assert brief["measured"][0]["concept"] == "lantern-brim-beanie"
    assert brief["measured"][0]["receipt"] == f"{C.VALIDATED_ACTION} row {validated[0][0]}"
    lines = C.brief_lines(brief)
    assert len(lines) == 1 and "saves 40" in lines[0] and "never a copy" in lines[0]
    # Acted on once: a fourth run does not re-validate the same observation.
    fourth = _run(db, "growth.preproduction", "growth")
    assert fourth["acted_on"] == [] and len(_rows(db, C.VALIDATED_ACTION)) == 1
    # Still nothing posted, on every run.
    assert all(d["posted"] is False for _i, _a, d in _rows(db, C.POST_ACTION))
    assert fourth["publish"]["posted"] == 0


def test_preproduction_reaches_the_generator_brief_of_the_next_tournament_4():
    """The act is read by the running system: `ideation.plan` carries the validated interest
    and `constraints_text` puts it in every generator brief, with the receipt row."""
    from brambleloop.commerce import preproduction_cycle as C
    from brambleloop.creative import ideation
    from brambleloop.intel import benchmarks
    from brambleloop.core.models import BenchmarkListing

    db = _db()
    with db.session() as s:
        for i in range(6):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"H{i}",
                                   title="Christmas Beanie Crochet Pattern", pod="hats",
                                   price_cad=7.0, audit_state="audited",
                                   detail={"num_favorers": 80}))
        s.add(AuditLog(actor="growth", action=C.VALIDATED_ACTION, artifact="lantern-brim-beanie",
                       detail={"premise": "a folded brim that stands proud of the crown",
                               "source": "pinterest analytics", "observed": {"saves": 40},
                               "observed_row": 1, "channel": "pinterest"}))
    plan = ideation.plan(db, kind="tournament", event="Christmas", pod="hats",
                         forms=["hat"], cycle=1)
    assert plan["preproduction"]["measured"][0]["concept"] == "lantern-brim-beanie"
    text, _assignment = ideation.constraints_text(plan, 0)
    assert "pre-production interest (preproduction.validated row 1" in text, text
    assert "saves 40" in text and "reported by pinterest analytics" in text


def test_preproduction_source_still_cannot_author_a_number_4():
    """The runtime half keeps the structural prohibition: neither module carries a literal
    metric assignment, and the only counts written are rows read."""
    from brambleloop.commerce import preproduction as P

    for rel in ("src/brambleloop/commerce/preproduction.py",
                "src/brambleloop/commerce/preproduction_cycle.py"):
        source = (ROOT / rel).read_text().replace("NEVER_FABRICATED", "")
        for metric in P.NEVER_FABRICATED:
            assert f'"{metric}":' not in source, (rel, metric)


# ---------------------------------------------------------------------------
# #194: the weekly deep evolution cycle can revise a metric, from evidence, to the owner


def _weekly_row(db, unmeasured: list[str]) -> None:
    """A previous weekly cycle's row, as handle_weekly_evolution writes it."""
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="improve.weekly",
                       detail={"complete": False, "cells_unmeasured": sorted(unmeasured)}))


def test_weekly_cycle_revises_a_metric_unmeasured_for_three_cycles_with_a_proxy_194():
    """#194 through `improve.weekly` on the worker. finance's `forecast_error` cannot be read
    (no revenue) while cost entries carrying estimates exist; after three consecutive
    unmeasured cycles the cycle generates a REVISE_METRIC change to `cost_estimate_error`
    under improve.weekly's rules and cards it to the owner. Two cycles are not enough, a
    department with no proxy rows is reported and not revised, and the old metric's history
    is untouched. Nothing is measured that the rows do not hold."""
    from brambleloop.core.models import CostEntry
    from brambleloop.improve import cells, evolution

    _scheduled("improve.weekly", "orchestrator")
    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i in range(4):
            s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=0.5 + 0.1 * i,
                            estimated_cad=0.4, department="market_radar",
                            at=now - timedelta(days=i)))
    _weekly_row(db, ["finance", "growth", "quality", "pricing"])

    first = _run(db, "improve.weekly", "orchestrator")
    mr = first["metric_revisions"]
    assert mr["history_cycles_read"] == 1 and mr["changes"] == [], mr
    assert "finance" in first["cells_unmeasured"]
    assert mr["considered"]["finance"].startswith("unmeasured 2 cycle(s) of the 3")
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == evolution.REVISE_CARD_KEY)) is None

    # The first run wrote its own row: the streak is now three, read from rows.
    second = _run(db, "improve.weekly", "orchestrator")
    mr = second["metric_revisions"]
    assert mr["history_cycles_read"] == 2, mr
    subjects = {c["subject"]: c for c in mr["changes"]}
    assert "finance" in subjects, mr
    fin = subjects["finance"]
    assert fin["move"] == "revise_metric" and fin["proposed_by"] == "improvement_director"
    assert fin["replaces_metric"] == cells.BY_KEY["finance"].metric == "forecast_error"
    assert fin["new_metric"] == "cost_estimate_error"
    assert "UNMEASURED for 3 weekly cycles" in fin["because"]
    assert "preserved under the old metric" in fin["history"]
    assert mr["evidence"]["finance"]["proxy"]["rows"] == 4
    assert mr["evidence"]["finance"]["kind"] == "unmeasured_streak"
    # growth is unmeasured for the streak too, but no experiment row exists to read: the
    # proxy has nothing, so nothing is proposed and the reason says so. quality has no proxy.
    assert "growth" not in subjects and "nothing is invented" in mr["considered"]["growth"]
    assert "quality" not in subjects and "no proxy" in mr["considered"]["quality"]
    assert second["architecture"]["metrics_revised"] == len(mr["changes"]) >= 1
    # Carded to the owner, with the evidence, as one batched card.
    assert mr["card"] == "queued"
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == evolution.REVISE_CARD_KEY))
        assert card is not None and "forecast_error -> cost_estimate_error" in card.action
        assert card.max_cost_cad == 0.0 and not card.done
    # The old metric's history is untouched: no capability point was written or migrated.
    assert cells.capability_history(db, "finance") == []
    row = _rows(db, "improve.weekly")[-1][2]
    assert row["metric_revisions"]["changes"][0]["subject"] == "finance"


def test_weekly_cycle_revises_a_metric_whose_realised_outcomes_contradict_it_194():
    """The second kind of evidence: pricing's `contribution_margin` moved up across its
    readings while both assessed promotions in pricing realised nothing against their own
    baselines (improve.roi). The cycle proposes the department's proxy from rows -- drafted
    listing prices against the observed band -- and cards it; a department whose contradiction
    has no proxy rows is reported, not revised."""
    from brambleloop.core.models import BenchmarkListing, CapabilityPoint, Improvement, Listing
    from brambleloop.improve import cells, evolution
    from brambleloop.intel import benchmarks

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i, base in enumerate((0.70, 0.72)):
            s.add(Improvement(cell="pricing", metric="contribution_margin", state=cells.PROMOTED,
                              hypothesis="h", baseline_value=base, evidence={},
                              promoted_at=now - timedelta(days=30 + i), at=now - timedelta(days=40)))
        for i, base in enumerate((0.40, 0.42)):
            s.add(Improvement(cell="quality", metric="defects_found_after_release",
                              state=cells.PROMOTED, hypothesis="h", baseline_value=base,
                              evidence={}, promoted_at=now - timedelta(days=30 + i),
                              at=now - timedelta(days=40)))
        # Readings written after the promotions, by the measurer, never by the promotion.
        for i, v in enumerate((0.50, 0.60)):
            s.add(CapabilityPoint(cell="pricing", metric="contribution_margin", value=v,
                                  sample=5, detail={"from": "improve.measure"},
                                  at=now - timedelta(days=10 - i)))
        for i, v in enumerate((0.60, 0.50)):   # lower is better: "improved"
            s.add(CapabilityPoint(cell="quality", metric="defects_found_after_release",
                                  value=v, sample=5, detail={"from": "improve.measure"},
                                  at=now - timedelta(days=10 - i)))
        for i in range(3):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"P{i}",
                                   title="Pattern", pod="hats", price_cad=6.0 + i))
        s.add(Listing(product_slug="p1", version="1.0.0", title="t", description="d",
                      price_cad=7.0))
        s.add(Listing(product_slug="p2", version="1.0.0", title="t", description="d",
                      price_cad=14.0))
    out = _run(db, "improve.weekly", "orchestrator")
    mr = out["metric_revisions"]
    subjects = {c["subject"]: c for c in mr["changes"]}
    assert "pricing" in subjects, mr
    pr = subjects["pricing"]
    assert pr["replaces_metric"] == "contribution_margin"
    assert pr["new_metric"] == "listing_price_inside_observed_band"
    assert "realised nothing" in pr["because"] and "0.5 -> 0.6" in pr["because"]
    ev = mr["evidence"]["pricing"]
    assert ev["kind"] == "contradiction" and ev["assessed"] == 2
    assert ev["proxy"]["value"] == 0.5 and ev["proxy"]["rows"] == 5
    # quality: the same contradiction, no proxy defined -> reported, never revised.
    assert "quality" not in subjects
    assert mr["evidence"]["quality"]["kind"] == "contradiction_unrevisable"
    assert "not revised" in mr["considered"]["quality"]
    assert mr["card"] == "queued"
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == evolution.REVISE_CARD_KEY))
        assert "contribution_margin -> listing_price_inside_observed_band" in card.action
        assert "quality" not in card.action
    # A revision proposed by the department itself, or argued from the number, is refused
    # by improve.weekly whatever this module does -- the rule is enforced there.
    from brambleloop.improve import weekly
    try:
        weekly.ArchitectureChange(move=weekly.REVISE_METRIC, subject="pricing",
                                  proposed_by="pricing", replaces_metric="contribution_margin",
                                  new_metric="listing_price_inside_observed_band",
                                  because="it fails to measure what the department produces")
    except weekly.WeeklyRefused as exc:
        assert "moved the goalposts" in str(exc)
    else:
        raise AssertionError("a department revised its own metric")


def test_weekly_cycle_with_nothing_to_revise_proposes_nothing_194():
    """No prior cycle rows, no promotions, no proxy rows: every department is considered and
    none is revised. A revision has to come from rows."""
    db = _db()
    out = _run(db, "improve.weekly", "orchestrator")
    mr = out["metric_revisions"]
    assert mr["changes"] == [] and mr["card"] == "none"
    assert mr["history_cycles_read"] == 0
    assert set(mr["considered"]) == set(out["cells_unmeasured"]) and mr["considered"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, "
          f"{fails} failing")
    sys.exit(1 if fails else 0)
