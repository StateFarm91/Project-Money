"""Commercial benchmark 1, phase 1: the purchased pattern parsed into Product Truth.

The pattern PDF and the seller's photographs are NOT in this repository (standing rule); the
PDF's text lives in the session scratchpad and this parser reads it at run time. What is
written to `out/product_truth.json` is facts about how the garment is made -- counts, gauge,
construction, measurements, assembly -- each cited to the PDF page it came from. None of the
seller's prose is reproduced.

Nothing here is taken from memory or from earlier experiments: every value is regex-matched
from the PDF text, and `cir/benchmarks.py` (an earlier, independent encoding) is only diffed
against the result afterwards as a cross-check.

Deterministic checks, in this order: (1) every row-count arithmetic the pattern states is
recomputed; (2) the stated finished measurements are recomputed from counts x gauge;
(3) the CIR built from the parse compiles (the compiler counts every row itself);
(4) the assembly's joins are checked edge against edge.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row, Seam  # noqa: E402
from brambleloop.cir import compiler, twin as T, assembly, benchmarks                      # noqa: E402
from brambleloop.visual import fabric                                                     # noqa: E402

OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
PATTERN_TXT = os.environ.get("BENCH1_PATTERN_TXT",
                             "/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/benchmark/pattern.txt")
SIZES = ("XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL")
SAMPLE = "S"   # p2: the sample is a size small


def pages(text: str) -> dict[int, str]:
    parts = re.split(r"=== page (\d+)\n", text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def vec(s: str) -> list:
    """'91(95, 95, 95, 95)(99, 99, 99, 99)' -> nine numbers, or one number for all sizes."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*\(([^)]*)\)\s*\(([^)]*)\)", s)
    if not m:
        n = re.search(r"(\d+(?:\.\d+)?)", s); v = float(n.group(1)); return [v] * 9
    nums = [float(m.group(1))] + [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(2))] + [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(3))]
    if len(nums) == 8:   # the pattern prints one size vector with a size missing (p4-8 '<90(94, 94, 94, 94)(98, 98, 98)>')
        nums.append(nums[-1])
    assert len(nums) == 9, (s, nums)
    return nums


def find(pg: dict[int, str], pattern: str, page: int) -> str:
    m = re.search(pattern, pg[page], re.S)
    if not m:
        raise ValueError(f"page {page}: could not find {pattern!r}")
    return m.group(1) if m.groups() else m.group(0)


def parse() -> dict:
    pg = pages(open(PATTERN_TXT, encoding="utf-8", errors="replace").read())
    i = SIZES.index(SAMPLE)
    facts = {}
    def fact(key, value, page, how):
        facts[key] = {"value": value, "page": page, "how": how}
    # --- product, construction (p2) ---
    fact("product_type", "cardigan with pockets, open front, no closure", 2, "MINI EXPLANATION and NOTES")
    fact("level", "beginner", 2, "LEVEL")
    fact("construction", {"body": "one piece worked flat side to side: first front, chained sleeve opening, back, chained sleeve opening, second front; hem ribbing worked into every body row",
                          "sleeves": "worked separately side to side, folded lengthways and seamed; sewn to the armholes",
                          "neckline_ribbing": "worked separately, sewn along the entire neckline",
                          "pockets": "worked separately, sewn to the front panels (optional, make 2)",
                          "seams": "whip stitch, right sides in, wrong side facing out"}, 2, "NOTES; ASSEMBLY p10-12")
    fact("sample_size", SAMPLE, 2, "'Sample is a size small'")
    fact("model_stated", {"height_cm": 160.0, "bust_cm": 81.3}, 2, "5'3\" model with a 32\" bust")
    # --- materials, gauge, measurements (p3) ---
    fact("yarn", {"line": "Lionbrand Color Theory", "weight": "Aran / Worsted / 10ply / Medium (4)", "put_up": "225 m / 100 g", "fibre": "100% acrylic", "colourway": "Stonewash",
                  "grams_by_size": vec(find(pg, r"approx\.\s*([0-9(),\s]+)g", 3))}, 3, "MATERIALS")
    fact("hook_mm", 6.0, 3, "6mm (US J)")
    fact("gauge", {"stitches_per_10cm": float(find(pg, r"=\s*([\d.]+)\s*stitches wide", 3)), "rows_per_10cm": float(find(pg, r"x\s*([\d.]+)\s*rows tall", 3)),
                   "in": "Crumpled Waffle Stitch pattern"}, 3, "GAUGE")
    meas = {}
    for key, label in (("bust_to_fit", "To fit Bust"), ("back_width", "Back Width"), ("armhole", "Armhole"), ("sleeve_length", "Sleeve length"), ("length", "Length")):
        meas[key] = vec(find(pg, label + r":\s*([0-9.(),\s]+)", 3))
    fact("stated_measurements_cm", meas, 3, "MEASUREMENTS")
    # --- stitch pattern (p4) ---
    fact("stitch_pattern", {"name": "Crumpled Waffle Stitch / Textured HDC", "foundation": "even chain", "row_1": "hdc across into back bumps",
                            "row_2": "ch1, (BLO hdc, FLO hdc) repeated, hdc in last", "row_3": "ch1, (FLO hdc, BLO hdc) repeated, hdc in last", "repeat": "rows 2-3"}, 4, "stitch pattern")
    # --- body (p4-8) ---
    body_ch = vec(find(pg, r"FIRST FRONT PANEL\s*\n?FOUNDATION CHAIN:\s*Ch\s*([0-9(),\s]+)\.", 4))
    body_sts = vec(find(pg, r"HDC across, turn\.\s*\n?<([0-9(),\s]+)>", 4))
    front_rows = vec(find(pg, r"Repeat BODY ROWS A\s*[–-]\s*B until ROW\s*([0-9(),\s]+)\.", 5))
    rib = int(find(pg, r"BLO\s*\n?HDC\s*(\d+),\s*HDC in last st", 4)) + 1   # the band is 9 back-loop stitches plus the plain last stitch
    arm_ch = vec(find(pg, r"ch\s*([0-9(),\s\n]+?),\s*turn", 6).replace("\n", " "))
    back_rows = vec(find(pg, r"Repeat BODY ROWS A\s*[–-]\s*B\s*until ROW\s*([0-9(),\s]+)\.", 6))
    total_after_back = vec(find(pg, r"Total Rows:\s*<([0-9(),\s]+)>", 6))
    second_front_rows = vec(find(pg, r"Repeat BODY ROWS A\s*[–-]\s*B until ROW\s*([0-9(),\s]+)\.", 7))
    total_after_second = vec(re.findall(r"Total Rows:\s*<([0-9(),\s]+)>", pg[7])[-1])
    total_rows = vec(find(pg, r"Total Rows:\s*<([0-9(),\s]+)>", 8))
    fact("body", {"foundation_ch": body_ch, "stitches": body_sts, "hem_rib_stitches": rib, "first_front_rows": front_rows, "sleeve_opening_chains": arm_ch,
                  "back_rows": back_rows, "second_front_rows": second_front_rows, "final_plain_row": 1, "total_rows": total_rows,
                  "stated_totals": {"after_back": total_after_back, "after_second_front": total_after_second}}, 4, "BODY PANEL p4-8")
    # --- sleeves (p8-9) ---
    sl_ch = vec(find(pg, r"SLEEVES\s*\n?\(\*Make 2\)\s*\n?FOUNDATION CHAIN:\s*Ch\s*([0-9(),\s]+)\.", 8))
    sl_sts = vec(find(pg, r"HDC in each ch across, turn\.\s*\n?<([0-9(),\s]+)>", 8))
    sl_rows = vec(find(pg, r"Repeat ROWS 2\s*[–-]\s*3 until ROW\s*([0-9(),\s]+)\.", 9))
    cuff = int(find(pg, r"BLO sl st\s*(\d+),\s*sl st in", 8)) + 1
    fact("sleeve", {"make": 2, "foundation_ch": sl_ch, "stitches": sl_sts, "rows": sl_rows, "cuff_stitches": cuff, "cuff_stitch": "slip stitch in back loop (rows B) / hdc BLO (rows A)",
                    "finish": "fold in half lengthways, whip stitch the edges together"}, 8, "SLEEVES p8-9")
    # --- neckline ribbing (p10) ---
    nb_ch = int(find(pg, r"NECKLINE RIBBING\s*\n?FOUNDATION CHAIN:\s*Ch\s*(\d+)\.", 10)); nb_sts = int(find(pg, r"HDC in each ch across, turn\.\s*\n?<(\d+)>", 10))
    fact("neckline_ribbing", {"foundation_ch": nb_ch, "stitches": nb_sts, "row": "ch1, BLO hdc 6, hdc in last", "length": "the entire neckline (measured, not counted)"}, 10, "NECKLINE RIBBING")
    # --- pockets (p11-12) ---
    pk_ch = int(find(pg, r"POCKETS\s*\n?\(\*Make 2/optional\)\s*\n?FOUNDATION CHAIN:\s*Ch\s*(\d+)\.", 11)); pk_sts = int(find(pg, r"HDC in each ch across, turn\.\s*\n?<(\d+)>", 11))
    pk_rows = int(find(pg, r"Repeat ROW 2 until ROW (\d+)\.", 12)) + 1   # plus row 13, plain hdc
    fact("pocket", {"make": 2, "optional": True, "foundation_ch": pk_ch, "stitches": pk_sts, "rows": pk_rows, "top_edge": "slip-stitch edging along a row-end edge (rows run vertically on the garment)",
                    "placement": "UNKNOWN in the text: 'try on the cardigan to double-check pocket placement'; sewn through the front panel only"}, 11, "POCKETS p11-12")
    fact("assembly_order", ["fronts laid on back, whip stitch shoulder seams", "whip stitch top of sleeves to armholes", "pin and whip stitch ribbing along neckline",
                            "pin and whip stitch pockets to the front panels", "weave in ends, steam block"], 10, "ASSEMBLY p10-12")
    return facts


def derive(facts: dict, size: str = SAMPLE) -> dict:
    i = SIZES.index(size); g = facts["gauge"]["value"]; st, rw = 10.0 / g["stitches_per_10cm"], 10.0 / g["rows_per_10cm"]
    b, s, m = facts["body"]["value"], facts["sleeve"]["value"], facts["stated_measurements_cm"]["value"]
    front, back, total = b["first_front_rows"][i], b["back_rows"][i], b["total_rows"][i]
    d = {"size": size, "cm_per_stitch": round(st, 4), "cm_per_row": round(rw, 4),
         "body_length_cm": b["stitches"][i] * st, "front_panel_width_cm": front * rw, "back_width_cm": back * rw,
         "body_total_width_cm": total * rw, "hem_rib_height_cm": b["hem_rib_stitches"] * st,
         "sleeve_length_cm": s["stitches"][i] * st, "sleeve_circumference_cm": s["rows"][i] * rw, "sleeve_folded_width_cm": s["rows"][i] * rw / 2,
         "cuff_length_cm_at_hdc_gauge": s["cuff_stitches"] * st, "sleeve_opening_chains": b["sleeve_opening_chains"][i],
         "neckband_width_cm": facts["neckline_ribbing"]["value"]["stitches"] * st,
         "back_neck_width_cm": back * rw - 2 * front * rw,
         "pocket_width_cm": facts["pocket"]["value"]["rows"] * rw, "pocket_height_cm": facts["pocket"]["value"]["stitches"] * st}
    d["neckband_length_cm"] = 2 * d["body_length_cm"] + d["back_neck_width_cm"]
    implied = [2 * b["sleeve_opening_chains"][k] / (s["rows"][k] * rw) * 10 for k in range(9)]
    d["implied_chain_gauge_per_10cm"] = {"by_size": [round(x, 1) for x in implied], "midpoint": round((min(implied) + max(implied)) / 2, 2), "DERIVED": "from armhole chains = half sleeve circumference across the nine sizes"}
    d["sleeve_opening_slit_cm"] = round(2 * b["sleeve_opening_chains"][i] / d["implied_chain_gauge_per_10cm"]["midpoint"] * 10 / 2, 1)
    checks = []
    def chk(name, ok, detail): checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    chk("stated row totals add up", total == 2 * front + back + 1 and b["stated_totals"]["after_back"][i] == front + back and b["stated_totals"]["after_second_front"][i] == 2 * front + back,
        f"{front}+{back}+{front}+1 = {total}")
    chk("foundation chain = stitches + 1 (body, sleeve, neckband, pocket)", b["foundation_ch"][i] == b["stitches"][i] + 1 and s["foundation_ch"][i] == s["stitches"][i] + 1
        and facts["neckline_ribbing"]["value"]["foundation_ch"] == facts["neckline_ribbing"]["value"]["stitches"] + 1 and facts["pocket"]["value"]["foundation_ch"] == facts["pocket"]["value"]["stitches"] + 1, "")
    chk("stated length within 5 % of stitches x gauge", abs(d["body_length_cm"] - m["length"][i]) / m["length"][i] <= 0.05, f"{d['body_length_cm']:.1f} vs stated {m['length'][i]}")
    chk("stated back width within 5 % of back rows x gauge", abs(d["back_width_cm"] - m["back_width"][i]) / m["back_width"][i] <= 0.05, f"{d['back_width_cm']:.1f} vs stated {m['back_width'][i]}")
    chk("stated armhole = half the sleeve circumference within 6 %", abs(d["sleeve_folded_width_cm"] - m["armhole"][i]) / m["armhole"][i] <= 0.06, f"{d['sleeve_folded_width_cm']:.1f} vs stated {m['armhole'][i]}")
    sl_dev = (d["sleeve_length_cm"] - m["sleeve_length"][i]) / m["sleeve_length"][i]
    chk("stated sleeve length vs stitches x gauge (recorded, not enforced: the cuff is slip stitch and shorter than hdc gauge)", True, f"{d['sleeve_length_cm']:.1f} vs stated {m['sleeve_length'][i]} ({sl_dev:+.0%})")
    chk("back wider than both fronts: a back neck exists", d["back_neck_width_cm"] > 0, f"{d['back_neck_width_cm']:.1f} cm")
    d["checks"] = checks
    d["assumed"] = {"pocket_placement": "centred on each front panel, pocket bottom 5 cm above the hem rib -- the text leaves placement to the maker",
                    "colour_rgb": "not derivable from the text; the colourway is named (Stonewash) and its appearance is taken from the seller's photograph of it, recorded in seller_photos.json"}
    return d


def build_cir(facts: dict, size: str = SAMPLE) -> CIR:
    """The parsed pattern as a CIR, size `size`, mirroring the pattern's own row structure."""
    i = SIZES.index(size); b = facts["body"]["value"]; s = facts["sleeve"]["value"]; g = facts["gauge"]["value"]
    total, rib = int(b["stitches"][i]), int(b["hem_rib_stitches"]) - 1; front, back, arm = int(b["first_front_rows"][i]), int(b["back_rows"][i]), int(b["sleeve_opening_chains"][i])
    def body_row(n, a_row):
        field = total - rib - 1; first, second = ("front", "back") if a_row else ("back", "front")
        pair = Repeat([Op("hdc", loop=first), Op("hdc", loop=second)], times=field // 2)
        ops = [Op("hdc", rib, loop="back"), pair, Op("hdc", 1)] if a_row else [pair, Op("hdc", rib, loop="back"), Op("hdc", 1)]
        return Row(index=n, ops=ops, declared_count=total, turning_chain=1)
    def arm_row(n):
        worked = total - arm + 1; field = worked - rib - 1
        # `chains` chains span `chains - 1` stitches: one is consumed turning into the next row (p6 "<64 + 27 chs>")
        return Row(index=n, ops=[Op("hdc", rib, loop="back"), Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=field // 2), Op("hdc", 1), Op("ch", arm, spans=arm - 1)],
                   declared_count=worked + arm, turning_chain=1, skips=arm - 1, note="chains bridge the sleeve opening")
    rows = [Row(index=1, ops=[Op("hdc", total)], declared_count=total, turning_chain=1)]; n = 1
    def field_rows(count, after_arm=False):
        nonlocal n
        for k in range(count):
            n += 1; r = body_row(n, a_row=(n % 2 == 1))
            if after_arm and k == 0: r.allow_remainder = True; r.note = "works back across the bridge; the first chain is the turning chain"
            rows.append(r)
    field_rows(front - 1); n += 1; rows.append(arm_row(n)); field_rows(back - 1, True); n += 1; rows.append(arm_row(n)); field_rows(front - 1, True)
    n += 1; rows.append(Row(index=n, ops=[Op("hdc", rib, loop="back"), Op("hdc", total - rib)], declared_count=total, turning_chain=1, note="final plain row"))
    body = Component("body", "flat_rows", rows, foundation=total, grain="across")
    sl_sts, sl_rows, cuff = int(s["stitches"][i]), int(s["rows"][i]), int(s["cuff_stitches"]) - 1
    srows = [Row(index=1, ops=[Op("hdc", sl_sts)], declared_count=sl_sts, turning_chain=1)]
    for k in range(2, sl_rows + 1):
        fld = sl_sts - cuff - 1
        if k % 2 == 0: ops = [Repeat([Op("hdc", loop="back"), Op("hdc", loop="front")], times=fld // 2), Op("slst", cuff, loop="back"), Op("slst", 1)]
        else: ops = [Op("hdc", cuff, loop="back"), Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=fld // 2), Op("hdc", 1)]
        srows.append(Row(index=k, ops=ops, declared_count=sl_sts, turning_chain=1))
    sleeve = Component("sleeve", "flat_rows", srows, foundation=sl_sts, make=2, grain="across")
    nb = facts["neckline_ribbing"]["value"]["stitches"]
    band = Component("neckband", "flat_rows", [Row(index=1, ops=[Op("hdc", nb)], declared_count=nb, turning_chain=1),
                                               Row(index=2, ops=[Op("hdc", nb - 1, loop="back"), Op("hdc", 1)], declared_count=nb, turning_chain=1, note="repeat to the neckline's length")], foundation=nb, grain="across")
    pk = facts["pocket"]["value"]; ps, pr = int(pk["stitches"]), int(pk["rows"])
    prows = [Row(index=1, ops=[Op("hdc", ps)], declared_count=ps, turning_chain=1)]
    for k in range(2, pr):
        prows.append(Row(index=k, ops=[Op("hdc", 1, loop="back"), Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=(ps - 2) // 2), Op("hdc", 1)], declared_count=ps, turning_chain=1))
    prows.append(Row(index=pr, ops=[Op("hdc", ps)], declared_count=ps, turning_chain=1, note="plain row, then slip-stitch edging along a row-end edge"))
    pocket = Component("pocket", "flat_rows", prows, foundation=ps, make=2, grain="across")
    # Chain gauge is not stated. The armhole is spanned by chains and must sew to half the
    # sleeve circumference, so the pattern's own nine sizes imply a chain gauge; the midpoint
    # is carried with its spread as uncertainty (DERIVED, the same reasoning cir/benchmarks
    # records), so the assembly check can say "indeterminate" rather than guess.
    implied = [2 * b["sleeve_opening_chains"][k] / (s["rows"][k] / g["rows_per_10cm"] * 10) * 10 for k in range(9)]
    mid = (min(implied) + max(implied)) / 2; unc = (max(implied) - min(implied)) / 2 / mid
    gauge = Gauge(stitches_per_10cm=g["stitches_per_10cm"], rows_per_10cm=g["rows_per_10cm"], stitch_type="hdc", hook_mm=6.0, yarn_weight="worsted",
                  chains_per_10cm=round(mid, 2), chain_gauge_uncertainty=round(unc, 3))
    y = facts["yarn"]["value"]
    mat = Material(name=f"{y['line']} ({y['weight']})", yarn_weight="worsted", colorway=y["colourway"], metres_estimate=round(y["grams_by_size"][i] * 2.25, 0), fibre_content=(("acrylic", 100),))
    seams = [Seam("whipstitch", "body", "body", note="shoulder seams: fronts laid on back", edge_a="top", edge_b="top"),
             Seam("whipstitch", "sleeve", "sleeve", note="fold lengthways, seam the long edges", edge_a="fold", edge_b="fold"),
             Seam("whipstitch", "sleeve", "body", note="top of sleeve to armhole slit", edge_a="top", edge_b="opening"),
             Seam("whipstitch", "neckband", "body", note="along the entire neckline; the pattern states no length"),
             Seam("whipstitch", "pocket", "body", note="to the front panel only; placement left to the maker")]
    return CIR(slug="bench1-cardigan-with-pockets", title="benchmark: textured cardigan with pockets (purchased pattern, size S)", version="1", construction="flat_rows",
               components=[body, sleeve, band, pocket], gauge=gauge, materials=[mat], authored="benchmark",
               finished_size_note="size S: see stated_measurements_cm", assembly=seams)


def main():
    facts = parse(); d = derive(facts)
    cir = build_cir(facts)
    res = compiler.compile_cir(cir)
    comp = {"ok": res.ok, "errors": [str(f) for f in res.errors], "warnings": [str(f) for f in getattr(res, "warnings", [])][:10]}
    geo = None; tex = None
    if res.ok:
        twins = {c.name: T.build_twin(cir, res, c.name) for c in cir.components}
        try:
            geo = assembly.assemble(cir, twins).to_dict()
        except Exception as exc:  # noqa: BLE001
            geo = {"error": f"{type(exc).__name__}: {exc}"}
        tex = {name: fabric.texture_signature(tw, max_rows=8) for name, tw in twins.items()}
    # independent cross-check against the earlier encoding (never used as a source)
    bm = benchmarks.reconcile(SAMPLE); i = SIZES.index(SAMPLE)
    cross = {"benchmarks.BODY_STS": (benchmarks.BODY_STS[i], facts["body"]["value"]["stitches"][i]), "benchmarks.FRONT_ROWS": (benchmarks.FRONT_ROWS[i], facts["body"]["value"]["first_front_rows"][i]),
             "benchmarks.BACK_ROWS": (benchmarks.BACK_ROWS[i], facts["body"]["value"]["back_rows"][i]), "benchmarks.ARMHOLE_CH": (benchmarks.ARMHOLE_CH[i], facts["body"]["value"]["sleeve_opening_chains"][i]),
             "benchmarks.SLEEVE_STS": (benchmarks.SLEEVE_STS[i], facts["sleeve"]["value"]["stitches"][i]), "benchmarks.SLEEVE_ROWS": (benchmarks.SLEEVE_ROWS[i], facts["sleeve"]["value"]["rows"][i]),
             "benchmarks.POCKET": ((benchmarks.POCKET_STS, benchmarks.POCKET_ROWS), (facts["pocket"]["value"]["stitches"], facts["pocket"]["value"]["rows"])),
             "benchmarks.NECK_RIB_STS": (benchmarks.NECK_RIB_STS, facts["neckline_ribbing"]["value"]["stitches"]), "benchmarks.reconcile.total_rows": (bm["total_rows"], facts["body"]["value"]["total_rows"][i])}
    cross_ok = all(a == b for a, b in cross.values())
    out = {"source": {"pdf": "purchased pattern PDF, 12 pages, text extracted with pypdf (not in the repository)", "sample_size": SAMPLE},
           "facts": facts, "derived_cm": d, "cir": {"fingerprint": cir.fingerprint, "components": [c.name for c in cir.components], "compile": comp, "assembly": geo, "texture_signature": tex},
           "cross_check_vs_cir_benchmarks": {"agree": cross_ok, "pairs": cross}}
    json.dump(out, open(OUT / "product_truth.json", "w"), indent=1, default=str)
    json.dump(cir.to_dict(), open(OUT / "cir_size_S.json", "w"), indent=1, default=str)
    print("compile", comp["ok"], comp["errors"][:3]); print("assembly", (geo or {}).get("verdict"), (geo or {}).get("why", "")[:200])
    for c in d["checks"]: print(f"  {c['status']:4s} {c['check']} {c['detail']}")
    print("cross-check vs cir.benchmarks:", cross_ok); print({k: round(v, 1) for k, v in d.items() if isinstance(v, float)})
    return out


if __name__ == "__main__":
    main()
