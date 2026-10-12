"""W4-FM2 / K8 (F-514): the Etsy surface classifications are re-verified against Etsy's API.

`intel.etsy_surfaces` held its verdicts as static code; `commerce.surface_inventory` re-checked
scopes and evidence freshness, but nothing re-checked a *classification* when Etsy's API
changed. `etsy_surfaces.openapi_reverify` recomputes the two inputs every verdict rests on
(cited operations, counted absences) from the current document; `runtime.etsy_ops.
reverify_openapi` (job `etsy.openapi_reverify`) reads the public document read-only, stores the
reading and opens/resolves a drift incident; `surface_inventory.reverify` (served at
/api/etsy/surfaces and run inside the daily shop snapshot) reports never-verified, unreadable,
stale and drifted classifications by name.

Every document below is a TEST FIXTURE served by a fake transport. No network, no Etsy write.
Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_fm2_surface_reverify.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import surface_inventory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident  # noqa: E402
from brambleloop.integrations.etsy import Response  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.runtime.worker import handlers  # noqa: E402

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fm2_surf_')}/t.sqlite")
    db.create_all()
    return db


def _document(*, add=(), drop=(), extra_text="") -> dict:
    """A document with exactly the pinned operations and the pinned absence counts."""
    ops = sorted((es.ETSY_OPERATIONS - set(drop)) | set(add))
    doc = {"openapi": "3.0.0", "info": {"version": "3.0.0", "description": ""},
           "paths": {f"/p{i}": {"get": {"operationId": op}} for i, op in enumerate(ops)}}
    pad: list[str] = []
    import json
    current = json.dumps(doc, ensure_ascii=False, sort_keys=True).lower()
    for term, (expected, _why) in es.ABSENCE_PROBES.items():
        have = current.count(term)
        # An added operation may itself carry a probe term (that is drift, by design).
        assert have <= expected or add, (term, have)
        pad += [term] * max(0, expected - have)
    doc["info"]["description"] = " ".join(pad) + extra_text
    return doc


class _Transport:
    def __init__(self, status=200, body=None, boom=False):
        self.status, self.body, self.boom, self.calls = status, body, boom, 0

    def request(self, method, url, *, headers, **_kw):
        self.calls += 1
        assert method == "GET" and url == es.OPENAPI_URL and not headers
        if self.boom:
            raise OSError("network down")
        return Response(status=self.status, body=self.body or {})


def _incident(db):
    with db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == etsy_ops.OPENAPI_DRIFT)
                       .order_by(Incident.id.desc()))
        if row is not None:
            s.expunge(row)
        return row


def test_the_pinned_document_reverifies_current():
    out = es.openapi_reverify(_document())
    assert out["status"] == es.OPENAPI_CURRENT, out
    assert out["operations"] == len(es.ETSY_OPERATIONS) and not out["affected"], out
    assert not out["absence_drift"] and not out["removed_operations"]


def test_an_ads_api_appearing_names_the_unsupported_surfaces():
    out = es.openapi_reverify(_document(add=["createAdCampaign"],
                                        extra_text=" advertising budget"))
    assert out["status"] == es.OPENAPI_DRIFTED, out
    assert out["added_operations"] == ["createAdCampaign"]
    terms = {d["term"] for d in out["absence_drift"]}
    assert {"advertis", "budget"} <= terms, terms
    affected = {a["surface"]: a for a in out["affected"]}
    unsupported = [s.key for s in es.by_verdict(es.UNSUPPORTED)]
    assert unsupported, "registry carries no UNSUPPORTED surface"
    for key in unsupported:
        assert key in affected, (key, sorted(affected))
    assert any("counted absence moved" in r for a in affected.values() for r in a["reasons"])


def test_a_removed_operation_names_the_surface_that_cites_it():
    citing = [s for s in es.surfaces() if s.operations]
    assert citing, "no surface cites an operation"
    target = citing[0]
    op = target.operations[0]
    out = es.openapi_reverify(_document(drop=[op]))
    assert out["status"] == es.OPENAPI_DRIFTED and op in out["removed_operations"]
    hit = [a for a in out["affected"] if a["surface"] == target.key]
    assert hit and op in hit[0]["reasons"][0], out["affected"]


def test_an_unreadable_document_confirms_nothing():
    for doc in ({}, "not json", {"paths": {}}):
        out = es.openapi_reverify(doc)
        assert out["status"] == es.OPENAPI_UNREADABLE, out


def test_the_job_stores_the_reading_opens_and_resolves_drift_and_reuses_a_fresh_reading():
    db = _db()
    drifted = _Transport(body=_document(add=["createAdCampaign"]))
    out = etsy_ops.reverify_openapi(db, transport=drifted, now=NOW)
    assert out["status"] == es.OPENAPI_DRIFTED and drifted.calls == 1
    row = _incident(db)
    assert row is not None and not row.resolved and row.severity == "P2"
    again = etsy_ops.reverify_openapi(db, transport=drifted, now=NOW + timedelta(days=2))
    assert again.get("reused") and drifted.calls == 1, "a fresh reading is not re-fetched"
    current = _Transport(body=_document())
    later = NOW + timedelta(days=etsy_ops.OPENAPI_REVERIFY_DAYS + 1)
    out = etsy_ops.reverify_openapi(db, transport=current, now=later)
    assert out["status"] == es.OPENAPI_CURRENT and current.calls == 1
    assert _incident(db).resolved, "a CURRENT re-verification resolves the drift incident"
    stored = etsy_ops.latest_reading(db, etsy_ops.OPENAPI_READING)
    assert stored["status"] == es.OPENAPI_CURRENT and stored["source"] == es.OPENAPI_URL


def test_a_failed_fetch_is_unreadable_and_is_retried_next_time():
    db = _db()
    down = _Transport(boom=True)
    out = etsy_ops.reverify_openapi(db, transport=down, now=NOW)
    assert out["status"] == es.OPENAPI_UNREADABLE and "network down" in out["why"]
    refused = _Transport(status=503)
    out = etsy_ops.reverify_openapi(db, transport=refused, now=NOW + timedelta(hours=1))
    assert refused.calls == 1 and out["status"] == es.OPENAPI_UNREADABLE, out
    assert _incident(db) is None, "an unread document is not a drift"


def test_the_served_inventory_reports_the_classification_state():
    db = _db()
    check = surface_inventory.reverify(db, now=NOW.timestamp())
    assert check["classification"]["status"] == "UNVERIFIED"
    assert any(p.startswith("classification: never re-verified") for p in check["problems"])
    assert check["items"] and all(i["classification_state"] == "UNVERIFIED"
                                  for i in check["items"])
    etsy_ops.reverify_openapi(db, transport=_Transport(body=_document(add=["createAdCampaign"])),
                              now=NOW)
    check = surface_inventory.reverify(db, now=(NOW + timedelta(hours=1)).timestamp())
    drifted = [i["key"] for i in check["items"] if i["classification_state"] == es.OPENAPI_DRIFTED]
    assert drifted and set(drifted) >= {s.key for s in es.by_verdict(es.UNSUPPORTED)}, drifted
    assert any("classification drifted" in p for p in check["problems"])
    stale = surface_inventory.reverify(db, now=(NOW + timedelta(days=30)).timestamp())
    assert stale["classification"]["status"] == "STALE", stale["classification"]
    summ = surface_inventory.summary(db)
    assert "classification" in summ and \
        "operating_readings:etsy.openapi_reverification" in summ["sources"]


def test_the_job_is_registered_for_the_worker():
    assert handlers.get("etsy.openapi_reverify") is etsy_ops.handle_openapi_reverify


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    assert TESTS, "no tests collected"
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
