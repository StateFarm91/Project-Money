"""F-814: a product's constellation carries content, approved lessons for its pattern topics
(widened by the graph), FAQ members and internal links; unlessoned needs are named; the route
is operator-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1cs_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/c.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import ContentPiece, PatternVersion, Product, SupportCase  # noqa: E402
from brambleloop.growth import constellation as C  # noqa: E402
from brambleloop.learn import graph_feeds  # noqa: E402
from brambleloop.learn.service import DIMENSIONS, review_lesson, save_lesson  # noqa: E402

main.db.create_all()
SPEC = {"author": "pattern-engineering", "learner_problem": "work a single crochet",
        "topics": ["stitch:sc"], "terminology": "US",
        "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
        "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                    "sha256": "a" * 64}],
        "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2, "term": "sc",
                   "instruction": "Work one single crochet in each of next two stitches."}]}


def _seed():
    with main.db.session() as s:
        p = Product(slug="hex", title="Hex")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={
            "construction": "flat_rows", "rows": [{"stitch": "hdc", "count": 2}]}))
        s.add(ContentPiece(product_slug="hex", channel="article", title="Hex article"))
        s.add(SupportCase(customer_ref="a", product_slug="hex", question="q", resolved=True,
                          specialist="sizing"))
    rev = save_lesson(main.db, "single-crochet", SPEC)
    review_lesson(main.db, "single-crochet", rev, "independent-qa",
                  dict.fromkeys(DIMENSIONS, "PASS"), "fixture-review:test-only")
    graph_feeds.run(main.db)


def test_members_with_reasons_and_named_gaps():
    _seed()
    c = C.constellation(main.db, "hex")
    # The pattern needs hdc; its prerequisite edge reaches sc, which has a lesson.
    assert [le["slug"] for le in c["lessons"]] == ["single-crochet"]
    assert c["faq"] == [{"node": "faq:sizing", "solved": 1}]
    assert {lk["to"] for lk in c["internal_links"]} == {c["lessons"][0]["href"], "faq:sizing"}
    assert "stitch:hdc" in c["filtered_out"] and c["content"][0]["channel"] == "article"


def test_route_operator_only():
    token = "k" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        cl = TestClient(main.app)
        assert cl.get("/api/marketing/constellation/hex").status_code == 401
        h = {"Authorization": f"Bearer {token}"}
        assert cl.get("/api/marketing/constellation/hex", headers=h).status_code == 200
        assert cl.get("/api/marketing/constellation/nope", headers=h).status_code == 404
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
