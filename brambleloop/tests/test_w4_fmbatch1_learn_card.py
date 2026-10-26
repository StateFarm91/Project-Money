"""F-827: the Studio Learn card on the dashboard, computed from the database."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1learn_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/l.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.learn.models import LearnGap, Lesson  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()


def _card(html):
    i = html.index("Studio Learn")
    return re.sub(r"<[^>]+>", " ", html[i:i + 2500])


def test_empty_learn_is_said_not_zeroed():
    card = _card(TestClient(main.app).get("/").text)
    assert "none written yet" in card and "UNMEASURED" in card


def test_learn_card_reads_lessons_and_coverage():
    with main.db.session() as s:
        s.add(Lesson(slug="magic-ring", revision="r1", spec={}, state="DRAFT"))
        s.add(Lesson(slug="sc", revision="r1", spec={}, state="APPROVED"))
        s.add(LearnGap(topic="magic ring", state="COVERED"))
        s.add(LearnGap(topic="invisible decrease", state="QUEUED"))
    card = _card(TestClient(main.app).get("/").text)
    assert "APPROVED: 1" in card and "DRAFT: 1" in card
    assert re.search(r"awaiting review\s+1", card)
    assert "1 / 2" in card


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
