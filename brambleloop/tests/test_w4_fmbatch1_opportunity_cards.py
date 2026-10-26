"""F-673: an opportunity card joins radar, arbitrage, rights feasibility and the next
pre-production experiment; missing readings are UNMEASURED, and the route is operator-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1oc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/o.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused: opportunity cards make no call")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.radar import arbitrage, cards as C  # noqa: E402

main.db.create_all()


def test_cards_join_four_readings_and_unmeasured_stays_unmeasured():
    out = C.cards(main.db, limit=5)
    assert out["count"] == 5 and out["pool"] >= 5
    assert any(c["feasibility"]["feasible"] for c in out["cards"])
    for c in out["cards"]:
        assert set(c) >= {"radar", "arbitrage", "feasibility", "next_experiment"}
        assert isinstance(c["radar"]["score"], float)
        assert c["arbitrage"]["state"] == C.UNMEASURED and "score" not in c["arbitrage"]
        if c["feasibility"]["feasible"]:
            assert c["next_experiment"]["step"] == "concept_post_waiting"
            assert c["next_experiment"]["interest"] == C.UNMEASURED
    assert out["unmeasured_arbitrage"] == 5


def test_measured_arbitrage_and_observed_interest_change_the_card():
    first = C.cards(main.db, limit=1)["cards"][0]
    pod = first["arbitrage"]["pod"]
    real = arbitrage.steering
    arbitrage.steering = lambda db: {pod: {"score": 0.7, "confidence": 0.8, "measured": 3}}
    try:
        with main.db.session() as s:
            s.add(AuditLog(actor="ingest", action="preproduction.interest_observed",
                           artifact=first["slug"],
                           detail={"source": "pinterest_api", "observed": {"saves": 12}}))
        card = C.cards(main.db, limit=1)["cards"][0]
    finally:
        arbitrage.steering = real
    assert card["arbitrage"] == {"pod": pod, "state": "MEASURED", "score": 0.7,
                                 "confidence": 0.8, "measured": 3}
    assert card["feasibility"]["feasible"], card["feasibility"]
    assert card["next_experiment"]["step"] == "engineer"
    assert card["next_experiment"]["interest"]["source"] == "pinterest_api"


def test_protected_title_and_class_c_block_the_experiment():
    quoted = SimpleNamespace(slug="q", title='"Son of a nutcracker" (quote) christmas stocking',
                             risk_class="A")
    f = C._feasibility(quoted)
    assert f["lane"] == "original_concept" and not f["may_reach_customers"]
    assert "Son of a nutcracker" in f["protected"] and not f["feasible"]
    seed = SimpleNamespace(slug="x", title="granny square amigurumi", risk_class="C")
    f = C._feasibility(seed)
    assert not f["feasible"] and any("Class C" in b for b in f["blockers"])
    assert f["filed_as_cultural_signal"] is False
    nxt = C._next_experiment(main.db, "x", {"open": True}, f)
    assert nxt["step"] == "resolve_blockers"
    clean = C._feasibility(SimpleNamespace(slug="y", title="granny square blanket",
                                           risk_class="A"))
    assert clean["feasible"] and clean["may_reach_customers"]


def test_route_is_operator_only():
    client = TestClient(main.app)
    token = "o" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert client.get("/api/opportunities").status_code == 401
        r = client.get("/api/opportunities?limit=3",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["count"] == 3
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
