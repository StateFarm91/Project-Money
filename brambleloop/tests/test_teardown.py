"""The teardown laboratory: what may be learned from a purchased product, and what may not.

v1.4.3 requirements 148-170. The owner will buy about ten representative competitor patterns
so this company can study what a customer actually receives after paying. That is legitimate,
valuable and ordinary — and it puts a folder of somebody else's copyrighted instructions on the
same disk as a system that writes crochet patterns.

Every test here is about that boundary, or about the standard the laboratory is supposed to
produce. The boundary is tested before any file exists, because a boundary added afterwards is
one that was absent exactly when it mattered.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.teardown import library, scorecard  # noqa: E402


def _purchase(tmp: Path, name: str = "MJsOffTheHookDesigns-cropped-cardigan") -> Path:
    folder = tmp / name
    folder.mkdir(parents=True)
    (folder / "cardigan-pattern.pdf").write_bytes(b"pretend pdf" * 200)
    (folder / "cardigan-chart.pdf").write_bytes(b"pretend chart" * 80)
    (folder / "printable-bw.pdf").write_bytes(b"print edition" * 60)
    return folder


def _db(tmp: Path) -> Database:
    db = Database(f"sqlite:///{tmp}/teardown.sqlite")
    db.create_all()
    return db


# ---- the quarantine -------------------------------------------------------


def test_pattern_generation_cannot_read_the_benchmark_library():
    """The reason the laboratory is safe to have at all.

    A folder of competitor instructions beside a pattern-writing system is only acceptable if
    the pattern-writing system cannot open it. Not by policy, by PermissionError — and the
    refusal names the role's reason, so a future session that hits it reads an argument rather
    than a generic denial and looks for a way around.
    """
    tmp = Path(tempfile.mkdtemp())
    folder = _purchase(tmp)
    env = {library.LIBRARY_ENV: str(tmp)}
    inside = f"{folder.name}/cardigan-pattern.pdf"

    for role in ("crochet_engineer", "validator", "listing", "support", "growth",
                 "publishing"):
        try:
            library.retrieve(inside, role, env)
        except library.LibraryRefused as e:
            assert role in str(e)
            assert len(str(e)) > 60, "the refusal should say why, not just no"
        else:
            raise AssertionError(f"{role} read a purchased competitor pattern")

    # A role nobody listed is refused too: the default is closed, as everywhere else here.
    try:
        library.retrieve(inside, "some_new_agent", env)
    except library.LibraryRefused:
        pass
    else:
        raise AssertionError("an unlisted role read the library")

    # And the analyst, whose job this is, can.
    body = library.retrieve(inside, "teardown_analyst", env)
    assert body.startswith(b"pretend pdf")


def test_a_reader_cannot_walk_out_of_the_library():
    """`../../src` is the interesting case, not a typo.

    A quarantine whose reader accepts a relative path can be pointed anywhere, which makes it
    a file-serving endpoint with a misleading name.
    """
    tmp = Path(tempfile.mkdtemp())
    _purchase(tmp)
    env = {library.LIBRARY_ENV: str(tmp)}

    for escape in ("../../etc/passwd", "../outside.txt", "/etc/hostname"):
        try:
            library.retrieve(escape, "teardown_analyst", env)
        except library.LibraryRefused:
            pass
        else:
            raise AssertionError(f"the reader escaped the library via {escape!r}")


def test_an_observation_that_is_really_the_competitors_pattern_is_refused():
    """#167, and the same argument as the mechanism vocabulary in the pods.

    The rule has to be mechanical, because the moment somebody is mid-teardown with a
    genuinely useful paragraph in front of them is exactly when "store the abstraction, not
    the text" loses the argument.
    """
    for text in ("row 1: ch 3, dc in each stitch across",
                 "rnd 1 is worked in the back loop only, sc in each",
                 "their cuff section, transcribed",
                 "excerpt: the yoke is worked flat"):
        try:
            library.check_derived(text)
        except library.ContentRefused:
            pass
        else:
            raise AssertionError(f"stored competitor expression: {text!r}")

    # A real mechanism-level observation is exactly what should pass.
    library.check_derived(
        "stitch counts are printed at the end of every row in bold, so a maker can check "
        "without re-reading the instruction")


# ---- intake ---------------------------------------------------------------


def test_intake_infers_what_it_can_and_asks_only_for_what_it_cannot():
    """#170: do not make the owner describe forty files by hand.

    Ten purchases become a task nobody finishes if each one is a form. Filenames and the
    listing reference carry most of it, so the system works those out and the owner answers
    the short remainder.
    """
    tmp = Path(tempfile.mkdtemp())
    folder = _purchase(tmp)

    result = library.scan(folder, listing_ref="1825269747", paid_cad=8.5)
    assert result.seller == "MJsOffTheHookDesigns"
    assert result.inferred["file_count"] == 3
    assert result.inferred["has_chart"] is True
    assert result.inferred["has_print_edition"] is True
    assert result.inferred["has_video"] is False
    assert result.needs_owner == []

    # And what it genuinely cannot infer, it asks for rather than assuming.
    bare = library.scan(folder)
    assert any("listing reference" in n for n in bare.needs_owner)
    assert any("what was paid" in n for n in bare.needs_owner)


def test_intake_never_opens_a_file_it_only_hashes_it():
    """A manifest that had to parse a competitor's PDF would be reading what it exists to
    keep unread.

    Sizes and hashes come from the filesystem, so the manifest can prove a file has not
    changed without anybody having looked inside it.
    """
    tmp = Path(tempfile.mkdtemp())
    folder = _purchase(tmp)
    result = library.scan(folder)

    for f in result.files:
        assert len(f.sha256) == 64
        assert f.bytes > 0
        assert f.role in ("pattern_pdf", "chart", "print_edition", "video", "bonus",
                          "photo", "text", "unclassified")
    # Nothing in the manifest carries file contents.
    blob = str(result.to_dict())
    assert "pretend pdf" not in blob


def test_the_manifest_is_generated_and_says_what_the_files_are_not_for():
    """#170's deliverable, and the sentence that has to be on it.

    The manifest is the artefact somebody reads a year from now when they find the folder and
    wonder what it is. If it does not say these files may never be published, quoted or fed to
    generation, it has failed at its only durable job.
    """
    tmp = Path(tempfile.mkdtemp())
    folder = _purchase(tmp)
    db = _db(tmp)

    empty = library.manifest_markdown(db)
    assert "No benchmark products have been purchased yet" in empty

    result = library.scan(folder, listing_ref="1825269747", paid_cad=8.5)
    library.register(db, result, category="garments", pod="garments",
                     listing_ref="1825269747", paid_cad=8.5,
                     why_selected="the named benchmark's strongest garment listing")

    md = library.manifest_markdown(db)
    assert "somebody else's copyrighted work" in md
    assert "never reachable by pattern generation" in md
    assert "cardigan-chart.pdf" in md
    assert "MJsOffTheHookDesigns" in md

    # Registering the same purchase twice updates it rather than duplicating it.
    library.register(db, result, category="garments")
    assert md.count("## MJsOffTheHookDesigns-cropped-cardigan") == 1


# ---- the standard ---------------------------------------------------------


def test_a_finding_with_no_action_is_refused_because_that_is_a_review():
    """#164. The laboratory's output is a standard this company must meet, not a critique."""
    ok = scorecard.finding(
        "bench-1", "instruction_clarity", 4,
        "stitch counts are bolded at the end of every row so a maker can self-check",
        "put the running stitch count at the end of every generated row, not only at the "
        "end of a section")
    assert ok.score == 4

    try:
        scorecard.finding("bench-1", "chart_quality", 5,
                          "the chart is beautifully laid out and easy to follow", "")
    except scorecard.ScoreRefused as e:
        assert "review" in str(e)
    else:
        raise AssertionError("a finding with no improvement was accepted")

    for bad in (("not_a_dimension", 3), ("chart_quality", 9)):
        try:
            scorecard.finding("bench-1", bad[0], bad[1], "a" * 30, "b" * 30)
        except scorecard.ScoreRefused:
            pass
        else:
            raise AssertionError(f"accepted {bad}")

    # And a finding that smuggles the competitor's instructions in is refused there too.
    try:
        scorecard.finding("bench-1", "instruction_clarity", 4,
                          "row 1: ch 3, dc in each stitch across, turn",
                          "adopt this row structure in our own patterns")
    except library.ContentRefused:
        pass
    else:
        raise AssertionError("competitor instructions passed through a finding")


def test_the_composite_refuses_to_be_one_sellers_product_with_extra_steps():
    """#162, and the check that makes it mean something.

    Taking every target from the strongest single benchmark is the path of least resistance
    and it produces imitation with a scorecard attached. It also caps the company at that
    shop, permanently.
    """
    tmp = Path(tempfile.mkdtemp())
    db = _db(tmp)

    for dimension in ("instruction_clarity", "chart_quality", "beginner_support"):
        scorecard.record(db, scorecard.finding(
            "bench-1", dimension, 5, f"benchmark one does {dimension} unusually well",
            f"raise our {dimension} target to match what was observed"))

    one_source = scorecard.composite_standard(db)
    assert one_source["single_source"] is True
    assert "imitation of that product" in one_source["note"]
    assert one_source["usable_as_a_standard"] is False

    scorecard.record(db, scorecard.finding(
        "bench-2", "chart_quality", 5,
        "charts carry a per-symbol legend on every page rather than once at the front",
        "repeat the legend on every chart page in our generated documents"))
    two_sources = scorecard.composite_standard(db)
    assert two_sources["single_source"] is False
    assert two_sources["dimensions"]["instruction_clarity"]["from_benchmark"] == "bench-1"
    # Both reached the same bar on chart quality by different mechanisms, so the standard
    # keeps both rather than resolving the tie by whoever was torn down first -- which is the
    # single-source failure arriving by accident instead of by choice.
    tied = two_sources["dimensions"]["chart_quality"]["contributors"]
    assert sorted(c["benchmark"] for c in tied) == ["bench-1", "bench-2"]
    # Still not usable as a standard: nine dimensions have no evidence at all.
    assert two_sources["usable_as_a_standard"] is False
    assert len(two_sources["dimensions_without_evidence"]) == len(scorecard.DIMENSIONS) - 3


def test_parity_with_the_composite_is_refused_as_a_position():
    """#163. A composite of other people's strengths is a floor.

    And the advantages are a closed list anchored in things this company already built,
    because free text accepts "better quality", which is not an advantage but a hope.
    """
    claimed = scorecard.check_unique_value(
        "garments", ["deterministic_validation", "colour_independent_charts"])
    assert len(claimed["advantages"]) == 2
    assert "reverse-compiled" in claimed["advantages"]["deterministic_validation"]

    try:
        scorecard.check_unique_value("blankets", [])
    except scorecard.ParityRefused as e:
        assert "floor, not a position" in str(e)
    else:
        raise AssertionError("a product class claimed nothing and passed")

    try:
        scorecard.check_unique_value("hats", ["better_quality", "nicer_photos"])
    except scorecard.ParityRefused as e:
        assert "evidence" in str(e)
    else:
        raise AssertionError("an aspiration was accepted as an advantage")


def test_the_promise_audit_judges_only_what_filenames_can_settle():
    """#151, and the limit that keeps it honest.

    Whether the sizing section is deep enough needs somebody to read the document. Claiming to
    have checked it from a file listing is the same error as grading a listing from its
    thumbnail — which this company has already made once, with the blank hero.
    """
    inferred = {"has_chart": True, "has_video": False, "has_print_edition": True,
                "file_count": 3}
    audit = scorecard.promise_audit(
        {"chart_included": True, "video_included": True, "print_edition": True,
         "file_count": 4, "sizing_depth": True}, inferred)

    assert "chart_included" in audit["kept"]
    broken = {b["promise"] for b in audit["broken"]}
    assert broken == {"video_included", "file_count"}
    assert audit["unverifiable_from_filenames"] == ["sizing_depth"]
    assert "file_count" not in audit["kept"]
    assert 0 < audit["alignment"] < 1


def test_the_delight_question_is_answered_from_drivers_not_from_the_mean():
    """#169. A product can be average everywhere and delightful nowhere.

    Averaging twelve dimensions hides the one a buyer notices in the first thirty seconds,
    which is the only one the question is about.
    """
    weak = scorecard.delight_question({
        "instruction_clarity": 5, "chart_quality": 5, "beginner_support": 2,
        "premium_presentation": 5, "delivery_packaging": 5, "support_experience": 5,
        "product_creativity": 5})
    assert weak["better_than_expected"] is False
    assert weak["weakest"] == "beginner_support"
    assert "notice first" in weak["note"]

    strong = scorecard.delight_question({
        "instruction_clarity": 4, "chart_quality": 5, "beginner_support": 4,
        "premium_presentation": 4, "delivery_packaging": 4, "support_experience": 5})
    assert strong["better_than_expected"] is True

    # Unscored is unanswerable, not neutral.
    assert scorecard.delight_question({"product_creativity": 5})["answerable"] is False


def test_the_improvement_queue_leads_with_what_the_competitor_does_best():
    """The strongest thing a competitor does is the most useful mechanism to learn from."""
    tmp = Path(tempfile.mkdtemp())
    db = _db(tmp)

    scorecard.record(db, scorecard.finding(
        "bench-1", "delivery_packaging", 2,
        "seven files with unexplained names arrive in one flat download",
        "name our bundle files by what they are and list them in the confirmation"))
    scorecard.record(db, scorecard.finding(
        "bench-2", "beginner_support", 5,
        "every new technique links to a short demonstration at the point it is first needed",
        "link technique help inline in our patterns rather than in an appendix"))

    queue = scorecard.improvement_queue(db)
    assert [q["score"] for q in queue] == [5.0, 2.0]
    assert queue[0]["dimension"] == "beginner_support"


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
