"""Deterministic statistics for the learning loops (ENG-LEARN).

Every learning decision here is a count compared with a count, by code a reviewer can re-run.
There is no model judgement, randomness or bootstrap, so the same observations always give
the same verdict.

**Why the thresholds are strict.** The loops re-evaluate every day, which means looking at the
same growing comparison many times. A test run at alpha 0.05 on every look will eventually
"find" a difference between two identical prompts. So promotion needs all of the following:
- a one-sided p below `ALPHA` (0.002);
- a minimum sample on both arms;
- a minimum absolute lift.

The noise tests in `tests/test_eng_learn.py` measure the false-promotion rate on identical
arms over many sequential looks.
"""
from __future__ import annotations

import math

ALPHA = 0.002          # one-sided, per look
MIN_N = 40             # observations per arm before any promotion verdict
MIN_LIFT = 0.08        # absolute first-pass-rate lift a promotion needs
HARM_ALPHA = 0.05      # a challenger measurably WORSE is stopped early (it costs retries)
HARM_MIN_N = 15
LESSON_MIN_N = 20      # per side, for a derived scene lesson
LESSON_ALPHA = 0.01
TREND_MIN_N = 10       # per window, for a trend to be stated at all

UNKNOWN = "UNKNOWN"


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """The Wilson score interval for k successes in n, or None with no observations."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - r) / d, 4), round((c + r) / d, 4))


def two_proportion(k_a: int, n_a: int, k_b: int, n_b: int) -> dict:
    """One-sided test that B's rate exceeds A's (pooled z). p is 1.0 when it cannot be read."""
    if n_a <= 0 or n_b <= 0:
        return {"p": 1.0, "z": 0.0, "rate_a": None, "rate_b": None, "lift": None}
    pa, pb = k_a / n_a, k_b / n_b
    pool = (k_a + k_b) / (n_a + n_b)
    se = math.sqrt(pool * (1 - pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        # Both arms are all-pass or all-fail: no evidence of any difference.
        return {"p": 1.0, "z": 0.0, "rate_a": round(pa, 4), "rate_b": round(pb, 4),
                "lift": round(pb - pa, 4)}
    z = (pb - pa) / se
    return {"p": round(1 - _phi(z), 6), "z": round(z, 4), "rate_a": round(pa, 4),
            "rate_b": round(pb, 4), "lift": round(pb - pa, 4)}


def welch_lower(a: list[float], b: list[float]) -> dict:
    """One-sided Welch test (normal approximation) that mean(b) is LOWER than mean(a).

    Used for cost: B is cheaper. p is 1.0 when either side has fewer than two values."""
    if len(a) < 2 or len(b) < 2:
        return {"p": 1.0, "mean_a": None, "mean_b": None}
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return {"p": 0.0 if mb < ma else 1.0, "mean_a": round(ma, 4), "mean_b": round(mb, 4)}
    z = (ma - mb) / se
    return {"p": round(1 - _phi(z), 6), "mean_a": round(ma, 4), "mean_b": round(mb, 4)}


def rate(k: int, n: int, *, min_n: int = TREND_MIN_N) -> dict:
    """A rate with its interval, or UNKNOWN (with the n it has and needs) when too small."""
    if n < min_n:
        return {"status": UNKNOWN, "k": k, "n": n, "needs_n": min_n,
                "why": f"{n} observations; a rate is stated from {min_n}"}
    return {"status": "MEASURED", "k": k, "n": n, "rate": round(k / n, 4),
            "interval": wilson(k, n)}
