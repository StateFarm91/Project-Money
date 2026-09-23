"""Whether the render pipeline is a capability or a run of luck, and what it costs.

A single passing sequence demonstrates possibility. Production needs a rate, and a rate
needs a standard written down before the sample is drawn -- otherwise the number that comes
back becomes the standard, which is how every disappointing measurement gets explained.

**The standard is about the gate, not about the generator.** The owner's framing on
2026-09-23 is the one that makes this tractable: a pipeline does not need a perfect
first-attempt rate if bad generations are reliably rejected and regeneration is
economically acceptable. What is unacceptable is a bad generation reaching a customer
because a gate wrongly passed it. So there are two standards and only one of them is about
image quality:

  CORRECTNESS -- no asset was ever marked usable with a floor that did not say `pass`.
                 This is absolute. One breach is a launch blocker, however good the rate.
  ECONOMICS   -- every attempted gallery reaches a usable state inside a bounded number of
                 attempts, at a cost per usable gallery this business can pay for every
                 product it sells.

**Failures are classified before they are counted.** A dimension that fails every time it
is asked is systematic and means the architecture is wrong; a dimension that fails some of
the times it is asked is stochastic and means retrying is the answer. Those need opposite
responses, and a single success rate hides which one you have -- the mistake this module
exists to stop anybody making again after watching v8, v10 and v11 each fail differently.

Each dimension is counted against the attempts that **asked** it, never against all
attempts. `product_truth` is decided by the detail frame and `morphology` by the fit frame,
so a floor asked three times and failed three times is systematic even in a sample of
thirty attempts. Dividing it by thirty instead would report an architecture failure as
bad luck -- the same wrong-denominator defect that made `remaining` subtract its own run's
work, and that made a coverage share read 1.0 because nothing had been observed.
"""
from __future__ import annotations

STANDARD_SET_AT = "2026-09-23"

# How many attempts a single gallery may take before the pipeline is not a pipeline.
#
# Three, matching `model_photography.ATTEMPTS`, and for the same reason: a fourth attempt is
# evidence that the method is wrong rather than the sample. With frame reuse an attempt
# re-renders only what failed, so three attempts is a genuine budget rather than three
# throws of everything. A gallery that spends all three without a usable asset has not been
# unlucky -- it has failed, and the product behind it cannot be listed.
MAX_ATTEMPTS_PER_GALLERY = 3

# What a usable gallery may cost, in Canadian dollars.
#
# Reasoned from the product rather than from the render. A pattern lists at roughly CA$9.50
# and its imagery is made once and serves the listing's whole life, so a ceiling near a
# fifth of a single sale is comfortably economic even before the second copy sells. At the
# observed ~CA$0.30-0.50 per attempt, three bounded attempts land inside it with room, and
# a pipeline that cannot is one whose architecture needs changing rather than whose budget
# needs raising.
MAX_CAD_PER_USABLE_GALLERY = 2.00

# Below this many completed galleries, a rate is not reported as one.
#
# The same rule `creative.blinded` applies to its own win rate: a proportion computed from
# two samples is not a capability measurement, and reporting it as one is how a company
# concludes it is ready. Deliberately small because cost containment is active -- this is
# the floor for saying anything at all, not a target sample.
MIN_GALLERIES_FOR_A_RATE = 3

# Below this many asks, a dimension's failures are not classified either way.
#
# A floor asked once and failed once looks exactly like a systematic failure and exactly
# like a stochastic one. Calling it systematic would send the next session to rebuild an
# architecture on a sample of one; calling it stochastic would tell it to retry forever. It
# is neither: it is unclassified, and the answer is to ask it again.
MIN_ASKS_FOR_A_CLASSIFICATION = 2


class ReliabilityRefused(ValueError):
    """A reliability claim made from a sample that cannot support one."""


def assess(galleries: list[dict]) -> dict:
    """Measure the pipeline from completed gallery attempts. Never renders anything.

    `galleries` is a list of records, one per gallery the pipeline tried to produce, each
    holding the attempts it took: `{"slug", "attempts": [sequence records...]}`. An attempt
    carries `floors` (the verdicts it was given), `usable_as_listing_asset` and
    `spent_cad`.
    """
    if not galleries:
        return {"measured": False,
                "why": "no gallery has been attempted, so there is nothing to measure"}

    usable, attempts_used, spend = [], [], []
    exhausted, over_budget = [], []
    asked: dict[str, int] = {}
    failed: dict[str, int] = {}
    correctness_breaches = []

    for gallery in galleries:
        slug = gallery.get("slug")
        tries = list(gallery.get("attempts") or [])
        attempts_used.append(len(tries))
        spend.append(round(sum(float(t.get("spent_cad") or 0.0) for t in tries), 4))
        won = next((t for t in tries if t.get("usable_as_listing_asset")), None)
        if won:
            usable.append(slug)
        else:
            exhausted.append(slug)
        if len(tries) > MAX_ATTEMPTS_PER_GALLERY:
            over_budget.append(slug)

        for attempt in tries:
            floors = dict(attempt.get("floors") or {})
            for name, verdict in floors.items():
                asked[name] = asked.get(name, 0) + 1
                if verdict != "pass":
                    failed[name] = failed.get(name, 0) + 1
            # The absolute standard, checked on every attempt rather than on the winners:
            # an asset marked usable while any floor did not say `pass`.
            if attempt.get("usable_as_listing_asset") and any(
                    v != "pass" for v in floors.values()):
                correctness_breaches.append({
                    "slug": attempt.get("slug") or slug,
                    "floors": {k: v for k, v in floors.items() if v != "pass"}})

    total_spend = round(sum(spend), 4)
    per_usable = round(total_spend / len(usable), 4) if usable else None
    enough = len(galleries) >= MIN_GALLERIES_FOR_A_RATE

    systematic, stochastic, unclassified = [], [], []
    for name, n in failed.items():
        times_asked = asked.get(name, 0)
        if n < times_asked:
            stochastic.append(name)
        elif times_asked >= MIN_ASKS_FOR_A_CLASSIFICATION:
            systematic.append(name)
        else:
            unclassified.append(name)
    systematic, stochastic, unclassified = (
        sorted(systematic), sorted(stochastic), sorted(unclassified))

    affordable = per_usable is not None and per_usable <= MAX_CAD_PER_USABLE_GALLERY
    meets_economics = bool(usable and affordable and not exhausted and not over_budget)

    return {
        "measured": True,
        "standard_set_at": STANDARD_SET_AT,
        "galleries_attempted": len(galleries),
        "galleries_usable": len(usable),
        "usable_slugs": sorted(s for s in usable if s),
        "exhausted_without_usable": sorted(s for s in exhausted if s),
        "over_attempt_budget": sorted(s for s in over_budget if s),
        "attempts_per_gallery": attempts_used,
        "max_attempts_allowed": MAX_ATTEMPTS_PER_GALLERY,
        "total_spend_cad": total_spend,
        "cad_per_usable_gallery": per_usable,
        "ceiling_cad_per_usable_gallery": MAX_CAD_PER_USABLE_GALLERY,
        "affordable": affordable,
        "dimensions_asked": dict(sorted(asked.items())),
        "failed_dimensions": dict(sorted(failed.items())),
        "systematic_failures": systematic,
        "stochastic_failures": stochastic,
        "unclassified_failures": unclassified,
        "correctness_breaches": correctness_breaches,
        "correctness_holds": not correctness_breaches,
        "meets_economics": meets_economics,
        # A rate, only when the sample can carry one.
        "success_rate": (round(len(usable) / len(galleries), 3) if enough else None),
        "rate_withheld_because": ("" if enough else
                                  f"{len(galleries)} galleries is below the floor of "
                                  f"{MIN_GALLERIES_FOR_A_RATE}. A proportion from this "
                                  f"many is not a capability measurement"),
        "verdict": _verdict(correctness_breaches, systematic, enough,
                            exhausted or over_budget, affordable),
        "what_to_do": _what_to_do(correctness_breaches, systematic, stochastic,
                                  unclassified, exhausted, over_budget, affordable,
                                  per_usable),
    }


def _verdict(breaches, systematic, enough, unreliable, affordable) -> str:
    if breaches:
        return "unsafe"
    if systematic:
        return "architecturally blocked"
    if not enough:
        return "unproven"
    if unreliable:
        return "unreliable"
    return "production capable" if affordable else "uneconomic"


def _what_to_do(breaches, systematic, stochastic, unclassified, exhausted, over_budget,
                affordable, per_usable) -> str:
    if breaches:
        return ("an asset was marked usable with a floor that did not pass. This is the "
                "one failure that reaches a customer, and it blocks launch whatever the "
                "rate says")
    if systematic:
        return (f"{systematic} failed every time they were asked, so retrying cannot fix "
                f"them. That is an architecture problem: the pipeline is not asking the "
                f"generator for something it can produce, or is checking it against the "
                f"wrong reference")
    if exhausted or over_budget:
        return (f"{sorted(s for s in exhausted + over_budget if s)} did not reach a usable "
                f"asset inside {MAX_ATTEMPTS_PER_GALLERY} attempts. Those products cannot "
                f"be listed, which is a reliability failure rather than a cost one")
    if not affordable:
        return (f"a usable gallery costs CA${per_usable} against a ceiling of "
                f"CA${MAX_CAD_PER_USABLE_GALLERY}. The pipeline works and cannot be "
                f"afforded, so the method has to get cheaper rather than the budget larger")
    tail = ""
    if unclassified:
        tail = (f". {unclassified} failed every time asked but were asked fewer than "
                f"{MIN_ASKS_FOR_A_CLASSIFICATION} times, so ask them again before "
                f"concluding anything about them")
    if stochastic:
        return ("bad generations are rejected, retrying fixes the ones that fail and a "
                "usable gallery is reached inside its budget, which is what production "
                "capability means here" + tail)
    return ("bad generations are rejected and a usable gallery is reached inside its "
            "budget, which is what production capability means here" + tail)


def measure(db, *, limit: int = 200) -> dict:
    """The standard applied to what this system has actually rendered.

    Reads the filed sequence records -- one row per attempt -- and groups them into
    galleries by product and release, because "how many attempts did this gallery take" is
    the question the standard is written in and a flat list of renders cannot answer it.

    Only the current `METHOD_VERSION` is counted, which `_frames` already enforces. That is
    deliberate: a rate that mixes v8, v10 and v12 measures a history rather than a
    pipeline, and every one of those method versions failed differently. When the method
    changes the measurement starts again, which is the honest thing for it to do.
    """
    from ..publish import model_photography

    galleries: dict[tuple, dict] = {}
    # `_frames` returns newest first; a gallery's attempts read better oldest first.
    for record in reversed(model_photography.sequences(db, limit=limit)):
        key = (record.get("slug"), record.get("version"))
        gallery = galleries.setdefault(key, {"slug": record.get("slug"),
                                             "version": record.get("version"),
                                             "attempts": []})
        gallery["attempts"].append(record)

    out = assess(list(galleries.values()))
    out["method_version"] = model_photography.METHOD_VERSION
    out["counts_only_the_current_method"] = (
        "a rate mixing method versions measures a history rather than a pipeline. When "
        "the method changes this measurement starts again")
    return out
