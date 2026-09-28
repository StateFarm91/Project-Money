"""Zero-cost adversarial proof-packet contract tests; synthetic data never certifies."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.build2.final_proof import STAGES, audit, validate


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "raw.json").write_text('{"synthetic":true}')
        self.head = "a" * 40
        self.row = {"uid": "F-514@v0.15", "protected_effect": "release", "protected_action_applicability": "protected"}
        def receipt(**extra):
            return dict(artifact="raw", head=self.head, run_id="run-1", observed=True, **extra)
        chain = {}
        prev = None
        for stage in STAGES:
            chain[stage] = receipt(identity=stage, input=prev)
            prev = stage
        self.packet = dict(uid=self.row["uid"], head=self.head, run_id="run-1",
            evidence_class="runtime", direct=True, implementer="builder", chain=chain,
            artifacts={"raw": {"path": "raw.json", "sha256": hashlib.sha256((self.root / "raw.json").read_bytes()).hexdigest()}},
            live_root=receipt(kind="worker", producer="producer"), production_producer=receipt(),
            failure_test=receipt(), suite=receipt(passed=5, failed=0, clean=True),
            execution_gate=receipt(phase="execution", effect="effect", outcome="refused"),
            independent_review=receipt(reviewer="reviewer", verdict="supported", result="result"))

    def check_packet(self, packet):
        return validate(self.row, packet, head=self.head, root=self.root)

    def test_complete_contract_is_reviewable_never_certified(self):
        result = self.check_packet(self.packet)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["verdict"], "REVIEWABLE")
        self.assertFalse(result["certified"])

    def test_each_missing_chain_stage_blocks(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                packet = copy.deepcopy(self.packet)
                del packet["chain"][stage]
                self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")

    def test_mutations_refused(self):
        mutations = [
            ("head", "b" * 40), ("uid", "F-514@v0.16"), ("evidence_class", "fixture"),
            ("evidence_class", "static"), ("direct", False), ("run_id", "other")]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                packet = copy.deepcopy(self.packet); packet[key] = value
                self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")

    def test_required_receipt_mutations(self):
        mutations = [("consumer", "input", "unrelated"), ("consumer", "observed", False)]
        for stage, key, value in mutations:
            packet = copy.deepcopy(self.packet); packet["chain"][stage][key] = value
            self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")
        for section, key, value in [
            ("execution_gate", "phase", "planning"), ("execution_gate", "effect", "other"),
            ("independent_review", "reviewer", "builder"), ("independent_review", "result", "other"),
            ("suite", "failed", 1), ("suite", "passed", 0), ("suite", "clean", False),
            ("live_root", "kind", "library"), ("production_producer", "observed", False)]:
            with self.subTest(section=section, key=key):
                packet = copy.deepcopy(self.packet); packet[section][key] = value
                self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")

    def test_malformed_receipts_fail_closed(self):
        for section in ("live_root", "suite", "independent_review", "execution_gate", "chain"):
            for value in (None, [], "bad"):
                with self.subTest(section=section, value=value):
                    packet = copy.deepcopy(self.packet); packet[section] = value
                    self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")
        for value in (None, [], "3", True):
            packet = copy.deepcopy(self.packet); packet["suite"]["passed"] = value
            self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")
        for stage in STAGES:
            packet = copy.deepcopy(self.packet); packet["chain"][stage] = []
            self.assertEqual(self.check_packet(packet)["verdict"], "BLOCKED")

    def test_absent_audited_applicability_is_unknown(self):
        del self.row["protected_action_applicability"]
        result = self.check_packet(self.packet)
        self.assertIn("protected-action applicability unknown", result["errors"])
        self.assertEqual(result["verdict"], "BLOCKED")

    def test_changed_artifact_blocks(self):
        (self.root / "raw.json").write_text("changed")
        self.assertEqual(self.check_packet(self.packet)["verdict"], "BLOCKED")

    def test_path_escape_blocks(self):
        self.packet["artifacts"]["raw"]["path"] = "../outside"
        self.assertEqual(self.check_packet(self.packet)["verdict"], "BLOCKED")

    def test_cli_reads_real_matrix_schema_and_persists_refusal(self):
        matrix = self.root / "matrix.json"
        packets = self.root / "packets.json"
        output = self.root / "report.json"
        matrix.write_text(json.dumps({"matrix": [self.row]}))
        packets.write_text("[]")
        script = Path(__file__).resolve().parents[1] / "src/brambleloop/build2/final_proof.py"
        result = subprocess.run([sys.executable, str(script), "--matrix", str(matrix),
            "--packets", str(packets), "--head", self.head, "--artifacts", str(self.root),
            "--output", str(output)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(output.read_text())["rows"][0]["verdict"], "BLOCKED")
        self.assertEqual(json.loads(matrix.read_text()), {"matrix": [self.row]})
        with self.assertRaises(ValueError):
            audit([], [], head=self.head, root=self.root)

    def test_no_packet_and_qualified_duplicate_handling(self):
        other = {**self.row, "uid": "F-514@v0.16"}
        result = audit([self.row, other], [self.packet], head=self.head, root=self.root)
        self.assertEqual([r["verdict"] for r in result["rows"]], ["REVIEWABLE", "BLOCKED"])
        with self.assertRaises(ValueError):
            audit([self.row, self.row], [], head=self.head, root=self.root)
        with self.assertRaises(ValueError):
            audit([self.row], [self.packet, self.packet], head=self.head, root=self.root)


if __name__ == "__main__":
    unittest.main()
