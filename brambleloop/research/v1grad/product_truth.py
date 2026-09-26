"""Product-only Visual V1 graduation, phase 1: Product Truth for a Brambleloop-original design,
recovered from Brambleloop-owned data only.

The design is the Heirloom Cable Throw (`products/texture.py::build_cable_throw`, in the
repository since 41c9356, 2026-09-18): a risk-class-A flat throw of 18 cable columns crossing
every fourth row, separated by back-post ribbing, in one cream worsted yarn. It has never been
made physically and no photograph of it exists anywhere, which is the production condition this
benchmark tests. Every fact below comes from the CIR the design builder emits, the stitch
registry, the compiler and the digital twin -- the company's own record of what it designed --
and is cited to its source. Nothing is inferred to make rendering easier; what the design does
not specify is recorded as unspecified.

FIREWALL (phase 0). Inputs this benchmark's construction, reference and generation stages may
consume are listed in `ALLOWED_INPUTS`; everything is a Brambleloop-owned design, record or
capability. No finished-product photograph, no earlier generated image of this design, no
competitor or Bench1/Bench2 imagery and no internet product is read by any stage, and no
web search is made. Images that exist and were NOT inspected are listed in `QUARANTINE`.
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.products import texture as T                      # noqa: E402  the design (Brambleloop-owned)
from brambleloop.cir import compiler, twin as TW, stitches as ST     # noqa: E402  the company's own compiler, twin and stitch registry
from brambleloop.visual import fabric as F                          # noqa: E402  the relief rule (visual.fabric)

SLUG = "heirloom-cable-blanket"
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")


def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()


ALLOWED_INPUTS = {
    "design_source": {"path": "src/brambleloop/products/texture.py", "what": "the design: stitch pattern, counts, gauge, yarn, colour, notes", "owned": True},
    "stitch_registry": {"path": "src/brambleloop/cir/stitches.py", "what": "stitch definitions (consumption, height, row height)", "owned": True},
    "compiler_and_twin": {"path": "src/brambleloop/cir/compiler.py, src/brambleloop/cir/twin.py", "what": "counts per row, dimensions from counts x gauge, yardage", "owned": True},
    "relief_rule": {"path": "src/brambleloop/visual/fabric.py, src/brambleloop/publish/charts.py", "what": "which stitches stand proud or recede (visual.fabric, charts.relief)", "owned": True},
    "generalised_capabilities": {"path": "research/bench1, research/bench2, research/e4, research/e5", "what": "flat-lay reference conventions, alignment, texture-period and lattice instruments, reader/gate/judge structure, provider route evidence -- code only, no images of any product", "owned": True},
}
FORBIDDEN_NOT_USED = ["finished-product photographs of this design (none exist)", "earlier generated images of this design", "competitor / seller / MJ's imagery",
                      "Bench1 or Bench2 finished-product imagery", "internet products, web search", "any image chosen as 'approximately what it should look like'", "hidden target renders"]
QUARANTINE = [
    {"what": "a 6 KB chart render of a cable pattern found in the session scratchpad from an earlier session (a Brambleloop chart, not a photograph)", "sha256_prefix": "be6da6539aca0d76",
     "moved_to": "scratchpad/v1grad_quarantine/ before any construction work; not opened by this benchmark"},
    {"what": "the production artifact store `artifacts/` holds 93 content-addressed image blobs (charts, heroes and possibly provider-trial images of catalogue products, including perhaps this design)",
     "action": "none opened, listed or matched to a product by this benchmark; they are outside every stage's inputs"},
]


def facts():
    cir = T.build_cable_throw(); res = compiler.compile_cir(cir); comp = cir.components[0]
    tw = TW.build_twin(cir, res, comp.name)
    rows = comp.rows; codes_by_row = [sorted({o.stitch for o in (r.ops[0].ops if hasattr(r.ops[0], "ops") else r.ops)}) for r in rows]
    crossing_rows = [r.index for r in rows if "cable2x2" in codes_by_row[r.index - 1]]
    rib_rows = [r.index for r in rows if "fpdc" in codes_by_row[r.index - 1]]
    def st(code): s = ST.get(code); return {"consumes": s.consumes, "produces": s.produces, "height": s.height, "row_height": s.row_height, "name_us": s.name_us, "name_uk": s.name_uk}
    cell_w_mm, cell_h_mm = F.cell_size_mm(cir.gauge)
    sc_row_cm = 10.0 / cir.gauge.rows_per_10cm
    row_cm = {r.index: round(max(ST.get(o.stitch).row_height for o in (r.ops[0].ops if hasattr(r.ops[0], "ops") else r.ops)) * sc_row_cm, 4) for r in rows}
    F_ = {
        "identity": {"value": {"slug": cir.slug, "title": cir.title, "version": cir.version, "risk_class": cir.risk_class, "construction": cir.construction, "fingerprint": cir.fingerprint,
                               "owner": "Brambleloop Studio (generated by products/texture.py, in the repository since 2026-09-18, commit 41c9356)"}, "source": "CIR"},
        "product_type": {"value": "throw blanket: one flat rectangular piece worked bottom-up in turned rows, no shaping, no seams, no border, no closures", "source": "CIR construction=flat_rows, one component, no assembly, no edging op"},
        "intended_size": {"value": "one size (a throw); finished size from counts x gauge below", "source": "CIR"},
        "gauge": {"value": {"stitches_per_10cm": cir.gauge.stitches_per_10cm, "rows_per_10cm": cir.gauge.rows_per_10cm, "stated_in": cir.gauge.stitch_type, "hook_mm": cir.gauge.hook_mm}, "source": "CIR gauge (WORSTED)"},
        "yarn": {"value": [{"name": m.name, "weight": m.yarn_weight, "colorway": m.colorway, "color_id": m.color_id} for m in cir.materials], "source": "CIR materials"},
        "colours": {"value": dict(cir.colors), "source": "CIR colors (hex)"},
        "stitch_family": {"value": "post-stitch ribbing with 2x2 cable crossings on a single-crochet foundation row; every stitch both-loop", "source": "CIR ops"},
        "stitch_definitions": {"value": {c: st(c) for c in ("sc", "fpdc", "bpdc", "cable2x2")}, "source": "cir.stitches registry"},
        "stitch_pattern": {"value": {"repeat_width_sts": 8, "repeats_across": 18, "plain_row": ["bpdc 2", "fpdc 4", "bpdc 2"], "crossing_row": ["bpdc 2", "cable2x2 (over 4)", "bpdc 2"],
                                     "block": "3 plain rows then 1 crossing row", "blocks": 30, "turning_chain": {"row_1": rows[0].turning_chain, "pattern_rows": rows[1].turning_chain}}, "source": "CIR rows"},
        "counts": {"value": {"foundation_sts": comp.foundation, "stitches_per_row": 144, "rows": len(rows), "row_1": "sc 144", "rib_rows": len(rib_rows), "crossing_rows": len(crossing_rows), "crossing_row_indices": crossing_rows,
                             "cable_columns": 18, "cable_width_sts": 4, "channel_width_sts": 4, "stitches_total": tw.stitch_total, "cells": len(tw.cells)}, "source": "CIR rows, compiler, twin"},
        "construction": {"value": {"direction": "bottom-up, turned rows (right side and wrong side alternate)", "pieces": 1, "joins": "none", "shaping": "none", "openings": "none", "edging": "none specified", "closures": "none", "pockets": "none"}, "source": "CIR"},
        "cable_crossing_direction": {"value": "UNSPECIFIED by the design (the CIR has no crossing-direction property; abbreviations.DIRECTION_NOT_IN_CIR); every crossing is the same operation so all cross the same way",
                                     "source": "publish.abbreviations", "uncertainty": "material to a maker's instructions, not to the product's appearance beyond which strand lies in front; the reference DECLARES one direction"},
        "relief": {"value": {"fpdc": "stands forward (charts.relief -0.13)", "bpdc": "recedes (+0.10)", "cable2x2": "a crossing sits proud (-0.20)", "sc": "flat ground", "loop_bars": "none (every stitch both-loop; visual.fabric._ridge gives no bar)"}, "source": "publish.charts.relief, visual.fabric"},
        "designer_notes": {"value": cir.designer_notes, "source": "CIR"},
        "finished_size_note": {"value": cir.finished_size_note, "source": "CIR"},
        "texture_signature": {"value": F.texture_signature(tw), "source": "visual.fabric.texture_signature(twin)"},
    }
    derived = {
        "width_cm": round(tw.width_cm, 2), "height_cm": round(tw.height_cm, 2), "cell_w_cm": round(cell_w_mm / 10, 4), "sc_row_cm": round(sc_row_cm, 4),
        "post_row_cm": round(ST.get("fpdc").row_height * sc_row_cm, 4), "row_cm_by_index_sample": {k: row_cm[k] for k in (1, 2, 5)},
        "cable_column_pitch_cm": round(8 * cell_w_mm / 10, 3), "cable_width_cm": round(4 * cell_w_mm / 10, 3), "channel_width_cm": round(4 * cell_w_mm / 10, 3),
        "crossing_period_cm": round(4 * ST.get("fpdc").row_height * sc_row_cm, 3), "aspect_h_over_w": round(tw.height_cm / tw.width_cm, 4),
        "yarn_m": tw.yarn_metres_by_color, "yardage_tolerance": tw.yardage_tolerance, "calibrated": tw.calibrated,
    }
    checks = [
        {"check": "compiles with no errors", "status": "PASS" if res.ok else "FAIL", "evidence": res.errors[:3]},
        {"check": "18 repeats of 8 stitches make the 144-stitch width", "status": "PASS" if 18 * 8 == 144 == comp.foundation else "FAIL"},
        {"check": "1 foundation row + 30 blocks of 4 rows = 121 rows", "status": "PASS" if len(rows) == 121 else "FAIL", "evidence": len(rows)},
        {"check": "every fourth pattern row crosses, 30 crossing rows, first at row 5", "status": "PASS" if (len(crossing_rows) == 30 and crossing_rows[0] == 5 and all(b - a == 4 for a, b in zip(crossing_rows, crossing_rows[1:]))) else "FAIL", "evidence": crossing_rows[:4]},
        {"check": "every row keeps 144 stitches (compiler counts)", "status": "PASS" if all(c == 144 for c in res.counts(comp.name)) else "FAIL", "evidence": sorted(set(res.counts(comp.name)))},
        {"check": "twin width equals 144 stitches at 16 per 10 cm (90.0 cm), matching the design's size note", "status": "PASS" if abs(tw.width_cm - 90.0) < 0.05 and "90 cm" in (cir.finished_size_note or "") else "FAIL", "evidence": tw.width_cm},
        {"check": "twin height equals the sum of the rows' heights (one sc row + 120 post-stitch rows at the registry's row heights)", "status": "PASS" if abs(tw.height_cm - sum(row_cm.values())) < 0.5 else "FAIL", "evidence": [tw.height_cm, round(sum(row_cm.values()), 2)]},
        {"check": "one colour, one material", "status": "PASS" if len(cir.colors) == 1 and len(cir.materials) == 1 else "FAIL"},
        {"check": "the technique claim in the title is backed by crossing stitches (asset_truth's rule)", "status": "PASS" if "cable2x2" in tw.stitch_types_used else "FAIL"},
        {"check": "the twin's texture signature reads the fabric as textured", "status": "PASS" if F.texture_signature(tw).get("textured") else "FAIL", "evidence": F.texture_signature(tw)},
    ]
    uncertainties = [
        {"what": "gauge is stated in single crochet (16 x 18 per 10 cm) while the fabric is post double crochet; the height uses the registry's row-height ratio (fpdc row_height x the sc row)", "used": f"{tw.height_cm:.1f} cm from the twin, the company's own model; a physical swatch would calibrate it (twin.calibrated = {tw.calibrated})", "material": "the aspect ratio of the reference (proportions bar +-10 %)"},
        {"what": "cable fabric draws in across its width (the design's own size note); the stated-gauge width is 90 cm", "used": "90.0 cm, as the design states it and the twin measures it", "material": "width only if a physical sample says otherwise"},
        {"what": "crossing direction is unspecified by the design", "used": "the reference draws every crossing with the LEFT pair in front (declared convention); the pattern text says all crossings go the same way", "material": "not to product identity"},
        {"what": "no edging or border is specified", "used": "none drawn", "material": "a border would be an invented feature"},
    ]
    return cir, tw, F_, derived, checks, uncertainties


def main():
    cir, tw, F_, derived, checks, uncert = facts()
    OUT.mkdir(parents=True, exist_ok=True)
    pt = {"benchmark": "Product-only Visual V1 graduation (blind Brambleloop product)", "slug": SLUG, "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "firewall": {"allowed_inputs": {k: {**v, "sha256": (sha(ROOT / v["path"]) if (ROOT / v["path"]).is_file() else None)} for k, v in ALLOWED_INPUTS.items()},
                       "forbidden_and_not_used": FORBIDDEN_NOT_USED, "quarantine": QUARANTINE, "web_search": "none",
                       "statement": "EXTERNAL FINISHED-PRODUCT VISUAL REFERENCES USED BY PRODUCT CONSTRUCTION OR GENERATION: NONE"},
          "facts": F_, "derived": derived, "checks": checks, "uncertainties": uncert,
          "cir": {"fingerprint": cir.fingerprint, "compile_ok": all(c["status"] == "PASS" for c in checks if c["check"].startswith("compiles"))}}
    json.dump(pt, open(OUT / "product_truth.json", "w"), indent=1, default=str)
    for c in checks: print(c["status"], c["check"])
    print("derived", json.dumps(derived)[:400])


if __name__ == "__main__":
    main()
