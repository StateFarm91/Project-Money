"""ENG-CATALOGUE fix round 1: distinct product counts, current-version stage tiles, the
verified-draft next action, escaped held filter, same-job dead letters, concurrency.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_eng_catalogue_fix1.py
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

_TMP = tempfile.mkdtemp(prefix="test_eng_catalogue_fix1_")
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

def _product(slug, versions, *, certified=True):
    with DB.session() as s:
        p = Product(slug=slug, title=f"Fixture {slug}")
        s.add(p)
        s.flush()
        for v in versions:
            s.add(PatternVersion(product_id=p.id, version=v, cir_json={}, certified=certified,
                                 release_hash=("r" + slug + v)[:60] if certified else None,
                                 certificate={"content_hash": "c" + slug} if certified else None))


def _listing(slug, version, state, eid):
    with DB.session() as s:
        s.add(Listing(product_slug=slug, version=version, title="t", description="d",
                      state=state, release_hash=("r" + slug + version)[:60],
                      etsy_listing_id=eid))


def _seed():
    # Two products, one with two versions (the superseded 1.0.0 had a live listing).
    _product("alpha-two-versions", ["1.0.0"])
    _product("alpha-two-versions-x", [])  # placeholder removed below
    with DB.session() as s:
        s.query(Product).filter_by(slug="alpha-two-versions-x").delete()
    with DB.session() as s:
        p = s.scalar(select(Product).where(Product.slug == "alpha-two-versions"))
        s.add(PatternVersion(product_id=p.id, version="1.1.0", cir_json={}, certified=False))
    _listing("alpha-two-versions", "1.0.0", "active", "EALPHA")
    _product("beta-one-version", ["1.0.0"])
    _listing("beta-one-version", "1.0.0", listing_state.PUBLISHED, "DBETA")   # verified draft
    _product("gamma-live", ["1.0.0"])
    _listing("gamma-live", "1.0.0", "active", "EGAMMA")                      # live
    # A concept-only slug: a research job names it, there is no Product row.
    with DB.session() as s:
        s.add(Job(agent="radar", job_type="radar.score", status=JobStatus.DONE,
                  inputs={"slug": "concept-only-slug"},
                  outputs={"promoted": False, "reason": "below the bar"}, finished_at=NOW))
        s.add(OwnerAction(action="approve the yarn purchase for gamma-live ",
                          requirement_key="fixture-paid", max_cost_cad=9.0))


_seed()


def _view(**p):
    C.reset()
    return C.view(DB, p)


def _sql():
    with DB.session() as s:
        return {"products": s.scalar(select(func.count()).select_from(Product)),
                "distinct": s.scalar(select(func.count(func.distinct(Product.slug)))),
                "versions": s.scalar(select(func.count()).select_from(PatternVersion))}


def test_products_are_distinct_versions_and_concepts_are_counted_apart():
    v = _view()
    assert v["status"] == "OK", v.get("reason")
    t, sql = v["totals"], _sql()
    assert t["products"] == sql["products"] == sql["distinct"] == 3
    assert t["versions"] == sql["versions"] == 4          # alpha has two
    assert t["concepts"] == 1                              # concept-only-slug
    assert t["superseded"] == 1                            # alpha 1.0.0
    assert v["matching"] == 5                              # rows: 4 versions + 1 concept
    # The old figure (rows + concepts) would have said 5 products.
    assert t["products"] != v["matching"]


def test_stage_tiles_count_each_product_once_at_its_current_version():
    t = _view()["totals"]
    # alpha's superseded 1.0.0 is a live listing; its CURRENT 1.1.0 is uncertified.
    assert t["by_stage"]["live_on_etsy"] == 1              # gamma only, not alpha 1.0.0
    assert sum(t["by_stage"].values()) == t["products"] + t["concepts"] == 4
    assert sum(t["by_state"].values()) == 4
    sup = _view(scope="superseded")
    assert [(r["slug"], r["version"], r["stage"], r["current"]) for r in sup["items"]] == \
        [("alpha-two-versions", "1.0.0", "live_on_etsy", False)]
    assert _view(scope="current")["matching"] == 4


def test_the_crosscheck_compares_counts_to_sql_not_just_presence():
    idx = C.build_index(DB)
    assert idx["crosscheck"]["ok"] and idx["crosscheck"]["sql"]["products"] == 3
    # An index that double counts a product (a second "product" slug) must not pass.
    idx["con"].execute("UPDATE cat SET is_product = 1 WHERE slug = 'concept-only-slug'")
    bad = C.crosscheck(DB, idx["con"])
    assert bad["ok"] is False and bad["checks"]["distinct_products_equal_sql"]["ok"] is False
    assert bad["checks"]["distinct_products_equal_sql"]["sql_distinct"] == 3
    assert bad["checks"]["distinct_products_equal_sql"]["index_distinct"] == 4
    idx["crosscheck"] = bad
    out = C.query(idx, {})
    assert out["status"] == C.UNKNOWN and out["totals"]["products"] is None
    # Two current rows for one product is also caught.
    idx2 = C.build_index(DB)
    idx2["con"].execute("UPDATE cat SET head = 1 WHERE slug = 'alpha-two-versions'")
    assert C.crosscheck(DB, idx2["con"])["checks"]["one_current_row_per_product"]["ok"] is False


def test_a_verified_draft_goes_to_owner_activation_only_a_live_row_to_sales_monitoring():
    v = _view()
    row = {(r["slug"], r["version"]): r for r in v["items"]}
    draft = row[("beta-one-version", "1.0.0")]
    assert draft["stage"] == "etsy_draft_verified"
    assert draft["next_action"]["action"] == C.ACTIVATE_ACTION
    assert draft["next_action"]["owner"] == "owner" and draft["next_action"]["job_type"] is None
    assert "monitor" not in draft["next_action"]["action"]
    live = row[("alpha-two-versions", "1.0.0")]
    assert live["next_action"]["action"] == "monitor sales and listing health"
    from brambleloop.autonomy.charters import department_of

    assert live["next_action"]["owner"] == department_of("commerce.orders_ingest")
    # Unit level: no bare literals needed, the helpers read core.listing_state.
    item = {"state": PI.PUBLISHED, "evidence": {}, "holds": []}
    assert C.next_action(item, {"state": listing_state.PUBLISHED, "etsy_listing_id": "D"}
                         )["action"] == C.ACTIVATE_ACTION
    assert C.next_action(item, {"state": listing_state.PUBLISHED_MANUALLY}
                         )["action"].startswith("monitor")
    assert C.next_action(item, None)["action"] == C.UNKNOWN
    assert C.next_action(item, {"state": listing_state.PUBLISHED})["action"] == C.UNKNOWN
    # The draft is counted in the owner's queue, not finance's.
    assert v["totals"]["by_owner"].get("owner", 0) >= 1


def test_held_filter_escapes_like_wildcards():
    everything = _view()["matching"]
    assert _view(held="any")["matching"] >= 1              # the paid hold on gamma-live
    for wild in ("%", "_", "%%", "paid_approval%", "%paid%", "_aid_approval"):
        assert _view(held=wild)["matching"] == 0, wild
    assert _view(held="paid_approval")["matching"] == 1
    assert everything == 5


def _dead(inputs, key=None, status="dead"):
    with DB.session() as s:
        s.add(Job(agent="publishing", job_type="assets.build", inputs=inputs,
                  status=JobStatus(status), created_at=NOW - timedelta(hours=2),
                  run_after=NOW - timedelta(hours=2), idempotency_key=key,
                  finished_at=NOW - timedelta(hours=2),
                  last_error="KeyError: x" if status == "dead" else None))


def _stalls(slug):
    rec = PI.load_records(DB)
    inv = PI.derive(DB, records=rec)
    fl = flow_health.flow(DB, inventory=inv, records=rec)
    return [st for r in fl["rows"] if r["slug"] == slug for st in r["stalls"]
            if st["kind"] == "dead_letter"]


def test_a_dead_letter_is_resolved_only_by_a_later_success_of_the_same_job():
    _product("delta-dead", ["1.0.0"])
    _dead({"slug": "delta-dead", "version": "1.0.0", "terminology": "US"}, key="k-us")
    assert len(_stalls("delta-dead")) == 1
    # A later success of the same TYPE with different inputs/key is a different job.
    _dead({"slug": "delta-dead", "version": "1.0.0", "terminology": "UK"}, key="k-uk",
          status="done")
    assert len(_stalls("delta-dead")) == 1, "another job of the same type resolved it"
    # The same job (same inputs, a retry under a new idempotency key) resolves it.
    _dead({"slug": "delta-dead", "version": "1.0.0", "terminology": "US"}, key="k-us-2",
          status="done")
    assert _stalls("delta-dead") == []


def test_overlapping_reads_do_not_use_a_closed_index():
    C.reset()
    idx = C._index(DB)
    C.reset()                                  # a cold read elsewhere replaces the cache
    out = C.query(idx, {})                     # ... and this read still holds the old index
    assert out["status"] == "OK"
    errors = []

    def reader():
        try:
            for _ in range(15):
                got = C.view(DB, {"page_size": 2})
                assert got["status"] in ("OK", C.UNKNOWN)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    def resetter():
        for _ in range(15):
            C.reset()

    ts = [threading.Thread(target=reader) for _ in range(4)] + [threading.Thread(target=resetter)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []


def test_cold_reads_coalesce_and_share_the_snapshot_with_the_production_view():
    real = PI.load_records
    calls = []

    def counting(db):
        calls.append(1)
        time.sleep(0.05)
        return real(db)

    C.reset()
    PROD.reset()
    with patch.object(PI, "load_records", counting):
        res = []
        ts = [threading.Thread(target=lambda: res.append(C.view(DB, {}))) for _ in range(6)]
        ts += [threading.Thread(target=lambda: res.append(PROD.view(DB))) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    assert len(res) == 8
    assert len(calls) == 1, f"inventory loaded {len(calls)} times; expected once (shared + coalesced)"


def test_service_worker_is_v34_or_later():
    sw = (ROOT / "src/brambleloop/app/command_center/static/sw.js").read_text()
    assert int(re.search(r'const VERSION = "cc-shell-v(\d+)";', sw).group(1)) >= 34


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
