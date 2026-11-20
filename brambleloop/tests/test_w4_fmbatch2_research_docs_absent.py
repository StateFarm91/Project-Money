"""F-405 in the deploy image: the repository documents are absent there, and the internal
search reports each as unavailable rather than skipping it or failing."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import research as R  # noqa: E402


def test_absent_repository_documents_are_reported_unavailable():
    missing = Path(tempfile.mkdtemp(prefix="nodocs-"))
    real = dict(R.DOCUMENTS)
    R.DOCUMENTS = {name: missing / name for name in real}
    try:
        db = Database("sqlite://", scratch=True)
        db.create_all()
        _evidence, searched = R.search_internal_report(db, ["yarn"])
    finally:
        R.DOCUMENTS = real
    by = {s["corpus"]: s for s in searched}
    for name in ("BUILD_STATE.md", "DECISION_LOG.md"):
        assert by[name]["hits"] is None and "not present" in by[name]["why"], by.get(name)


if __name__ == "__main__":
    test_absent_repository_documents_are_reported_unavailable()
    print("OK   test_absent_repository_documents_are_reported_unavailable")
