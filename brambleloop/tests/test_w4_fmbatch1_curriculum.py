"""F-800: curriculum tracks follow the prerequisite ladder; techniques are placed by table;
unknown topics are named as unplaced; coverage is UNMEASURED for an empty track."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1cu_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/c.db"

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.learn import curriculum as C, graph_feeds  # noqa: E402
from brambleloop.learn.models import LearnGap  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()


def test_tracks_follow_the_ladder():
    assert C.tracks(db)["tracks"]["advanced"]["coverage"] == "UNMEASURED"
    graph_feeds.seed_prerequisites(db)
    with db.session() as s:
        s.add(LearnGap(topic="technique:magic_ring", state="QUEUED", owner="learn", evidence=[]))
        s.add(LearnGap(topic="yarn:worsted", state="QUEUED", owner="learn", evidence=[]))
    t = C.tracks(db)["tracks"]
    assert {"stitch:ch", "stitch:sc", "technique:magic_ring"} <= set(t["foundations"]["topics"])
    assert {"stitch:hdc", "stitch:inc"} <= set(t["building"]["topics"])
    assert {"stitch:dc", "stitch:tr", "stitch:dc_inc"} <= set(t["advanced"]["topics"])
    assert t["unplaced"]["topics"] == ["yarn:worsted"]
    assert t["foundations"]["coverage"] == 0.0


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
