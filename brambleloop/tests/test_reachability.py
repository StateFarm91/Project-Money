"""The runtime-reachability rule (C-65): a call graph from what executes, not a name search.

A synthetic package is laid out in a temporary directory with one module per blind spot the
9434c53 audit found, and the analysis is pointed at it. Each module is reached or not for
exactly one reason, so a regression in the rule shows as one named module changing verdict.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import reachability as R  # noqa: E402

FILES = {
    "__init__.py": "",
    "runtime/__init__.py": "",
    "runtime/worker.py": """
        class HandlerRegistry:
            def register(self, job_type):
                def deco(fn):
                    return fn
                return deco
        handlers = HandlerRegistry()
        CADENCES = [
            ("nightly", "orchestrator", "x.nightly", 86400),
        ]
    """,
    "runtime/release.py": """
        from .worker import handlers
        from ..lib import live, auditonly, writer, helperchain

        @handlers.register("x.nightly")
        def nightly(ctx):
            result = live.compute(ctx.db)
            if result:
                ctx.enqueue("orchestrator", "x.downstream", {})
            ctx.audit("x.receipt", detail=auditonly.describe())
            ctx.audit("x.written", detail=writer.record(ctx.db))
            summary = auditonly.summarise()
            ctx.audit("x.summary", detail=summary)
            return {"n": helperchain.first(ctx.db)}

        @handlers.register("x.downstream")
        def downstream(ctx):
            from ..lib import enqueued
            return enqueued.act(ctx.db)

        @handlers.register("x.manual")
        def manual(ctx):
            from ..lib import manualonly
            return manualonly.go(ctx.db)
    """,
    "app/__init__.py": "",
    "app/main.py": """
        from ..lib import static, dbroute, guard
        db = object()
        app = object()

        @app.get("/api/static")
        def api_static():
            return static.state()

        @app.get("/api/db")
        def api_db():
            with db.session() as s:
                rows = s.scalars("q")
                return dbroute.summarise(rows)

        @app.post("/api/manual")
        def api_manual(authorization: str = ""):
            try:
                guard.check(authorization)
            except guard.Refused:
                return {"refused": True}
            from ..queue import q
            q.JobQueue(db).enqueue("orchestrator", "x.manual", {})
            return {}
    """,
    "queue/__init__.py": "",
    "queue/q.py": """
        class JobQueue:
            def __init__(self, db):
                self.db = db
            def enqueue(self, agent, job_type, inputs):
                self.db.add((agent, job_type))
    """,
    "lib/__init__.py": "",
    "lib/live.py": "def compute(db):\n    return db.read()\n",
    "lib/auditonly.py": "def describe():\n    return {'a': 1}\ndef summarise():\n    return 2\n",
    "lib/writer.py": "def record(db):\n    db.add('row')\n    return {'ok': True}\n",
    "lib/helperchain.py": "from . import deep\ndef first(db):\n    return deep.second(db)\n",
    "lib/deep.py": "def second(db):\n    return 1\n",
    "lib/enqueued.py": "def act(db):\n    return 1\n",
    "lib/manualonly.py": "def go(db):\n    return 1\n",
    "lib/static.py": "RULES = ['a']\ndef state():\n    return {'rules': RULES}\n",
    "lib/dbroute.py": "def summarise(rows):\n    return len(list(rows))\n",
    "lib/guard.py": "class Refused(Exception):\n    pass\ndef check(token):\n    if not token:\n        raise Refused()\n",
    "lib/unimported.py": "def nothing():\n    return 0\n",
}


def _package() -> Path:
    base = Path(tempfile.mkdtemp()) / "brambleloop"
    for rel, body in FILES.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return base


def _with_package(fn):
    real = R.PKG
    R.PKG = _package()
    R.clear_cache()
    try:
        return fn()
    finally:
        R.PKG = real
        R.clear_cache()


def _verdicts() -> dict[str, dict]:
    return _with_package(lambda: {
        rel: R.reached(rel) for rel in FILES if rel.startswith("lib/") and rel != "lib/__init__.py"})


V = None


def _v():
    global V
    if V is None:
        V = _verdicts()
    return V


def test_a_module_called_from_a_scheduled_handler_is_reached():
    assert _v()["lib/live.py"]["reached"], _v()["lib/live.py"]
    assert "x.nightly" in _v()["lib/live.py"]["why"]


def test_reach_is_transitive_through_library_helpers():
    assert _v()["lib/helperchain.py"]["reached"]
    assert _v()["lib/deep.py"]["reached"], _v()["lib/deep.py"]


def test_a_handler_enqueued_by_a_live_handler_is_live():
    assert _v()["lib/enqueued.py"]["reached"], _v()["lib/enqueued.py"]


def test_a_module_used_only_inside_an_audit_receipt_is_not_reached():
    v = _v()["lib/auditonly.py"]
    assert not v["reached"], v


def test_a_writer_whose_receipt_is_audited_is_still_reached():
    """The call is the act; the audit row is only its receipt."""
    assert _v()["lib/writer.py"]["reached"], _v()["lib/writer.py"]


def test_a_module_behind_a_static_state_route_is_not_reached():
    v = _v()["lib/static.py"]
    assert not v["reached"], v


def test_a_route_that_computes_from_the_database_reaches_its_module():
    assert _v()["lib/dbroute.py"]["reached"], _v()["lib/dbroute.py"]


def test_an_auth_guard_in_a_route_is_a_use():
    assert _v()["lib/guard.py"]["reached"], _v()["lib/guard.py"]


def test_a_handler_only_a_manual_post_enqueues_is_not_live():
    v = _v()["lib/manualonly.py"]
    assert not v["reached"], v


def test_a_module_no_root_imports_is_not_reached():
    assert not _v()["lib/unimported.py"]["reached"]


def test_the_real_package_still_reaches_its_handlers_libraries():
    """Guard against the rule being so strict it reaches nothing in the real package."""
    R.clear_cache()
    for rel in ("commerce/kill_table.py", "swarm/orchestrate.py", "ops/artefacts.py"):
        assert R.reached(rel)["reached"], R.reached(rel)
    # The library the 9434c53 audit named as static-route-only (commerce/offers.py) was wired
    # by the C-64 repair: it must now read as reached THROUGH A LIVE ROOT, and the verdict
    # must say which handler, not merely that a route imports it.
    offers = R.reached("commerce/offers.py")
    assert offers["reached"] and "handler " in str(offers.get("why", "")), offers
    # #4 was wired by the residue repair wave: commerce/preproduction.py must now read as
    # reached through the growth.preproduction cadence handler, not merely the route.
    wired = R.reached("commerce/preproduction.py")
    assert wired["reached"] and "handler growth.preproduction" in str(wired.get("why", "")), wired
    # A library that is still only used by an app/main.py route (growth/free_to_paid.py:
    # growth/clusters.py imports one constant from it and /api reads it) stays unreached. If
    # this fires because it got wired, that is a repair working: pick another static-only
    # fixture rather than loosening the rule.
    static_only = R.reached("growth/free_to_paid.py")
    assert not static_only["reached"], ("fixture wired; choose another static-only module",
                                        static_only)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
