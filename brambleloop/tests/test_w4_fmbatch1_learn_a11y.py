"""F-824: Learn pages get the accessibility checks pattern charts get -- diagrams need an
accessible name and a text label per stage, lessons need alt text, explicit terminology and
short worded steps; an inaccessible diagram is not served."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.learn import accessibility as A, technique as T  # noqa: E402


def test_every_generated_diagram_passes():
    supported = T.supported()
    assert supported
    for code in supported:
        svg = T.render(code, "both")
        assert A.check_svg(svg, len(T.technique(code, "both").stages())) == [], code


def test_failures_are_named():
    good = T.render("sc", "both")
    no_title = good.replace(b"<title>", b"<desc>").replace(b"</title>", b"</desc>")
    assert any("accessible name" in p for p in A.check_svg(no_title, 3))
    no_text = __import__("re").sub(rb"<text\b[^>]*>.*?</text>", b"", good, flags=16)
    probs = A.check_svg(no_text, 3)
    assert any("drawing alone" in p for p in probs) and any("colours" in p for p in probs)


def test_lesson_checks_and_alt_text():
    spec = {"terminology": "US", "steps": [{"instruction": "Work one sc in each stitch."},
                                           {"instruction": ""},
                                           {"instruction": "word " * 41}]}
    probs = A.check_lesson(spec)
    assert probs == ["step 2 has no instruction in words", "step 3 runs 41 words (> 40)"]
    assert A.check_lesson({"steps": []}) == ["terminology (US/UK) is not stated"]
    assert "single crochet (sc)" in A.alt_text("single crochet", "sc", "both")


def test_lesson_page_carries_alt_text_and_the_report_and_serves_the_diagram():
    import hashlib
    import os
    import tempfile

    t = tempfile.mkdtemp(prefix="fmb1a11y_")
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{t}/a.db"
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(t, "a")
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.learn.service import DIMENSIONS, review_lesson, save_lesson

    main.db.create_all()
    svg = T.render("sc", "both")
    spec = {"author": "pattern-engineering", "learner_problem": "work a single crochet",
            "topics": ["stitch:sc"], "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                        "sha256": "a" * 64},
                       {"kind": "technique_diagram", "stitch": "sc", "loop": "both",
                        "rights": "brambleloop_original", "source": "learn.technique",
                        "sha256": hashlib.sha256(svg).hexdigest()}],
            "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2,
                       "term": "sc", "instruction": "Work one single crochet in each of "
                                                     "next two stitches."}]}
    rev = save_lesson(main.db, "sc-a11y", spec)
    review_lesson(main.db, "sc-a11y", rev, "independent-qa",
                  dict.fromkeys(DIMENSIONS, "PASS"), "fixture-review:test-only")
    c = TestClient(main.app)
    page = c.get("/learn/sc-a11y").json()
    assert page["accessibility"] == {"problems": []}
    assert "single crochet (sc)" in page["technique_diagrams"][0]["alt"]
    assert c.get(page["technique_diagrams"][0]["href"]).status_code == 200


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
