"""Receipt identity detects source edits without relying on a Git commit changing."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'research/final_build/codex/run_local_suite.py'
spec = importlib.util.spec_from_file_location('local_suite_runner', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SourceIdentityTests(unittest.TestCase):
    def test_uncommitted_edit_and_new_module_change_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'src'
            source.mkdir()
            fake_runner = root / 'runner.py'
            fake_runner.write_bytes(SCRIPT.read_bytes())
            old_file = runner.__file__
            runner.__file__ = str(fake_runner)
            try:
                module = source / 'gate.py'
                module.write_text('allow = False\n')
                original = runner.source_fingerprint(root)
                module.write_text('allow = True\n')
                self.assertNotEqual(original, runner.source_fingerprint(root))
                module.write_text('allow = False\n')
                self.assertEqual(original, runner.source_fingerprint(root))
                (source / 'new_gate.py').write_text('allow = True\n')
                self.assertNotEqual(original, runner.source_fingerprint(root))
            finally:
                runner.__file__ = old_file

    def test_generated_evidence_and_bytecode_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src').mkdir()
            fake_runner = root / 'runner.py'
            fake_runner.write_bytes(SCRIPT.read_bytes())
            old_file = runner.__file__
            runner.__file__ = str(fake_runner)
            try:
                original = runner.source_fingerprint(root)
                (root / 'src/__pycache__').mkdir()
                (root / 'src/__pycache__/test.pyc').write_bytes(b'generated')
                (root / 'research/evidence').mkdir(parents=True)
                (root / 'research/evidence/result.json').write_text('{}')
                self.assertEqual(original, runner.source_fingerprint(root))
            finally:
                runner.__file__ = old_file


if __name__ == '__main__':
    unittest.main()
