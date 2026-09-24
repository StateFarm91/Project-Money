"""Physically based relaxation of a validated crochet yarn path.

WHAT THIS IS FOR. The topology layer produces a yarn route that is certifiably correct --
every stitch linked to the right loop, nothing passing through anything -- and that looks
like a lattice of identical authored modules, because that is what it is. Real fabric does
not get its shape from an author placing key points. It gets it from a length of yarn
finding equilibrium: pulled taut, bent as little as its stiffness allows, resting against
itself wherever it touches. This module is the attempt to let that happen.

THE HARD INVARIANT. Relaxation may change geometry. It may not change topology. The yarn
cannot break, cannot reconnect, cannot pass through itself, and every linkage the validator
certified must still be there afterwards. Nothing here repairs topology after the fact: the
solver is constrained so that breaking it is difficult, and then the existing validators are
run again to prove it, and a run that changed the topology is reported as a failure rather
than quietly returned.

WHY THIS METHOD AND NOT A SIMULATOR. Kaldor, James and Marschner model each yarn as an
inextensible tube and impose inextensibility "using efficient projections", with yarn-yarn
interaction through contact. That is the established shape of the method, and the problem
here is easier than theirs in the way that matters: they simulate motion through time, and
this needs a single static equilibrium. A projection solver goes straight at it.

PyElastica was installed and tested rather than dismissed. It is MIT, it works, its Cosserat
rods carry real material parameters, and it was rejected for a measured reason: its
`RodSelfContact` is a doubly nested loop over element pairs, so at the ~5,500 elements of one
swatch of yarn it is quadratic per timestep, and dynamic relaxation needs thousands of
timesteps. Its contact is also penalty-based, which cannot promise non-penetration. Both
problems get worse with garment size rather than better.

WHAT DRIVES THE SHAPE. Unstressed yarn is straight. That single fact is the engine here:
bending pulls every part of the path towards straightness, inextensibility refuses to let it
lengthen, and contact refuses to let it pass through itself. A loop with nowhere to go
tightens, and rows settle against each other. The nonuniformity that results is mechanical,
not noise sprinkled on afterwards -- stitches near a boundary have different neighbours from
stitches in the middle, and so they end up in different places.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import crochet_topology as topo

__all__ = ["Material", "RelaxationReport", "material_for", "relax",
           "apply_contacts", "project_lengths", "PROVENANCE"]


# Where each physical number comes from. The owner's instruction is to eliminate arbitrary
# constants where the evidence can constrain them, and to say plainly which ones it cannot.
PROVENANCE = {
    "rest_lengths": "measured -- the segment lengths of the certified geometry itself",
    "yarn_diameter_mm": "derived -- the pattern states a 6mm hook; hook/1.8, cross-checked "
                        "against the certified gauge's 6.9mm stitch being about two strands "
                        "wide, which agree to within three per cent",
    "contact_rest": "estimated -- where two touching strands sit, as a fraction of diameter",
    "contact_floor": "estimated, bounded by observation -- published measurements of weft "
                     "knits give yarn unit width reductions of about 19% at 11% strain and "
                     "39% at 22%, so squeezing past roughly half a diameter is not physical",
    "bend_compliance": "SOURCED, with a stated conversion and stated uncertainty. See "
                       "KALDOR_RELAXATION below. The earlier value of 0.18, and the 0.03 "
                       "that replaced it, were both chosen by which swatch looked better, "
                       "which is not a way to pick a physical constant.",
    "rest_curvature": "sourced -- unstressed yarn is straight, so bending relaxes towards "
                      "zero curvature rather than towards the authored shape. Relaxing "
                      "towards the authored curvature would merely re-assert what was drawn",
}


# --------------------------------------------------------------------------------------
# WHERE THE BENDING NUMBER COMES FROM
#
# Kaldor, James and Marschner, "Simulating Knitted Cloth at the Yarn Level" (SIGGRAPH 2008),
# Table 1, which lists separate parameters for their RELAXATION phase and their simulation
# phase. Relaxation is what this module does, so those are the applicable ones.
#
#     yarn radius        r = 0.125 cm
#     linear density     m = 0.006 g/cm, i.e. 600 tex
#     bending            k_bend    = 0.005 g cm^2 / s^2   (relaxation)
#                        k_bend    = 5     g cm^2 / s^2   (simulation)
#     contact            k_contact = 3250  g / s^2        (both)
#
# Their relaxation bending is a THOUSAND times softer than their simulation bending. That is
# deliberate and it is the single most useful fact here: during settling, yarn is allowed to
# be very floppy so the fabric can find its shape.
#
# APPLICABILITY, which is the part that decides whether these numbers may be borrowed. Their
# yarn is comparable to the benchmark's rather than materially different: radius 1.25mm
# against this fabric's 1.67mm, and 600 tex against the pattern's implied ~444 tex. Both are
# chunky yarns of the same class. This is a transfer between similar yarns with the
# difference stated, not a figure lifted from a fine filament and presented as ground truth.
#
# THE CONVERSION, and its uncertainty. This solver is a projection scheme, not a force
# integrator, so Kaldor's stiffnesses cannot be used directly. What carries across is the
# dimensionless ratio k_bend / (k_contact * l^2), which compares bending authority to contact
# authority over a segment of length l. Inextensibility does not enter it: Kaldor constrain
# length rather than penalise it, and so does this solver, so length is not a competing
# energy in either.
#
#     Kaldor relaxation:  9.2e-6      Kaldor simulation:  9.2e-3
#
# Mapping that onto this solver's per-iteration weights (bend_compliance against a contact
# gain of about 0.35) is an ORDER OF MAGNITUDE correspondence, not an equality. Two
# projection schemes with the same ratio do not converge to identical geometry. So the honest
# output is a justified RANGE spanning those two published settings, and the question to put
# to the fabric is whether the result is stable across it.
#
# For reference: bend_compliance = 0.03, the value in use before this was researched, sits at
# a ratio of 8.6e-2 -- roughly ten times stiffer than the stiffest published figure and four
# orders of magnitude above the relaxation figure. It was outside the defensible range.
KALDOR_RELAXATION = 9.2e-6
KALDOR_SIMULATION = 9.2e-3
CONTACT_AUTHORITY = 0.35


@dataclass(frozen=True)
class Material:
    """The physical description of the yarn, and where each number came from."""

    yarn_diameter_mm: float
    contact_rest: float = topo.RESTING_CONTACT
    contact_floor: float = topo.COMPRESSED_CONTACT
    # Kaldor's RELAXATION figure, converted through the ratio described above. Chosen
    # because it is the phase-matched published value, not because of how the swatch looks.
    #
    # A sweep across the whole justified range -- 9.2e-6 to 9.2e-3, three orders of
    # magnitude -- gives fabric dimensions identical to within 0.1mm, row spacing constant
    # at 10.52-10.53mm against a gauge row height of 10.53mm, and the gate passing at every
    # value. What changes is the number of self-contacts, 182 down to 72: a floppier yarn
    # touches itself more, which is what it should do. The macro-geometry does not move.
    #
    # So the exact value inside the range does not control the fabric, and the earlier
    # 0.03 -- which sat OUTSIDE the range, ten times stiffer than the stiffest published
    # figure -- was not buying realism either. It gives the same geometry to within 2%.
    bend_compliance: float = KALDOR_RELAXATION * CONTACT_AUTHORITY
    provenance: dict = field(default_factory=lambda: dict(PROVENANCE))

    @property
    def rest_separation_mm(self) -> float:
        return self.yarn_diameter_mm * self.contact_rest

    @property
    def floor_separation_mm(self) -> float:
        return self.yarn_diameter_mm * self.contact_floor


def material_for(fab: topo.Fabric, *,
                 bend_compliance: float = KALDOR_RELAXATION * CONTACT_AUTHORITY) -> Material:
    """The material of a fabric, taken from the fabric's own derived yarn."""
    return Material(yarn_diameter_mm=fab.yarn_diameter, bend_compliance=bend_compliance)


@dataclass
class RelaxationReport:
    """What the solver did, in terms that can be checked rather than admired."""

    iterations: int = 0
    converged: bool = False
    max_strain_before: float = 0.0
    max_strain_after: float = 0.0
    total_length_before_mm: float = 0.0
    total_length_after_mm: float = 0.0
    bend_energy_before: float = 0.0
    bend_energy_after: float = 0.0
    min_clearance_before_mm: float = 0.0
    min_clearance_after_mm: float = 0.0
    # The smallest gap between non-adjacent segments at any point in the trajectory. If this
    # stayed above zero, the yarn never touched itself, so it never passed through itself.
    min_gap_seen_mm: float = float("inf")
    crossing_impossible: bool = False
    contacts_resolved: int = 0
    largest_step_mm: float = 0.0
    displacement_cap_mm: float = 0.0
    capped_iterations: int = 0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["length_change_pct"] = (
            100.0 * (self.total_length_after_mm - self.total_length_before_mm)
            / max(self.total_length_before_mm, 1e-9))
        d["bend_energy_drop_pct"] = (
            100.0 * (self.bend_energy_before - self.bend_energy_after)
            / max(self.bend_energy_before, 1e-9))
        return d


def _segment_lengths(pts: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.diff(pts, axis=0), axis=1)


def _bend_energy(pts: np.ndarray) -> float:
    """Sum of squared turning angles. Zero for a straight line, which is yarn at rest."""
    if len(pts) < 3:
        return 0.0
    a = pts[1:-1] - pts[:-2]
    b = pts[2:] - pts[1:-1]
    na = np.linalg.norm(a, axis=1)
    nb = np.linalg.norm(b, axis=1)
    ok = (na > 1e-9) & (nb > 1e-9)
    cos = np.ones(len(a))
    cos[ok] = np.clip(np.einsum("ij,ij->i", a[ok], b[ok]) / (na[ok] * nb[ok]), -1.0, 1.0)
    return float((np.arccos(cos) ** 2).sum())


def _min_clearance(pts: np.ndarray, skip: int = 3) -> float:
    """Closest approach between parts of the path that are not neighbours along it."""
    n = len(pts)
    step = max(1, n // 700)
    s = pts[::step]
    idx = np.arange(0, n, step)
    d = np.linalg.norm(s[:, None, :] - s[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    d[np.abs(idx[:, None] - idx[None, :]) <= skip * step] = np.inf
    return float(d.min()) if np.isfinite(d).any() else float("inf")


# A single contact correction may not move an endpoint by more than this fraction of the
# separation it is correcting towards. Without it the correction diverges at small
# separations.
_MAX_CONTACT_GAIN = 0.35

# Inextensibility is projected this many times per iteration, after contact. Contact moves
# points without regard to yarn length, so the length constraint needs enough passes to
# take that back before the next iteration builds on it.
_LENGTH_PASSES = 8

_NEIGHBOURHOOD = tuple((i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1))


def _segment_contacts(pts: np.ndarray, reach: float, yarn_diameter: float):
    """Closest approach between pairs of yarn SEGMENTS, not pairs of vertices.

    This is the difference between contact that works and contact that does not. Consecutive
    key points here sit about 1.6mm apart while the contact radius is about 2mm, so two
    strands can cross clean between one vertex and the next without any vertex pair ever
    coming close. Vertex-to-vertex contact saw nothing and bending straightened strands
    directly through one another: 42 of 42 linkages destroyed in a run whose contact was
    "active" the whole time. Segment-to-segment distance is what the yarn-level literature
    computes, for this reason.

    Returns the two segment indices, the closest-point parameters along each, and the
    separation, for every pair closer than `reach`.
    """
    a0, a1 = pts[:-1], pts[1:]
    d = a1 - a0
    seg_len = np.linalg.norm(d, axis=1)
    live = seg_len > 1e-6          # the joins are microns long; they are not segments
    mid = 0.5 * (a0 + a1)
    # Exclusion by ARC LENGTH along the yarn, not by index. A strand doubling back on itself
    # inside one stitch really is touching itself there, and that is a bend rather than an
    # interpenetration; index distance cannot tell the two apart when segments run from
    # microns to millimetres. pi * radius is the tightest half-bend the yarn can make.
    arc = np.concatenate([[0.0], np.cumsum(seg_len)])
    arc_mid = 0.5 * (arc[:-1] + arc[1:])
    apart = np.pi * (yarn_diameter / 2.0)

    cell_size = max(reach + float(seg_len.max()), 1e-6)
    cell = np.floor(mid / cell_size).astype(np.int64)
    buckets: dict[tuple, list[int]] = {}
    for i, key in enumerate(map(tuple, cell)):
        if live[i]:
            buckets.setdefault(key, []).append(i)

    out_i: list[int] = []
    out_j: list[int] = []
    for key, members in buckets.items():
        near: list[int] = []
        for off in _NEIGHBOURHOOD:
            near.extend(buckets.get((key[0] + off[0], key[1] + off[1], key[2] + off[2]), ()))
        if not near:
            continue
        for i in members:
            for j in near:
                if j - i > 1 and abs(arc_mid[j] - arc_mid[i]) > apart:
                    out_i.append(i)
                    out_j.append(j)
    if not out_i:
        e = np.empty(0, np.int64)
        f = np.empty(0, np.float64)
        return e, e, f, f, f

    i = np.asarray(out_i)
    j = np.asarray(out_j)
    s_par, t_par, dist = _closest_between_segments(a0[i], d[i], a0[j], d[j])
    keep = dist < reach
    return i[keep], j[keep], s_par[keep], t_par[keep], dist[keep]


def _closest_between_segments(p, u, q, v):
    """Closest points between two batches of segments p+s*u and q+t*v, s,t in [0,1]."""
    w = p - q
    a = np.einsum("ij,ij->i", u, u)
    b = np.einsum("ij,ij->i", u, v)
    c = np.einsum("ij,ij->i", v, v)
    dd = np.einsum("ij,ij->i", u, w)
    e = np.einsum("ij,ij->i", v, w)
    denom = a * c - b * b
    parallel = denom < 1e-12
    safe = np.where(parallel, 1.0, denom)
    s = np.where(parallel, 0.0, (b * e - c * dd) / safe)
    s = np.clip(s, 0.0, 1.0)
    t = (b * s + e) / np.where(c < 1e-12, 1.0, c)
    t = np.clip(t, 0.0, 1.0)
    # One more pass on s now that t is clamped, which is what makes clamped pairs correct.
    s = np.clip((b * t - dd) / np.where(a < 1e-12, 1.0, a), 0.0, 1.0)
    diff = (p + s[:, None] * u) - (q + t[:, None] * v)
    return s, t, np.linalg.norm(diff, axis=1)


def min_segment_separation(pts: np.ndarray, skip: int = 4) -> float:
    """The true closest approach between non-adjacent yarn SEGMENTS.

    Not sampled vertices. This number is what the non-crossing guarantee is built on, so it
    has to be the real minimum over segment pairs rather than an estimate from a subsample.
    """
    a0 = pts[:-1]
    d = np.diff(pts, axis=0)
    seg_len = np.linalg.norm(d, axis=1)
    live = seg_len > 1e-6
    if not live.any():
        return float("inf")
    mid = 0.5 * (a0 + pts[1:])
    reach = float(seg_len.max()) * 2.0 + 1.0
    cell = np.floor(mid / reach).astype(np.int64)
    buckets: dict[tuple, list[int]] = {}
    for i, key in enumerate(map(tuple, cell)):
        if live[i]:
            buckets.setdefault(key, []).append(i)
    best = float("inf")
    for key, members in buckets.items():
        near: list[int] = []
        for off in _NEIGHBOURHOOD:
            near.extend(buckets.get((key[0] + off[0], key[1] + off[1], key[2] + off[2]), ()))
        if not near:
            continue
        ii, jj = [], []
        for i in members:
            for j in near:
                if j - i > skip:
                    ii.append(i)
                    jj.append(j)
        if not ii:
            continue
        i = np.asarray(ii)
        j = np.asarray(jj)
        _, _, dist = _closest_between_segments(a0[i], d[i], a0[j], d[j])
        if len(dist):
            best = min(best, float(dist.min()))
    return best



def apply_contacts(pts, yarn_diameter, rest_sep, floor_sep):
    """Push apart strands that are resting on one another. Returns how many pairs it moved.

    Extracted from `relax` so that the drape solver uses THIS code rather than a copy of it.
    Two implementations of contact would be two places for the floor, the gain and the clamp
    to drift apart, and a second copy that quietly disagreed about when yarn is being
    squeezed too hard is exactly how a solver starts pushing strands through their
    neighbours.
    """
    seg_i, seg_j, sp, tp, dist = _segment_contacts(pts, rest_sep, yarn_diameter)
    if not len(seg_i):
        return 0
    pa = pts[seg_i] + sp[:, None] * (pts[seg_i + 1] - pts[seg_i])
    pb = pts[seg_j] + tp[:, None] * (pts[seg_j + 1] - pts[seg_j])
    delta = pa - pb
    n = np.linalg.norm(delta, axis=1)
    n[n < 1e-9] = 1e-9
    want = np.where(dist < floor_sep, floor_sep, rest_sep)
    gain = np.where(dist < floor_sep, 1.0, 0.5)
    grow = np.minimum((want - n) / n * gain, _MAX_CONTACT_GAIN)
    push = grow[:, None] * delta * 0.5
    for idx, w in ((seg_i, 1.0 - sp), (seg_i + 1, sp)):
        np.add.at(pts, idx, +push * w[:, None])
    for idx, w in ((seg_j, 1.0 - tp), (seg_j + 1, tp)):
        np.add.at(pts, idx, -push * w[:, None])
    return len(seg_i)


def project_lengths(pts, rest, passes=_LENGTH_PASSES, fixed=None):
    """Hold every segment at the length the certified geometry was built with.

    `fixed` marks vertices a boundary condition holds in place. They must not be moved by the
    projection, so a segment with one fixed end gives its whole correction to the free end.
    Splitting the correction evenly and then resetting the fixed vertices afterwards -- which
    is the obvious way to write this -- silently undoes half of every correction at the
    boundary, and the error accumulates along the clamped edge rather than staying local.
    """
    if fixed is None:
        w0 = w1 = None
    else:
        free = (~fixed).astype(float)
        share = free[:-1] + free[1:]
        share[share < 1e-9] = 1e-9
        w0 = free[:-1] / share
        w1 = free[1:] / share
    for _ in range(passes):
        d = np.diff(pts, axis=0)
        ln = np.linalg.norm(d, axis=1)
        ln[ln < 1e-9] = 1e-9
        corr = ((ln - rest) / ln)[:, None] * d
        if w0 is None:
            pts[:-1] += corr * 0.5
            pts[1:] -= corr * 0.5
        else:
            pts[:-1] += corr * w0[:, None]
            pts[1:] -= corr * w1[:, None]
    return pts


def relax(fab: topo.Fabric, material: Material | None = None, *,
          iterations: int = 400,
          tolerance_mm: float = 1e-3) -> tuple[topo.Fabric, RelaxationReport]:
    """Let the yarn find equilibrium, without letting it find one through itself.

    Three constraints, projected in turn until the path stops moving:

    INEXTENSIBILITY. Each segment is held at the length it was built with. Yarn stretches
    very little, and the lengths of the certified path are the one physical quantity here
    that is measured rather than estimated, so they are the hardest constraint.

    BENDING towards STRAIGHT. This is the engine. Unstressed yarn is straight, so every part
    of the path is pulled towards its neighbours' midpoint. Relaxing towards the authored
    curvature instead would only re-assert the shape that was drawn, which is the thing this
    module exists to stop doing. With length fixed and contact holding, a loop pulled towards
    straightness has nowhere to go but tighter -- which is what yarn tension IS, and it is
    where row nesting and compaction come from rather than from anybody placing them.

    CONTACT. Strands resting on each other are pushed apart towards the separation two
    touching strands sit at, and are never allowed inside the floor where yarn cannot be
    squeezed further. Published measurements of weft knits show yarn widths reducing by
    19-39% under strain, so the floor is an observation about textiles rather than a number
    that made the picture work.

    PULL-THROUGH. Contact makes passing through expensive; the displacement cap makes it
    geometrically hard. No vertex may move more than a fraction of the CURRENT smallest
    clearance in a single iteration, so no strand can cross another between one look at the
    geometry and the next. This is a sufficient condition enforced each iteration, not a
    formal continuous-collision proof, and it is deliberately backed by running the real
    topology validators afterwards. Nothing here repairs topology; the validators report it.
    """
    material = material or material_for(fab)
    pts = fab.points.copy()
    if len(pts) < 4:
        return fab, RelaxationReport()

    rest = _segment_lengths(pts)
    rest[rest < 1e-9] = 1e-9

    report = RelaxationReport()
    report.total_length_before_mm = float(rest.sum())
    report.bend_energy_before = _bend_energy(pts)
    report.min_clearance_before_mm = _min_clearance(pts)
    report.max_strain_before = 0.0

    rest_sep = material.rest_separation_mm
    floor_sep = material.floor_separation_mm

    for it in range(iterations):
        before = pts.copy()

        # THE NON-CROSSING GUARANTEE.
        #
        # Topology is preserved here by construction, not by measuring it afterwards. If no
        # vertex moves further than half the current smallest gap between two non-adjacent
        # segments, then no two strands can close that gap: each can travel at most half of
        # it, so they meet only in the limit and never cross. Enforcing that every step
        # means the yarn cannot pass through itself at any point in the trajectory, which is
        # the hard invariant stated directly rather than checked for afterwards.
        #
        # This replaced a cap derived from a sampled vertex-to-vertex clearance. That number
        # was not the real minimum and gave no guarantee of anything.
        gap, _ = topo.min_segment_separation(pts, fab.yarn_diameter)
        cap = max(min(0.45 * gap, 0.5 * float(np.median(rest))), 1e-5)
        report.min_gap_seen_mm = min(report.min_gap_seen_mm, gap)
        report.displacement_cap_mm = cap

        # --- bending towards straight ------------------------------------------
        # Laplacian: pull each interior point towards the midpoint of its neighbours. That
        # is a discrete bending force whose rest state is a straight line.
        lap = np.zeros_like(pts)
        lap[1:-1] = 0.5 * (pts[:-2] + pts[2:]) - pts[1:-1]
        pts += lap * material.bend_compliance

        # --- contact ------------------------------------------------------------
        moved = apply_contacts(pts, fab.yarn_diameter, rest_sep, floor_sep)
        report.contacts_resolved += moved

        # --- inextensibility -----------------------------------------------------
        # Last, and iterated, because it is the constraint allowed to win.
        pts = project_lengths(pts, rest)

        # --- the cap --------------------------------------------------------------
        step = pts - before
        mag = np.linalg.norm(step, axis=1)
        worst = float(mag.max()) if len(mag) else 0.0
        capped_this_pass = worst > cap
        if capped_this_pass:
            report.capped_iterations += 1
            pts = before + step * (cap / worst)
            worst = cap
        report.largest_step_mm = max(report.largest_step_mm, worst)
        report.iterations = it + 1
        # Converged means the geometry stopped moving of its own accord. An iteration whose
        # step was cut by the cap has not stopped moving; it was stopped, and calling that
        # equilibrium is how the first version reported success after one pass.
        if worst < tolerance_mm and not capped_this_pass:
            report.converged = True
            break

    after = _segment_lengths(pts)
    report.total_length_after_mm = float(after.sum())
    # Per segment, against its own rest length. Dividing the largest absolute error by the
    # SHORTEST segment in the path compares each error to something unrelated to it.
    # Segments long enough to have a meaningful strain. The joins between stitches are
    # microns long by construction, and dividing their error by their length reported a
    # strain of 2320 for a path that had barely moved.
    real = rest > 0.05
    report.max_strain_after = float((np.abs(after[real] - rest[real]) / rest[real]).max())
    report.bend_energy_after = _bend_energy(pts)
    report.min_clearance_after_mm = _min_clearance(pts)
    final_gap, _ = topo.min_segment_separation(pts, fab.yarn_diameter)
    report.min_gap_seen_mm = min(report.min_gap_seen_mm, final_gap)
    # Stated as what it is: a guarantee that held, or did not.
    report.crossing_impossible = report.min_gap_seen_mm > 0.0

    out = topo.Fabric(L=fab.L, H=fab.H, D=fab.D, yarn_diameter=fab.yarn_diameter)
    at = 0
    for o in fab.ops:
        n = len(o.points)
        out.ops.append(replace(o, points=pts[at:at + n]))
        at += n
    return out, report
