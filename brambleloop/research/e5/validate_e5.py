"""E5 validation: every drawn candidate through the unchanged E4 instrument (per-stitch, then
global including handedness) and the unchanged independent D judge, then yield per mode.

A draw is CERTIFIED only when the structural verdict is PASS and every judge item is PASS.
UNKNOWN never counts. Judge readings are cached by image digest so re-running costs nothing.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "research", "e4")); sys.path.insert(0, os.path.join(ROOT, "research", "e3")); sys.path.insert(0, HERE)
import frozen as F
import validate_e4 as V
OUT = os.path.join(HERE, "out"); MANIFEST = os.path.join(OUT, "e5_manifest.json")


def structural_verdict(path, refine):
    loc = V.local("sc", "camera", path, refine=refine); glob = V.global_props("sc", "camera", path, refine=refine)
    return loc, glob, ("FAIL" if "FAIL" in (loc["status"], glob["status"]) else ("UNKNOWN" if "UNKNOWN" in (loc["status"], glob["status"]) else "PASS"))


def validate_one(path, sha):
    # E5's instrument is the E4 instrument with the silhouette-refined alignment (see
    # validate_e4.aligned_masks); the E4 aligner's verdict is kept beside it on every image.
    loc, glob, structural = structural_verdict(path, refine=True)
    loc1, glob1, structural_v1 = structural_verdict(path, refine=False)
    from brambleloop.visual import d_judge as DJ
    cache = os.path.join(OUT, f"judge_{os.path.splitext(os.path.basename(path))[0]}.json"); cost = 0.0
    j = json.load(open(cache)) if os.path.exists(cache) else None
    if not (j and j["views"][0].get("image_sha256") == sha):
        j = DJ.judge_views([path]); cost = j["total_cost_usd"]; json.dump(j, open(cache, "w"), indent=1)
    judge = {k: v["status"] for k, v in j["items"].items()}
    return {"local": loc, "global": glob, "structural": structural, "structural_e4_aligner": structural_v1,
            "global_e4_aligner": {k: v["status"] for k, v in glob1["items"].items()}, "local_e4_aligner": {"status": loc1["status"], "mean_iou": loc1.get("mean_iou")},
            "judge": judge, "judge_all_pass": all(v == "PASS" for v in judge.values()),
            "judge_notes": j["views"][0]["reading"].get("notes", ""), "judge_response_id": j["views"][0]["response_id"], "judge_usd": cost,
            "certified": structural == "PASS" and all(v == "PASS" for v in judge.values())}


def main():
    man = json.load(open(MANIFEST)); F.verify()
    results = json.load(open(os.path.join(OUT, "e5_validation.json"))) if os.path.exists(os.path.join(OUT, "e5_validation.json")) else {"results": {}}
    judge_spend = 0.0
    for run in man["runs"]:
        if not run.get("ok"): continue
        key = f"{run['mode']}_{run['draw']}"
        if key in results["results"] and results["results"][key]["output_sha256"] == run["output_sha256"] and "structural_e4_aligner" in results["results"][key]: continue
        v = validate_one(run["path"], run["output_sha256"]); judge_spend += v["judge_usd"]
        results["results"][key] = {"mode": run["mode"], "draw": run["draw"], "output_sha256": run["output_sha256"], "usd_generation": run.get("usd", 0.0), "seconds": run.get("seconds"), **v}
        g = v["global"]["items"]
        print(f"{key}: structural {v['structural']} (local {v['local']['status']} {v['local'].get('tested')} tested min IoU {min([s['iou'] for s in v['local']['per_stitch'].values() if 'iou' in s] or [0]):.2f}; "
              f"silhouette {g['silhouette']['evidence'].get('iou_aligned', 0):.3f} drift {g['major_proportions']['evidence'].get('drift', 0):.3f} ncc {g['structure_placement']['evidence'].get('ncc_aligned', 0):.3f} hand {g['handedness']['status']}) | judge {sum(1 for x in v['judge'].values() if x == 'PASS')}/7 | {'CERTIFIED' if v['certified'] else 'no'} | {v['judge_notes'][:100]}")
    man["judge_usd"] = round(man.get("judge_usd", 0.0) + judge_spend, 4)
    man["spent_usd"] = round(sum(r.get("usd", 0.0) for r in man["runs"]) + man["judge_usd"], 4)
    json.dump(man, open(MANIFEST, "w"), indent=1)
    # yields per mode
    per = {}
    for key, r in results["results"].items():
        p = per.setdefault(r["mode"], {"draws": 0, "structural_pass": 0, "judge_pass": 0, "certified": 0, "structural_pass_e4_aligner": 0, "certified_e4_aligner": 0, "usd_generation": 0.0, "usd_judge": 0.0, "seconds": []})
        p["draws"] += 1; p["structural_pass"] += r["structural"] == "PASS"; p["judge_pass"] += r["judge_all_pass"]; p["certified"] += r["certified"]
        p["structural_pass_e4_aligner"] += r["structural_e4_aligner"] == "PASS"; p["certified_e4_aligner"] += (r["structural_e4_aligner"] == "PASS" and r["judge_all_pass"])
        p["usd_generation"] += r["usd_generation"]; p["usd_judge"] += r["judge_usd"]; p["seconds"].append(r["seconds"])
    failed = [r for r in man["runs"] if not r.get("ok")]
    for m, p in per.items():
        n = p["draws"]; p["structural_rate"] = round(p["structural_pass"] / n, 3); p["judge_rate"] = round(p["judge_pass"] / n, 3); p["certified_rate"] = round(p["certified"] / n, 3)
        p["usd_per_draw"] = round((p["usd_generation"] + p["usd_judge"]) / n, 4)
        p["usd_per_certified"] = round((p["usd_generation"] + p["usd_judge"]) / p["certified"], 4) if p["certified"] else None
        p["mean_seconds"] = round(sum(p["seconds"]) / n, 1); del p["seconds"]
    results["yield_per_mode"] = per; results["refused_or_failed_draws"] = [{k: r.get(k) for k in ("mode", "draw", "error")} for r in failed]
    results["spend_usd"] = {"generation": round(sum(r.get("usd", 0.0) for r in man["runs"]), 4), "judge": man["judge_usd"], "total": man["spent_usd"], "cap": man["cap_usd"]}
    results["e4_baseline"] = {"certified_rate": "1/14 (sc camera 1/6)", "sha256": F.FROZEN["e4_baseline"][1]}
    json.dump(results, open(os.path.join(OUT, "e5_validation.json"), "w"), indent=1, default=str)
    print("\nyield per mode:")
    for m, p in per.items():
        print(f"  {m:14s} draws {p['draws']} structural {p['structural_pass']} (E4 aligner {p['structural_pass_e4_aligner']}) judge {p['judge_pass']} certified {p['certified']} (E4 aligner {p['certified_e4_aligner']}) | US$/draw {p['usd_per_draw']} US$/certified {p['usd_per_certified']} | {p['mean_seconds']} s")
    print(f"spend: {results['spend_usd']}")


if __name__ == "__main__":
    main()
