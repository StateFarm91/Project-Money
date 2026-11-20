"""W4-MARKETINTEL: market intelligence from sanctioned sources, labelled, and routed.

The owner: "I do not want to manually collect Etsy search terms, screenshots or competitor
data." These tests check five things:
- the company collects what Etsy's API allows;
- every figure says it is a proxy where it is one;
- the existing consumers (SEO, Creative, Pattern Engineering, Learning experiments, Product
  Truth) read the routed findings in a scratch run;
- the one thing only the owner can see (Marketplace Insights) is a paste on a phone page,
  parsed deterministically;
- Etsy's limit is recorded from its own OpenAPI document.

No test makes a network call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_marketintel.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import re
import os
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EV = ROOT / "research/final_build/w4/evidence_MARKETINTEL"
OPS = "m" * 40
Q = "crochet blanket pattern"


def ok(msg: str) -> None:
    print(f"  ok  {msg}")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/mi.sqlite")
    db.create_all()
    return db


@dataclass
class _R:
    status: int
    body: dict
    headers: dict


class _Stub:
    def __init__(self, status=200, favs=None, count=5000, created=None):
        self.status, self.favs, self.count = status, favs or {}, count
        self.created = created or {}
        self.requests: list[str] = []

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        self.requests.append(url)
        if self.status != 200:
            return _R(self.status, {"error": "refused"}, {})
        path = urllib.parse.urlparse(url).path
        if path == "/v3/application/listings/active":
            res = [{"listing_id": i, "shop_id": 900 + i, "title": "Crochet blanket pattern",
                    "taxonomy_id": 1, "num_favorers": f,
                    "original_creation_timestamp": self.created.get(i),
                    "price": {"amount": 600, "divisor": 100, "currency_code": "USD"}}
                   for i, f in self.favs.items()]
            return _R(200, {"count": self.count, "results": res}, {})
        return _R(200, {"results": []}, {})


def _reader(stub):
    from brambleloop.intel import etsy_public as ep

    return ep.PublicReader(stub, env={ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"},
                           sleep=lambda _s: None)


def _two_snapshots(db):
    from brambleloop.intel import serp

    t0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    recent = int((t0 + timedelta(days=2)).timestamp()) - 10 * 86400
    old = int(t0.timestamp()) - 400 * 86400
    serp.capture(db, _reader(_Stub(favs={1: 100, 2: 50, 3: 10}, count=5000)), Q, now=t0)
    serp.capture(db, _reader(_Stub(favs={1: 110, 2: 56, 3: 10, 4: 3}, count=5200,
                                   created={1: old, 2: old, 3: recent, 4: recent})), Q,
                 now=t0 + timedelta(days=2))


# ---- 1. Etsy's limit, from its own document --------------------------------------------------

def test_etsy_publishes_no_insights_or_search_volume_api():
    from brambleloop.intel import etsy_surfaces, market_intel

    facts = json.loads((EV / "etsy_openapi_facts_2026-10-11.json").read_text())
    for term in ("insight", "stats", "statistic", "search volume", "traffic", "impression"):
        assert facts["term_counts"][term] == 0, (term, facts["term_counts"][term])
    assert etsy_surfaces.ABSENCE_PROBES["insight"][0] == 0
    search_ops = [o for o in facts["operation_ids"]
                  if re.search(r"search|insight|stats\b|statistic|traffic|visit", o, re.I)]
    assert search_ops == [], search_ops
    assert "keywords" in facts["findAllListingsActive"]["parameters"]
    assert "only for active listings" in facts["views_field"]["description"]
    assert "'insight' 0" in market_intel.ETSY_LIMIT
    ok("Etsy OpenAPI 3.0.0 (2026-10-11): no insights/stats/search-volume operation")


# ---- 2. collection -------------------------------------------------------------------------

def test_capture_stores_creation_time_and_stops_on_a_refused_credential():
    from brambleloop.intel import serp

    db = _db()
    _two_snapshots(db)
    snap = serp.latest(db, Q, n=1)[0]
    assert {e["listing_id"]: e["created_ts"] for e in snap.rank_list}[3] is not None
    stub = _Stub(status=403)
    out = serp.capture_targets(db, reader=_reader(stub))
    assert out["ran"] is False and out["credential_refused"] is True, out
    assert len(stub.requests) == 1, len(stub.requests)  # not every target query
    ok("creation time captured; a 403 stops the run after one request")


# ---- 3. labelled signals -------------------------------------------------------------------

def test_every_figure_is_labelled_and_unknown_is_never_zero():
    from brambleloop.intel import market_intel as MI

    db = _db()
    _two_snapshots(db)
    r = MI.query_signals(db, Q, pod="blankets")
    m = r["metrics"]
    assert m["competition"]["value"] == 5200 and m["competition"]["kind"] == MI.PROXY
    assert m["competition_change"]["value"] == 200
    assert m["favourite_velocity"]["value"] == 3.0, m["favourite_velocity"]  # (10,6,0)/2 -> 3
    assert m["recent_entrant_share"]["value"] == 0.5
    assert m["insights_search_count"]["value"] is None
    assert m["insights_search_count"]["unknown_because"]
    for k, v in m.items():
        assert v["source"] and "search volume" not in v["label"].lower() or v["kind"] == "MEASURED"
        if v["kind"] == MI.PROXY:
            assert "findAllListingsActive" in v["source"], v
    none = MI.query_signals(db, "crochet sock pattern")
    assert all(v["value"] is None and v["unknown_because"] for v in none["metrics"].values())
    ok("competition/velocity/entrants are PROXY with source+time; absent is UNKNOWN, not 0")


# ---- 4. routing, read by the existing consumers in a scratch run ---------------------------

def test_findings_reach_seo_creative_engineering_and_learning():
    from brambleloop.growth import experiments as X
    from brambleloop.improve import bus, consume
    from brambleloop.intel import market_intel as MI
    from brambleloop.seo import evidence

    db = _db()
    _two_snapshots(db)
    out = MI.refresh(db)
    assert out["lessons"] and Q in out["opportunities"], out
    seo = consume.matching(db, "seo_search", "Crochet blanket pattern, textured throw PDF")
    assert any(l["evidence_ref"].startswith("market_intel:query:") for l in seo), seo
    eng = consume.matching(db, "pattern_engineering", "blankets crochet blanket pattern concept")
    assert any(l["evidence_ref"].startswith("market_intel:opportunity:") for l in eng), eng
    brief = bus.brief_lessons(db, artifact="ideation:test:blankets")
    text = json.dumps(brief, default=str)
    assert "market_intel" in text or "Market proxy" in text, text[:500]
    exp = X.load(db, "market_intel:crochet-blanket-pattern")
    assert exp.gated_on == "live_listings"
    rows = [r for r in evidence.collect(db) if r["source"] == "intel.market_intel"]
    assert {r["use"] for r in rows} == {"proxy:demand_interest", "proxy:market_entry"}, rows
    again = MI.refresh(db)
    assert again["lessons"] == out["lessons"]  # unchanged numbers republish nothing new
    ok("SEO, Creative brief, Pattern Engineering, growth experiment and SEO evidence read it")


def test_product_truth_refuses_demand_claims():
    from brambleloop.seo import facts as F, truth
    from brambleloop.store_foundation import lint

    codes = {f["code"] for f in lint.lint("A trending crochet blanket, in demand now")}
    assert "TRUTH_MARKET_CLAIM" in codes, codes
    assert "TRUTH_MARKET_CLAIM" not in {f["code"] for f in lint.lint("A crochet blanket")}
    pf = F.launch0_facts()[0]
    v = truth.check_term("trending blanket", pf, competitors=[])
    assert any("claims market demand" in f for f in v.findings), v.findings
    ok("'trending'/'in demand' refused by store lint and by the SEO tag validator")


# ---- 5. the owner's one step ---------------------------------------------------------------

PASTE = """Search term: crochet blanket pattern
Searches 12.4K
Listings 85,321
Trend: up
Related searches
granny square blanket 3.1K
mosaic blanket pattern 950
Some banner text Etsy shows
Search term: crochet stocking pattern
Searches 2,100
"""


def test_paste_is_parsed_deterministically_and_recorded_only_on_confirm():
    from brambleloop.build2 import executor as E
    from brambleloop.intel import market_intel as MI

    p = MI.parse_insights(PASTE)
    a, b = p["readings"]
    assert (a["keyword"], a["search_count"], a["listing_count"], a["trend_direction"]) == (
        "crochet blanket pattern", 12400, 85321, "up"), a
    assert a["related_terms"] == ["granny square blanket", "mosaic blanket pattern"], a
    assert p["unparsed"] == ["Some banner text Etsy shows"], p["unparsed"]
    assert b["search_count"] == 2100
    db = _db()
    MI.record_paste(db, PASTE, recorded_by="owner")
    assert E.GATE_BY_KEY["insights_access"].open(db, {}) is False
    out = MI.record_paste(db, PASTE, recorded_by="owner", confirm=True)
    assert len(out["recorded"]) == 2 and out["digest"]
    assert E.GATE_BY_KEY["insights_access"].open(db, {}) is True
    r = MI.query_signals(db, Q)["metrics"]["insights_search_count"]
    assert r["value"] == 12400 and r["kind"] == "MEASURED" and "owner" in r["source"]
    ok("paste -> parse preview -> confirm records InsightsSnapshot; gate opens")


def test_routes_are_operator_gated_and_the_phone_page_has_no_inline_script():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.core import opsauth

    os.environ[opsauth.TOKEN_VAR] = OPS
    main.db.create_all()
    c = TestClient(main.app)
    assert c.post("/api/insights/paste", json={"text": PASTE}).status_code == 401
    h = {"Authorization": f"Bearer {OPS}"}
    r = c.post("/api/insights/paste", json={"text": PASTE, "recorded_by": "owner"}, headers=h)
    assert r.status_code == 200 and r.json()["confirmed"] is False, r.text
    r = c.get("/ops/insights", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/ops/teardown#insights"
    page = c.get("/ops/teardown").text
    assert 'id="insights"' in page and 'id="ins-text"' in page
    assert page.count("<script") == 1  # the one script the page policy allows
    js = c.get("/ops/teardown.js").text
    assert "/api/insights/paste" in js and "localStorage.setItem" not in js
    # W4-SECFIX: the payload carries the owner's Insights readings -> operator credential.
    assert c.get("/api/market-intel").status_code == 401
    assert c.get("/api/market-intel", headers=h).status_code == 200
    ok("paste route 401 without the operator token; Insights paste lives on the one allowed ops page")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {exc}")
        else:
            print(f"OK   {t.__name__}")  # run_tests.sh counts ^OK lines
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
