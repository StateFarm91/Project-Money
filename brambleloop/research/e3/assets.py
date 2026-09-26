"""E3 conditioning and validation assets from the FROZEN certified geometry.

Everything here is derived from `research/d/out/<kind>_draped.npz` -- the points `milestone_d`
assessed, refused unless their hash matches the final record -- under the same presentation
scene that produced the judged reference renders. No vertex moves. Produced per view:

  <kind>_<view>_mask.png    the fabric's own silhouette (yarn pixels only; the form and the
                            backdrop are not the product)
  <kind>_<view>_depth.npz   depth of the fabric where the mask is set, millimetres from camera
  <kind>_<view>_normal.png  shading normals of the fabric, encoded 0-1

The RGB structural reference itself is the judged `<kind>_draped_presentation2_<view>.png`
from commit 4a08871; its hash is recorded by `run_e3.py` before anything is generated.
"""
import hashlib, json, os, sys, time
import numpy as np
from dataclasses import replace
import mitsuba as mi
from brambleloop.visual import milestone_d as MD, pbr_scene as PS, drape as DR

mi.set_variant("llvm_ad_rgb")
OUT = os.path.join(os.path.dirname(__file__), "out")
D = os.path.join(os.path.dirname(os.path.dirname(__file__)), "d", "out")


def frozen(kind):
    rec = json.load(open(os.path.join(D, f"milestone_d_{kind}_final.json")))
    z = np.load(os.path.join(D, f"{kind}_draped.npz"))
    pts = z["points"]
    sha = hashlib.sha256(np.ascontiguousarray(pts, dtype=np.float64).tobytes()).hexdigest()
    assert sha == rec["geometry_sha256"]["draped"], "the saved geometry is not the assessed geometry"
    cir, twin, flat, _, tex = MD.certified_swatch(kind, 5, 5)
    return replace(flat, ops=DR._rewrite(flat, pts)), flat, tuple(float(x) for x in z["form"]), tex, sha


def aov_scene(fab, flat, form, tex, view):
    """The presentation scene's camera on the fabric alone, with an AOV integrator."""
    import tempfile
    d = tempfile.mkdtemp(prefix="brambleloop-e3-")
    curve = os.path.join(d, "plies.txt")
    PS.write_plied_curve_file(fab, curve, tex=tex, fibres_per_ply=0)
    centre = PS.framing_centre(flat)
    spec = PS.scene_dict(curve, centre, view=view, staging=PS.STAGING_PRESENTATION, form=None)
    spec["integrator"] = {"type": "aov", "aovs": "dd:depth,nn:sh_normal"}
    spec["sensor"]["sampler"]["sample_count"] = 16
    spec["sensor"].pop("aperture_radius", None); spec["sensor"].pop("focus_distance", None)
    spec["sensor"]["type"] = "perspective"          # a pinhole for a mask: no lens blur on a silhouette
    _, origin, target, up = spec["sensor"]["to_world"]
    spec["sensor"]["to_world"] = mi.ScalarTransform4f().look_at(origin=list(origin), target=list(target), up=list(up))
    spec["sensor"]["film"]["rfilter"] = {"type": "box"}
    spec.pop("backdrop"); spec.pop("key"); spec.pop("fill")
    spec["light"] = {"type": "constant", "radiance": 1.0}
    return spec, d


def main(kinds=("hdc", "sc"), views=("camera", "oblique")):
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for kind in kinds:
        fab, flat, form, tex, sha = frozen(kind)
        manifest[kind] = {"geometry_sha256": sha, "views": {}}
        for view in views:
            spec, d = aov_scene(fab, flat, form, tex, view)
            img = np.array(mi.render(mi.load_dict(spec)))
            # aov channel layout: rgb (3), depth (1), sh_normal (3); take by count from the end
            depth = img[..., -4]
            normal = img[..., -3:]
            mask = depth > 0
            from PIL import Image
            Image.fromarray((mask * 255).astype(np.uint8)).save(os.path.join(OUT, f"{kind}_{view}_mask.png"))
            np.savez_compressed(os.path.join(OUT, f"{kind}_{view}_depth.npz"), depth_mm=np.where(mask, depth, 0.0).astype(np.float32))
            Image.fromarray(np.clip((normal * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, f"{kind}_{view}_normal.png"))
            ys, xs = np.nonzero(mask)
            manifest[kind]["views"][view] = {
                "mask_pixels": int(mask.sum()), "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                "depth_mm_range": [float(depth[mask].min()), float(depth[mask].max())],
                "reference_rgb": os.path.join(D, f"{kind}_draped_presentation2_{view}.png"),
                "reference_rgb_sha256": hashlib.sha256(open(os.path.join(D, f"{kind}_draped_presentation2_{view}.png"), "rb").read()).hexdigest()}
            print(kind, view, manifest[kind]["views"][view]["mask_pixels"], "mask px, bbox", manifest[kind]["views"][view]["bbox"])
    json.dump(manifest, open(os.path.join(OUT, "assets_manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
