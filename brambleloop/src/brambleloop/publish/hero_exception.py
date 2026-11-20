"""Hero collage / text restraint, with its measured-evidence exception (F-028).

The rule (`publish.listing_assets.check_frame_plan`): the first image is the finished result,
not an infographic, collage or text card. The requirement allows one exception -- "unless
measured evidence justifies" it -- and this module is the only door through which it enters.

The evidence must be a remembered listing-test result (`commerce.listing_tests`, the durable
`ListingMemory` table) that:

- tested the first image itself (`idea` "hero_image" or "thumbnail"),
- tested a text/collage treatment, declared in the test key (`hero-text:` / `hero-collage:`),
- was SUPPORTED -- the treatment won -- on at least `listing_tests.MIN_EXPOSURE` impressions,
- and was written to memory, which `listing_tests.read` allows only for an unconfounded,
  readable test.

An owner preference, a competitor's hero or a designer's taste is not measured evidence and
has no path here. No such memory exists today, so the rule binds every listing.
"""
from __future__ import annotations

HERO_IDEAS = ("hero_image", "thumbnail")
TREATMENT_PREFIXES = ("hero-text:", "hero-collage:")
# The findings the exception may lift. A concept hero, a flat render or a hero that dies at
# thumbnail scale are truth and legibility failures, and no test result excuses them.
EXCEPTABLE = ("LISTING_HERO_IS_AN_INFOGRAPHIC",)


def measured_exception(db, *, context: str | None = None) -> dict | None:
    """The remembered result that licenses a text/collage hero, or None."""
    from sqlalchemy import select

    from ..commerce import listing_tests as lt
    from ..core.models import ListingMemory

    try:
        rows = list(db.scalars(select(ListingMemory)))
    except AttributeError:
        with db.session() as s:
            rows = list(s.scalars(select(ListingMemory)))
    for r in sorted(rows, key=lambda r: r.on, reverse=True):
        if (r.idea in HERO_IDEAS and r.outcome == lt.SUPPORTED
                and str(r.test_key).startswith(TREATMENT_PREFIXES)
                and int(r.exposure or 0) >= lt.MIN_EXPOSURE
                and (context is None or r.context == context)):
            return {"test_key": r.test_key, "idea": r.idea, "outcome": r.outcome,
                    "exposure": int(r.exposure), "context": r.context,
                    "on": r.on.date().isoformat() if hasattr(r.on, "date") else str(r.on),
                    "basis": "commerce.listing_tests memory (F-028 measured exception)"}
    return None


def apply(problems: list[str], exception: dict | None) -> dict:
    """Split frame-plan problems into what still blocks and what the evidence excuses."""
    if not exception:
        return {"blocking": list(problems), "excepted": [], "exception": None}
    excepted = [p for p in problems if p.startswith(EXCEPTABLE)]
    return {"blocking": [p for p in problems if p not in excepted], "excepted": excepted,
            "exception": exception}
