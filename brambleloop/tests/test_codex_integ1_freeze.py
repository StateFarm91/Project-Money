"""The integration freeze is fixed in advance, not supplied by a challenger."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from brambleloop.quality import design_eval


class IntegrationFreezeTests(unittest.TestCase):
    def test_integ1_freeze_is_explicit_and_only_two_existing_cases_changed(self):
        before = json.loads(design_eval._MANIFEST.read_text())
        after = json.loads(design_eval._INTEG1_MANIFEST.read_text())
        self.assertEqual(after["freeze"]["basis_commit"],
                         "7c42e706569af8d255d716133fc333d5c600c747")
        self.assertEqual(after["freeze"]["operator"], "codex")
        self.assertTrue(after["freeze"]["reason"])
        self.assertEqual([c["id"] for c in before["cases"]], [c["id"] for c in after["cases"]])
        changed = {a["id"] for a, b in zip(before["cases"], after["cases"]) if a != b}
        self.assertEqual(changed, {"hexagonal-bread-basket", "hexagon-coaster-set"})
        with patch.object(design_eval, "materialize_cases", return_value=after["cases"]):
            self.assertEqual(design_eval.load_cases()["sha256"], after["sha256"])

    def test_untrusted_modified_manifest_is_refused(self):
        original = json.loads(design_eval._INTEG1_MANIFEST.read_text())
        original["cases"][0]["cir_sha256"] = "0" * 64
        original["sha256"] = design_eval._digest(original["cases"])
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "design_eval_cases_integ1.json"
            path.write_text(json.dumps(original))
            with patch.object(design_eval, "_MANIFEST", Path(tmp) / "missing.json"), \
                    patch.object(design_eval, "_INTEG1_MANIFEST", path), \
                    patch.object(design_eval, "materialize_cases", return_value=original["cases"]):
                with self.assertRaises(design_eval.DesignEvaluationRefused):
                    design_eval.load_cases()


if __name__ == "__main__":
    unittest.main()
