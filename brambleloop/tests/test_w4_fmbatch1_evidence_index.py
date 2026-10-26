"""F-475: one evidence index over research corpora plus provenance, pod lessons, trend
provenance and company memory; every corpus searched is reported; operator-only route."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ei_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/e.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Lesson, PodLesson  # noqa: E402
from brambleloop.intel import evidence_index as X, research  # noqa: E402

main.db.create_all()
research.DOCUMENTS = {}
research.TESTS_DIR = Path(_T) / "no-tests"


def test_hits_come_from_every_kind_of_store_and_searched_corpora_are_named():
    with main.db.session() as s:
        s.add(Lesson(origin_cell="seo_search", subject="mosaic", statement="mosaic blanket "
                     "titles with the colour count converted better"))
        s.add(PodLesson(pod="home", subject="mosaic", statement="mosaic throws sell in autumn",
                        mechanism="seasonal"))
    memory.remember(main.db, "brief:mosaic", kind="note", subject="Mosaic blanket review")
    out = X.search(main.db, "mosaic")
    kinds = set(out["by_kind"])
    assert {"lesson", "pod_lessons", "company_memory"} <= kinds, out["by_kind"]
    names = {c["corpus"] for c in out["searched"]}
    assert {"artefact_provenance", "pod_lessons", "trend_provenance", "company_memory",
            "lessons"} <= names
    assert X.search(main.db, "ab")["why"].startswith("no searchable term")


def test_route_is_operator_only():
    token = "v" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        c = TestClient(main.app)
        assert c.get("/api/evidence?subject=mosaic").status_code == 401
        r = c.get("/api/evidence?subject=mosaic", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["count"] >= 3
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
