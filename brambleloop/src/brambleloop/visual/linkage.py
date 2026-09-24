"""Linking number of two closed curves.

Why this module exists. The validator used to ask whether a *sub-path* of the yarn crossed a
surface an odd number of times. That is not a topological property: truncate the sub-path a
few points earlier or later and the parity flips, so the answer depended on where the path
happened to be cut rather than on how the yarn is threaded. It reported 16 stitches linked
and 7 unlinked and neither number meant anything.

The linking number of two *closed* curves is an integer topological invariant. It does not
move when either curve is deformed, only when one is pulled through the other -- which is
exactly the event being tested. Nothing here depends on where a path was cut, because the
curves passed in are closed before anything is measured.

The computation is the textbook one: fan-triangulate a surface spanning the first curve, and
count the signed crossings the second curve makes through it. The count is independent of
which spanning surface is chosen, so long as the curves do not intersect each other -- which
is checked, because if they intersect the linking number is undefined rather than zero.
"""
from __future__ import annotations

import numpy as np

__all__ = ["close_arc", "close_path_outside", "linking_number",
           "link_with_open_path", "CurvesIntersect"]


class CurvesIntersect(Exception):
    """The two curves touch, so their linking number is undefined.

    Raised rather than returned as zero. Zero means "not linked", which is a different
    statement from "these curves occupy the same point and the question is malformed".
    """


def close_arc(points: np.ndarray) -> np.ndarray:
    """Close an open arc into a cycle with a single chord between its endpoints.

    The top loops of a crochet stitch are arcs of the continuous yarn, not cycles. Closing
    one with a chord is the standard way to give an open strand a definite linking number,
    and it is the right chord here: the strand's two ends are held together by the stitch
    body they emerge from, so the chord runs through yarn that is really there.
    """
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        raise ValueError("an arc needs at least three points to bound anything")
    if np.allclose(pts[0], pts[-1]):
        return pts.copy()
    return np.vstack([pts, pts[0]])


def close_path_outside(path: np.ndarray, centre: np.ndarray, radius: float) -> np.ndarray:
    """Close an open path with a detour that provably stays outside a sphere.

    The detour cannot contribute crossings, because every surface spanning the other curve
    lies inside that sphere and the detour never enters it. So the linking number computed
    from this closure is a property of the path, not of the closure -- which is the whole
    point, and is asserted rather than assumed: the returned closure is checked.
    """
    pts = np.asarray(path, dtype=np.float64)
    centre = np.asarray(centre, dtype=np.float64)
    out = float(radius) * 4.0 + 1.0

    # Leave from the end, run around the outside, come back to the start. The waypoints are
    # placed on a box well clear of the sphere.
    corners = np.array([
        [+1, +1, +1], [-1, +1, +1], [-1, -1, +1], [+1, -1, +1],
    ], dtype=np.float64) * out + centre

    closure = np.vstack([corners, pts[0]])
    closed = np.vstack([pts, closure])

    # The detour must not enter the sphere. If it did, the result would depend on it.
    detour = closed[len(pts) - 1:]
    if _min_distance_to_point(detour, centre) <= radius:
        raise ValueError("the closure enters the region it must avoid")
    return closed


def _min_distance_to_point(poly: np.ndarray, p: np.ndarray) -> float:
    a, b = poly[:-1], poly[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    denom[denom == 0] = 1e-12
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / denom, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return float(np.linalg.norm(closest - p, axis=1).min())


def linking_number(loop: np.ndarray, path: np.ndarray, *, tol: float = 1e-9) -> int:
    """Signed number of times `path` passes through `loop`.

    Both must be closed. Returns an integer: 0 is genuinely unlinked, and any non-zero value
    means the path cannot be pulled free of the loop without breaking one of them.
    """
    loop = np.asarray(loop, dtype=np.float64)
    path = np.asarray(path, dtype=np.float64)
    if not np.allclose(loop[0], loop[-1]) or not np.allclose(path[0], path[-1]):
        raise ValueError("linking number is defined for closed curves")

    centroid = loop[:-1].mean(axis=0)
    scale = float(np.linalg.norm(loop[:-1] - centroid, axis=1).max()) or 1.0

    # A fan is a legitimate spanning surface, but its apex is shared by every triangle, so a
    # path passing exactly through the apex registers a hit on all of them at once -- a rod
    # straight through a 32-segment ring scored 32 instead of 1. That is a degeneracy of the
    # triangulation, not of the topology, and the linking number does not depend on which
    # spanning surface is used. So when a crossing lands on a triangle boundary the apex is
    # moved and the count retaken. The offsets are fixed, not random: the same curves must
    # always give the same answer.
    for nudge in _APEX_NUDGES:
        apex = centroid + np.asarray(nudge) * scale
        tri_a = np.repeat(apex[None, :], len(loop) - 1, axis=0)
        total, degenerate = 0, False
        for q0, q1 in zip(path[:-1], path[1:]):
            n, deg = _segment_crossings(q0, q1, tri_a, loop[:-1], loop[1:], tol)
            total += n
            degenerate |= deg
        if not degenerate:
            return int(total)
    raise CurvesIntersect(
        "every spanning surface tried was crossed at a boundary, which means the path runs "
        "along the loop rather than through or past it")


# Fixed, deliberately irrational-ish offsets so no nudge lines up with a mesh feature.
_APEX_NUDGES = (
    (0.0, 0.0, 0.0),
    (0.0137, -0.0271, 0.0193),
    (-0.0419, 0.0163, -0.0337),
    (0.0271, 0.0419, 0.0137),
)


def _segment_crossings(q0, q1, pa, pb, pc, tol):
    """Signed crossings of one segment through a fan of triangles.

    Moller-Trumbore, vectorised over the fan, with the sign taken from the direction of
    travel through the triangle rather than from the triangle's winding -- so the answer does
    not depend on how the fan happened to be ordered.
    """
    d = q1 - q0
    e1, e2 = pb - pa, pc - pa
    h = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, h)

    parallel = np.abs(det) < tol
    safe = np.where(parallel, 1.0, det)
    s = q0 - pa
    u = np.einsum("ij,ij->i", s, h) / safe
    qv = np.cross(s, e1)
    v = np.einsum("j,ij->i", d, qv) / safe
    t = np.einsum("ij,ij->i", e2, qv) / safe

    inside = (~parallel) & (u >= -tol) & (v >= -tol) & (u + v <= 1 + tol)
    hit = inside & (t > tol) & (t < 1 - tol)

    # A hit sitting on a triangle's edge or vertex is shared with the neighbouring triangle
    # and would be counted twice, or on the fan apex and counted once per triangle.
    #
    # A crossing sitting at the END of a path segment is the same problem seen from the
    # other side, and it used to be invisible: the t-range test dropped it and nothing
    # noticed, so the answer came back 0 -- not linked -- for a crossing that was really
    # there. A Hopf link scored zero because its crossing fell exactly on a vertex.
    # Absence of a detection was being reported as absence of a crossing.
    #
    # Both are reported so the caller can move the surface rather than trust the number.
    edge = 1e-6
    on_edge = bool((hit & ((u < edge) | (v < edge) | (u + v > 1 - edge))).any())
    at_vertex = bool((inside & (t > -edge) & (t < edge + 1.0)
                      & ((t <= edge) | (t >= 1.0 - edge))).any())
    degenerate = on_edge or at_vertex
    if not hit.any():
        return 0, degenerate
    normals = np.cross(e1, e2)
    sense = np.sign(np.einsum("j,ij->i", d, normals))
    return int(sense[hit].sum()), degenerate


# Directions to try when closing an open path. The first that works is used; which one it is
# cannot change the answer, because a closure is only accepted once it has been shown to
# contribute no crossings at all.
_CLOSURE_DIRECTIONS = (
    np.array([0.0, 1.0, 0.0]),    # up, over the top of the fabric
    np.array([0.0, -1.0, 0.0]),   # down
    np.array([0.0, 0.0, 1.0]),    # out the front
    np.array([1.0, 0.0, 0.0]),    # off the side
)


def link_with_open_path(loop: np.ndarray, path: np.ndarray) -> int:
    """How many times an *open* strand passes through a closed loop.

    A length of yarn in a fabric has two loose ends, so it is not a closed curve and has no
    linking number of its own. The usual repair is to close it and measure that -- but then
    the answer can be an artefact of the closure, which is precisely the failure this module
    exists to remove. So the closure is not trusted: it is routed away from the loop, its own
    contribution is counted separately, and it is accepted only if that contribution is zero.
    When it is zero the closure has cancelled out of the arithmetic entirely, and what is
    returned is a property of the strand and the loop alone.

    Raises if no closure can be found that contributes nothing, rather than returning a
    number that quietly depends on one.
    """
    loop = np.asarray(loop, dtype=np.float64)
    path = np.asarray(path, dtype=np.float64)
    if not np.allclose(loop[0], loop[-1]):
        raise ValueError("the loop must be closed")

    centroid = loop[:-1].mean(axis=0)
    scale = float(np.linalg.norm(loop[:-1] - centroid, axis=1).max()) or 1.0
    reach = scale * 40.0 + float(np.abs(path - centroid).max()) * 4.0

    for direction in _CLOSURE_DIRECTIONS:
        far = centroid + direction * reach
        closure = np.vstack([path[-1], far + (path[-1] - centroid), far + (path[0] - centroid),
                             path[0]])
        for nudge in _APEX_NUDGES:
            apex = centroid + np.asarray(nudge) * scale
            tri_a = np.repeat(apex[None, :], len(loop) - 1, axis=0)
            walked = _count(tri_a, loop, path)
            if walked is None:
                continue
            shut = _count(tri_a, loop, closure)
            if shut is None:
                continue
            if shut == 0:
                return int(walked)
    raise CurvesIntersect(
        "no closure route left the linking number unchanged, which means the strand passes "
        "through the loop's rim rather than cleanly through or past it")


def _count(tri_a, loop, poly, tol: float = 1e-9):
    """Signed crossings of a polyline through the fan, or None if any hit was degenerate."""
    total = 0
    for q0, q1 in zip(poly[:-1], poly[1:]):
        n, degenerate = _segment_crossings(q0, q1, tri_a, loop[:-1], loop[1:], tol)
        if degenerate:
            return None
        total += n
    return total
