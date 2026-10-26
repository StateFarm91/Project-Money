"""F-194: seasonal rows carry a cohort (legacy / launch_candidate / programme) and the
dashboard renders counts and at-risk rows grouped by it."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="fmb1_cohort_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'c.db')}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the test")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.products.builder import CATALOGUE  # noqa: E402
from brambleloop.products.launch0 import LAUNCH0_SLUGS  # noqa: E402
from brambleloop.seasonal import leadtime as LT  # noqa: E402


def test_cohort_classification():
    launch = LAUNCH0_SLUGS[0]
    legacy = next(s for s in CATALOGUE if s not in LAUNCH0_SLUGS)
    assert LT.cohort_for(launch) == LT.COHORT_LAUNCH
    assert LT.cohort_for(legacy) == LT.COHORT_LEGACY
    assert LT.cohort_for("zz-future-easter-basket") == LT.COHORT_PROGRAMME
    both = [s for s in CATALOGUE if s in LAUNCH0_SLUGS]
    for s in both:                                     # the launch list wins
        assert LT.cohort_for(s) == LT.COHORT_LAUNCH


def test_rows_are_tagged_and_counted_by_cohort():
    launch = LAUNCH0_SLUGS[0]
    legacy = next(s for s in CATALOGUE if s not in LAUNCH0_SLUGS)
    rows = [{"slug": launch, "status": LT.AT_RISK}, {"slug": legacy, "status": LT.AT_RISK},
            {"slug": legacy, "status": LT.MISSED}, {"slug": "zz-new", "status": LT.ON_TRACK}]
    counts = LT.tag_cohorts(rows)
    assert [r["cohort"] for r in rows] == ["launch_candidate", "legacy", "legacy", "programme"]
    assert counts["legacy"][LT.AT_RISK] == 1 and counts["legacy"][LT.MISSED] == 1
    assert counts["launch_candidate"][LT.AT_RISK] == 1
    assert counts["programme"][LT.ON_TRACK] == 1 and counts["programme"][LT.AT_RISK] == 0


def test_dashboard_renders_the_cohort():
    from fastapi.testclient import TestClient

    from brambleloop.agents.registry import Registry
    from brambleloop.app import main

    legacy = next(s for s in CATALOGUE if s not in LAUNCH0_SLUGS)
    fake = {"counts": {"on_track": 0, "past_preferred": 0, "at_risk": 1, "missed": 0},
            "counts_by_cohort": {"legacy": {"on_track": 0, "past_preferred": 0,
                                            "at_risk": 1, "missed": 0}},
            "at_risk_or_missed": [{"slug": legacy, "cohort": "legacy", "event": "Christmas",
                                   "status": "at_risk", "days_to_latest": 9,
                                   "latest_effective_launch": "2026-11-30"}]}
    real = LT.catalogue_plans
    LT.catalogue_plans = lambda db, **kw: fake
    try:
        main.db.create_all()
        Registry(main.db).seed_defaults()
        html = TestClient(main.app).get("/").text
    finally:
        LT.catalogue_plans = real
    assert "<th>Cohort</th>" in html or ">Cohort<" in html
    i = html.find(legacy)
    assert i >= 0 and "legacy" in html[i:i + 300]
    assert "at risk: 1" in html


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
