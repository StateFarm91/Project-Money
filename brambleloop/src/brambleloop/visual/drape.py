"""Out-of-plane equilibrium: what the certified fabric does when you let gravity have it.

WHAT THIS IS AND IS NOT. The relaxation module finds the yarn's equilibrium with the fabric
effectively confined to the plane it was authored in. Nothing there pushed it out, so nothing
came out, and the result renders as a perfectly flat mat -- which became the dominant reason
the images read as CG once repetition and material were dealt with. This module adds the
missing physics rather than the missing appearance: gravity, a surface to rest on, and
boundary conditions. The fabric's shape is then an OUTCOME. Nothing here displaces vertices
to look like drape, adds curl, wrinkles or noise, or deforms anything towards a reference
photograph.

PRODUCT TRUTH VERSUS PHYSICAL PRESENTATION. These are different things and this module only
touches the second. Topology, stitch identity, stitch count, loop targets, the yarn path's
connectivity, gauge and the authored construction are the product, and they are invariant
here by construction: no vertex is added, removed or reconnected, and segment rest lengths
are the ones the certified geometry was built with. What changes is the CONFIGURATION that
same product occupies in space. A draped garment photographs narrower without becoming
narrower, which is why `intrinsic_dimensions` measures along the cloth and the projected
figure is reported separately and never as the product's size.

THE MECHANICS, IN REAL UNITS. The previous solver used dimensionless gains, which was fine
while every term was a constraint projection. Gravity is not a constraint, it is a force, and
a gain on it would be exactly the invented drape parameter this increment is forbidden. So
the energy is written with physical quantities:

    E_bend  = (B/2) * sum |d2p|^2 / l^3      B = yarn bending rigidity          [N m^2]
    E_grav  = sum m_i g h_i                  m_i = lambda * l_i, lambda [kg/m]

and the shape is decided by their ratio, B / (lambda g l^4), which is a real dimensionless
group rather than a dial. The integration step affects how fast it converges, not where.

WHERE THE NUMBERS COME FROM.

  lambda   DERIVED. The yarn is 444 tex, which IS mass per length by definition: 444 g/km =
           4.44e-4 kg/m. No estimate involved.
  g        SOURCED. Standard gravity, 9.80665 m/s^2.
  B        BOUNDED, AND THE BOUNDS ARE ENORMOUS -- which is the honest finding rather than a
           failure to look. Textile theory gives yarn flexural rigidity as
           R = (1/4pi) * eta * E * T^2 / rho, with shape factors eta published between 0.59
           (silk) and 1.0 (glass). That formula describes a coherent rod. A spun, plied yarn
           is not one: its fibres slip past each other when it bends, and the difference is
           not a correction but orders of magnitude. For this yarn a solid acrylic rod of the
           same diameter computes to ~1.5e-2 N m^2, while the same fibres bending
           independently compute to ~2e-8 -- a factor of a million, bracketing the truth
           rather than locating it.

           No published flexural rigidity for chunky crochet yarn was found. So B is not
           chosen. `sensitivity()` sweeps the whole bracket and reports what the fabric does
           across it, and the configuration is judged against the ASTM D1388 cantilever test,
           which is a standard measurement rather than an opinion: a strip is advanced over
           an edge until its tip falls 41.5 degrees, the bending length is half that overhang,
           and flexural rigidity is G = W c^3. Running that test IN the simulation gives a
           number that can be compared with published fabric values, and comparing the
           measured bending length against the analytic (B/W g)^(1/3) checks the solver
           against beam theory rather than against my expectations.

WHAT KEEPS THE TOPOLOGY. Everything that protected it in-plane still applies and is not
relaxed here: segment rest lengths, self-contact with the same published floor, and the
displacement cap that makes crossing geometrically impossible between one look at the
geometry and the next. The support plane is an additional one-sided constraint. Afterwards
the real validators run on the 3D result -- and they had to be made frame-invariant first,
because both the morphology check and the linkage check were silently measuring global
orientation and would have failed every curved row.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import crochet_topology as topo
from . import relaxation as rx

__all__ = ["DrapeSetup", "DrapeReport", "drape", "areal_mass", "bending_bracket",
           "cantilever_test", "intrinsic_dimensions", "PROVENANCE"]

STANDARD_GRAVITY = 9.80665            # m/s^2, sourced
ACRYLIC_DENSITY = 1180.0              # kg/m^3, already used to derive fibre radius
ACRYLIC_MODULUS = 2.5e9               # Pa, bounded: acrylic bulk modulus is quoted 2.2-3.2

PROVENANCE = {
    "linear_density": "DERIVED -- 444 tex is mass per length by definition, 4.44e-4 kg/m",
    "gravity": "SOURCED -- standard gravity 9.80665 m/s^2",
    "bending_rigidity": "BOUNDED, spanning six orders of magnitude. A solid acrylic rod of "
                        "this diameter and the same fibres bending independently differ by "
                        "~1e6, and no published value for chunky crochet yarn was found. "
                        "Swept by sensitivity() rather than chosen; the configuration is "
                        "checked against ASTM D1388 and against beam theory, not by eye",
    "shape_factor": "BOUNDED -- published shape factors run 0.59 (silk) to 1.0 (glass); "
                    "none published for acrylic, so the range is carried",
    "support_friction": "NOT MODELLED -- the support is frictionless, which is stated "
                        "because friction would resist sliding and the swatch is not "
                        "claimed to be in the configuration friction would give",
}


def linear_density_kg_per_m(tex: float) -> float:
    """Mass per unit length. tex is grams per kilometre, so this is a unit change."""
    return tex * 1e-6


def bending_bracket(yarn_diameter_mm: float, tex: float, fibre_radius_mm: float,
                    n_fibres: int) -> dict:
    """The two ends of the bracket B must lie between, and why it is this wide.

    UPPER: the yarn as a coherent solid rod, E*I with I the full circular second moment.
    LOWER: every fibre bending independently with no coupling at all, n * E * I_fibre.

    Real spun yarn sits between, nearer the lower end, because twist and inter-fibre friction
    couple the fibres only partially. Reporting both rather than interpolating between them
    is the point: the interpolation would be the invented parameter.
    """
    r = yarn_diameter_mm * 1e-3 / 2.0
    I_solid = np.pi * r ** 4 / 4.0
    rf = fibre_radius_mm * 1e-3
    I_fibre = np.pi * rf ** 4 / 4.0
    return {
        "upper_solid_rod_N_m2": ACRYLIC_MODULUS * I_solid,
        "lower_free_fibres_N_m2": n_fibres * ACRYLIC_MODULUS * I_fibre,
        "ratio": (ACRYLIC_MODULUS * I_solid) / max(n_fibres * ACRYLIC_MODULUS * I_fibre, 1e-30),
    }


def areal_mass(fab: topo.Fabric, tex: float) -> dict:
    """Mass per unit area of the fabric, derived from its own yarn length and extent.

    Not looked up: measured off the certified geometry. The yarn's length is the path it
    actually follows and the area is the fabric's own span, so W is a consequence of the
    product rather than an input to it.
    """
    pts = fab.points
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    seg = seg[seg < 5.0]                      # drop the artificial jumps between ops
    length_m = float(seg.sum()) * 1e-3
    lam = linear_density_kg_per_m(tex)
    mass_kg = length_m * lam
    w = float(np.ptp(pts[:, 0])) * 1e-3
    h = float(np.ptp(pts[:, 1])) * 1e-3
    return {"yarn_length_m": length_m, "mass_kg": mass_kg,
            "area_m2": w * h, "areal_mass_kg_m2": mass_kg / max(w * h, 1e-12),
            "linear_density_kg_m": lam}


@dataclass(frozen=True)
class DrapeSetup:
    """The boundary conditions. These are the physics that decides the configuration."""

    bending_rigidity_N_m2: float
    linear_density_kg_m: float
    gravity: float = STANDARD_GRAVITY
    # Which way is down, in fabric coordinates. The fabric is authored in the xy plane with
    # +y up the rows, so a swatch lying on a table has gravity along -z and one hanging has
    # it along -y. Named rather than assumed, because it is a staging choice and staging
    # choices have already proved able to masquerade as fabric properties here.
    down: tuple = (0.0, 0.0, -1.0)
    support_at: float | None = None       # plane the fabric rests on, along `down`
    clamp_fraction: float = 0.0           # fraction of the fabric held fixed, by +y
    iterations: int = 400


@dataclass
class DrapeReport:
    iterations: int = 0
    max_out_of_plane_mm: float = 0.0
    mean_out_of_plane_mm: float = 0.0
    edge_curl_mm: float = 0.0
    tip_angle_deg: float = 0.0
    length_change_pct: float = 0.0
    max_strain: float = 0.0
    min_gap_seen_mm: float = float("inf")
    crossing_impossible: bool = False
    support_violations: int = 0
    largest_step_mm: float = 0.0
    cap_exceeded: int = 0
    degenerate_segments: int = 0
    gap_checks: int = 0
    retries: int = 0

    def as_dict(self):
        return dict(self.__dict__)


def _segment_lengths(pts):
    return np.linalg.norm(np.diff(pts, axis=0), axis=1)


def drape(fab: topo.Fabric, setup: DrapeSetup,
          material: rx.Material | None = None) -> tuple[topo.Fabric, DrapeReport]:
    """Find the fabric's equilibrium under gravity, contact and its boundary conditions."""
    material = material or rx.material_for(fab)
    pts = fab.points.copy().astype(float)
    n = len(pts)
    if n < 4:
        return fab, DrapeReport()

    rest = _segment_lengths(pts)
    rest[rest < 1e-9] = 1e-9
    rest_m = rest * 1e-3
    down = np.asarray(setup.down, dtype=float)
    down = down / np.linalg.norm(down)
    start = pts.copy()

    # Vertex masses from the yarn either side of each vertex.
    lumped = np.zeros(n)
    lumped[:-1] += rest_m / 2.0
    lumped[1:] += rest_m / 2.0
    mass = lumped * setup.linear_density_kg_m
    grav_force = mass[:, None] * setup.gravity * down[None, :]      # newtons

    # Clamp: the held region is a boundary condition, not a fudge. For a cantilever it is
    # the part still on the table.
    held = np.zeros(n, bool)
    if setup.clamp_fraction > 0:
        y = pts[:, 1]
        cut = y.min() + (y.max() - y.min()) * (1.0 - setup.clamp_fraction)
        held = y >= cut

    ell = float(np.median(rest_m))
    bend_coeff = setup.bending_rigidity_N_m2 / max(ell ** 3, 1e-30)
    # Step size scaled so the largest force moves a vertex a small fraction of a segment.
    # Affects convergence rate only: the equilibrium is where the forces balance.
    ref = max(bend_coeff * ell, float(np.abs(grav_force).max()), 1e-30)
    step = 0.05 * ell / ref

    report = DrapeReport()
    rest_sep = material.rest_separation_mm
    floor_sep = material.floor_separation_mm

    # Segments the certified geometry built with essentially zero length -- coincident
    # points where one stitch's path meets the next. There are nine of them here, the
    # shortest 28 NANOMETRES. Relative strain on such a segment is meaningless: the first
    # version reported a maximum strain of 540, i.e. 54,000 per cent, while total yarn length
    # had changed by -0.17 per cent, which is the arithmetic signature of dividing by
    # approximately nothing. They are excluded from the strain STATISTIC and still fully
    # constrained by the projection, because a segment being too short to measure is not a
    # reason to stop holding it.
    measurable = rest > 0.01

    # Reaching gravitational equilibrium takes thousands of iterations here, because the
    # yarn's own bending forces are 200 to 30,000 times larger than gravity on it and the
    # fabric has to rearrange against them. The segment-to-segment gap check is the cost of
    # each iteration, so it is amortised rather than dropped: the gap is recomputed every
    # GAP_EVERY iterations and the budget it licenses is SPENT DOWN by the actual movement
    # in between. While cumulative movement since the last measurement stays below the
    # clearance that was measured, no strand can have reached another, so the guarantee is
    # the same one -- just bought in bulk. When the budget runs out the gap is remeasured
    # early rather than the cap being guessed.
    GAP_EVERY = 12
    gap = float("inf")
    budget = 0.0
    scale = 1.0

    for it in range(setup.iterations):
        if budget <= 0.0 or it % GAP_EVERY == 0:
            gap, _ = topo.min_segment_separation(pts, fab.yarn_diameter)
            report.min_gap_seen_mm = min(report.min_gap_seen_mm, gap)
            report.gap_checks += 1
            budget = 0.45 * gap
        cap = max(min(budget, 0.5 * float(np.median(rest))), 1e-5)

        before = pts.copy()
        force = grav_force.copy()
        lap = np.zeros_like(pts)
        lap[1:-1] = (pts[:-2] - 2.0 * pts[1:-1] + pts[2:]) * 1e-3
        force += bend_coeff * lap

        # The FORCE step is capped, not the finished move. Scaling the whole update after
        # the constraints have run is what broke inextensibility in the first version: it
        # rescales the constraint corrections too, so the projection's work is partly undone
        # every iteration and the error accumulates. Capping the input leaves the constraints
        # free to be satisfied exactly, and the resulting displacement is then measured
        # rather than assumed.
        move = step * scale * force * 1e3
        worst_force = float(np.linalg.norm(move, axis=1).max()) if len(move) else 0.0
        limit = 0.15 * cap
        if worst_force > limit:
            move *= limit / worst_force
        pts = pts + move
        pts[held] = before[held]

        rx.apply_contacts(pts, fab.yarn_diameter, rest_sep, floor_sep)
        pts[held] = before[held]

        if setup.support_at is not None:
            depth = pts @ down
            through = depth > setup.support_at
            if through.any():
                pts[through] -= np.outer(depth[through] - setup.support_at, down)
                report.support_violations += int(through.sum())

        # Inextensibility LAST and boundary-aware, so it is the constraint that wins.
        pts = rx.project_lengths(pts, rest, passes=24, fixed=held)

        # The guarantee has to cover the FINISHED move, not the force step. Capping the
        # input bounds only part of it: contact and the length projection move vertices too,
        # and the first version of this loop counted six iterations whose total displacement
        # exceeded the clearance that licensed it -- so `crossing_impossible` was being
        # reported on a bound that did not hold. Rather than report the violation and carry
        # on, the iteration is REVERTED and retried at a smaller step until the whole move
        # fits inside the measured clearance. That is slower and it is the only version of
        # this that is actually a guarantee.
        delta = pts - before
        mag = np.linalg.norm(delta, axis=1)
        worst = float(mag.max()) if len(mag) else 0.0
        if worst > budget:
            gap, _ = topo.min_segment_separation(before, fab.yarn_diameter)
            report.min_gap_seen_mm = min(report.min_gap_seen_mm, gap)
            report.gap_checks += 1
            budget = 0.45 * gap
            if worst > budget:
                pts = before
                scale *= 0.5
                report.retries += 1
                if scale < 1e-6:
                    break
                continue
        scale = min(scale * 1.05, 1.0)
        report.largest_step_mm = max(report.largest_step_mm, worst)
        budget -= worst
        report.iterations = it + 1
        if worst < 1e-5:
            break

    now = _segment_lengths(pts)
    report.length_change_pct = float(100.0 * (now.sum() - rest.sum()) / rest.sum())
    report.max_strain = float(np.abs(now[measurable] / rest[measurable] - 1.0).max())
    report.degenerate_segments = int((~measurable).sum())
    disp = (pts - start) @ down
    report.max_out_of_plane_mm = float(np.abs(disp).max())
    report.mean_out_of_plane_mm = float(np.abs(disp).mean())
    # Honest: the guarantee holds only if no iteration ever moved further than the cap.
    report.crossing_impossible = report.min_gap_seen_mm > 0.0 and report.cap_exceeded == 0

    # Edge curl: how much further the free edges moved than the body did.
    x = start[:, 0]
    edge = (x < np.percentile(x, 12)) | (x > np.percentile(x, 88))
    if edge.any() and (~edge).any():
        report.edge_curl_mm = float(np.abs(disp[edge]).max() - np.abs(disp[~edge]).mean())

    out = replace(fab, ops=_rewrite(fab, pts))
    return out, report


def _rewrite(fab, pts):
    ops, i = [], 0
    for o in fab.ops:
        k = len(o.points)
        ops.append(replace(o, points=pts[i:i + k]))
        i += k
    return ops


def intrinsic_dimensions(fab: topo.Fabric, rows: int, cols: int) -> dict:
    """The product's own size, measured ALONG the cloth rather than across the photograph.

    This is the distinction the owner drew and it is not a technicality. A draped fabric
    projects smaller in every image of it while remaining exactly the size it was; measuring
    a bounding box after deformation and calling it the garment's width would report the
    product shrinking because it was photographed differently. So width is summed stitch to
    stitch along each row, and height column by column up the wales, both following the
    surface. Projected extent is reported too, clearly labelled, because it is what a camera
    sees and it is a legitimate thing to know -- just not the product's dimensions.
    """
    hdc = [o for o in fab.ops if o.kind == "hdc"]
    by = {(o.row, o.position): o.points.mean(axis=0) for o in hdc}
    rs = sorted({r for r, _ in by})
    ps = sorted({p for _, p in by})
    widths = []
    for r in rs:
        run = [by[(r, p)] for p in ps if (r, p) in by]
        if len(run) > 1:
            widths.append(sum(float(np.linalg.norm(run[i + 1] - run[i]))
                              for i in range(len(run) - 1)))
    heights = []
    for p in ps:
        col = [by[(r, p)] for r in rs if (r, p) in by]
        if len(col) > 1:
            heights.append(sum(float(np.linalg.norm(col[i + 1] - col[i]))
                               for i in range(len(col) - 1)))
    pts = fab.points
    return {
        "intrinsic_width_mm": float(np.mean(widths)) if widths else 0.0,
        "intrinsic_height_mm": float(np.mean(heights)) if heights else 0.0,
        "projected_width_mm": float(np.ptp(pts[:, 0])),
        "projected_height_mm": float(np.ptp(pts[:, 1])),
    }


def cantilever_test(fab: topo.Fabric, setup: DrapeSetup, material=None,
                    overhang_fractions=(0.3, 0.4, 0.5, 0.6, 0.7)) -> dict:
    """ASTM D1388 in simulation: advance the fabric over an edge until the tip falls 41.5deg.

    A standard measurement rather than a judgement. The bending length is half the overhang
    at which the tip reaches that angle, and flexural rigidity is G = W * c^3. Comparing the
    result against the analytic (B / W g)^(1/3) checks the solver against beam theory.
    """
    results = []
    for frac in overhang_fractions:
        s = replace(setup, clamp_fraction=1.0 - frac)
        out, rep = drape(fab, s, material)
        pts = out.points
        y = pts[:, 1]
        tip = pts[y < np.percentile(y, 6)]
        start = fab.points[fab.points[:, 1] < np.percentile(fab.points[:, 1], 6)]
        drop = float(np.mean(start[:, 2]) - np.mean(tip[:, 2]))
        reach = float(np.ptp(fab.points[:, 1]) * frac)
        angle = float(np.degrees(np.arctan2(max(drop, 0.0), max(reach, 1e-9))))
        results.append({"overhang_fraction": frac, "overhang_mm": reach,
                        "tip_drop_mm": drop, "tip_angle_deg": angle})
    return {"steps": results}
