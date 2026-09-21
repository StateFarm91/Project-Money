"""Whether the laboratory can receive the purchase, answered from evidence.

The owner's instruction before spending CA$292: do not ask me to buy until the complete
intake and analysis path is verified ready. The temptation in a readiness report is to
describe the parts that exist and let the reader infer the rest, so these tests are mostly
about the report being willing to say no -- including now that the answer is yes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.teardown import reader, readiness  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_the_four_blocking_capabilities_are_now_backed_by_a_run():
    """Ready because something ran, not because a line was edited to say so."""
    out = readiness.check(_db())
    by_key = {c["key"]: c for c in out["capabilities"]}
    proof = by_key["pdf_ingestion"]["self_test"]

    assert out["ready_for_purchase"] is True
    assert out["blocking"] == []
    assert proof["ran"] is True and proof["ready"] is True
    assert proof["pages_with_text"] == proof["pages"] > 1
    assert proof["sections_not_found"] == []
    assert by_key["pdf_ingestion"]["retrieve_callers"], "nothing calls retrieve()"


def test_it_still_reports_not_ready_when_nothing_can_read_a_page():
    """The check that matters: it changes its answer when the capability goes away.

    A readiness report that cannot say no is a sentence, not a check. So the reader is
    removed from under it and the report has to notice -- otherwise `READY` means only that
    somebody once wrote `READY`.
    """
    original = reader.available
    reader.available = lambda: ""
    try:
        out = readiness.check(_db())
    finally:
        reader.available = original

    assert out["ready_for_purchase"] is False
    assert out["verdict"].startswith("NOT READY")
    assert set(out["blocking"]) == {"pdf_ingestion", "pattern_analysis",
                                    "promise_cross_reference", "construction_to_object"}


def test_every_capability_the_owner_listed_is_covered():
    out = readiness.check(_db())
    keys = {c["key"] for c in out["capabilities"]}
    assert keys == {k for k, _ in readiness.CAPABILITIES}
    for capability in out["capabilities"]:
        assert capability["what"], capability
        assert capability["evidence"], capability


def test_readiness_is_checked_rather_than_declared():
    """The caller check reads the source tree; the reader check runs the reader."""
    source = (ROOT / "src/brambleloop/teardown/readiness.py").read_text()
    assert "ast.walk" in source
    assert "reader.self_test()" in source
    # Parsed rather than grepped: the first version searched for `library.retrieve(` and
    # found three hits, all of them docstrings explaining what `retrieve` is for.
    callers = readiness.retrieve_callers()
    assert any("reader.py" in c for c in callers), callers


def test_the_two_empty_capabilities_are_reported_empty_rather_than_ticked():
    """Built, exercised, and with nothing in them, because nothing has been bought."""
    out = readiness.check(_db())
    by_key = {c["key"]: c for c in out["capabilities"]}
    assert by_key["cross_set_comparison"]["ready"] is False
    assert by_key["derived_standards"]["ready"] is False
    # And they do not block the purchase, because the purchase is what fills them.
    assert "cross_set_comparison" not in out["blocking"]
    assert "a comparison across a set of nothing is not a comparison" in \
        out["empty_rather_than_absent"]


def test_the_halves_that_do_work_are_not_talked_down():
    """Listing imagery and promises genuinely work, and an honest report says so."""
    out = readiness.check(_db())
    by_key = {c["key"]: c for c in out["capabilities"]}
    assert by_key["listing_images"]["ready"] is True
    assert by_key["listing_promises"]["ready"] is True
    assert by_key["provenance"]["ready"] is True


def test_the_owner_is_not_asked_to_buy_while_the_laboratory_cannot_read_a_page():
    """The owner's protocol, enforced in the queue rather than remembered by whoever asks.

    *Do not ask me to purchase the benchmark set until this complete intake/analysis path is
    verified ready.* An instruction held only in a conversation is one the next context does
    not have, so the launch assessment withholds the purchase request itself while the lab
    is unready -- and marks the requirement ours to finish rather than the owner's to fund.
    """
    from brambleloop.launch import readiness as launch

    db = _db()

    def purchase_request(assessment):
        return [r for r in assessment.owner_requests() if r.key == "benchmark_challenge"]

    original = reader.available
    reader.available = lambda: ""
    try:
        unready = launch.assess(db, phase="shadow")
    finally:
        reader.available = original
    assert purchase_request(unready) == []
    blocked = [r for r in unready.requirements if r.key == "benchmark_challenge"][0]
    assert blocked.blocked_by == launch.BLOCKED_BUILD
    assert blocked.evidence["teardown_laboratory"]["ready_for_purchase"] is False

    ready = launch.assess(db, phase="shadow")
    asked = purchase_request(ready)
    assert len(asked) == 1 and asked[0].max_cost_cad == 300.0
    now = [r for r in ready.requirements if r.key == "benchmark_challenge"][0]
    assert now.blocked_by == launch.BLOCKED_OWNER


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
