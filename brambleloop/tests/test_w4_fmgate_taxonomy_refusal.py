"""W4-FMGATE: an Etsy credential refusal on the taxonomy read is reported, not dead-lettered.

Production 0417f35 (2026-10-11T14:05Z): `listing.taxonomy_refresh` dead-lettered with
"EtsyRejected: Etsy returned 403 for GET /seller-taxonomy/nodes ... on the API-key-only path".
The refusal is the owner-held `etsy_api` credential; a dead letter for it fails /api/verify's
no_unexpected_dead_letters_in_24h and keeps the 24-hour off-device proof (the
`production_window` gate) from ever reading PROVEN. Same treatment W4-PRODDIAG gave mjs.scan.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.integrations import etsy_taxonomy as T  # noqa: E402
from brambleloop.integrations.etsy import EtsyRejected, Response, TransientError  # noqa: E402


class _Status:
    def __init__(self, status):
        self.status, self.requests = status, []

    def request(self, method, url, *, headers, json=None, form=None, multipart=None,
                timeout=None):
        self.requests.append((method, url))
        return Response(self.status, {"error": "refused"})


def _refresh_with(transport):
    db = Database("sqlite://")
    db.create_all()
    saved = (T.api_key_transport_factory, os.environ.get("ETSY_KEYSTRING"))
    T.api_key_transport_factory = lambda: transport
    os.environ["ETSY_KEYSTRING"] = "fmgatetestkey"
    try:
        return db, T.refresh(db)
    finally:
        T.api_key_transport_factory = saved[0]
        if saved[1] is None:
            os.environ.pop("ETSY_KEYSTRING", None)
        else:
            os.environ["ETSY_KEYSTRING"] = saved[1]


def test_a_403_is_reported_as_a_credential_refusal_and_nothing_is_stored():
    from sqlalchemy import func, select

    from brambleloop.core.models import EtsyTaxonomySnapshot

    t = _Status(403)
    db, got = _refresh_with(t)
    assert got["ran"] is False and got["reading"] == "UNMEASURED", got
    assert got["credential_refused"] is True and got["status"] == 403
    assert "UNKNOWN" in got["why"] and "fmgatetestkey" not in got["why"]
    assert len(t.requests) == 1          # one re-test per run; no hammering
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(EtsyTaxonomySnapshot)) == 0
    assert T.latest(db) is None          # categories stay UNKNOWN


def test_a_401_is_a_credential_refusal_too():
    _db, got = _refresh_with(_Status(401))
    assert got["credential_refused"] is True and got["status"] == 401


def test_other_failures_still_raise_for_the_job_retries():
    for status, exc in ((500, TransientError), (429, TransientError), (404, EtsyRejected)):
        try:
            _refresh_with(_Status(status))
        except exc:
            continue
        raise AssertionError(f"HTTP {status} did not raise {exc.__name__}")


def test_the_classifier_reads_both_clients_messages():
    assert T.credential_refusal_status(EtsyRejected(
        "Etsy returned 403 for GET /seller-taxonomy/nodes (getSellerTaxonomyNodes) on the "
        "API-key-only path")) == 403
    assert T.credential_refusal_status(EtsyRejected(
        "Etsy returned 401 for GET /seller-taxonomy/nodes (x): {'error': 'invalid'}")) == 401
    assert T.credential_refusal_status(EtsyRejected("Etsy returned 400 for GET /x (y)")) is None
    assert T.credential_refusal_status(RuntimeError("Etsy returned 403 for GET /x")) is None


def test_the_handler_names_the_refusal_in_its_result():
    import inspect

    from brambleloop.runtime import release

    src = inspect.getsource(release.handle_taxonomy_refresh)
    assert '"credential_refused"' in src


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
    sys.exit(1 if fails else 0)
