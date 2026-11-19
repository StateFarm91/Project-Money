"""ENG-CATALOGUE fix round 1 (performance): a cold catalogue read at production scale -- 600
products, 70k jobs, 150k audit rows -- must not be O(products x jobs). The measured defect was
6.4-6.9 s on PG; the target is under 1 s there, and this test holds a generous bound on SQLite.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_eng_catalogue_perf.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="test_eng_catalogue_perf_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'c.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import func, select  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import catalogue as C  # noqa: E402
from brambleloop.app.command_center import production as PROD  # noqa: E402
from brambleloop.core import listing_state  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing,  # noqa: E402
                                     OwnerAction, PatternVersion, Product)
from brambleloop.ops import flow_health  # noqa: E402
from brambleloop.products import production_inventory as PI  # noqa: E402

main.db.create_all()
DB = main.db
NOW = datetime.now(timezone.utc)

PRODUCTS, JOBS, AUDITS = 600, 70_000, 150_000
BOUND_SECONDS = 5.0     # generous: the pre-fix cold read was 7.7 s here, ~3.2 s now


def _seed():
    from sqlalchemy import insert

    with DB.session() as s:
        for i in range(PRODUCTS):
            p = Product(slug=f"perf-{i:04d}", title=f"Perf {i:04d}")
            s.add(p)
            s.flush()
            for v in (("1.0.0", "1.1.0") if i % 3 == 0 else ("1.0.0",)):
                s.add(PatternVersion(product_id=p.id, version=v, cir_json={}, certified=False))
        s.commit()
    types = ("cir.compile", "gate.certify", "assets.build", "listing.seo", "store.publish")
    rows = [{"agent": "w", "job_type": types[n % 5], "status": JobStatus.DONE,
             "inputs": {"slug": f"perf-{n % PRODUCTS:04d}", "version": "1.0.0", "n": n},
             "outputs": {}, "priority": 100, "attempts": 1, "max_attempts": 3,
             "run_after": NOW, "created_at": NOW, "finished_at": NOW, "cost_cad": 0.0}
            for n in range(JOBS)]
    actions = ("assets.built", "listing.seo_drafted", "quality.reverified", "store.release_gates",
               "listing.parity")
    audits = [{"actor": "t", "action": actions[n % 5],
               "artifact": f"perf-{n % PRODUCTS:04d}@1.0.0", "detail": {"version": "1.0.0"},
               "at": NOW} for n in range(AUDITS)]
    with DB.session() as s:
        for k in range(0, JOBS, 5000):
            s.execute(insert(Job), rows[k:k + 5000])
        for k in range(0, AUDITS, 10000):
            s.execute(insert(AuditLog), audits[k:k + 10000])
        s.commit()


_seed()


def _timed_cold():
    C.reset()
    PROD.reset()
    t0 = time.perf_counter()
    v = C.view(DB, {})
    return time.perf_counter() - t0, v


def test_cold_catalogue_read_at_production_scale_is_not_quadratic():
    took, v = _timed_cold()
    assert v["status"] == "OK", v.get("reason")
    assert v["totals"]["products"] == PRODUCTS
    assert v["totals"]["versions"] == PRODUCTS + PRODUCTS // 3
    print(f"cold catalogue read: {took:.2f}s ({PRODUCTS} products, {JOBS} jobs, {AUDITS} audits)")
    assert took < BOUND_SECONDS, f"{took:.1f}s cold read: per-product scans of all jobs/audits"


def test_the_per_product_lookups_use_the_grouped_index_not_a_scan():
    rec = PI.load_records(DB)
    ix = PI._ix(rec)
    assert sum(len(v) for v in ix["jobs"].values()) == JOBS
    assert len(ix["audits"]) == PRODUCTS
    t0 = time.perf_counter()
    for slug in [f"perf-{i:04d}" for i in range(PRODUCTS)]:
        PI._jobs_for(rec, slug, "1.0.0", True)
        PI._audits_for(rec, slug, "1.0.0", PI.AUDIT_ACTIONS)
    assert time.perf_counter() - t0 < 1.0


if __name__ == "__main__":
    failed = passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
