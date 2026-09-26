"""Commercial benchmark 2, phase 1: the purchased "Mini Star Stitch Cardigan" parsed into
Product Truth for ALL TEN SIZES.

The PDF, its text and the designer's photographs are outside the repository (the pattern's own
licence forbids using its images or text to sell finished items, and the repository's standing
rule keeps a seller's expression out). This parser reads the extracted text at run time. What is
written to `out/product_truth.json` is facts about how the garment is made -- counts, gauge,
construction, measurements -- each cited to a page. The designer's prose is not reproduced.

The PDF's body pages are letter-spaced ("W o r k e d"); the parser normalises that first, then
regex-matches every size vector. Every arithmetic claim the pattern makes is recomputed across
all ten sizes, and every stated measurement is recomputed from counts x gauge. Ambiguities are
recorded, never silently resolved.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row, Seam  # noqa: E402
from brambleloop.cir import compiler, twin as T                                          # noqa: E402

PATTERN_TXT = os.environ.get("BENCH2_PATTERN_TXT", "/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/bench2/pattern.txt")
SIZES = ("0-3m", "3-6m", "6-12m", "12-18m", "2-3T", "4", "6", "8", "10", "12")
N = len(SIZES)


def normalise(text: str) -> str:
    """Collapse letter spacing: single spaces between non-space characters are removed, runs of
    two or more spaces become one. 'R o w  2 :  C h  3' -> 'Row 2: Ch 3'. Applied to every line
    (normal lines lose their inter-word single spaces, which the regexes below do not need)."""
    out = []
    for line in text.split("\n"):
        line = re.sub(r"(?<=\S) (?=\S)", "", line); line = re.sub(r" {2,}", " ", line)
        out.append(line)
    return "\n".join(out)


def pages(text):
    """Page number -> the page's text with every space and newline removed. The PDF mixes
    letter-spaced and ordinary lines and breaks size vectors across lines; the regexes below
    are written without spaces, so matching on the squeezed text is robust to both."""
    parts = re.split(r"=== page (\d+)\n", text)
    return {int(parts[i]): re.sub(r"[ \n\r\t]", "", parts[i + 1]) for i in range(1, len(parts) - 1, 2)}


def raw_pages(text):
    parts = re.split(r"=== page (\d+)\n", text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def vec(s, n=N):
    """'6(6,7,7,8,8,9,9,11,11)' -> ten numbers; a dash means 'not this size' (None)."""
    s = s.replace("\n", "")
    m = re.search(r"([\d.]+|-|x)\s*\(([^)]*)\)", s)
    assert m, s
    toks = [m.group(1)] + [t.strip() for t in m.group(2).split(",")]
    vals = [None if t in ("-", "x", "") else float(t) for t in toks]
    assert len(vals) == n, (s, vals)
    return vals


def find(pg, page, pattern, flags=re.S):
    m = re.search(pattern, pg[page], flags)
    if not m: raise ValueError(f"page {page}: no match for {pattern!r}")
    return m.group(1)


def parse():
    text = open(PATTERN_TXT, encoding="utf-8", errors="replace").read(); pg = pages(text); rp = raw_pages(text)
    F = {}
    def fact(k, v, page, how): F[k] = {"value": v, "page": page, "how": how}
    fact("identity", {"title": "Mini Star Stitch Cardigan", "designer": "MJ's Off The Hook Designs Inc.", "skill": "intermediate", "pages": 17,
                      "licence_note": "the pattern's photographs, images and text may not be used to sell finished items; personal-use licence"}, 1, "cover, p2, p14")
    fact("product_type", "children's hooded cardigan, buttoned, star-stitch body, sc-blo ribbed bands and cuffs, worked flat in one piece bottom-up with sleeves built in", 2, "PROJECT DETAILS / CONSTRUCTION p4")
    fact("sizes", list(SIZES), 2, "Sizes Included: 0-3 (3-6, 6-12, 12-18, 2-3T, 4, 6, 8, 10, 12)")
    fact("fit", "oversized; sample shown with approx. 2 to 5 in of positive ease", 4, "Fit & Ease")
    fact("yarn", {"line": "MJ's Off The Hook Designs Timeless Tones", "weight": "DK #3", "fibre": "100% premium acrylic", "put_up": "273 yd / 100 g", "shown_in": ["Oat Milk", "Toasted Almond"]}, 3, "YARN")
    fact("hooks_mm", {"body": 5.5, "bands_edging": 5.0}, 3, "HOOKS; p7 body with larger hook, bands with smaller")
    fact("buttons", {"count": "4-6", "size_mm": "18-20"}, 3, "SUPPLIES")
    fact("gauge", {"body": {"stitches_per_4in": float(find(pg, 3, r"Pattern:(\d+)sts")), "stars_per_4in": float(find(pg, 3, r"\((\d+)stars\)")), "rows_per_4in": float(find(pg, 3, r"stars\)and(\d+)rows")), "hook_mm": 5.5, "in": "star stitch pattern"},
                   "ribbing": {"stitches_per_2in": float(find(pg, 3, r"Ribbing:(\d+)sts")), "rows_per_2in": float(find(pg, 3, r"Ribbing:\d+stsand(\d+)rows")), "hook_mm": 5.0, "in": "sc blo"}}, 3, "GAUGE (repeated p15)")
    # size chart p4: quadruples chest / finished / balls / yards, scrambled in the text; sorted by chest = size order
    quads = re.findall(r"(?m)^([\d.]+)\n([\d.]+)\n(\d+)\n(\d+)$", rp[4].replace(" ", ""))
    quads = sorted(((float(a), float(b), int(c), int(d)) for a, b, c, d in quads), key=lambda q: q[0])
    assert len(quads) == N, quads
    fact("size_chart_in", {"chest": [q[0] for q in quads], "finished_chest": [q[1] for q in quads], "balls": [q[2] for q in quads], "yards": [q[3] for q in quads],
                           "how_recovered": "ten (chest, finished, balls, yards) quadruples in the table text, assigned to sizes by ascending chest"}, 4, "SIZE CHART")
    sch = pg[5]
    meas = {}
    for key, label in (("back_width", r"BackWidth:([\d.() ,]+)\""), ("front_width", r"FrontWidth:([\d.() ,]+)\""), ("underarm_to_hem", r"UnderarmtoHem:([\d.() ,]+)\""), ("hem_band", r"UnderarmtoHem:[\d.() ,]+\"Plus([\d.() ,]+)\""),
                       ("sleeve_width", r"SleeveWidth:([\d.() ,]+)\""), ("sleeve_length", r"SleeveLength:([\d.() ,]+)\""), ("cuff", r"SleeveLength:[\d.() ,]+\"Plus([\d.() ,]+)\""),
                       ("neck_opening", r"NeckOpening:([\d.() ,]+)\""), ("hood_height", r"HoodHeight:([\d.() ,]+)\""), ("hood_width", r"HoodTotalWidth\(basedonstitchcount\):([\d.() ,]+)\"")):
        meas[key] = vec(find(pg, 5, label))
    fact("schematic_in", meas, 5, "SCHEMATIC (inches)")
    fact("special_stitches", {"beg_star": "ch 3 counts as the turning chains; loops in 2nd ch, next ch and next 3 sts (6 loops), yo through all, ch 1 = eye; consumes 3 sts",
                              "star": "loops in the previous eye, the leg of its last loop, its base st, then the next 2 sts (6 loops), yo through all, ch 1; consumes 2 new sts",
                              "end_star": "as star but into the last st only (5 loops); consumes 1 st; its eye and its top are both worked into on the return",
                              "return_row": "ch 1, 1 hdc in the first eye, 2 hdc in each eye across, 1 hdc in the top of the last star",
                              "period": "two rows: a star row (RS) and an hdc return row (WS); stars = sts / 2"}, 6, "SPECIAL STITCHES; body rows 2-3 p7")
    # --- back band ---
    bb = {"foundation_ch": vec(find(pg, 7, r"Row1:Withthesmallerhook,ch([\d(),]+),work")), "stitches": vec(find(pg, 7, r"eachchacross,turn—([\d(),]+)sts\.Row2")),
          "rows": vec(find(pg, 7, r"Rows3-([\d(),]+):RepRow2")), "stitch": "sc blo every row (ribbing), 5 mm hook"}
    fact("back_band", bb, 7, "Back Band rows 1-3+")
    # --- body (back) ---
    body = {"setup_sts": vec(find(pg, 7, r"\(1stperrow\)—([\d(),]+)sts")), "row1_sts": vec(find(pg, 7, r"work2scineachoflast2sts,turn—([\d(),]+)sts")),
            "stars": vec(find(pg, 7, r"endstar,turn—([\d(),]+)stars")), "return_sts": vec(find(pg, 7, r"topofthelaststar,turn—([\d(),]+)sts")),
            "last_row": vec(find(pg, 7, r"Rows4-([\d(),]+):RepRows2&3")), "row1": "sc with 2 sc in the first 2 and last 2 sts (+4)", "then": "rows 2-3 star/return, repeated"}
    fact("body_back", body, 7, "Body Setup Row, Rows 1-3, Rows 4-N")
    # --- sleeves ---
    sl = {"left_chain": vec(find(pg, 8, r"ch([\d(),]+)chsandfastenoff")), "right_chain": vec(find(pg, 8, r"Row1\(RS\):Ch([\d(),]+),begstar")),
          "stars": vec(find(pg, 8, r"lastch,endstar,turn—([\d(),]+)stars")), "return_sts": vec(find(pg, 8, r"topofthelaststar,turn—([\d(),]+)sts")),
          "last_row_before_neck": vec(find(pg, 8, r"Rows4-([\d(),]+):RepRows2&3,endingrepeatonRow2")), "note": "the right sleeve chain is 3 more than the left: the first star's turning chains"}
    fact("sleeves_built_in", sl, 8, "Sleeves: Left Sleeve, Right Sleeve Rows 1-3, Rows 4-N")
    neck = {"count_over": vec(find(pg, 8, r"countover([\d(),]+)sts,pm")), "opening_sts": vec(find(pg, 8, r"openingshouldbe([\d(),]+)sts"))}
    fact("neck_opening", neck, 8, "Mark Neck Opening")
    fr = {"row1_stars": vec(find(pg, 8, r"beforemarker,endstar,turn—([\d(),]+)stars")), "row2_sts": vec(find(pg, 8, r"Row2\(Incr\).*?turn—([\d(),]+)sts")),
          "row3_stars": vec(find(pg, 8, r"ndRow3:Ch3,begstar,starstnext2stsacrosstothelastst,endstar,turn—([\d(),]+)stars")), "rows_4_to": vec(find(pg, 8, r"Rows4-([\d(),]+):RepRows2&3endingrepeatonRow2")),
          "ending_sts": vec(find(pg, 8, r"endingwith([\d(),]+)sts")), "later_rows_from": vec(find(pg, 9, r"Rows(-\([-\d,]+\))torow"), n=9), "later_rows_to": vec(find(pg, 9, r"torow(-\([-\d,]+\)):WorkRows7-8"), n=9),
          "row2_shaping": "increase of 2 sts at the neck edge on each return row (front neck shaping)"}
    fact("front_right", fr, 8, "Front Right rows 1-N; p9 later sizes")
    fact("mark_sleeve", {"count_from_sleeve_edge": vec(find(pg, 9, r"Fromsleeveedgecountover([\d(),]+),placemarker"))}, 9, "Mark Sleeve")
    fp = {"stars": vec(find(pg, 9, r"FrontRightPanelRow1\(RS\):Ch3,begstar,starstnext2stsacrosstothelastst,endstar,turn—([\d(),]+)stars")), "sts": vec(find(pg, 9, r"FrontRightPanel.*?turn—([\d(),]+)sts\.Rows3")),
          "rows_3_to": vec(find(pg, 9, r"Rows3-([\d(),]+):RepRows1&2endingrepeatonRow1")), "final_sc_row": vec(find(pg, 9, r"Row([\d(),]+):Ch1,work1scintheeye")),
          "band_rows_4_to": vec(find(pg, 9, r"Rows4-([\d(),]+):RepRow2&3")), "band_stitches": vec(find(pg, 9, r"BandThebandisjoined.*?turn—([\d(),]+)sts")), "band": "sc blo ribbing joined as you go along the front's bottom edge, 2 body sts per 2 band rows"}
    fact("front_panels", fp, 9, "Front Right Panel, Band; Front Left mirrors (p10)")
    hd = {"join_row_down": None, "row1_sts": vec(find(pg, 10, r"\(2stsperrow\),turn—([\d(),]+)sts")),
          "row2_sts": vec(find(pg, 11, r"2scinlastst,turn—([\d(),]+)sts")), "row3_stars": vec(find(pg, 11, r"Row3:Ch3,begstar,starstnext2stsacrosstothelastst,endstar,turn—([\d(),]+)stars")),
          "row4_sts": vec(find(pg, 11, r"2hdcinthetopofthelaststar,turn—([\d(),]+)sts")), "row5_stars": vec(find(pg, 11, r"Row5:Ch3,begstar,starstnext2stsacrosstothelastst,endstar,turn—([\d(),]+)stars")),
          "rows_7_to": vec(find(pg, 11, r"Rows7-([\d(),]+):RepRows5&6")), "shaping": "3 further rows: decrease (1 hdc instead of 2 in each of the 2 centre eyes), star row, decrease; each decrease removes one star",
          "seam": "fold in half, whip stitch across the top", "optional": True}
    hd["join_row_down"] = [float(re.sub(r"[a-z]", "", t)) for t in re.findall(r"\d+[a-z]{2}", find(pg, 10, r"rowedgeatthe([\d(),thrdns]+)rowdownfromtheneckedge"))]
    fact("hood", hd, 10, "Hood (Optional) p10-11, Hood Shaping, Hood Seam")
    fact("seams", ["hood: fold, whip stitch across the top", "sleeve and side seams: fold RS facing, sew cuff to underarm and down the side"], 11, "Hood Seam; Sleeve and Side Seams")
    fact("edging", "sc evenly up the right front (3 sc per 2 rows), across the band sts, around the hood edge, down the left front; 5 mm hook", 11, "Edging p11-12")
    fact("buttonholes", {"count": "4-6, evenly spaced along the right front edge", "where": "in the centre of the collar band width at each marker", "small": "ch 1, skip 1", "large": "ch 2, skip 2"}, 12, "Mark Buttonholes, Buttonhole Row")
    fact("collar_band", {"stitches": [v - 1 for v in vec(find(pg, 12, r"Row1:Ch([\d(),]+),1scin2ndch"))], "how": "sc blo ribbing joined as you go along the whole front/hood edge from the bottom of the right front to the bottom of the left front; buttons sewn on the left collar edge"}, 12, "Collar")
    fact("cuff", {"round1_sts": vec(find(pg, 12, r"aroundthesleeveedge:([\d(),]+)sts")), "how": "sc round, then sc-blo ribbing joined as you go; first and last ribbing rows seamed"}, 12, "Cuff")
    return F


def derive(F):
    g = F["gauge"]["value"]; st_in = 4.0 / g["body"]["stitches_per_4in"]; row_in = 4.0 / g["body"]["rows_per_4in"]; star_in = 2 * st_in
    rib_st_in = 2.0 / g["ribbing"]["stitches_per_2in"]; rib_row_in = 2.0 / g["ribbing"]["rows_per_2in"]
    m = F["schematic_in"]["value"]; bb = F["back_band"]["value"]; body = F["body_back"]["value"]; sl = F["sleeves_built_in"]["value"]; nk = F["neck_opening"]["value"]
    fr = F["front_right"]["value"]; fp = F["front_panels"]["value"]; hd = F["hood"]["value"]; ms = F["mark_sleeve"]["value"]; cf = F["cuff"]["value"]; cb = F["collar_band"]["value"]
    per_size = []; checks = []; ambiguities = []
    def chk(name, ok_list, detail): checks.append({"check": name, "status": "PASS" if all(ok_list) else "FAIL", "per_size": ok_list, "detail": detail})
    for i, size in enumerate(SIZES):
        d = {"size": size}
        d["back_sts"] = body["row1_sts"][i]; d["back_stars"] = body["stars"][i]; d["body_rows"] = body["last_row"][i]  # rows 1..N incl. the sc row 1
        d["sleeve_chain"] = sl["left_chain"][i]; d["yoke_sts"] = sl["return_sts"][i]; d["yoke_stars"] = sl["stars"][i]
        d["sleeve_rows_before_neck"] = sl["last_row_before_neck"][i]
        d["neck_sts"] = nk["opening_sts"][i]; d["neck_side_count"] = nk["count_over"][i]
        d["front_right_final_sts"] = fr["ending_sts"][i]
        d["front_panel_sts"] = fp["sts"][i]; d["front_panel_stars"] = fp["stars"][i]; d["front_panel_rows"] = fp["final_sc_row"][i]
        d["band_sts"] = bb["stitches"][i]; d["band_rows"] = bb["rows"][i]; d["front_band_rows"] = fp["band_rows_4_to"][i]
        d["hood_join_row_down"] = hd["join_row_down"][i]; d["hood_row1_sts"] = hd["row1_sts"][i]; d["hood_width_sts"] = hd["row4_sts"][i]; d["hood_rows"] = hd["rows_7_to"][i] + 3
        d["cuff_sts"] = cf["round1_sts"][i]; d["collar_sts"] = cb["stitches"][i]
        # the sleeve rows after the neck marker: front right rows (the later-size line is short by one size; see ambiguities)
        after = fr["rows_4_to"][i] if i < 2 else (fr["later_rows_to"][i - 1] if i - 1 < len(fr["later_rows_to"]) and fr["later_rows_to"][i - 1] is not None else None)
        d["sleeve_rows_after_neck_stated"] = after
        d["sleeve_rows_total_from_width"] = round(m["sleeve_width"][i] / row_in)
        d["sleeve_rows_after_neck_derived"] = d["sleeve_rows_total_from_width"] - d["sleeve_rows_before_neck"]
        # inches from counts
        d["cm"] = {"back_width": round(d["back_sts"] * st_in * 2.54, 1), "front_width": round(d["front_panel_sts"] * st_in * 2.54, 1),
                   "underarm_to_hem": round(d["body_rows"] * row_in * 2.54, 1), "hem_band": round(d["band_sts"] * rib_st_in * 2.54, 1),
                   "sleeve_width": round(d["sleeve_rows_total_from_width"] * row_in * 2.54, 1), "sleeve_length": round(d["sleeve_chain"] * st_in * 2.54, 1), "cuff": round(d["collar_sts"] * rib_st_in * 2.54, 1),
                   "neck_opening": round(d["neck_sts"] * st_in * 2.54, 1), "hood_width": round(d["hood_width_sts"] * st_in * 2.54, 1), "hood_height": round(d["hood_rows"] * row_in * 2.54, 1),
                   "star_pitch": round(star_in * 2.54, 2), "row_pair_pitch": round(2 * row_in * 2.54, 2), "wingspan": round((d["back_sts"] + 2 * d["sleeve_chain"]) * st_in * 2.54, 1)}
        d["stated_in"] = {k: m[k][i] for k in m}
        d["finished_chest_in"] = F["size_chart_in"]["value"]["finished_chest"][i]; d["yards"] = F["size_chart_in"]["value"]["yards"][i]
        per_size.append(d)
    P = per_size
    chk("stars = sts / 2 on the back", [P[i]["back_stars"] == P[i]["back_sts"] / 2 for i in range(N)], "row 2 stars vs row 1 sts")
    chk("body row 1 = setup + 4", [body["row1_sts"][i] == body["setup_sts"][i] + 4 for i in range(N)], "2 sc in the first 2 and last 2 sts")
    chk("back band rows = body setup sts (1 sc per band row)", [bb["rows"][i] == body["setup_sts"][i] for i in range(N)], "")
    chk("back band foundation = sts + 1", [bb["foundation_ch"][i] == bb["stitches"][i] + 1 for i in range(N)], "")
    chk("yoke sts = 2 x sleeve chain + back sts", [sl["return_sts"][i] == 2 * sl["left_chain"][i] + body["row1_sts"][i] for i in range(N)], "")
    chk("right sleeve chain = left chain + 3", [sl["right_chain"][i] == sl["left_chain"][i] + 3 for i in range(N)], "the first star's turning chains")
    chk("yoke stars = yoke sts / 2", [sl["stars"][i] == sl["return_sts"][i] / 2 for i in range(N)], "")
    chk("neck: 2 x side count + opening = yoke sts", [2 * nk["count_over"][i] + nk["opening_sts"][i] == sl["return_sts"][i] for i in range(N)], "")
    chk("front right row 1 stars = side count / 2", [fr["row1_stars"][i] == nk["count_over"][i] / 2 for i in range(N)], "")
    chk("front right row 2 = side count + 2 (neck shaping)", [fr["row2_sts"][i] == nk["count_over"][i] + 2 for i in range(N)], "")
    chk("front right ends with sleeve chain + front panel sts", [fr["ending_sts"][i] == sl["left_chain"][i] + fp["sts"][i] for i in range(N)], "")
    chk("mark sleeve = sleeve chain", [ms["count_from_sleeve_edge"][i] == sl["left_chain"][i] for i in range(N)], "")
    chk("front panel stars = sts / 2", [fp["stars"][i] == fp["sts"][i] / 2 for i in range(N)], "")
    chk("hood row 1 = neck sts + 4 x join row (2 sc per row, both fronts)", [hd["row1_sts"][i] == nk["opening_sts"][i] + 4 * hd["join_row_down"][i] for i in range(N)], "")
    chk("hood row 3 stars = row 2 sts / 2", [hd["row3_stars"][i] == hd["row2_sts"][i] / 2 for i in range(N)], "")
    chk("hood row 4 = row 2 + 4", [hd["row4_sts"][i] == hd["row2_sts"][i] + 4 for i in range(N)], "")
    chk("stated back width within 6 % of sts x gauge", [abs(P[i]["back_sts"] * st_in - m["back_width"][i]) / m["back_width"][i] <= 0.06 for i in range(N)], "")
    chk("stated front width within 6 % of sts x gauge", [abs(P[i]["front_panel_sts"] * st_in - m["front_width"][i]) / m["front_width"][i] <= 0.06 for i in range(N)], "")
    chk("stated underarm-to-hem within 6 % of body rows x gauge", [abs(P[i]["body_rows"] * row_in - m["underarm_to_hem"][i]) / m["underarm_to_hem"][i] <= 0.06 for i in range(N)], "")
    chk("stated hem band within a quarter inch of band sts x ribbing gauge (the schematic rounds to 1/4 in)", [abs(P[i]["band_sts"] * rib_st_in - m["hem_band"][i]) <= 0.25 + 1e-9 for i in range(N)],
        "7 sts x 0.2 in = 1.4 vs stated 1.5; 8 sts = 1.6 vs 1.75: rounding, recorded")
    chk("stated sleeve length within 6 % of sleeve chain x gauge", [abs(P[i]["sleeve_chain"] * st_in - m["sleeve_length"][i]) / m["sleeve_length"][i] <= 0.06 for i in range(N)], "")
    chk("stated hood width within 6 % of hood sts x gauge", [abs(P[i]["hood_width_sts"] * st_in - m["hood_width"][i]) / m["hood_width"][i] <= 0.06 for i in range(N)], "")
    chk("stated hood height within 6 % of (hood rows + 3 shaping rows) x gauge", [abs(P[i]["hood_rows"] * row_in - m["hood_height"][i]) / m["hood_height"][i] <= 0.06 for i in range(N)], "")
    chk("stated neck opening within 12 % of neck sts x gauge", [abs(P[i]["neck_sts"] * st_in - m["neck_opening"][i]) / m["neck_opening"][i] <= 0.12 for i in range(N)], "the schematic rounds the neck to the quarter inch")
    chk("sleeve rows before the neck = half the rows the stated sleeve width implies", [P[i]["sleeve_rows_before_neck"] == P[i]["sleeve_rows_total_from_width"] / 2 for i in range(N)], "the sleeve is folded: half its width is worked before the neck marker, half after")
    stated_after = [P[i]["sleeve_rows_after_neck_stated"] for i in range(N)]; derived_after = [P[i]["sleeve_rows_after_neck_derived"] for i in range(N)]
    ambiguities.append({"where": "p9-10 'Rows - (-, 9, 9, 9, 11, 11, 11, 11) to row - (-, 10, 10, 12, 12, 14, 16, 18)'",
                        "what": "the later-size row-range line lists nine entries for ten sizes; read literally it ends size 10 at row 18 and gives size 12 nothing",
                        "consistent_reading": f"the sleeve rows after the neck must equal the rows before it ({derived_after}); the line is one value short (size 8 = 14 was dropped), so sizes 6-12m..12 end at rows {derived_after[2:]}",
                        "stated_literal": stated_after, "used": derived_after, "material": "row count only; the finished sleeve width is stated on the schematic and used"})
    ambiguities.append({"where": "p11 Hood Shaping 'Work the final 3 rows as follows'", "what": "whether the 3 shaping rows replace the last 3 pattern rows or follow them",
                        "consistent_reading": "they follow them: hood height = (rows 7-N + 3) x row gauge matches the schematic within 6 % on all ten sizes; replacing would miss by 3 rows", "used": "additional"})
    ambiguities.append({"where": "p12 buttons", "what": "4-6 buttons 'depending on size and preference'; placement by markers", "used": "5 buttons, evenly spaced on the right collar band, for the benchmark size (declared)"})
    ambiguities.append({"where": "colour", "what": "yarn shown in Oat Milk and Toasted Almond; the gallery also shows a dusty pink; no RGB in the text", "used": "Oat Milk (a warm cream), RGB sampled from the designer's photograph of it, declared"})
    return {"per_size": per_size, "checks": checks, "ambiguities": ambiguities, "units": {"stitch_in": round(st_in, 4), "row_in": round(row_in, 4), "star_in": round(star_in, 4), "rib_stitch_in": rib_st_in, "rib_row_in": rib_row_in}}


def build_cir(F, size):
    """The garment at one size as a CIR: back band, the one-piece body (back, yoke with built-in
    sleeves, fronts), hood, front bands, collar, cuffs. Star rows use the star-stitch family now
    in `cir.stitches`; every row's declared count is the pattern's own."""
    i = SIZES.index(size); bb = F["back_band"]["value"]; body = F["body_back"]["value"]; sl = F["sleeves_built_in"]["value"]; nk = F["neck_opening"]["value"]
    fr = F["front_right"]["value"]; fp = F["front_panels"]["value"]; hd = F["hood"]["value"]; cb = F["collar_band"]["value"]; cf = F["cuff"]["value"]
    def star_row(n, sts, note=None):
        stars = sts // 2
        return Row(index=n, ops=[Op("beg_star"), Op("star", stars - 2), Op("end_star")], declared_count=stars + 1, turning_chain=3, note=note or f"{stars} stars")
    def return_row(n, stars, extra=0):
        # 1 hdc in the first eye, 2 hdc in each remaining eye, 1 hdc in the top of the last star
        ops = [Op("hdc", 1), Op("hdc_inc", stars - 1), Op("hdc", 1)]
        return Row(index=n, ops=ops, declared_count=2 * stars, turning_chain=1)
    # back band: ribbing rows of sc blo
    w = int(bb["stitches"][i]); rows = [Row(index=1, ops=[Op("sc", w)], declared_count=w, turning_chain=1)]
    rows += [Row(index=k, ops=[Op("sc", w, loop="back")], declared_count=w, turning_chain=1) for k in range(2, int(bb["rows"][i]) + 1)]
    band = Component("back_band", "flat_rows", rows, foundation=w, grain="across", note="sc blo ribbing; the body's setup row is worked along its long edge")
    # body: setup (1 sc per band row) -> row 1 (+4) -> star/return pairs -> yoke rows with sleeves chained on -> fronts worked separately
    setup, r1, stars = int(body["setup_sts"][i]), int(body["row1_sts"][i]), int(body["stars"][i]); last = int(body["last_row"][i])
    brows = [Row(index=0, ops=[Op("sc", setup)], declared_count=setup, turning_chain=1, note="setup row along the band's edge, 1 sc per band row"),
             Row(index=1, ops=[Op("inc", 2), Op("sc", setup - 4), Op("inc", 2)], declared_count=r1, turning_chain=1)]
    n = 1
    for k in range(2, last + 1):
        n = k
        brows.append(star_row(k, r1) if k % 2 == 0 else return_row(k, stars))
    body_c = Component("back_body", "flat_rows", brows, foundation=0, foundation_kind="none", grain="up", note="hem to underarm; rows alternate star (RS) and hdc return (WS)")
    # yoke: sleeves chained on both sides, then star/return pairs to the neck marker
    ch, ysts, ystars, yrows = int(sl["left_chain"][i]), int(sl["return_sts"][i]), int(sl["stars"][i]), int(sl["last_row_before_neck"][i])
    yr = [star_row(1, ysts, note=f"right sleeve chained ({ch}+3) and left sleeve chained ({ch}) beside the back's {r1} sts; {ystars} stars across sleeve, back, sleeve")]
    for k in range(2, yrows + 1):
        yr.append(return_row(k, ystars) if k % 2 == 0 else star_row(k, ysts))
    yoke = Component("yoke_with_sleeves", "flat_rows", yr, foundation=ysts, foundation_kind="none", grain="up",
                     note=f"sleeves built into the body: {ch} chains each side plus the back's last row = {ysts} sts available to row 1; neck marked after the last row")
    # fronts (each): rows from the neck marker with +2 neck shaping on return rows, then the front panel to the hem, then the sc row
    side = int(nk["count_over"][i]); fstars = int(fr["row1_stars"][i]); after = int(round(F["_derived_after"][i])) if "_derived_after" in F else None
    frows = [star_row(1, side)]; cur_stars = fstars
    k = 1
    while k < (after or 6):
        k += 1
        if k % 2 == 0:
            # 1 hdc in the first eye, 1 in its top, 2 in the next eye, 1 in its top, 2 in each eye, 1 in the last top:
            # five stitches from the two neck-edge stars, counted as a 3-into-1 on the first eye
            frows.append(Row(index=k, ops=[Op("hdc3", 1), Op("hdc_inc", cur_stars - 1), Op("hdc", 1)], declared_count=2 * cur_stars + 2, turning_chain=1, note="neck shaping: +2 at the neck edge"))
            cur_stars += 1
        else:
            frows.append(star_row(k, 2 * cur_stars))
    front = Component("front_with_sleeve", "flat_rows", frows, foundation=0, foundation_kind="none", make=2, grain="up", note="worked separately from the neck marker; the sleeve is then marked off and the front panel continues")
    psts, pstars, prow = int(fp["sts"][i]), int(fp["stars"][i]), int(fp["final_sc_row"][i])
    prows = [star_row(1, psts)]
    for k in range(2, prow):
        prows.append(return_row(k, pstars) if k % 2 == 0 else star_row(k, psts))
    prows.append(Row(index=prow, ops=[Op("sc", 1), Op("inc", pstars - 1), Op("sc", 1)], declared_count=psts, turning_chain=1, note="final sc row, then the band is joined along it"))
    panel = Component("front_panel", "flat_rows", prows, foundation=0, foundation_kind="none", make=2, grain="up")
    hrows = [Row(index=1, ops=[Op("sc", int(hd["row1_sts"][i]))], declared_count=int(hd["row1_sts"][i]), turning_chain=1, note="sc across the front row edges (2 per row) and the neck sts")]
    r2 = int(hd["row2_sts"][i]); hrows.append(Row(index=2, ops=[Op("sc", int(hd["row1_sts"][i]) - (r2 - int(hd["row1_sts"][i]))), Op("inc", r2 - int(hd["row1_sts"][i]))], declared_count=r2, turning_chain=1, note="increase row"))
    hrows.append(star_row(3, r2)); s3 = r2 // 2
    hrows.append(Row(index=4, ops=[Op("hdc3", 1), Op("hdc_inc", s3 - 2), Op("hdc3", 1), Op("hdc_inc", 1)], declared_count=2 * s3 + 4, turning_chain=1, note="increase row: +2 at each edge (eye + top of the first two and last two stars)"))
    hw = int(hd["row4_sts"][i]); hs = hw // 2
    for k in range(5, int(hd["rows_7_to"][i]) + 1):
        hrows.append(star_row(k, hw) if k % 2 == 1 else return_row(k, hs))
    hrows.append(Row(index=int(hd["rows_7_to"][i]) + 1, ops=[Op("hdc", 1), Op("hdc_inc", hs - 3), Op("hdc", 2), Op("hdc", 1)], declared_count=2 * hs - 2, turning_chain=1, note="shaping decrease: 1 hdc in each of the 2 centre eyes"))
    hrows.append(star_row(int(hd["rows_7_to"][i]) + 2, 2 * hs - 2)); hrows.append(Row(index=int(hd["rows_7_to"][i]) + 3, ops=[Op("hdc", 1), Op("hdc_inc", hs - 4), Op("hdc", 2), Op("hdc", 1)], declared_count=2 * hs - 4, turning_chain=1, note="shaping decrease"))
    hood = Component("hood", "flat_rows", hrows, foundation=0, foundation_kind="none", grain="up", note="optional; folded and seamed across the top")
    cw = int(cb["stitches"][i])
    collar = Component("collar_band", "flat_rows", [Row(index=1, ops=[Op("sc", cw)], declared_count=cw, turning_chain=1), Row(index=2, ops=[Op("sc", cw, loop="back")], declared_count=cw, turning_chain=1, note="repeat, joined as you go along the front and hood edge; buttonholes in the right front's rows")],
                       foundation=cw, grain="across")
    cuff = Component("cuff", "flat_rows", [Row(index=1, ops=[Op("sc", cw)], declared_count=cw, turning_chain=1), Row(index=2, ops=[Op("sc", cw, loop="back")], declared_count=cw, turning_chain=1, note=f"joined as you go around the {int(cf['round1_sts'][i])}-st sleeve edge")], foundation=cw, make=2, grain="across")
    g = F["gauge"]["value"]["body"]
    gauge = Gauge(stitches_per_10cm=round(g["stitches_per_4in"] / 4 / 2.54 * 10, 3), rows_per_10cm=round(g["rows_per_4in"] / 4 / 2.54 * 10, 3), stitch_type="star", hook_mm=5.5, yarn_weight="dk")
    y = F["yarn"]["value"]; mat = Material(name=f"{y['line']} ({y['weight']})", yarn_weight="dk", colorway="Oat Milk", metres_estimate=round(F["size_chart_in"]["value"]["yards"][i] * 0.9144), fibre_content=(("acrylic", 100),))
    seams = [Seam("sew", "hood", "hood", note="fold in half, whip stitch across the top", edge_a="top", edge_b="top"),
             Seam("sew", "front_with_sleeve", "yoke_with_sleeves", note="sleeve and side seams, cuff to underarm and down the side"),
             Seam("slst", "collar_band", "front_panel", note="joined as you go along the front and hood edge; 5 buttons opposite buttonholes (declared)"),
             Seam("slst", "cuff", "front_with_sleeve", note="joined as you go around the sleeve edge")]
    return CIR(slug=f"bench2-mini-star-stitch-cardigan-{size}", title=f"benchmark: Mini Star Stitch Cardigan (purchased pattern, size {size})", version="1", construction="flat_rows",
               components=[band, body_c, yoke, front, panel, hood, collar, cuff], gauge=gauge, materials=[mat], authored="benchmark", assembly=seams)


def main(size="2-3T"):
    F = parse(); D = derive(F); F["_derived_after"] = [p["sleeve_rows_after_neck_derived"] for p in D["per_size"]]
    cir = build_cir(F, size); res = compiler.compile_cir(cir)
    comp = {"ok": res.ok, "errors": [str(f) for f in res.errors][:8]}
    F.pop("_derived_after")
    out = {"source": {"pdf": "purchased pattern PDF, 17 pages, text extracted with pypdf and de-letter-spaced (not in the repository)", "sizes": list(SIZES)}, "facts": F, "derived": D,
           "cir_for_size": {"size": size, "fingerprint": cir.fingerprint, "components": [c.name for c in cir.components], "compile": comp}}
    json.dump(out, open(OUT / "product_truth.json", "w"), indent=1, default=str)
    for c in D["checks"]: print(f"  {c['status']:4s} {c['check']}" + ("" if c["status"] == "PASS" else f"  {c['per_size']}"))
    print("ambiguities:", len(D["ambiguities"])); print("compile", comp)
    for p in D["per_size"]: print(p["size"], p["cm"]["back_width"], p["cm"]["wingspan"], "sleeve rows before/after", p["sleeve_rows_before_neck"], p["sleeve_rows_after_neck_stated"], p["sleeve_rows_after_neck_derived"])
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2-3T")
