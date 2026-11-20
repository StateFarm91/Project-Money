"""Hand tension: does the variation model say what it claims to say?

The failure this file exists to prevent is the one that already happened once here. The
first drift field normalised by standard deviation but not by mean; with a correlation
length longer than the swatch the field went nearly constant, dividing by its tiny standard
deviation amplified the residual mean to about -8, and stitch widths came out NEGATIVE.
The anchor then divided by a negative row sum, flipped the signs back, and returned
plausible-looking positive widths with the variation crushed to a tenth of its specified
size. Every value printed fine. Only measuring the realised statistic caught it, so that is
what these tests do: they measure the output rather than trusting the parameter.
"""
import sys
import numpy as np

sys.path.insert(0, "src")
from brambleloop.visual.hand_tension import (      # noqa: E402
    HandTension, tension_field, realised_variation, PROVENANCE)

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED += 1
        print("FAIL", name, detail)


L, H = 6.897, 10.526
R, C = 7, 7

# --- the anchor, which is the owner's hard constraint -------------------------
w, h, delta = tension_field(R, C, L, H, HandTension())
check("every row spans exactly the certified width",
      np.allclose(w.sum(axis=1), C * L, atol=1e-9), str(w.sum(axis=1)))
check("the rows total exactly the certified height",
      abs(h.sum() - R * H) < 1e-9, str(h.sum()))
check("no stitch has zero or negative width", w.min() > 0, str(w.min()))
check("no row has zero or negative height", h.min() > 0, str(h.min()))

# --- REGRESSION: the sign bug -------------------------------------------------
# Preserved as a fixture per the standing rule that failed cases stay. The deviation field
# is fractional, so a correct one stays within a few tenths of zero. The bug produced -8.
check("the deviation field is centred near zero, not offset by the mean bug",
      abs(delta.mean()) < 0.25, "mean=%.4f" % delta.mean())
check("no deviation is anywhere near -100%, which would invert a stitch",
      np.abs(delta).max() < 0.5, "max|delta|=%.4f" % np.abs(delta).max())
# The bug was only visible BEFORE the anchor renormalised, so check that stage directly.
raw = L * (1.0 + delta)
check("widths are positive BEFORE the anchor renormalises them",
      raw.min() > 0, "min raw width=%.4f" % raw.min())

# A correlation length far longer than the swatch is the exact configuration that broke it.
for drift_cm in (12.0, 50.0, 500.0):
    hand = HandTension(drift_length_cm=drift_cm)
    ww, hh, dd = tension_field(R, C, L, H, hand)
    check("a %gcm drift length over a 5cm swatch stays sane" % drift_cm,
          ww.min() > 0 and abs(dd.mean()) < 0.25 and np.allclose(ww.sum(axis=1), C * L),
          "min w=%.4f mean d=%.4f" % (ww.min(), dd.mean()))

# --- it must not be independent jitter ---------------------------------------
# The owner's requirement is spatial correlation. Neighbouring stitches must resemble one
# another more than distant ones do; white noise would show no such falloff.
big_w, _, big_d = tension_field(24, 24, L, H, HandTension())
d0 = big_d - big_d.mean()
near = float(np.mean(np.abs(d0[:, 1:] - d0[:, :-1])))
far = float(np.mean(np.abs(d0[:, 12:] - d0[:, :-12])))
check("neighbouring stitches are more alike than distant ones (correlated, not jitter)",
      near < far, "adjacent %.5f vs distant %.5f" % (near, far))
# Row tension must drift, and must DECORRELATE with distance. Measured as a correlation
# over many seeds rather than one, because a single seed of a smooth field is not a sample.
# The first drift field failed this: built from three modes all at the correlation length,
# it was periodic, so rows one wavelength apart resembled each other more than adjacent
# ones. The correlation at long lag must fall to about nothing, and it is the falloff that
# is being tested -- the lag-1 value is capped well below 1 because the per-row term is
# deliberately independent, carrying a third of the variance.
near_c, far_c = [], []
for seed in range(24):
    _, _, dd = tension_field(40, 12, L, H, HandTension(seed=100 + seed))
    rm = dd.mean(axis=1) - dd.mean()
    near_c.append(np.corrcoef(rm[1:], rm[:-1])[0, 1])
    far_c.append(np.corrcoef(rm[20:], rm[:-20])[0, 1])
near_c, far_c = float(np.mean(near_c)), float(np.mean(far_c))
check("row tension is correlated from one row to the next",
      near_c > 0.15, "lag-1 correlation %.3f" % near_c)
check("row tension decorrelates well beyond the drift length (not periodic)",
      abs(far_c) < 0.12 and far_c < near_c,
      "lag-1 %.3f vs lag-20 %.3f" % (near_c, far_c))

# --- Munden: one perturbation, two dimensions, linearly ----------------------
# Width and height both scale with loop length, so a fabric made with more variation must
# show proportionally more in BOTH. If only one responded, the published relation would not
# have been implemented.
lo = realised_variation(R, C, L, H, HandTension(total_cv=0.02), seeds=24)
hi = realised_variation(R, C, L, H, HandTension(total_cv=0.08), seeds=24)
ratio_w = hi["observed_stitch_width_cv"] / lo["observed_stitch_width_cv"]
ratio_h = hi["observed_row_height_cv"] / lo["observed_row_height_cv"]
check("stitch width responds linearly to loop-length variation (Munden)",
      abs(ratio_w - 4.0) < 0.4, "ratio=%.3f" % ratio_w)
check("row height responds linearly to loop-length variation (Munden)",
      abs(ratio_h - 4.0) < 0.4, "ratio=%.3f" % ratio_h)

# --- honesty about what the anchor costs -------------------------------------
r = realised_variation(R, C, L, H, HandTension(), seeds=32)
check("the anchor holds to floating-point precision across many seeds",
      r["worst_anchor_error_mm"] < 1e-9, str(r["worst_anchor_error_mm"]))
check("observable variation is reported as LESS than specified, not as equal to it",
      r["observed_stitch_width_cv"] < r["specified_loop_length_cv"],
      "%.4f vs %.4f" % (r["observed_stitch_width_cv"], r["specified_loop_length_cv"]))
check("observable variation is still in the perceptible band (above ~1%)",
      r["observed_stitch_width_cv"] > 0.01 and r["observed_row_height_cv"] > 0.01,
      "w %.4f h %.4f" % (r["observed_stitch_width_cv"], r["observed_row_height_cv"]))
check("observable variation stays below the 10% that reads as a fault",
      r["observed_stitch_width_cv"] < 0.10 and r["observed_row_height_cv"] < 0.10)

# --- determinism, because a product must be reproducible ----------------------
a = tension_field(R, C, L, H, HandTension(seed=7))[0]
b = tension_field(R, C, L, H, HandTension(seed=7))[0]
c = tension_field(R, C, L, H, HandTension(seed=8))[0]
check("the same seed gives the same fabric", np.array_equal(a, b))
check("a different seed gives a different fabric", not np.array_equal(a, c))

# --- a machine, for comparison -----------------------------------------------
z = realised_variation(R, C, L, H, HandTension(total_cv=0.0), seeds=4)
check("zero tension variation reproduces the identical-stitch control exactly",
      z["observed_stitch_width_cv"] < 1e-12 and z["observed_row_height_cv"] < 1e-12)

# --- provenance ---------------------------------------------------------------
check("every parameter carries a provenance label",
      set(PROVENANCE) >= {"mechanism", "total_cv", "drift_length_cm", "variance_split"})
check("the variance split is labelled an estimate rather than sourced",
      "estimate" in PROVENANCE["variance_split"].lower(), PROVENANCE["variance_split"])

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
