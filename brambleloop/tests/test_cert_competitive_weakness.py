"""Certification: #33's competitive-weakness factor is measured, not declared sourceless.

The seasonal engine had left "competitive weakness" permanently unmeasured with the note that
no source measured it. Once the API search index was captured (C-40, #2/#15) that stopped
being true: the index's listing count for an occasion's own query is a measured reading of
how crowded it is. These tests drive the daily engine run on recorded snapshots.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import SerpSnapshot  # noqa: E402
from brambleloop.intel import serp  # noqa: E402
from brambleloop.seasonal import daily  # noqa: E402

TODAY = date(2026, 9, 27)


def _db(counts: dict[str, int]):
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/cw.sqlite")
    db.create_all()
    with db.session() as s:
        for word, n in counts.items():
            s.add(SerpSnapshot(query=serp.query_for(word), total_count=n, rank_list=[],
                               basis=serp.DENSITY_BASIS if hasattr(serp, "DENSITY_BASIS")
                               else "api_index_count"))
    return db


def _factors(out: dict) -> dict:
    rows = {}
    for u in out["engine"]["unscored"]:
        rows[u["event"]] = u["measured"]
    for o in out["engine"].get("scored_detail", []):
        rows[o["event"]] = o["factors"]
    return rows


def test_every_seasonal_event_has_a_capture_query():
    targets = {t["query"] for t in serp.target_queries()}
    for word in ("christmas", "halloween", "thanksgiving", "valentine", "easter", "mother"):
        assert serp.query_for(word) in targets, word


def test_competitive_weakness_is_measured_relative_to_the_most_crowded_occasion():
    out = daily.run(_db({"christmas": 40000, "halloween": 10000}), today=TODAY)
    weak = {}
    for u in out["engine"]["unscored"]:
        if "competitive_weakness" in u["measured"]:
            weak[u["event"]] = u["measured"]["competitive_weakness"]
    assert weak.get("Christmas") == 0.0, weak          # the most crowded occasion
    assert weak.get("Halloween") == 0.75, weak         # a quarter of Christmas's listings
    # An occasion whose query was never captured is unmeasured, not "no competition".
    easter = next(u for u in out["engine"]["unscored"] if u["event"] == "Easter")
    assert "competitive_weakness" in easter["unmeasured"], easter


def test_with_no_capture_every_occasion_stays_unmeasured():
    out = daily.run(_db({}), today=TODAY)
    _vac_68 = 0
    for u in out["engine"]["unscored"]:
        _vac_68 += 1
        assert "competitive_weakness" in u["unmeasured"], u
    assert _vac_68, "out['engine']['unscored'] was empty: the loop proved nothing (F-123)"


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
