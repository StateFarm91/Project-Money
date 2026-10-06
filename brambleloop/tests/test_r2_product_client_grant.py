"""R2 / J-product P-5: create_draft / upload_image / delete_listing need the owner's verified
grant at the client, and the client re-resolves the phase instead of trusting its constructor.

On ddf9c6e `EtsyClient(t, phase="production", owner_authorised=True).create_draft(p)` reached
the transport with no grant, no database and no recorded phase (j_product_client_nogrant.py).
Recording transport only: no socket is opened, nothing reaches Etsy.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_client_grant.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import tempfile
from unittest.mock import patch

from _r2_harness import run

from brambleloop.core.db import Database
from brambleloop.integrations import etsy as E
from brambleloop.integrations.http import Response

TOKEN = "r2-product-ops-token-for-tests-only"


class _Rec:
    def __init__(self):
        self.sent = []

    def request(self, method, url, **kw):
        self.sent.append((method, url))
        if method == "GET":
            return Response(200, {"listing_id": 1, "state": "draft"}, {})
        return Response(200, {"listing_id": 123, "listing_image_id": 9}, {})


CREDS = E.Credentials(api_key="k", access_token="t", shop_id="S")
PAYLOAD = E.build_payload(title="Probe", description="d", price_cad=1.0, tags=["a"],
                          materials=["yarn"])


def _db():
    d = tempfile.mkdtemp(prefix="r2grant_")
    db = Database(f"sqlite:///{d}/x.sqlite")
    db.create_all()
    return db


def _calls(client):
    yield "create_draft", lambda g: client.create_draft(PAYLOAD, grant=g)
    yield "upload_image", lambda g: client.upload_image("1", filename="c.png", data=b"x",
                                                        grant=g)
    yield "delete_listing", lambda g: client.delete_listing("1", grant=g)


def test_a_production_string_and_owner_flag_send_nothing_without_a_grant():
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="production", owner_authorised=True)
    calls = list(_calls(client))
    assert calls
    for name, call in calls:
        try:
            call(None)
            raise AssertionError(f"{name} ran without a grant")
        except E.EtsyNotPermitted as e:
            assert "OwnerGrant" in str(e), (name, e)
    assert rec.sent == [], rec.sent


def test_a_grant_naming_no_recorded_authority_is_refused_before_the_request():
    db = _db()
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="production", owner_authorised=True)
    bogus = E.OwnerGrant(db, action=E.OwnerGrant.PUBLISH, approval_id=424242, slug="s",
                         version="1")
    with patch.dict(os.environ, {"BRAMBLELOOP_PHASE": "production"}):
        calls = list(_calls(client))
        assert calls
        for name, call in calls:
            try:
                call(bogus)
                raise AssertionError(f"{name} ran on a grant naming nothing")
            except E.EtsyNotPermitted as e:
                assert "refused at the client" in str(e), (name, e)
    assert rec.sent == [], rec.sent


def test_the_shadow_lane_rereads_the_phase_and_refuses_in_a_recorded_production():
    from phase_fixture import record_phase_path

    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                 "BRAMBLELOOP_PHASE": "production"}):
        record_phase_path(db, TOKEN, "production")
        rec = _Rec()
        # the constructor says shadow; the recorded, chained phase says production
        client = E.EtsyClient(rec, credentials=CREDS, phase="shadow",
                              shadow_writes_authorised=True)
        client.db = db
        try:
            client.create_draft(PAYLOAD)
            raise AssertionError("shadow lane wrote in a recorded production phase")
        except E.EtsyNotPermitted as e:
            assert "effective runtime phase" in str(e), e
        assert rec.sent == []


def test_the_owner_shadow_probe_lane_still_drafts_in_a_non_publishing_phase():
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="shadow",
                          shadow_writes_authorised=True)
    assert client.create_draft(PAYLOAD) == "123"
    assert client.refusal_for(E.Authority.ACTIVATE) is not None


def test_publish_still_requires_and_uses_the_grant():
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="production", owner_authorised=True)
    out = client.publish(payload=PAYLOAD, filename="x.pdf", data=b"x")
    assert not out.published and "OwnerGrant" in " ".join(out.problems), out
    assert rec.sent == []


run(globals())
