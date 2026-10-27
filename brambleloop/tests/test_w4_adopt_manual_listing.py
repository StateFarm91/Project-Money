"""W-ADOPT (E-4): `listing.adopt_manual` links a hand-made Etsy listing to its certified release.

The owner publishes the first listings by hand in Shop Manager. Without this action the census
raised `etsy.unexpected_listing:<id>`, orders were "unmatched", the stats export matched only
an exact title, and `store.publish` would have created a second listing for the release.

Proven here, with no network (sockets refused) and an in-process Etsy transport that counts
every request:
- an unauthorised adoption (no session, operator bearer only, no step-up) is refused;
- a duplicate adoption is idempotent; a conflicting one is refused;
- adoption blocks `store.publish` from creating a duplicate listing;
- census, orders and the stats export match the adopted listing;
- an unreadable Etsy gives UNVERIFIED, never VERIFIED;
- zero Etsy write calls (asserted on the transport).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_adopt_manual_listing.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import re
import socket
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="adopt_manual_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the adoption harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approvals, auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Listing, PatternVersion,  # noqa: E402
                                     Phase, Product)
from brambleloop.integrations.etsy import EtsyClient, ListingPayload, Response  # noqa: E402
from brambleloop.publish import draft_intent  # noqa: E402
from brambleloop.publish import manual_adoption as MA  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402

OPS = "q" * 40
PASS = "owner passphrase for the manual adoption harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db

SHOP = "55501"
ETSY_ENV = {"ETSY_KEYSTRING": "adoptkey", "ETSY_SHARED_SECRET": "adoptsecret",
            "ETSY_ACCESS_TOKEN": "adopt-static-token", "ETSY_SHOP_ID": SHOP}
TITLE = ("Hexagon Coaster Set | Crochet Pattern PDF | Written Instructions and Chart | "
         "US and UK Terms")
TAGS = ["crochet pattern", "coaster pattern", "hexagon coaster"]
DESCRIPTION = ("DIGITAL CROCHET PATTERN, NOT A FINISHED ITEM. Instant digital download in US "
               "terms and UK terms. Skill level: beginner. You will need yarn and a 4 mm hook. "
               "Questions? Message us with the row number. How this pattern was made: This "
               "design was created with AI assistance, and every row's stitch count is "
               "checked before release.")


class FakeEtsyTransport:
    """In-process Etsy: answers the read endpoints; records every request it is sent."""

    def __init__(self, listings: dict[str, dict] | None = None, *, fail: int | None = None):
        self.listings = listings or {}
        self.fail = fail
        self.requests: list[tuple[str, str]] = []

    def writes(self) -> list[tuple[str, str]]:
        return [r for r in self.requests if r[0] != "GET"]

    def request(self, method, url, *, headers, json=None, form=None, multipart=None):
        self.requests.append((method, url))
        if method != "GET":
            return Response(405, {"error": "the adoption harness refuses every write"})
        if self.fail:
            return Response(self.fail, {"error": "injected failure"})
        path = url.split("/v3/application", 1)[-1].split("?", 1)[0]
        query = url.split("?", 1)[1] if "?" in url else ""
        m = re.fullmatch(r"/listings/(\d+)", path)
        if m:
            row = self.listings.get(m.group(1))
            return Response(200, dict(row)) if row else Response(404, {"error": "not found"})
        m = re.fullmatch(r"/listings/(\d+)/images", path)
        if m:
            return Response(200, {"results": list((self.listings.get(m.group(1)) or {})
                                                  .get("images") or [])})
        m = re.fullmatch(r"/shops/(\d+)/listings/(\d+)/files", path)
        if m:
            return Response(200, {"results": list((self.listings.get(m.group(2)) or {})
                                                  .get("_files") or [])})
        m = re.fullmatch(r"/shops/(\d+)/listings/(\d+)/properties", path)
        if m:
            return Response(200, {"results": []})
        if re.fullmatch(rf"/shops/{SHOP}/listings", path):
            state = dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("state")
            return Response(200, {"results": [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in self.listings.values() if r.get("state") == state]})
        return Response(404, {"error": f"unmodelled path {path}"})


def remote_listing(lid: str, **over) -> dict:
    row = {"listing_id": int(lid), "shop_id": int(SHOP), "state": "active", "title": TITLE,
           "description": DESCRIPTION, "tags": list(TAGS), "taxonomy_id": 2856,
           "price": {"amount": 400, "divisor": 100, "currency_code": "CAD"},
           "images": [{"rank": 1, "alt_text": "photo"}, {"rank": 2, "alt_text": "render"}],
           "_files": [{"filename": "hexagon-coaster-set-pattern-us.pdf", "size_bytes": 60876},
                      {"filename": "hexagon-coaster-set-pattern-uk.pdf", "size_bytes": 60885}]}
    row.update(over)
    return row


ALL_TRANSPORTS: list[FakeEtsyTransport] = []
from brambleloop.products import launch0 as _launch0  # noqa: E402

CIR_JSON = _launch0.cir_for("hexagon_coasters").to_dict()


def transport(*a, **k) -> FakeEtsyTransport:
    t = FakeEtsyTransport(*a, **k)
    ALL_TRANSPORTS.append(t)
    return t


def seed(db, slug="hexagon-coaster-set", version="1.2.0", release=None) -> str:
    """A certified release with its drafted listing (no Etsy id), as the chain leaves it."""
    release = release or uuid.uuid4().hex + uuid.uuid4().hex
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            product = Product(slug=slug, title="Hexagon Coaster Set (4)")
            s.add(product)
            s.flush()
        for pv in s.scalars(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                         PatternVersion.version == version)):
            s.delete(pv)
        for li in s.scalars(select(Listing).where(Listing.product_slug == slug,
                                                  Listing.version == version)):
            s.delete(li)
        s.execute(draft_intent.DraftIntent.__table__.delete().where(
            draft_intent.DraftIntent.slug == slug, draft_intent.DraftIntent.version == version))
        s.flush()
        s.add(PatternVersion(product_id=product.id, version=version, cir_json=CIR_JSON,
                             release_hash=release, certified=True))
        s.add(Listing(product_slug=slug, version=version, title=TITLE, description=DESCRIPTION,
                      tags=list(TAGS), price_cad=4.0, state="draft", release_hash=release,
                      created_at=datetime.now(timezone.utc) - timedelta(days=3)))
    return release


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def post(c, csrf, body):
    return c.post("/api/cc/actions/listing.adopt_manual", json=body, headers=fresh(csrf))


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def listing_row(db, slug="hexagon-coaster-set", version="1.2.0"):
    with db.session() as s:
        r = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                           Listing.version == version))
        return {"etsy_listing_id": r.etsy_listing_id, "state": r.state}


def intents(db, slug="hexagon-coaster-set"):
    with db.session() as s:
        return [(i.state, i.remote_id) for i in s.scalars(
            select(draft_intent.DraftIntent).where(draft_intent.DraftIntent.slug == slug))]


def adopt(db, t, lid, release, **kw):
    with patch.dict(os.environ, ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        return MA.adopt(db, etsy_listing_id=lid, slug=kw.pop("slug", "hexagon-coaster-set"),
                        version=kw.pop("version", "1.2.0"), release=release,
                        actor="owner:test", reason="published by hand in Shop Manager", **kw)


# ---- authorisation ----------------------------------------------------------------------


def test_the_action_is_owner_only_and_step_up():
    assert approvals.ACTIONS["listing.adopt_manual"][0] is True
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert not any("adopt" in p for p in paths), "no new route: the existing action route"


def test_unauthorised_adoption_is_refused():
    release = seed(DB)
    body = {"etsy_listing_id": "1001", "slug": "hexagon-coaster-set", "version": "1.2.0",
            "release": release, "reason": "made by hand"}
    t = transport({"1001": remote_listing("1001")})
    with patch.dict(os.environ, ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
        for headers in ({}, {"Authorization": f"Bearer {OPS}"}):
            r = anon.post("/api/cc/actions/listing.adopt_manual", json=body, headers=headers)
            assert r.status_code in (401, 403), (headers, r.status_code, r.text)
        c, csrf = session()
        expire_stepup(c)
        r = post(c, csrf, body)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert listing_row(DB) == {"etsy_listing_id": "", "state": "draft"}
    assert intents(DB) == []
    assert t.requests == [], "a refused request must not even read Etsy"


def test_cc_adoption_with_step_up_verifies_and_links():
    release = seed(DB)
    t = transport({"1002": remote_listing("1002")})
    with patch.dict(os.environ, ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        c, csrf = session()
        body = {"etsy_listing_id": "1002", "slug": "hexagon-coaster-set", "version": "1.2.0",
                "release": release}
        r = post(c, csrf, body)                       # no reason: refused
        assert r.status_code == 409, r.text
        r = post(c, csrf, {**body, "reason": "published by hand in Shop Manager"})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["verification"] == "VERIFIED" and res["adopted"] and not res["repeat"]
    assert listing_row(DB) == {"etsy_listing_id": "1002", "state": "published_manually"}
    assert intents(DB) == [("ADOPTED_MANUAL", "1002")]
    rec = MA.adoption_for(DB, "hexagon-coaster-set", "1.2.0")
    assert rec["observed"]["state"] == "active" and rec["observed"]["title"] == TITLE
    assert rec["observed"]["price"] == {"amount": 4.0, "currency": "CAD"}
    assert rec["observed"]["tags"] == TAGS and rec["observed"]["taxonomy_id"] == 2856
    assert rec["observed"]["image_count"] == 2 and rec["observed"]["file_count"] == 2
    assert any("NOT READABLE" in n for n in rec["not_verifiable"]), \
        "the file hash is never claimed as matched"
    with DB.session() as s:
        adopted = s.scalar(select(AuditLog).where(AuditLog.action == MA.ADOPTED)
                           .order_by(AuditLog.id.desc()))
        cc = s.scalar(select(AuditLog).where(
            AuditLog.action == "cc.owner_action.listing.adopt_manual"))
        assert adopted.artifact == "hexagon-coaster-set@1.2.0"
        assert adopted.detail["verification"] == "VERIFIED"
        assert adopted.detail["etsy_listing_id"] == "1002"
        assert cc is not None and cc.detail["result"]["verification"] == "VERIFIED"
    assert t.writes() == []


# ---- idempotency ------------------------------------------------------------------------


def test_duplicate_adoption_is_idempotent_and_conflicts_are_refused():
    release = seed(DB)
    t = transport({"1003": remote_listing("1003"), "1004": remote_listing("1004")})
    first = adopt(DB, t, "1003", release)
    reads = len(t.requests)
    again = adopt(DB, t, "1003", release)
    assert again["repeat"] and not again["changed"] and again["verification"] == "VERIFIED"
    assert len(t.requests) == reads, "a verified repeat does not re-read Etsy"
    assert intents(DB) == [("ADOPTED_MANUAL", "1003")]
    assert listing_row(DB)["etsy_listing_id"] == "1003"
    for lid, rel in (("1004", release), ("1003", "f" * 64)):
        try:
            adopt(DB, t, lid, rel)
        except MA.AdoptionRefused:
            pass
        else:
            raise AssertionError(f"conflicting adoption {lid} accepted")
    # The same Etsy listing cannot be linked to a second release either.
    other = seed(DB, version="1.3.0")
    try:
        adopt(DB, t, "1003", other, version="1.3.0")
    except MA.AdoptionRefused as e:
        assert "already linked" in str(e)
    else:
        raise AssertionError("one Etsy listing linked to two releases")
    assert intents(DB) == [("ADOPTED_MANUAL", "1003")]
    assert first["audit_id"] != again["audit_id"]
    assert t.writes() == []


# ---- UNVERIFIED -------------------------------------------------------------------------


def test_unreadable_etsy_is_unverified_never_verified():
    release = seed(DB)
    # No credential at all: nothing is read.
    t = transport({"1005": remote_listing("1005")})
    with patch.object(MA, "_transport", lambda: t):
        res = MA.adopt(DB, etsy_listing_id="1005", slug="hexagon-coaster-set",
                       version="1.2.0", release=release, actor="owner:test", reason="by hand")
    assert res["verification"] == "UNVERIFIED" and t.requests == []
    assert listing_row(DB) == {"etsy_listing_id": "1005", "state": "published_manually"}
    with DB.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "listing.adoption_review:hexagon-coaster-set@1.2.0",
            Incident.resolved.is_(False)))
        assert inc is not None and inc.halts_publication is False
        assert "UNVERIFIED" in inc.summary
    # An Etsy error is UNVERIFIED too, and the row stays one row.
    broken = transport({"1005": remote_listing("1005")}, fail=503)
    res = adopt(DB, broken, "1005", release)
    assert res["verification"] == "UNVERIFIED" and res["repeat"]
    # Readable again: the same adoption is upgraded to VERIFIED, still one intent.
    ok = transport({"1005": remote_listing("1005")})
    res = adopt(DB, ok, "1005", release)
    assert res["verification"] == "VERIFIED" and res["repeat"] and res["changed"]
    assert intents(DB) == [("ADOPTED_MANUAL", "1005")]
    with DB.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == "listing.adoption_review:hexagon-coaster-set@1.2.0",
            Incident.resolved.is_(False))) is None, "a clean re-verification resolves it"
    assert broken.writes() == [] and ok.writes() == []


def test_differences_are_recorded_and_open_a_review_but_do_not_block():
    release = seed(DB)
    t = transport({"1006": remote_listing(
        "1006", title="Hexagon Coasters crochet pattern", tags=["coaster"],
        price={"amount": 1500, "divisor": 100, "currency_code": "CAD"},
        _files=[{"filename": "hexagon-coaster-set-pattern-us.pdf", "size_bytes": 1}])})
    res = adopt(DB, t, "1006", release)
    assert res["adopted"] and res["verification"] == "VERIFIED"
    fields = {d["field"] for d in res["differences"]}
    assert {"title", "tags", "price", "file_count", "file:UK"} <= fields, fields
    with DB.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "listing.adoption_review:hexagon-coaster-set@1.2.0",
            Incident.resolved.is_(False)))
        assert inc is not None and not inc.halts_publication and inc.severity == "P2"
    assert listing_row(DB)["etsy_listing_id"] == "1006"
    assert t.writes() == []


def test_missing_or_foreign_listings_are_refused():
    release = seed(DB)
    t = transport({"1008": remote_listing("1008", shop_id=999)})
    for lid in ("1007", "1008", "not-a-number"):
        try:
            adopt(DB, t, lid, release)
        except MA.AdoptionRefused:
            pass
        else:
            raise AssertionError(f"{lid} adopted")
    assert listing_row(DB) == {"etsy_listing_id": "", "state": "draft"} and intents(DB) == []
    with DB.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == MA.REFUSED)) >= 3
    assert t.writes() == []


# ---- census, orders, stats --------------------------------------------------------------


def test_census_orders_and_stats_match_after_adoption():
    from brambleloop.commerce import listing_outcomes, orders_ingest

    release = seed(DB)
    t = transport({"1009": remote_listing("1009", title="Edited by hand in Shop Manager")})
    # Before adoption: the census reports the hand-made listing as unexpected.
    census_t = transport({"1009": remote_listing("1009", title="Edited by hand in Shop Manager")})
    real_build = etsy_ops.build_client
    ctx = SimpleNamespace(db=DB, phase=Phase.SHADOW, audit=lambda *a, **k: None,
                          job=SimpleNamespace(inputs={}), enqueue=lambda *a, **k: None)
    with patch.dict(os.environ, ETSY_ENV), patch.object(
            etsy_ops, "build_client",
            lambda db, phase, **k: real_build(db, phase, transport=census_t)):
        before = etsy_ops.handle_listing_census(ctx)
    assert before["unexpected"] == ["1009"], before

    adopt(DB, t, "1009", release)

    with patch.dict(os.environ, ETSY_ENV), patch.object(
            etsy_ops, "build_client",
            lambda db, phase, **k: real_build(db, phase, transport=census_t)):
        after = etsy_ops.handle_listing_census(ctx)
    assert after["unexpected"] == [] and "1009" not in after["suspected_policy"], after
    with DB.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == "etsy.unexpected_listing:1009",
            Incident.resolved.is_(False))) is None, "the census resolved its own incident"
    known = etsy_ops._expected_listings(DB)
    assert known["1009"]["slug"] == "hexagon-coaster-set" and known["1009"]["state"] == "active"

    history = orders_ingest.listing_history(DB)
    sold = orders_ingest.version_at(history, "1009", datetime.now(timezone.utc))
    assert sold["matched"] and sold["slug"] == "hexagon-coaster-set" \
        and sold["version"] == "1.2.0" and sold["basis"] == "listing.adopted_manual", sold

    index = listing_outcomes._listing_index(DB)
    assert index["1009"] == ("hexagon-coaster-set", "1.2.0")
    assert t.writes() == [] and census_t.writes() == []


# ---- store.publish ----------------------------------------------------------------------


class FakeRemote(EtsyClient):
    def __init__(self):
        self.creates = 0

    def refusal(self):
        return None

    def create_draft(self, payload, **kw):
        self.creates += 1
        return "999"


def test_adoption_blocks_store_publish_from_creating_a_duplicate():
    from phase_fixture import record_phase_path

    with tempfile.TemporaryDirectory() as td:
        db = Database("sqlite:///" + str(Path(td) / "pub.db"), scratch=True)
        db.create_all()
        release = seed(db)
        adopt(db, transport({"1010": remote_listing("1010")}), "1010", release)
        remote = FakeRemote()
        audits: list = []
        ctx = SimpleNamespace(db=db, phase=Phase.PRODUCTION,
                              audit=lambda *a, **k: audits.append((a, k)),
                              job=SimpleNamespace(inputs={"slug": "hexagon-coaster-set",
                                                          "version": "1.2.0",
                                                          "release": release}))
        token = "adopt-synthetic-owner-credential"
        with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": token,
                                     "BRAMBLELOOP_PHASE": "production"}):
            record_phase_path(db, token, "production")
            with patch.object(pipeline, "_listing_parity",
                              return_value={"verdict": "pass", "blocks_release": False}), \
                    patch.object(pipeline, "_release_gates",
                                 return_value={"blocks_release": False, "reasons": []}), \
                    patch("brambleloop.integrations.etsy.EtsyClient", return_value=remote), \
                    patch("brambleloop.integrations.etsy.Credentials.from_env",
                          return_value=None):
                result = pipeline.handle_store_publish(ctx)
        assert result["published"] is False and result["etsy_listing_id"] == "1010"
        assert result["reason"] == "already published manually", result
        assert remote.creates == 0
        # The durable intent is the second guard: the create path itself refuses too.
        try:
            draft_intent.claim(db, slug="hexagon-coaster-set", version="1.2.0",
                               release=release, content_digest="0" * 64)
        except draft_intent.ReconciliationRequired:
            pass
        else:
            raise AssertionError("a second creation intent was claimed")
        assert listing_row(db) == {"etsy_listing_id": "1010", "state": "published_manually"}
        db.engine.dispose()


# ---- W-ADOPT-2: the owner-accepted baseline ---------------------------------------------

EDITED = DESCRIPTION + " Edited by hand in Shop Manager: gauge note added."


def run_census(t):
    real_build = etsy_ops.build_client
    ctx = SimpleNamespace(db=DB, phase=Phase.SHADOW, audit=lambda *a, **k: None,
                          job=SimpleNamespace(inputs={}), enqueue=lambda *a, **k: None)
    with patch.dict(os.environ, ETSY_ENV), patch.object(
            etsy_ops, "build_client", lambda db, phase, **k: real_build(db, phase, transport=t)):
        return etsy_ops.handle_listing_census(ctx)


def open_incident(sig):
    with DB.session() as s:
        return s.scalar(select(Incident).where(Incident.signature == sig,
                                               Incident.resolved.is_(False)))


def baseline_of(lid):
    return MA.accepted_baselines(DB).get(lid)


def cc_baseline(c, csrf, action, body):
    return c.post(f"/api/cc/actions/{action}", json=body, headers=fresh(csrf))


def test_hand_edits_accepted_as_baseline_stop_the_halting_drift_and_new_drift_still_raises():
    release = seed(DB)
    live = {"2001": remote_listing("2001", description=EDITED)}
    t = transport(live)
    adopt(DB, t, "2001", release)
    # Not automatic: adopting (even with differences) accepts nothing.
    assert baseline_of("2001") is None
    first = run_census(t)
    assert "2001" in first["field_drift"], first
    drift = open_incident("etsy.listing_drift:2001")
    assert drift is not None and drift.halts_publication and drift.severity == "P1"

    body = {"etsy_listing_id": "2001", "slug": "hexagon-coaster-set", "version": "1.2.0"}
    with patch.dict(os.environ, ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        c, csrf = session()
        r = cc_baseline(c, csrf, "listing.baseline_preview", body)     # a read: no step-up
        assert r.status_code == 200, r.text
        shown = r.json()["result"]
        assert shown["acceptable"] and shown["refusals"] == []
        assert {d["field"] for d in shown["differences_from_certified"]} == {"description"}
        accept = {**body, "expected_digest": shown["digest"], "reason": "my Shop Manager edit"}
        expire_stepup(c)
        r = cc_baseline(c, csrf, "listing.accept_baseline", accept)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        c, csrf = session()
        r = cc_baseline(c, csrf, "listing.accept_baseline", {**accept, "expected_digest": "0" * 64})
        assert r.status_code == 409 and "preview changed" in r.json().get("error", r.text), r.text
        r = cc_baseline(c, csrf, "listing.accept_baseline", {**accept, "reason": ""})
        assert r.status_code == 409, r.text
        assert baseline_of("2001") is None, "nothing accepted by a refused request"
        r = cc_baseline(c, csrf, "listing.accept_baseline", accept)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["accepted"] and "etsy.listing_drift:2001" in res["incidents_resolved"]
    assert baseline_of("2001")["digest"] == shown["digest"]
    assert open_incident("etsy.listing_drift:2001") is None
    with DB.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == MA.BASELINE_ACCEPTED)
                       .order_by(AuditLog.id.desc()))
        assert row.detail["etsy_listing_id"] == "2001" and row.detail["reason"]
        assert row.detail["accepted_differences"][0]["field"] == "description"
        assert s.scalar(select(AuditLog).where(
            AuditLog.action == "cc.owner_action.listing.accept_baseline")) is not None

    # The census now compares with the baseline: the accepted edit is not drift.
    second = run_census(t)
    assert "2001" not in second["field_drift"], second
    assert open_incident("etsy.listing_drift:2001") is None
    # Genuinely new drift after acceptance still raises the halting incident.
    live["2001"] = remote_listing("2001", description=EDITED, title="Hexagon Coasters PDF")
    third = run_census(t)
    assert "2001" in third["field_drift"], third
    inc = open_incident("etsy.listing_drift:2001")
    assert inc is not None and inc.halts_publication
    assert any("title: accepted baseline" in d for d in inc.detail["drift"]), inc.detail
    assert t.writes() == []


def test_acceptance_is_refused_when_the_live_copy_breaks_truth_or_disclosures():
    release = seed(DB)
    no_ai = DESCRIPTION.replace("This design was created with AI assistance, and every row's "
                                "stitch count is checked before release.", "")
    live = {"2002": remote_listing("2002", description=no_ai)}
    t = transport(live)
    adopt(DB, t, "2002", release)
    for broken, why in (
            ({"description": no_ai}, "ai_assisted_design"),
            ({"title": "Hexagon Coaster Set of 12 | Crochet Pattern PDF | US and UK Terms"},
             "Product Truth (title promise)"),
            ({"description": "Hexagon coasters. Message us with questions."}, "disclosures")):
        live["2002"] = remote_listing("2002", **broken)
        with patch.dict(os.environ, ETSY_ENV), patch.object(MA, "_transport", lambda: t):
            shown = MA.baseline_preview(DB, slug="hexagon-coaster-set", version="1.2.0",
                                        etsy_listing_id="2002")
            assert not shown["acceptable"] and any(why in p for p in shown["refusals"]), \
                (why, shown["refusals"])
            try:
                MA.accept_baseline(DB, slug="hexagon-coaster-set", version="1.2.0",
                                   etsy_listing_id="2002", expected_digest=shown["digest"],
                                   actor="owner:test", reason="accept it")
            except MA.AdoptionRefused as e:
                assert "Product Truth or a required disclosure" in str(e)
            else:
                raise AssertionError(f"accepted a live copy that breaks {why}")
        assert baseline_of("2002") is None
        inc = open_incident("listing.adoption_review:hexagon-coaster-set@1.2.0")
        assert inc is not None and "NOT accepted" in inc.summary, "the incident is kept"
    with DB.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == MA.BASELINE_REFUSED)) >= 3
    # A listing that is not the adopted one cannot be given a baseline at all.
    try:
        MA.baseline_preview(DB, slug="hexagon-coaster-set", version="1.2.0",
                            etsy_listing_id="2999")
    except MA.AdoptionRefused:
        pass
    else:
        raise AssertionError("baseline preview for a listing that was not adopted")
    assert t.writes() == []


# ---- W-ADOPT-2: every "live on Etsy" reader counts a manual listing ----------------------


def test_every_live_reader_counts_a_manually_published_listing():
    from brambleloop.app import verify_checks
    from brambleloop.core.listing_state import LIVE_ON_ETSY, is_live_on_etsy
    from brambleloop.finance import sustainability
    from brambleloop.growth import ads_readiness
    from brambleloop.products import lifecycle
    from brambleloop.scale import confidence, runrate
    from brambleloop.store_foundation import preview

    assert is_live_on_etsy("published_manually") and is_live_on_etsy("published")
    assert not is_live_on_etsy("draft") and "published_manually" in LIVE_ON_ETSY
    assert "published_manually" in sustainability.LIVE_STATES
    with tempfile.TemporaryDirectory() as td:
        db = Database("sqlite:///" + str(Path(td) / "live.db"), scratch=True)
        db.create_all()
        release = seed(db)
        # Before: nothing live anywhere.
        assert verify_checks.publication_checks(db)["published"]["ok"] is True
        assert runrate.orders_source_live(db)["published_listings"] == 0
        adopt(db, transport({"3001": remote_listing("3001")}), "3001", release)
        assert listing_row(db)["state"] == "published_manually"

        # /api/verify (shadow): nothing_published must NOT pass while a manual listing is live.
        checks = verify_checks.publication_checks(db)
        assert checks["published"]["check"] == "nothing_published"
        assert checks["published"]["ok"] is False
        assert checks["published"]["evidence"]["listings_published_manually"] == 1
        # /api/verify (live phases): a VERIFIED owner adoption is its grant and read-back.
        proven = verify_checks._published_rows_proven(db)
        assert proven["listings_on_etsy"] == 1 and proven["unproven"] == [], proven
        # Readiness, dashboards, ledger evidence, lifecycle and launch gates.
        assert runrate.orders_source_live(db)["published_listings"] == 1
        assert runrate.orders_source_live(db)["live"] is True
        assert confidence._counts(db)["published_listings"] == 1
        assert lifecycle.derive(db, "hexagon-coaster-set")["stage"] == "LIVE"
        assert preview._live_on_etsy(db) == {"live": True, "published": True}
        gates = ads_readiness.listing_readiness(db, "hexagon-coaster-set")
        gate = next(g for g in gates["gates"] if g["gate"] == "listing_live")
        assert gate["status"] == "PASS", gate
        db.engine.dispose()
    # The catalogue on the shared database: published is computed, never hard-coded.
    with DB.session() as s:
        live_any = any(is_live_on_etsy(r.state) for r in s.scalars(select(Listing)))
    assert live_any and main.api_catalogue()["published"] is True


def test_no_reader_compares_listing_state_to_published_literally():
    """Static guard: a new "live" reader must use core.listing_state, not == "published"."""
    src = ROOT / "src" / "brambleloop"
    patterns = (re.compile(r"""state\s*[!=]=\s*["']published["']"""),
                re.compile(r"""by\.get\(\s*["']published["']"""),
                re.compile(r"""["']published["']\s+(not\s+)?in\s+states"""))
    allowed = ("ContentPiece.state",)  # content pieces, not listings
    offenders = []
    for path in src.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(p.search(line) for p in patterns) and not any(a in line for a in allowed):
                offenders.append(f"{path.relative_to(src)}:{n}: {line.strip()}")
    assert offenders == [], offenders


# ---- read-only against Etsy -------------------------------------------------------------


def test_zero_etsy_write_calls_across_every_case():
    assert ALL_TRANSPORTS, "the cases above ran"
    writes = [w for t in ALL_TRANSPORTS for w in t.writes()]
    assert writes == [], writes
    gets = sum(len(t.requests) for t in ALL_TRANSPORTS)
    assert gets > 0, "the verified cases actually read Etsy"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
