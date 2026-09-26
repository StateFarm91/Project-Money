"""E4 validation: locally (every testable projected stitch), then globally, then the judge.

Order is the brief's: the instrument must have validated itself on the reference; each visible
stitch is tested in the photograph; then silhouette, proportions, colour, row placement,
construction cues and macro deformation; the independent photographic judge runs last and
only its verdict is reported beside a structural verdict it cannot override.
"""
import json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src")); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "e3")); sys.path.insert(0, HERE)
from correspond import yarn_mask, CRITERIA as GC
import correspond as C
import project as P
D = os.path.join(os.path.dirname(HERE), "d", "out")
W = P.W


def aligned_masks(kind, view, gen_path):
    ref_mask = np.array(Image.open(os.path.join(OUT, f"{kind}_{view}_mask.png"))) > 127
    gen = Image.open(gen_path).convert("RGB").resize((W, W), Image.LANCZOS)
    gmask, gh = yarn_mask(gen)
    from scipy.ndimage import zoom
    ys, xs = np.nonzero(gmask); rys, rxs = np.nonzero(ref_mask)
    if len(ys) < 0.01 * len(rys):
        # no yarn region to align: nothing corresponds, and the answer is FAIL everywhere,
        # not a scale of several hundred (a blank frame once asked zoom() for 1.3 TiB)
        return ref_mask, np.zeros_like(ref_mask), {"scale": None, "shift_px": None, "why": "no yarn region found in the photograph"}, gh, gmask
    s = np.sqrt(len(rys) / len(ys)); z = zoom(gmask.astype(float), s, order=1) > 0.5
    zys, zxs = np.nonzero(z); dy, dx = rys.mean() - zys.mean(), rxs.mean() - zxs.mean()
    out = np.zeros_like(ref_mask); h, w = z.shape; sy0, sx0 = int(round(dy)), int(round(dx))
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, W), min(sx0 + w, W)
    out[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    return ref_mask, out, {"scale": float(s), "shift_px": [float(dy), float(dx)]}, gh, gmask


def local(kind, view, gen_path):
    man = json.load(open(os.path.join(OUT, f"{kind}_{view}_manifest.json")))
    sv = man.get("self_validation", {})
    if not sv.get("valid"):
        return {"status": "UNKNOWN", "why": "the instrument did not validate itself on the reference; it does not judge", "self_validation": sv}
    ref_mask, gen_al, align, _, _ = aligned_masks(kind, view, gen_path)
    bar = man["criteria"]["stitch_present_iou"]["value"]
    per = {}
    for s in man["stitches"]:
        if not s["testable"]:
            per[s["id"]] = {"status": "UNKNOWN", "why": "not visible enough at this camera", "visible_fraction": s["visible_fraction"]}; continue
        iou = P.region_iou(gen_al, ref_mask, s["bbox_px"])
        per[s["id"]] = {"status": "PASS" if iou >= bar else "FAIL", "iou": round(iou, 3), "reference_iou": round(sv["per_stitch_reference_iou"].get(s["id"], 0.0), 3),
                        "row": s["row"], "position": s["position"], "family": s["family"]}
    tested = [v for v in per.values() if v["status"] != "UNKNOWN"]
    failed = [k for k, v in per.items() if v["status"] == "FAIL"]
    return {"status": "FAIL" if failed else "PASS", "tested": len(tested), "untestable": len(per) - len(tested), "failed_stitches": failed,
            "mean_iou": float(np.mean([v["iou"] for v in tested])) if tested else None, "alignment": align, "per_stitch": per, "bar": bar}


def global_props(kind, view, gen_path):
    num = C.numeric(kind, view, gen_path) if False else None
    # E3's numeric measures, against the E4 masks (the mask directory differs); reuse the pieces
    ref_mask, gen_al, align, gh, gmask = aligned_masks(kind, view, gen_path)
    if align["scale"] is None:
        why = {"why": align["why"]}
        names = ("silhouette", "major_proportions", "colour_regions", "row_placement", "structure_placement", "construction_cues", "macro_deformation", "handedness")
        return {"status": "FAIL", "items": {k: {"status": ("UNKNOWN" if k == "handedness" else "FAIL"), "evidence": why} for k in names}}
    iou_al = float((gen_al & ref_mask).sum() / max((gen_al | ref_mask).sum(), 1))
    def bbox(m):
        ys, xs = np.nonzero(m); return (xs.min(), ys.min(), xs.max(), ys.max())
    rb, gb = bbox(ref_mask), bbox(gmask); r_asp = (rb[3] - rb[1]) / max(rb[2] - rb[0], 1); g_asp = (gb[3] - gb[1]) / max(gb[2] - gb[0], 1)
    drift = abs(g_asp - r_asp) / r_asp
    from scipy.ndimage import gaussian_filter, sobel, zoom
    ref_rgb = Image.open(os.path.join(D, f"{kind}_draped_presentation3_{view}.png")).convert("RGB")
    gen = Image.open(gen_path).convert("RGB").resize((W, W), Image.LANCZOS)
    def struct(im):
        g = np.array(im.convert("L")).astype(float); return gaussian_filter(np.hypot(sobel(g, 0), sobel(g, 1)), 4.0)
    a, b = struct(ref_rgb), struct(gen); b_al = zoom(b, align["scale"], order=1) if align["scale"] else np.zeros_like(b)
    a_mirror = a[:, ::-1]
    canvas = np.zeros_like(a); h, w = b_al.shape; sy0, sx0 = (int(round(align["shift_px"][0])), int(round(align["shift_px"][1]))) if align["shift_px"] else (0, 0)
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, W), min(sx0 + w, W); canvas[y0:y1, x0:x1] = b_al[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    sel = gaussian_filter(ref_mask.astype(float), 6.0) > 0.5
    av, bv = a[sel] - a[sel].mean(), canvas[sel] - canvas[sel].mean(); ncc = float((av * bv).sum() / max(np.sqrt((av * av).sum() * (bv * bv).sum()), 1e-9))
    # handedness: the same structure map against the MIRRORED reference. The per-stitch
    # presence test cannot tell a mirror image of a near-symmetric swatch from the swatch
    # (research/e4/test_e4.py proves it), so the certified orientation must explain the
    # photograph's structure at least twice as well as its mirror does. On the four
    # references themselves the ratio is 4.2-9.5; on unrelated textures both are ~0.
    sel_m = sel[:, ::-1]; am, bm = a_mirror[sel_m] - a_mirror[sel_m].mean(), canvas[sel_m] - canvas[sel_m].mean()
    ncc_mirror = float((am * bm).sum() / max(np.sqrt((am * am).sum() * (bm * bm).sum()), 1e-9))
    hand = ("UNKNOWN" if max(ncc, ncc_mirror) < 0.10 else ("PASS" if ncc >= 2.0 * ncc_mirror else "FAIL"))
    ang = np.deg2rad(gh[gmask]); R = np.hypot(np.cos(ang).mean(), np.sin(ang).mean()); hue_spread = float(np.degrees(np.sqrt(-2 * np.log(max(R, 1e-9)))))
    # row placement: each certified row's projected centroid band must hold yarn in the photograph
    man = json.load(open(os.path.join(OUT, f"{kind}_{view}_manifest.json")))
    rows = {}
    for s in man["stitches"]:
        if s["testable"]: rows.setdefault(s["row"], []).append(s["bbox_px"])
    row_res = {}
    for r, boxes in rows.items():
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes); x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        row_res[r] = round(P.region_iou(gen_al, ref_mask, [x0, y0, x1, y1]), 3)
    items = {
        "silhouette": ("PASS" if iou_al >= GC["silhouette_iou"][0] else "FAIL", {"iou_aligned": iou_al, "alignment": align}),
        "major_proportions": ("PASS" if drift <= GC["aspect_drift"][0] else "FAIL", {"aspect_ref": float(r_asp), "aspect_gen": float(g_asp), "drift": float(drift)}),
        "colour_regions": ("PASS" if hue_spread <= GC["hue_spread_deg"][0] else "FAIL", {"hue_spread_gen_deg": hue_spread}),
        "row_placement": ("PASS" if row_res and min(row_res.values()) >= GC["silhouette_iou"][0] * 0.9 else "FAIL", {"per_row_iou": row_res, "bar": round(GC["silhouette_iou"][0] * 0.9, 2)}),
        "structure_placement": ("PASS" if ncc >= GC["structure_ncc"][0] else "FAIL", {"ncc_aligned": ncc}),
        "construction_cues": ("PASS" if iou_al >= GC["silhouette_iou"][0] and ncc >= GC["structure_ncc"][0] else "FAIL",
                              {"basis": "the yarn's two real ends and the row edges are part of the silhouette and structure maps; no separate blind reading", "iou": iou_al, "ncc": ncc}),
        "macro_deformation": ("PASS" if iou_al >= GC["silhouette_iou"][0] and ncc >= GC["structure_ncc"][0] else "FAIL", {"iou": iou_al, "ncc": ncc}),
        "handedness": (hand, {"ncc_certified": ncc, "ncc_mirrored": ncc_mirror, "rule": "CHOSEN: certified >= 2 x mirrored; UNKNOWN when neither reaches 0.10"}),
    }
    statuses = [s for s, _ in items.values()]
    return {"status": "FAIL" if "FAIL" in statuses else ("UNKNOWN" if "UNKNOWN" in statuses else "PASS"), "items": {k: {"status": s, "evidence": e} for k, (s, e) in items.items()}}


def main(tag="e4"):
    man = json.load(open(os.path.join(OUT, f"{tag}_manifest.json")))
    from brambleloop.visual import d_judge as DJ
    results = []; judge_cost = 0.0
    for run in man["runs"]:
        if not run.get("ok"): continue
        kind, view = run["kind"], run["view"]
        loc = local(kind, view, run["path"]); glob = global_props(kind, view, run["path"])
        structural = "FAIL" if "FAIL" in (loc["status"], glob["status"]) else ("UNKNOWN" if "UNKNOWN" in (loc["status"], glob["status"]) else "PASS")
        r = {"kind": kind, "view": view, "draw": run.get("draw"), "generated": run["path"], "output_sha256": run["output_sha256"], "geometry_sha256": run["geometry_sha256"],
             "conditioning_sha256": run["conditioning_sha256"], "local": loc, "global": glob, "structural": structural}
        suffix = os.path.splitext(os.path.basename(run["path"]))[0].replace(f"{kind}_{view}_", "")
        cache = os.path.join(OUT, f"judge_{kind}_{view}_{suffix}.json")
        j = json.load(open(cache)) if os.path.exists(cache) else None
        if j and j["views"][0].get("image_sha256") == run["output_sha256"]:
            r["judge_reused"] = True  # the same bytes were judged already; no second spend
        else:
            j = DJ.judge_views([run["path"]]); judge_cost += j["total_cost_usd"]
        r["judge"] = {k: v["status"] for k, v in j["items"].items()}; r["judge_notes"] = j["views"][0]["reading"].get("notes", ""); r["judge_response_id"] = j["views"][0]["response_id"]
        json.dump(j, open(cache, "w"), indent=1)
        results.append(r)
        print(f"{kind} {view}{' #' + str(run['draw']) if run.get('draw') else ''}: structural {structural} | local {loc['status']} ({loc.get('tested')} tested, failed {loc.get('failed_stitches')}, mean IoU {loc.get('mean_iou') and round(loc['mean_iou'], 3)}) | global {glob['status']} { {k: v['status'] for k, v in glob['items'].items()} }")
        print("   judge:", r["judge"], "|", r["judge_notes"][:160])
    json.dump({"results": results, "judge_cost_usd": round(judge_cost, 4)}, open(os.path.join(OUT, f"{tag}_validation.json"), "w"), indent=1, default=str)
    print("judge spend US$%.4f" % judge_cost)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "e4")
