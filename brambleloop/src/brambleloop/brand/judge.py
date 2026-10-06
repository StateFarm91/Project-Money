"""Judge the identity directions: measured raster checks plus a written, declared rubric.

Two kinds of evidence, kept apart and labelled:

  measured  -- computed from the same geometry that ships, rasterised at the real sizes
               (40 px and 70 px Etsy icon, phone header): contrast, ink coverage, stroke
               survival, crispness, silhouette distinctness from each other and from generic
               craft clip-art, monochrome integrity, circle-crop safety, header legibility.
  judged    -- a rubric scored by the lane-A builder (premium feel, ownability, story fit,
               coherence, owner-taste alignment, complement to Laura), each score with its
               reason. This is opinion and is labelled so; the independent certifier (lane J)
               and the owner are the real judges. Internal judges never substitute for
               marketplace evidence (impressions, CTR, favourites, conversion).

A "blind" structural comparison against premium handmade / design-house archetypes is
included as descriptions only. No competitor asset was fetched, embedded or traced.
"""
from __future__ import annotations

import math
from functools import lru_cache

from . import bible
from . import directions as _D
from . import typeset as T
from .vector import Circle, Fill, Mark, Path, Stroke, circle_path, cubic_through, rasterize

SIZES = (40, 70)


def _lum(rgb):
    import numpy as np

    def ch(c):
        return np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    return 0.2126 * ch(rgb[..., 0]) + 0.7152 * ch(rgb[..., 1]) + 0.0722 * ch(rgb[..., 2])


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def contrast(a: str, b: str) -> float:
    return bible.contrast_ratio(_hex(a), _hex(b))


def ink_mask(arr, ground_hex: str, thresh: float = 0.18):
    """Pixels visibly different from the ground (Euclidean RGB distance)."""
    import numpy as np

    g = np.array(_hex(ground_hex), dtype=np.float32)
    return np.sqrt(((arr[..., :3] - g) ** 2).sum(-1)) > thresh


def _erode(mask, r: int):
    import numpy as np

    out = mask.copy()
    for _ in range(r):
        m = out
        sh = [np.roll(m, 1, 0), np.roll(m, -1, 0), np.roll(m, 1, 1), np.roll(m, -1, 1)]
        out = m & sh[0] & sh[1] & sh[2] & sh[3]
    return out


def _iou(a, b) -> float:
    inter = float((a & b).sum())
    union = float((a | b).sum())
    return inter / union if union else 0.0


def _centred(mask, n: int = 40):
    """Crop to the ink bbox and resample into an n x n box (aspect kept, centred)."""
    import numpy as np
    from PIL import Image

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((n, n), bool)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    s = n / max(h, w)
    im = Image.fromarray((crop * 255).astype("uint8")).resize(
        (max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    out = np.zeros((n, n), bool)
    a = np.asarray(im) > 127
    oy, ox = (n - a.shape[0]) // 2, (n - a.shape[1]) // 2
    out[oy:oy + a.shape[0], ox:ox + a.shape[1]] = a
    return out


# ---- generic craft clip-art references (what the brief says not to be) ---------------------


def generic_references() -> dict[str, Mark]:
    refs: dict[str, Mark] = {}
    m = Mark("ref-yarn-ball", 500, 500)
    m.add(Circle(250, 250, 170, "ink"))
    for k in (-0.5, 0.0, 0.5):
        m.add(Stroke(Path().M(110, 250 + k * 160).Q(250, 150 + k * 160, 390, 250 + k * 160), 12,
                     "g"))
    m.add(Stroke(cubic_through([(380, 330), (430, 400), (470, 420)]), 14, "ink"))
    refs["generic_yarn_ball"] = m
    m = Mark("ref-plain-B", 500, 500)
    size = 520
    m.add(Fill(T.set_text("gloock", "B", size, 250 - 632 * size / 2000, 250 + 750 * size / 2000),
               "ink"))
    refs["plain_serif_B"] = m
    m = Mark("ref-hook", 500, 500)
    m.add(Stroke(cubic_through([(120, 420), (330, 160), (370, 110), (395, 100), (400, 128),
                                (378, 140)]), 26, "ink"))
    refs["generic_hook"] = m
    m = Mark("ref-flower", 500, 500)
    for i in range(5):
        a = math.radians(i * 72 - 90)
        m.add(Circle(250 + 90 * math.cos(a), 220 + 90 * math.sin(a), 70, "ink"))
    m.add(Stroke(Path().M(250, 300).Q(240, 400, 260, 480), 16, "ink"))
    refs["generic_flower_sprig"] = m
    m = Mark("ref-badge", 500, 500)
    m.add(Stroke(circle_path(250, 250, 200), 22, "ink"))
    refs["generic_circle_badge"] = m
    return refs


def _ref_mask(mark: Mark, px: int):
    arr = rasterize(mark, {"ink": "#000000", "g": "#FFFFFF"}, px, ground="#FFFFFF")
    return ink_mask(arr, "#FFFFFF")


# ---- measured metrics ------------------------------------------------------------------------


def measure_direction(d: _D.Direction) -> dict:
    import numpy as np

    out: dict = {"id": d.id, "basis": "measured"}
    icon = d.icon()
    col, ground = d.colours("colour"), d.ground("colour")
    # contrast of every drawn role against the ground (WCAG non-text floor is 3:1)
    used = icon.roles()
    roles = {r: col[r] for r in used}
    out["role_contrast"] = {r: round(contrast(c, ground), 2) for r, c in sorted(roles.items())}
    out["primary_contrast"] = round(contrast(col["ink"], ground), 2)
    rasters = {px: rasterize(icon, col, px, ground=ground) for px in SIZES}
    out["non_blank"] = {px: bool(ink_mask(rasters[px], ground).any()) for px in SIZES}
    cov = {px: float(ink_mask(rasters[px], ground).mean()) for px in SIZES}
    out["ink_coverage"] = {px: round(v, 3) for px, v in cov.items()}
    # crispness at 40: share of ink pixels within reach of a real palette colour (not mush)
    pal = np.array([_hex(c) for c in set(roles.values()) | {ground}], dtype=np.float32)
    a40 = rasters[40][..., :3]
    dist = np.sqrt(((a40[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1)).min(-1)
    m40 = ink_mask(rasters[40], ground)
    out["crispness_40"] = round(float((dist[m40] < 0.16).mean()) if m40.any() else 0.0, 3)
    # stroke survival at 40 px: render at 160 (4x), erode by 2 px (= 0.5 px each side at 40):
    # anything thinner than ~1 px at 40 vanishes.
    big = ink_mask(rasterize(icon, col, 160, ground=ground), ground)
    er = _erode(big, 2)
    out["stroke_survival_40"] = round(float(er.sum() / big.sum()) if big.sum() else 0.0, 3)
    # thinnest stroke element at 40 px
    widths = [e.width for e in icon.elements if isinstance(e, Stroke)]
    out["thinnest_stroke_px_40"] = round(min(widths) * 40 / icon.width, 2) if widths else None
    # circle-crop safety: ink outside the inscribed circle (r = 0.49 side)
    yy, xx = np.mgrid[0:160, 0:160]
    outside = ((xx - 79.5) ** 2 + (yy - 79.5) ** 2) > (0.49 * 160) ** 2
    out["ink_outside_circle"] = round(float((big & outside).sum() / max(1, big.sum())), 4)
    # monochrome integrity at 70 px: edges of the colour render still present in mono
    mono = rasterize(icon, d.colours("mono"), 70, ground=d.ground("mono"))
    lc, lm = _lum(rasters[70][..., :3]), _lum(mono[..., :3])
    gc = np.hypot(*np.gradient(lc))
    gm = np.hypot(*np.gradient(lm))
    out["mono_edge_correlation"] = round(float(np.corrcoef(gc.ravel(), gm.ravel())[0, 1]), 3)
    rev = rasterize(icon, d.colours("reversed"), 70, ground=d.ground("reversed"))
    out["reversed_non_blank"] = bool(ink_mask(rev, d.ground("reversed")).any())
    # phone header: horizontal lockup inside 280 x 40 px
    lk = d.lockup_horizontal()
    wm = d.wordmark()
    s = min(280 / lk.width, 40 / lk.height)
    met = T.font_metrics(d.typography["wordmark"]["font"])
    word_scale = s  # wordmark is placed at scale 1 inside the lockup
    case = d.typography["wordmark"].get("case", "")
    unit = met["cap_height"] if case in ("upper",) else met["x_height"]
    out["header_letter_px"] = round(unit * 100 / 1000 * word_scale, 1)
    out["header_lockup_px"] = [round(lk.width * s), round(lk.height * s)]
    out["wordmark_aspect"] = round(wm.width / wm.height, 2)
    out["_mask40"] = _centred(ink_mask(rasters[40], ground))
    return out


def _distinctness(metrics: dict[str, dict]) -> dict[str, dict]:
    refs = {k: _centred(_ref_mask(m, 40)) for k, m in generic_references().items()}
    out = {}
    for did, mt in metrics.items():
        mine = mt["_mask40"]
        vs_ref = {k: round(_iou(mine, r), 3) for k, r in refs.items()}
        vs_dir = {o: round(_iou(mine, m2["_mask40"]), 3) for o, m2 in metrics.items()
                  if o != did}
        worst = max(list(vs_ref.values()) + list(vs_dir.values()))
        out[did] = {"iou_vs_generic": vs_ref, "iou_vs_other_directions": vs_dir,
                    "distinctness": round(1 - worst, 3)}
    return out


# ---- the declared rubric (judged, not measured) ---------------------------------------------

RUBRIC_CRITERIA = {
    "premium": "Would it sit beside a premium design-house or heritage-mill identity "
               "without looking template-made?",
    "ownable": "Could only Brambleloop own it? Is it free of generic yarn-ball / hook / "
               "flower / chain-icon readings?",
    "story": "Does the mark tell the name (bramble + loop) and crochet without words?",
    "coherence": "Do icon, emblem, wordmark, palette and motif read as one system?",
    "owner_taste": "Alignment with the owner's 2026-10-06 concept images (strong signal, "
                   "not an automatic win).",
    "laura_fit": "Does it complement a warm, photographic Laura portrait rather than compete?",
}

RUBRIC: dict[str, dict[str, tuple[int, str]]] = {
    "D1-briar-monogram": {
        "premium": (5, "High-contrast serif monogram, spaced capitals, hairline descriptor and "
                       "a restrained sage/cream/rose palette: the structure of heritage and "
                       "stationery houses, executed without clip-art."),
        "ownable": (4, "A serif B alone is common; the B held in a yarn loop with a leaf pair, "
                       "and the figure-of-eight emblem, make it Brambleloop's. Risk: monogram "
                       "+ botanical is a popular Etsy aesthetic, so execution quality matters."),
        "story": (5, "Bramble (leaf, blossom, berry) + loop (yarn) + B, literally the name."),
        "coherence": (5, "One B, one strand, one sprig across icon, emblem and motif."),
        "owner_taste": (5, "Rebuilt directly from the owner's concept."),
        "laura_fit": (5, "Cream/sage/rose sits naturally with a warm, natural-light portrait "
                         "and cream crochet; the mark is calm enough to sit beside a face."),
    },
    "D2-chain-link": {
        "premium": (3, "Clean and modern, but reads as a tech brand more than a pattern house."),
        "ownable": (2, "Two interlocked ovals are the universal 'hyperlink' / chain icon; "
                       "the crochet meaning needs explaining -- the opposite of the owner's "
                       "brief to stop looking like a software project."),
        "story": (3, "Loop, yes; bramble, no."),
        "coherence": (4, "Simple and consistent."),
        "owner_taste": (1, "Nothing of the owner's concept."),
        "laura_fit": (3, "Neutral; cool charcoal fights a warm portrait slightly."),
    },
    "D3-drupelet": {
        "premium": (3, "Charming and warm; closer to a jam label than a design house."),
        "ownable": (3, "A berry of bobble stitches with a looped stem is clever up close, but "
                       "at 40 px it reads as a generic raspberry/grape icon."),
        "story": (4, "Bramble fruit + loop stem."),
        "coherence": (4, "Berry, drupelet motif and rounded serif agree."),
        "owner_taste": (3, "Shares the palette mood and the bramble, not the monogram."),
        "laura_fit": (4, "Warm wine/cream complements a portrait."),
    },
    "D4-tapestry-b": {
        "premium": (3, "Graphic and confident; risks reading as a knitting app or pixel art."),
        "ownable": (4, "A B worked in V stitches is specific to the craft and unusual."),
        "story": (3, "Crochet and B; no bramble, no loop."),
        "coherence": (4, "Stitch grid unifies icon and motif."),
        "owner_taste": (2, "Different mood (indigo/saffron, modern) from the owner's concept."),
        "laura_fit": (3, "Strong colour blocks compete with a portrait in a banner."),
    },
}

WEIGHTS = {"measured": 0.5, "judged": 0.5}


def _measured_score(mt: dict, dist: dict) -> tuple[float, dict]:
    """0..100 from the measured metrics; each component documented."""
    comp = {}
    comp["contrast"] = min(1.0, (mt["primary_contrast"] - 3.0) / 6.0) if mt[
        "primary_contrast"] >= 3 else 0.0
    cov = mt["ink_coverage"][40]
    comp["coverage"] = 1.0 if 0.14 <= cov <= 0.5 else max(0.0, 1 - abs(cov - 0.3) * 3)
    comp["crispness"] = mt["crispness_40"]
    comp["stroke_survival"] = min(1.0, mt["stroke_survival_40"] / 0.6)
    comp["distinctness"] = min(1.0, dist["distinctness"] / 0.6)
    comp["mono"] = max(0.0, mt["mono_edge_correlation"])
    comp["circle_safe"] = 1.0 if mt["ink_outside_circle"] < 0.01 else 0.5
    comp["header"] = min(1.0, mt["header_letter_px"] / 12.0)
    w = {"contrast": 1, "coverage": 1, "crispness": 1, "stroke_survival": 1.5,
         "distinctness": 2, "mono": 1, "circle_safe": 0.5, "header": 1}
    total = sum(comp[k] * w[k] for k in w) / sum(w.values()) * 100
    return round(total, 1), {k: round(v, 3) for k, v in comp.items()}


def verdict() -> dict:
    metrics = {did: measure_direction(d) for did, d in _D.DIRECTIONS.items()}
    dist = _distinctness(metrics)
    scores: dict[str, dict] = {}
    for did in _D.DIRECTIONS:
        ms, comp = _measured_score(metrics[did], dist[did])
        rub = RUBRIC[did]
        js = sum(v[0] for v in rub.values()) / (5 * len(rub)) * 100
        total = WEIGHTS["measured"] * ms + WEIGHTS["judged"] * js
        scores[did] = {"measured": ms, "measured_components": comp, "judged": round(js, 1),
                       "total": round(total, 1)}
    ranked = sorted(scores, key=lambda k: -scores[k]["total"])
    winner = ranked[0]
    clean = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
             for k, v in metrics.items()}
    why_not = {}
    for did in ranked[1:]:
        weakest = sorted(RUBRIC[did].items(), key=lambda kv: kv[1][0])[:2]
        why_not[did] = "; ".join(f"{k}: {v[1]}" for k, v in weakest)
    return {"winner": winner, "ranking": ranked, "scores": scores, "metrics": clean,
            "distinctness": dist, "rubric": {k: {c: list(v) for c, v in r.items()}
                                             for k, r in RUBRIC.items()},
            "rubric_criteria": RUBRIC_CRITERIA, "weights": WEIGHTS, "why_not": why_not,
            "basis": {"measured": "raster of the shipped geometry at 40/70/160 px",
                      "judged": "lane-A builder's rubric; opinion, labelled; lane J and the "
                                "owner are the independent judges"},
            "benchmarks": BENCHMARKS}


@lru_cache(maxsize=1)
def cached_verdict() -> dict:
    return verdict()


# ---- blind structural comparison (descriptions only; no assets fetched) ----------------------

BENCHMARKS = [
    {"archetype": "heritage wool mill / yarn house",
     "structure": "serif or slab capitals, generous tracking, small pictorial emblem (animal, "
                  "landscape), one dark ink on natural ground, descriptor line with a founding "
                  "date or place",
     "lesson": "restraint and one ink carry premium; the emblem is simple enough to stamp",
     "closest": "D1"},
    {"archetype": "Scandinavian design-led yarn/pattern brand",
     "structure": "lower-case geometric sans wordmark, no or abstract mark, photography does "
                  "the emotional work, lots of white space",
     "lesson": "type alone can be premium if the imagery is excellent",
     "closest": "D2"},
    {"archetype": "botanical stationery / letterpress studio",
     "structure": "monogram or initial with fine botanical line art, serif + italic pairing, "
                  "hairline rules, muted sage/blush palette",
     "lesson": "the illustration must have a simplified small-size cut or it fails as an icon",
     "closest": "D1"},
    {"archetype": "top Etsy pattern shops (visual merchandising)",
     "structure": "square icon that is a simple initial or object on a flat colour; banners "
                  "built from product photography; consistent thumbnail styling matters far "
                  "more than the logo for clicks",
     "lesson": "the icon must read at 40 px; the grid of listing photos is the real brand",
     "closest": "D1/D3"},
    {"archetype": "artisan food / preserves label",
     "structure": "fruit illustration, rounded serif, warm reds",
     "lesson": "a fruit mark drifts into 'jam brand' unless tied to the craft",
     "closest": "D3"},
]
