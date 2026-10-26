"""Review cbd4ff1 N-1 audit: every route this branch added has an explicit auth level, and the
public ones carry no owner, finance, customer or unpublished-product data.

`test_route_auth_default_deny` proves mutating routes are gated, but a GET left public on
purpose is never flagged by it. This walks each route by name: operator routes refuse without
the credential, and each public route's body is checked for the keys that must never appear.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ra_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/r.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
TOKEN = "r" * 40
os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core.models import CostEntry, Product  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
with main.db.session() as s:
    s.add(Product(slug="secret-unreleased", title="Unreleased Design"))
    s.add(CostEntry(agent="market_radar", kind="model", amount_cad=3.21, purpose="p",
                    provider="anthropic"))

OPERATOR = {
    "/api/finance/owner": "/api/finance/owner",
    "/api/orchestrator": "/api/orchestrator",
    "/api/opportunities": "/api/opportunities",
    "/api/etsy/scorecard": "/api/etsy/scorecard",
    "/api/product/{slug}/dossier": "/api/product/secret-unreleased/dossier",
    "/api/products/lifecycle": "/api/products/lifecycle",
    "/api/evidence": "/api/evidence?subject=mosaic",
    "/api/marketing/constellation/{slug}": "/api/marketing/constellation/secret-unreleased",
    "/api/company/departments/{key}": "/api/company/departments/executive",
    "/api/physical-truth": "/api/physical-truth",
    "/api/spend-report/governance": "/api/spend-report/governance",
}
# Public on purpose, each with what must never appear in it.
FORBIDDEN = ('"cash_on_hand_cad"', '"cash_unreconciled_lines"', '"expected_payout_cad"',
             '"owner_payable"', '"runway"', "secret-unreleased", "Unreleased Design",
             '"learning_value"', '"adoptions"', '"customer_id"', '"customer_ref"')
PUBLIC = ("/api/finance", "/api/useful-work", "/api/company/departments", "/api/spend-report",
          "/api/owned", "/m")


def test_operator_routes_refuse_without_the_credential():
    c = TestClient(main.app)
    for template, url in OPERATOR.items():
        assert security.requires_operator("GET", template), template
        assert c.get(url).status_code == 401, url
        assert c.get(url, headers={"Authorization": f"Bearer {TOKEN}"}).status_code in (200, 404), url


def test_public_routes_carry_no_owner_finance_customer_or_unpublished_product_data():
    c = TestClient(main.app)
    for url in PUBLIC:
        assert not security.requires_operator("GET", url), url
        r = c.get(url)
        assert r.status_code == 200, (url, r.status_code)
        for k in FORBIDDEN:
            assert k not in r.text, f"public {url} carries {k}"


def test_mobile_view_shows_owner_actions_only_as_a_count():
    html = TestClient(main.app).get("/m").text
    assert "m-act owner" not in html, "owner card texts belong behind the owner session"


def test_learn_curriculum_needs_the_learn_editor_credential():
    r = TestClient(main.app).get("/api/learn/curriculum")
    assert r.status_code in (401, 503), r.status_code


def test_mutating_research_evidence_is_gated():
    assert security.requires_operator("POST", "/api/research/evidence")
    assert TestClient(main.app).post("/api/research/evidence", json={}).status_code == 401


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
