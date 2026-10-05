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
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402


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
            s.add(PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True,
                                 release_hash="release-a"))
        self.add_built_hashes()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "BRAMBLELOOP_PUBLISH_AUTHORISED": "1", "BRAMBLELOOP_PHASE": "production"}))
        self.stack.enter_context(patch.object(pipeline, "_listing_parity",
                                              return_value={"blocks_release": False}))
        self.stack.enter_context(patch.object(pipeline, "_release_gates",
                                              return_value={"blocks_release": False}))
        self.stack.enter_context(patch.object(etsy_ops, "certified_payload",
                                              return_value=copy.deepcopy(self.kw["payload"])))
        self.stack.enter_context(patch.object(etsy_ops, "certified_images", return_value={
            **copy.deepcopy(self.kw["listing_images"]), "problems": []}))

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
        self.retry_creates_exactly_one()

    def test_built_pdf_hash_absent_then_present(self):
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
        t = FakeTransport()
        client = EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=False)
        out = pipeline._publish_and_read_back(self.ctx, client, **self.kw)
        self.assertFalse(out["published"]); self.assertIsNone(out["etsy_listing_id"])
        self.assertEqual(t.calls, [])
        self.assert_parked_nowhere()
        self.retry_creates_exactly_one()

    def test_unknown_publish_implementation_stays_fail_closed(self):
        # A client whose publish order is not the stock one is presumed to have possibly sent.
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
