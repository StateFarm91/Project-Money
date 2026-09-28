"""Synthetic local documents exercise real ingestion/DB consumers; no live services."""
import copy
import io
import tempfile
from pathlib import Path
import sys
import textwrap
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures
from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkListing, Product, PatternVersion
from brambleloop.intel import benchmarks
from brambleloop.gates import originality as O
from brambleloop.gates.certificate import certify
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.writer import write_pattern
from brambleloop.teardown import intake, library, licence
from brambleloop.publish import release_gates


def pdf(text):
    from reportlab.pdfgen.canvas import Canvas
    out=io.BytesIO(); c=Canvas(out)
    y=800
    for line in text.splitlines():
        for part in textwrap.wrap(line,95) or [""]:
            c.drawString(30,y,part);y-=12
            if y<35: c.showPage();y=800
    c.save();return out.getvalue()


class RuntimeOriginality(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"proof.db"
        self.db=Database("sqlite:///"+str(self.path));self.db.create_all()
        self.addCleanup(self.db.engine.dispose)
        self.env={library.LIBRARY_ENV:str(Path(self.tmp.name)/"quarantine")}
        self.cir=fixtures.good_mosaic_panel()
        self.text=write_pattern(self.cir,compile_cir(self.cir))
        with self.db.session() as s:
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,listing_ref="77",
                  title="Synthetic purchased evidence",pod="blankets",product_type="pattern",
                  price_cad=7,url="https://example.invalid/77",detail={}))

    def upload(self,text=None,data=None):
        return intake.receive(self.db,"77",[("pattern.pdf",data if data is not None else pdf(text or self.text))],
                              env=self.env,mirror_files=False)

    def test_real_intake_reopened_evidence_refuses_certificate(self):
        self.assertTrue(certify(self.cir,db=self.db).granted)
        out=self.upload()
        self.assertEqual(out["wording_readings"][0]["state"],"READ")
        other=Database("sqlite:///"+str(self.path));self.addCleanup(other.engine.dispose)
        self.assertTrue(O.fingerprints_from_db(other))
        cert=certify(self.cir,db=other)
        self.assertFalse(cert.granted)
        self.assertIn("SIMILARITY_ESCALATED",[f.code for f in cert.errors])

    def store_certificate(self):
        cert=certify(self.cir,db=self.db)
        self.assertTrue(cert.granted,cert.blocking_reasons)
        with self.db.session() as s:
            p=Product(slug=self.cir.slug,title=self.cir.title);s.add(p);s.flush()
            s.add(PatternVersion(product_id=p.id,version=self.cir.version,
                  cir_json=self.cir.to_dict(),certified=True,release_hash=cert.release_hash,
                  certificate=cert.to_dict()))

    def test_new_corpus_after_approval_blocks_current_publication_gate(self):
        self.store_certificate()
        kw=dict(slug=self.cir.slug,version=self.cir.version)
        self.assertFalse(release_gates.originality_gate(self.db,**kw)["blocks"])
        self.upload()
        after=release_gates.originality_gate(self.db,**kw)
        self.assertTrue(after["blocks"])
        self.assertTrue(any("SIMILARITY_ESCALATED" in x for x in after["reasons"]))
        # Use real assembled for_publish; unrelated missing listing checks may also refuse.
        assembled=release_gates.for_publish(self.db,**kw)
        self.assertTrue(assembled["blocks_release"])
        self.assertTrue(assembled["originality"]["blocks"])

    def test_publish_handler_refuses_before_external_effect(self):
        # Synthetic prerequisites isolate the real current-corpus gate and handler.
        from types import SimpleNamespace
        from contextlib import ExitStack
        from brambleloop.core.models import Listing, Phase
        from brambleloop.runtime import pipeline
        self.store_certificate()
        self.upload()
        with self.db.session() as session:
            session.add(Listing(product_slug=self.cir.slug, version=self.cir.version,
                                title="Synthetic listing", description="Synthetic", tags=[]))
        ctx=SimpleNamespace(db=self.db, phase=Phase.PRODUCTION,
                            job=SimpleNamespace(inputs=dict(slug=self.cir.slug,version=self.cir.version)),
                            audit=lambda *a,**k: None)
        with ExitStack() as stack:
            def mock(name, **kw): return stack.enter_context(patch(name, **kw))
            mock("brambleloop.runtime.pipeline._listing_parity",return_value={"blocks_release":False})
            mock("brambleloop.integrations.http.UrllibTransport")
            mock("brambleloop.integrations.etsy.Credentials.from_env")
            client=mock("brambleloop.integrations.etsy.EtsyClient").return_value
            client.refusal.return_value=None
            mock("brambleloop.runtime.etsy_ops.certified_payload",return_value={})
            mock("brambleloop.runtime.release._released_on",return_value=None)
            mock("brambleloop.publish.pdf.build_pattern_pdf",return_value=SimpleNamespace(pdf_bytes=b"synthetic"))
            mock("brambleloop.runtime.pipeline.check_pdf_hashes",return_value={})
            mock("brambleloop.creative.preengineering.release_grid_verdict",return_value={"cleared":True})
            result=pipeline.handle_store_publish(ctx)
            self.assertTrue(result["blocked"])
            self.assertTrue(any("SIMILARITY_ESCALATED" in x for x in result["reasons"]))
            self.assertEqual([c[0] for c in client.mock_calls],["refusal"])

    def test_failed_replacement_removes_stale_wording_authority(self):
        self.upload()
        out=self.upload(data=b"not a PDF")
        self.assertEqual(out["wording_readings"][0]["state"],"UNKNOWN")
        self.assertFalse(O.fingerprints_from_db(self.db)[0].wording)
        self.assertIn("ORIGINALITY_EVIDENCE_UNKNOWN",[f.code for f in certify(self.cir,db=self.db).errors])

    def test_licence_revocation_is_read_at_execution(self):
        # Source is explicitly research, not licensed adaptation. Keep text unrelated.
        self.upload(text=" ".join("independentword"+str(n) for n in range(70)))
        self.cir.provenance.benchmarks_consulted=("mjs-77",)
        entry={"benchmark_ref":"mjs-77","learned":"test independent demand", "why_better":"no shoulder seams to sew and a neckline that sits on every size",
               "changed":[{"aspect":"construction","what":"top down raglan assembly"},
                          {"aspect":"fit","what":"graded positive ease","magnitude_pct":18}],
               "independent_aspects":["size chart","assembly"]}
        O.record_ledger(self.db,self.cir.provenance.concept_key,[entry])
        self.store_certificate()
        lic=licence.conservative("mjs-77")
        from dataclasses import replace
        licence.record(self.db,replace(lic,allowed_uses=(),prohibited_uses=licence.USES,
                                      terms_source="synthetic revoked private research rights"))
        gate=release_gates.originality_gate(self.db,slug=self.cir.slug,version=self.cir.version)
        self.assertTrue(any("ORIGINALITY_LICENCE_REFUSED" in x for x in gate["reasons"]))

    def test_denied_private_analysis_does_not_read_or_fingerprint(self):
        from dataclasses import replace
        licence.record(self.db,replace(licence.conservative("mjs-77"),
                       allowed_uses=(),prohibited_uses=licence.USES))
        with patch("brambleloop.teardown.reader.inventory",side_effect=AssertionError("must not extract")):
            out=self.upload()
        self.assertEqual(out["wording_readings"][0]["state"],"UNKNOWN")
        self.assertFalse(O.fingerprints_from_db(self.db))

    def test_no_database_and_missing_release_are_not_full_proof(self):
        cert=certify(self.cir)
        self.assertIn("ORIGINALITY_DURABLE_EVIDENCE_UNCHECKED",[f.code for f in cert.findings])
        self.assertEqual(release_gates.originality_gate(self.db,slug="absent",version="1")["state"],"UNKNOWN")
        self.store_certificate()
        with patch.object(O,"fingerprints_from_db",side_effect=RuntimeError("unavailable")):
            self.assertEqual(release_gates.originality_gate(self.db,slug=self.cir.slug,
                             version=self.cir.version)["state"],"UNKNOWN")

if __name__=="__main__": unittest.main()

