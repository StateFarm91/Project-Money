"""FB2-R2 #3: an unreadable benchmark hash manifest refuses the render (fail closed).

No network and no provider: `_post` and the budget reservation are replaced by recorders
that fail the test if reached. Synthetic SQLite fixtures only.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkProduct  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402

ENV = {I.PROVIDER_VAR: "gpt-image-2", I.KEY_VAR: "synthetic-key"}
PHOTO = b"bytes of a purchased listing photo (fixture)"


class Reached(AssertionError):
    pass


class HashLookupFailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db = Database("sqlite:///" + str(root / "refs.db")); self.db.create_all()
        self.addCleanup(self.db.engine.dispose)
        with self.db.session() as s:
            s.add(BenchmarkProduct(ref="mjs-1", seller="fixture", files=[
                {"name": "photo.png", "role": "photo", "bytes": len(PHOTO),
                 "sha256": hashlib.sha256(PHOTO).hexdigest()}]))
        # A renamed copy: neutral directory and name, so only the byte test can catch it.
        renders = root / "renders"; renders.mkdir()
        self.renamed = renders / "hero-final.png"; self.renamed.write_bytes(PHOTO)
        self.ours = renders / "twin-hero.png"; self.ours.write_bytes(b"our own twin render")
        self.work = root / "work"

    def generate(self, ref):
        def post(*a, **k):
            raise Reached("provider request sent")

        def reserve(*a, **k):
            raise Reached("budget reserved")
        with patch.object(I, "_post", side_effect=post), \
                patch.object(I, "reserve_render", side_effect=reserve):
            return I.generate("a cardigan", reference_urls=[str(ref)], env=ENV,
                              work_dir=str(self.work), db=self.db)

    def test_lookup_failure_refuses_before_budget_or_request(self):
        with patch.object(O, "benchmark_file_hashes",
                          side_effect=RuntimeError("manifest table unavailable")):
            for ref in (self.renamed, self.ours):
                with self.assertRaises(I.ImagesRefused) as caught:
                    self.generate(ref)
                self.assertNotIsInstance(caught.exception, Reached)
                self.assertIn("UNKNOWN", str(caught.exception))
                self.assertIn("F-785", str(caught.exception))

    def test_working_lookup_still_catches_renamed_copy(self):
        with self.assertRaises(I.ImagesRefused) as caught:
            self.generate(self.renamed)
        self.assertIn("byte-identical", str(caught.exception))

    def test_working_lookup_lets_our_own_reference_reach_the_budget(self):
        # Control: with readable hashes our own render passes the reference checks and the
        # call proceeds to the budget reservation (stopped there by the recorder).
        with self.assertRaises(Reached) as caught:
            self.generate(self.ours)
        self.assertIn("budget", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
