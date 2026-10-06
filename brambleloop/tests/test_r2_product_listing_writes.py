"""R2 / J-product P-5 follow-up: attach_file, update_listing and set_listing_property need the
owner's verified grant (or the shadow draft-only lane under a re-resolved non-publishing phase),
exactly like create_draft. A publication grant completes only the draft it created.

On ddf9c6e a production-string client with owner_authorised=True sent all three writes with no
grant at all. Recording transport only: no socket is opened, nothing reaches Etsy.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_listing_writes.py
"""
from __future__ import annotations

import inspect
import os
import tempfile
from unittest.mock import patch

from _r2_harness import run

from brambleloop.core.db import Database
from brambleloop.integrations import etsy as E
from brambleloop.integrations.http import Response

TOKEN = "r2-product-ops-token-for-tests-only"
CREDS = E.Credentials(api_key="k", access_token="t", shop_id="S")


class _Rec:
    def __init__(self):
        self.sent = []

    def request(self, method, url, **kw):
        self.sent.append((method, url))
        return Response(200, {"listing_id": 5, "listing_file_id": 7}, {})


def _db():
    d = tempfile.mkdtemp(prefix="r2writes_")
    db = Database(f"sqlite:///{d}/x.sqlite")
    db.create_all()
    return db


def _writes(client, grant_kw):
    yield "attach_file", lambda: client.attach_file("5", filename="p.pdf", data=b"%PDF",
                                                    **grant_kw)
    yield "update_listing", lambda: client.update_listing("5", {"title": "x"}, **grant_kw)
    yield "set_listing_property", lambda: client.set_listing_property(
        "5", {"property_id": 200, "value_ids": [1], "values": ["Beige"]}, **grant_kw)


def _refused(client, rec, grant_kw, needle):
    calls = list(_writes(client, grant_kw))
    assert calls
    for name, call in calls:
        try:
            call()
            raise AssertionError(f"{name} reached the transport")
        except E.EtsyNotPermitted as e:
            assert needle in str(e), (name, e)
    assert rec.sent == [], rec.sent


def test_a_production_string_and_owner_flag_send_none_of_the_three_without_a_grant():
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="production", owner_authorised=True)
    _refused(client, rec, {}, "OwnerGrant")


def test_the_shadow_lane_rereads_the_phase_for_the_three_writes():
    from phase_fixture import record_phase_path

    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                 "BRAMBLELOOP_PHASE": "production"}):
        record_phase_path(db, TOKEN, "production")
        rec = _Rec()
        client = E.EtsyClient(rec, credentials=CREDS, phase="shadow",
                              shadow_writes_authorised=True)
        client.db = db
        _refused(client, rec, {}, "effective runtime phase")


def test_a_publication_grant_completes_only_the_draft_it_created():
    from phase_fixture import record_phase_path
    from brambleloop.core.models import Listing
    from brambleloop.ops import publication_authority as pa

    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="p", version="1", title="t", description="d",
                      release_hash="r" * 64, etsy_listing_id="555"))
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                 "BRAMBLELOOP_PHASE": "production",
                                 pa.KILL_SWITCH_VAR: "1"}):
        record_phase_path(db, TOKEN, "production")
        grant = E.OwnerGrant(db, action=E.OwnerGrant.PUBLISH, approval_id=None, slug="p",
                             version="1", release="r" * 64)
        other = grant.refusal(action=E.OwnerGrant.PUBLISH_COMPLETE, listing_id="5")
        assert other and "not the draft this publication created" in other, other
        own = grant.refusal(action=E.OwnerGrant.PUBLISH_COMPLETE, listing_id="555")
        assert own and "grant required" in own, own        # no recorded grant -> refused
        rec = _Rec()
        client = E.EtsyClient(rec, credentials=CREDS, phase="production",
                              owner_authorised=True)
        _refused(client, rec, {"grant": grant}, "refused at the client")


def test_an_activation_grant_names_its_listing():
    db = _db()
    rec = _Rec()
    client = E.EtsyClient(rec, credentials=CREDS, phase="production", owner_authorised=True)
    grant = E.OwnerGrant(db, action=E.OwnerGrant.ACTIVATE, approval_id=1, slug="p",
                         version="1", listing_id="999")
    _refused(client, rec, {"grant": grant}, "refused at the client")


def test_the_pipeline_passes_the_grant_to_every_post_create_write():
    from brambleloop.runtime import pipeline

    src = inspect.getsource(pipeline._publish_and_read_back)
    for call in ("client.set_listing_property(", "client.attach_file("):
        assert call in src, call
        tail = src.split(call, 1)[1].split(")\n", 1)[0]
        assert "grant=" in tail, (call, tail[:200])


run(globals())
