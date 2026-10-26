"""F-549: the Etsy scorecard carries every line the requirement names, each sourced; empty
shop reads UNMEASURED, a broken source reads UNKNOWN, and the route is operator-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1sc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/s.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused: the scorecard makes no Etsy call")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import CostEntry, Listing  # noqa: E402
from brambleloop.intel import etsy_scorecard as S  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
LINES = ("live_listings", "search_visibility", "traffic_and_conversion", "revenue_and_margin",
         "reviews", "service", "refunds", "ads", "policy", "oauth_api_health", "owner_actions")


def test_every_line_is_present_sourced_and_unmeasured_not_zero():
    c = S.scorecard(main.db)
    for k in LINES:
        assert k in c, k
        assert c[k].get("state") != "UNKNOWN", (k, c[k])
    assert c["traffic_and_conversion"]["conversion"] == "UNMEASURED"
    assert c["ads"]["ad_spend_cad"] == "UNMEASURED" and c["ads"]["roas"] == "UNMEASURED"
    assert c["oauth_api_health"]["state"] == "UNMEASURED"
    assert c["live_listings"]["live"] == 0 and c["live_listings"]["source"] == "listings"


def test_rows_change_the_card_and_a_broken_source_is_unknown():
    with main.db.session() as s:
        s.add(Listing(product_slug="hex", version="1", title="t", description="d", state="published"))
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=5.0, purpose="ads"))
    c = S.scorecard(main.db)
    assert c["live_listings"]["live"] == 1
    assert c["ads"]["ad_spend_cad"] == 5.0 and c["ads"]["roas"] == 0.0
    from brambleloop.gates import platform_policy

    real = platform_policy.policy_stamp
    platform_policy.policy_stamp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    try:
        c = S.scorecard(main.db)
    finally:
        platform_policy.policy_stamp = real
    assert c["policy"]["state"] == "UNKNOWN" and c["live_listings"]["live"] == 1


def test_route_is_operator_only():
    client = TestClient(main.app)
    token = "e" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert client.get("/api/etsy/scorecard").status_code == 401
        r = client.get("/api/etsy/scorecard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and set(LINES) <= set(r.json())
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
