"""Commercial benchmark 1 regression tests, offline. Run: python research/bench1/test_bench1.py
Needs the pattern text in the scratchpad only for the parse tests; the rest reads out/."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gate as G

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

pt = json.load(open(os.path.join(OUT, "product_truth.json")))
check("every Product Truth fact cites a PDF page", all(isinstance(f.get("page"), int) and 1 <= f["page"] <= 12 for f in pt["facts"].values()))
check("the sample size is the pattern's stated sample (S)", pt["facts"]["sample_size"]["value"] == "S")
check("gauge parsed as 14.5 stitches x 9.5 rows per 10 cm", pt["facts"]["gauge"]["value"] == {"stitches_per_10cm": 14.5, "rows_per_10cm": 9.5, "in": "Crumpled Waffle Stitch pattern"})
check("all nine sizes parsed for every size vector", all(len(pt["facts"]["body"]["value"][k]) == 9 for k in ("foundation_ch", "stitches", "first_front_rows", "back_rows", "sleeve_opening_chains", "total_rows")))
check("every deterministic consistency check passed", all(c["status"] == "PASS" for c in pt["derived_cm"]["checks"]), str([c["check"] for c in pt["derived_cm"]["checks"] if c["status"] != "PASS"]))
check("the CIR built from the parse compiles", pt["cir"]["compile"]["ok"], str(pt["cir"]["compile"]["errors"][:2]))
check("the independent earlier encoding (cir.benchmarks) agrees with the parse on every count", pt["cross_check_vs_cir_benchmarks"]["agree"], str(pt["cross_check_vs_cir_benchmarks"]["pairs"]))
check("the body texture is measured as textured and checkered (alternating loop targets)", pt["cir"]["texture_signature"]["body"]["textured"] and pt["cir"]["texture_signature"]["body"]["surface"] == "checkered")
check("assumptions are declared, not hidden", "pocket_placement" in pt["derived_cm"]["assumed"] and "colour_rgb" in pt["derived_cm"]["assumed"])
joins = pt["cir"]["assembly"]["joins"]
check("the sleeve-to-opening join is sound or indeterminate under the derived chain gauge, never mismatched", all(j["verdict"] != "mismatched" for j in joins), str([(j["a"], j["b"], j["verdict"]) for j in joins]))
for v in ("ref", "ref2", "ref3"):
    meta = json.load(open(os.path.join(OUT, f"{v}_meta.json")))
    check(f"{v}: every region of the finished product is present in the reference", all(meta["region_pixels"][k] > 0 for k in meta["regions"]), str({k: n for k, n in meta["region_pixels"].items() if n == 0}))
    check(f"{v}: the reference's dimensions are Product Truth's", all(abs(meta["dimensions_cm"][k] - pt["derived_cm"][k]) < 1e-6 for k in meta["dimensions_cm"]))
    check(f"{v}: two pockets, two sleeves, two cuffs", all(meta["region_pixels"][f"{p}_left"] == meta["region_pixels"][f"{p}_right"] > 0 for p in ("pocket", "sleeve", "cuff")))
    check(f"{v}: the assumed pocket placement is declared in the reference metadata", "pocket_placement_ASSUMED" in meta["layout"])
# gate logic
det_pass = {"status": "PASS", "items": {"silhouette": {"status": "PASS"}}}
props_ok = {"pocket_count": {"status": "PASS", "material": True}, "body_ridge_direction": {"status": "FAIL", "material": False}}
check("a non-material FAIL does not fail the verdict", G.verdict(det_pass, props_ok, {"a": "PASS"})["status"] == "PASS")
check("a material FAIL fails the verdict whatever the judge says", G.verdict(det_pass, {"pocket_count": {"status": "FAIL", "material": True}}, {"a": "PASS"})["status"] == "FAIL")
check("a material UNKNOWN never passes", G.verdict(det_pass, {"pocket_count": {"status": "UNKNOWN", "material": True}}, {"a": "PASS"})["status"] == "UNKNOWN")
check("a judge FAIL fails the verdict", G.verdict(det_pass, props_ok, {"a": "FAIL"})["status"] == "FAIL")
check("a deterministic FAIL is material", G.verdict({"status": "FAIL", "items": {"silhouette": {"status": "FAIL"}}}, props_ok, {"a": "PASS"})["status"] == "FAIL")
check("the reader's expectations come from Product Truth (cardigan, open, no closure, 2 hip pockets, long sleeves, one colour)",
      G.EXPECT["product_type"][0] == {"cardigan"} and G.EXPECT["closure_count"][0] == {0} and G.EXPECT["pocket_count"][0] == {2} and G.EXPECT["sleeve_length"][0] == {"long"} and G.EXPECT["colour_count"][0] == {1})
# bookkeeping
if os.path.exists(os.path.join(OUT, "bench1_manifest.json")):
    m = json.load(open(os.path.join(OUT, "bench1_manifest.json"))); g = json.load(open(os.path.join(OUT, "bench1_gate.json")))
    check("spend stayed under the ceiling", m["spent_usd"] <= m["cap_usd"], str(m["spent_usd"]))
    ok_runs = [r for r in m["runs"] if r.get("ok")]
    check("every successful draw was gated", all(f"{r['mode']}_{r['draw']}" in g for r in ok_runs))
    check("every gated candidate records its reference and prompt digests and the reader's answers", all("output_sha256" in r and "reader_answers" in r for r in g.values()))
    check("verdicts follow the rule on every candidate", all(G.verdict(r["deterministic"], r["properties"], r["judge"])["status"] == r["verdict"]["status"] for r in g.values()))
    sellers = json.load(open(os.path.join(OUT, "seller_photos.json")))
    check("all four seller photographs were read by the same reader", len(sellers) == 4)
# nothing of the seller's is in the repository
tracked = subprocess.run(["git", "ls-files", "research/bench1"], cwd=ROOT, capture_output=True, text=True).stdout.split()
check("no PDF, pattern text or seller photograph is tracked under research/bench1 (the readers' JSON answers are derived data and are)", not any(t.endswith((".pdf", "pattern.txt", ".jpg", ".jpeg")) for t in tracked), str([t for t in tracked if t.endswith((".pdf", ".jpg", ".jpeg", "pattern.txt"))]))
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
