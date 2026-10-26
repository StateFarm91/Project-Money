"""F-448: owner-supplied sources and terminology become research evidence (operator-only
route), tiered and labelled source_claim; supplied terms steer the research search."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1oe_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/o.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import LearningObservation  # noqa: E402
from brambleloop.intel import owner_evidence as O, search_strategy as S  # noqa: E402

main.db.create_all()
TOKEN = "q" * 40


def _post(body, auth=True):
    h = {"Authorization": f"Bearer {TOKEN}"} if auth else {}
    return TestClient(main.app).post("/api/research/evidence", json=body, headers=h)


def test_route_is_operator_only_and_validates():
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        assert _post({"domain": "techniques", "url": "https://x.gov"}, auth=False).status_code == 401
        assert _post({"domain": "techniques"}).status_code == 422
        assert _post({"domain": "nope", "url": "https://x.gov/a",
                      "note": "a regulator page about labelling rules"}).status_code == 422
        r = _post({"domain": "marketplace_policy", "url": "https://help.etsy.com/hc/a/1",
                   "note": "Etsy says digital listings may include up to five files",
                   "decision_ref": "listing.bundle_policy"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["source_tier"] == "primary" and j["retrieval"] == "search_summary"
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    with main.db.session() as s:
        row = s.get(LearningObservation, j["recorded"])
        assert row.detail["kind"] == O.KIND and row.detail["claim_class"] == "source_claim"


def test_owner_terms_join_the_search_glossary():
    O.record(main.db, {"domain": "techniques",
                       "terms": {"Moss stitch": ["linen stitch", "woven stitch"]}})
    extra = O.owner_terms(main.db)
    assert extra["moss stitch"] == ("linen stitch", "woven stitch")
    steps = S.plan(["moss stitch"], [], extra)
    assert {"round": "terminology", "terms": ["linen stitch"],
            "why": "'moss stitch' is also called 'linen stitch'"} in steps
    for bad in ({"domain": "techniques", "terms": {"x": "notalist"}}, "nope"):
        try:
            O.record(main.db, bad)
        except O.OwnerEvidenceRefused:
            pass
        else:
            raise AssertionError(bad)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
