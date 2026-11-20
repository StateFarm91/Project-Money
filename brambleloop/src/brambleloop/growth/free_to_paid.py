"""Free work with a commercial job, and a ladder that cannot count a rung nobody reached.

Requirement 10. The useful free motif, the mini pattern, the tutorial and the little tool are
how a shop with no audience demonstrates that its patterns are worth paying for -- and the
requirement adds the condition that makes them work rather than merely cost: *free content
must have a commercial job*. Not a hope that it helps. A named premium product it leads to,
and a stated reason somebody who just used it would want that product next.

An asset without both is a giveaway with a marketing story attached, and it is a pleasant
thing to make, which is why a company produces dozens of them and cannot say what any of
them did.

**The second refusal is the one that costs money.** A free mini pattern that gives away the
paid pattern's object does not lead to it; it replaces it. That failure looks identical to
success from inside -- downloads, comments, saves -- and the shop wonders why its conversion
is falling while its traffic rises. So a free asset may not be a complete pattern for
something this company sells, and the check is against the catalogue rather than against
somebody's judgement of how much was given away.

**The ladder is visitor, consented email, first purchase, repeat purchase, collection
purchase**, and two rules keep it honest.

A rung nobody reached is absent, not zero. A conversion rate computed from an upstream of
zero is not a bad rate; there is no rate, and reporting 0% makes an untried funnel look like
a failed one -- which is how the thing that was never tried gets abandoned.

And an email is a rung only once it is consented. An address captured without a CASL basis is
not a step toward a purchase, it is a liability with a growth metric attached, so the count
comes from the consent records through `growth.owned` rather than from whatever the form
collected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import owned

# The four kinds the requirement names. Closed, because "content" is not a kind and cannot be
# given a commercial job.
FREE_KINDS: dict[str, str] = {
    "motif": "one repeatable unit -- a square, a flower, an edging -- complete in itself",
    "mini_pattern": "a small finished object, whole and honest, that is not something we sell",
    "tutorial": "one technique taught properly, in the terms our patterns use",
    "tool": "a calculator or chart that is useful whether or not anything is bought",
}

# Where free work is placed. Both are owned surfaces: the requirement is about the funnels
# this company controls rather than about renting attention.
SURFACES: tuple[str, ...] = ("article", "pins")

# The ladder, in order. Each rung is a different person's decision, which is why the drop
# between them is the interesting number rather than the total.
STAGES: tuple[str, ...] = (
    "visitor", "consented_email", "first_purchase", "repeat_purchase", "collection_purchase")


class FunnelRefused(ValueError):
    """A free asset with no commercial job, or a count that cannot be true."""


@dataclass(frozen=True)
class FreeAsset:
    """One piece of free work, and the job it is doing."""

    key: str
    kind: str
    surface: str
    teaches: str
    # The premium product this leads to, and why somebody who just used this wants it.
    leads_to: str = ""
    why_next: str = ""
    # When the free thing is itself a pattern, the object it makes. Named so the catalogue
    # check has something to compare, rather than a judgement about how much was given away.
    makes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in FREE_KINDS:
            raise FunnelRefused(f"{self.kind!r} is not a kind of free work: "
                                f"{sorted(FREE_KINDS)}. 'Content' is not a kind, and a kind "
                                f"nobody can name is a kind nobody can give a job to")
        if self.surface not in SURFACES:
            raise FunnelRefused(f"{self.surface!r} is not an owned surface: {list(SURFACES)}")


def check_asset(asset: FreeAsset, *, paid_slugs: tuple[str, ...] = ()) -> dict:
    """Whether this free work has a commercial job, and whether it does the paid work's."""
    reasons: list[str] = []

    if not asset.leads_to.strip():
        reasons.append(
            "no premium product named. Free work with no next step is a giveaway with a "
            "marketing story attached, and it is pleasant to make, which is why a shop ends "
            "up with dozens and cannot say what any of them did")
    if len(asset.why_next.split()) < 5:
        reasons.append(
            "no stated reason somebody who just used this would want that product. 'It "
            "leads to the collection' is a hope; the reason is the job")
    if not asset.teaches.strip():
        reasons.append("nothing stated that it teaches or gives, which is what makes it "
                       "worth finding at all")

    if asset.makes and asset.makes in paid_slugs:
        reasons.append(
            f"{asset.makes!r} is something this company sells. A free pattern for a paid "
            f"object does not lead to it, it replaces it -- and that failure looks exactly "
            f"like success from the inside, because the downloads go up")
    if asset.leads_to and asset.makes and asset.leads_to == asset.makes:
        reasons.append(
            "this leads to the object it already gives away, which is not a funnel")

    return {
        "key": asset.key, "ok": not reasons, "reasons": reasons,
        "kind": asset.kind, "surface": asset.surface,
        "job": ({"leads_to": asset.leads_to, "why_next": asset.why_next}
                if not reasons else None),
    }


def count_consented(consents: list[owned.Consent], today: date | None = None) -> dict:
    """How many addresses are a rung, which is fewer than how many were captured.

    An address with no valid basis is not a step toward a purchase; it is a liability with a
    growth metric attached, so it is excluded and counted separately rather than quietly
    dropped.
    """
    today = today or date.today()
    allowed, refused = [], []
    for consent in consents:
        (allowed if owned.may_send(consent, today)["may_send"] else refused).append(consent)
    return {
        "consented": len(allowed), "captured": len(consents),
        "not_a_rung": len(refused),
        "why": ("an address captured without a valid basis is not a funnel step. Counting it "
                "as one is how a list grows and a send becomes non-compliant on the same "
                "day"),
    }


def funnel(counts: dict[str, int | None]) -> dict:
    """The ladder, with the drop between each rung -- and silence where nobody reached one.

    A rate computed from an upstream of zero is not a bad rate. There is no rate, and
    reporting 0% makes an untried funnel look like a failed one, which is how something
    nobody tried gets abandoned as something that did not work.
    """
    unknown = sorted(set(counts) - set(STAGES))
    if unknown:
        raise FunnelRefused(f"{unknown} are not stages: {list(STAGES)}")

    rungs = []
    for name in STAGES:
        rungs.append({"stage": name, "count": counts.get(name)})

    # A rung cannot exceed the one above it. This is a counting bug rather than a bad funnel,
    # and it is worth catching because the ratio it produces looks merely surprising.
    for above, below in zip(rungs, rungs[1:]):
        a, b = above["count"], below["count"]
        if a is not None and b is not None and b > a:
            raise FunnelRefused(
                f"{below['stage']} ({b}) is larger than {above['stage']} ({a}). Nobody "
                f"reaches a rung without the one above it, so this is a counting fault and "
                f"not a remarkable funnel")

    steps = []
    for above, below in zip(rungs, rungs[1:]):
        a, b = above["count"], below["count"]
        if a is None or b is None:
            rate, why = None, f"{'upstream' if a is None else 'downstream'} count unmeasured"
        elif a == 0:
            rate, why = None, (f"nobody reached {above['stage']}, so there is no conversion "
                               f"to {below['stage']}. Absent is not zero: a rate of 0% makes "
                               f"an untried funnel look like a failed one")
        else:
            rate, why = round(b / a, 5), ""
        steps.append({"from": above["stage"], "to": below["stage"], "rate": rate,
                      "why": why})

    measured = [s for s in steps if s["rate"] is not None]
    return {
        "rungs": rungs, "steps": steps,
        "measured_steps": len(measured), "of": len(steps),
        "weakest": (min(measured, key=lambda s: s["rate"])["from"] if measured else None),
        "note": ("no step in this funnel has been measured. That is an unbuilt funnel, not a "
                 "failing one, and the difference is the whole of what to do next"
                 if not measured else ""),
    }


def plan(assets: list[FreeAsset], *, paid_slugs: tuple[str, ...] = ()) -> dict:
    """Every free asset, whether it has a job, and which premium products nothing feeds."""
    checked = [check_asset(a, paid_slugs=paid_slugs) for a in assets]
    working = [c for c in checked if c["ok"]]
    fed = {c["job"]["leads_to"] for c in working}
    return {
        "assets": checked,
        "with_a_job": len(working), "of": len(checked),
        "premium_products_fed": sorted(fed),
        "premium_products_with_nothing_feeding_them": sorted(set(paid_slugs) - fed),
        "note": ("no free work exists yet, so nothing feeds anything. An empty funnel is an "
                 "empty funnel and not a funnel that is not working"
                 if not assets else ""),
    }


def state() -> dict:
    """What free work must carry, and the ladder it is supposed to move people up."""
    return {
        "kinds": dict(FREE_KINDS),
        "surfaces": list(SURFACES),
        "stages": list(STAGES),
        "every_asset_must_name": ["leads_to", "why_next", "teaches"],
        "note": ("Free work has a commercial job or it is a giveaway with a marketing story "
                 "attached. A free pattern for something this company sells does not lead to "
                 "it, it replaces it -- and that failure looks exactly like success from the "
                 "inside. An email is a rung only once it is consented, and a rung nobody "
                 "reached is absent rather than zero (#10)."),
    }
