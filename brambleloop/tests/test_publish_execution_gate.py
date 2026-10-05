"""Synthetic local evidence and fake HTTP; not provider or full certification proof."""
import sys,tempfile,unittest,hashlib,copy,os
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_draft_creation_durability import setup,ctx,args
from test_etsy import FakeTransport,CREDS
from brambleloop.runtime import pipeline,etsy_ops
from brambleloop.integrations.etsy import EtsyClient
from brambleloop.core.models import Product,PatternVersion,AuditLog,Job
from brambleloop.publish import draft_intent
from brambleloop.core.resilience import PermanentError
from brambleloop.ops import publication_authority

OWNER_TOKEN="synthetic-owner-ops-credential-not-a-secret"

REAL_RELEASE_GATES=pipeline._release_gates

class ExecutionRecheck(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=setup(Path(self.tmp.name)/"state.db");self.addCleanup(self.db.engine.dispose)
        self.kw=args();self.ctx=ctx(self.db)
        with self.db.session() as s:
            p=Product(slug="original",title="Synthetic");s.add(p);s.flush()
            s.add(PatternVersion(product_id=p.id,version="1",cir_json={"synthetic":True},certified=True,release_hash="release-a"))
            j=Job(agent="synthetic",job_type="assets.build",inputs={"release":"release-a"});s.add(j);s.flush()
            s.add(AuditLog(actor="synthetic",action="assets.built",artifact="original@1",job_id=j.id,
                detail={"pdf_sha256_by_terminology":{k:hashlib.sha256(v.pdf_bytes).hexdigest() for k,v in self.kw["docs"].items()}}))
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ,{"BRAMBLELOOP_PUBLISH_AUTHORISED":"1","BRAMBLELOOP_PHASE":"production",
            "BRAMBLELOOP_OPS_TOKEN":OWNER_TOKEN}))
        self.parity=self.stack.enter_context(patch.object(pipeline,"_listing_parity",return_value={"blocks_release":False}))
        self.gates=self.stack.enter_context(patch.object(pipeline,"_release_gates",return_value={"blocks_release":False}))
        self.payload=self.stack.enter_context(patch.object(etsy_ops,"certified_payload",return_value=copy.deepcopy(self.kw["payload"])))
        self.images=self.stack.enter_context(patch.object(etsy_ops,"certified_images",return_value={**copy.deepcopy(self.kw["listing_images"]),"problems":[]}))
        # FB3-P: owner publication authority is a durable sealed grant, not the env flag.
        content=publication_authority.snapshot(self.db,"original","1","release-a")
        self.grant=publication_authority.approve(self.db,authorization=OWNER_TOKEN,slug="original",version="1",
            release="release-a",expected_digest=publication_authority.digest(content),reason="synthetic owner review")["approval_id"]

    def check(self):
        pipeline._revalidate_publish_effect(self.ctx,**{k:self.kw[k] for k in
            ("slug","version","release","payload","docs","listing_images")})

    def test_bound_packet_passes_but_changed_pdf_bytes_refuse(self):
        self.check();self.kw["docs"]["UK"].pdf_bytes=b"changed"
        with self.assertRaises(PermanentError):self.check()

    def test_payload_image_release_and_unknown_gates_refuse(self):
        self.payload.return_value.title="changed"
        with self.assertRaises(PermanentError):self.check()
        self.payload.return_value=copy.deepcopy(self.kw["payload"])
        self.images.return_value["images"]=[("image.png",b"changed")]
        with self.assertRaises(PermanentError):self.check()
        self.images.return_value={**copy.deepcopy(self.kw["listing_images"]),"problems":[]}
        self.gates.return_value={}
        with self.assertRaises(PermanentError):self.check()
        self.gates.return_value={"blocks_release":False};self.kw["release"]="changed"
        with self.assertRaises(PermanentError):self.check()

    def test_gate_changed_after_claim_blocks_real_client_http_and_retry(self):
        t=FakeTransport();client=EtsyClient(t,credentials=CREDS,phase="production",owner_authorised=True)
        original=draft_intent.claim
        def claim(*a,**kw):
            out=original(*a,**kw);self.gates.return_value={"blocks_release":True};return out
        with patch.object(draft_intent,"claim",side_effect=claim):
            with self.assertRaises(PermanentError):pipeline._publish_and_read_back(self.ctx,client,**self.kw)
        self.assertEqual(t.calls,[])
        with self.assertRaises(draft_intent.ReconciliationRequired):pipeline._publish_and_read_back(self.ctx,client,**self.kw)
        self.assertEqual(t.calls,[])

    def test_mutation_after_reservation_refuses_even_if_current_payload_agrees(self):
        t=FakeTransport();client=EtsyClient(t,credentials=CREDS,phase="production",owner_authorised=True)
        original=draft_intent.claim
        def claim(*a,**kw):
            out=original(*a,**kw)
            self.kw["payload"].title="changed together"
            self.payload.return_value.title="changed together"
            return out
        with patch.object(draft_intent,"claim",side_effect=claim):
            with self.assertRaises(PermanentError):pipeline._publish_and_read_back(self.ctx,client,**self.kw)
        self.assertEqual(t.calls,[])

    def test_owner_revocation_inside_client_blocks_http(self):
        t=FakeTransport();client=EtsyClient(t,credentials=CREDS,phase="production",owner_authorised=True)
        original=client.refusal
        def refusal():
            out=original();os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"]="0";return out
        with patch.object(client,"refusal",side_effect=refusal):
            with self.assertRaises(PermanentError):pipeline._publish_and_read_back(self.ctx,client,**self.kw)
        self.assertEqual(t.calls,[])

    def test_real_client_calls_callback_before_fake_http_create(self):
        t=FakeTransport();client=EtsyClient(t,credentials=CREDS,phase="production",owner_authorised=True);seen=[]
        def check():
            self.assertEqual(t.calls,[]);self.check();seen.append(True)
        client.publish(payload=self.kw["payload"],filename="synthetic.pdf",data=b"pdf",images=[],before_create=check)
        self.assertEqual(seen,[True]);self.assertTrue(t.calls)

    def test_missing_real_release_proof_refuses_without_http(self):
        # The synthetic DB row is deliberately not a genuine certified CIR.
        self.gates.side_effect=REAL_RELEASE_GATES
        t=FakeTransport();client=EtsyClient(t,credentials=CREDS,phase="production",owner_authorised=True)
        with self.assertRaises(PermanentError):pipeline._publish_and_read_back(self.ctx,client,**self.kw)
        self.assertEqual(t.calls,[])

    def test_env_flag_alone_no_longer_authorises(self):
        self.check()
        publication_authority.revoke(self.db,authorization=OWNER_TOKEN,approval_id=self.grant)
        self.assertEqual(os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"],"1")
        with self.assertRaises(PermanentError) as caught:self.check()
        self.assertIn("revoked",str(caught.exception))

    def test_phase_and_unavailable_evidence_refuse(self):
        os.environ["BRAMBLELOOP_PHASE"]="shadow"
        with self.assertRaises(PermanentError):self.check()
        os.environ["BRAMBLELOOP_PHASE"]="production";self.images.side_effect=RuntimeError("unavailable")
        with self.assertRaises(PermanentError):self.check()

if __name__=="__main__":unittest.main()
