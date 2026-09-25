"""The physically based scene, committed, so two fabrics can be compared rather than admired.

WHY THIS FILE EXISTS. The drape attribution set in this repository -- `yarn_drape_control.png`,
`yarn_drape_draped.png`, `yarn_drape_oblique.png`, and the Layer 1-5 yarn ladder -- was
rendered with Mitsuba by hand and **the scene was never committed**. The commit that added
those images states they are "identical in yarn, material, fibre layers, lighting, camera and
contact staging, differing only in out-of-plane relaxation", and that claim cannot be checked
or repeated from anything in the tree. It is the same defect family as `CALIBRATED_BENDING_N_M2`
being a literal whose derivation cannot be re-run, which research/VISUAL_WAVE2.md recorded.

So the staging is DATA here, in one place, and a comparison between two fabrics is two calls
that differ only in the fabric. Nothing in this module invents geometry, moves a vertex or
improves an appearance: it converts a certified `crochet_topology.Fabric` into strands and
hands them to a renderer.

WHAT IT REFUSES TO DRAW, and this is the one substantive decision in it. The stored yarn path
is not all yarn. On the certified 5x5 swatch, 87 of 473 segments are artificial hops between
ops -- up to 6.73mm -- and 20 are sub-micron joins where one stitch's point list meets the
next. Drawing the hops as yarn would put strands in the picture that are not in the fabric,
and they are exactly the segments `genuine_yarn_vertices` has identified since
research/VISUAL_WAVE3.md. The path is therefore SPLIT at them into separate strands, which is
also what Mitsuba's linear-curve format expects: one blank line per strand.

MITSUBA IS NOT A DEPENDENCY. `requirements.txt` deliberately excludes it -- the renderer is
~200MB and the deployed service never renders -- so `render` imports it lazily and says so
plainly if it is absent. Everything above `render` works without it and is tested without it.
"""
from __future__ import annotations

import numpy as np

from . import crochet_topology as topo
from . import drape as dr

__all__ = ["fabric_strands", "write_curve_file", "STAGING", "scene_dict", "render"]


def fabric_strands(fab: topo.Fabric, *, per_segment: int = 6) -> list[np.ndarray]:
    """The fabric's yarn, as separate strands, with the path's artefacts removed.

    A segment is not yarn if it is longer than `drape.JUMP_SEGMENT_MM` (an artificial hop
    between ops) or shorter than `drape.DEGENERATE_SEGMENT_MM` (a join between one stitch's
    point list and the next). The path is cut at every such segment. `per_segment` Catmull-Rom
    samples are then taken inside each strand, because yarn does not turn corners: a polyline
    with hard corners renders as bent wire. The control points are not moved.
    """
    pts = np.asarray(fab.points, dtype=float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cut = (seg >= dr.JUMP_SEGMENT_MM) | (seg <= dr.DEGENERATE_SEGMENT_MM)
    strands: list[np.ndarray] = []
    start = 0
    for i, bad in enumerate(cut):
        if bad:
            if i + 1 - start >= 2:
                strands.append(pts[start:i + 1])
            start = i + 1
    if len(pts) - start >= 2:
        strands.append(pts[start:])
    return [_smooth(s, per_segment) for s in strands]


def _smooth(p: np.ndarray, per_segment: int) -> np.ndarray:
    """Catmull-Rom through the control points. Interpolating, so no control point moves."""
    if per_segment <= 1 or len(p) < 4:
        return p
    out = [p[0]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for j in range(per_segment):
            t = j / per_segment
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                              (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(p[-2])
    out.append(p[-1])
    return np.asarray(out)


def write_curve_file(fab: topo.Fabric, filename: str, *, per_segment: int = 6,
                     radius_mm: float | None = None) -> tuple[int, int]:
    """Mitsuba's linear-curve format: `x y z radius` per vertex, a blank line per strand.

    Returns (strands, vertices). The radius is the fabric's own derived yarn radius unless one
    is given, so the picture is the size the geometry says and not a size chosen for it.
    """
    r = float(radius_mm if radius_mm is not None else fab.yarn_diameter / 2.0)
    strands = fabric_strands(fab, per_segment=per_segment)
    n = 0
    with open(filename, "w") as f:
        for s in strands:
            for x, y, z in s:
                f.write("%.5f %.5f %.5f %.5f\n" % (x, y, z, r))
                n += 1
            f.write("\n")
    return len(strands), n


# THE STAGING. One dictionary, so "identical camera, lighting, material and staging" is a
# literal that two renders can be checked against rather than a sentence in a commit message.
# Distances are in millimetres, the same units the certified geometry is in.
#
# The camera is given as an OFFSET from the framing fabric's own centre, not as an absolute
# position, and the framing fabric is passed in. Two fabrics compared under this scene are
# framed by the SAME reference -- normally the certified flat swatch -- so a fabric that has
# drooped is seen to have drooped instead of being re-centred out of the comparison.
STAGING = {
    "camera": {
        # Straight on, far enough that the swatch spans most of the frame, with a long-ish
        # lens so the perspective does not do the drape's job for it.
        "offset": (0.0, 0.0, 165.0),
        "up": (0.0, 1.0, 0.0),
        "fov": 26.0,
    },
    "oblique": {
        "offset": (110.0, 70.0, 115.0),
        "up": (0.0, 1.0, 0.0),
        "fov": 26.0,
    },
    "film": {"width": 900, "height": 900, "spp": 96},
    # A single soft key from above and behind the camera's shoulder, a uniform ambient fill,
    # and a mid-grey backdrop. No coloured rim light and no vignette: this is a measurement
    # instrument, not a product photograph, and anything that flatters one fabric flatters
    # both.
    #
    # The key is placed BEHIND every view's camera, which is checked rather than eyeballed --
    # the first version put a 55mm fill sphere 63mm from the oblique camera and filled a third
    # of that frame with the lamp. The fill is an environment emitter and not geometry for the
    # same reason: a light that can appear in the picture is a light that can appear in one
    # picture of a comparison and not the other.
    "key": {"position": (-180.0, 300.0, 380.0), "radius": 70.0, "radiance": 27.0},
    "ambient": 0.35,
    "backdrop": {"z": -55.0, "half": 900.0, "reflectance": (0.34, 0.33, 0.32)},
    # Worsted acrylic, as a rough dielectric over a diffuse base. The yarn's own fibre halo,
    # ply wobble and surface fuzz are the Layer 1-5 ladder's subject and are NOT reproduced
    # here; this scene exists to compare two GEOMETRIES under one material, and saying which
    # layers are absent is the point of saying it at all.
    "material": {"base": (0.62, 0.30, 0.36), "roughness": 0.46, "specular": 0.18},
    # Said in DATA, not in a comment, because an instrument that quietly looks like the yarn
    # ladder will be read as a claim about appearance. Every one of these is a committed
    # result of the Layer 1-5 ladder and NOT reproduced here.
    "not_reproduced": ("fibre halo", "ply wobble", "surface fuzz", "hand tension drift",
                       "the Layer 1-5 yarn ladder's material stack"),
}


def framing_centre(fab: topo.Fabric) -> tuple[float, float, float]:
    """The centre of a fabric's bounding box, which is what the camera looks at."""
    p = np.asarray(fab.points, dtype=float)
    return tuple(float(x) for x in (p.min(axis=0) + p.max(axis=0)) / 2.0)


def scene_dict(curve_file: str, centre, *, view: str = "camera",
               staging: dict | None = None) -> dict:
    """The scene as a plain dictionary, checkable without Mitsuba.

    This is the ONLY description of the scene. `render` builds from it and substitutes the
    three symbolic transforms -- `("look_at", ...)`, `("translate", ...)`, `("backdrop", ...)`
    -- for Mitsuba objects. A second description built directly inside `render` is two places
    for a material or a light to drift apart, which is how a comparison stops being one.
    """
    st = staging or STAGING
    cam = dict(st[view])
    cam["target"] = tuple(centre)
    cam["origin"] = tuple(c + o for c, o in zip(centre, cam["offset"]))
    film, key, back, mat = st["film"], st["key"], st["backdrop"], st["material"]
    return {
        "type": "scene",
        "integrator": {"type": "path", "max_depth": 12},
        "sensor": {
            "type": "perspective",
            "fov": cam["fov"],
            "to_world": ("look_at", cam["origin"], cam["target"], cam["up"]),
            "film": {"type": "hdrfilm", "width": film["width"], "height": film["height"],
                     "pixel_format": "rgb"},
            "sampler": {"type": "independent", "sample_count": film["spp"]},
        },
        "yarn": {
            "type": "linearcurve",
            "filename": curve_file,
            "bsdf": {
                "type": "roughplastic",
                "distribution": "ggx",
                "diffuse_reflectance": {"type": "rgb", "value": list(mat["base"])},
                "alpha": mat["roughness"],
                "specular_reflectance": {"type": "rgb", "value": [mat["specular"]] * 3},
            },
        },
        "backdrop": {
            "type": "rectangle",
            "to_world": ("backdrop", tuple(centre), back["z"], back["half"]),
            "bsdf": {"type": "diffuse",
                     "reflectance": {"type": "rgb", "value": list(back["reflectance"])}},
        },
        "key": {
            "type": "sphere",
            "radius": key["radius"],
            "to_world": ("translate",
                         tuple(c + p for c, p in zip(centre, key["position"]))),
            "emitter": {"type": "area",
                        "radiance": {"type": "rgb", "value": [key["radiance"]] * 3}},
        },
        "fill": {"type": "constant",
                 "radiance": {"type": "rgb", "value": [st["ambient"]] * 3}},
    }


def render(fab: topo.Fabric, out_png: str, *, view: str = "camera", spp: int | None = None,
           per_segment: int = 6, curve_file: str | None = None,
           frame: topo.Fabric | None = None) -> dict:
    """Render one certified fabric. Raises a plain message if Mitsuba is not installed.

    `frame` is the fabric whose bounding box aims the camera. For a comparison, pass the SAME
    fabric -- normally the certified flat swatch -- to every render, so a fabric that has
    moved is seen to have moved rather than being re-centred out of the picture.

    Returns what was drawn -- strands, vertices, view, samples, the camera it used -- so two
    renders can be shown to have been made the same way instead of asserted to have been.
    """
    try:
        import mitsuba as mi
    except ImportError as exc:                                  # pragma: no cover
        raise RuntimeError(
            "Mitsuba is not installed. It is deliberately not in requirements.txt: the "
            "renderer is ~200MB and the deployed service never renders. Install it in a "
            "local environment to reproduce these images.") from exc

    import os
    import tempfile
    mi.set_variant("llvm_ad_rgb")
    tmp = curve_file or os.path.join(tempfile.mkdtemp(), "fabric.txt")
    strands, verts = write_curve_file(fab, tmp, per_segment=per_segment)

    centre = framing_centre(frame if frame is not None else fab)
    spec = scene_dict(tmp, centre, view=view)
    if spp is not None:
        spec["sensor"]["sampler"]["sample_count"] = int(spp)
    cam_origin = spec["sensor"]["to_world"][1]
    cam_target = spec["sensor"]["to_world"][2]

    # The key must be behind every camera this scene offers, or a lamp appears in one picture
    # of a comparison and not the other. Checked, not eyeballed: the first version put a 55mm
    # fill sphere 63mm from the oblique camera and filled a third of that frame with it.
    _view = np.asarray(cam_target, float) - np.asarray(cam_origin, float)
    _to_key = np.asarray(spec["key"]["to_world"][1], float) - np.asarray(cam_origin, float)
    if float(_view @ _to_key) > 0.0:
        raise RuntimeError("the key light is in front of the '%s' camera and would appear in "
                           "the frame" % view)

    # The three symbolic transforms, substituted. This is the only place Mitsuba objects are
    # built, and the description above them is `scene_dict`'s and nobody else's.
    _, origin, target, up = spec["sensor"]["to_world"]
    spec["sensor"]["to_world"] = mi.ScalarTransform4f().look_at(
        origin=list(origin), target=list(target), up=list(up))
    spec["sensor"]["film"]["rfilter"] = {"type": "gaussian"}
    _, pos = spec["key"]["to_world"]
    spec["key"]["to_world"] = mi.ScalarTransform4f().translate(list(pos))
    _, bcentre, bz, bhalf = spec["backdrop"]["to_world"]
    spec["backdrop"]["to_world"] = (mi.ScalarTransform4f()
                                    .translate([bcentre[0], bcentre[1], bcentre[2] + bz])
                                    .scale([bhalf, bhalf, 1.0]))
    img = mi.render(mi.load_dict(spec))
    mi.util.write_bitmap(out_png, img)
    return {"strands": strands, "vertices": verts, "view": view,
            "spp": spec["sensor"]["sampler"]["sample_count"],
            "curve_file": tmp, "out": out_png, "centre": centre,
            "camera_origin": tuple(origin), "camera_target": tuple(target),
            "fov": spec["sensor"]["fov"], "radius_mm": fab.yarn_diameter / 2.0}
