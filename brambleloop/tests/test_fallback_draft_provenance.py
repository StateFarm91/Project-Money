"""G-R2: the `concept_to_cir` fallback draft carries its real lineage, or none.

Synthetic local evidence only (SQLite, no network): proves the producer/consumer contract
from the queued `cir.draft` inputs through compile to the certificate's provenance stage. It
is not an originality, ownership or release proof.
"""
import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import PatternVersion, Product  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

SLUG = "nordic-forest-basket"
PROVENANCE_CODES = {"PROVENANCE_MISSING", "PROVENANCE_INCOMPLETE", "PROVENANCE_NOT_OURS"}


class FallbackProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Database("sqlite:///" + str(Path(self.tmp.name) / "fallback.db"))
        self.db.create_all(); self.addCleanup(self.db.engine.dispose)
        self.seed = pipeline._seed_for(SLUG)
        self.assertIsNotNone(self.seed)
        self.assertIsNone(pipeline._engineered_cir(SLUG))
        # A certified earlier version makes this a rebuild (established), so the real handler
        # takes the concept_to_cir fallback with the radar slot's queued inputs.
        with self.db.session() as s:
            p = Product(slug=SLUG, title=self.seed.title); s.add(p); s.flush()
            s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))

    def payload(self, **extra):
        # What `radar.score` queues: the scored seed plus concept_geometry(seed).
        out = {k: v for k, v in dataclasses.asdict(self.seed).items()
               if not isinstance(v, tuple)}
        out.update(pipeline.concept_geometry(self.seed))
        out.update(extra)
        return out

    def draft(self, inputs):
        emitted, audits = [], []
        ctx = SimpleNamespace(
            db=self.db, job=SimpleNamespace(inputs=inputs),
            audit=lambda action, **kw: audits.append((action, kw)),
            enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
        result = pipeline.handle_cir_draft(ctx)
        return ctx, result, emitted, audits

    def compiled_cir(self, ctx, emitted):
        self.assertEqual(emitted[0][0], "cir.compile")
        cir = CIR.from_dict(emitted[0][1]["cir"])
        ctx.job.inputs = emitted[0][1]
        pipeline.handle_cir_compile(ctx)
        self.assertEqual(emitted[-1][0], "gate.certify")
        self.assertEqual(emitted[-1][1]["cir"].get("provenance"),
                         cir.to_dict().get("provenance"))
        return cir

    def test_radar_fallback_records_real_producer_and_passes_provenance_stage(self):
        inputs = self.payload()
        ctx, result, emitted, audits = self.draft(inputs)
        cir = self.compiled_cir(ctx, emitted)
        prov = cir.provenance
        self.assertIsNotNone(prov)
        self.assertEqual(prov.concept_key, SLUG)
        self.assertEqual(prov.generated_by, "brambleloop")
        self.assertEqual(prov.benchmarks_consulted, ())
        self.assertEqual(prov.primitives_used, (
            "runtime.pipeline.concept_to_cir",
            f"runtime.pipeline.concept_geometry:{self.seed.category}",
            "creative.prototype.gauge_for:worsted"))
        # Independently recompute the digest from the queued inputs: it binds this design.
        concept = pipeline.Concept(
            slug=SLUG, title=inputs["title"], category=inputs["category"],
            stitch_repeat=[(a, b) for a, b in inputs["stitch_repeat"]],
            width_stitches=inputs["width_stitches"], rows=inputs["rows"],
            colors=inputs["colors"], opportunity_score=inputs.get("opportunity_score", 0.0),
            season=inputs.get("season"), risk_class=inputs.get("risk_class", "A"))
        concept.source_provenance = f"radar.pool:{SLUG}"
        _, brief, _ = __import__("brambleloop.creative.preengineering",
                                 fromlist=["concept_from"]).concept_from(inputs)
        concept.source_brief = brief or None
        expected = O.brief_digest({"concept": {**concept.__dict__,
                                               "provenance": concept.source_provenance},
                                   "brief": brief or None,
                                   "primitives": list(prov.primitives_used)})
        self.assertEqual(prov.brief_digest, expected)
        # A different design gives a different digest.
        other = O.brief_digest({"concept": {**concept.__dict__, "rows": concept.rows + 2,
                                            "provenance": concept.source_provenance},
                                "brief": brief or None,
                                "primitives": list(prov.primitives_used)})
        self.assertNotEqual(prov.brief_digest, other)
        codes = {f.code for f in O.provenance_findings(cir)}
        self.assertFalse(codes & PROVENANCE_CODES, codes)
        cert_codes = {f.code for f in certify(cir, db=self.db).errors}
        self.assertFalse(cert_codes & PROVENANCE_CODES, cert_codes)
        drafted = [kw for a, kw in audits if a == "cir.drafted"]
        self.assertEqual(drafted[0]["detail"]["provenance"], "recorded")

    def test_brief_benchmarks_are_carried_so_the_gate_still_decides(self):
        ctx, result, emitted, _ = self.draft(self.payload(
            benchmarks_consulted=["synthetic-brief-source"], provenance="benchmark:lineage-src"))
        cir = self.compiled_cir(ctx, emitted)
        self.assertEqual(cir.provenance.benchmarks_consulted,
                         ("synthetic-brief-source", "lineage-src"))
        self.assertIn("DESIGN_LEDGER_MISSING", {f.code for f in certify(cir, db=self.db).errors})

    def test_geometry_the_table_did_not_produce_is_unknown_and_refused(self):
        inputs = self.payload(rows=self.payload()["rows"] + 2)
        ctx, result, emitted, audits = self.draft(inputs)
        cir = self.compiled_cir(ctx, emitted)
        self.assertIsNone(cir.provenance)
        self.assertIn("PROVENANCE_MISSING", {f.code for f in certify(cir, db=self.db).errors})
        drafted = [kw for a, kw in audits if a == "cir.drafted"]
        self.assertTrue(drafted[0]["detail"]["provenance"].startswith("UNKNOWN"))

    def test_raw_geometry_without_seed_stays_unqualified(self):
        ctx, result, emitted, _ = self.draft({
            "slug": "raw-local-geometry", "title": "Raw", "category": "blanket",
            "stitch_repeat": [["sc", 4]], "width_stitches": 20, "rows": 12,
            "colors": {"cream": "#ffffff"}})
        cir = self.compiled_cir(ctx, emitted)
        self.assertIsNone(cir.provenance)
        self.assertIn("PROVENANCE_MISSING", {f.code for f in certify(cir, db=self.db).errors})

    def test_malformed_benchmark_identity_refuses_the_draft(self):
        for refs in ([123], [""], "abc"):
            ctx, result, emitted, audits = self.draft(self.payload(benchmarks_consulted=refs))
            self.assertFalse(result["drafted"])
            self.assertEqual(emitted, [])
            self.assertIn("cir.draft_refused", [a for a, _ in audits])


if __name__ == "__main__":
    unittest.main()
