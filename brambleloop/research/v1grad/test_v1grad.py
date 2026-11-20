"""Product-only Visual V1 graduation regression tests, offline. Run: python research/v1grad/test_v1grad.py
Reads out/ (derived data only); nothing here calls a provider."""
import json, os, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "src"))
import gate as G

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

pt = json.load(open(os.path.join(OUT, "product_truth.json")))
check("the design is Brambleloop's own (products/texture.py) and the firewall statement is made", "Brambleloop" in pt["facts"]["identity"]["value"]["owner"] and pt["firewall"]["statement"].endswith("NONE"))
check("every allowed input is a Brambleloop-owned file with a digest or a named capability", all(v["owned"] for v in pt["firewall"]["allowed_inputs"].values()))
check("no web search and every forbidden source recorded as not used", pt["firewall"]["web_search"] == "none" and len(pt["firewall"]["forbidden_and_not_used"]) >= 6)
check("quarantine recorded before construction (scratchpad chart, artifact-store blobs)", len(pt["firewall"]["quarantine"]) == 2)
check("every Product Truth fact cites its source", all(f.get("source") for f in pt["facts"].values()))
check("every deterministic cross-check passed", all(c["status"] == "PASS" for c in pt["checks"]), str([c["check"] for c in pt["checks"] if c["status"] != "PASS"]))
check("uncertainties are declared (gauge basis, draw-in, crossing direction, no edging)", len(pt["uncertainties"]) >= 4)
d = pt["derived"]
check("counts x gauge: 144 sts at 16 per 10 cm = 90.0 cm; 18 columns 5.0 cm apart; crossing every 4.22 cm", d["width_cm"] == 90.0 and d["cable_column_pitch_cm"] == 5.0 and abs(d["crossing_period_cm"] - 4.222) < 1e-3)
meta = json.load(open(os.path.join(OUT, "ref_meta.json")))
check("reference: every cell, row and crossing of the CIR drawn, extent equals Product Truth", all(meta["validation"][k] for k in ("every_cell_drawn", "every_row_drawn", "crossings_drawn_equals_truth", "extent_matches_truth")))
check("reference: built from the frozen Product Truth digest and CIR fingerprint", meta["inputs"]["cir_fingerprint"] == pt["cir"]["fingerprint"])
check("reference: conventions declared (view, surface, crossing direction)", all(k in meta["conventions_DECLARED"] for k in ("view", "surface_rgb", "front_pair")))
st = json.load(open(os.path.join(OUT, "cable_identity_selftest.json")))
check("instrument bars are the a priori ones and each has a reason", set(st["bars"]) == set(G.BARS) and all(k in st["why"] for k in st["bars"]))
r = st["results"]
check("recorded: the reference passes identity and gauge, with and without the column map", r["reference"]["status"] == "PASS" and r["reference_without_column_map"]["status"] == "PASS")
check("recorded: at 2x scale identity passes and gauge fails", r["reference_2x_scale(gauge_must_fail)"]["identity"] == "PASS" and r["reference_2x_scale(gauge_must_fail)"]["gauge"]["status"] == "FAIL")
musts = [k for k in r if "must_fail" in k and "gauge" not in k]
check("recorded: rotated, plain, star and waffle controls all fail identity", len(musts) >= 4 and all(r[k]["identity"] == "FAIL" for k in musts), str([(k, r[k]["identity"]) for k in musts]))
# live re-run of a deterministic case
from PIL import Image
ref = np.array(Image.open(os.path.join(OUT, "ref_flatlay.png")).convert("L")).astype(float); mask = np.array(Image.open(os.path.join(OUT, "ref_mask.png"))) > 127
live = G.measure(ref, mask, meta["expected_px"]["cable_column_pitch"], meta["expected_px"]["crossing_period"])
check("live: the reference reads as cable at gauge now", live["status"] == "PASS", str(live.get("failed")))
check("live: a blank region is UNKNOWN, never PASS", G.measure(np.full((300, 300), 200.0), np.ones((300, 300), bool), 51.2, 43.2)["identity"] != "PASS")
check("live: the reference passes its own deterministic gate", G.deterministic(os.path.join(OUT, "ref_flatlay.png"))["status"] == "PASS")
# gate rules
det_pass = {"status": "PASS", "items": {"silhouette": {"status": "PASS"}}}
props_ok = {"texture": {"status": "PASS", "material": True}, "cable_column_count": {"status": "FAIL", "material": False}}
check("a non-material FAIL does not fail the verdict", G.verdict(det_pass, props_ok, {"a": "PASS"})["status"] == "PASS")
check("a material FAIL fails the verdict whatever the judge says", G.verdict(det_pass, {"texture": {"status": "FAIL", "material": True}}, {"a": "PASS"})["status"] == "FAIL")
check("a material UNKNOWN never passes", G.verdict(det_pass, {"texture": {"status": "UNKNOWN", "material": True}}, {"a": "PASS"})["status"] == "UNKNOWN")
check("a deterministic UNKNOWN never passes", G.verdict({"status": "UNKNOWN", "items": {"cable_gauge": {"status": "UNKNOWN"}}}, props_ok, {"a": "PASS"})["status"] == "UNKNOWN")
check("a judge FAIL fails the verdict", G.verdict(det_pass, props_ok, {"a": "FAIL"})["status"] == "FAIL")
check("expectations come from Product Truth (throw, rectangle, cabled, columns along the length, one colour, no edging, nothing extra)",
      G.EXPECT["product_type"][0] == {"blanket_or_throw"} and G.EXPECT["texture"][0] == {"cabled"} and G.EXPECT["colour_count"][0] == {1} and G.EXPECT["edging"][0] == {"none"} and G.EXPECT["extra_features"][0] == set())
check("an invented feature fails (pockets on a throw)", G.properties({"extra_features": ["pockets"]})["extra_features"]["status"] == "FAIL" and G.properties({"extra_features": ["none"]})["extra_features"]["status"] == "PASS")
check("the reader expectation follows the presentation: columns along the length on the whole throw, across the longer side in the folded view",
      G.expectations("ref")["cable_direction"][0] == {"along_the_length"} and (G.expectations("ref3")["cable_direction"][0] == {"across_the_width"} if os.path.exists(os.path.join(OUT, "ref3_meta.json")) else True))
for v in ("ref2", "ref3"):
    if os.path.exists(os.path.join(OUT, f"{v}_meta.json")):
        mv = json.load(open(os.path.join(OUT, f"{v}_meta.json")))
        check(f"{v}: re-states the frozen Product Truth (same digest, same cells drawn) and passes its own gate", mv["inputs"]["product_truth_sha256"] == meta["inputs"]["product_truth_sha256"] and mv["validation"]["every_cell_drawn"] and G.deterministic(os.path.join(OUT, f"{v}_flatlay.png"), v)["status"] == "PASS")
# manifest
if os.path.exists(os.path.join(OUT, "v1grad_manifest.json")):
    m = json.load(open(os.path.join(OUT, "v1grad_manifest.json")))
    check("the blind deterministic chain verdict is recorded with every check", "verdict" in m["blind_deterministic_chain"] and len(m["blind_deterministic_chain"]["checks"]) >= 10)
    check("frozen digests cover Product Truth, the reference set, the instrument record and the code", all(k in m["frozen_digests"] for k in ("product_truth.json", "ref_rgb", "ref_mask", "ref_normal", "cable_identity_selftest.json", "gate.py", "reference.py")))
    check("the generation package is the evidenced OpenAI route (gpt-image-1.5, input_fidelity high)", m["generation_package"]["model"] == "gpt-image-1.5" and m["generation_package"]["params"]["input_fidelity"] == "high")
    check("assets by stage name no finished-product image", m["assets_by_stage"]["finished_product_images"].startswith("NONE"))
    check("spend stayed under the ceiling", m["spent_usd"] <= m["cap_usd"], str(m["spent_usd"]))
    check("every run used the frozen reference or a frozen later version of it (digests recorded before use)",
          all(r["reference_sha256"]["rgb"] == (m["frozen_digests"]["ref_rgb"] if r.get("reference_version", "ref") == "ref" else m["reference_versions"][r["reference_version"]]["rgb"]) for r in m["runs"]))
    check("every external call records provider and model", all(c.get("provider") and c.get("model") for c in m["calls"]))
    if os.path.exists(os.path.join(OUT, "v1grad_gate.json")):
        gj = json.load(open(os.path.join(OUT, "v1grad_gate.json")))
        check("every successful draw was gated", all(f"oa15_hifi_{r['draw']}" in gj for r in m["runs"] if r.get("ok")))
        check("verdicts follow the rule on every candidate", all(G.verdict(r["deterministic"], r["properties"], r["judge"])["status"] == r["verdict"]["status"] for r in gj.values()))
        check("every candidate's properties are its stored readings judged by the current expectations (no reading changed)", all(G.properties(r["reader_answers"], None, r.get("reference_version", "ref"))[k]["status"] == v["status"] for r in gj.values() for k, v in r["properties"].items()))
        check("no candidate is certified unless every deterministic item, every material property and every judge item PASS", all((r["verdict"]["status"] == "PASS") == (r["deterministic"]["status"] == "PASS" and all(p["status"] == "PASS" for p in r["properties"].values() if p["material"]) and all(j == "PASS" for j in r["judge"].values())) for r in gj.values()))
tracked = subprocess.run(["git", "ls-files", "research/v1grad"], cwd=ROOT, capture_output=True, text=True).stdout.split()
check("nothing photographic or external is tracked under research/v1grad", not any(t.endswith((".jpg", ".jpeg", ".jp2", ".pdf")) for t in tracked))
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
