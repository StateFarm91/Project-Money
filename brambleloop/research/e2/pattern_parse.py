"""E2 step 1: the purchased pattern, size S, parsed into Product Truth WITHOUT the photographs.

Every number below is cited to a page of the seller's PDF (text extracted with pypdf; the PDF
itself is NOT in this repository and the seller's prose is not reproduced -- only counts,
gauge, construction and measurements, which are facts about how a garment is made). The
existing `cir/benchmarks.py` encoding was NOT read as a source; it is diffed at the end as an
independent cross-check only.

Honesty notes, up front:
  * The seller photographs were displayed to me before this parse. Every structural value here
    is therefore cited to the PDF so a reader can verify none came from a picture.
  * Brambleloop's own `teardown.reader` inventoried this PDF but extracted 0 stitch counts and
    0 gauge statements: it audits document architecture, it does not parse construction. This
    parse is manual. That is a finding, recorded in the report.
  * The yarn colourway is named (p3) but its colour is not derivable from text. UNKNOWN.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row, Seam  # noqa: E402
from brambleloop.cir import compiler, twin as T                                          # noqa: E402

SIZE = "S"   # the sample size (p2: "Sample is a size small shown on a 5'3" model with a 32" bust")

# ---- page-cited facts, size S ----------------------------------------------------------
P = {
    "gauge_st_per_10cm": 14.5, "gauge_rows_per_10cm": 9.5, "hook_mm": 6.0,          # p3
    "stitch_pattern": "alternating BLO/FLO hdc ('crumpled waffle'), hdc, worked flat",  # p2, p4
    "yarn": {"line": "Lionbrand Color Theory", "weight": "worsted/aran (4)",
             "fibre": "100% acrylic", "colourway_named": "Stonewash", "colour_rgb": None},  # p3
    "listed_cm": {"bust_to_fit": 81, "back_width": 53, "armhole": 15, "sleeve_length": 39,
                  "length": 65},                                                         # p3
    "body": {"foundation_ch": 95, "sts": 94, "front_rows": 20, "back_rows": 50,
             "final_row": 1, "hem_rib_sts": 10, "sleeve_opening_ch": 29,
             "construction": "one piece, side to side: front, back (with two chained "
                             "sleeve openings), front; foundation runs top-to-bottom"},   # p2,p4-8
    "sleeve": {"foundation_ch": 63, "sts": 62, "rows": 30, "cuff_rib_sts": 9,
               "cuff_stitch": "slst BLO", "construction": "side to side, folded lengthways, seamed"},  # p8-9
    "neckband": {"foundation_ch": 8, "sts": 7, "rib": "BLO hdc 6 + hdc 1",
                 "runs": "entire neckline: up one front edge, across back neck, down the other"},  # p10-11
    "pocket": {"make": 2, "optional": True, "foundation_ch": 25, "sts": 24, "rows": 13,
               "top_edge": "slst edging on a row-end edge; rows therefore run vertically",
               "placement": "UNKNOWN: 'try on to double-check pocket placement, adjust'"},   # p11-12
    "closure": "none; open front, no buttons, no neck shaping",                          # p2,p8
    "assembly": ["fronts on back, whip stitch shoulder seams", "sleeves to armholes",
                 "neckband pinned and whip stitched", "pockets whip stitched to front panel only",
                 "steam block"],                                                         # p10-12
}

def cm_st(n): return n / P["gauge_st_per_10cm"] * 10.0
def cm_row(n): return n / P["gauge_rows_per_10cm"] * 10.0

# ---- the CIR, from those facts ----------------------------------------------------------
g = Gauge(stitches_per_10cm=P["gauge_st_per_10cm"], rows_per_10cm=P["gauge_rows_per_10cm"],
          stitch_type="hdc", hook_mm=P["hook_mm"], yarn_weight="worsted")
mat = Material(name="Lionbrand Color Theory", yarn_weight="worsted", colorway="Stonewash",
               fibre_content=(("acrylic", 100),))

B = P["body"]; total = B["sts"]; rib = B["hem_rib_sts"] - 1   # "BLO HDC 9, HDC in last st"
def body_row(i, a_row):
    field = total - rib - 1
    pair = Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")], times=field // 2) if not a_row \
        else Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=field // 2)
    ops = [Op("hdc", rib, loop="back"), pair, Op("hdc", 1)] if a_row else [pair, Op("hdc", rib, loop="back"), Op("hdc", 1)]
    return Row(index=i, ops=ops, declared_count=total, turning_chain=1)

rows = [Row(index=1, ops=[Op("hdc", total)], declared_count=total, turning_chain=0, skips=1)]
n = 1
for _ in range(B["front_rows"] - 1):
    n += 1; rows.append(body_row(n, a_row=(n % 2 == 1)))
# Back panel row 1: BLO 9, pairs until 29 left, hdc 1, ch 29 (the sleeve opening)
ch = B["sleeve_opening_ch"]; worked = total - ch
n += 1
pairs_arm = (total - rib - 1 - (ch - 1)) // 2          # 28 for S: p6 "<66 + 29 chs>"
rows.append(Row(index=n, ops=[Op("hdc", rib, loop="back"),
                              Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=pairs_arm),
                              Op("hdc", 1), Op("ch", ch, spans=ch - 1)],
                declared_count=rib + 2 * pairs_arm + 1 + ch, turning_chain=1, allow_remainder=True,
                note="sleeve opening 1: 28 sts left unworked under the 29-chain bridge"))
n += 1
rows.append(Row(index=n, ops=[Op("hdc", ch - 1), Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")], times=(total - (ch - 1) - rib - 1) // 2),
                              Op("hdc", rib, loop="back"), Op("hdc", 1)],
                declared_count=total, turning_chain=0, skips=1, note="worked back along the opening chains: hdc in 2nd ch from hook"))
for _ in range(B["back_rows"] - 2):
    n += 1; rows.append(body_row(n, a_row=(n % 2 == 1)))
n += 1
rows.append(Row(index=n, ops=[Op("hdc", rib, loop="back"),
                              Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=pairs_arm),
                              Op("hdc", 1), Op("ch", ch, spans=ch - 1)],
                declared_count=rib + 2 * pairs_arm + 1 + ch, turning_chain=1, allow_remainder=True,
                note="sleeve opening 2"))
n += 1
rows.append(Row(index=n, ops=[Op("hdc", ch - 1), Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")], times=(total - (ch - 1) - rib - 1) // 2),
                              Op("hdc", rib, loop="back"), Op("hdc", 1)], declared_count=total, turning_chain=0, skips=1))
for _ in range(B["front_rows"] - 2):
    n += 1; rows.append(body_row(n, a_row=(n % 2 == 1)))
n += 1
rows.append(Row(index=n, ops=[Op("hdc", rib, loop="back"), Op("hdc", total - rib)], declared_count=total, turning_chain=1, note="final body row"))
body = Component("body", "flat_rows", rows, foundation=B["foundation_ch"], grain="across")

S_ = P["sleeve"]; ss = S_["sts"]; srib = S_["cuff_rib_sts"]
srows = [Row(index=1, ops=[Op("hdc", ss)], declared_count=ss, turning_chain=0, skips=1)]
for r in range(2, S_["rows"] + 1):
    if r % 2 == 0:
        srows.append(Row(index=r, declared_count=ss, turning_chain=1,
                         ops=[Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")], times=(ss - srib - 1) // 2),
                              Op("slst", srib, loop="back"), Op("slst", 1)]))
    else:
        srows.append(Row(index=r, declared_count=ss, turning_chain=1,
                         ops=[Op("hdc", srib, loop="back"),
                              Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=(ss - srib - 1) // 2), Op("hdc", 1)]))
sleeve = Component("sleeve", "flat_rows", srows, foundation=S_["foundation_ch"], make=2, grain="across")

Pk = P["pocket"]; ps = Pk["sts"]
prows = [Row(index=1, ops=[Op("hdc", ps)], declared_count=ps, turning_chain=0, skips=1)]
for r in range(2, Pk["rows"]):
    prows.append(Row(index=r, declared_count=ps, turning_chain=1,
                     ops=[Op("hdc", 1, loop="back"), Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=(ps - 2) // 2), Op("hdc", 1)]))
prows.append(Row(index=Pk["rows"], ops=[Op("hdc", ps)], declared_count=ps, turning_chain=1))
pocket = Component("pocket", "flat_rows", prows, foundation=Pk["foundation_ch"], make=2, grain="across")

neck_len_cm = 2 * cm_st(total) + cm_row(B["back_rows"])          # up a front, across the back, down a front
neck_rows = int(round(neck_len_cm / 10.0 * P["gauge_rows_per_10cm"]))
nrows = [Row(index=1, ops=[Op("hdc", 7)], declared_count=7, turning_chain=0, skips=1)] + \
        [Row(index=r, ops=[Op("hdc", 6, loop="back"), Op("hdc", 1)], declared_count=7, turning_chain=1) for r in range(2, neck_rows + 1)]
neckband = Component("neckband", "flat_rows", nrows, foundation=8, grain="across")

cir = CIR(slug="benchmark-cardigan-with-pockets", title="Cardigan with pockets (purchased benchmark, size S)",
          version="0.1.0", construction="flat_rows", authored="benchmark", gauge=g, materials=[mat],
          components=[body, sleeve, pocket, neckband],
          assembly=[Seam(method="whipstitch", piece_a="body", piece_b="body", note="shoulder seams, fronts on back"),
                 Seam(method="whipstitch", piece_a="sleeve", piece_b="sleeve", note="fold lengthways, seam"),
                 Seam(method="whipstitch", piece_a="sleeve", piece_b="body", note="sleeve top to armhole"),
                 Seam(method="whipstitch", piece_a="neckband", piece_b="body"),
                 Seam(method="whipstitch", piece_a="pocket", piece_b="body", note="front panel only")])

# ---- compile through the repository's own chain ------------------------------------------
res = compiler.compile_cir(cir)
errors = [str(f) for f in getattr(res, "findings", []) if getattr(f, "severity", "") == "ERROR"] if hasattr(res, "findings") else []
twins = {c.name: T.build_twin(cir, res, component=c.name) for c in cir.components}

derived = {
    "body_length_cm": round(cm_st(total), 1), "front_panel_width_cm": round(cm_row(B["front_rows"]), 1),
    "back_width_cm": round(cm_row(B["back_rows"]), 1), "body_total_width_cm": round(cm_row(2 * B["front_rows"] + B["back_rows"] + 1), 1),
    "hem_rib_height_cm": round(cm_st(B["hem_rib_sts"]), 1), "sleeve_opening_depth_cm": round(cm_st(ch), 1),
    "sleeve_length_cm": round(cm_st(ss), 1), "sleeve_circumference_cm": round(cm_row(S_["rows"]), 1),
    "armhole_flat_cm": round(cm_row(S_["rows"]) / 2, 1), "cuff_rib_length_cm": round(cm_st(srib), 1),
    "neckband_width_cm": round(cm_st(7), 1), "neckband_length_cm": round(neck_len_cm, 1),
    "pocket_h_cm": round(cm_st(ps), 1), "pocket_w_cm": round(cm_row(Pk["rows"]), 1),
}
L = P["listed_cm"]
spec_check = {
    "length": (derived["body_length_cm"], L["length"]), "back_width": (derived["back_width_cm"], L["back_width"]),
    "armhole": (derived["armhole_flat_cm"], L["armhole"]), "sleeve_length": (derived["sleeve_length_cm"], L["sleeve_length"]),
}
spec_check = {k: {"derived": d, "listed": l, "diff_cm": round(d - l, 1), "diff_pct": round((d - l) / l * 100, 1)} for k, (d, l) in spec_check.items()}

structure = {
    "slug": cir.slug, "size": SIZE, "source": "purchased pattern PDF, text only, page-cited", "facts": P,
    "derived_cm": derived, "spec_check_derived_vs_listed": spec_check,
    "twin": {n: {"w": round(t.width_cm or 0, 1), "h": round(t.height_cm or 0, 1), "calibrated": t.calibrated,
                 "yarn_m": {k: round(v, 1) for k, v in t.yarn_metres_by_color.items()}} for n, t in twins.items()},
    "compile_errors": errors,
    "stitch_family": "hdc (BLO/FLO alternating)", "texture_direction_body": "rows VERTICAL (side-to-side construction)",
    "texture_direction_sleeve": "rows ALONG the sleeve length", "colour_bands": "none: single colour",
    "colour_rgb": None, "colour_note": "colourway 'Stonewash' named on p3; RGB not derivable from text -> UNKNOWN; reference rendered neutral",
    "construction_cues": ["open_front_no_closure", "no_neck_shaping", "drop_shoulder", "integral_hem_rib", "cuff_rib",
                          "neckband_full_front_edge_and_back_neck", "two_patch_pockets_on_fronts", "vertical_texture_rows"],
    "openings": ["front_opening_full_length", "round_neck_unshaped"],
    "ratios": {"length_over_back_width": round(derived["body_length_cm"] / derived["back_width_cm"], 3),
               "sleeve_length_over_body_length": round(derived["sleeve_length_cm"] / derived["body_length_cm"], 3),
               "pocket_h_over_body_length": round(derived["pocket_h_cm"] / derived["body_length_cm"], 3),
               "front_width_over_back_width": round(derived["front_panel_width_cm"] / derived["back_width_cm"], 3)},
    "twin_calibrated": False,
}
(HERE / "out" / "structure.json").write_text(json.dumps(structure, indent=1, default=str))
print(json.dumps({"compile_errors": errors, "twin": structure["twin"], "spec_check": spec_check}, indent=1))

# ---- independent cross-check against the repository's own encoding (read AFTER deriving) -----
try:
    from brambleloop.cir import benchmarks as BM
    ref = BM.cardigan(SIZE); rr = compiler.compile_cir(ref)
    rt = {c.name: T.build_twin(ref, rr, component=c.name) for c in ref.components}
    print("cross-check vs cir/benchmarks.cardigan('S') twins:",
          {n: (round(t.width_cm or 0, 1), round(t.height_cm or 0, 1)) for n, t in rt.items()})
except Exception as e:
    print("cross-check unavailable:", type(e).__name__, str(e)[:120])
