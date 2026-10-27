"""Visual gallery as validation (F-769) -- W4-C14.

"Finished-object gallery/reference imagery is useful as independent evidence that instructions
produce plausible finished results, but it does not override written Product Truth or replace
physical testing."

`weigh` combines three things and keeps them apart:

* Product Truth -- the deterministic validation verdict (PASS / FAIL / None = UNKNOWN). It is
  the verdict. Nothing here changes it.
* the physical test -- PASS / FAIL / NOT_RUN / None. A gallery never marks it satisfied.
* gallery images -- each `{ref, source, version, plausible}`, `plausible` being a recorded
  judgement (True / False / None = not judged) that the finished object matches what the
  instructions say it makes.

The gallery's contribution is bounded (`GALLERY_WEIGHT_CAP` of the confidence) and only ever
corroborates a PASS. It CORROBORATES with `MIN_PLAUSIBLE` plausible images from at least two
independent sources (our own studio photograph and a tester's, say) of the version being
judged. A single implausible image CONTRADICTS: it opens a review of the pattern, and the
Product Truth verdict still stands until the compiler or a physical test says otherwise.
Images of another version are set aside, not counted.
"""
from __future__ import annotations

UNKNOWN = "UNKNOWN"
GALLERY_WEIGHT_CAP = 0.2
TRUTH_WEIGHT = 0.6
TEST_WEIGHT = 0.2
MIN_PLAUSIBLE = 2
SOURCES = ("studio", "tester", "customer")


def gallery_support(images, *, version: str) -> dict:
    current = [i for i in images or () if i.get("version") == version]
    other = [i.get("ref") for i in images or () if i.get("version") != version]
    implausible = [i.get("ref") for i in current if i.get("plausible") is False]
    plausible = [i for i in current if i.get("plausible") is True]
    sources = sorted({i.get("source") for i in plausible if i.get("source") in SOURCES})
    if implausible:
        state = "CONTRADICTS"
    elif len(plausible) >= MIN_PLAUSIBLE and len(sources) >= 2:
        state = "CORROBORATES"
    elif current:
        state = "INSUFFICIENT"
    else:
        state = UNKNOWN
    return {"state": state, "plausible": [i.get("ref") for i in plausible],
            "implausible": implausible, "independent_sources": sources,
            "unjudged": [i.get("ref") for i in current if i.get("plausible") is None],
            "other_version": other}


def weigh(*, product_truth: str | None, physical_test: str | None, images, version: str) -> dict:
    g = gallery_support(images, version=version)
    review = bool(g["implausible"])
    test_satisfied = physical_test == "PASS"
    if product_truth is None:
        confidence, why = None, ("Product Truth has no verdict, so there is nothing for the "
                                 "gallery to corroborate; it is reported only")
    elif product_truth != "PASS":
        confidence, why = 0.0, ("Product Truth is not PASS; a gallery cannot override written "
                                "Product Truth")
    else:
        confidence = TRUTH_WEIGHT
        if test_satisfied:
            confidence += TEST_WEIGHT
        if g["state"] == "CORROBORATES":
            confidence += GALLERY_WEIGHT_CAP
        confidence = round(min(confidence, 1.0), 3)
        why = ("Product Truth PASS" + (", physical test PASS" if test_satisfied else
                                       ", physical test outstanding")
               + (", gallery corroborates" if g["state"] == "CORROBORATES" else ""))
    return {"verdict": product_truth or UNKNOWN,
            "physical_test": physical_test or UNKNOWN,
            "physical_test_satisfied": test_satisfied,
            "physical_test_outstanding": not test_satisfied,
            "gallery": g, "confidence": confidence, "review_required": review,
            "why": why + ("; an implausible finished image opens a pattern review" if review
                          else ""),
            "rule": "the gallery is bounded evidence: it never sets the verdict and never "
                    "stands in for a physical test"}
