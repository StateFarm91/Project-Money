"""Wave 3 lane B: the v2 storefront on a phone -- top fold language, tap targets, no
horizontal scroll at 390 px, and the measured comparison against the rejected v1.

Static checks run on every machine. Browser measurements (Chromium via Playwright) are
committed evidence produced by scripts/w3_store_preview_evidence.py; when that file is
present these tests hold the numbers to the claims the comparison page makes.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w3_store_ux_mobile.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import preview, preview_v2  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
FAILS = 0
_PAGES: dict = {}
EVIDENCE = ROOT / preview_v2.EVIDENCE_REL


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def page(vp: str = "mobile", variant: str = "v2") -> str:
    if (vp, variant) not in _PAGES:
        _PAGES[(vp, variant)] = preview.render_preview(None, vp, now=NOW, variant=variant)
    return _PAGES[(vp, variant)]


def fold_text(html: str) -> str:
    part = html.split('data-fold="first-screen">', 1)[1].split('<ul class="trust"', 1)[0]
    # preview labels are not shop copy
    part = re.sub(r'<(div|span) class="pvs?"[^>]*>.*?</\1>', " ", part, flags=re.S)
    return preview_v2.visible_text(part)


def test_no_technical_jargon_above_the_fold():
    for vp in ("mobile", "desktop"):
        text = fold_text(page(vp))
        assert len(text) > 200, text
        hits = preview_v2.jargon_hits(text)
        assert not hits, (vp, hits)
        for word in ("compiler", "machine-readable", "row check", "checked row by row",
                     "verifier", "deterministic", "algorithm", "machine"):
            assert word not in text.lower(), word


def test_jargon_detector_catches_v1():
    hits = preview_v2.jargon_hits(preview_v2.visible_text(
        preview_v2.fold_v1(page("mobile", "standard"))))
    assert "compiler" in hits and "checked row by row" in hits and "machine" in hits


def test_fold_leads_with_product_not_process():
    html = page("mobile")
    fold = html.split('data-fold="first-screen">', 1)[1].split('<ul class="trust"', 1)[0]
    # banner, shop header, announcement, sections, then product cards -- in that order
    order = [fold.index(x) for x in ('class="bn', 'class="sh"', 'class="ann"',
                                     'class="secs"', 'class="card"')]
    assert order == sorted(order), order
    assert fold.count('class="card"') == 3


def _css(html: str) -> str:
    return html.split("<style>", 1)[1].split("</style>", 1)[0]


def _rule(css: str, selector: str) -> str:
    m = re.search(r"(?:^|[}\s])" + re.escape(selector) + r"\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_tap_targets_are_at_least_44px():
    css = _css(page("mobile"))
    for sel in (".pbar a", ".btn", ".secs li", "summary"):
        decl = _rule(css, sel)
        m = re.search(r"min-height:(\d+)px", decl)
        assert m and int(m.group(1)) >= 44, (sel, decl)
    # every tappable-looking element on the shop page is one of those
    shop = page("mobile").split('<div class="frame">', 1)[1].split('<section class="board"', 1)[0]
    assert "<a " not in shop and "<button" not in shop
    assert shop.count("<summary>") >= 8


def test_no_fixed_width_wider_than_the_phone():
    html = page("mobile")
    css = _css(html)
    for m in re.finditer(r"(?<![-\w(])(min-)?width:(\d+)px", css):
        assert int(m.group(2)) <= 390, m.group(0)
    # inline widths above 390 px only on board figures that shrink to the screen
    for m in re.finditer(r'<(\w+) class="([^"]*)" style="width:(\d+)px"', html):
        if int(m.group(3)) > 390:
            assert "bnwrap" in m.group(2), m.group(0)
    assert re.search(r"\.board \.bnwrap\{\{?max-width:100%", css)
    assert re.search(r"\.frame\{[^}]*max-width:390px", css)


def test_compare_page_shows_both_first_screens_and_metrics():
    html = page("desktop", "compare")
    assert 'class="screen s-v1 vp-mobile"' in html and 'class="screen s-v2 vp-mobile"' in html
    assert "height:844px" in html and "width:390px" in html
    for needle in ("Technical terms in the top region", "Words in the top region",
                   "Lowest text contrast", "v1 — rejected", "v2 — proposed"):
        assert needle in html, needle
    # the two stylesheets are scoped so neither restyles the other
    css = _css(html)
    assert ".s-v1 .banner" in css and ".s-v2 .bn" in css
    assert not re.search(r"(?:^|\})\s*\.banner\{", css)


def test_static_metrics_show_the_improvement():
    sm = preview_v2.static_metrics(page("mobile", "standard"), page("mobile"))
    assert sm["v1"]["top_jargon"] >= 5, sm
    assert sm["v2"]["top_jargon"] == 0, sm
    assert sm["v2"]["page_jargon"] < sm["v1"]["page_jargon"], sm


def test_measured_evidence_when_present():
    if not EVIDENCE.exists():
        print("OK note: no browser evidence committed; measured checks skipped")
        return
    m = json.loads(EVIDENCE.read_text())
    v1, v2 = m["v1_mobile"], m["v2_mobile"]
    assert m["as_of"] and "Chromium" in m["basis"]
    assert v2["horizontal_overflow_px"] == 0 and m["v2_desktop"]["horizontal_overflow_px"] == 0
    assert v2["tap_targets_under_44"] == 0 and v2["tap_targets"] > 0
    assert v1["tap_targets_under_44"] > 0          # the rejected baseline really had them
    assert v2["jargon_first_screen"] == 0 < v1["jargon_first_screen"]
    assert v2["image_share_pct"] > v1["image_share_pct"]
    assert v2["min_contrast_first_screen"] >= 4.5
    assert v2["headline_to_body_ratio"] > v1["headline_to_body_ratio"]
    assert v2["words_first_screen"] <= v1["words_first_screen"]


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
