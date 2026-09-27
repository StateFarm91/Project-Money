"""The API+vision acceptance runner proves each step from stored rows, or fails it (#222, #320).

The runner fetches nothing. These tests build the rows a real scan and a real gallery
analysis would leave -- through the same `observe.scan` and `mission.record` paths -- and
check that each step passes only on mandated evidence, that a fixture recorded without the
capability cannot pass anything, and that every filed report carries the provisional grade
naming the decision that is still missing.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import acceptance as A  # noqa: E402
from brambleloop.intel import benchmarks, mission, observe  # noqa: E402

GRANTED = {"ETSY_API_KEY": "k", "ETSY_SHARED_SECRET": "s"}
KEY = benchmarks.MJS_KEY


class _Reader:
    def __init__(self, listings):
        self.listings = listings

    def resolve_shop(self, name):
        return {"shop_id": 4242, "shop_name": benchmarks.MJS_SHOP}

    def catalogue(self, shop_id, **kwargs):
        return list(self.listings)

    def images(self, ref):
        return [{"rank": r, "hex_code": "1F3A2E", "hue": 150, "saturation": 30,
                 "brightness": 22, "is_black_and_white": False,
                 "url_fullxfull": f"https://i.etsystatic.com/{ref}_{r}.jpg"} for r in (1, 2)]

    def videos(self, ref):
        return []


def _listing(i, title, modified=1000):
    return {"listing_id": i, "title": title,
            "price": {"amount": 850, "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
            "last_modified_timestamp": modified, "num_favorers": 10, "taxonomy_id": 66,
            "url": f"https://www.etsy.com/listing/{i}"}


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    benchmarks.seed(db)
    return db


def _observe_image(db, ref, rank, env=GRANTED):
    mission.record(db, benchmark_key=KEY, kind="gallery_image_observation", listing_ref=ref,
                   detail={"image": {"listing_ref": ref, "rank": rank},
                           "observation": {"shot_type": "flat_lay"}}, env=env)


def _full_history(env=GRANTED) -> Database:
    db = _db()
    listings = [_listing(1, "Cropped Striped Cardigan"), _listing(2, "Chunky Throw Blanket")]
    observe.scan(db, _Reader(listings), env=env)                      # baseline
    listings[0] = _listing(1, "Cropped Striped Cardigan Pattern Sizes XS-5X", modified=2000)
    observe.scan(db, _Reader(listings), env=env)                      # a change, re-audited
    _observe_image(db, "1", 1, env)
    _observe_image(db, "2", 1, env)
    return db


def test_every_step_passes_on_mandated_stored_evidence_and_files_one_report_each():
    db = _full_history()
    out = A.run(db, job_id=7, env=GRANTED)
    assert out["verdict"] == "PASS", out["failed_steps"]
    assert out["passed"] == out["of"] == len(A.STEPS) == 9
    assert out["failed_steps"] == []
    assert out["grade"].startswith("mandated") and "B-105" in out["grade"]
    assert len(out["observation_ids"]) == len(A.STEPS)

    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkObservation
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.kind == A.EVIDENCE_KIND)))
    assert len(rows) == len(A.STEPS)
    for r in rows:
        mission.check_report(r.detail)            # each is a real #319 mission report
        assert r.detail["grade_provisional"] is True
        assert "B-105" in r.detail["provisional_note"]
        assert r.detail["evidence"] is not None and r.detail["job_id"] == 7
    assert {r.detail["acceptance_step"] for r in rows} == set(A.STEPS)


def test_evidence_recorded_without_the_capability_passes_nothing_it_depends_on():
    """A scan and observations stored while no credential existed are supporting only."""
    db = _full_history(env={})
    out = A.run(db, env={})
    for step in ("resolve", "observations", "staleness_change", "re_audit"):
        assert step in out["failed_steps"], step
    assert out["verdict"] == "FAIL" and out["grade"] == "supporting"


def test_an_empty_database_fails_every_step_and_says_why():
    db = Database("sqlite://")
    db.create_all()
    steps = A.evaluate(db)
    assert all(not s.passed for s in steps)
    assert all(s.why for s in steps)
    out = A.run(db, env=GRANTED)
    assert out["verdict"] == "FAIL" and out["passed"] == 0


def test_a_baseline_alone_is_not_a_detected_change_and_stale_coverage_fails():
    db = _db()
    observe.scan(db, _Reader([_listing(1, "Cropped Striped Cardigan"),
                              _listing(2, "Chunky Throw Blanket")]), env=GRANTED)
    steps = {s.name: s for s in A.evaluate(db)}
    assert steps["resolve"].passed and steps["deep_audit"].passed
    assert not steps["staleness_change"].passed and not steps["re_audit"].passed

    later = datetime.now(timezone.utc) + timedelta(hours=A.market_map.STALE_AFTER_HOURS + 1)
    steps = {s.name: s for s in A.evaluate(_full_history(), now=later)}
    assert not steps["staleness_change"].passed
    assert "older than" in steps["staleness_change"].why


def test_the_run_returns_what_the_handler_reads_and_latest_reads_it_back():
    db = _full_history()
    out = A.run(db, env=GRANTED)
    for key in ("verdict", "passed", "of", "failed_steps", "grade"):
        assert key in out
    last = A.latest(db)
    assert last["status"] == "measured" and last["verdict"] == "PASS"
    assert last["of"] == len(A.STEPS)
    empty = Database("sqlite://")
    empty.create_all()
    assert A.latest(empty)["status"] == "UNMEASURED"
    desc = A.describe(db)
    assert desc["evidence_kind"] == "api_gallery_traversal" and desc["requirements"] == [222, 320]


def test_the_runner_touches_no_network_and_the_handler_import_resolves():
    import inspect

    src = inspect.getsource(A)
    for forbidden in ("urllib", "requests", "httpx", "PublicReader", "etsy.com/"):
        assert forbidden not in src.replace("etsy.com/ca/shop", ""), forbidden
    from brambleloop.runtime import release  # noqa: F401  (imports ..intel.acceptance)
    from brambleloop.runtime.worker import handlers
    assert handlers.get("intel.acceptance") is release.handle_intel_acceptance


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
