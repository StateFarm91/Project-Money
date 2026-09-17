"""Row-level repeats: derived, written, and read back independently (section 2).

A pattern that prints all 120 rows of a five-repeat blanket is complete and unusable — four
pages of near-identical lines that a maker loses their place in. Real patterns say "repeat rows
25-48 three more times".

Two properties carry the whole feature and both are tested here.

The cycle is **derived from the compiled rows**, never declared. A declared repeat can disagree
with the rows it claims to describe, and both halves would be internally consistent, so no
arithmetic would catch it. There is no field to get wrong.

And the reverse compiler **expands the instruction itself**, from the customer text alone. If
the writer handed over the expansion the two would no longer be independent and the whole
validation chain would be checking its own work.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fixtures import good_mosaic_panel, good_sphere  # noqa: E402

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import Op, Row  # noqa: E402
from brambleloop.cir.reverse import (  # noqa: E402
    ParseProblem, compare, parse_pattern, parse_row_repeat,
)
from brambleloop.cir.rowcycle import (  # noqa: E402
    MIN_CYCLE_ROWS, RowCycle, describe, detect_cycle, expand,
)
from brambleloop.cir.writer import collapses_rows, write_pattern  # noqa: E402
from brambleloop.commerce.seo import build_description  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402


def _all_designs():
    yield "nordic-throw", nf.build("throw")
    yield "nordic-baby", nf.build("baby")
    yield "nordic-large", nf.build("large")
    for slug, design in CATALOGUE.items():
        yield slug, build(design)


# ---- detection -------------------------------------------------------------


def test_the_flagship_has_a_real_cycle():
    cir = nf.build("throw")
    cycle = detect_cycle(cir.components[0].rows)
    assert cycle is not None
    assert cycle.period == 24, cycle
    assert cycle.repeats == 3, cycle
    assert cycle.rows_saved == 72


def test_a_short_pattern_is_left_alone():
    """Collapsing two rows reads as a puzzle and saves nothing."""
    assert detect_cycle(good_mosaic_panel().components[0].rows) is None


def test_a_pattern_with_no_repetition_has_no_cycle():
    assert detect_cycle(good_sphere().components[0].rows) is None


def test_a_cycle_is_never_claimed_where_the_rows_differ():
    """The property that makes deriving safer than declaring."""
    cir = nf.build("throw")
    rows = cir.components[0].rows
    # Break one row inside the second pass: the block no longer tiles.
    victim = rows[50]
    victim.ops = [Op("sc", victim.declared_count)]
    cycle = detect_cycle(rows)
    if cycle is not None:
        for i in range(cycle.repeats):
            for j in range(cycle.period):
                a = rows[cycle.start - 1 + j]
                b = rows[cycle.end + i * cycle.period + j]
                assert [(*_op(o),) for o in a.ops] == [(*_op(o),) for o in b.ops], \
                    "a cycle was claimed across rows that differ"


def _op(node):
    return (getattr(node, "stitch", None), getattr(node, "count", None),
            getattr(node, "times", None))


def test_a_cycle_that_would_save_too_little_is_not_worth_it():
    rows = [Row(index=i, ops=[Op("sc", 10)], declared_count=10, turning_chain=1)
            for i in range(1, 9)]
    # Eight identical rows: the block could be one row, but a one-row "cycle" is noise.
    cycle = detect_cycle(rows)
    if cycle is not None:
        assert cycle.period >= MIN_CYCLE_ROWS
        assert cycle.rows_saved >= MIN_CYCLE_ROWS


# ---- expansion -------------------------------------------------------------


def test_expansion_restores_exactly_the_rows_that_were_collapsed():
    cir = nf.build("throw")
    rows = cir.components[0].rows
    cycle = detect_cycle(rows)
    kept = [r for r in rows if not cycle.covers(r.index)]
    restored = expand(kept, cycle)
    assert len(restored) == len(rows)
    for original, back in zip(rows, restored):
        assert original.index == back.index
        assert original.declared_count == back.declared_count
        assert original.color == back.color
        assert [_op(o) for o in original.ops] == [_op(o) for o in back.ops]


def test_expanding_a_cycle_whose_rows_are_missing_is_an_error():
    cir = nf.build("throw")
    rows = cir.components[0].rows[:10]
    try:
        expand(rows, RowCycle(start=25, end=48, repeats=3))
    except KeyError as e:
        assert "not all present" in str(e)
    else:
        raise AssertionError("expanded a cycle over rows that do not exist")


# ---- the customer sentence -------------------------------------------------


def test_the_instruction_gives_the_maker_a_checkpoint():
    """Naming the final row is not redundant; it is how someone who lost count recovers."""
    text = describe(RowCycle(start=25, end=48, repeats=3), 120)
    assert "rows 25-48" in text
    assert "3 more times" in text
    assert "ending with row 120" in text
    assert "4 repeats" in text


def test_a_single_further_pass_reads_as_once_more():
    assert "once more" in describe(RowCycle(start=9, end=16, repeats=1), 24)


def test_the_reader_understands_what_the_writer_wrote():
    assert parse_row_repeat(describe(RowCycle(25, 48, 3), 120)) == (25, 48, 3)
    assert parse_row_repeat(describe(RowCycle(9, 16, 1), 24)) == (9, 16, 1)
    assert parse_row_repeat("Row 4: Ch 1, turn. sc in next 40 sts. (40 sts)") is None


def test_a_nonsensical_repeat_instruction_is_refused():
    try:
        parse_row_repeat("Repeat rows 48-25 3 more times.")
    except ParseProblem as e:
        assert "nonsensical" in str(e)
    else:
        raise AssertionError("a backwards row range was accepted")


# ---- the round trip that matters -------------------------------------------


def test_every_design_collapses_and_reverse_compiles_clean():
    problems = []
    for slug, cir in _all_designs():
        result = compile_cir(cir)
        text = write_pattern(cir, result)
        printed = len([ln for ln in text.splitlines() if ln.startswith("Row ")])
        parsed = parse_pattern(text, "US")
        findings = compare(cir, text, "US")
        rows = len(cir.components[0].rows)
        if findings or len(parsed) != rows:
            problems.append((slug, len(findings), len(parsed), rows))
        # Where a cycle exists, the printed pattern must actually be shorter.
        if detect_cycle(cir.components[0].rows) is not None and printed >= rows:
            problems.append((slug, "collapsed nothing", printed, rows))
    assert not problems, problems


def test_the_flagship_prints_a_fraction_of_its_rows():
    cir = nf.build("large")
    text = write_pattern(cir, compile_cir(cir))
    printed = len([ln for ln in text.splitlines() if ln.startswith("Row ")])
    assert printed == 48, printed
    assert len(cir.components[0].rows) == 168
    assert len(parse_pattern(text, "US")) == 168


# ---- attacks ---------------------------------------------------------------


def test_a_tampered_repeat_count_is_caught():
    """The instruction is as load-bearing as a row, so it has to be checked like one."""
    cir = nf.build("throw")
    text = write_pattern(cir, compile_cir(cir))
    tampered = text.replace("3 more times", "4 more times")
    assert tampered != text
    findings = compare(cir, tampered, "US")
    assert findings, "an extra repeat pass passed unchallenged"
    assert any("REVERSE_ROW_COUNT" in f.code for f in findings), [str(f) for f in findings]


def test_a_tampered_repeat_range_is_caught():
    cir = nf.build("throw")
    text = write_pattern(cir, compile_cir(cir))
    tampered = text.replace("rows 25-48", "rows 25-44")
    assert tampered != text
    assert compare(cir, tampered, "US"), "a shifted repeat range passed unchallenged"


def test_a_deleted_repeat_instruction_is_caught():
    """Dropping the line silently turns a 120-row blanket into a 48-row one."""
    cir = nf.build("throw")
    text = write_pattern(cir, compile_cir(cir))
    stripped = "\n".join(ln for ln in text.splitlines()
                         if not ln.startswith("Repeat rows"))
    findings = compare(cir, stripped, "US")
    assert findings
    assert any(f.code == "REVERSE_ROW_COUNT" for f in findings), [str(f) for f in findings]


def test_a_repeat_pointing_at_rows_that_were_never_printed_is_refused():
    text = ("Test\nVersion 1.0.0\n\n"
            "Row 1: Ch 1, turn. sc in next 10 sts. (10 sts)\n"
            "Repeat rows 5-9 3 more times.\n")
    try:
        parse_pattern(text, "US")
    except ParseProblem as e:
        assert "only 0 of those rows appear" in str(e)
    else:
        raise AssertionError("a repeat over absent rows was expanded anyway")


def test_a_tampered_row_inside_the_repeated_block_is_caught_in_every_pass():
    """One wrong row in the block is wrong four times over, and must be reported."""
    cir = nf.build("throw")
    text = write_pattern(cir, compile_cir(cir))

    # Take the needle from the rendered text rather than a guessed literal: a hardcoded
    # instruction string silently stops matching the day the design changes, and a tamper
    # that does not apply is a test that proves nothing.
    lines = text.splitlines()
    victim = next(i for i, line in enumerate(lines) if re.match(r"^Row 30\b", line))
    run = re.search(r"in next (\d+) sts", lines[victim])
    assert run is not None, f"no stitch run to tamper with in {lines[victim]!r}"
    lines[victim] = (
        lines[victim][: run.start(1)]
        + str(int(run.group(1)) + 1)
        + lines[victim][run.end(1):]
    )
    tampered = "\n".join(lines)
    assert tampered != text, "the tamper did not apply; the test proves nothing"
    findings = compare(cir, tampered, "US")
    assert len(findings) >= 4, (
        f"a row inside a four-pass block was reported {len(findings)} times; the error "
        f"exists in every pass")


# ---- the copy has to match the document ------------------------------------


def _describe(cir):
    return build_description(
        cir.title, size_label="90 x 122 cm", yardage_lines=["cream: about 328-492 m"],
        tolerance_pct=20, difficulty="confident beginner", colors=["cream", "pine"],
        terminology="US", gauge_line=None, stitches=["sc", "dc"], pages=7,
        collapsed_repeats=collapses_rows(cir))


def test_the_listing_does_not_promise_a_printed_line_for_every_row():
    """The claim follows the document. It used to say "every single row" unconditionally."""
    cir = nf.build("throw")
    assert collapses_rows(cir) is True
    text = write_pattern(cir, compile_cir(cir))
    printed = {int(m.group(1)) for m in re.finditer(r"^Row (\d+):", text, re.M)}
    assert 120 not in printed, "the flagship still prints its last row"

    copy = _describe(cir)
    assert "every single row" not in copy, (
        "the description promises a stitch count on every single row while the PDF stops "
        "printing rows at 48")
    assert "written once" in copy


def test_a_pattern_that_prints_every_row_still_says_so():
    cir = good_mosaic_panel()
    assert collapses_rows(cir) is False
    assert "for every row" in _describe(cir)


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
