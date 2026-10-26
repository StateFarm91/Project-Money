"""F-601 / F-454 / F-656: department records, domains, and RUN -> GROW -> IMPROVE -> WATCHING."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import charters, departments as D, generators, memory  # noqa: E402
from brambleloop.autonomy import orchestrator  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def boot():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1d-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_every_generatable_job_type_is_classified_deliberately():
    gen = {jt for c in charters.CHARTERS for jt in c.generatable}
    assert gen <= set(D.WORK_CLASS), sorted(gen - set(D.WORK_CLASS))
    assert D.work_class("autonomy.department_review") == D.IMPROVE
    assert D.work_class("seo.cycle") == D.GROW and D.work_class("ops.slo") == D.RUN
    assert D.work_class("brand.new.job") == D.RUN       # unlisted is never deprioritised


def test_twelve_named_departments_report_present_and_missing_truthfully():
    out = D.coverage(boot())
    assert out["total"] == 12
    by = {r["key"]: r for r in out["departments"]}
    assert set(out["incomplete"]) >= {"compliance_policy", "analytics_intelligence"}
    assert by["compliance_policy"]["missing"] == ["backlog", "evidence", "improvement_loop",
                                                   "kpis", "mandate"]
    # FMBATCH2 F-601: the executive department's improvement loop is its own cell now.
    assert by["executive"]["complete"] and "executive" not in out["incomplete"]
    assert by["executive"]["elements"]["improvement_loop"]["value"] == ["executive"]
    fin = by["finance_accounting"]
    assert fin["complete"] and fin["elements"]["backlog"]["value"]["finance.reconcile"] == "RUN"
    for r in out["departments"]:
        if r["charter"]:
            assert r["agents_unregistered"] == [], r["key"]
    assert out["domains_missing"] == ["analytics", "integration"]


def test_pull_order_is_run_then_grow_then_improve():
    db = boot()
    ch = charters.BY_KEY["executive"]

    def cands(db_, charter, snap):
        mk = lambda jt, v: generators.Candidate(            # noqa: E731
            department=charter.key, job_type=jt, value=v, source="review",
            reason="t", fingerprint=f"{jt}:{v}")
        return [mk("autonomy.department_review", 99), mk("scale.trajectory", 50),
                mk("autonomy.morning_handoff", 1)] if charter.key == "executive" else []

    real = generators.candidates
    generators.candidates = cands
    try:
        rep = orchestrator.tick(db, now=NOW, departments=[ch])
    finally:
        generators.candidates = real
    e = rep["departments"]["executive"]
    assert e["state"] == "GENERATED" and e["work_class"] == D.RUN, e
    assert e["queues"] == {"RUN": 1, "GROW": 1, "IMPROVE": 1}
    assert rep["missions"][0]["job_type"] == "autonomy.morning_handoff"


def test_nothing_runnable_is_watching_with_a_recorded_span_and_no_job():
    db = boot()
    ch = charters.BY_KEY["support"]
    real = generators.candidates
    generators.candidates = lambda db_, charter, snap: []
    try:
        r1 = orchestrator.tick(db, now=NOW, departments=[ch])
        r2 = orchestrator.tick(db, now=NOW.replace(hour=13), departments=[ch])
    finally:
        generators.candidates = real
    e = r2["departments"]["support"]
    assert e["mode"] == D.WATCHING and r1["created"] == 0 and r2["created"] == 0
    span = memory.get(db, "department.watching:support")
    assert span["state"] == "watching" and span["body"]["since"] == NOW.isoformat()
    assert span["body"]["last_seen"] == NOW.replace(hour=13).isoformat()
    orchestrator._end_watching(db, "support", NOW.replace(hour=14), "busy")
    assert memory.get(db, "department.watching:support")["state"] == "ended"


def test_review_f11_an_open_watching_span_is_not_rewritten_every_tick():
    db = boot()
    ch = charters.BY_KEY["support"]
    real = generators.candidates
    generators.candidates = lambda db_, charter, snap: []
    try:
        orchestrator.tick(db, now=NOW, departments=[ch])
        first = memory.get(db, "department.watching:support")
        orchestrator.tick(db, now=NOW.replace(minute=15), departments=[ch])
        same = memory.get(db, "department.watching:support")
        orchestrator.tick(db, now=NOW.replace(hour=13, minute=1), departments=[ch])
        later = memory.get(db, "department.watching:support")
    finally:
        generators.candidates = real
    assert same["updated_at"] == first["updated_at"] and same["body"] == first["body"]
    assert later["body"]["last_seen"] == NOW.replace(hour=13, minute=1).isoformat()
    assert later["body"]["since"] == NOW.isoformat()


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
