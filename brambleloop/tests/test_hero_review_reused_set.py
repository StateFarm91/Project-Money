"""A reused disclosed set whose hero was never described is described on the next build.

Production (cloudline-baby-blanket@1.2.0): parity HERO `unjudged` for good. The hero's blind
review (`visual.hero_review`) ran only when `assets.build` made a NEW disclosed set; a rebuild
of the same release and CIR fingerprint reuses the set and returned before reviewing. A set
first built while `image_vision` was closed (or whose review call failed) was never described
again, so HERO could never be judged. Now the reuse branch describes the hero once when no
successful review of those exact bytes is on file, and never re-buys one that exists.
Stub providers only: no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_hero_review_reused_set.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="hero_reused_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the hero-reuse harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Phase  # noqa: E402
from brambleloop.publish import listing_asset  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import hero_review, parity  # noqa: E402

SLUG = "hexagon-coaster-set"


class _Provider:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.003 * 1.37
    cost_per_1k_output_cad = 0.015 * 1.37

    def __init__(self):
        self.calls = 0

    def see(self, system, prompt, images, max_tokens=0):
        self.calls += 1
        payload = json.dumps({"object_shown": "four hexagon coasters", "object_count": 4,
                              "finished_or_in_progress": "finished", "human_present": False,
                              "text_present": True, "chart_or_diagram": False,
                              "dominant_colours": "cream, wine", "clarity": "clear",
                              "third_party_marks": "none"})

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


def _certified_db(name):
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    cir = pipeline._engineered_cir(SLUG)
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key="cert", priority=0)
    Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
    return db, cir


def _build(db, cir, key):
    JobQueue(db).enqueue("publishing", "assets.build",
                         {"slug": SLUG, "version": cir.version, "release": "",
                          "rebuild": key}, idempotency_key=key, priority=0)
    Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()


def _hero_rows(db):
    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "assets.disclosed_hero_review").order_by(AuditLog.id))]


def _hero(db):
    return parity.assess(listing_asset.frames_for(db, slug=SLUG))["dimensions"][parity.HERO]


def test_reused_set_gets_its_hero_described_once_and_not_rebought():
    db, cir = _certified_db("reuse")
    # 1. first build with image_vision closed: the set is made, the hero is not described
    _build(db, cir, "first")
    first = _hero_rows(db)
    assert first and first[-1]["reviewed"] is False and "closed" in first[-1]["why"], first
    assert _hero(db)["verdict"] == "unjudged"
    sha_before = [f["image"]["sha256"] for f in listing_asset.last(db, slug=SLUG)["frames"]]

    # 2. image_vision opens; the next build reuses the set (same fingerprint)
    p = _Provider()
    real = hero_review.review_disclosed_hero
    hero_review.review_disclosed_hero = (
        lambda db_, slug_, **kw: real(db_, slug_, provider=p, gate_open=True,
                                      store=kw.get("store")))
    try:
        _build(db, cir, "second")
        rows = _hero_rows(db)
        assert len(rows) == len(first) + 1, rows
        assert rows[-1]["reviewed"] is True and rows[-1]["reused_set"] is True, rows[-1]
        assert p.calls == 2, p.calls                      # describe + grid, once
        rec = listing_asset.last(db, slug=SLUG)
        assert [f["image"]["sha256"] for f in rec["frames"]] == sha_before, \
            "the set was reused, not rebuilt"
        assert _hero(db)["verdict"] == "pass", _hero(db)

        # 3. a further build with the review on file for these bytes buys nothing
        _build(db, cir, "third")
        assert p.calls == 2, p.calls
        assert len(_hero_rows(db)) == len(rows)
    finally:
        hero_review.review_disclosed_hero = real


def test_a_failed_review_on_reuse_stays_unjudged_never_pass():
    """UNKNOWN never PASS: a describer that errors leaves HERO unjudged on reuse."""
    db, cir = _certified_db("fail")
    _build(db, cir, "first")
    real = hero_review.review_disclosed_hero

    def boom(*_a, **_k):
        raise RuntimeError("provider unavailable")

    hero_review.review_disclosed_hero = boom
    try:
        _build(db, cir, "second")
        rows = _hero_rows(db)
        assert rows[-1]["reviewed"] is False and "provider unavailable" in rows[-1]["why"]
        assert _hero(db)["verdict"] == "unjudged"
    finally:
        hero_review.review_disclosed_hero = real


if __name__ == "__main__":
    failures = 0
    for name, fn in [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            failures += 1
            print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
