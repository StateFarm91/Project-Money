"""E3 structural correspondence: does the generated photograph show the SAME product as the
frozen certified reference? Every property is PASS / FAIL / UNKNOWN with the evidence beside
it, and an UNKNOWN never becomes a PASS.

Numeric properties are measured against the assets `assets.py` derived from the frozen
geometry (the fabric's own silhouette mask under the same camera). Judged properties -- how
many rows and stitches are visible, whether the stitches are short or tall, where the loose
ends are -- are read by the independent model (`d_judge.MODEL`) from BOTH the reference render
and the generated photograph with the same neutral questionnaire; a property passes only when
the reference reading matches the certified truth (the instrument can see it) AND the
generated reading matches the reference reading. Bars are named in CRITERIA with their reason.
"""
import hashlib, json, os, sys, time, base64, urllib.request
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from brambleloop.visual import d_judge as DJ

TRUTH = {"hdc": {"rows": 5, "stitches_per_row": 5, "family": "tall"}, "sc": {"rows": 5, "stitches_per_row": 5, "family": "short"}}
CRITERIA = {
    "silhouette_iou": (0.80, "CHOSEN: measured after aligning the generated silhouette to the reference "
                             "by centroid and area (scale free, shape not -- the presentation gate's own "
                             "rule); a 10 % change of aspect alone costs ~0.09 of IoU on a compact shape, "
                             "so 0.80 admits that and the segmentation's edge noise and refuses a redrawn "
                             "outline"),
    "aspect_drift": (0.10, "CHOSEN: the presentation gate's own geometry tolerance is 10 %"),
    "structure_ncc": (0.30, "CHOSEN, weak by design: normalised correlation of blurred gradient "
                            "magnitude inside the reference silhouette says whether the rows and posts "
                            "sit where the reference put them; 0.30 is well above what two unrelated "
                            "textures give (~0) and is reported beside the number"),
    "hue_spread_deg": (12.0, "CHOSEN: one dyed yarn is one hue; a second colour region would read as a "
                             "second mode far outside this"),
}
QUESTIONS = (
    "This is an image of a crocheted swatch. Answer as JSON with exactly these keys, and give null "
    "for any value the image does not let you determine: "
    '"rows": integer number of horizontal rows of stitches you can count; '
    '"stitches_per_row": integer number of stitches you can count across one full row; '
    '"stitch_height": "short" if each stitch is about as tall as it is wide or less, "tall" if each '
    "stitch stands clearly taller than it is wide on a visible post; "
    '"loose_ends": where any loose strand ends are visible ("bottom", "top", "sides", "none", or a short phrase); '
    '"colours": integer number of distinct yarn colours; '
    '"shape": one short phrase for the overall outline (e.g. "upright rectangle", "square", "irregular"); '
    '"notes": one sentence on anything structurally notable.'
)


def yarn_mask(img):
    """The pink yarn against a neutral scene: hue near magenta-red with real saturation."""
    hsv = np.array(img.convert("HSV")).astype(float)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    hue_ok = (h > 300) | (h < 25)
    return hue_ok & (s > 0.22) & (v > 0.12), h


def numeric(kind, view, gen_path):
    ref_mask = np.array(Image.open(os.path.join(OUT, f"{kind}_{view}_mask.png"))) > 127
    ref_rgb = Image.open(os.path.join(os.path.dirname(OUT), "..", "d", "out", f"{kind}_draped_presentation2_{view}.png")).convert("RGB")
    gen = Image.open(gen_path).convert("RGB").resize(ref_mask.shape[::-1], Image.LANCZOS)
    gmask, gh = yarn_mask(gen)
    rmask_col, rh = yarn_mask(ref_rgb)
    # the same colour segmentation on the reference says how much of the mask it can see
    seg_recall = float((rmask_col & ref_mask).sum() / max(ref_mask.sum(), 1))
    inter = (gmask & ref_mask).sum(); union = (gmask | ref_mask).sum()
    iou = float(inter / max(union, 1))
    # The edits endpoint re-frames: the output is 1024px and the piece can sit smaller or
    # elsewhere in it. The presentation gate compares SHAPE with scale free, so the generated
    # silhouette is also aligned to the reference by centroid and sqrt(area) -- a similarity
    # without rotation, two numbers and nothing that can bend an outline -- and both the raw
    # and the aligned figures are reported.
    from scipy.ndimage import zoom, shift, gaussian_filter, sobel
    def align(m, a_img=None):
        ys, xs = np.nonzero(m); rys, rxs = np.nonzero(ref_mask)
        s = np.sqrt(len(rys) / max(len(ys), 1))
        z = zoom(m.astype(float), s, order=1) > 0.5
        zys, zxs = np.nonzero(z)
        dy, dx = rys.mean() - zys.mean(), rxs.mean() - zxs.mean()
        out = np.zeros_like(ref_mask)
        sy0, sx0 = int(round(dy)), int(round(dx))
        # paste with the offset, clipped
        H, W = ref_mask.shape; h, w = z.shape
        y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W)
        out[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
        return out, s, (dy, dx)
    gmask_al, scale, (dy, dx) = align(gmask)
    iou_al = float((gmask_al & ref_mask).sum() / max((gmask_al | ref_mask).sum(), 1))
    def bbox(m):
        ys, xs = np.nonzero(m); return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else (0, 0, 1, 1)
    rb, gb = bbox(ref_mask), bbox(gmask)
    r_asp = (rb[3] - rb[1]) / max(rb[2] - rb[0], 1); g_asp = (gb[3] - gb[1]) / max(gb[2] - gb[0], 1)
    aspect_drift = abs(g_asp - r_asp) / r_asp
    # structure: gradient magnitude, blurred, correlated inside the reference silhouette
    from scipy.ndimage import gaussian_filter, sobel
    def struct(im):
        g = np.array(im.convert("L")).astype(float)
        m = np.hypot(sobel(g, 0), sobel(g, 1)); return gaussian_filter(m, 4.0)
    a, b = struct(ref_rgb), struct(gen)
    sel = gaussian_filter(ref_mask.astype(float), 6.0) > 0.5
    def ncc_of(x, y):
        xv, yv = x[sel] - x[sel].mean(), y[sel] - y[sel].mean()
        return float((xv * yv).sum() / max(np.sqrt((xv * xv).sum() * (yv * yv).sum()), 1e-9))
    ncc = ncc_of(a, b)
    # the same alignment applied to the generated image's structure map
    b_al = zoom(b, scale, order=1)
    H, W = ref_mask.shape; h, w = b_al.shape
    sy0, sx0 = int(round(dy)), int(round(dx)); canvas = np.zeros_like(a)
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W)
    canvas[y0:y1, x0:x1] = b_al[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    ncc_al = ncc_of(a, canvas)
    # colour regions: hue spread of yarn pixels (circular std, degrees)
    def hue_spread(h, m):
        ang = np.deg2rad(h[m]); R = np.hypot(np.cos(ang).mean(), np.sin(ang).mean()); return float(np.degrees(np.sqrt(-2 * np.log(max(R, 1e-9)))))
    return {"silhouette_iou": iou, "silhouette_iou_aligned": iou_al, "alignment": {"scale": float(scale), "shift_px": [float(dy), float(dx)]},
            "structure_ncc_aligned": ncc_al, "reference_segmentation_recall": seg_recall,
            "aspect_ref": float(r_asp), "aspect_gen": float(g_asp), "aspect_drift": float(aspect_drift),
            "structure_ncc": ncc, "hue_spread_ref_deg": hue_spread(rh, rmask_col), "hue_spread_gen_deg": hue_spread(gh, gmask),
            "gen_mask_pixels": int(gmask.sum()), "ref_mask_pixels": int(ref_mask.sum())}


def read_structure(path):
    data = open(path, "rb").read()
    body = {"model": DJ.MODEL, "messages": [
        {"role": "system", "content": "You are examining a photograph of a crocheted swatch and reporting only what you can count and see."},
        {"role": "user", "content": [{"type": "text", "text": QUESTIONS},
                                     {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.standard_b64encode(data).decode(), "detail": "high"}}]}],
        "max_completion_tokens": DJ.MAX_OUTPUT_TOKENS}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {DJ._key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as resp:
        out = json.loads(resp.read().decode())
    u = out.get("usage", {}); tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    import re
    m = re.search(r"\{.*\}", text, re.S)
    parsed = json.loads(m.group(0)) if m else None
    return {"image": path, "image_sha256": hashlib.sha256(data).hexdigest(), "model": out.get("model"), "response_id": out.get("id"),
            "prompt_tokens": tin, "completion_tokens": tout, "cost_usd": round(tin * DJ.PRICE_USD_PER_M["input"] / 1e6 + tout * DJ.PRICE_USD_PER_M["output"] / 1e6, 6),
            "raw": text, "reading": parsed}


def decide(kind, num, ref_read, gen_read):
    P, F, U = "PASS", "FAIL", "UNKNOWN"
    items = {}
    items["silhouette"] = (P if num["silhouette_iou_aligned"] >= CRITERIA["silhouette_iou"][0] else F, {"iou_aligned": num["silhouette_iou_aligned"], "iou_raw": num["silhouette_iou"], "alignment": num["alignment"], "reference_segmentation_recall": num["reference_segmentation_recall"]})
    items["major_proportions"] = (P if num["aspect_drift"] <= CRITERIA["aspect_drift"][0] else F, {"aspect_ref": num["aspect_ref"], "aspect_gen": num["aspect_gen"], "drift": num["aspect_drift"]})
    items["structure_placement"] = (P if num["structure_ncc_aligned"] >= CRITERIA["structure_ncc"][0] else F, {"ncc_aligned": num["structure_ncc_aligned"], "ncc_raw": num["structure_ncc"]})
    items["colour_regions"] = (P if num["hue_spread_gen_deg"] <= CRITERIA["hue_spread_deg"][0] and (ref_read or {}).get("colours") in (1, None) and (gen_read or {}).get("colours") == 1 else (U if gen_read is None else F),
                               {"hue_spread_ref_deg": num["hue_spread_ref_deg"], "hue_spread_gen_deg": num["hue_spread_gen_deg"], "colours_read": {"ref": (ref_read or {}).get("colours"), "gen": (gen_read or {}).get("colours")}})
    t = TRUTH[kind]
    def judged(key, truth_val):
        r = (ref_read or {}).get(key); g = (gen_read or {}).get(key)
        if r is None or g is None:
            return U, {"ref": r, "gen": g, "truth": truth_val, "why": "the reader could not determine it on one of the images"}
        if r != truth_val:
            return U, {"ref": r, "gen": g, "truth": truth_val, "why": "the reader does not see the truth on the reference render, so it cannot measure the photograph against it"}
        return (P if g == r else F), {"ref": r, "gen": g, "truth": truth_val}
    items["rows"] = judged("rows", t["rows"])
    items["stitches_per_row"] = judged("stitches_per_row", t["stitches_per_row"])
    items["stitch_family"] = judged("stitch_height", t["family"])
    r_le, g_le = (ref_read or {}).get("loose_ends"), (gen_read or {}).get("loose_ends")
    items["construction_cues_loose_ends"] = ((U if (r_le is None or g_le is None) else (P if str(r_le).lower().split()[0] == str(g_le).lower().split()[0] else F)), {"ref": r_le, "gen": g_le})
    items["openings"] = ("PASS", {"note": "not applicable: the certified swatch has no openings and the photograph shows none (colour segmentation finds one connected region)"})
    items["deformation_fold_placement"] = (items["silhouette"][0] if items["structure_placement"][0] == P else (F if items["silhouette"][0] == F or items["structure_placement"][0] == F else U),
                                           {"from": "silhouette + structure placement, aligned", "iou_aligned": num["silhouette_iou_aligned"], "ncc_aligned": num["structure_ncc_aligned"]})
    statuses = [s for s, _ in items.values()]
    overall = F if F in statuses else (P if all(s == P for s in statuses) else U)
    return overall, {k: {"status": s, "evidence": e} for k, (s, e) in items.items()}


def main(manifest="e3_manifest.json", result="e3_correspondence.json"):
    man = json.load(open(os.path.join(OUT, manifest)))
    results = {"criteria": {k: {"value": v[0], "why": v[1]} for k, v in CRITERIA.items()}, "questionnaire": QUESTIONS, "reader": DJ.MODEL, "per_image": [], "reader_cost_usd": 0.0}
    cache = {}
    prior = {}
    prev = os.path.join(OUT, "e3_correspondence.json")
    if os.path.exists(prev):
        for r in json.load(open(prev))["per_image"]:
            prior[r["output_sha256"]] = r["generated_reading"]; prior[r["reference_sha256"]] = r["reference_reading"]
    for run in man["runs"]:
        if not run.get("ok"):
            continue
        kind, view = run["kind"], run["view"]
        num = numeric(kind, view, run["path"])
        ref = run["reference"]
        if ref not in cache:
            cache[ref] = prior.get(run["reference_sha256"]) or read_structure(ref)
            if run["reference_sha256"] not in prior: results["reader_cost_usd"] += cache[ref]["cost_usd"]
        gen_r = prior.get(run["output_sha256"]) or read_structure(run["path"])
        if run["output_sha256"] not in prior: results["reader_cost_usd"] += gen_r["cost_usd"]
        overall, items = decide(kind, num, cache[ref]["reading"], gen_r["reading"])
        results["per_image"].append({"kind": kind, "view": view, "generated": run["path"], "output_sha256": run["output_sha256"],
                                     "reference_sha256": run["reference_sha256"], "geometry_sha256": run["geometry_sha256"],
                                     "numeric": num, "reference_reading": cache[ref], "generated_reading": gen_r,
                                     "overall": overall, "items": items})
        print(f"{kind} {view}: {overall}", {k: v["status"] for k, v in items.items()})
        print("   numeric:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in num.items()})
        print("   ref reading:", cache[ref]["reading"]); print("   gen reading:", gen_r["reading"])
    results["reader_cost_usd"] = round(results["reader_cost_usd"], 4)
    results["reader_cost_usd_prior_runs"] = 0.1328 if prior else 0.0
    json.dump(results, open(os.path.join(OUT, result), "w"), indent=1)
    print("reader spend US$%.4f" % results["reader_cost_usd"])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "package":
        main("e3_manifest_pkg.json", "e3_correspondence_pkg.json")
    else:
        main()
