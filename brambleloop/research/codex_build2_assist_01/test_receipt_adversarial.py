"""Offline adversarial receipt tests against unchanged Claude source.

Exit 1 means desired behavior failed; it is not converted to an expected PASS.
Fixtures use public Etsy receipt status/Money fields, never actual customers.
"""
import argparse,copy,hashlib,json,os,socket,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--deps",required=True);args=ap.parse_args()
sys.path[:0]=[str(Path(args.deps).resolve()),str(ROOT/"src"),str(ROOT)]
for key in list(os.environ):
    if key.startswith(("ANTHROPIC","OPENAI","ETSY","GEMINI","GOOGLE_API","DATABASE_URL","BRAMBLELOOP_DATABASE")):
        os.environ.pop(key,None)
os.environ.update(BRAMBLELOOP_PHASE="shadow",BRAMBLELOOP_REQUIRE_POSTGRES="0")
def offline(*a,**k):raise RuntimeError("Network forbidden in Codex verification")
socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog,OAuthCredential,Listing,Order,OrderVersion,LedgerEntry,Customer
from brambleloop.commerce import orders_ingest as oi,buyer_trust
NOW=datetime(2026,9,27,12,tzinfo=timezone.utc)
OBSERVATIONS={}
def receipt(rid=1,*,days=10,paid=True,status="paid",refund=0,amount=1200,buyer=101):
    return {"receipt_id":rid,"buyer_user_id":buyer,"create_timestamp":int((NOW-timedelta(days=days)).timestamp()),
      "update_timestamp":int(NOW.timestamp()),"status":status,"is_paid":paid,
      "refunds":[{"amount":{"amount":refund,"divisor":100,"currency_code":"CAD"}}] if refund else [],
      "transactions":[{"transaction_id":rid*10,"listing_id":111,"quantity":1,
        "price":{"amount":amount,"divisor":100,"currency_code":"CAD"}}]}
class Feed:
    def __init__(self,rows,filter_created=False):self.rows=rows;self.calls=0;self.filter_created=filter_created;self.since=None
    def receipts(self,*,since):
        self.calls+=1;self.since=since
        return [r for r in self.rows if not self.filter_created or since is None or r["create_timestamp"]>=since.timestamp()]
def snapshot(db):
    with db.session() as s:
        return {
          "orders":[{k:getattr(o,k) for k in ("external_ref","version","revenue_cad","contribution_cad","refunded","is_repeat","acquisition_source")} for o in s.scalars(select(Order))],
          "ledger":[{k:getattr(o,k) for k in ("evidence_ref","gross_cad","refunds_cad","net_cad")} for o in s.scalars(select(LedgerEntry))],
          "versions":[{"ref":o.order_ref,"version":o.version} for o in s.scalars(select(OrderVersion))],
          "customers":[{"ref":o.customer_ref,"first_seen_at":o.first_seen_at.isoformat()} for o in s.scalars(select(Customer))]}
class ReceiptCases(unittest.TestCase):
    def setUp(self):
        temp=HERE/".tmp";temp.mkdir(exist_ok=True)
        self.directory=Path(tempfile.mkdtemp(prefix="receipts_",dir=temp)).resolve()
        assert self.directory.is_relative_to(temp.resolve())
        self.url="sqlite:///"+str(self.directory/"case.db").replace("\\","/")
        self.db=Database(self.url,scratch=True);self.db.create_all()
        with self.db.session() as s:
            s.add(AuditLog(actor="codex-test",action="etsy.probe",detail={"ok":True}))
            s.add(OAuthCredential(provider="etsy",refresh_token_sealed="synthetic-not-a-token",
               token_fingerprint="synthetic",scopes="transactions_r"))
            s.add(Listing(product_slug="codex-synthetic-product",version="2.0.0",
              title="Synthetic fixture",description="",price_cad=12,state="published",
              etsy_listing_id="111",created_at=NOW-timedelta(days=2)))
        self.notes={}
    def tearDown(self):
        OBSERVATIONS[self._testMethodName]={"state":snapshot(self.db),"notes":self.notes}
        self.db.engine.dispose()
    def ingest(self,rows,**kwargs):
        return oi.ingest(self.db,reader=Feed(rows,**kwargs),now=NOW)
    def test_control_paid_receipt_is_idempotent(self):
        self.ingest([receipt()]);self.ingest([receipt()])
        v=snapshot(self.db)
        self.assertEqual((len(v["orders"]),len(v["ledger"]),len(v["versions"])),(1,1,1))
    def test_control_closed_gate_never_reads_feed(self):
        with self.db.session() as s:s.get(OAuthCredential,"etsy").scopes=""
        feed=Feed([receipt()]);out=oi.ingest(self.db,reader=feed,now=NOW)
        self.assertFalse(out["ran"]);self.assertEqual(feed.calls,0);self.assertEqual(snapshot(self.db)["orders"],[])
    def test_O01_late_full_refund_reconciles_existing_order(self):
        self.ingest([receipt()]);self.ingest([receipt(refund=1200)])
        v=snapshot(self.db)
        self.assertEqual((v["orders"][0]["revenue_cad"],v["ledger"][0]["refunds_cad"]),(0,12))
    def test_O01_partial_refund_preserves_unreturned_revenue(self):
        self.ingest([receipt(refund=200)])
        v=snapshot(self.db)
        self.assertEqual((v["orders"][0]["revenue_cad"],v["ledger"][0]["refunds_cad"]),(10,2))
    def test_O01_old_modified_receipt_is_not_lost_to_creation_watermark(self):
        self.ingest([receipt(1,days=60),receipt(2,days=1,buyer=202)])
        feed=Feed([receipt(1,days=60,refund=1200),receipt(2,days=1,buyer=202)],filter_created=True)
        oi.ingest(self.db,reader=feed,now=NOW)
        self.notes["requested_since"]=feed.since.isoformat()
        self.assertEqual(snapshot(self.db)["orders"][0]["revenue_cad"],0)
    def test_O02_unpaid_open_receipt_creates_no_sales_revenue(self):
        self.ingest([receipt(paid=False,status="open")]);v=snapshot(self.db)
        self.assertEqual(sum(r["revenue_cad"] for r in v["orders"]),0)
    def test_O02_cancelled_receipt_creates_no_sales_revenue(self):
        self.ingest([receipt(status="canceled")]);v=snapshot(self.db)
        self.assertEqual(sum(r["revenue_cad"] for r in v["orders"]),0)
    def test_O03_imported_old_sale_does_not_inherit_future_listing_version(self):
        self.ingest([receipt(days=60)]);v=snapshot(self.db)
        self.assertNotIn("2.0.0",[r["version"] for r in v["versions"]],
          "Only the current listing version is known, and it postdates this sale; preserve unknown.")
    def test_O04_first_purchase_is_earliest_not_first_encountered(self):
        self.ingest([receipt(2,days=1),receipt(1,days=60)])
        first=snapshot(self.db)["customers"][0]["first_seen_at"]
        self.assertTrue(first.startswith((NOW-timedelta(days=60)).date().isoformat()),first)
    def test_O05_retry_after_order_commit_repairs_version_evidence(self):
        with patch.object(buyer_trust,"record_sale_version",side_effect=RuntimeError("injected post-order-commit interruption")):
            with self.assertRaisesRegex(RuntimeError,"injected"):self.ingest([receipt()])
        self.notes["after_interruption"]=snapshot(self.db)
        self.db.engine.dispose();self.db=Database(self.url,scratch=True)
        self.ingest([receipt()]);v=snapshot(self.db)
        self.assertEqual((len(v["orders"]),len(v["versions"]),len(v["ledger"])),(1,1,1))
    def test_O07_negative_contribution_matches_negative_ledger(self):
        self.ingest([receipt(amount=1)]);v=snapshot(self.db)
        self.assertLess(v["ledger"][0]["net_cad"],0)
        self.assertAlmostEqual(v["orders"][0]["contribution_cad"],v["ledger"][0]["net_cad"],places=2)
class Recorder(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.records=[]
    def addSuccess(self,t):super().addSuccess(t);self.records.append({"test":t._testMethodName,"status":"PASS"})
    def addFailure(self,t,e):
        super().addFailure(t,e);self.records.append({"test":t._testMethodName,"status":"FAIL","detail":self._exc_info_to_string(e,t)})
    def addError(self,t,e):
        super().addError(t,e);self.records.append({"test":t._testMethodName,"status":"ERROR","detail":self._exc_info_to_string(e,t)})
if __name__=="__main__":
    out=HERE/"out";out.mkdir(exist_ok=True)
    result=unittest.TextTestRunner(verbosity=1,resultclass=Recorder).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReceiptCases))
    data={"base_sha":"4edacff1f8b445a84749464dc1d7271e6c71173e","scope":"unchanged source, direct production ingest service; fresh/reopened SQLite; no network",
      "tests":result.records,"observations":OBSERVATIONS,"ran":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
      "spend_usd":0,"source_hashes":{name:hashlib.sha256((ROOT/"src/brambleloop"/name).read_bytes()).hexdigest()
        for name in ["commerce/orders_ingest.py","commerce/cohorts.py","commerce/buyer_trust.py"]},
      "public_fixture_schema_sources":["https://developer.etsy.com/documentation/reference","https://developers.etsy.com/documentation/essentials/definitions/"]}
    (out/"receipt_adversarial.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"tests":data["ran"],"failures":data["failures"],"errors":data["errors"],"paid_spend":0}))
    sys.exit(0 if result.wasSuccessful() else 1)
