"""The SERP laboratory: the API search index, read the sanctioned way and labelled honestly.

#15 asks what wins in search for the target queries. The one sanctioned route is Etsy's
`findAllListingsActive` on the API key alone, and what it returns is the API index's
`sort_on=score` order and result count -- not the rendered etsy.com page. Every test below
holds one of the ways that distinction, or the allowlist discipline around it, could slip.
No test makes a network call: the reader runs over a scripted transport.
"""
from __future__ import annotations

import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, SerpSnapshot  # noqa: E402
from brambleloop.gateway import anthropic as GW  # noqa: E402
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402
from brambleloop.intel import etsy_public as ep  # noqa: E402
from brambleloop.intel import learning, serp  # noqa: E402

ENV = {ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/serp.sqlite")
    db.create_all()
    return db


@dataclass
class _R:
    status: int
    body: dict
    headers: dict


class _Stub:
    """Answers the search endpoint and the images endpoint from a script. Records requests."""

    def __init__(self, ids=(11, 12, 13, 14), count=5321, extra=None):
        self.ids = list(ids)
        self.count = count
        self.extra = extra or {}
        self.requests: list[tuple[str, dict]] = []

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        self.requests.append((url, dict(headers)))
        path = urllib.parse.urlparse(url).path
        if path == "/v3/application/listings/active":
            results = [{"listing_id": i, "shop_id": 900 + i,
                        "price": {"amount": 500 + i, "divisor": 100, "currency_code": "USD"},
                        "num_favorers": i * 3, **self.extra.get(i, {})} for i in self.ids]
            return _R(200, {"count": self.count, "results": results}, {})
        if path.endswith("/images"):
            lid = int(path.split("/")[-2])
            return _R(200, {"results": [
                {"rank": 2, "url_570xN": f"https://i.etsystatic.com/{lid}-b.jpg"},
                {"rank": 1, "url_570xN": f"https://i.etsystatic.com/{lid}-a.jpg"}]}, {})
        return _R(404, {}, {})


def _reader(stub: _Stub) -> ep.PublicReader:
    return ep.PublicReader(stub, env=ENV, sleep=lambda _s: None)


# ---- the allowlist addition ------------------------------------------------


def test_the_search_endpoint_is_allowlisted_on_the_api_key_alone():
    assert ep.ALLOWED["search_listings"] == "/v3/application/listings/active"
    stub = _Stub()
    _reader(stub).search("crochet hat pattern", taxonomy_id=1234, sort_on="score",
                         limit=25, offset=50)
    url, headers = stub.requests[0]
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert query["keywords"] == "crochet hat pattern"
    assert query["taxonomy_id"] == "1234" and query["sort_on"] == "score"
    assert query["limit"] == "25" and query["offset"] == "50"
    assert not any(k.lower() == "authorization" for k in headers), headers
    assert headers["x-api-key"] == "k:s"
    assert ep.capability_report({})["oauth_scopes_requested"] == []


def test_an_undeclared_ordering_or_an_unscoped_search_is_refused():
    reader = _reader(_Stub())
    for call in (lambda: reader.search("hat", sort_on="views"),
                 lambda: reader.search("")):
        try:
            call()
        except ep.EndpointRefused:
            pass
        else:
            raise AssertionError("an undeclared search shape was sent")
    assert reader.calls == []


# ---- capture ---------------------------------------------------------------


def test_a_snapshot_records_rank_price_images_and_its_basis():
    db = _db()
    stub = _Stub(extra={12: {"is_sale": True}})
    out = serp.capture(db, _reader(stub), "crochet hat pattern", detail_top=2)

    assert out["basis"] == "api_index_score_sort" and out["total_count"] == 5321
    with db.session() as s:
        row = s.get(SerpSnapshot, out["id"])
        ranks = row.rank_list
        assert row.basis == "api_index_score_sort" and row.total_count == 5321
    assert [e["rank"] for e in ranks] == [1, 2, 3, 4]
    assert ranks[0]["price"] == 5.11 and ranks[0]["favourites"] == 33
    assert ranks[0]["image_count"] == 2
    assert ranks[0]["thumbnail_url"].endswith("11-a.jpg"), "the thumbnail is rank 1"
    # Past the detail depth, the gallery is unmeasured -- not zero images.
    assert ranks[3]["image_count"] is None
    # A sale flag the API did not send is unknown, not "not on sale".
    assert ranks[1]["has_sale"] is True and ranks[0]["has_sale"] is None


def test_no_credential_captures_nothing_and_says_why():
    db = _db()
    out = serp.capture_targets(db, env={})
    assert out["ran"] is False and "not both set" in out["reason"]
    with db.session() as s:
        assert s.query(SerpSnapshot).count() == 0


def test_a_query_captured_recently_is_not_read_again():
    db = _db()
    stub = _Stub()
    targets = [{"query": "crochet hat pattern"}, {"query": "crochet bag pattern"}]
    first = serp.capture_targets(db, reader=_reader(stub), queries=targets)
    assert len(first["captured"]) == 2
    calls = len(stub.requests)
    again = serp.capture_targets(db, reader=_reader(stub), queries=targets)
    assert again["captured"] == [] and len(again["skipped_recent"]) == 2
    assert len(stub.requests) == calls
    later = serp.capture_targets(db, reader=_reader(stub), queries=targets,
                                 now=datetime.now(timezone.utc) + timedelta(days=1))
    assert len(later["captured"]) == 2


def test_target_queries_come_from_the_pod_vocabulary():
    from brambleloop.intel import pods

    targets = serp.target_queries()
    assert {t["pod"] for t in targets} == {p.key for p in pods.PODS}
    for t in targets:
        assert t["keyword"] in pods.BY_KEY[t["pod"]].keywords
        assert t["query"] == f"crochet {t['keyword']} pattern"


# ---- change over time and the search_behaviour domain ----------------------


def _two_snapshots(db):
    t0 = datetime.now(timezone.utc) - timedelta(days=2)
    serp.capture(db, _reader(_Stub(ids=(1, 2, 3, 4), count=100)), "q", detail_top=0, now=t0)
    serp.capture(db, _reader(_Stub(ids=(3, 1, 9, 2), count=120)), "q", detail_top=0,
                 now=t0 + timedelta(days=1))


def test_changes_report_entrants_exits_and_directional_movement():
    db = _db()
    single = _db()
    serp.capture(single, _reader(_Stub()), "q", detail_top=0)
    assert serp.changes(single, "q")["comparable"] is False

    _two_snapshots(db)
    c = serp.changes(db, "q")
    assert c["comparable"] and c["basis"] == "api_index_score_sort"
    assert c["entrants"] == [9] and c["exits"] == [4]
    assert c["moved"] == {"3": 2, "1": -1, "2": -2}
    assert (c["count_from"], c["count_to"]) == (100, 120)


def test_search_behaviour_is_fed_as_a_labelled_proxy_once_a_query_has_moved():
    db = _db()
    today = date.today()
    empty = learning.ingest_search_behaviour(db, today=today)
    assert empty["recorded"] == [] and "stays unobserved" in empty["reason"]

    _two_snapshots(db)
    got = learning.ingest_search_behaviour(db, today=today)
    assert got["recorded"] == ["search_behaviour"] and got["proxy"] is True
    row = learning.observations(db, domain="search_behaviour", today=today)[0]
    assert row["source"] == "serp_laboratory" and row["fresh"]
    assert row["summary"].startswith("proxy, API search index")
    assert learning.ingest_search_behaviour(db, today=today)["recorded"] == []


# ---- thumbnails through the vision path -----------------------------------


class _Seeing:
    name = "anthropic"
    model = GW.VISION_PROBE_MODEL
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen: list[list[str]] = []

    @staticmethod
    def key() -> str:
        return "a-key"

    def see(self, system, prompt, image_urls, *, max_tokens):
        self.seen.append(list(image_urls))
        return ModelResponse(text=self.answers.pop(0), provider=self.name, model=self.model,
                             input_tokens=900, output_tokens=40, latency_ms=10.0)


def test_thumbnails_are_refused_without_demonstrated_vision():
    db = _db()
    snap = serp.capture(db, _reader(_Stub()), "q", detail_top=2)
    seeing = _Seeing([])
    out = serp.score_thumbnails(db, snap["id"], provider=seeing)
    assert out["refused"] is True and "image_vision is unavailable" in out["reason"]
    assert seeing.seen == []


def test_top_thumbnails_are_judged_one_per_call_and_stored_as_composition():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=GW.VISION_PROBE_ACTION,
                       artifact="probe", detail={"ok": True}))
    snap = serp.capture(db, _reader(_Stub()), "q", detail_top=2)
    seeing = _Seeing(['{"shot_type": "flat_lay", "thumbnail_readability": "clear"}',
                      '{"shot_type": "in_use"}'])
    out = serp.score_thumbnails(db, snap["id"], top_n=3, provider=seeing)
    # Only the two top listings whose gallery was read have a thumbnail URL to look at.
    assert out["judged"] == 2 and out["attempted"] == 2
    assert all(len(call) == 1 for call in seeing.seen)
    assert out["shot_types_in_top"] == {"flat_lay": 1, "in_use": 1}
    with db.session() as s:
        thumbs = s.get(SerpSnapshot, snap["id"]).detail["thumbnails"]
    assert thumbs["11"]["composition"]["thumbnail_readability"] == "clear"
    # Already judged is not paid for twice.
    again = serp.score_thumbnails(db, snap["id"], top_n=3, provider=_Seeing([]))
    assert again["attempted"] == 0


# ---- the cadence handler ---------------------------------------------------


def test_the_handler_reports_blocked_without_a_credential():
    import os
    from types import SimpleNamespace

    from brambleloop.runtime import release

    saved = {k: os.environ.pop(k, None) for k in (ep.KEYSTRING_VAR, ep.SECRET_VAR)}
    audits = []
    try:
        ctx = SimpleNamespace(db=_db(), job=SimpleNamespace(id=1, inputs={}),
                              audit=lambda action, **kw: audits.append(action))
        out = release.handle_serp_capture(ctx)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert out["ran"] is False and audits == ["serp.capture_blocked"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
