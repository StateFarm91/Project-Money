"""Whether the laboratory can receive the purchase, answered from evidence.

The owner's instruction before spending CA$292: do not ask me to buy until the complete
intake and analysis path is verified ready. The temptation in a readiness report is to
describe the parts that exist and let the reader infer the rest, so these tests are mostly
about the report being willing to say no.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.teardown import readiness  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_it_reports_not_ready_while_nothing_can_read_a_page():
    """The purchase would land, be filed, be hashed, be manifested -- and then sit there."""
    out = readiness.check(_db())
    assert out["ready_for_purchase"] is False
    assert out["verdict"].startswith("NOT READY")
    assert "pdf_ingestion" in out["blocking"]
    by_key = {c["key"]: c for c in out["capabilities"]}
    assert by_key["pdf_ingestion"]["retrieve_callers"] == []
    assert "the money bought a folder" in out["why_this_matters"]


def test_every_capability_the_owner_listed_is_covered():
    out = readiness.check(_db())
    keys = {c["key"] for c in out["capabilities"]}
    assert keys == {k for k, _ in readiness.CAPABILITIES}
    for capability in out["capabilities"]:
        assert capability["what"], capability
        assert capability["evidence"], capability


def test_readiness_is_checked_rather_than_declared():
    """A readiness report maintained by hand is a readiness report that says ready.

    The PDF check imports; the caller check reads the source tree. Both would change their
    answer if the capability appeared, which is the only property that makes a report worth
    reading twice.
    """
    source = (ROOT / "src/brambleloop/teardown/readiness.py").read_text()
    assert "importlib.util.find_spec" in source
    assert "ast.walk" in source
    # The quarantine's reader genuinely has no callers today, which is what makes this a
    # real check. The first version grepped the source text and found three hits, all of
    # them docstrings explaining what `retrieve` is for -- a check that cannot tell a call
    # from a sentence about a call reports the capability it exists to detect the absence of.
    assert readiness.retrieve_callers() == []
    # A reader *is* importable; the gap is a module, not a dependency, and saying so
    # correctly is the difference between "install something" and "write something".
    assert readiness._has_pdf_reader() is True


def test_the_report_names_what_is_missing_rather_than_only_that_something_is():
    out = readiness.check(_db())
    missing = out["what_is_missing"]
    assert "a reader" in missing
    assert "retrieve()" in missing
    assert "check_derived" in missing


def test_the_halves_that_do_work_are_not_talked_down():
    """Listing imagery and promises genuinely work, and an honest report says so."""
    out = readiness.check(_db())
    by_key = {c["key"]: c for c in out["capabilities"]}
    assert by_key["listing_images"]["ready"] is True
    assert by_key["listing_promises"]["ready"] is True
    assert by_key["provenance"]["ready"] is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
