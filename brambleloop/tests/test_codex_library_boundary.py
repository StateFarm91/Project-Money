"""The private benchmark library must not enter source or the image context."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from brambleloop.teardown.library import LIBRARY_ENV, LibraryRefused, library_root


class LibraryBoundaryTests(unittest.TestCase):
    def test_rejects_source_tree_and_symlink_into_it(self):
        source = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            link = Path(tmp) / "linked-source"
            link.symlink_to(source, target_is_directory=True)
            for root in (source / "benchmark_library", link / "benchmark_library"):
                with self.assertRaises(LibraryRefused):
                    library_root({LIBRARY_ENV: str(root)})


    def test_accepts_external_quarantine(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(library_root({LIBRARY_ENV: tmp}), Path(tmp).resolve())


if __name__ == "__main__":
    unittest.main()
