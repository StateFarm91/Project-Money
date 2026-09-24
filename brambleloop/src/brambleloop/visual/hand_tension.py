"""Hand-made variation: what a person's tension does to a crocheted fabric.

Every stitch in the certified geometry is identical, and after the material layers were
right that repetition became the loudest remaining cue that the image is synthetic. Real
crochet is made by a hand whose tension drifts, and this is the smallest physically
defensible model of that.

WHAT VARIES, AND WHY IT IS THE RIGHT QUANTITY. Not stitch width directly: LOOP LENGTH, the
yarn drawn through per stitch, which is what a hand actually controls. Munden (1959)
established for plain knitted fabric that courses per cm times loop length and wales per cm
times loop length are both constants, independent of cover factor. So stitch height and
stitch width each scale LINEARLY with loop length, and one perturbation propagates to both
by a published relation rather than by two invented ones.

HOW MUCH. Two independent sources agree on where perceptibility begins:

  * Machine-knitting quality literature: "an irregular loop length can be defined as a
    difference in loop length of 4% or more, though differences of 10% or more are more
    noticeable in knitted fabric."
  * Crochet craft practice: if two places in a swatch differ by more than half a stitch,
    the tension is uneven. At this pattern's 14.5 stitches per 10cm, half a stitch is 3.4%.

A competent maker selling on Etsy sits in the detectable-but-not-obvious band, so the
default total is 5%: above the ~3.4-4% where variation becomes visible at all, well below
the 10% that reads as a fault. Bounded by evidence at both ends rather than chosen.

HOW IT IS CORRELATED, which is the part that separates hand work from noise. Craft sources
describe three distinct behaviours and this model has exactly those three and nothing else:

  DRIFT     Tension wanders over a long distance -- "compare your current rows against
            earlier rows every 10-15cm to catch drift early". A smooth field with a
            correlation length of about 12cm.
  ROW       Each row has its own tension: a row worked while tired or distracted comes out
            looser than its neighbours.
  STITCH    Individual stitches come out tighter or looser, uncorrelated.

Independent per-stitch jitter alone is what noise looks like; real hand work is dominated
by the first two, so they carry most of the variance here.

WHAT IS ANCHORED. The certified product is not negotiable, so the field is renormalised:
mean row height is exactly the gauge row height, and every row's widths sum to exactly the
certified row width. Local variation is therefore real and cannot accumulate into garment
drift. Stitch count, stitch type, loop targets, topology and joins are untouched -- this
module only says how big each stitch is, never what it is.

WHAT THE ANCHOR COSTS, stated plainly because the specified number and the visible number
are not the same and it would be easy to quote the flattering one. The specified total is
5% of loop length, but the anchor is a constraint on the same field, and it removes exactly
the long-wavelength part: renormalising each row's widths subtracts that row's mean, which
deletes the row term from the widths outright and most of the drift with it. What survives
to be seen is about 2.5% in stitch width and 3.2% in row height (measured over 200 seeds,
matching the per-component prediction). That is not leakage, it is the physical content of
the anchor -- a maker who checks gauge against the pattern is doing precisely this
correction, absorbing slow drift while leaving stitch-to-stitch variation in the fabric.
The honest claim for this module is therefore 5% of loop length generated, ~2.5-3.2%
observable after gauge is held, and `realised_variation` measures it rather than asserting
it.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

__all__ = ["HandTension", "tension_field", "realised_variation", "PROVENANCE"]

PROVENANCE = {
    "mechanism": "sourced -- Munden (1959): course and wale spacing each scale linearly "
                 "with loop length, so one loop-length perturbation drives both",
    "total_cv": "bounded by two independent sources -- 4% is where loop-length irregularity "
                "becomes detectable and 10% where it is clearly noticeable (machine knitting "
                "quality literature); half a stitch over a gauge swatch, which is 3.4% here, "
                "is the craft threshold for 'uneven'. 5% sits deliberately between them",
    "drift_length_cm": "sourced from craft practice -- makers are advised to compare rows "
                       "every 10-15cm to catch tension drift, so drift is coherent over "
                       "roughly that distance",
    "variance_split": "BOUNDED ESTIMATE. That drift, row and stitch components all exist is "
                      "sourced; their relative sizes are not measured. Drift and row are "
                      "given the larger share because hand tension is described as wandering "
                      "and as differing between rows, not as independent per stitch",
}


@dataclass(frozen=True)
class HandTension:
    total_cv: float = 0.05          # 5%: above ~3.4-4% detectable, below 10% obvious
    drift_share: float = 0.45       # fraction of VARIANCE in the long wander
    row_share: float = 0.35         # fraction of variance in per-row tension
    stitch_share: float = 0.20      # fraction of variance in per-stitch jitter
    drift_length_cm: float = 12.0
    seed: int = 20260924
    provenance: dict = field(default_factory=lambda: dict(PROVENANCE))

    def sigmas(self) -> tuple[float, float, float]:
        """Component standard deviations, from the variance split."""
        total = self.drift_share + self.row_share + self.stitch_share
        return tuple(self.total_cv * np.sqrt(s / total)
                     for s in (self.drift_share, self.row_share, self.stitch_share))


def _drift_field(rows, cols, L_mm, H_mm, length_mm, sigma, rng):
    """Slow tension wander, as a few low-frequency modes.

    Built from modes rather than by filtering noise because filtering has a pathology here
    that bit once already: when the correlation length exceeds the patch -- and it does, a
    12cm drift scale against a 5cm swatch -- the filtered field is nearly constant, its
    standard deviation is nearly zero, and normalising by that standard deviation amplifies
    its residual mean enormously. The first version produced deviations around -8.0 where it
    should have produced a few per cent.

    Modes have no such failure. Over a large piece they give a field of standard deviation
    `sigma`; over a patch smaller than one wavelength they give a gentle gradient, which is
    exactly what a slow drift looks like when you only see 5cm of it.
    """
    xs = (np.arange(cols) + 0.5) * L_mm
    ys = (np.arange(rows) + 0.5) * H_mm
    gx, gy = np.meshgrid(xs, ys)
    # Wavelengths SPREAD around the correlation length, not all equal to it. The previous
    # version used three modes all at exactly `length_mm`, which sums to a PERIODIC field:
    # it repeats every 12cm, so over a garment the drift would appear as regular banding at
    # a fixed pitch -- the opposite of the wandering it is meant to represent. The test
    # caught it as rows twelve apart, one full wavelength, resembling each other MORE than
    # adjacent rows did. Drawing each mode's wavelength from a half-octave either side makes
    # the sum aperiodic over any distance that matters, while keeping the characteristic
    # scale where the source puts it. Five rather than three only so that the spread has
    # something to spread over.
    n_modes = 5
    amp = sigma * np.sqrt(2.0 / n_modes)
    out = np.zeros((rows, cols))
    for _ in range(n_modes):
        ang = rng.uniform(0, 2 * np.pi)
        phase = rng.uniform(0, 2 * np.pi)
        k = 2.0 * np.pi / (length_mm * rng.uniform(0.7, 1.4))
        out += amp * np.cos(k * (gx * np.cos(ang) + gy * np.sin(ang)) + phase)
    return out


def tension_field(rows: int, cols: int, L_mm: float, H_mm: float,
                  hand: HandTension | None = None):
    """Per-stitch loop-length deviation, and the widths and heights it implies.

    Returns (widths[rows, cols], heights[rows]) in millimetres, renormalised so that every
    row is exactly cols * L_mm wide and the mean row height is exactly H_mm.
    """
    hand = hand or HandTension()
    rng = np.random.default_rng(hand.seed)
    s_drift, s_row, s_stitch = hand.sigmas()

    drift = _drift_field(rows, cols, L_mm, H_mm,
                         hand.drift_length_cm * 10.0, s_drift, rng)

    row_term = (rng.standard_normal(rows) * s_row)[:, None]
    stitch = rng.standard_normal((rows, cols)) * s_stitch

    delta = drift + row_term + stitch          # fractional loop-length deviation

    # Munden: width and height each scale linearly with loop length.
    widths = L_mm * (1.0 + delta)
    heights = H_mm * (1.0 + delta.mean(axis=1))

    # ANCHOR. Each row is renormalised to the certified row width, and the row heights to
    # the certified mean, so variation is local and the garment cannot drift.
    widths *= (cols * L_mm) / widths.sum(axis=1, keepdims=True)
    heights *= (rows * H_mm) / heights.sum()
    return widths, heights, delta


def realised_variation(rows: int, cols: int, L_mm: float, H_mm: float,
                       hand: HandTension | None = None, seeds: int = 64):
    """Measure what actually survives the anchor, rather than quoting what went in.

    The specified CV is a property of the generated loop-length field; the anchor then
    removes its long-wavelength part. These are different numbers and only this one is
    observable in the fabric, so it is measured over many seeds and reported.
    """
    hand = hand or HandTension()
    widths_cv, heights_cv, anchor_err = [], [], 0.0
    for s in range(seeds):
        w, h, _ = tension_field(rows, cols, L_mm, H_mm,
                                dataclasses.replace(hand, seed=hand.seed + s))
        widths_cv.append(float(np.mean([w[r].std() / w[r].mean() for r in range(rows)])))
        heights_cv.append(float(h.std() / h.mean()))
        anchor_err = max(anchor_err,
                         float(np.abs(w.sum(axis=1) - cols * L_mm).max()),
                         float(abs(h.sum() - rows * H_mm)))
    return {
        "specified_loop_length_cv": hand.total_cv,
        "observed_stitch_width_cv": float(np.mean(widths_cv)),
        "observed_row_height_cv": float(np.mean(heights_cv)),
        "worst_anchor_error_mm": anchor_err,
        "seeds": seeds,
    }
