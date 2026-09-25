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

The solver's own effective bending length was then MEASURED -- deflect a cantilever, invert
delta = l^4 / 8c^3 -- and B set so that measurement landed on the midpoint. The target is a
published fabric property and the free parameter is the one genuinely unknown to six orders
of magnitude, which is what made it calibration rather than taste.

WHAT HAS SINCE BEEN MEASURED ABOUT THAT PROCEDURE, and it is worse than "uncertain".

  a. The cantilever solve was never converged. `cantilever_equilibrium_bound` computes the
     reason without running it: the implemented bending force is bend_coeff*(lap - lap_rest),
     a LAPLACIAN, which is a string under an effective tension B/l^2 -- not the gradient of
     the bending energy written above, which is bend_coeff * D^T (lap - lap_rest) and is a
     beam. On the certified 5x5 swatch that tension is 1.80e-3 N while the free region of the
     standard cantilever weighs 5.43e-3 N, three times more, so the specimen cannot hold
     itself up in a shallow configuration at all and the descent is still falling at every
     iteration count reached. Every bending length ever quoted from it is a transient.
  b. The energy is not invariant under a rigid rotation of the cloth. Rotating the whole
     certified swatch 5 degrees, deforming nothing, costs the equivalent of lifting every
     stitch 1.17mm. So the bending length read off it grows with the SIZE of the swatch --
     57.6mm at 5x5, 98.5mm at 12x10, same yarn, same B.
  c. The cross-check once recorded here (B landing at 1.45x the free-fibre floor) was
     WITHDRAWN as materially weaker than claimed, and is not restored.

So the honest status of B is BOUNDED and CONDITIONED, not calibrated: the procedure that set
it cannot be re-run to the same answer. `flexural_rigidity` and `derive_bending_rigidity`
below are the replacement -- closed form, nothing to converge, and they state every condition
they hold under. They are NOT wired into the default; changing B moves every committed
Visual result and that is an owner-visible decision, not a side effect of measuring better.

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
           "PROVENANCE", "rest_curvature_of", "angular_radius_to_lap", "relief_profile",
           "genuine_yarn_vertices", "corotational_rotations", "bending_energy_J",
           "rigid_motion_response", "cylindrical_bend", "flexural_rigidity",
           "derive_bending_rigidity", "cantilever_equilibrium_bound",
           "TARGET_BENDING_LENGTH_MM"]

STANDARD_GRAVITY = 9.80665            # m/s^2, sourced
ACRYLIC_DENSITY = 1180.0              # kg/m^3, already used to derive fibre radius
ACRYLIC_MODULUS = 2.5e9               # Pa, bounded: acrylic bulk modulus is quoted 2.2-3.2

# The calibrated yarn bending rigidity, set by the procedure documented above: the solver's
# own effective bending length was measured from a cantilever deflection and this is the
# value that put it on the geometric midpoint of the 15-80mm band that published jersey
# stiffness and observed crochet behaviour bracket.
#
# IT LIVES HERE AND NOWHERE ELSE. It was briefly a literal in the test suite as well, chosen
# before the calibration existed and left twenty times too stiff afterwards, which showed up
# as a test asserting gravity had moved the fabric while the fabric moved 0.03mm.
#
# WHAT IS NOW KNOWN ABOUT THE PROCEDURE THAT SET IT, and it is not good. Three findings, all
# measured, all in research/VISUAL_WAVE2.md and research/VISUAL_WAVE3.md:
#
#   1. The cantilever solve it was read off was NEVER converged, at any iteration count
#      tried, and the inverted bending length moves 2.09x across the iteration range for one
#      unchanged fabric. `cantilever_equilibrium_bound` now computes why in closed form.
#   2. The energy this module documents is NOT invariant under a rigid rotation of the
#      fabric, so a bending length read from it grows with the SIZE OF THE SWATCH: 57.6mm on
#      a 5x5, 98.5mm on a 12x10, same yarn and same B. A quantity that depends on how much
#      cloth you measured is not a material property. `rigid_motion_response` measures the
#      defect and `flexural_rigidity(frame_invariant=True)` removes it.
#   3. The cross-check once recorded here -- "1.45x the free-fibre hard lower bound, a
#      cross-check it was not fitted to" -- WAS WITHDRAWN on 2026-09-25 as materially weaker
#      than it sounded, and is deliberately not restated. It is not restored anywhere.
#
# The constant is therefore left exactly where it was, and everything derived from it is
# conditioned on that history rather than on a converged measurement. `derive_bending_rigidity`
# re-derives a value from scratch, states its conditions, and is NOT wired into the default.
CALIBRATED_BENDING_N_M2 = 3.0e-8

# The calibration target: the geometric midpoint of the 15-80mm bending-length band that
# published jersey stiffness (0.5-1.4cm) floors and observed chunky-crochet behaviour caps.
# BOUNDED, argued rather than measured; it is the target, not a result.
TARGET_BENDING_LENGTH_MM = 34.6

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
    "bending_calibration": "CONDITIONED, not converged. B was set against a published "
                           "fabric property -- the geometric midpoint of the 15-80mm "
                           "bending-length band -- but the cantilever solve it was read "
                           "off never converged at any iteration count tried, and the "
                           "inverted bending length moves 2.09x across that range for one "
                           "unchanged fabric. The cross-check once claimed here (1.45x the "
                           "free-fibre floor) was WITHDRAWN and is not restored. The "
                           "documented bending energy is also not rigid-rotation "
                           "invariant, so a bending length read from it grows with swatch "
                           "size: 57.6mm on a 5x5 and 98.5mm on a 12x10 at the same B. See "
                           "rigid_motion_response, flexural_rigidity and "
                           "derive_bending_rigidity, and research/VISUAL_WAVE3.md",
    "frame_invariant_rest": "DERIVED, standard co-rotational construction, OFF BY DEFAULT. "
                            "The rest curvature is stored as a world-space second "
                            "difference, so rotating the cloth without deforming it costs "
                            "energy -- measured at the equivalent of lifting every stitch "
                            "1.17mm for a 5 degree turn and 308mm for a right angle. "
                            "Kaldor et al. 2010 avoid this by holding the rest state as a "
                            "2D point in the segment pair's OWN frame; the same thing here "
                            "is a per-vertex rotation carrying the rest edge pair onto the "
                            "current one (Kabsch, exact and equivariant). What is DERIVED "
                            "is the construction; what is UNKNOWN is whether removing this "
                            "spurious stiffness is sufficient for conformability, which is "
                            "measured rather than claimed",
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
    # FRAME-INVARIANT REST STATE. OFF BY DEFAULT, for the same reason as the line above: it
    # changes the fabric's shape and every committed Visual result was produced without it.
    #
    # The rest curvature is stored as a second difference in WORLD coordinates, so turning a
    # piece of cloth round -- deforming nothing -- changes every residual and costs energy.
    # Measured on the certified 5x5 swatch by `rigid_motion_response`: a 5 degree rotation
    # of the whole fabric costs the equivalent of lifting every stitch 1.17mm, and a right
    # angle costs 308mm. The entire gravitational drive on the standard cantilever is worth
    # about 1.4mm of droop at 800 iterations, so the spurious rotational stiffness is not a
    # correction to the mechanics; at stitch scale it dominates them.
    #
    # THAT IS A CANDIDATE MECHANISM FOR THE STANDING CONFORMABILITY SYMPTOM, and it is
    # exactly the right shape for it. A fabric conforms by letting each stitch turn
    # relative to its neighbours. An energy that charges for turning, per stitch, in
    # proportion to how curved the stitch already is -- and a crochet loop is nothing but
    # curvature -- is an energy that holds rows rigid. Whether removing it is SUFFICIENT is
    # measured in research/VISUAL_WAVE3.md, not claimed here.
    #
    # With this on, the rest curvature is carried into each vertex's current frame before
    # the residual is taken, by the co-rotational rotation in `corotational_rotations`.
    # Kaldor et al. 2010 hold the rest state in the segment pair's own frame for the same
    # reason. DERIVED construction, standard; the rate and sufficiency are UNKNOWN.
    frame_invariant_rest: bool = False
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


# --------------------------------------------------------------------------------------
# Frame invariance, and the instruments that depend on it.
#
# Everything below is measurement, not appearance. None of it is wired into the default
# solve; `frame_invariant_rest` is an option that defaults to off, exactly like the Kaldor
# plasticity, because every committed Visual result was produced without it.
# --------------------------------------------------------------------------------------

JUMP_SEGMENT_MM = 5.0        # the artificial hops between ops; `areal_mass` uses the same
DEGENERATE_SEGMENT_MM = 0.01  # the sub-micron joins; the strain statistic uses the same


def genuine_yarn_vertices(pts: np.ndarray) -> np.ndarray:
    """Vertices whose BOTH adjacent segments are real yarn, so a curvature there is real.

    The yarn path as stored is not all yarn. It contains artificial hops between ops -- 87
    of 473 segments on the certified 5x5 swatch, up to 6.73mm -- and sub-micron joins where
    one stitch's path meets the next, 20 of them. A second difference taken across either is
    not a bend in any yarn; it is an artefact of how the path was concatenated. The solver's
    bending term does not currently exclude them, which is recorded rather than silently
    changed, and every instrument here reports the answer both ways so the contribution can
    be seen instead of argued about.
    """
    pts = np.asarray(pts, dtype=float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    bad = (seg >= JUMP_SEGMENT_MM) | (seg <= DEGENERATE_SEGMENT_MM)
    good = np.zeros(len(pts), bool)
    if len(pts) > 2:
        good[1:-1] = ~(bad[:-1] | bad[1:])
    return good


def corotational_rotations(pts: np.ndarray, rest_pts: np.ndarray) -> np.ndarray:
    """Per-vertex rotation carrying the REST edge pair onto the CURRENT one. DERIVED.

    This is what makes a rest curvature a property of the CLOTH rather than of the cloth's
    orientation in the room. The rest state as stored is a second difference in world
    coordinates, so turning a finished fabric round -- deforming nothing -- changes every
    rest residual and costs energy. `rigid_motion_response` measures how much.

    Kaldor et al. 2010 do not have this problem because their rest state is a 2D point in
    the segment pair's own frame (which is also why their plasticity radii are 2D and ours,
    mapped in `angular_radius_to_lap`, are not). The equivalent here is the standard
    co-rotational construction: the least-squares rotation R_i taking the rest vertex's two
    unit edge vectors onto the current vertex's two, by Kabsch. Comparing `lap` against
    `R_i @ lap_rest` is then exactly invariant under any rigid motion of the fabric, which
    is asserted to machine precision in the suite rather than argued here.

    Endpoints have no edge pair and get the identity; a vertex whose rest edges are
    collinear has a rotation about that axis that no data determines, and Kabsch returns the
    minimal one, which is the right default because the rest curvature it acts on lies along
    that same axis and is therefore unmoved by it.
    """
    pts = np.asarray(pts, dtype=float)
    rest_pts = np.asarray(rest_pts, dtype=float)
    n = len(pts)
    out = np.tile(np.eye(3), (n, 1, 1))
    if n < 3:
        return out

    def unit(v):
        m = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.maximum(m, 1e-12)

    a = unit(pts[1:-1] - pts[:-2])
    b = unit(pts[2:] - pts[1:-1])
    ra = unit(rest_pts[1:-1] - rest_pts[:-2])
    rb = unit(rest_pts[2:] - rest_pts[1:-1])
    # H = sum over the pair of (rest outer current); argmax_R tr(R H) is Kabsch.
    h = ra[:, :, None] * a[:, None, :] + rb[:, :, None] * b[:, None, :]
    u, _s, vt = np.linalg.svd(h)
    v = np.transpose(vt, (0, 2, 1))
    ut = np.transpose(u, (0, 2, 1))
    d = np.ones((len(h), 3))
    # np.sign would return 0 on an exactly singular pair and hand back a non-rotation.
    d[:, 2] = np.where(np.linalg.det(v @ ut) < 0.0, -1.0, 1.0)
    out[1:-1] = (v * d[:, None, :]) @ ut
    return out


def bending_energy_J(pts: np.ndarray, lap_rest: np.ndarray, bending_rigidity_N_m2: float,
                     ell_m: float, *, rest_pts: np.ndarray | None = None,
                     frame_invariant: bool = False,
                     mask: np.ndarray | None = None) -> float:
    """The bending energy this module documents, evaluated exactly on a configuration.

    E = (B / 2 l^3) * sum |lap - lap_rest|^2, which is the energy in the module docstring.
    With `frame_invariant`, the rest curvature is carried into each vertex's current frame
    first, which is the only version of this that is a material energy.
    """
    pts = np.asarray(pts, dtype=float)
    if frame_invariant and rest_pts is None:
        # Silently falling back to the world-space residual here would make every
        # frame-invariance result in this module a measurement of the defect it claims to
        # have removed, and it would read as a pass.
        raise ValueError("frame_invariant needs rest_pts: a rest curvature without the "
                         "configuration it belongs to cannot be carried into another frame")
    k = bending_rigidity_N_m2 / max(ell_m ** 3, 1e-30)
    resid = _laplacian(pts) - (
        np.einsum("nij,nj->ni", corotational_rotations(pts, rest_pts), lap_rest)
        if frame_invariant else lap_rest)
    sq = np.einsum("ni,ni->n", resid, resid)
    if mask is not None:
        sq = sq[mask]
    return 0.5 * k * float(sq.sum())


def _median_segment_m(pts: np.ndarray) -> float:
    seg = _segment_lengths(np.asarray(pts, dtype=float))
    seg = seg.copy()
    seg[seg < 1e-9] = 1e-9
    return float(np.median(seg)) * 1e-3


def rigid_motion_response(fab: topo.Fabric, *,
                          bending_rigidity_N_m2: float = CALIBRATED_BENDING_N_M2,
                          tex: float = 444.0,
                          angles_deg=(0.5, 1.0, 5.0, 15.0, 45.0, 90.0),
                          axis=(0.3, 0.5, 0.81)) -> dict:
    """What the bending energy reads when the fabric is MOVED without being deformed.

    A material energy reads zero for every rigid motion. This one reads zero for translation
    and does not for rotation, and the size of that number is the size of a stiffness the
    fabric has against turning that no yarn possesses. Reported in joules and, because
    joules are hard to weigh, as the height every stitch would have to be lifted against
    gravity to cost the same -- which is the comparison that decides whether the defect can
    compete with the force that drives drape.
    """
    pts = fab.points.astype(float)
    ell = _median_segment_m(pts)
    lap_rest = _laplacian(pts)
    lam = linear_density_kg_per_m(tex)
    per_vertex_weight = lam * ell * STANDARD_GRAVITY
    centre = pts.mean(axis=0)
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    kx = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])

    rows = []
    for deg in angles_deg:
        th = np.radians(deg)
        rot = np.eye(3) + np.sin(th) * kx + (1.0 - np.cos(th)) * (kx @ kx)
        moved = (pts - centre) @ rot.T + centre
        e_world = bending_energy_J(moved, lap_rest, bending_rigidity_N_m2, ell)
        e_frame = bending_energy_J(moved, lap_rest, bending_rigidity_N_m2, ell,
                                   rest_pts=pts, frame_invariant=True)
        rows.append({
            "angle_deg": float(deg),
            "world_rest_energy_J": e_world,
            "frame_invariant_energy_J": e_frame,
            "equivalent_lift_per_vertex_mm":
                1e3 * (e_world / len(pts)) / max(per_vertex_weight, 1e-30),
        })
    shifted = pts + np.array([13.0, -7.0, 4.0])
    return {
        "rotations": rows,
        "translation_energy_J": bending_energy_J(shifted, lap_rest,
                                                 bending_rigidity_N_m2, ell),
        "vertices": int(len(pts)),
        "per_vertex_weight_N": float(per_vertex_weight),
        "median_segment_mm": ell * 1e3,
    }


def cylindrical_bend(pts: np.ndarray, curvature_per_m: float, along: str = "wale") -> np.ndarray:
    """Wrap a flat fabric onto a cylinder of the given curvature. Midsurface-isometric.

    `along` names the direction the curvature runs in: "wale" is +y, the direction rows
    advance and the direction the cantilever droops, and "course" is +x, along a row. Both
    are reported because a crochet fabric is not isotropic and ASTM D1388 is run on strips
    cut both ways.

    The map is an exact isometry of the z = 0 midsurface and is NOT an isometry of the yarn,
    which has thickness: a strand sitting z above the midsurface is stretched by z * kappa.
    Every caller measures that residual and reports it rather than assuming it away -- at
    kappa = 0.5 /m it is 0.29 per cent on the certified swatch.
    """
    pts = np.asarray(pts, dtype=float)
    if curvature_per_m <= 0:
        raise ValueError("curvature must be positive")
    idx = {"wale": 1, "course": 0}.get(along)
    if idx is None:
        raise ValueError("along must be 'wale' or 'course'")
    radius_mm = 1000.0 / curvature_per_m
    out = pts.copy()
    s = pts[:, idx] - 0.5 * (pts[:, idx].min() + pts[:, idx].max())
    theta = s / radius_mm
    r = radius_mm - pts[:, 2]
    out[:, idx] = r * np.sin(theta)
    out[:, 2] = radius_mm - r * np.cos(theta)
    return out


def flexural_rigidity(fab: topo.Fabric, tex: float = 444.0, *,
                      bending_rigidity_N_m2: float = CALIBRATED_BENDING_N_M2,
                      along: str = "wale",
                      curvature_per_m: float = 0.25,
                      frame_invariant: bool = True,
                      yarn_only: bool = True) -> dict:
    """The fabric's areal flexural rigidity G, by imposed curvature. NOTHING TO CONVERGE.

    This replaces the cantilever as the route to a bending length, and the reason is not
    convenience. ASTM D1388's cantilever is an equilibrium measurement, and this solver's
    cantilever has no shallow equilibrium to find -- see `cantilever_equilibrium_bound` --
    so every bending length taken from it is a transient of the iteration count. Imposing
    the curvature instead of waiting for it removes the solve entirely: bend the certified
    geometry onto a cylinder, evaluate the model's own bending energy in closed form, and
    read G off the definition of bending energy per unit area, (1/2) G kappa^2.

    The bending length follows ASTM's own relation, G = W g c^3, with W measured off this
    fabric's own yarn length and extent rather than looked up.

    CONDITIONS, all reported in the result so a number from here cannot travel without them:

      * `curvature_independent_to` -- G must not depend on kappa or the model is not linearly
        elastic and a single rigidity does not describe it. Measured over a 4x sweep. The
        residual is the yarn's own thickness, and it is proportional to kappa: 1.003 at
        kappa = 0.25/m, 1.010 at 1.0, 1.037 at 4.0. That is why the default curvature is
        gentle rather than convenient -- a 4 metre radius on a 58mm swatch.
      * `max_segment_strain` -- the wrap is isometric on the midsurface only, so the yarn's
        own thickness is strained. Bend gently enough that this stays small, and read it.
      * `frame_invariant` -- with the world-space rest state, G is NOT a material property:
        it grows with the size of the swatch, because rotating cloth costs energy. Default
        True here on purpose; False reproduces what the committed solver's energy says.
      * `yarn_only` -- whether the artificial hops between ops contribute. They are 60 per
        cent of the world-space energy and are not yarn.
    """
    pts = fab.points.astype(float)
    ell = _median_segment_m(pts)
    lap_rest = _laplacian(pts)
    mask = genuine_yarn_vertices(pts) if yarn_only else None
    am = areal_mass(fab, tex)
    w_g = am["areal_mass_kg_m2"] * STANDARD_GRAVITY
    idx = {"wale": 1, "course": 0}[along]
    span_bend = float(np.ptp(pts[:, idx])) * 1e-3
    span_wide = float(np.ptp(pts[:, 1 - idx])) * 1e-3
    area = span_bend * span_wide

    def one(kappa):
        bent = cylindrical_bend(pts, kappa, along)
        e = bending_energy_J(bent, lap_rest, bending_rigidity_N_m2, ell,
                             rest_pts=pts, frame_invariant=frame_invariant, mask=mask)
        e0 = bending_energy_J(pts, lap_rest, bending_rigidity_N_m2, ell,
                              rest_pts=pts, frame_invariant=frame_invariant, mask=mask)
        seg0 = _segment_lengths(pts)
        seg1 = _segment_lengths(bent)
        live = seg0 > DEGENERATE_SEGMENT_MM
        strain = float(np.abs(seg1[live] / seg0[live] - 1.0).max())
        return 2.0 * (e - e0) / (kappa ** 2 * max(area, 1e-30)), e - e0, strain

    g, energy, strain = one(curvature_per_m)
    g_lo, _, _ = one(0.5 * curvature_per_m)
    g_hi, _, _ = one(2.0 * curvature_per_m)
    spread = max(g, g_lo, g_hi) / max(min(g, g_lo, g_hi), 1e-30)
    return {
        "along": along,
        "curvature_per_m": float(curvature_per_m),
        "flexural_rigidity_N_m": float(g),
        "bending_length_mm": float((max(g, 0.0) / max(w_g, 1e-30)) ** (1.0 / 3.0) * 1e3),
        "bend_energy_J": float(energy),
        "areal_mass_kg_m2": am["areal_mass_kg_m2"],
        "area_m2": float(area),
        "span_bend_mm": span_bend * 1e3,
        "span_wide_mm": span_wide * 1e3,
        "max_segment_strain": strain,
        "curvature_independent_to": float(spread),
        "frame_invariant": bool(frame_invariant),
        "yarn_only": bool(yarn_only),
        "vertices_used": int(mask.sum()) if mask is not None else int(len(pts)),
        "vertices": int(len(pts)),
        "bending_rigidity_N_m2": float(bending_rigidity_N_m2),
    }


def derive_bending_rigidity(fab: topo.Fabric, tex: float = 444.0, *,
                            target_bending_length_mm: float = TARGET_BENDING_LENGTH_MM,
                            along: str = "wale",
                            curvature_per_m: float = 0.25,
                            frame_invariant: bool = True,
                            yarn_only: bool = True) -> dict:
    """Re-derive B from the calibration target, in code, in closed form.

    The bending energy is linear in B, so G is linear in B and the bending length goes as
    B^(1/3). One evaluation at a reference B therefore inverts exactly:

        B_target = B_ref * (c_target / c_ref)^3

    No sweep, no fitting, no solver, no iteration count, and nothing that can be stopped
    early. The whole of the result is the conditions: the same ones `flexural_rigidity`
    reports, plus the target and the fabric it was derived on. `derivable` is False -- and
    the derived value must not be used -- unless the rigidity it inverts is actually a
    material property, which means frame invariance is on and the curvature sweep agrees
    with itself.

    This does NOT set `CALIBRATED_BENDING_N_M2`. Moving that constant moves every committed
    Visual result, and doing it as a side effect of a better measurement is exactly the move
    this module keeps catching.
    """
    ref = flexural_rigidity(fab, tex, bending_rigidity_N_m2=CALIBRATED_BENDING_N_M2,
                            along=along, curvature_per_m=curvature_per_m,
                            frame_invariant=frame_invariant, yarn_only=yarn_only)
    c_ref = ref["bending_length_mm"]
    ratio = (target_bending_length_mm / max(c_ref, 1e-30)) ** 3
    out = dict(ref)
    out.update({
        "target_bending_length_mm": float(target_bending_length_mm),
        "reference_bending_rigidity_N_m2": CALIBRATED_BENDING_N_M2,
        "reference_bending_length_mm": c_ref,
        "derived_bending_rigidity_N_m2": float(CALIBRATED_BENDING_N_M2 * ratio),
        "factor_on_committed_value": float(ratio),
        "derivable": bool(frame_invariant and ref["curvature_independent_to"] < 1.01),
    })
    return out


def cantilever_equilibrium_bound(fab: topo.Fabric, setup: DrapeSetup,
                                 overhang_fraction: float = 0.7) -> dict:
    """Whether the cantilever the solver runs HAS a shallow equilibrium, in closed form.

    This is the closed-form answer to a question the sweep in research/VISUAL_WAVE2.md could
    only answer by running out of iterations. The implemented bending force is
    bend_coeff * (lap - lap_rest): a second difference, not the second difference applied
    twice, so it is not the gradient of the energy the module documents. For a chain of
    segment length l carrying a transverse field u, bend_coeff * lap is (B/l) u'' per vertex
    and so (B/l^2) u'' per unit length -- a STRING under tension B/l^2, not a beam.

    A string clamped at one end with a free end cannot support a transverse load at all: the
    natural boundary condition at the free end is u' = 0, which is incompatible with
    u'' = w/T anywhere along it. Discretely, the free end of the yarn path is the one vertex
    with no bending equation. So the specimen falls until the geometry itself turns over,
    and the descent has no shallow state to converge to. `effective_tension_N` against
    `free_region_weight_N` says how far from supporting itself it is, and
    `equilibrium_second_difference_mm` is the value the solver's own force law is heading
    for -- which a run can be checked against to see how far through its descent it is.
    """
    pts = fab.points.astype(float)
    ell = _median_segment_m(pts)
    bend_coeff = setup.bending_rigidity_N_m2 / max(ell ** 3, 1e-30)
    seg = _segment_lengths(pts)
    seg[seg < 1e-9] = 1e-9
    lumped = np.zeros(len(pts))
    lumped[:-1] += seg * 1e-3 / 2.0
    lumped[1:] += seg * 1e-3 / 2.0
    weight = lumped * setup.linear_density_kg_m * setup.gravity
    y = pts[:, 1]
    free = y < (y.min() + (y.max() - y.min()) * overhang_fraction)
    tension = setup.bending_rigidity_N_m2 / max(ell ** 2, 1e-30)
    free_weight = float(weight[free].sum())
    typical = setup.linear_density_kg_m * ell * setup.gravity
    return {
        "overhang_fraction": float(overhang_fraction),
        "free_vertices": int(free.sum()),
        "vertices": int(len(pts)),
        "effective_tension_N": float(tension),
        "free_region_weight_N": free_weight,
        "weight_over_tension": free_weight / max(tension, 1e-30),
        "supports_its_own_weight": bool(free_weight < tension),
        "equilibrium_second_difference_mm": float(1e3 * typical / max(bend_coeff, 1e-30)),
        "bend_coeff_N_per_m": float(bend_coeff),
        "median_segment_mm": ell * 1e3,
        "force_law": "laplacian (string, tension B/l^2) -- NOT the gradient of the "
                     "documented bending energy, which is the second difference applied "
                     "twice (a beam)",
    }


def drape(fab: topo.Fabric, setup: DrapeSetup,
          material: rx.Material | None = None,
          rest_curvature: np.ndarray | None = None,
          rest_points: np.ndarray | None = None) -> tuple[topo.Fabric, DrapeReport]:
    """Find the fabric's equilibrium under gravity, contact and its boundary conditions.

    `rest_curvature`, when given, is the rest state to bend against, as produced by
    `rest_curvature_of`. It overrides `setup.rest_is_relaxed_shape`, and it is the only way to
    carry ONE rest state across two calls -- which any recovery or load-cycle experiment
    requires and which the capture-at-call-start default cannot express.

    `rest_points` is the configuration that rest curvature belongs to, and is needed only by
    `setup.frame_invariant_rest`, which has to know which way the rest state was FACING in
    order to carry it into the current frame. It defaults to the fabric as passed in, which
    is what `rest_is_relaxed_shape` means; a load-cycle experiment must pass the same pair to
    both calls or the two options disagree about what the rest state is.
    """
    if setup.frame_invariant_rest and setup.plastic_rest_migration:
        # Kaldor's projections are defined on a rest state in the element's own frame, and
        # ours is in world space; running both at once would migrate a world-space rest
        # state against a frame-carried residual, and what that composition means is
        # UNKNOWN. Refused rather than run, because a silently meaningless combination is
        # how a measurement becomes a number nobody can account for.
        raise ValueError("frame_invariant_rest and plastic_rest_migration are not defined "
                         "together: the plasticity projects a world-space rest state and "
                         "the frame-invariant residual is taken in the vertex frame")
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
    # The configuration the rest curvature belongs to. Only the frame-invariant option needs
    # it, and it needs it because a rest curvature without an orientation cannot be carried
    # into any other frame.
    rest_frame_pts = (np.array(rest_points, dtype=float)
                      if rest_points is not None else start.copy())
    if setup.frame_invariant_rest and rest_frame_pts.shape != pts.shape:
        raise ValueError("rest_points is %s but this fabric is %s"
                         % (rest_frame_pts.shape, pts.shape))

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
        if setup.frame_invariant_rest:
            # Carry the rest curvature into each vertex's CURRENT frame before taking the
            # residual, so turning the cloth costs nothing and only deforming it does.
            oriented = np.einsum("nij,nj->ni",
                                 corotational_rotations(pts, rest_frame_pts), lap_rest)
        else:
            oriented = lap_rest
        force += bend_coeff * (lap - oriented)

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
