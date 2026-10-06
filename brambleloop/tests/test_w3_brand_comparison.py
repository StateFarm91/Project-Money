"""Wave 3 lane A2: identity comparison board for the owner's logo decision.

Checks that every candidate renders non-blank at the real sizes, that sizes match Etsy's verified
constraints, that the storefront/banner mocks are script-free with no external URL, that the
evidence set is small (<= 8 PNGs, each <= 300 KB) and that the full owner original is not in the
repository. The owner raster is optional (it lives outside the repo); its checks run only when the
byte-identical file is present.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_brand_comparison.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import comparison as C  # noqa: E402
from brambleloop.integrations import etsy_constraints as E  # noqa: E402

EV = ROOT / "research/final_build/w3/evidence"
FAILS = 0
EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']?(?!data:|#|\?)[a-z][a-z0-9+.-]*:|"""
                      r"""(?:src|href)\s*=\s*["']?//|url\(\s*["']?(?!data:|#)[^)"']*//""",
                      re.I)


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _nonblank(im, ground_hex: str, min_share: float = 0.02):
    import numpy as np

    from brambleloop.brand.judge import ink_mask

    a = np.asarray(im.convert("RGB")).astype("float32") / 255
    share = float(ink_mask(a, ground_hex).mean())
    assert share >= min_share, f"only {share:.3%} ink"
    return share


CS = C.candidates()


def test_finalists_follow_judge_ranking():
    v = json.loads((EV / "A_judge_verdict.json").read_text())
    top = v["ranking"][:3]
    assert top, "empty ranking"
    assert list(C.FINALIST_IDS) == top, (C.FINALIST_IDS, top)
    keys = [c.key for c in CS]
    assert keys[0] == "D1" and {"D2", "D3"} <= set(keys), keys


def test_icons_render_non_blank_at_real_sizes():
    lo = E.value("logo_min_px")
    assert CS, "no candidates"
    for c in CS:
        big = C.icon_image(c)
        assert big.size == (C.ICON_PX, C.ICON_PX) and big.size[0] >= lo[0] and big.size[1] >= lo[1]
        for px in (40, 70):
            im = C.small_icon(c, px)
            assert im.size == (px, px), (c.key, im.size)
            _nonblank(im, C.ground(c))


def test_monochrome_non_blank_both_grounds():
    for c in CS:
        _nonblank(C.mono_image(c, 160, C.BLACK, C.CREAM), C.CREAM)
        _nonblank(C.mono_image(c, 160, C.CREAM, C.FOREST), C.FOREST)
        assert C.mono_image(c, 40, C.BLACK, C.CREAM).size == (40, 40)


def test_measurements_complete_and_bounded():
    for c in CS:
        m = C.measure(c)
        for k in ("ink_coverage_40", "ink_at_3to1_share_40", "stroke_survival_40",
                  "mono_ink_kept", "ink_outside_circle"):
            assert 0.0 <= m[k] <= 1.0, (c.key, k, m[k])
        assert m["contrast_darkest_ink_40"] >= m["contrast_median_ink_40"] >= 1.0, m
        assert m["header_letter_px"] > 0
        assert ("DERIVED" in m["mono_basis"]) == (c.kind == "raster")


def _html_ok(html: str, label: str):
    assert "<script" not in html.lower(), "script tag"
    hits = EXTERNAL.findall(html)
    assert not hits, f"external refs: {hits[:3]}"
    assert label in html, "candidate label missing"
    assert "not publication-approved" in html, "Laura internal label missing"


def test_storefront_mock_no_external_urls():
    picks = [c for c in CS if c.key in ("D1", "OWNER")] or CS[:1]
    assert picks, "no candidates"
    for c in picks:
        for vp, w in (("mobile", 390), ("desktop", 1280)):
            h = C.storefront_html(c, vp)
            _html_ok(h, c.label)
            assert f'name="shoot" content="{w}x' in h
            icon_uri, _ = C._marks(c)
            assert icon_uri in h, "candidate icon not injected"


def test_banner_at_etsy_recommended_size():
    bw, bh = E.value("big_banner_recommended_px")
    assert (bw, bh) == (1600, 400)
    c = CS[0]
    h = C.banner_html(c)
    _html_ok(h, c.label)
    assert f'content="{bw}x{bh}"' in h and f"width:{bw}px" in h
    _, lock = C._marks(c)
    assert lock in h, "candidate lockup not injected"


def test_owner_raster_shown_as_supplied():
    c = next((x for x in CS if x.kind == "raster"), None)
    if c is None:
        print("OK owner raster absent here; owner checks skipped (file lives outside the repo)")
        return
    assert c.label == "Owner concept (raster, as supplied)"
    from PIL import Image

    src = Image.open(C.owner_path()).convert("RGB")
    assert src.size == C.OWNER_SIZE
    crop = src.crop(C.OWNER_CROP_MARK)
    sq = C._pad_square(crop, C.owner_ground()).resize((C.ICON_PX,) * 2, Image.LANCZOS)
    assert sq.tobytes() == C.icon_image(c).tobytes(), "icon is not crop+resample"


def test_evidence_small_and_bounded():
    pngs = sorted(EV.glob("A2_*.png"))
    if not pngs:
        print("OK no A2 evidence built here (run research/final_build/w3/A2_build_comparison.py)")
        return
    assert len(pngs) <= 8, [p.name for p in pngs]
    from PIL import Image, ImageStat

    for p in pngs:
        assert p.stat().st_size <= 300_000, (p.name, p.stat().st_size)
        im = Image.open(p).convert("L")
        assert ImageStat.Stat(im).stddev[0] > 5, f"{p.name} looks blank"
        assert im.width >= 600 and im.height >= 400, (p.name, im.size)
    rec = json.loads((EV / "A2_measurements.json").read_text())
    assert rec["recommendation"] is None and rec["decision"] == "OWNER_TO_DECIDE"


def test_full_owner_original_not_in_repo():
    big = [p for p in (ROOT / "research").rglob("*") if p.is_file()
           and p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.stat().st_size > 2_000_000]
    for p in big:  # vacuity-ok: no large image in research is the expected state
        assert hashlib.sha256(p.read_bytes()).hexdigest() != C.OWNER_SHA256, p
    for p in EV.glob("A2_*"):  # vacuity-ok: evidence may not be built in this checkout
        assert hashlib.sha256(p.read_bytes()).hexdigest() != C.OWNER_SHA256, p


def test_no_recommendation_in_summary_doc():
    md = (ROOT / "research/final_build/w3/A2_COMPARISON.md")
    if not md.exists():
        raise AssertionError("A2_COMPARISON.md missing")
    t = md.read_text().lower()
    for w in ("we recommend", "recommended choice", "the winner is", "should choose"):
        assert w not in t, w


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests found"
    for n, f in tests:
        check(n, f)
    print("FAILS", FAILS)
    sys.exit(1 if FAILS else 0)
