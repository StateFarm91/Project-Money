"""W4-B2ASSETS: F-527 Brand Asset Health -- the live icon and banner against the canon.

The live shop's icon and banner (as getShop returns them) are compared with the owner's
canonical files (D-FB-17). The check finds four things:
- missing: no URL;
- low resolution: an icon under Etsy's recommended 500 x 500 px. The banner is UNKNOWN,
  because the API gives only a 760 x 100 rendition;
- stale: the brand's colours, but not the current artwork;
- off-brand: neither.

One incident per problem routes the upload to Brand/Visual, and it closes when a fresh
reading is clean. The image fetch is a stub, so no network is touched.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_b2assets.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import asset_health as AH  # noqa: E402
from brambleloop.brand import canonical_assets as ca  # noqa: E402

_TMP = tempfile.mkdtemp()


def ok(m):
    print(f"  ok  {m}")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/d{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _png(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _live():
    from PIL import Image

    logo = ca.image(ca.HERO_LOGO)
    icon = ca._pad_square(logo.crop(ca.LOGO_CROP_MONOGRAM), ca.paper_colour()).resize((500, 500))
    banner = ca.image(ca.STOREFRONT_BANNER).resize((760, 100), Image.LANCZOS)
    return {"icon_ok": _png(icon), "icon_small": _png(icon.resize((170, 170))),
            "banner_ok": _png(banner),
            "off": _png(Image.new("RGB", (600, 600), (255, 0, 255))),
            "stale": _png(Image.new("RGB", (600, 600), (36, 74, 58)))}


def test_the_canonical_assets_read_on_brand_and_the_banner_resolution_stays_unknown():
    files = _live()
    shop = {"icon_url_fullxfull": "https://i.etsystatic.com/icon", "image_url_760x100":
            "https://i.etsystatic.com/banner"}
    got = AH.assess(shop, fetch=lambda u: files["icon_ok" if u.endswith("icon") else "banner_ok"])
    assert got["surfaces"]["icon"]["state"] == AH.ON_BRAND, got["surfaces"]["icon"]
    assert got["surfaces"]["banner"]["state"] == AH.ON_BRAND, got["surfaces"]["banner"]
    assert got["surfaces"]["banner"]["low_resolution"] is None
    assert "UNKNOWN" in got["surfaces"]["banner"]["resolution_basis"]
    assert got["healthy"] is True and got["problems"] == []
    ok("the canonical icon and banner read on-brand; banner resolution is UNKNOWN, not a pass")


def test_missing_low_resolution_stale_and_off_brand_are_each_named():
    files = _live()
    got = AH.assess({"icon_url_fullxfull": "x://icon"}, fetch=lambda u: files["icon_small"])
    kinds = {(p["surface"], p["problem"]) for p in got["problems"]}
    assert ("banner", "missing") in kinds and ("icon", "low_resolution") in kinds, kinds
    for name, want in (("off", AH.OFF_BRAND), ("stale", AH.STALE)):
        r = AH.assess({"icon_url_fullxfull": "x", "image_url_760x100": ""},
                      fetch=lambda u, n=name: files[n])
        assert r["surfaces"]["icon"]["state"] == want, (name, r["surfaces"]["icon"])
    bad = AH.assess({"icon_url_fullxfull": "x"}, fetch=lambda u: (_ for _ in ()).throw(OSError("x")))
    assert bad["surfaces"]["icon"]["state"] == AH.UNKNOWN and bad["healthy"] is False
    ok("missing, low-resolution, stale and off-brand are separate findings; unread is UNKNOWN")


def test_problems_route_as_incidents_and_close_on_a_clean_reading():
    from brambleloop.core.models import Incident

    db = _db()
    files = _live()
    first = AH.record(db, AH.assess({"icon_url_fullxfull": "x"}, fetch=lambda u: files["off"]))
    assert f"{AH.INCIDENT_PREFIX}icon:off_brand" in first["opened"]
    assert f"{AH.INCIDENT_PREFIX}banner:missing" in first["opened"]
    with db.session() as s:
        inc = s.query(Incident).filter_by(signature=f"{AH.INCIDENT_PREFIX}icon:off_brand").one()
        assert "Info & appearance" in inc.summary and inc.detail["department"] == "brand"
    shop = {"icon_url_fullxfull": "i", "image_url_760x100": "b"}
    again = AH.record(db, AH.assess(shop, fetch=lambda u: files["icon_ok" if u == "i"
                                                                 else "banner_ok"]))
    assert set(again["resolved"]) == set(first["opened"]), again
    ok("each problem opens one routed incident; a clean reading closes them")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
