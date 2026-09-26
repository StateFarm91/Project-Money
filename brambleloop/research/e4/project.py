"""E4 — the projected-stitch correspondence instrument.

We own the certified geometry, the stitch identities and the exact camera, so no stitch is
ever counted blind. Every certified stitch is projected through the presentation camera
(analytic pinhole, verified against Mitsuba's own rendering to 0.5 px -- research/e4 log) into
the reference image, giving a manifest per stitch: id, family, row, position, projected key
points, centroid, bounding region, orientation, colour region, visibility (depth-tested
against the yarn's own depth map and the form), and its structural neighbours (the anchor it
was worked into, the neighbours along its row) with their projected offsets.

THE INSTRUMENT VALIDATES ITSELF FIRST. On the deterministic reference it must (a) put the
projected points inside the fabric's own silhouette and (b) read every visible stitch's region
in the RGB render as the certified silhouette says it is. If it cannot recover the reference
it does not judge a photograph.

THE STITCH TEST on a photograph: after the global similarity alignment (scale free, shape not),
the photograph's yarn mask inside each visible stitch's region is compared with the certified
silhouette there (IoU). A stitch whose region agrees is PRESENT AS CERTIFIED; below the bar it
is not, and the manifest says which one. The per-stitch bar and the visibility rule are named
in CRITERIA with their reasons.
"""
import hashlib, json, os, sys
import numpy as np
from dataclasses import replace
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "e3"))
from brambleloop.visual import milestone_d as MD, pbr_scene as PS, drape as DR, crochet_topology as CT

D = os.path.join(os.path.dirname(HERE), "d", "out")
W = PS.STAGING_PRESENTATION["film"]["width"]
CRITERIA = {
    "visible_fraction": (0.5, "CHOSEN: a stitch is testable when at least half of its key points are "
                              "unoccluded at the camera; a stitch mostly behind other yarn or the form "
                              "is reported, not tested"),
    "self_validation_iou": (0.70, "CHOSEN: the reference RGB render's yarn region against the certified "
                                  "silhouette inside a stitch's region; the thin lens blurs edges and the "
                                  "colour segmentation is not the geometry, so 0.70 is where the instrument "
                                  "is reading the reference and below it it is not"),
    "stitch_present_iou": (0.60, "CHOSEN: the photograph's yarn region against the certified silhouette "
                                 "inside a stitch's region after global alignment; the generator may "
                                 "thicken yarn with fuzz and shift edges, so the bar sits below the "
                                 "self-validation bar by the same margin E3 measured between the RGB "
                                 "render and its own aligned outline (0.82-0.93 vs 0.70 here)"),
    "in_silhouette": (0.98, "DERIVED: every projected point of a visible stitch lies on yarn by "
                            "construction; 2 per cent covers points at the grazing edge of a strand"),
}


def camera(flat, view):
    centre = np.array(PS.framing_centre(flat)); cam = dict(PS.STAGING_PRESENTATION[view])
    o = centre + np.array(cam["offset"]); fwd = (centre - o) / np.linalg.norm(centre - o)
    up = np.array(cam["up"], float); right = np.cross(fwd, up); right /= np.linalg.norm(right); upv = np.cross(right, fwd)
    f = 0.5 * W / np.tan(np.radians(cam["fov"]) / 2)
    return {"origin": o, "fwd": fwd, "right": right, "up": upv, "f": f, "target": centre}


def project(cam, pts):
    d = np.asarray(pts, float) - cam["origin"]; z = d @ cam["fwd"]; x = d @ cam["right"]; y = d @ cam["up"]
    col = W / 2 + cam["f"] * x / z - 0.5; row = W / 2 - cam["f"] * y / z - 0.5
    return np.stack([col, row], axis=1), z


def occluded_by_form(cam, pts, form):
    """A point is hidden by the form if the ray from the camera meets the sphere before it."""
    c = np.array(form[:3]); R = form[3]
    d = np.asarray(pts, float) - cam["origin"]; dist = np.linalg.norm(d, axis=1); u = d / dist[:, None]
    oc = cam["origin"] - c; b = u @ oc; disc = b * b - (oc @ oc - R * R)
    hit = disc > 0
    t = -b - np.sqrt(np.where(hit, disc, 0.0))
    return hit & (t > 0) & (t < dist)


def manifest(kind, view):
    rec = json.load(open(os.path.join(D, f"milestone_d_{kind}_final.json")))
    z = np.load(os.path.join(D, f"{kind}_draped.npz")); pts = z["points"]
    sha = hashlib.sha256(np.ascontiguousarray(pts, dtype=np.float64).tobytes()).hexdigest()
    assert sha == rec["geometry_sha256"]["draped"]
    cir, twin, flat, _, tex = MD.certified_swatch(kind, 5, 5)
    fab = replace(flat, ops=DR._rewrite(flat, pts)); form = tuple(float(x) for x in z["form"])
    cam = camera(flat, view)
    depth = np.load(os.path.join(OUT, f"{kind}_{view}_depth.npz"))["depth_mm"]
    mask = np.array(Image.open(os.path.join(OUT, f"{kind}_{view}_mask.png"))) > 127
    r_px = fab.yarn_diameter / 2 * cam["f"] / float(np.linalg.norm(cam["target"] - cam["origin"]))
    stitches = [o for o in fab.ops if CT.is_stitch(o)]
    by_key = {(o.row, o.position): o for o in stitches}; rows = sorted({o.row for o in stitches})
    frames = CT.stitch_frames(fab, reference=flat)
    out = []
    for o in stitches:
        uv, zc = project(cam, o.points)
        # visible: not behind other yarn (the yarn's own depth map, one yarn radius tolerance) nor the form
        col = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1); row = np.clip(np.round(uv[:, 1]).astype(int), 0, W - 1)
        dm = depth[row, col]
        vis = (dm > 0) & (zc <= dm + fab.yarn_diameter) & ~occluded_by_form(cam, o.points, form)
        fr = frames.get((o.row, o.position))
        c3 = o.points.mean(axis=0)
        upv = (project(cam, [c3 + fr[1] * fab.H * 0.5])[0][0] - project(cam, [c3])[0][0]) if fr else None
        ri = rows.index(o.row)
        anchor = by_key.get((rows[ri - 1], o.position)) if ri > 0 else None
        neigh = {k: by_key.get((o.row, o.position + s)) for k, s in (("ahead", 1), ("behind", -1))}
        cen = uv.mean(axis=0)
        def off(q):
            return None if q is None else (project(cam, [q.points.mean(axis=0)])[0][0] - cen).round(1).tolist()
        pad = int(np.ceil(r_px)) + 2
        bbox = [int(uv[:, 0].min()) - pad, int(uv[:, 1].min()) - pad, int(uv[:, 0].max()) + pad, int(uv[:, 1].max()) + pad]
        out.append({"id": f"r{o.row}p{o.position}", "row": o.row, "position": o.position, "family": o.kind,
                    "loop_target": o.loop_target, "points_px": uv.round(1).tolist(), "depth_mm": zc.round(2).tolist(),
                    "centroid_px": cen.round(1).tolist(), "bbox_px": bbox, "yarn_radius_px": float(r_px),
                    "orientation_up_px": (upv.round(2).tolist() if upv is not None else None),
                    "colour_region": "yarn (single dyed colour, the only material)",
                    "visible_points": int(vis.sum()), "visible_fraction": float(vis.mean()),
                    "testable": bool(vis.mean() >= CRITERIA["visible_fraction"][0]),
                    "neighbours": {"anchor_below": (f"r{anchor.row}p{anchor.position}" if anchor else None),
                                   "anchor_offset_px": off(anchor),
                                   "row_ahead": (f"r{neigh['ahead'].row}p{neigh['ahead'].position}" if neigh["ahead"] else None),
                                   "row_ahead_offset_px": off(neigh["ahead"]),
                                   "row_behind": (f"r{neigh['behind'].row}p{neigh['behind'].position}" if neigh["behind"] else None)}})
    return {"kind": kind, "view": view, "geometry_sha256": sha, "form": list(form), "image_px": W,
            "camera": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in cam.items()},
            "stitches": out, "criteria": {k: {"value": v[0], "why": v[1]} for k, v in CRITERIA.items()}}, fab, mask


def region_iou(a, b, bbox):
    x0, y0, x1, y1 = [max(0, v) for v in bbox]; x1, y1 = min(x1, W), min(y1, W)
    A, Bm = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    u = (A | Bm).sum(); return float((A & Bm).sum() / u) if u else 0.0


def self_validate(man, mask, ref_rgb_path):
    """(a) projected visible points lie in the certified silhouette; (b) the reference RGB
    render's yarn region agrees with the silhouette inside every testable stitch's region."""
    from correspond import yarn_mask
    rgb = Image.open(ref_rgb_path).convert("RGB"); ymask, _ = yarn_mask(rgb)
    inside = []; per = []
    for s in man["stitches"]:
        uv = np.array(s["points_px"]); col = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1); row = np.clip(np.round(uv[:, 1]).astype(int), 0, W - 1)
        if s["testable"]:
            inside.append(mask[row, col].mean())
            per.append((s["id"], region_iou(ymask, mask, s["bbox_px"])))
    frac_inside = float(np.mean(inside)) if inside else 0.0
    ious = {k: v for k, v in per}
    worst = min(ious.values()) if ious else 0.0
    ok = frac_inside >= CRITERIA["in_silhouette"][0] and worst >= CRITERIA["self_validation_iou"][0]
    return {"valid": bool(ok), "testable_stitches": len(per), "of": len(man["stitches"]),
            "projected_points_in_silhouette": frac_inside, "per_stitch_reference_iou": ious, "worst": worst,
            "reference_rgb_sha256": hashlib.sha256(open(ref_rgb_path, "rb").read()).hexdigest()}


if __name__ == "__main__":
    kinds = sys.argv[1:] or ["hdc", "sc"]
    for kind in kinds:
        for view in ("camera", "oblique"):
            man, fab, mask = manifest(kind, view)
            ref = os.path.join(D, f"{kind}_draped_presentation3_{view}.png")
            sv = self_validate(man, mask, ref) if os.path.exists(ref) else {"valid": None, "why": "no presentation3 render yet"}
            man["self_validation"] = sv
            json.dump(man, open(os.path.join(OUT, f"{kind}_{view}_manifest.json"), "w"), indent=1)
            t = [s for s in man["stitches"] if s["testable"]]
            print(kind, view, "stitches", len(man["stitches"]), "testable", len(t), "| self-validation:",
                  {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sv.items() if k not in ("per_stitch_reference_iou", "reference_rgb_sha256")})
