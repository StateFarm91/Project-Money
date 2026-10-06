"""FB2-R2 #1: a pre-create refusal never parks a version behind RECONCILE_REQUIRED.

Synthetic local evidence and a fake HTTP transport; no provider is contacted. A refusal that
provably happens before any createDraftListing request (owner publication authority absent,
`assets.built` PDF hashes absent) must leave no durable intent and no halting incident, and
the retry after the condition clears must create exactly one draft. Crash-after-send stays
RECONCILE_REQUIRED (tests/test_draft_creation_durability.py).
"""
import copy
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import delete, select  # noqa: E402

from test_draft_creation_durability import args, ctx, setup  # noqa: E402
from test_etsy import CREDS, FakeTransport  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, PatternVersion, Product  # noqa: E402
from brambleloop.core.resilience import PermanentError  # noqa: E402
from brambleloop.integrations.etsy import EtsyClient  # noqa: E402
from brambleloop.publish import draft_intent  # noqa: E402
from brambleloop.ops import publication_authority as pa  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402

OWNER_TOKEN = "synthetic-owner-ops-credential-not-a-secret"


def creates(transport):
    return [c for c in transport.calls
            if c[0] == "POST" and c[1].rstrip("/").endswith("/listings")]


class PreCreateRefusal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = setup(Path(self.tmp.name) / "state.db"); self.addCleanup(self.db.engine.dispose)
        self.kw = args(); self.ctx = ctx(self.db)
        self.ctx.enqueue = lambda *a, **k: None
        with self.db.session() as s:
            p = Product(slug="original", title="Synthetic"); s.add(p); s.flush()
            s.add(PatternVersion(product_id=p.id, version="1", cir_json={"synthetic": True},
                                 certified=True, release_hash="release-a"))
        self.add_built_hashes()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "BRAMBLELOOP_PUBLISH_AUTHORISED": "1", "BRAMBLELOOP_PHASE": "production",
            "BRAMBLELOOP_OPS_TOKEN": OWNER_TOKEN}))
        self.stack.enter_context(patch.object(pipeline, "_listing_parity",
                                              return_value={"blocks_release": False}))
        self.stack.enter_context(patch.object(pipeline, "_release_gates",
                                              return_value={"blocks_release": False}))
        self.stack.enter_context(patch.object(etsy_ops, "certified_payload",
                                              return_value=copy.deepcopy(self.kw["payload"])))
        self.stack.enter_context(patch.object(etsy_ops, "certified_images", return_value={
            **copy.deepcopy(self.kw["listing_images"]), "problems": []}))
        # F-299: the env phase must agree with the owner's recorded transition.
        from phase_fixture import record_phase_path
        record_phase_path(self.db, OWNER_TOKEN, "production")

    def grant(self, *, slug="original", version="1", release="release-a"):
        """The owner's durable publication grant, through the real approve path."""
        content = pa.snapshot(self.db, slug, version, release)
        return pa.approve(self.db, authorization=OWNER_TOKEN, slug=slug, version=version,
                          release=release, expected_digest=pa.digest(content),
                          reason="synthetic owner review")["approval_id"]

    def assert_refused_before_any_request(self, needle):
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
        with self.assertRaises(PermanentError) as caught:
            pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertNotIsInstance(caught.exception, draft_intent.ReconciliationRequired)
        self.assertIn("authority", str(caught.exception))
        self.assertIn(needle, str(caught.exception))
        self.assertEqual(t.calls, [])
        self.assert_parked_nowhere()

    def add_built_hashes(self):
        with self.db.session() as s:
            j = Job(agent="synthetic", job_type="assets.build", inputs={"release": "release-a"})
            s.add(j); s.flush()
            s.add(AuditLog(actor="synthetic", action="assets.built", artifact="original@1",
                           job_id=j.id, detail={"pdf_sha256_by_terminology": {
                               k: hashlib.sha256(v.pdf_bytes).hexdigest()
                               for k, v in self.kw["docs"].items()}}))

    def assert_parked_nowhere(self):
        with self.db.session() as s:
            self.assertIsNone(s.get(draft_intent.DraftIntent,
                                    draft_intent.key_for("original", "1")))
            self.assertEqual(s.scalars(select(draft_intent.DraftIntent).where(
                draft_intent.DraftIntent.state == "RECONCILE_REQUIRED")).all(), [])
            self.assertIsNone(s.scalar(select(Incident).where(
                Incident.halts_publication.is_(True))))

    def retry_creates_exactly_one(self):
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
        pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertEqual(len(creates(t)), 1)
        with self.db.session() as s:
            intent = s.get(draft_intent.DraftIntent, draft_intent.key_for("original", "1"))
            self.assertIsNotNone(intent)
            self.assertEqual(intent.remote_id, "987654321")
        # The durable intent still forbids a second automatic create afterwards.
        t2 = FakeTransport()
        client2 = EtsyClient(t2, credentials=CREDS, phase="production", owner_authorised=True)
        with self.assertRaises(draft_intent.ReconciliationRequired):
            pipeline._publish_and_read_back(self.ctx, client2, **self.kw)
        self.assertEqual(creates(t2), [])

    # ---- FB3-P: durable owner publication grant -----------------------------------------

    def test_no_grant_is_refused_with_zero_requests_even_with_the_env_flag(self):
        self.assertEqual(os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"], "1")
        self.assert_refused_before_any_request("grant required")
        self.grant()
        self.retry_creates_exactly_one()

    def test_forged_grants_are_refused(self):
        # A row inserted by hand under the owner principal, with no valid seal.
        from datetime import timedelta
        now = pa._now()
        content = pa.snapshot(self.db, "original", "1", "release-a")
        with self.db.session() as s:
            s.add(AuditLog(actor=pa.PRINCIPAL, action=pa.APPROVED, artifact="original@1",
                           detail={"principal": pa.PRINCIPAL, "action": pa.ACTION,
                                   "scope": "original@1", "release": "release-a",
                                   "content": content, "digest": pa.digest(content),
                                   "reason": "forged", "approved_at": now.isoformat(),
                                   "expires_at": (now + timedelta(hours=1)).isoformat(),
                                   "seal": "0" * 64}))
        self.assert_refused_before_any_request("invalid")
        # rc1-AUTH D2: the forged row broke the sealed grant chain, so no new grant can be
        # recorded on top of it until the owner rebases (which voids every earlier grant).
        with self.assertRaises(ValueError):
            self.grant()
        pa.rebase(self.db, authorization=OWNER_TOKEN, reason="forged row found")
        # A genuine grant whose row is edited afterwards (extended expiry) no longer verifies.
        ident = self.grant()
        with self.db.session() as s:
            row = s.get(AuditLog, ident)
            d = dict(row.detail)
            d["expires_at"] = (now + timedelta(days=365)).isoformat()
            row.detail = d
        self.assert_refused_before_any_request("invalid")
        pa.rebase(self.db, authorization=OWNER_TOKEN, reason="edited row found")
        # A grant sealed under a credential that has since rotated.
        self.grant()
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = OWNER_TOKEN + "-rotated"
        self.assert_refused_before_any_request("invalid")
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = OWNER_TOKEN
        # A grant presented by an id that is not an owner publication approval at all.
        with self.db.session() as s:
            other = AuditLog(actor="synthetic", action="owner.activation.approved",
                             artifact="original@1", detail={})
            s.add(other); s.flush(); other_id = other.id
        self.ctx.job.inputs["owner_publication_approval_id"] = other_id
        self.assert_refused_before_any_request("grant required")
        del self.ctx.job.inputs["owner_publication_approval_id"]

    def test_expired_grant_is_refused(self):
        from datetime import timedelta
        self.grant()
        later = pa._now() + timedelta(hours=pa.GRANT_HOURS, seconds=1)
        with patch.object(pa, "_now", return_value=later):
            self.assert_refused_before_any_request("expired")
        self.retry_creates_exactly_one()

    def test_revoked_grant_is_refused(self):
        ident = self.grant()
        pa.revoke(self.db, authorization=OWNER_TOKEN, approval_id=ident)
        self.assert_refused_before_any_request("revoked")
        with self.assertRaises(Exception):
            pa.revoke(self.db, authorization="not-the-owner-credential-at-all", approval_id=ident)
        self.grant()
        self.retry_creates_exactly_one()

    def test_grant_for_another_version_or_release_or_content_is_refused(self):
        with self.db.session() as s:
            p = s.scalar(select(Product).where(Product.slug == "original"))
            s.add(PatternVersion(product_id=p.id, version="2", cir_json={"synthetic": 2},
                                 certified=True, release_hash="release-a"))
            from brambleloop.core.models import Listing
            s.add(Listing(product_slug="original", version="2", title="Other version",
                          description="Fixture", release_hash="release-a"))
        self.grant(version="2")
        self.assert_refused_before_any_request("grant required")
        # Granted for this version, then the listing content to be sent changes.
        self.grant()
        changed = copy.deepcopy(self.kw["payload"]); changed.title = "Changed after review"
        with patch.object(etsy_ops, "certified_payload", return_value=changed):
            self.kw["payload"] = copy.deepcopy(changed)
            self.assert_refused_before_any_request("does not match current content")

    def test_kill_switch_denies_even_with_a_valid_grant(self):
        self.grant()
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "0"
        self.assert_refused_before_any_request("kill-switch")
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
        self.retry_creates_exactly_one()

    def test_valid_grant_proceeds_and_is_named_at_both_boundaries(self):
        ident = self.grant()
        seen = []
        self.ctx.audit = lambda action, **k: seen.append((action, k.get("detail") or {}))
        self.retry_creates_exactly_one()
        runs = [d for a, d in seen if a == "store.execution_revalidated"]
        self.assertEqual([d["stage"] for d in runs[:2]], ["pre_claim", "before_create"])
        self.assertTrue(all(d["owner_publication_grant"] == ident for d in runs[:2]))

    def test_owner_api_grants_and_revokes_only_with_the_owner_credential(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from brambleloop.app.publication_authority_api import make_router
        app = FastAPI(); app.include_router(make_router(self.db)); api = TestClient(app)
        body = {"slug": "original", "version": "1", "release": "release-a"}
        self.assertEqual(api.post("/api/owner/publication/preview", json=body).status_code, 403)
        auth = {"Authorization": f"Bearer {OWNER_TOKEN}"}
        preview = api.post("/api/owner/publication/preview", json=body, headers=auth).json()
        approve = {**body, "expected_digest": preview["digest"], "reason": "reviewed"}
        self.assertEqual(api.post("/api/owner/publication/approve", json=approve).status_code, 403)
        stale = {**approve, "expected_digest": "0" * 64}
        self.assertEqual(api.post("/api/owner/publication/approve", json=stale,
                                  headers=auth).status_code, 409)
        r = api.post("/api/owner/publication/approve", json=approve, headers=auth)
        self.assertEqual(r.status_code, 200, r.text)
        ident = r.json()["approval_id"]
        self.assertIsNone(pa.validate(self.db, ident, slug="original", version="1",
                                      release="release-a"))
        self.assertEqual(api.post(f"/api/owner/publication/{ident}/revoke").status_code, 403)
        self.assertEqual(api.post(f"/api/owner/publication/{ident}/revoke",
                                  headers=auth).status_code, 200)
        self.assertIn("revoked", pa.validate(self.db, ident, slug="original", version="1",
                                             release="release-a"))

    def test_authority_absent_then_granted(self):
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "0"
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
        with self.assertRaises(PermanentError) as caught:
            pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertNotIsInstance(caught.exception, draft_intent.ReconciliationRequired)
        self.assertIn("authority", str(caught.exception))
        self.assertEqual(t.calls, [])
        self.assertEqual(creates(t), [])
        self.assert_parked_nowhere()
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
        self.grant()
        self.retry_creates_exactly_one()

    def test_built_pdf_hash_absent_then_present(self):
        self.grant()
        with self.db.session() as s:
            s.execute(delete(AuditLog).where(AuditLog.action == "assets.built"))
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
        with self.assertRaises(PermanentError) as caught:
            pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertNotIsInstance(caught.exception, draft_intent.ReconciliationRequired)
        self.assertEqual(t.calls, [])
        self.assert_parked_nowhere()
        self.add_built_hashes()
        self.retry_creates_exactly_one()

    def test_client_refusal_before_hook_releases_intent(self):
        # The stock client refuses (no owner authority on the client) before its create hook:
        # provably nothing was sent, so the claimed intent is released, not parked.
        self.grant()
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=False)
        out = pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertFalse(out["published"]); self.assertIsNone(out["etsy_listing_id"])
        self.assertEqual(t.calls, [])
        self.assert_parked_nowhere()
        self.retry_creates_exactly_one()

    def test_unknown_publish_implementation_stays_fail_closed(self):
        # A client whose publish order is not the stock one is presumed to have possibly sent.
        self.grant()
        class Opaque(EtsyClient):
            def publish(self, **kw):
                raise RuntimeError("opaque failure")
        client = Opaque(FakeTransport(), credentials=CREDS, phase="production",
                        owner_authorised=True)
        with self.assertRaises(RuntimeError):
            pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        with self.db.session() as s:
            intent = s.get(draft_intent.DraftIntent, draft_intent.key_for("original", "1"))
            self.assertEqual(intent.state, "RECONCILE_REQUIRED")
            self.assertIsNotNone(s.scalar(select(Incident).where(
                Incident.halts_publication.is_(True))))


if __name__ == "__main__":
    unittest.main()
