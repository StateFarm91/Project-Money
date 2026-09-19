"""Events against departments, with the competitor's half filled from what was observed.

Requirement 299. For each major event and department, hold a matrix of the elite benchmark's
product markets against Brambleloop's coverage, and use it to expose proven markets nobody
here serves.

Half of this already existed: the calendar knows which departments an occasion spans and
which of them this catalogue answers. The missing half was the benchmark's, and it was
missing for a specific reason -- nothing had ever observed a competitor's catalogue. That
changed on 2026-09-19, when the developer credential was verified by use and 438 listings
were read from the benchmark shop.

So this module is deliberately thin. It joins two things that already exist and refuses the
one thing that would make the join a lie: reporting a department as *unserved by the market*
when the market was never observed. Absence of evidence arrives looking exactly like evidence
of absence in a matrix, because both render as an empty cell, and an empty cell is what
somebody points at in a planning meeting.
"""
from __future__ import annotations

from datetime import date

from ..intel import benchmarks
from .calendar import coverage_matrix

OBSERVED, UNOBSERVED = "observed", "unobserved"


# The key the proven-and-unserved rows are returned under. A constant because a reader
# guessed it wrong once and got an empty list, which reads exactly like a catalogue that
# answers every proven market.
PROVEN_KEY = "proven_and_unserved"


def benchmark_depth(db, *, benchmark_key: str | None = None) -> dict:
    """How many observed listings the benchmark has in each department.

    The key defaults to the constant the scanner writes, never to a short string that looks
    like it. The first version of this defaulted to "mjs" while the scanner wrote
    "mjs_off_the_hook_designs", so it read zero listings from a database holding 438 and
    reported that as "nothing has been observed" -- which is exactly the sentence this module
    exists to stop anybody saying wrongly.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = [r.pod for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))]

    counts: dict[str, int] = {}
    for pod in rows:
        if pod:
            counts[pod] = counts.get(pod, 0) + 1
    return {"observed": len(rows), "by_department": counts,
            "basis": OBSERVED if rows else UNOBSERVED}


def matrix(db, *, today: date | None = None,
           covered: dict[str, tuple[str, ...]] | None = None,
           benchmark_key: str | None = None) -> dict:
    """The full matrix: what the occasion spans, what we answer, what they were seen to sell.

    A department where the benchmark has listings and this catalogue has none is the row the
    requirement exists to surface: a proven market with no Brambleloop answer. A department
    where neither has anything is *not* that row, and saying so is the whole discipline here.
    """
    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    ours = coverage_matrix(today, covered=covered)
    theirs = benchmark_depth(db, benchmark_key=benchmark_key)
    observed = theirs["basis"] == OBSERVED

    rows = []
    for event in ours["rows"]:
        cells = []
        for department in event["departments"]:
            their_count = theirs["by_department"].get(department, 0)
            we_cover = department in event["covered"]
            cells.append({
                "department": department,
                "brambleloop": "covered" if we_cover else "absent",
                "benchmark_listings": their_count if observed else None,
                "benchmark_basis": theirs["basis"],
                # The only row the requirement is actually about, and it can only exist when
                # somebody has looked. Unobserved is reported as unknown, never as zero.
                "proven_and_unserved": bool(observed and their_count and not we_cover),
                "unknown_whether_proven": (not observed) and not we_cover,
            })
        cells.sort(key=lambda c: -(c["benchmark_listings"] or 0))
        rows.append({
            "event": event["event"], "days_away": event["days_away"],
            "phase": event["phase"], "depth": event["depth"], "cells": cells,
        })

    proven_gaps = [
        {"event": row["event"], "department": cell["department"],
         "benchmark_listings": cell["benchmark_listings"], "days_away": row["days_away"]}
        for row in rows for cell in row["cells"] if cell["proven_and_unserved"]]
    proven_gaps.sort(key=lambda g: (-g["benchmark_listings"], g["days_away"]))

    return {
        "today": ours["today"],
        "benchmark": benchmark_key,
        "benchmark_observed_listings": theirs["observed"],
        "rows": rows,
        PROVEN_KEY: proven_gaps,
        "note": (
            "no competitor listing has been observed, so every benchmark cell is unknown "
            "rather than empty. An unobserved market and a market with nothing in it render "
            "identically in a matrix, and the empty cell is the one somebody points at"
            if not observed else
            f"{len(proven_gaps)} department(s) where the benchmark was observed selling and "
            f"this catalogue has no answer, ordered by how much they sell there and how soon "
            f"the occasion is"),
    }
