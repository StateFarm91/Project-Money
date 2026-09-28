"""Synthetic local author/brief wiring evidence; not market, ownership or live proof."""
import sys, tempfile, unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_prototype import _concept
from brambleloop.creative import prototype as P, intake
from brambleloop.creative.concept import Concept as CreativeConcept
from brambleloop.creative.prospecting import Candidate
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import JobContext
from brambleloop.runtime import pipeline
from brambleloop.gates.certificate import certify
from brambleloop.gates import originality as O
from brambleloop.publish.release_gates import originality_gate
from brambleloop.core.models import Product, PatternVersion
from brambleloop.cir.compiler import compile_cir

class AuthorProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database("sqlite:///"+str(Path(self.tmp.name)/"lineage.db"));self.db.create_all()
        self.addCleanup(self.db.engine.dispose);Registry(self.db).seed_defaults()
        self.c=_concept("rectangle_throw","flat_rows")

    def test_brief_only_source_survives_author_and_blocks_certify_publish(self):
        cir=P.author(self.c,brief={"benchmarks_consulted":["synthetic-owned-source"]})
        self.assertTrue(compile_cir(cir).ok)
        self.assertEqual(cir.provenance.benchmarks_consulted,("synthetic-owned-source",))
        self.assertIn("DESIGN_LEDGER_MISSING",[f.code for f in certify(cir,db=self.db).errors])
        # Simulate obsolete approval only to test current protected gate, not valid evidence.
        with self.db.session() as s:
            p=Product(slug=cir.slug,title=cir.title);s.add(p);s.flush()
            s.add(PatternVersion(product_id=p.id,version=cir.version,cir_json=cir.to_dict(),certified=True))
        result=originality_gate(self.db,slug=cir.slug,version=cir.version)
        self.assertTrue(result["blocks"])
        self.assertTrue(any("DESIGN_LEDGER_MISSING" in x for x in result["reasons"]))

    def test_exact_source_ids_and_context_change_digest(self):
        self.c=replace(self.c,provenance="benchmark:exact-source-A")
        a=P.author(self.c,brief={"benchmarks_consulted":["Exact Source B"],"source_context":{"gap_id":17}})
        b=P.author(self.c,brief={"benchmarks_consulted":["Exact Source B"],"source_context":{"gap_id":18}})
        self.assertEqual(a.provenance.benchmarks_consulted,("Exact Source B","exact-source-A"))
        self.assertNotEqual(a.provenance.brief_digest,b.provenance.brief_digest)

    def test_malformed_source_identity_is_not_stringified(self):
        for refs in ("abc",[123],[{}],[""]):
            with self.assertRaises(P.PrototypeRefused): P.author(self.c,brief={"benchmarks_consulted":refs})

    def test_raw_geometry_without_source_stays_unqualified(self):
        raw=pipeline.Concept(slug="raw-local",title="Raw",category="blanket",stitch_repeat=[("sc",4)],
                             width_stitches=20,rows=12,colors={"cream":"#ffffff"})
        cir=pipeline.concept_to_cir(raw)
        self.assertIsNone(cir.provenance)
        self.assertIn("PROVENANCE_MISSING",[f.code for f in certify(cir,db=self.db).errors])

    def test_actual_intake_preserves_benchmark_lineage_and_brief(self):
        self.c=replace(self.c,provenance="benchmark:original-source")
        q=JobQueue(self.db)
        ctx=JobContext(job=q.enqueue("creative_director","creative.tournament",{}),db=self.db,
                       queue=q,registry=Registry(self.db),phase=None)
        intake.intake(ctx,candidate=Candidate(concept=self.c,slot=None),
                      plan={"lessons":{"lesson_ids":[]},"vision":None,
                            "brief":{"benchmarks_consulted":["brief-only-source"],
                                     "design_difference_ledger":[],"source_context":{"opaque":"unchanged"}}},
                      source="synthetic-test",funnel_rounds=[])
        detail=intake.intake_rows(self.db)[0][2]
        payload=detail["payload"]
        self.assertEqual(payload["concept"]["provenance"],"benchmark:original-source")
        self.assertEqual(payload["brief"]["benchmarks_consulted"],["brief-only-source","original-source"])
        self.assertEqual(payload["brief"]["source_context"],{"opaque":"unchanged"})
        # Intake correctly refuses unproven research/absent funnel. Author boundary only.
        self.assertNotEqual(detail["decision"],intake.ENGINEERING)
        emitted=[]
        author_ctx=SimpleNamespace(db=self.db,job=SimpleNamespace(inputs=payload),
                    audit=lambda *a,**k:None,
                    enqueue=lambda role,kind,inputs,**kw:emitted.append((kind,inputs)))
        result=pipeline._draft_creative(author_ctx,payload["slug"])
        self.assertTrue(result["drafted"])
        from brambleloop.cir.model import CIR
        cir=CIR.from_dict(emitted[0][1]["cir"])
        self.assertEqual(emitted[0][0],"cir.compile")
        # Exercise the real compile consumer and its emitted certificate input too.
        author_ctx.job.inputs=emitted[0][1]
        pipeline.handle_cir_compile(author_ctx)
        self.assertEqual(emitted[-1][0],"gate.certify")
        self.assertEqual(emitted[-1][1]["cir"]["provenance"],cir.to_dict()["provenance"])
        self.assertEqual(cir.provenance.benchmarks_consulted,("brief-only-source","original-source"))
        self.assertFalse(certify(cir,db=self.db).granted)

if __name__=="__main__": unittest.main()
