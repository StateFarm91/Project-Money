"""W4-IMAGES: the owner-only internal image review, and the set-hero finding.

* every candidate image is a deterministic disclosed render, verified on its bytes, never
  generated or photographed, and none is approved for customers by this page;
* a set's hero shows every piece (W4-MULTIPIECE); a partial set is INCOMPLETE in the review
  and withheld from the customer preview;
* `/cc/image-review` needs an owner session, is no-store/noindex, script-free and phone-sized,
  and shows the images with their status; the customer preview never shows a withheld frame.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_images.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_images_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-IMAGES harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.store_foundation import image_review as IR  # noqa: E402
from brambleloop.store_foundation import preview as P  # noqa: E402

OPS = "i" * 40
PASS = "owner passphrase for the images harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()

# Kept small for CPU: one product per form plus the set the finding is about.
# D-W4-OWNER-BASKET-IDENTITY: the launched basket is the small one (the medium is held).
BUILDS = ["hexagon_coasters", "snowflake_ornaments", "basket_small"]


def _rows():
    if "rows" not in _C:
        _C["rows"] = {r["build"]: r for r in IR.review(main.db, builds=BUILDS)["rows"]}
    return _C["rows"]


_C: dict = {}


def test_candidates_cover_the_preview_products_and_the_proposals():
    cands = IR.candidates()
    assert cands
    builds = {c["build"] for c in cands}
    assert {"basket_small", "cloudline_blanket",
            "hexagon_coasters", "snowflake_ornaments", "snowfall_throw"} <= builds
    # D-W4-OWNER-BASKET-IDENTITY: the held nursery family's sizes are not reviewed for a page.
    assert not {"basket_medium", "basket_large"} & builds
    # W4-IMGCAP1: the old `in_customer_preview == 5` claim became false once CAP-1 raised the
    # Launch-0 cap (the field counted the *owner* Store Preview grid, which now holds 8). What
    # is still true, and asserted: only the 5 core products may reach the customer page; the 3
    # CAP-1 products are in scope, not approved, and not customer-page eligible.
    from brambleloop.products import launch0 as L

    core = {c["slug"] for c in cands if c["group"] == "launch0"}
    assert core == {"hexagonal-bread-basket", "cloudline-baby-blanket", "hexagon-coaster-set",
                    "nordic-star-ornaments", "winter-village-graphghan"}
    eligible = {c["slug"] for c in cands if c["customer_page_eligible"]}
    assert eligible == core
    later = [c for c in cands if c["group"] in ("cap1", "proposed")]
    assert {c["slug"] for c in later} == set(L.PROPOSED_SLUGS)
    want = "cap1" if L.CATALOGUE_FLOOR_APPROVED else "proposed"
    for c in later:
        assert c["group"] == want and c["customer_page_eligible"] is False
        if want == "cap1":
            assert c["scope_label"] == "in Launch-0 scope (CAP-1); not approved"
    shown = sum(1 for c in cands if c["in_owner_store_preview"])
    assert shown == len(L.LAUNCH0_SLUGS)


def test_a_cap1_product_is_labelled_and_never_customer_eligible_without_every_gate():
    r = IR.assess("key_basket", db=main.db)
    assert r["approval"]["customer_approved"] is False
    assert r["customer_page_eligible"] is False
    assert any("never shown on the customer page unless every gate passes" in x
               for x in r["limitations"])
    html = IR._card(r)
    assert r["scope_label"] in html and "customer page: not eligible" in html


def test_every_image_is_a_verified_deterministic_render_and_none_is_customer_approved():
    rows = _rows()
    assert set(rows) == set(BUILDS)
    for b, r in rows.items():
        assert r["generated"] is False and r["photograph"] is False, b
        assert "deterministic disclosed render" in r["provenance"]
        assert r["verifier"]["status"] == "PASS", (b, r["verifier"])
        assert r["disclosure"]["in_image"] and r["disclosure"]["in_alt_text"], b
        assert r["approval"]["customer_approved"] is False, b
        assert r["approval"]["why_not"], b
        assert r["status"] != IR.APPROVED
        assert r["remediation"] and r["limitations"]
        assert r["png"] and r["thumb"] and len(r["sha256"]) == 64


def test_a_set_hero_shows_every_piece_and_verifies():
    """W4-MULTIPIECE changed this test because its claim became false: the ornament hero no
    longer shows 1 of 6 pieces (it was INCOMPLETE); it now draws all 6 and verifies."""
    rows = _rows()
    orn = rows["snowflake_ornaments"]
    assert orn["pieces_finding"] is None, orn["pieces_finding"]
    assert orn["status"] == IR.VERIFIED_NOT_APPROVED, orn["status"]
    assert "all 6 pieces" in orn["disclosure"]["alt_text"]
    assert any(c["check"] == "object_count" and c["status"] == "PASS"
               for c in orn["verifier"]["checks"])
    assert rows["hexagon_coasters"]["pieces_finding"] is None
    assert rows["hexagon_coasters"]["status"] == IR.VERIFIED_NOT_APPROVED
    assert rows["basket_small"]["status"] == IR.VERIFIED_NOT_APPROVED


def test_pieces_finding_reads_the_manifest_conservatively():
    class _C1:
        components = [type("c", (), {"make": 6})()]

    assert IR.pieces_finding({"view": "hero", "pieces": 6, "layout": {}}, _C1())
    assert IR.pieces_finding({"view": "hero", "pieces": 6, "layout": {"objects": 6}}, _C1()) is None
    assert IR.pieces_finding({"view": "scale", "pieces": 6, "layout": {}}, _C1()) is None
    assert IR.pieces_finding({"view": "hero", "pieces": "x", "layout": {}}, _C1())


def test_the_customer_preview_shows_the_full_set_and_withholds_a_partial_one():
    """W4-MULTIPIECE changed this test because its claim became false (the preview no longer
    carries a 1-of-6 finding). A partial set is withheld, never shown as VERIFIED."""
    f = P.hero_frame("snowflake_ornaments")
    assert f["status"] == "VERIFIED" and f["pieces_finding"] is None
    assert P.hero_frame("hexagon_coasters")["pieces_finding"] is None
    html = P._tile({"title": "x", "price_cad": 5.0, "variant_count": 1},
                   {"status": "WITHHELD", "png": None, "pieces_finding": "1 of 6"})
    assert "fewer pieces" in html and "<img" not in html


def test_the_review_page_is_owner_only_script_free_and_shows_the_images():
    assert security.owner_session_route(IR.REVIEW_PATH)
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = anon.get(IR.REVIEW_PATH)
    assert r.status_code == 401, (r.status_code, r.text[:200])
    html = IR.render_page(main.db, builds=BUILDS)
    assert "OWNER ONLY, INTERNAL REVIEW" in html
    assert "<script" not in html.lower()
    assert 'name="viewport"' in html and "width=device-width" in html
    assert html.count("data:image/png;base64,") == len(BUILDS)
    assert "customer-approved: 0" in html
    assert "Image material that is not a candidate" in html


def test_the_review_route_serves_an_owner_session_with_no_store_and_noindex():
    original = IR.candidates
    IR.candidates = lambda: [c for c in original() if c["build"] == "hexagon_coasters"]
    try:
        c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
        assert c.post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200
        r = c.get(IR.REVIEW_PATH)
    finally:
        IR.candidates = original
    assert r.status_code == 200, r.text[:300]
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]
    assert "content-security-policy" in r.headers
    assert r.text.count("data:image/png;base64,") == 1


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
