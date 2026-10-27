"""W4-CLOSE6: F-662 Live Company Timeline -- causal stories, not tool-call noise.

  F-662  "human-readable causal activity stream across departments instead of raw tool-call
          noise."

`JobContext.enqueue` now records which job caused each follow-on job (`runtime.lineage`).
`command_center.causal.stories` tells a chain of jobs as one story across departments:
- each step says what happened in words, with its outcome;
- routine scheduled checks that caused nothing are counted, not told;
- a cause that was not recorded is shown as such, never guessed.
The stories are on GET /api/cc/timeline and in the Timeline view.

Local, deterministic; a private handler registry runs through the real Worker and queue.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_timeline.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import causal  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import lineage  # noqa: E402
from brambleloop.core.resilience import PermanentError  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402

SLUG = {"slug": "cloudline-baby-blanket", "version": "1.2.0"}


def _company():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/tl.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    reg = HandlerRegistry()

    @reg.register("cir.compile")
    def _compile(ctx):
        ctx.enqueue("quality_director", "gate.certify", dict(SLUG), idempotency_key="cert")
        return {"ok": True}

    @reg.register("gate.certify")
    def _certify(ctx):
        ctx.enqueue("listing", "listing.seo", dict(SLUG), idempotency_key="seo")
        return {"certified": True}

    @reg.register("listing.seo")
    def _seo(ctx):
        ctx.enqueue("store_operator", "store.publish", dict(SLUG), idempotency_key="pub")
        return {"drafted": True}

    @reg.register("store.publish")
    def _publish(ctx):
        raise PermanentError("capability not enabled: SHADOW mode")

    @reg.register("ops.heartbeat")
    def _beat(ctx):
        return {"alive": True}

    q = JobQueue(db)
    return db, reg, q, Worker(db, "tl", phase=Phase.SHADOW, registry=reg)


def _drain(w):
    n = 0
    while w.run_once() and n < 50:
        n += 1


def test_a_pipeline_run_is_one_causal_story_across_departments():
    db, _reg, q, w = _company()
    q.enqueue("validator", "cir.compile", {"cir": dict(SLUG)},
              idempotency_key="cadence:compile:1")
    for i in range(3):
        q.enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key=f"cadence:hb:{i}")
    _drain(w)
    out = causal.stories(db)
    assert len(out["stories"]) == 1, [s["headline"] for s in out["stories"]]
    st = out["stories"][0]
    assert [s["job_type"] for s in st["steps"]] == ["cir.compile", "gate.certify",
                                                    "listing.seo", "store.publish"]
    assert st["departments"] == sorted({"validator", "quality_director", "listing",
                                        "store_operator"})
    assert st["headline"].startswith("cloudline-baby-blanket 1.2.0: validator compiled "
                                     "the pattern → quality_director certified the release"), \
        st["headline"]
    assert st["outcome"].startswith("store_operator tried to publish to Etsy: stopped"), st
    assert st["cause"] == "scheduled (compile)"
    for prev, step in zip(st["steps"], st["steps"][1:]):
        assert step["caused_by"] == prev["job"], (prev, step)
    assert out["routine"]["count"] == 3 and out["routine"]["by_type"] == {"ops.heartbeat": 3}


def test_an_unrecorded_cause_is_shown_as_such_and_never_blocks_the_work():
    db, _reg, q, w = _company()
    q.enqueue("validator", "cir.compile", {"cir": dict(SLUG)}, idempotency_key="manual")
    with patch.object(lineage, "ensure_table", side_effect=RuntimeError("db busy")):
        _drain(w)
    from sqlalchemy import func, select

    from brambleloop.core.models import Job

    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job)) == 4, "the work all ran"
    out = causal.stories(db)
    causes = sorted(s["cause"] for s in out["stories"])
    assert causes == ["cause not recorded"] * 4, causes
    assert all(len(s["steps"]) == 1 for s in out["stories"]), "unlinked jobs are not merged"


def test_the_timeline_serves_the_stories():
    db, _reg, q, w = _company()
    q.enqueue("validator", "cir.compile", {"cir": dict(SLUG)},
              idempotency_key="cadence:compile:1")
    _drain(w)
    from brambleloop.app.command_center import tabs

    t = tabs.timeline(db, 50)
    assert t["stories"]["status"] == "OK" and len(t["stories"]["stories"]) == 1
    assert t["events"] is not None, "the raw event list is kept beside the stories"
    view = (ROOT / "src/brambleloop/app/command_center/static/js/views/timeline.js").read_text()
    assert "data.stories" in view and "What the company did" in view


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
