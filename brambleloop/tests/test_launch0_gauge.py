"""C2 round-product redesign proof. No physical calibration or closure claims."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.products import vessels, launch0
from brambleloop.creative.prototype import gauge_for
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.cir.writer import write_pattern
from brambleloop.cir.reverse import compare
from brambleloop.cir.geometry import corners, VESSEL, DISC
from brambleloop.gates.certificate import certify, gauge_findings, GAUGE_STANDARD

class GaugeTests(unittest.TestCase):
    def products(self):
        return [vessels.build_basket(s.key) for s in vessels.BASKET_SIZES] + [vessels.build_hexagon_coaster()]

    def test_complete_construction_compile_reverse_certificate(self):
        assert len(self.products()) == 4  # three basket sizes + the coaster
        for c in self.products():
            with self.subTest(slug=c.slug):
                r=compile_cir(c);self.assertTrue(r.ok)
                twin=build_twin(c,r)
                self.assertFalse(twin.calibrated)
                self.assertIsNone(twin.size_refusal)
                self.assertEqual(compare(c,write_pattern(c,r)), [])
                self.assertTrue(certify(c).granted)
                self.assertFalse(gauge_findings(c))
                self.assertEqual(c.components[0].foundation_kind,"magic_ring")
                self.assertEqual(c.version,"1.2.0")
                if 'basket' in c.slug:
                    self.assertEqual(twin.shape,VESSEL)
                    self.assertEqual(c.risk_class,"B")
                else:
                    self.assertEqual(twin.shape,DISC)
                    self.assertEqual(corners(r.rows),6)
                    self.assertEqual(c.components[0].make,4)
                    self.assertEqual(c.components[0].rows[-2].color,"wine")

    def test_existing_basket_size_tolerance_and_materials(self):
        for spec in vessels.BASKET_SIZES:
            c=vessels.build_basket(spec.key);t=build_twin(c,compile_cir(c))
            # PT-10: width is across the points of the hexagon; the circle-formula target
            # (across_cm) lies between the points and the flats.
            self.assertLessEqual(t.across_flats_cm, spec.across_cm + 0.5)
            self.assertGreaterEqual(t.across_points_cm, spec.across_cm - 0.5)
            self.assertLess(abs(t.height_cm-spec.tall_cm),1.5)
            self.assertEqual(c.gauge,gauge_for("worsted"))
            self.assertTrue(all(m.yarn_weight=="worsted" and m.name=="worsted cotton" for m in c.materials))
        c=vessels.build_hexagon_coaster();t=build_twin(c,compile_cir(c))
        self.assertEqual(c.gauge,gauge_for("dk"))
        self.assertEqual((t.width_cm,t.across_flats_cm),(9.7,8.4))   # PT-10: hexagon spans
        self.assertTrue(all(m.yarn_weight=="dk" for m in c.materials))

    def test_invalid_old_gauge_and_broken_count_are_detected(self):
        c=vessels.build_basket();c.gauge=copy.deepcopy(c.gauge)
        c.gauge.stitches_per_10cm=18
        self.assertIn("GAUGE_OUTSIDE_DECLARED_YARN_BAND",[f.code for f in gauge_findings(c)])
        c=vessels.build_hexagon_coaster();c.components[0].rows[-1].declared_count+=1
        self.assertFalse(compile_cir(c).ok)

    def test_legacy_catalogue_does_not_gain_a_gauge_pass(self):
        # W4-PIPE3: the typed record (released 1.3.0, as drawn) is still refused; the design
        # passes only as the 1.4.0 re-engineering, whose gauge IS its yarn's derived gauge.
        from brambleloop.products.builder import as_drawn, for_slug
        c=as_drawn("autumn-oak-mosaic-throw")
        self.assertEqual((c.version,c.gauge.stitches_per_10cm),("1.3.0",16))
        self.assertFalse(certify(c).granted)
        self.assertIn("GAUGE_OUTSIDE_DECLARED_YARN_BAND",[f.code for f in certify(c).errors])
        n=for_slug("autumn-oak-mosaic-throw")
        self.assertEqual(n.version,"1.4.0")
        self.assertEqual(n.gauge.stitches_per_10cm,gauge_for("worsted").stitches_per_10cm)
        self.assertFalse(gauge_findings(n))
        self.assertTrue(certify(n).granted)

    def test_cloudline_explicit_symmetric_border_preserves_full_motifs(self):
        from brambleloop.products.motifs import get
        c=launch0.cir_for("cloudline_blanket");r=compile_cir(c);t=build_twin(c,r)
        self.assertTrue(r.ok)
        # PT-08: stitch-weighted row heights; PT-09: two-row stripes (1.2.0).
        self.assertEqual((t.width_cm,t.height_cm),(79.2,96.4))
        self.assertLess(abs(t.width_cm-78.8),0.5)
        self.assertLess(abs(t.height_cm-97.2),1.0)
        self.assertFalse(t.calibrated)
        self.assertEqual(c.version,"1.2.0")
        motif=get("diamond-lattice")
        rows=c.components[0].rows
        self.assertEqual(len(rows),100)
        for row in rows[:6]+rows[-6:]:
            self.assertEqual([(op.stitch,op.count) for op in row.ops],[("sc",99)])
            self.assertEqual(row.color,"cream")
        for index,row in enumerate(r.rows[6:-6]):
            codes=[]
            for op in row.ops:
                codes.extend(["1" if op.stitch=="dc" else "0"]*op.produces)
            self.assertEqual("".join(codes),motif.grid[index%8]*11)
        text=write_pattern(c,r)
        self.assertEqual(compare(c,text),[])
        self.assertIn("6 single-crochet rows",c.designer_notes)
        cert=certify(c)
        self.assertTrue(cert.granted,cert.blocking_reasons)
        self.assertEqual(cert.gauge_standard,GAUGE_STANDARD)
        # Adversarial mutation cannot retain approval just because dimensions once passed.
        c.gauge.stitches_per_10cm=16
        self.assertFalse(certify(c).granted)

if __name__=="__main__": unittest.main()
