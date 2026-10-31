"""OPUS2-P0: P0-LEARNING-GAPS -- knowledge gaps become owner-approved reference recommendations.

Owner directive 2026-10-31 §3 items 17-18 and §4: gaps are counted from our own evidence
(empty product lines, drafting refusals, failed compiles, library coverage) and the shortlist
is one listing per uncovered pod, capped, never bought. Everything here is real except the
listing picker, which reads marketplace observations this offline database does not hold.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_knowledge_gaps.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, BenchmarkProduct, OperatingReading,  # noqa: E402
                                     OwnerAction, PatternVersion, Product)
from brambleloop.intel import knowledge_gaps as K  # noqa: E402

TODAY = date(2026, 10, 31)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_kg_')}/k.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _picker(prices=None):
    calls = []

    def pick(db, pod):
        calls.append(pod)
        if prices is not None and pod not in prices:
            return None
        return {"benchmark": "fixture", "listing_ref": f"L-{pod}", "title": f"A {pod} pattern",
                "price_cad": (prices or {}).get(pod, 7.5), "answers": "how it is constructed",
                "url": f"https://example.invalid/{pod}"}
    pick.calls = calls
    return pick


def _refuse(db, slug, category, needs="a construction"):
    with db.session() as s:
        s.add(AuditLog(actor="crochet_engineer", action="cir.draft_refused", artifact=slug,
                       detail={"gate": "construction", "category": category, "needs": needs}))


def _certify(db, slug):
    with db.session() as s:
        p = Product(slug=slug, title=slug, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True))


def test_every_owner_line_has_a_pod_and_no_category_belongs_to_two_lines():
    from brambleloop.intel import pods

    assert len(K.LINES) == 12
    keys = set(pods.POD_KEYS)
    seen = {}
    for ln in K.LINES:
        assert ln.pod in keys, ln
        for c in ln.categories:
            assert c not in seen, (c, seen.get(c), ln.key)
            seen[c] = ln.key


def test_construction_refusals_rank_the_gap_and_one_capped_recommendation_is_raised():
    db = _db()
    for slug in ("woodland-fox-amigurumi", "no-sew-reindeer", "pocket-penguin-trio"):
        _refuse(db, slug, "amigurumi", "shaped pieces worked in the round")
    pick = _picker()
    out = K.assess(db, today=TODAY, pick=pick)
    top = out["gaps"][0]
    assert top["line"] == "amigurumi" and top["score"] == K.W_NO_CERTIFIED + 3, top
    assert top["refused"] == ["woodland-fox-amigurumi", "no-sew-reindeer",
                              "pocket-penguin-trio"]
    assert len(out["raised"]) == K.MAX_OPEN and out["raised"][0]["line"] == "amigurumi"
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{K.ACTION_PREFIX}%"))))
    assert len(rows) == K.MAX_OPEN
    ami = next(r for r in rows if r.requirement_key == "knowledge_gap:amigurumi")
    assert ami.max_cost_cad == 7.5 and "Approve buying" in ami.action
    assert "shaped pieces" not in ami.action and "3 concept(s) refused" in ami.reason
    # One pod is never asked for twice, even by two lines that share it.
    line_pod = {ln.key: ln.pod for ln in K.LINES}
    pods_asked = [line_pod[r["line"]] for r in out["raised"]]
    assert len(set(pods_asked)) == len(pods_asked), pods_asked
    # Re-running asks nothing again and records why.
    again = K.assess(db, today=TODAY, pick=pick)
    assert again["raised"] == [] and any("already asked" in h["why"] for h in again["held"])
    with db.session() as s:
        assert s.scalar(select(OperatingReading).where(
            OperatingReading.kind == K.KIND)).payload["gaps"]
    assert K.latest(db)["as_of"] == TODAY.isoformat()


def test_a_line_the_library_covers_or_that_has_no_listing_asks_for_nothing():
    db = _db()
    _refuse(db, "woodland-fox-amigurumi", "amigurumi")
    with db.session() as s:
        s.add(BenchmarkProduct(ref="b-ami", seller="fixture", title="owned", pod="amigurumi"))
    out = K.assess(db, today=TODAY, pick=_picker(prices={}))
    assert out["raised"] == []
    reasons = {u["line"]: u["why"] for u in out["unrecommended"]}
    assert "already holds" in reasons["amigurumi"]
    assert all("never asked to go and find one" in w for line, w in reasons.items()
               if line != "amigurumi")


def test_a_certified_line_scores_lower_than_an_empty_one_and_scores_recompute():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    ev = K.evidence(db, today=TODAY)
    assert ev["blankets_throws"]["certified"] == 1
    gaps = {g["line"]: g for g in K.gaps(db, today=TODAY)}
    assert "blankets_throws" not in gaps and gaps["amigurumi"]["score"] == K.W_NO_CERTIFIED
    for g in gaps.values():
        assert g["score"] == K.score(ev[g["line"]])


def test_the_job_is_scheduled_registered_and_never_spends():
    from brambleloop.authority import classes
    from brambleloop.runtime import worker
    from brambleloop.runtime.worker import handlers

    cad = [c for c in worker.CADENCES if c[2] == "learning.knowledge_gaps"]
    assert cad and cad[0][3] == 7 * 24 * 60 * 60, cad
    assert handlers.get("learning.knowledge_gaps") is not None
    assert classes.JOB_CLASS["learning.knowledge_gaps"] == classes.JOB_CLASS[
        "improve.commercial_lessons"]
    assert not classes.is_gated("learning.knowledge_gaps")


def test_a_real_drafting_refusal_becomes_the_lines_gap():
    """The handoff end to end: `cir.draft` refuses a shaped concept by name, and that refusal
    is the evidence the gap engine counts."""
    import dataclasses
    from types import SimpleNamespace

    from brambleloop.runtime import pipeline

    db = _db()
    seed = pipeline._seed_for("woodland-fox-amigurumi")
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))

    def audit(action, artifact=None, detail=None, **_):
        with db.session() as s:
            s.add(AuditLog(actor="crochet_engineer", action=action, artifact=artifact,
                           detail=detail or {}))
    ctx = SimpleNamespace(db=db, job=SimpleNamespace(inputs=inputs), audit=audit,
                          enqueue=lambda *a, **k: None)
    out = pipeline.handle_cir_draft(ctx)
    assert out["drafted"] is False and out.get("gate") == "construction", out
    gap = next(g for g in K.gaps(db, today=date.today()) if g["line"] == "amigurumi")
    assert gap["construction_refusals"] == 1 and gap["refused"] == [seed.slug]
    assert gap["needs"] and "in the round" in gap["needs"][0]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
