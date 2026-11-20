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
# INTEG7 (review R-1): these were public when FMBATCH1 audited them. W4-SECPATCH made every GET
# not on security.PUBLIC_GET_ROUTES operator-only, so each is now asserted refused to an
# anonymous caller and served to the operator. Stricter: none may be re-opened to pass.
NOW_OPERATOR = ("/api/finance", "/api/useful-work", "/api/company/departments",
                "/api/spend-report", "/api/owned", "/m")


def test_operator_routes_refuse_without_the_credential():
    c = TestClient(main.app)
    for template, url in OPERATOR.items():
        assert security.requires_operator("GET", template), template
        assert c.get(url).status_code == 401, url
        assert c.get(url, headers={"Authorization": f"Bearer {TOKEN}"}).status_code in (200, 404), url


def test_formerly_public_routes_are_operator_only_and_leak_nothing_anonymously():
    c = TestClient(main.app)
    for url in NOW_OPERATOR:
        assert security.requires_operator("GET", url), url
        assert url not in security.PUBLIC_GET_ROUTES, url
        r = c.get(url)
        assert r.status_code == 401, (url, r.status_code)
        for k in FORBIDDEN:
            assert k not in r.text, f"anonymous {url} carries {k}"
        assert c.get(url, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200, url


def test_mobile_view_shows_owner_actions_only_as_a_count():
    c = TestClient(main.app)
    anon = c.get("/m")                     # INTEG7 (R-1): operator-only since W4-SECPATCH
    assert anon.status_code == 401 and "m-act" not in anon.text
    html = c.get("/m", headers={"Authorization": f"Bearer {TOKEN}"}).text
    assert "m-act owner" not in html, "owner card texts belong behind the owner session"


def test_learn_curriculum_needs_the_learn_editor_credential():
    r = TestClient(main.app).get("/api/learn/curriculum")
    assert r.status_code in (401, 503), r.status_code


def test_mutating_research_evidence_is_gated():
    assert security.requires_operator("POST", "/api/research/evidence")
    assert TestClient(main.app).post("/api/research/evidence", json={}).status_code == 401


MARK_ACTION = "zq-owner-action-text-7731"
MARK_REASON = "zq-owner-reason-text-7732"
MARK_DELAY = "zq-owner-delay-text-7733"


def _public_get_paths():
    # INTEG7 (R-1): every route, routers included (security.iter_api_routes), not app.routes.
    out = set()
    for path, methods, _dep in security.iter_api_routes(main.app):
        if "GET" not in methods or "{" in path:
            continue
        if security.requires_operator("GET", path):
            continue
        out.add(path)
    return sorted(out)


def test_no_unauthenticated_page_carries_owner_inbox_text():
    """Coordinator decision 2026-10-26: owner decisions appear on public pages only as a
    count linking to /cc/. Every public GET (no path parameter) is swept for the texts an
    owner action carries."""
    from brambleloop.core.models import OwnerAction

    with main.db.session() as s:
        s.add(OwnerAction(requirement_key="zq-req", action=MARK_ACTION, reason=MARK_REASON,
                          consequence_of_delay=MARK_DELAY, minutes=5))
    c = TestClient(main.app)
    paths = _public_get_paths()
    assert "/" in paths and set(paths) <= security.PUBLIC_GET_ROUTES, \
        sorted(set(paths) - security.PUBLIC_GET_ROUTES)
    leaks = []
    for p in paths:
        try:
            r = c.get(p)
        except Exception:                                  # noqa: BLE001 - not a leak
            continue
        for mark in (MARK_ACTION, MARK_REASON, MARK_DELAY):
            if mark in r.text:
                leaks.append((p, mark))
    # An access request's own texts reach the inbox too (gate cards); they are owner inbox
    # text as much as an OwnerAction row is.
    from brambleloop.launch import access

    req = access.pending_requests(dict(os.environ))
    if req:
        for p in ("/", "/api/owner-actions", "/api/build", "/api/console"):
            body = c.get(p).text
            for r in req:
                for text in (r.action, r.purpose, r.consequence_of_declining):
                    if len(text) >= 24 and text[:60] in body:
                        leaks.append((p, text[:40]))
    assert not leaks, leaks
    # The operator, presenting the credential, still reads the inbox as stored.
    op = c.get("/api/owner-actions", headers={"Authorization": f"Bearer {TOKEN}"}).text
    assert MARK_ACTION in op
    home = c.get("/").text
    assert 'href="/cc/"' in home, "the public dashboard links the owner session"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
