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
