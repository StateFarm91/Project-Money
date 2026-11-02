"""The held-out evidence set is fixed and cannot be chosen by a challenger."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from brambleloop.quality import design_eval


class FrozenCaseTests(unittest.TestCase):
    def test_case_hash_is_stable_and_includes_each_required_source(self):
        first = design_eval.load_cases()
        self.assertEqual(first, design_eval.load_cases())
        self.assertEqual(len(first["sha256"]), 64)
        self.assertEqual({c["kind"] for c in first["cases"]},
                         {"launch0", "benchmark_truth", "stitch_family"})
        self.assertEqual({c["id"] for c in first["cases"] if c["kind"] == "benchmark_truth"},
                         {"bench1_xs", "bench2"})

    def test_challenger_cases_and_changed_truth_are_refused(self):
        with self.assertRaises(design_eval.DesignEvaluationRefused):
            design_eval.load_cases(challenger_cases=[])
        with TemporaryDirectory() as tmp:
            changed = Path(tmp) / "truth.json"
            changed.write_text("{}")
            with patch.object(design_eval, "_BENCH2", changed):
                with self.assertRaises(design_eval.DesignEvaluationRefused):
                    design_eval.load_cases()
            with patch.object(design_eval, "_BENCH2", changed.parent / "missing.json"):
                with self.assertRaises(design_eval.DesignEvaluationRefused):
                    design_eval.load_cases()


if __name__ == "__main__":
    unittest.main()
