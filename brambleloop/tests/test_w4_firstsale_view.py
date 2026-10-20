"""W4-FIRSTSALE: Etsy image-upload readiness (B4) and the first-sale readiness view.

* `integrations.etsy_image_readiness` builds the exact uploadListingImage requests with the
  client's own `_upload_image`, re-parses the multipart bytes with an independent parser and
  checks them against Etsy's documented constraints -- and refuses what breaks one.
* `launch.first_sale.build` lists every first-sale gate per product and shop-wide with its
  evidence and who acts; on a fresh shadow database nothing reads PASS that was not measured.
* `GET /api/cc/first-sale` is behind the owner-session gate, read-only, and the PWA renders it.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale_view.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_firstsale_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-FIRSTSALE harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from PIL import Image  # noqa: E402

from brambleloop.integrations import etsy_image_readiness as R  # noqa: E402

STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"


def _png(w=2000, h=2000, mode="RGB") -> bytes:
    b = io.BytesIO()
    Image.new(mode, (w, h), (200, 180, 160) if mode == "RGB" else (0, 0, 0, 0)).save(b, "PNG")
    return b.getvalue()


def test_the_exact_requests_match_etsys_documented_contract():
    imgs = [(f"p-frame-{i}.png", _png(), f"Disclosed render, not a photograph {i}")
            for i in range(1, 7)]
    out = R.check_set(imgs)
    assert out["state"] == R.PASS, out["failures"]
    assert out["etsy_called"] is False and out["only_a_real_upload_confirms"]
    for i, row in enumerate(out["images"], start=1):
        assert row["rank"] == i and row["operation"] == "uploadListingImage"
        assert row["method"] == "POST"
        assert row["path"] == "/shops/{shop_id}/listings/{listing_id}/images"
        assert row["content_type"] == "image/png" and row["width"] == 2000


def test_each_documented_rule_is_enforced():
    big_alt = [("a.png", _png(), "x" * 501)]
    out = R.check_set(big_alt)
    assert out["state"] == R.FAIL and "500" in " ".join(out["failures"])
    clear = R.check_set([("t.png", _png(mode="RGBA"), "alt")])
    assert clear["state"] == R.FAIL and "IMAGE_TRANSPARENT" in " ".join(clear["failures"])
    many = R.check_set([(f"m{i}.png", _png(700, 700), "alt") for i in range(21)])
    assert many["state"] == R.FAIL and "allows 20" in " ".join(many["failures"])
    pdf = R.check_set([("p.pdf", b"%PDF-1.7 not an image", "alt")])
    assert pdf["state"] == R.FAIL, "a PDF is never uploaded as a photograph"
    portrait = R.check_set([("p.png", _png(1000, 1500), "alt")])
    assert portrait["state"] == R.PASS and any("FIRST_IMAGE_PORTRAIT" in w
                                               for w in portrait["warnings"])
    assert R.check_set([])["state"] == R.FAIL


def test_a_part_that_does_not_carry_the_certified_bytes_fails():
    from brambleloop.integrations import http as H

    real = H.multipart_body

    def corrupt(part, fields=None):
        return real(H.FilePart(field=part.field, filename=part.filename,
                               data=part.data[:-1] + b"\x00", content_type=part.content_type),
                    fields)

    H.multipart_body = corrupt
    try:
        out = R.check_set([("a.png", _png(), "alt")])
    finally:
        H.multipart_body = real
    assert out["state"] == R.FAIL and "differ" in " ".join(out["failures"]), out


def _db():
    from brambleloop.app import main

    main.db.create_all()
    return main.db


def test_first_sale_view_on_a_fresh_shadow_database_claims_nothing_unmeasured():
    from brambleloop.launch import first_sale as FS
    from brambleloop.products import launch0 as l0

    v = FS.build(_db())
    assert [p["candidate"] for p in v["products"]] == list(l0.LAUNCH0_SLUGS)
    assert len(v["products"]) == 8 and v["publishes_anything"] is False
    assert v["first_sale_possible"] is False
    for p in v["products"]:
        assert p["first_sale_ready"] is False
        for r in p["releases"]:
            assert set(r["gates"]) == set(FS.FIRST_SALE_GATES)
            for name, g in r["gates"].items():
                assert g["state"] in (FS.PASS, FS.FAIL, FS.UNKNOWN), (name, g)
                if g["state"] != FS.PASS:
                    assert g["who_acts"] in ("company", "owner", "external"), (name, g)
            # nothing certified, nothing held, nothing granted, nothing read from Etsy
            for k in ("durable_delivery", "etsy_category", "publication_grant",
                      "etsy_upload_confirmed", "image_upload_payload", "physical_sample"):
                assert r["gates"][k]["state"] != FS.PASS, (k, r["gates"][k])
            assert r["gates"]["publication_grant"]["who_acts"] == "owner"
            assert r["gates"]["etsy_upload_confirmed"]["who_acts"] == "owner"
    assert v["shop"]["operating_phase"]["state"] == FS.FAIL      # shadow
    assert v["shop"]["etsy_taxonomy_read"]["state"] == FS.UNKNOWN
    md = FS.render_markdown(v)
    assert "| hexagon-coaster-set |" in md


def test_cc_route_is_owner_gated_read_only_and_rendered():
    from fastapi.testclient import TestClient

    from brambleloop.agents.registry import Registry
    from brambleloop.app import main
    from brambleloop.app.command_center import auth, first_sale
    from brambleloop.core import opsauth

    ops, pw = "p" * 40, "owner passphrase for the W4-FIRSTSALE harness"
    os.environ[opsauth.TOKEN_VAR] = ops
    os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(pw, iterations=100_000)
    _db()
    Registry(main.db).seed_defaults()
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.get("/api/cc/first-sale").status_code == 401
    assert c.get("/api/cc/first-sale",
                 headers={"Authorization": f"Bearer {ops}"}).status_code == 401
    assert c.post("/api/cc/auth/login", json={"passphrase": pw}).status_code == 200
    first_sale.reset()
    first_sale.WAIT_S = 900
    r = c.get("/api/cc/first-sale")
    first_sale.WAIT_S = 2.0
    assert r.status_code == 200 and r.headers.get("cache-control") == "no-store", r.text[:300]
    env = r.json()["sections"]["first_sale"]
    assert env["status"] in ("BLOCKED", "UNKNOWN"), env.get("status")
    assert len(env["items"]) == 8 and env["shop"], env.get("reason")
    for it in env["items"]:
        assert it["status"] != "OK"
        assert all(g["status"] != "OK" or g["state"] == "PASS" for g in it["gates"])
    assert c.post("/api/cc/first-sale", json={}).status_code in (403, 404, 405)
    js = (STATIC / "js" / "views" / "completion.js").read_text()
    api = (STATIC / "js" / "api.js").read_text()
    assert "firstSaleCard(fs)" in js and "api.firstSale()" in js
    assert 'firstSale: () => `${API_BASE}/first-sale`' in api
    card = js[js.index("export function firstSaleCard"):js.index("export async function render")]
    for bad in ("innerHTML", "insertAdjacentHTML", "api.action", "post(", "guardedAction"):
        assert bad not in card, bad


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc(limit=5)
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500], flush=True)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
