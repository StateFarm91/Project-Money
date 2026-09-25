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

HOW B IS FIXED, AND WHY THIS IS CALIBRATION RATHER THAN TUNING. The bracket on yarn bending
rigidity spans a factor of 735,000, so it cannot select a value by itself. The first attempt
to narrow it analytically assumed the fabric's rigidity per unit width was the yarn's divided
by the stitch pitch. The solver disagrees with that by about sixteen times -- at the value
that mapping calls a 33mm bending length, beam theory predicts an 8mm tip deflection and the
solver gives 0.5mm -- so the mapping was a guess, and an earlier argument that used it to
exclude the lower bound was wrong for the same reason.

Yarn-to-fabric homogenisation is the hard part of this problem and is not solved here. So the
calibration is done the other way round, against the quantity that IS bounded by published
measurement: the fabric's bending length. Thin cotton jersey is published at 0.5-1.4cm, and a
6mm-hook chunky crochet is unambiguously stiffer than jersey, which puts a floor near 15mm;
the ceiling comes from crochet of this weight visibly bending at swatch scale, which puts it
below roughly 80mm. The geometric midpoint of that band is 34.6mm.

The solver's own effective bending length is then MEASURED -- deflect a cantilever, invert
delta = l^4 / 8c^3 -- and B is set so that measurement lands on the midpoint. What makes this
calibration rather than taste is that the target is a published fabric property, the free
parameter is the one genuinely unknown to six orders of magnitude, and the answer can be
checked against something it was not fitted to: the resulting B is 1.45 times the free-fibre
lower bound, which is an independent hard floor. A soft chunky acrylic yarn whose fibres are
nearly free to slip, with a little coupling from twist, is exactly where that sits. Had the
calibration demanded a B below the floor, or hundreds of times above it, the model would have
been reported as failing rather than adopted.

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
           "cantilever_test", "intrinsic_dimensions", "CALIBRATED_BENDING_N_M2",
           "PROVENANCE", "rest_curvature_of", "angular_radius_to_lap", "relief_profile"]

STANDARD_GRAVITY = 9.80665            # m/s^2, sourced
ACRYLIC_DENSITY = 1180.0              # kg/m^3, already used to derive fibre radius
ACRYLIC_MODULUS = 2.5e9               # Pa, bounded: acrylic bulk modulus is quoted 2.2-3.2

# The calibrated yarn bending rigidity, derived by the procedure documented above: the
# solver's own effective bending length is measured from a cantilever deflection and this is
# the value that puts it on the geometric midpoint of the 15-80mm band that published jersey
# stiffness and observed crochet behaviour bracket. It comes out at 1.45x the free-fibre hard
# lower bound, a cross-check it was not fitted to.
#
# It lives here and nowhere else. It was briefly a literal in the test suite as well, chosen
# before the calibration existed and left twenty times too stiff afterwards, which showed up
# as a test asserting gravity had moved the fabric while the fabric moved 0.03mm.
CALIBRATED_BENDING_N_M2 = 3.0e-8

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
    "bending_calibration": "CALIBRATED against a published fabric property, not tuned. The "
                           "solver's effective bending length is measured from a cantilever "
                           "deflection and B set so it lands on the geometric midpoint of "
                           "the 15-80mm band that published jersey stiffness and observed "
                           "crochet behaviour bracket. Cross-check it was not fitted to: the "
                           "result is 1.45x the free-fibre hard lower bound",
    "rest_curvature": "The yarn is taken as set in the shape it relaxed into, following the reference method's own split between a relaxation phase and a simulation phase. Measuring bending against straight instead makes every formed loop pre-stressed and the fabric's drape stops responding to its stiffness at all -- tested, not assumed",
    "plastic_rest_migration": "SOURCED mechanism, SOURCED parameter values, DERIVED "
                              "coordinate mapping, UNKNOWN application rate. Kaldor et al. "
                              "2010 S2 3.1 give the two bounded projections and the values "
                              "p_plastic 0.01 and p_max_plastic 2.5 in angular space; the "
                              "map from that angular space onto this solver's "
                              "second-difference rest state is derived exactly for equal "
                              "segments; the rate is applied once per solver iteration and "
                              "this solver's iterations are NOT physical time steps, so "
                              "how much plasticity a run accumulates depends on its "
                              "iteration count. Measured, not assumed away: see "
                              "research/VISUAL_WAVE2.md",
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

    linear_density_kg_m: float
    bending_rigidity_N_m2: float = CALIBRATED_BENDING_N_M2
    gravity: float = STANDARD_GRAVITY
    # Which way is down, in fabric coordinates. The fabric is authored in the xy plane with
    # +y up the rows, so a swatch lying on a table has gravity along -z and one hanging has
    # it along -y. Named rather than assumed, because it is a staging choice and staging
    # choices have already proved able to masquerade as fabric properties here.
    down: tuple = (0.0, 0.0, -1.0)
    support_at: float | None = None       # plane the fabric rests on, along `down`
    # Whether the yarn's REST shape is straight, or the shape it was relaxed into.
    #
    # This is the single most consequential physical choice in the module, so it is named
    # rather than assumed. Measuring bending against straight treats every formed loop as
    # pre-stressed, and since a crochet stitch is nothing but curvature, that internal stress
    # dominates gravity by two to four orders of magnitude and sets the fabric's effective
    # rigidity by itself -- which is exactly what the first sweep showed, with out-of-plane
    # displacement identical across a 160-fold range of bending rigidity. A fabric whose
    # drape does not respond to its own stiffness is not modelling drape.
    #
    # The reference method already separates these two phases: Kaldor et al. relax with a
    # bending constant a thousand times lower than they simulate with, precisely because
    # relaxation is finding the rest state rather than moving about it. The relaxation stage
    # here has already done that, so for drape the yarn is taken as set in the configuration
    # it relaxed into -- which is also what blocking does to a finished piece. Gravity then
    # acts on a fabric at rest instead of fighting a stitch trying to unbend itself.
    rest_is_relaxed_shape: bool = True
    # KALDOR-2010 BOUNDED PLASTIC REST-STATE MIGRATION. OFF BY DEFAULT, deliberately: it
    # changes the fabric's shape, and every committed Visual result was produced without it.
    #
    # The two rest states above BRACKET the problem rather than solving it. Straight makes
    # every formed loop pre-stressed by 200-32,000 times gravity, everts free-edge stitches
    # and leaves drape blind to stiffness. Relaxed keeps the stitches and makes drape respond
    # to stiffness, but freezes the fabric into an elastic plate that resists any departure
    # from one configuration. The published state of the art uses NEITHER: Kaldor, James and
    # Marschner (SIGGRAPH 2010, section 3.1) use inextensible rods with a non-straight rest
    # configuration PLUS a plasticity model on the rest state --
    #
    #   "If the rest state (represented as a 2D point) at a segment/bending element pair lies
    #    outside the circle of radius p_plastic centered at the current state of that pair,
    #    the rest state is projected onto the boundary of the circle. Similarly, if the rest
    #    state falls outside the circle of radius p_max_plastic centered at the origin, it is
    #    projected onto the boundary."
    #
    # with reported parameters 0.01 and 2.5. [SOURCED, S2 3.1 and Table; quoted in
    # research/YARN_SLIP_RESEARCH.md section 8(e)]
    #
    # WHAT IT CHANGES MECHANICALLY. The rest curvature is dragged toward the current
    # curvature but is never allowed closer than p_plastic to it, so at steady state the
    # fabric carries a BOUNDED prestress of p_plastic radians whose direction opposes
    # whichever curvature change last happened -- a yield-stress-like resistance rather than
    # a spring pulling back to one remembered shape. p_max_plastic then caps how curved the
    # rest state may become in absolute terms.
    #
    # WHAT IT IS NOT. It is not yarn sliding and it is not a conformability MECHANISM; the
    # research ranked it fourth and called it an interim fix for the rest-state bracket,
    # explicitly noting the fabric remains an elastic plate. Milestone D does not turn on it.
    #
    # LABELS. Mechanism: SOURCED. Both parameter values: SOURCED. The mapping from Kaldor's
    # angular space to this solver's second-difference rest state: DERIVED (exact for equal
    # segments, see angular_radius_to_lap). The application RATE: UNKNOWN -- Kaldor apply the
    # projections once per dynamic time step, and this solver's iterations are a quasi-static
    # descent rather than physical time, so the plasticity a run accumulates depends on its
    # iteration count. That dependence is measured in research/VISUAL_WAVE2.md rather than
    # assumed away.
    plastic_rest_migration: bool = False
    p_plastic_rad: float = 0.01
    p_max_plastic_rad: float = 2.5
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
    # Convergence instruments. `largest_step_mm` is the maximum over the whole run, which
    # cannot distinguish a solve that finished from one that ran out of iterations still
    # moving -- and that distinction turned out to be the whole ASTM cantilever result.
    final_step_mm: float = 0.0
    converged: bool = False
    # How far the plastic rest state actually migrated, so the option cannot be believed to
    # have done something without being measured. Angular by the same DERIVED mapping.
    rest_migration_max_rad: float = 0.0
    rest_migration_mean_rad: float = 0.0

    def as_dict(self):
        return dict(self.__dict__)


def _segment_lengths(pts):
    return np.linalg.norm(np.diff(pts, axis=0), axis=1)


def _laplacian(pts):
    """The discrete second difference, in metres: the curvature measure the bending force is
    written against, and the quantity Kaldor's plasticity acts on. One definition, one place,
    because it was previously written out twice in this file -- once for the rest state and
    once inside the loop -- and two copies of a physical definition is how a stale constant
    becomes indistinguishable from a real result."""
    lap = np.zeros_like(pts)
    lap[1:-1] = (pts[:-2] - 2.0 * pts[1:-1] + pts[2:]) * 1e-3
    return lap


def rest_curvature_of(fab: topo.Fabric) -> np.ndarray:
    """The rest curvature a fabric in THIS configuration would be taken as set in.

    This exists because a recovery experiment cannot be run without it, and the first attempt
    at one was invalid for exactly this reason. `rest_is_relaxed_shape` captures the rest
    curvature at the START of the call it is used in, so releasing gravity on an
    already-draped fabric takes the DRAPED shape as its own rest state: there is no restoring
    force by construction, and the experiment cannot detect recovery either way, whichever
    answer is true. Capture this from the FLAT fabric and pass it to
    `drape(rest_curvature=...)` to hold one rest state fixed across both calls.
    """
    return _laplacian(fab.points.astype(float))


def angular_radius_to_lap(theta_rad: float, ell_m: float) -> float:
    """Convert one of Kaldor's angular plasticity radii into this solver's rest-state units.

    Their rest state is a 2D point in ANGULAR space; ours is a second difference in metres.
    For two segments of equal length l meeting at turning angle theta,

        |p_{i-1} - 2 p_i + p_{i+1}| = 2 l sin(theta/2)

    exactly -- so this is a change of variable rather than a small-angle linearisation, which
    matters because a crochet loop's turning angles are not small. DERIVED.

    The honest residual: the second-difference VECTOR also carries a component along the
    segment direction, which is length variation rather than turning angle, so the ball this
    radius defines is three-dimensional where Kaldor's is two. The length projection keeps
    that third component small rather than zero, and this is the one part of the mapping that
    is an approximation rather than an identity.
    """
    return 2.0 * ell_m * float(np.sin(0.5 * min(float(theta_rad), np.pi)))


def _migrate_rest(lap_rest, lap, r_rel, r_abs):
    """One step of Kaldor 2010's bounded plastic rest-state migration, in this solver's
    curvature representation and in their order: project onto the ball of radius `r_rel`
    around the CURRENT curvature, then onto the ball of radius `r_abs` around the ORIGIN.
    [SOURCED, S2 3.1]"""
    out = lap_rest.copy()
    d = out - lap
    nd = np.linalg.norm(d, axis=1)
    over = nd > r_rel
    if over.any():
        out[over] = lap[over] + d[over] * (r_rel / nd[over])[:, None]
    nr = np.linalg.norm(out, axis=1)
    over2 = nr > r_abs
    if over2.any():
        out[over2] *= (r_abs / nr[over2])[:, None]
    return out


def drape(fab: topo.Fabric, setup: DrapeSetup,
          material: rx.Material | None = None,
          rest_curvature: np.ndarray | None = None) -> tuple[topo.Fabric, DrapeReport]:
    """Find the fabric's equilibrium under gravity, contact and its boundary conditions.

    `rest_curvature`, when given, is the rest state to bend against, as produced by
    `rest_curvature_of`. It overrides `setup.rest_is_relaxed_shape`, and it is the only way to
    carry ONE rest state across two calls -- which any recovery or load-cycle experiment
    requires and which the capture-at-call-start default cannot express.
    """
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

    # The curvature the yarn is at rest in. Captured once, before anything moves -- unless
    # the caller supplies one, which is the only way a rest state survives across two calls.
    if rest_curvature is not None:
        lap_rest = np.array(rest_curvature, dtype=float)
        if lap_rest.shape != pts.shape:
            raise ValueError("rest_curvature is %s but this fabric is %s"
                             % (lap_rest.shape, pts.shape))
    elif setup.rest_is_relaxed_shape:
        lap_rest = _laplacian(pts)
    else:
        lap_rest = np.zeros_like(pts)
    lap_rest_initial = lap_rest.copy()

    ell = float(np.median(rest_m))
    bend_coeff = setup.bending_rigidity_N_m2 / max(ell ** 3, 1e-30)
    # Step size scaled so the largest force moves a vertex a small fraction of a segment.
    # Affects convergence rate only: the equilibrium is where the forces balance.
    ref = max(bend_coeff * ell, float(np.abs(grav_force).max()), 1e-30)
    step = 0.05 * ell / ref

    # Kaldor's two plasticity radii, once, in this solver's rest-state units.
    r_rel = angular_radius_to_lap(setup.p_plastic_rad, ell)
    r_abs = angular_radius_to_lap(setup.p_max_plastic_rad, ell)

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
        lap = _laplacian(pts)
        force += bend_coeff * (lap - lap_rest)

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
        report.final_step_mm = worst
        budget -= worst

        # The plastic step is taken HERE, after the iteration has been accepted, and against
        # the accepted curvature. Migrating earlier would let a reverted iteration -- one
        # whose move was too large for its measured clearance and was thrown away -- leave a
        # permanent mark on the rest state, so the fabric would remember a configuration it
        # was never allowed to occupy.
        if setup.plastic_rest_migration:
            lap_rest = _migrate_rest(lap_rest, _laplacian(pts), r_rel, r_abs)

        report.iterations = it + 1
        if worst < 1e-5:
            report.converged = True
            break

    if setup.plastic_rest_migration:
        moved = np.linalg.norm(lap_rest - lap_rest_initial, axis=1)
        # Reported as an angle by the same DERIVED mapping, inverted. It is the angular
        # equivalent of a distance moved in the rest-state space, not a turning angle of any
        # single element, and is labelled that way rather than dressed up as one.
        def _as_angle(v):
            return float(2.0 * np.arcsin(np.clip(v / (2.0 * ell), 0.0, 1.0)))
        report.rest_migration_max_rad = _as_angle(float(moved.max()))
        report.rest_migration_mean_rad = _as_angle(float(moved.mean()))

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


def relief_profile(flat: topo.Fabric, draped: topo.Fabric,
                   down=(0.0, 0.0, -1.0)) -> dict:
    """How much of the fabric's relief is whole-row bowing, and how much is anything else.

    The standing symptom against the realism floor is that the fabric reads as a CORRUGATED
    RELIEF -- each row bowing gently as a rigid unit, so the surface is essentially a function
    of position along the cantilever and barely varies across a row. That is a measurable
    statement rather than an impression, and it needs to be measured or a change that claims
    to address it cannot be checked.

    Displacement along `down` is taken at each stitch's centre and decomposed into the part a
    per-row mean explains and the part left over. `within_row_fraction` is the residual's
    share of the total variance: a moulded panel whose rows are rigid bars scores near zero,
    and cloth whose stitches move against their neighbours does not. It is a NECESSARY
    condition, not a sufficient one -- a high score says the rows are not rigid, not that the
    fabric looks like crochet.
    """
    d = np.asarray(down, dtype=float)
    d = d / np.linalg.norm(d)
    a = {(o.row, o.position): o.points.mean(axis=0)
         for o in flat.ops if o.kind == "hdc"}
    b = {(o.row, o.position): o.points.mean(axis=0)
         for o in draped.ops if o.kind == "hdc"}
    keys = sorted(set(a) & set(b))
    if len(keys) < 4:
        return {"stitches": len(keys), "within_row_fraction": 0.0,
                "within_row_rms_mm": 0.0, "total_rms_mm": 0.0, "rows": 0}
    z = np.array([float((b[k] - a[k]) @ d) for k in keys])
    rows = np.array([k[0] for k in keys])
    resid = np.empty_like(z)
    for r in sorted(set(rows.tolist())):
        m = rows == r
        resid[m] = z[m] - z[m].mean()
    total = float(np.var(z))
    within = float(np.mean(resid ** 2))
    return {"stitches": len(keys), "rows": len(set(rows.tolist())),
            "total_rms_mm": float(np.sqrt(np.mean((z - z.mean()) ** 2))),
            "within_row_rms_mm": float(np.sqrt(within)),
            "within_row_fraction": within / total if total > 0 else 0.0}


def cantilever_test(fab: topo.Fabric, setup: DrapeSetup, material=None,
                    overhang_fractions=(0.3, 0.4, 0.5, 0.6, 0.7)) -> dict:
    """ASTM D1388 in simulation: advance the fabric over an edge until the tip falls 41.5deg.

    A standard measurement rather than a judgement. The bending length is half the overhang
    at which the tip reaches that angle, and flexural rigidity is G = W * c^3. Comparing the
    result against the analytic (B / W g)^(1/3) checks the solver against beam theory.

    TWO THINGS THIS INSTRUMENT CANNOT DO, BOTH MEASURED RATHER THAN SUSPECTED. Written here
    because every bending length quoted from this solver comes through this function.

    1. `overhang_mm` is NOMINAL: `ptp(y) * frac`, the length the clamp fraction asks for. The
       clamp is a threshold on y and the fabric has a handful of discrete rows, so the length
       actually left free is quantised to row boundaries and can differ from the nominal by up
       to 8 per cent on a five-row swatch, non-monotonically -- fractions 0.4 and 0.5 free the
       same two rows. Since the tip angle is arctan(drop / overhang), a denominator that is
       wrong by 8 per cent in an unpredictable direction puts a wiggle into the angle that has
       nothing to do with the fabric. `free_extent_mm` and `angle_on_measured_overhang_deg`
       are therefore reported ALONGSIDE the nominal pair rather than replacing it, so no
       existing figure silently changes and the two can be compared.
    2. The solve underneath is not converged at any iteration count used so far, and the
       report's `converged` flag now says so per step. At a fixed iteration count the tip drop
       is dominated by near-uniform descent, which does not depend on the overhang at all --
       so the drop comes out roughly CONSTANT across overhangs and the angle falls as
       1/overhang, which is arithmetic rather than stiffness. See research/VISUAL_WAVE2.md for
       the sweep. Read `converged` before believing any bending length taken from here.
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
        # The overhang the boundary condition actually produced, as opposed to the one asked
        # for: the free region of the ORIGINAL fabric, measured the same way the clamp cuts.
        y0 = fab.points[:, 1]
        cut = y0.min() + (y0.max() - y0.min()) * frac
        free = y0 < cut
        extent = float(np.ptp(y0[free])) if free.any() else 0.0
        results.append({"overhang_fraction": frac, "overhang_mm": reach,
                        "tip_drop_mm": drop, "tip_angle_deg": angle,
                        "free_extent_mm": extent, "free_vertices": int(free.sum()),
                        "angle_on_measured_overhang_deg":
                            float(np.degrees(np.arctan2(max(drop, 0.0), max(extent, 1e-9)))),
                        "converged": bool(rep.converged),
                        "final_step_mm": rep.final_step_mm,
                        "iterations": rep.iterations})
    return {"steps": results}
