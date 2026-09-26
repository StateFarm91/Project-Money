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

__all__ = ["fabric_strands", "write_curve_file", "write_plied_curve_file", "STAGING",
           "STAGING_PLIED", "scene_dict", "render"]


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


def write_plied_curve_file(fab: topo.Fabric, filename: str, *, tex: float,
                           per_segment: int = 6, fibres_per_ply: int = 16,
                           seed: int = 20260924, plies: int | None = None) -> dict:
    """The same strands as `write_curve_file`, drawn as the yarn is built: plies twisted
    around each strand's centreline and a sparse halo of surface fibres over the plies.

    THE BRIDGE. Until this existed the repository had two geometry pipelines that never met:
    the certified `crochet_topology.Fabric` -- built, relaxed, validated, draped, measured --
    was rendered as a smooth tube, while the ply-and-fibre yarn construction was only ever
    drawn on `visual/yarn.py`'s separate, unvalidated path. Every mechanics number was of one
    geometry and every convincing picture of another. This function is the single place the
    two meet: the centreline it takes is the certified fabric's own strands, cut at the same
    artificial hops `fabric_strands` refuses to draw, and `yarn_construction.ply_geometry`
    derives the plies from it without moving a control point.

    The lock is the one `yarn_construction` states: everything here is a rendering derivation
    from the validated centreline. Nothing feeds back.

    Returns what was written -- strand, ply and fibre counts, radii, the PlySpec -- so a
    render can say what it drew.
    """
    from . import yarn_construction as yc
    kw = {} if plies is None else {"plies": plies}
    spec = yc.PlySpec(yarn_diameter_mm=float(fab.yarn_diameter), tex=float(tex), **kw)
    strands = fabric_strands(fab, per_segment=per_segment)
    r_ply = spec.ply_radius_mm
    n_ply = n_fib = verts = 0
    r_fib = None
    with open(filename, "w") as f:
        for k, s in enumerate(strands):
            if len(s) < 2:
                continue
            plies_k = yc.ply_geometry(s, spec)
            for ply in plies_k:
                for x, y, z in ply:
                    f.write("%.5f %.5f %.5f %.5f\n" % (x, y, z, r_ply))
                    verts += 1
                f.write("\n")
                n_ply += 1
            if fibres_per_ply > 0:
                fibres, r_fib = yc.surface_fibres(plies_k, spec, per_ply=fibres_per_ply,
                                                  seed=seed + k)
                for fb in fibres:
                    for x, y, z in fb:
                        f.write("%.5f %.5f %.5f %.5f\n" % (x, y, z, r_fib))
                        verts += 1
                    f.write("\n")
                    n_fib += 1
    return {"strands": len(strands), "plies": n_ply, "fibres": n_fib, "vertices": verts,
            "ply_radius_mm": r_ply, "fibre_radius_mm": r_fib, "spec": spec.describe(),
            "yarn_diameter_mm": float(fab.yarn_diameter)}


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


# The same scene with the yarn drawn by `write_plied_curve_file`. It differs from STAGING in
# exactly one field, and that field is the honest one: what the picture does not have. Plies
# and a surface-fibre halo are now geometry in the curve file; the fibre normal map
# (`fibre_surface_map`), hand tension drift and the rest of the Layer 1-5 material stack are
# still absent, and a picture from this scene is still a geometry instrument, not evidence
# about appearance.
STAGING_PLIED = dict(STAGING)
STAGING_PLIED["not_reproduced"] = ("fibre surface normal map", "surface fuzz beyond the "
                                   "sparse fibre halo", "hand tension drift",
                                   "the Layer 3-5 material stack")
STAGING_PLIED["reproduced_as_geometry"] = ("plies at the derived radius and twist",
                                           "a sparse surface-fibre halo at the derived "
                                           "fibre radius")


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
           frame: topo.Fabric | None = None, plied_tex: float | None = None,
           fibres_per_ply: int = 16) -> dict:
    """Render one certified fabric. Raises a plain message if Mitsuba is not installed.

    `plied_tex`, when given, draws the yarn through `write_plied_curve_file` at that linear
    density -- plies and fibres rather than a tube -- under `STAGING_PLIED`. The geometry the
    camera sees is still the certified fabric's; only how its yarn is drawn changes.

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

    import contextlib
    import os
    import tempfile
    mi.set_variant("llvm_ad_rgb")
    # The curve file is removed with the render unless the caller named one and therefore
    # owns it. A bare `mkdtemp()` here left a directory nobody deleted, which made this the
    # SECOND unremoved mkdtemp in the tree; exactly one is allowed, and it is named in
    # `test_cost_governance_wave2` rather than exempted silently -- the continuity download,
    # which cleans up after its response is sent. A renderer that only ever runs by hand is
    # still a renderer that should not litter the disk it runs on.
    with contextlib.ExitStack() as _scratch:
        if curve_file:
            tmp, caller_owns = curve_file, True
        else:
            tmp = os.path.join(
                _scratch.enter_context(
                    tempfile.TemporaryDirectory(prefix="brambleloop-render-")),
                "fabric.txt")
            caller_owns = False
        if plied_tex is not None:
            drawn = write_plied_curve_file(fab, tmp, tex=plied_tex, per_segment=per_segment,
                                           fibres_per_ply=fibres_per_ply)
            strands, verts = drawn["strands"], drawn["vertices"]
            staging = STAGING_PLIED
        else:
            strands, verts = write_curve_file(fab, tmp, per_segment=per_segment)
            drawn = None
            staging = STAGING

        centre = framing_centre(frame if frame is not None else fab)
        spec = scene_dict(tmp, centre, view=view, staging=staging)
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
                "curve_file": tmp if caller_owns else None,
                "curve_file_was_temporary": not caller_owns, "out": out_png, "centre": centre,
                "camera_origin": tuple(origin), "camera_target": tuple(target),
                "fov": spec["sensor"]["fov"], "radius_mm": fab.yarn_diameter / 2.0,
                "plied": drawn, "not_reproduced": staging["not_reproduced"]}
