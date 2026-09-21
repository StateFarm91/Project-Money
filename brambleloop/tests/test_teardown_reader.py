"""Reading a purchased pattern without keeping a word of it.

The owner's MJs protocol asks for every page ingested and analysed, and in the same
paragraph forbids competitor expression reaching a Brambleloop product. These tests are
about the second half holding while the first half works, because a reader that returns text
would satisfy the protocol on paper and leave the rule to everyone's good intentions.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf  # noqa: E402
from brambleloop.teardown import reader  # noqa: E402
from brambleloop.teardown.library import LIBRARY_ENV, LibraryRefused  # noqa: E402


def _filed(slug: str = reader.SELF_TEST_SLUG):
    """A real pattern PDF, in a temporary library root. Returns (path, env, text)."""
    cir = for_slug(slug)
    doc = build_pattern_pdf(cir)
    tmp = tempfile.TemporaryDirectory(prefix="reader-test-")
    root = Path(tmp.name)
    (root / "purchase").mkdir()
    (root / "purchase" / "pattern.pdf").write_bytes(doc.pdf_bytes)
    return tmp, {LIBRARY_ENV: str(root)}


def test_it_reads_every_page_through_the_quarantine():
    tmp, env = _filed()
    try:
        out = reader.read("purchase/pattern.pdf", env=env)
    finally:
        tmp.cleanup()
    assert out["pages"] > 1
    assert out["pages_with_text"] == out["pages"]
    assert out["fully_readable"] is True
    assert out["instruction_lines"] > 0
    assert "gauge" in out["sections"] and "materials" in out["sections"]


def test_nothing_it_returns_is_a_substring_of_the_document():
    """The guarantee, tested the only way it can be: against the document's own words.

    Every string in the result is a vocabulary key defined in this repository, so a value
    that appears in the PDF and not in the module is expression that escaped.
    """
    tmp, env = _filed()
    try:
        out = reader.read("purchase/pattern.pdf", env=env)
    finally:
        tmp.cleanup()

    ours = set()
    ours.update(reader.SECTION_CUES)
    ours.update(reader.STITCH_VOCABULARY)
    ours.update(reader.PIECE_VOCABULARY)
    ours.update(reader.SIZE_LABELS)

    def walk(value, path="") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                assert isinstance(key, str)
                # Keys are field names and vocabulary keys; both are ours.
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for item in value:
                walk(item, path)
        elif isinstance(value, str):
            # The few descriptive strings are this module's own fields, not the document's.
            assert (value in ours or path in (".ref", ".file", ".read_by", ".role",
                                              ".holds_no_text")), (path, value)

    walk(out)


def test_a_section_it_did_not_find_in_a_document_it_could_not_read_is_withheld():
    """Not found is not absent -- the same rule the canonical-model floors needed.

    A scanned pattern yields no text. Answering the #152 presence schedule `false` from that
    would report eighteen absent sections in a document nobody read.
    """
    unreadable = reader.Inventory(pages=4, pages_with_text=1, pages_without_text=[2, 3, 4],
                                  sections={"materials": [1]})
    out = reader.architecture_answers(unreadable)
    assert out["answers"]["materials"]["score"] is True
    assert "gauge" not in out["answers"]
    assert "gauge" in out["withheld"]
    assert out["complete"] is False

    readable = reader.Inventory(pages=2, pages_with_text=2, sections={"materials": [1]})
    answered = reader.architecture_answers(readable)
    assert answered["answers"]["gauge"]["score"] is False
    assert answered["withheld"] == ["cover"]


def test_a_topic_mentioned_in_prose_is_not_a_section():
    """#152 asks whether each part exists as its own addressable section.

    A cue matched anywhere on a page answered yes for a licence paragraph buried in a
    support page and for the word "yarn" in a sentence about gauge. Presence comes from
    heading-shaped lines; a topic that appears only in prose is handed to the analyst with
    its pages named, rather than counted either way.
    """
    inv = reader.Inventory(pages=2, pages_with_text=2, sections={"materials": [1]},
                           mentions={"rights_terms": [2]})
    out = reader.architecture_answers(inv)
    assert out["answers"]["materials"]["score"] is True
    assert "rights_terms" not in out["answers"]
    assert out["mentioned_but_not_a_heading"]["rights_terms"] == [2]
    # And a topic that appears nowhere, in a document fully read, is absent.
    assert out["answers"]["blocking"]["score"] is False

    # The analysis dimensions ask a different question -- is the information in the
    # document -- so a mention counts there. Bad architecture and good materials
    # information is one fault, not two.
    assert reader.analysis(inv)["dimensions"]["materials"]["verdict"] == "observed"


def test_analysis_has_three_verdicts_and_unmeasurable_is_one_of_them():
    partial = reader.Inventory(pages=3, pages_with_text=1, pages_without_text=[2, 3],
                               sections={"materials": [1]})
    out = reader.analysis(partial)
    assert out["dimensions"]["materials"]["verdict"] == "observed"
    assert out["dimensions"]["assembly"]["verdict"] == "unmeasurable"
    assert "assembly" in out["unmeasurable"]

    whole = reader.Inventory(pages=1, pages_with_text=1, sections={"materials": [1]})
    assert reader.analysis(whole)["dimensions"]["assembly"]["verdict"] == "absent"


def test_a_promise_a_pdf_cannot_settle_is_unverifiable_rather_than_kept():
    inv = reader.Inventory(pages=2, pages_with_text=2, sections={"charts": [2]})
    out = reader.cross_reference({"has_chart": True, "has_video": True, "format": "PDF"}, inv)
    assert [c["claim"] for c in out["kept"]].count("has_chart") == 1
    assert [c["claim"] for c in out["unverifiable"]] == ["has_video"]
    assert out["missing"] == []

    promised_absent = reader.cross_reference({"has_chart": True}, reader.Inventory(
        pages=2, pages_with_text=2))
    assert [c["claim"] for c in promised_absent["missing"]] == ["has_chart"]


def test_a_seamless_construction_is_not_missing_the_pieces_it_never_needed():
    """This module said a one-piece basket was missing its base, so the rule is now a test."""
    seamless = reader.Inventory(pages=3, pages_with_text=3, round_lines=40, pieces=[])
    out = reader.construction_correspondence(seamless, advertised_form="basket")
    pieces = [f for f in out["findings"] if f["check"] == "expected_pieces"][0]
    assert pieces["result"] == "unverifiable"
    assert pieces["seamless"] is True

    # A flat document that names some pieces and not the ones the form needs is the case
    # worth flagging: a cardigan with a back and a front and no sleeve.
    flat = reader.Inventory(pages=6, pages_with_text=6, pieces=["back", "front"],
                            sections={"assembly": [6]})
    cardigan = reader.construction_correspondence(flat, advertised_form="cardigan")
    named = [f for f in cardigan["findings"] if f["check"] == "expected_pieces"][0]
    assert named["result"] == "discrepancy"
    assert named["not_found"] == ["sleeve"]


def test_an_unknown_form_is_unverifiable_rather_than_wrong():
    out = reader.construction_correspondence(
        reader.Inventory(pages=2, pages_with_text=2), advertised_form="wall hanging")
    assert out["verdict"] == "unverifiable"
    assert all(f["result"] != "discrepancy" for f in out["findings"])


def test_the_quarantine_still_refuses_generation_and_path_escape():
    tmp, env = _filed()
    try:
        for role in ("crochet_engineer", "listing", "support"):
            try:
                reader.read("purchase/pattern.pdf", role=role, env=env)
            except LibraryRefused:
                pass
            else:
                raise AssertionError(f"{role} read a purchased pattern")
        try:
            reader.read("../../etc/passwd", env=env)
        except LibraryRefused:
            pass
        else:
            raise AssertionError("the reader walked out of the quarantine")
    finally:
        tmp.cleanup()


def test_pieces_come_from_headings_rather_than_from_prose():
    """"Weave the end back through a few stitches" is not a piece called `back`."""
    prose = ("Finishing\n"
             "Fasten off and weave in all ends on the wrong side. Thread each end through "
             "at least 5 cm of stitches, then back through a few in the opposite "
             "direction.\n")
    assert reader._pieces_in(prose) == set()
    assert "sleeve" in reader._pieces_in("## Sleeve (make 2)\nRow 1: ch 20.\n")


def test_the_self_test_is_the_proof_and_it_runs_the_whole_path():
    out = reader.self_test()
    assert out["ran"] is True and out["ready"] is True
    assert out["analysis_dimensions_measured"] == out["analysis_dimensions"]
    assert out["cross_reference"]["unverifiable"] == ["has_video"]
    assert out["quarantine_still_refuses_generation"] is True
    assert out["quarantine_still_refuses_path_escape"] is True


def test_our_own_pattern_now_tells_the_maker_how_to_finish_it():
    """Found by pointing the benchmark reader at this company's own document.

    Every Brambleloop pattern ended at the last row: no fastening off, no ends, no blocking.
    The reader was built to audit somebody else's PDF and audited ours first.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import FINISHING_HEADING, write_pattern

    cir = for_slug(reader.SELF_TEST_SLUG)
    text = write_pattern(cir, compile_cir(cir), width_cm=90, height_cm=110)
    assert FINISHING_HEADING in text
    assert "weave in all ends" in text
    assert "90 x 110 cm" in text
    assert "ball band" in text


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
