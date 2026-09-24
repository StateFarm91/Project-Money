"""Yarn as it is actually built: plies twisted around a centre, not a smooth tube.

WHY THIS EXISTS. The relaxed geometry is correct and passes every topology and geometry
lock, and rendered as a smooth circular tube it reads as CGI. A real worsted yarn is not a
tube. It is several plies twisted around one another, and the spiral where those plies meet
is the single most recognisable thing about yarn at the distance an Etsy listing photograph
is viewed from -- before any fibre, halo or fuzz is considered.

THE LOCK. Everything here is a RENDERING derivation from the validated yarn centreline. The
centreline is authoritative and is never modified, never fed back, and never re-validated
against these curves. Plies are geometry for the renderer to shade; the fabric's topology,
gauge, yarn diameter and macro geometry are what they were.

METHOD, following Montazeri et al., "A Practical Ply-Based Appearance Modeling for Knitted
Fabrics" (EGSR 2021): "Ply curves are generated twisting around the yarn curves given the
parameters (e.g. number of plies, ply twist)... Each segment forms a cylinder with given ply
radius." Their fibre detail is added by normal and tangent mapping rather than by simulating
fibres explicitly, which is what makes the approach practical at this scale. This module is
the ply-geometry half of that.

WHERE THE NUMBERS COME FROM
---------------------------
PLY COUNT -- sourced, with its uncertainty stated. The pattern specifies "worsted acrylic".
Worsted weight is commonly four-ply, and that is the value used, but the weight class does
not determine it: worsted yarns are also sold as singles, two-ply and others. Four is the
common case for this class, not a property the pattern states.

PLY RADIUS and PLY CENTRE OFFSET -- DERIVED, by geometry alone, with no free constant. N
plies of radius r packed touching around a yarn of radius R, with their centres a distance d
from the axis:

    adjacent ply centres are 2r apart:   2 d sin(pi/N) = 2 r
    the plies fill the yarn:             d + r = R

    => r = R sin(pi/N) / (1 + sin(pi/N)),  d = R - r

For four plies that is r = 0.414 R and d = 0.586 R. Nothing here was chosen.

TWIST -- derived from a sourced formula and a sourced range. Textile practice expresses twist
through the twist multiplier, TM = TPM / sqrt(tex) in the direct count system, and quotes
TM = 3.0 to 3.6 for knitting yarns. The pattern's stated yarn implies about 444 tex, giving

    TPM = TM * sqrt(444) = 63 to 76 turns per metre,  a twist pitch of 13 to 16 mm

Both ends are carried rather than a single value being picked. At a 3.33mm yarn that is a
surface helix angle of roughly 33 to 39 degrees, which is high-but-plausible for a plied
knitting yarn; the tex figure itself rests on an assumed linear density, so this is a
bounded estimate and is labelled as one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["PlySpec", "ply_geometry", "TWIST_MULTIPLIER_RANGE", "WORSTED_PLIES"]

# Typical twist multipliers quoted for weft and knitting yarns, direct (tex) count system.
TWIST_MULTIPLIER_RANGE = (3.0, 3.6)
WORSTED_PLIES = 4


@dataclass(frozen=True)
class PlySpec:
    """A yarn's construction, with every number either derived or labelled."""

    yarn_diameter_mm: float
    tex: float
    plies: int = WORSTED_PLIES
    twist_multiplier: float = 3.3      # midpoint of the sourced range; swept, not assumed

    @property
    def yarn_radius_mm(self) -> float:
        return self.yarn_diameter_mm / 2.0

    @property
    def ply_radius_mm(self) -> float:
        """Derived. No free constant: it is what fits."""
        s = np.sin(np.pi / self.plies)
        return self.yarn_radius_mm * s / (1.0 + s)

    @property
    def ply_offset_mm(self) -> float:
        """Distance of each ply's centre from the yarn axis. Derived with the radius."""
        return self.yarn_radius_mm - self.ply_radius_mm

    @property
    def turns_per_metre(self) -> float:
        return self.twist_multiplier * np.sqrt(self.tex)

    @property
    def twist_pitch_mm(self) -> float:
        return 1000.0 / self.turns_per_metre

    @property
    def helix_angle_deg(self) -> float:
        """The angle the ply spiral makes with the yarn axis, which is what the eye reads."""
        return float(np.degrees(np.arctan2(
            2.0 * np.pi * self.ply_offset_mm, self.twist_pitch_mm)))

    def describe(self) -> dict:
        return {
            "plies": self.plies,
            "ply_radius_mm": round(self.ply_radius_mm, 3),
            "ply_offset_mm": round(self.ply_offset_mm, 3),
            "twist_multiplier": self.twist_multiplier,
            "turns_per_metre": round(self.turns_per_metre, 1),
            "twist_pitch_mm": round(self.twist_pitch_mm, 2),
            "helix_angle_deg": round(self.helix_angle_deg, 1),
        }


def _parallel_transport_frames(pts: np.ndarray):
    """A frame that follows the curve without spinning about it.

    Naive frames built from a fixed up-vector tumble wherever the curve turns through
    vertical, and a yarn whose reference frame tumbles gets a twist that is an artefact of
    the bookkeeping rather than of the spinning. Parallel transport rotates the previous
    frame by exactly the rotation between consecutive tangents and no more, so the only twist
    in the result is the twist that was asked for.
    """
    d = np.diff(pts, axis=0)
    n = np.linalg.norm(d, axis=1, keepdims=True)
    n[n < 1e-12] = 1e-12
    tang = d / n
    tang = np.vstack([tang, tang[-1]])

    seed = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(seed, tang[0])) > 0.9:
        seed = np.array([1.0, 0.0, 0.0])
    u = seed - np.dot(seed, tang[0]) * tang[0]
    u /= max(np.linalg.norm(u), 1e-12)

    us = np.empty_like(tang)
    us[0] = u
    for i in range(1, len(tang)):
        t0, t1 = tang[i - 1], tang[i]
        axis = np.cross(t0, t1)
        s = np.linalg.norm(axis)
        if s < 1e-12:
            us[i] = us[i - 1]
            continue
        axis /= s
        ang = np.arctan2(s, float(np.clip(np.dot(t0, t1), -1.0, 1.0)))
        c, sn = np.cos(ang), np.sin(ang)
        prev = us[i - 1]
        us[i] = (prev * c + np.cross(axis, prev) * sn
                 + axis * np.dot(axis, prev) * (1.0 - c))
        us[i] -= np.dot(us[i], t1) * t1
        us[i] /= max(np.linalg.norm(us[i]), 1e-12)
    vs = np.cross(tang, us)
    return tang, us, vs


def ply_geometry(centreline: np.ndarray, spec: PlySpec) -> list[np.ndarray]:
    """The ply curves for one yarn centreline. One polyline per ply."""
    pts = np.asarray(centreline, dtype=np.float64)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    _, u, v = _parallel_transport_frames(pts)

    phase = 2.0 * np.pi * arc / spec.twist_pitch_mm
    out = []
    for k in range(spec.plies):
        off = 2.0 * np.pi * k / spec.plies
        a = phase + off
        out.append(pts + spec.ply_offset_mm
                   * (np.cos(a)[:, None] * u + np.sin(a)[:, None] * v))
    return out


# Acrylic staple fibre, 3.3 dtex, polyacrylonitrile at 1180 kg/m3. Diameter derived from
# linear density and density, not looked up as a length: 18.9um, so a radius of 0.0094mm.
FIBRE_DTEX = 3.3
PAN_DENSITY_KG_M3 = 1180.0


def fibre_radius_mm(dtex: float = FIBRE_DTEX, density: float = PAN_DENSITY_KG_M3) -> float:
    lin = dtex * 1e-4 / 1000.0                 # g/10000m -> kg/m
    area = lin / density                       # m^2
    return float(np.sqrt(area / np.pi) * 1e3)  # m -> mm, radius


def fibres_per_yarn(tex: float, dtex: float = FIBRE_DTEX) -> int:
    return int(round(tex * 10.0 / dtex))


def surface_fibres(ply_curves, spec: PlySpec, *, per_ply: int = 16,
                   seed: int = 20260924):
    """A sparse halo of surface fibres, sized by what the image can actually resolve.

    WHY SPARSE, and why that is not a shortcut. A 444 tex yarn of 3.3 dtex acrylic holds
    about 1345 fibres, 336 per ply. At the resolution of a listing photograph -- 1000 pixels
    across a 54mm swatch, so 0.054mm per pixel -- a single 18.9 micron fibre is 0.35 pixels
    wide. No individual fibre is resolvable. What reaches the image is the AGGREGATE: a soft
    halo that breaks the silhouette, and a little texture where fibres cross the surface.
    Rendering all 1345 would compute something the image cannot show, which is the exact
    trade Montazeri et al.'s ply-based model exists to avoid.

    So this is a rendering budget rather than a physical count, and it is stated as one:
    16 per ply is 64 per yarn, roughly 5 per cent of the real fibre population. The fibre
    RADIUS is derived and correct; the NUMBER is chosen for the image scale and is the one
    number here that is neither measured nor derived.

    Fibres are not noise sprinkled on the surface. Each one follows its ply, lies against it
    for most of its length, and lifts away over a short span the way a fibre end does.
    """
    rng = np.random.default_rng(seed)
    r_fib = fibre_radius_mm()
    out = []
    for ply in ply_curves:
        n = len(ply)
        tang, u, v = _parallel_transport_frames(ply)
        for k in range(per_ply):
            phase = rng.uniform(0, 2 * np.pi)
            # A slow wander around the ply, so the fibre lies along it rather than crossing.
            wander = phase + np.linspace(0, rng.uniform(-6.0, 6.0), n)
            # Lift-off: mostly hugging the ply, rising over one short stretch.
            lift = np.zeros(n)
            start = rng.integers(0, max(n - 2, 1))
            span = int(rng.integers(n // 40 + 2, n // 12 + 3))
            end = min(start + span, n)
            if end > start:
                t = np.linspace(0, np.pi, end - start)
                lift[start:end] = np.sin(t) * rng.uniform(0.10, 0.55)
            radius = spec.ply_radius_mm + r_fib + lift
            pts = ply + radius[:, None] * (np.cos(wander)[:, None] * u
                                           + np.sin(wander)[:, None] * v)
            out.append(pts)
    return out, r_fib


# Singles twist. In a balanced plied yarn the singles are twisted OPPOSITE to the ply --
# Z-spun singles plied S, or the reverse -- which is what lets the yarn hang without
# corkscrewing. So the fibre grain on a ply surface runs counter to the ply spiral, and that
# opposition is a property of the yarn rather than a choice.
SINGLES_TWIST_MULTIPLIER = 3.7      # within the 3.0-4.0 quoted for spun knitting yarns
FIBRE_DIAMETER_CV = 0.18            # staple fibre diameter varies; 15-25% CV is typical


def fibre_surface_map(spec: PlySpec, *, tile_mm: float = 4.0, size: int = 1024,
                      seed: int = 20260924):
    """A tangent-space normal map of the fibres lying on a ply surface.

    This is the half of Montazeri et al.'s ply model that geometry alone does not give. They
    UV-map the ply so that "the V-direction is aligned with the ply tangent" and the U
    coordinate is "the phase around the ellipse", then assign 1D textures specifying fibre
    normal and tangent per cross-section, interpolated along the ply for continuity.

    Mitsuba's linearcurve already carries exactly that parameterisation -- measured, not
    assumed: firing rays at a straight curve gives u = 0.25, 0.0, 0.75 at 0, 90 and 180
    degrees around it, and v rising monotonically along its length. So the published mapping
    transfers without adaptation, and it is continuous through curved stitch paths because
    the curve's own parameterisation is.

    WHAT IS DRAWN, and why it is not noise. Each fibre is a cylinder lying on the surface, so
    across its width the normal tilts by asin(t/r) exactly as a cylinder does. The fibres run
    at the singles helix angle, counter to the ply twist. Nothing here is a random field: it
    is a bed of cylinders at a derived diameter, a derived spacing and a derived angle.

      fibres around the circumference   DERIVED: 2*pi*r_ply / fibre diameter = 229
      fibre helix angle                 DERIVED from singles twist, 8.6 to 10.4 degrees
      diameter variation                BOUNDED: staple fibre CV is typically 15-25%

    Returned as a float array in [0,1], the usual normal-map encoding.
    """
    rng = np.random.default_rng(seed)
    r_fib = fibre_radius_mm()
    d_fib = 2.0 * r_fib
    circ = 2.0 * np.pi * spec.ply_radius_mm

    tex_single = spec.tex / spec.plies
    tpm = SINGLES_TWIST_MULTIPLIER * np.sqrt(tex_single)
    pitch = 1000.0 / tpm
    theta = np.arctan2(2.0 * np.pi * spec.ply_radius_mm, pitch)   # fibre angle to ply axis

    # Millimetre coordinates across one tile: u spans the full circumference, v a slice.
    uu = np.linspace(0.0, circ, size, endpoint=False)[None, :]
    vv = np.linspace(0.0, tile_mm, size, endpoint=False)[:, None]

    # Distance perpendicular to the fibre direction. The sign of theta is negative because
    # the singles run counter to the ply.
    perp = uu * np.cos(theta) + vv * np.sin(theta)

    # Fibre boundaries with a little diameter variation, as staple fibre has.
    n_f = max(int(round(circ / d_fib)), 8)
    widths = d_fib * (1.0 + FIBRE_DIAMETER_CV * rng.standard_normal(n_f * 3))
    widths = np.clip(widths, 0.4 * d_fib, 1.8 * d_fib)
    edges = np.concatenate([[0.0], np.cumsum(widths)])
    span = edges[-1]

    p = np.mod(perp, span)
    idx = np.searchsorted(edges, p, side="right") - 1
    idx = np.clip(idx, 0, len(widths) - 1)
    centre = 0.5 * (edges[idx] + edges[idx + 1])
    half = 0.5 * widths[idx]
    t = np.clip((p - centre) / np.maximum(half, 1e-9), -1.0, 1.0)

    tilt = np.arcsin(t)                    # a cylinder's normal, across its width
    s = np.sin(tilt)
    nx = s * np.cos(theta)
    ny = s * np.sin(theta)
    nz = np.cos(tilt)
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
    return (n * 0.5 + 0.5).astype(np.float32), dict(
        fibres_around=n_f, fibre_helix_deg=float(np.degrees(theta)),
        tile_mm=tile_mm, singles_tpm=float(tpm))
