"""E5 regression tests, offline: the frozen package is what it says, every draw was conditioned
on it, certification is strict, spend stayed under the ceiling, and the baseline comparison
is like for like. Run: python research/e5/test_e5.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
import frozen as F

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

digests = F.verify()
check("every frozen input still has its recorded digest", len(digests) == len(F.FROZEN))
man = json.load(open(os.path.join(OUT, "e5_manifest.json"))); val = json.load(open(os.path.join(OUT, "e5_validation.json")))
ok_runs = [r for r in man["runs"] if r.get("ok")]
check("the manifest froze the same digests the package has now", man["frozen"] == digests, str({k: (man["frozen"].get(k, "")[:8], v[:8]) for k, v in digests.items() if man["frozen"].get(k) != v}))
check("every draw names the frozen certified geometry", all(r["geometry_sha256"] == F.GEOMETRY_SHA256 for r in man["runs"]))
ref_ok = all(all(r["conditioning_sha256"].get(k) == F.FROZEN[k][1] for k in r["refs"] if k in F.FROZEN) for r in man["runs"])
check("every draw was conditioned on the frozen reference, mask and normals (by digest)", ref_ok)
check("every draw records provider, model, endpoint or parameters, prompt digest and output digest", all(all(k in r for k in ("provider", "model", "params", "prompt_sha256")) and ("output_sha256" in r or not r.get("ok")) for r in man["runs"]))
check("every successful draw's output digest matches the file on disk", all(F.sha256(r["path"]) == r["output_sha256"] for r in ok_runs))
check("no mode's prompt names a stitch family, count or construction", not any(w in man["modes"][m]["prompt"].lower() for m in man["modes"] for w in ("single crochet", "double crochet", "half double", " sc ", "hdc", "five stitches", "5 stitches", "five rows", "5 rows", "stitches per row")))
check("spend stayed under the ceiling", man["spent_usd"] <= man["cap_usd"], str(man["spent_usd"]))
check("the manifest's spend is the sum of its draws and the judge", abs(man["spent_usd"] - (sum(r.get("usd", 0) for r in man["runs"]) + man.get("judge_usd", 0))) < 1e-3)
res = val["results"]
check("every successful draw was validated", all(f"{r['mode']}_{r['draw']}" in res for r in ok_runs), str([f"{r['mode']}_{r['draw']}" for r in ok_runs if f"{r['mode']}_{r['draw']}" not in res]))
check("certified means structural PASS and every judge item PASS, nothing weaker",
      all(r["certified"] == (r["structural"] == "PASS" and all(v == "PASS" for v in r["judge"].values())) for r in res.values()))
check("an UNKNOWN anywhere in the structure never certifies", all(not r["certified"] for r in res.values() if r["structural"] == "UNKNOWN" or "UNKNOWN" in [i["status"] for i in r["global"]["items"].values()]))
check("a judge UNKNOWN never certifies", all(not r["certified"] for r in res.values() if "UNKNOWN" in r["judge"].values()))
check("every validated image carries the E4-aligner verdict beside the E5 one", all("structural_e4_aligner" in r for r in res.values()))
check("the E5 aligner never lowers a bar: the same thresholds are read from the E3/E4 criteria", val["results"] and all(r["local"]["bar"] == 0.6 for r in res.values()))
y = val["yield_per_mode"]
check("yield counts add up per mode", all(y[m]["draws"] == sum(1 for r in res.values() if r["mode"] == m) and y[m]["certified"] == sum(1 for r in res.values() if r["mode"] == m and r["certified"]) for m in y))
check("no mode reports consecutive certified draws (the brief's bar for a repeatable route)",
      not any(all(res.get(f"{m}_{i}", {}).get("certified") and res.get(f"{m}_{i+1}", {}).get("certified") for _ in [0]) for m in y for i in range(1, y[m]["draws"])))
base = json.load(open(os.path.join(OUT, "e4_baseline_under_e5_instrument.json")))
check("the E4 baseline was re-measured under both aligners on the same view", len(base["rows"]) == 4 and all("v1" in r and "v2" in r for r in base["rows"]))
check("E4's certified image stays certified under the E5 aligner", next(r for r in base["rows"] if r["image"] == "sc_camera_e4")["certified_v2"])
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
