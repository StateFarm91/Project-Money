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
from brambleloop.gates.certificate import certify, gauge_findings

class GaugeTests(unittest.TestCase):
    def products(self):
        return [vessels.build_basket(s.key) for s in vessels.BASKET_SIZES] + [vessels.build_hexagon_coaster()]

    def test_complete_construction_compile_reverse_certificate(self):
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
                self.assertEqual(c.version,"1.1.0")
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
            self.assertLess(abs(t.width_cm-spec.across_cm),1.5)
            self.assertLess(abs(t.height_cm-spec.tall_cm),1.5)
            self.assertEqual(c.gauge,gauge_for("worsted"))
            self.assertTrue(all(m.yarn_weight=="worsted" and m.name=="worsted cotton" for m in c.materials))
        c=vessels.build_hexagon_coaster();t=build_twin(c,compile_cir(c))
        self.assertEqual(c.gauge,gauge_for("dk"))
        self.assertEqual(t.width_cm,9.2)
        self.assertTrue(all(m.yarn_weight=="dk" for m in c.materials))

    def test_invalid_old_gauge_and_broken_count_are_detected(self):
        c=vessels.build_basket();c.gauge=copy.deepcopy(c.gauge)
        c.gauge.stitches_per_10cm=18
        self.assertIn("GAUGE_OUTSIDE_DECLARED_YARN_BAND",[f.code for f in gauge_findings(c)])
        c=vessels.build_hexagon_coaster();c.components[0].rows[-1].declared_count+=1
        self.assertFalse(compile_cir(c).ok)

    def test_cloudline_still_explicitly_unqualified(self):
        c=launch0.cir_for("cloudline_blanket")
        self.assertIn("GAUGE_OUTSIDE_DECLARED_YARN_BAND",[f.code for f in gauge_findings(c)])
        self.assertIsNone(certify(c).gauge_standard)

if __name__=="__main__": unittest.main()
