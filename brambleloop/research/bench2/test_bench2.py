"""Commercial benchmark 2 regression tests, offline. Run: python research/bench2/test_bench2.py
Reads out/ (derived data only); the parse tests need the pattern text in the scratchpad and are
skipped without it. Nothing here calls a provider."""
import json, os, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "src"))
import star_identity as SI, gate as G

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

# --- stitch vocabulary ---
from brambleloop.cir import stitches as ST
check("star-stitch vocabulary registered with the pattern's consumption (beg 3->1, star 2->1, end 1->2)", ST.BEG_STAR.consumes == 3 and ST.STAR.consumes == 2 and ST.STAR.produces == 1 and ST.END_STAR.produces == 2)
check("hdc increases registered (1->2, 1->3)", ST.HDC_INC.produces == 2 and ST.HDC_INC3.produces == 3)
check("every new code has a UK term", all(k in ST.UK_TERMS for k in ("beg_star_st", "star_st", "end_star_st", "hdc_inc", "hdc3")))

# --- Product Truth ---
pt = json.load(open(os.path.join(OUT, "product_truth.json")))
check("every Product Truth fact cites a PDF page", all(isinstance(f.get("page"), int) and 1 <= f["page"] <= 17 for f in pt["facts"].values()))
check("all ten sizes derived", [r["size"] for r in pt["derived"]["per_size"]] == ["0-3m", "3-6m", "6-12m", "12-18m", "2-3T", "4", "6", "8", "10", "12"])
check("every deterministic cross-check passed", all(c["status"] == "PASS" for c in pt["derived"]["checks"]), str([c.get("check") for c in pt["derived"]["checks"] if c["status"] != "PASS"]))
check("ambiguities are recorded, not hidden (row-range line, hood shaping rows, button count, colour)", len(pt["derived"]["ambiguities"]) >= 4)
check("the CIR for the frozen size compiles", pt["cir_for_size"]["compile"]["ok"], str(pt["cir_for_size"]["compile"]["errors"][:2]))
row = next(r for r in pt["derived"]["per_size"] if r["size"] == "2-3T")
check("2-3T: 29 stars across the back, 59 across the yoke, 13 per front panel", row["back_stars"] == 29 and row["yoke_stars"] == 59 and row["front_panel_stars"] == 13)
check("2-3T: gauge pitches 1.13 cm per star, 2.03 cm per row pair", row["cm"]["star_pitch"] == 1.13 and row["cm"]["row_pair_pitch"] == 2.03)

# --- star instrument: the self-test record and a live re-run of the deterministic cases ---
st = json.load(open(os.path.join(OUT, "star_identity_selftest.json")))
check("bars are the a priori ones and each has a stated reason", set(st["bars"]) == set(SI.BARS) and all(k in st["why"] for k in st["bars"]))
r = st["results"]
check("recorded: truth passes identity and gauge at both phases", r["truth_star"]["status"] == "PASS" and r["truth_star_phase"]["status"] == "PASS")
check("recorded: truth at 2x scale passes identity and fails gauge", r["truth_star_2x_scale(gauge_must_fail)"]["identity"] == "PASS" and r["truth_star_2x_scale(gauge_must_fail)"]["gauge"]["status"] == "FAIL")
controls = [k for k in r if k.startswith("control_")]
check("recorded: every wrong control fails identity (half-offset, hdc, seed, knit, waffle, Bench1 hero)", len(controls) >= 6 and all(r[k]["identity"] != "PASS" for k in controls), str([(k, r[k]["identity"]) for k in controls if r[k]["identity"] == "PASS"]))
photos = [k for k in r if k.startswith("real_photo:")]
check("recorded: every flat-lay photograph crop of the real fabric passes identity", all(r[k]["identity"] == "PASS" for k in photos if "flatlay" in k) and len([k for k in photos if "flatlay" in k]) == 4)
W_, H_ = 480, 400
live = SI.measure(np.array(SI.draw_star_fabric(W_, H_, 24, 43).convert("L")).astype(float), 24, 43)
check("live: the deterministic truth passes now", live["status"] == "PASS", str(live.get("failed")))
check("live: the half-offset (first model) fabric fails on column offset", "column_offset" in SI.measure(np.array(SI.draw_star_fabric(W_, H_, 24, 43, column_offset=0.5).convert("L")).astype(float), 24, 43)["failed"])
check("live: plain hdc rows fail", SI.measure(np.array(SI.draw_hdc_fabric(W_, H_, 12, 21.5).convert("L")).astype(float), 24, 43)["identity"] == "FAIL")
check("live: a seed checker fails", SI.measure(np.array(SI.draw_seed_fabric(W_, H_, 12, 21.5).convert("L")).astype(float), 24, 43)["identity"] == "FAIL")
check("live: a knit fabric fails", SI.measure(np.array(SI.draw_knit_fabric(W_, H_, 12, 21.5).convert("L")).astype(float), 24, 43)["identity"] == "FAIL")
check("live: a blank region is UNKNOWN, never PASS", SI.measure(np.full((200, 200), 200.0), 24, 43)["identity"] in ("UNKNOWN", "FAIL"))

# --- reference ---
meta = json.load(open(os.path.join(OUT, "ref_meta.json")))
check("reference: every region present", all(meta["validation"]["region_pixels"][k] > 0 for k in meta["regions"]), str({k: n for k, n in meta["validation"]["region_pixels"].items() if n == 0}))
check("reference: two sleeves and two cuffs of equal area, five buttons", meta["validation"]["region_pixels"]["sleeve_left"] == meta["validation"]["region_pixels"]["sleeve_right"] and meta["validation"]["region_pixels"]["cuff_left"] == meta["validation"]["region_pixels"]["cuff_right"] and len(meta["buttons_px"]) == 5)
g = meta["geometry_cm"]
check("reference: dimensions are Product Truth's (back width, sleeve length, hood, cuff, hem band)", g["BW"] == row["cm"]["back_width"] and g["SL"] == row["cm"]["sleeve_length"] and g["HOODH"] == row["cm"]["hood_height"] and g["CUFF"] == row["cm"]["cuff"] and g["HEM"] == row["cm"]["hem_band"])
check("reference: the star instrument reads its own fabric as star stitch at gauge", meta["validation"]["star_instrument_on_reference_front"]["status"] == "PASS")
check("reference: conventions not in the pattern are declared (gap, buttons, hood)", all(k in meta["layout"] for k in ("centre_gap_cm_DECLARED", "buttons_DECLARED", "hood_DECLARED")))
if os.path.exists(os.path.join(OUT, "ref_flatlay.png")):
    det = G.deterministic(os.path.join(OUT, "ref_flatlay.png"), "ref")
    check("gate: the reference passes its own deterministic gate (silhouette, proportions, span, 5 buttons, star identity, gauge)", det["status"] == "PASS", str({k: v["status"] for k, v in det["items"].items()}))

# --- gate logic ---
det_pass = {"status": "PASS", "items": {"silhouette": {"status": "PASS"}}}
props_ok = {"texture": {"status": "PASS", "material": True}, "body_ridge_direction": {"status": "FAIL", "material": False}}
check("a non-material FAIL does not fail the verdict", G.verdict(det_pass, props_ok, {"a": "PASS"})["status"] == "PASS")
check("a material FAIL fails the verdict whatever the judge says", G.verdict(det_pass, {"texture": {"status": "FAIL", "material": True}}, {"a": "PASS"})["status"] == "FAIL")
check("a material UNKNOWN never passes", G.verdict(det_pass, {"texture": {"status": "UNKNOWN", "material": True}}, {"a": "PASS"})["status"] == "UNKNOWN")
check("a deterministic UNKNOWN (star instrument could not read) never passes", G.verdict({"status": "UNKNOWN", "items": {"star_identity": {"status": "UNKNOWN"}}}, props_ok, {"a": "PASS"})["status"] == "UNKNOWN")
check("a judge FAIL fails the verdict", G.verdict(det_pass, props_ok, {"a": "FAIL"})["status"] == "FAIL")
check("expectations come from Product Truth (cardigan, buttoned, 5 buttons, hood, star stitch, no pockets, long sleeves, one colour)",
      G.EXPECT["product_type"][0] == {"cardigan"} and G.EXPECT["closure_count"][0] == {5} and G.EXPECT["hood"][0] == {"attached_hood"} and G.EXPECT["texture"][0] == {"star_stitch"} and G.EXPECT["pocket_count"][0] == {0} and G.EXPECT["colour_count"][0] == {1})
check("extra features: hood and buttons are the product's own; anything else fails", G.properties({"extra_features": ["hood", "buttons"]})["extra_features"]["status"] == "PASS" and G.properties({"extra_features": ["hood", "pockets"]})["extra_features"]["status"] == "FAIL")
if os.path.exists(G.CALIBRATION_FILE):
    cal = json.load(open(G.CALIBRATION_FILE))
    check("calibration withdrew materiality only by the recorded rule (wrong on more than half of the designer's photographs that show it)", all(cal["tally"][k]["agree"] * 2 < cal["tally"][k]["of"] for k in cal["withdrawn_material"]))

# --- bookkeeping ---
if os.path.exists(os.path.join(OUT, "bench2_manifest.json")):
    m = json.load(open(os.path.join(OUT, "bench2_manifest.json")))
    check("the size is frozen with a reason and the Product Truth digest", m["size"] == "2-3T" and len(m["size_reason"]) > 50 and m["product_truth_sha256"])
    check("spend stayed under the ceiling", m["spent_usd"] <= m["cap_usd"], str(m["spent_usd"]))
    check("every external call records its provider and model", all(c.get("provider") and c.get("model") for c in m["calls"]))
    if os.path.exists(os.path.join(OUT, "bench2_gate.json")):
        gj = json.load(open(os.path.join(OUT, "bench2_gate.json"))); ok_runs = [r for r in m["runs"] if r.get("ok")]
        check("every successful draw was gated", all(f"{r['mode']}_{r['draw']}" in gj for r in ok_runs))
        check("verdicts follow the rule on every candidate", all(G.verdict(r["deterministic"], r["properties"], r["judge"])["status"] == r["verdict"]["status"] for r in gj.values()))
        check("every gated candidate records the star instrument's reading on both fronts", all("star_identity" in r["deterministic"].get("items", {}) for r in gj.values() if r["deterministic"].get("items")))
# nothing of the designer's is in the repository
tracked = subprocess.run(["git", "ls-files", "research/bench2"], cwd=ROOT, capture_output=True, text=True).stdout.split()
check("no PDF, pattern text or designer photograph is tracked under research/bench2", not any(t.endswith((".pdf", "pattern.txt", ".jpg", ".jpeg", ".jp2")) for t in tracked), str([t for t in tracked if t.endswith((".pdf", ".jpg", ".jpeg", ".jp2", "pattern.txt"))]))
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
