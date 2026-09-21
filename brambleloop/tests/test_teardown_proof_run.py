"""The laboratory driven end to end on documents this company made.

The owner's instruction before CA$292: run it against Brambleloop's own patterns as a proof
fixture and report what it actually read and compared. A readiness table whose rows each say
"the code imports" is what that refuses.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.teardown import proof_run  # noqa: E402

RUN = proof_run.run()


def test_it_drives_every_stage_on_real_documents():
    assert RUN["proven"] is True, RUN["failures"]
    assert len(RUN["documents"]) >= 4
    for stage, detail in RUN["stages"].items():
        assert detail["ran"] is True, (stage, detail)


def test_it_reports_what_it_read_rather_than_that_it_ran():
    """A run that says '9 of 9 steps ran' and does not say what it saw is a green tick with
    a stack trace hidden behind it."""
    for doc in RUN["documents"]:
        assert doc["pages"] > 1
        assert doc["pages_read"] == doc["pages"]
        assert doc["sections"], doc["ref"]
        assert doc["stitch_vocabulary"], doc["ref"]
        assert doc["instruction_lines"] > 0, doc["ref"]
        assert doc["analysis_observed"], doc["ref"]
        assert doc["construction_findings"], doc["ref"]


def test_a_dimension_absent_from_the_fixture_is_named_rather_than_counted_as_proven():
    """The first run reported two dimensions 'never observed' and was telling the truth
    about the fixture rather than about the laboratory.

    Our catalogue is flat and seamless pieces, so nothing in it is assembled. That is an
    answer, not a gap -- and it also means this fixture does not exercise that path, which
    the report says instead of implying otherwise.
    """
    analysis = RUN["stages"]["pattern_analysis"]
    assert analysis["undecided_in_a_readable_document"] == []
    assert "assembly" in analysis["absent_from_this_fixture"]
    assert "does not exercise those paths" in analysis["what_absent_means_here"]


def test_the_shaped_fixture_exercises_shaping():
    """Added because three flat pieces could not: a proof whose fixture cannot reach a path
    does not prove that path."""
    observed = {k for d in RUN["documents"] for k in d["analysis_observed"]}
    assert "shaping" in observed
    assert any(d["ref"].endswith("basket") for d in RUN["documents"])


def test_the_cross_set_step_needs_more_than_one_document():
    single = proof_run.run(slugs=("cloudline-baby-blanket",), fresh=True)
    assert single["stages"]["cross_set_comparison"]["ran"] is False
    assert single["proven"] is False


def test_it_says_what_it_does_not_prove():
    assert "what a competitor's document contains is what the purchase is for" in \
        RUN["what_it_is_not"]
    assert "proving the path on a file that does not exist" in RUN["what_this_is"]


def test_readiness_blocks_the_purchase_until_the_chain_has_been_driven():
    from brambleloop.teardown import readiness

    out = readiness.check(None)
    row = next(c for c in out["capabilities"] if c["key"] == "end_to_end_proof")
    assert row["ready"] is True
    assert "pages read" in row["evidence"]
    assert row["blocks_purchase"] is False
    assert "end_to_end_proof" in {k for k, _ in readiness.CAPABILITIES}


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
