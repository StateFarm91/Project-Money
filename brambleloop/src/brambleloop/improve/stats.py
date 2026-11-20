"""The one significance test the self-improvement team decides on: two proportions.

Every department KPI the team tunes against is a rate measured from rows (useful completions
over finished runs, granted certificates over attempts, ...), so a pooled two-proportion
z-test is the honest instrument. The same formula `visual.rnd.loop._z` uses for marketplace
calibration; kept here without that module's imports so the cadence job stays light.

Three rules make it safe to call repeatedly on a growing stream (peeking):
* a floor on the sample in EACH arm before anything is decided (`MIN_ARM_N`);
* a promotion is judged only at fixed LOOKS -- the first MIN_ARM_N * 2**k units of each arm
  (`checkpoint`) -- however often the job runs, so a trial gets at most `len(LOOKS)` looks;
* a strict per-look threshold (`PROMOTE_Z`, one-sided alpha 0.0025; Bonferroni over the
  looks keeps the family-wise false-promotion rate under 2%) together with a minimum
  absolute effect (`MIN_EFFECT`), so a promotion needs a gain that is both unlikely to be
  noise and large enough to matter. Measured: 0 of 40 null streams promote
  (tests/test_eng_improve.py).
A small sample is UNKNOWN, never a trend.
"""
from __future__ import annotations

import math

# These are evidence floors: the invariants guard refuses any proposal that names them
# (vocabulary "min_", "significan", "regression" ...), so the loop cannot lower its own bar.
MIN_ARM_N = 50
PROMOTE_Z = 2.807          # one-sided alpha 0.0025 per look
LOOKS: tuple[int, ...] = tuple(MIN_ARM_N * 2 ** k for k in range(6))   # 50 .. 1600
HARM_Z = 1.96              # a challenger this much worse stops at once
REGRESSION_Z = 1.96        # a promoted value this much worse than its holdback rolls back
MIN_EFFECT = 0.03          # absolute rate gain a promotion must also show
TREND_MIN_N = 20           # per window, for a department KPI trend


def z_two_proportions(x1: int, n1: int, x2: int, n2: int) -> float | None:
    """z for rate1 - rate2 (pooled); None when either arm is empty or the pool is degenerate."""
    if not n1 or not n2:
        return None
    p = (x1 + x2) / (n1 + n2)
    if not 0 < p < 1:
        return 0.0 if x1 / n1 == x2 / n2 else None
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return ((x1 / n1) - (x2 / n2)) / se


def checkpoint(n_smaller_arm: int) -> int | None:
    """The look a trial is judged at: the largest LOOK the smaller arm has reached."""
    reached = [k for k in LOOKS if k <= n_smaller_arm]
    return reached[-1] if reached else None


def one_sided_p(z: float | None) -> float | None:
    return None if z is None else 0.5 * math.erfc(z / math.sqrt(2))


def compare(new: tuple[int, int], old: tuple[int, int], *, min_n: int = MIN_ARM_N) -> dict:
    """The comparison of `new` (successes, trials) against `old`, with its verdict.

    verdict: UNKNOWN (an arm below `min_n`), BETTER (z >= PROMOTE_Z and gain >= MIN_EFFECT),
    WORSE (z <= -HARM_Z), or NO_DIFFERENCE.
    """
    (x1, n1), (x2, n2) = new, old
    out = {"new": {"successes": x1, "trials": n1, "rate": round(x1 / n1, 4) if n1 else None},
           "old": {"successes": x2, "trials": n2, "rate": round(x2 / n2, 4) if n2 else None},
           "min_n": min_n}
    if n1 < min_n or n2 < min_n:
        return {**out, "verdict": "UNKNOWN", "z": None, "gain": None,
                "why": f"needs >= {min_n} trials in each arm (have {n1} and {n2})"}
    z = z_two_proportions(x1, n1, x2, n2)
    gain = x1 / n1 - x2 / n2
    out.update(z=None if z is None else round(z, 3), gain=round(gain, 4),
               p_one_sided=None if z is None else round(one_sided_p(z), 5))
    if z is None:
        return {**out, "verdict": "NO_DIFFERENCE", "why": "degenerate pool"}
    if z >= PROMOTE_Z and gain >= MIN_EFFECT:
        return {**out, "verdict": "BETTER",
                "why": f"z={z:.2f} >= {PROMOTE_Z} and gain {gain:+.3f} >= {MIN_EFFECT}"}
    if z <= -HARM_Z:
        return {**out, "verdict": "WORSE", "why": f"z={z:.2f} <= -{HARM_Z}"}
    return {**out, "verdict": "NO_DIFFERENCE",
            "why": f"z={z:.2f}, gain {gain:+.3f}: not a meaningful difference"}


def trend(recent: tuple[int, int], prior: tuple[int, int]) -> dict:
    """UP / DOWN / FLAT between two windows, or UNKNOWN when either is small. Never invented."""
    (x1, n1), (x2, n2) = recent, prior
    base = {"recent": {"successes": x1, "trials": n1,
                       "rate": round(x1 / n1, 4) if n1 else None},
            "prior": {"successes": x2, "trials": n2,
                      "rate": round(x2 / n2, 4) if n2 else None}}
    if n1 < TREND_MIN_N or n2 < TREND_MIN_N:
        return {**base, "trend": "UNKNOWN",
                "why": f"needs >= {TREND_MIN_N} finished runs in each window "
                       f"(have {n1} recent, {n2} prior)"}
    z = z_two_proportions(x1, n1, x2, n2)
    if z is None:
        return {**base, "trend": "UNKNOWN", "why": "degenerate pool"}
    t = "UP" if z >= HARM_Z else "DOWN" if z <= -HARM_Z else "FLAT"
    return {**base, "trend": t, "z": round(z, 3)}
