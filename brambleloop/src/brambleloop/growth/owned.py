"""An audience this company owns, and the law that governs writing to it.

Requirement 20. Every flagship should have an owned acquisition counterpart -- an article or
tutorial, a pin cluster, video where useful, and a **consented** email path -- with assisted
conversions tracked and long-term dependence on one marketplace falling.

The email half is not a feature. Canada's Anti-Spam Legislation governs every commercial
electronic message this company will ever send, and `growth/content.py` already carried the
right sentence -- *express consent required before this is ever sent* -- in a detail
dictionary, where it is a comment. A comment does not stop a send. So the rules are here, as
code that refuses.

**Consent has a basis, a date, and sometimes an expiry.** Express consent lasts until it is
withdrawn. Implied consent does not: it runs two years from a purchase and six months from an
enquiry, and then it is gone whether or not anybody noticed. A list that quietly keeps sending
past those dates is the ordinary way a small sender ends up non-compliant, because nothing
about the address changes on the day it expires.

**Every message identifies its sender and can be unsubscribed from.** Both are conditions of
sending rather than good manners, and a message missing either is refused here rather than
reviewed later.

**This is a screen, not clearance.** The same wording `culture/rights.py` uses, for the same
reason: encoding the rules a careful sender follows is not the same as legal advice, and a
module that implied otherwise would be worse than one that says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

EXPRESS, IMPLIED_PURCHASE, IMPLIED_ENQUIRY = "express", "implied_purchase", "implied_enquiry"
# CASL s.10(9)(b): an address the recipient conspicuously published in their business
# capacity, without a statement refusing unsolicited messages, and the message is relevant to
# that capacity. This is the basis creator outreach travels on (#9), and both of its
# conditions are facts about the recipient rather than about our list -- `growth.creators`
# checks them, because that is where those facts are recorded.
IMPLIED_PUBLISHED = "implied_published"

BASES: dict[str, str] = {
    EXPRESS: "the recipient actively asked to receive messages, and said so",
    IMPLIED_PURCHASE: "an existing business relationship: they bought something",
    IMPLIED_ENQUIRY: "they asked this company a question and gave an address to answer it",
    IMPLIED_PUBLISHED: ("they conspicuously published this address in their business "
                        "capacity without refusing unsolicited messages, and the message is "
                        "relevant to that capacity"),
}

# CASL's own clocks. Express consent has none; the other two do, and they run from the event
# rather than from the last send -- a list that keeps mailing does not keep the consent alive.
IMPLIED_LIFETIME_DAYS: dict[str, int] = {
    IMPLIED_PURCHASE: 730,   # two years from the transaction
    IMPLIED_ENQUIRY: 180,    # six months from the enquiry
}

# An unsubscribe mechanism has to keep working after the message is sent, and has to be
# actioned promptly. Both are conditions of sending.
UNSUBSCRIBE_VALID_DAYS = 60
UNSUBSCRIBE_ACTIONED_WITHIN_BUSINESS_DAYS = 10

# What every commercial electronic message must carry. Checked on the message rather than
# promised in a policy, because the policy is not what arrives in somebody's inbox.
REQUIRED_IN_EVERY_MESSAGE: tuple[str, ...] = (
    "sender_name", "mailing_address", "contact", "unsubscribe_url")

# The owned channels a flagship is supposed to have a counterpart in.
OWNED_CHANNELS: tuple[str, ...] = ("article", "pins", "email", "teaser")


class ConsentRefused(ValueError):
    """A send that CASL does not permit, refused before it becomes one."""


@dataclass(frozen=True)
class Consent:
    """One recipient's basis for being written to, and when it started."""

    address_ref: str          # a reference, never the address itself
    basis: str
    obtained_on: date
    source: str               # where the basis came from, so somebody can check it
    withdrawn_on: date | None = None

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise ConsentRefused(
                f"{self.basis!r} is not a consent basis: {sorted(BASES)}. A send with no "
                f"named basis is a send with no basis")
        if not self.source.strip():
            raise ConsentRefused(
                "a consent with no recorded source cannot be checked by anybody later, "
                "which is the only thing that makes it a record rather than an assertion")

    def expires_on(self) -> date | None:
        days = IMPLIED_LIFETIME_DAYS.get(self.basis)
        return None if days is None else self.obtained_on + timedelta(days=days)


def may_send(consent: Consent, today: date | None = None) -> dict:
    """Whether this company may write to this person today, and why.

    The expiry is the part that catches people out. Nothing about an address changes on the
    day implied consent runs out, so a list that is not checking simply carries on -- which
    is the ordinary route to a non-compliant send by a sender who believed they were careful.
    """
    today = today or date.today()
    expires = consent.expires_on()

    if consent.withdrawn_on is not None and consent.withdrawn_on <= today:
        return {"may_send": False, "basis": consent.basis,
                "why": (f"consent was withdrawn on {consent.withdrawn_on.isoformat()}. "
                        f"Withdrawal is final and does not need a reason")}
    if expires is not None and today >= expires:
        return {"may_send": False, "basis": consent.basis, "expired_on": expires.isoformat(),
                "why": (f"implied consent from {consent.obtained_on.isoformat()} ran out on "
                        f"{expires.isoformat()}. Implied consent expires on its own, and a "
                        f"list that keeps sending does not keep it alive")}
    return {
        "may_send": True, "basis": consent.basis, "means": BASES[consent.basis],
        "expires_on": expires.isoformat() if expires else None,
        "why": (("express consent lasts until it is withdrawn"
                 if consent.basis == EXPRESS else
                 "this basis has no clock of its own: it lasts while its conditions hold, "
                 "and stops the day they do not")
                if expires is None else
                f"valid until {expires.isoformat()}, then gone unless it is renewed by a "
                f"fresh transaction or a fresh request"),
    }


def check_message(message: dict) -> list[str]:
    """What is missing from a message before it may be sent. Empty means nothing is.

    Identification and unsubscribe are conditions of sending rather than good manners, so a
    message missing either is refused here rather than reviewed after it has arrived in
    somebody's inbox.
    """
    problems = []
    for field in REQUIRED_IN_EVERY_MESSAGE:
        if not str(message.get(field) or "").strip():
            problems.append(
                f"no {field}: every commercial electronic message must carry it, and this "
                f"one would arrive without it")
    return problems


def send_gate(consent: Consent, message: dict, today: date | None = None) -> dict:
    """The two halves together: may we write to this person, and is this message sendable."""
    permission = may_send(consent, today)
    missing = check_message(message)
    return {
        "sendable": permission["may_send"] and not missing,
        "consent": permission,
        "missing_from_message": missing,
        "unsubscribe_must_work_for_days": UNSUBSCRIBE_VALID_DAYS,
        "unsubscribe_actioned_within_business_days":
            UNSUBSCRIBE_ACTIONED_WITHIN_BUSINESS_DAYS,
        "screen_not_clearance": (
            "these are the rules a careful sender follows, encoded so a send cannot skip "
            "them. Passing this screen is not legal advice and is not clearance"),
    }


def counterparts(db) -> dict:
    """Which certified products have an owned acquisition counterpart, and which do not.

    The requirement says *every* flagship should have one. A report that lists what exists is
    an inventory; the useful half is the list of products that have none, because that is the
    work.
    """
    from sqlalchemy import select

    from ..core.models import ContentPiece, PatternVersion, Product

    with db.session() as s:
        products = list(s.scalars(select(Product)))
        certified = {
            v.product_id for v in s.scalars(select(PatternVersion))
            if v.certified}
        pieces = [(p.product_slug, p.channel) for p in s.scalars(select(ContentPiece))]

    by_slug: dict[str, set] = {}
    for slug, channel in pieces:
        by_slug.setdefault(slug, set()).add(channel)

    flagships = [p for p in products if p.id in certified]
    rows = []
    for product in flagships:
        have = by_slug.get(product.slug, set())
        missing = [c for c in OWNED_CHANNELS if c not in have]
        rows.append({"slug": product.slug, "has": sorted(have & set(OWNED_CHANNELS)),
                     "missing": missing, "covered": not missing})

    uncovered = [r["slug"] for r in rows if not r["covered"]]
    return {
        "measurable": bool(flagships),
        "flagships": len(flagships),
        "covered": sum(1 for r in rows if r["covered"]),
        "without_a_full_counterpart": uncovered,
        "products": rows,
        "channels": list(OWNED_CHANNELS),
        "why": (f"{len(uncovered)} of {len(flagships)} certified products lack at least one "
                f"owned channel. Every visit that arrives through the marketplace instead is "
                f"a visit rented rather than owned"
                if flagships else
                "no certified product exists yet, so there is nothing to have a counterpart "
                "for. An empty coverage report is not full coverage"),
    }


def owned_share(db) -> dict:
    """How much business arrives through something this company owns (#20).

    Read from orders by channel (`finance.channel_comparison.channel_of`): owned = the owned
    direct channel (site, email, search to our own pages) plus social posts we published.
    It previously read `Cohort.arm == "organic"`, which is the *unpaid Etsy* arm of a launch
    cohort -- marketplace traffic, the very dependence #20 asks to reduce -- so it would have
    reported Etsy search as "owned". Reported unmeasurable with the reason rather than as
    zero when there are no orders.
    """
    from sqlalchemy import select

    from ..core.models import Order
    from ..finance.channel_comparison import channel_of

    with db.session() as s:
        channels = [channel_of(o.acquisition_source) for o in s.scalars(select(Order))]
    if not channels:
        return {"measurable": False,
                "reason": ("no order has been recorded, so the share arriving through owned "
                           "channels is unknown. A company with no traffic has no "
                           "marketplace dependence either, and that is not the same finding"),
                "feeds": "the traffic_source axis of the anti-fragility rule (#29)"}
    owned = sum(1 for c in channels if c in OWNED_ORDER_CHANNELS)
    known = sum(1 for c in channels if c != "unattributed")
    return {"measurable": True, "orders": len(channels), "owned_orders": owned,
            "unattributed_orders": len(channels) - known,
            "owned_share": round(owned / len(channels), 3),
            "marketplace_share": round(sum(1 for c in channels if c in (
                "organic_search", "etsy_ads", "offsite_ads", "share_and_save"))
                / len(channels), 3),
            "basis": "orders by acquisition channel; unattributed orders count as not owned",
            "feeds": "the traffic_source axis of the anti-fragility rule (#29)"}


OWNED_ORDER_CHANNELS: tuple[str, ...] = ("owned_direct", "social")


def assisted_conversions(db) -> dict:
    """#20: orders the owned channels produced directly, and marketplace orders they assisted.

    Direct: an order credited to an owned channel. Assisted: a marketplace-credited order from
    a customer whose *earlier* order came through an owned channel -- the owned audience
    brought them back through Etsy. Per product, plus the launch-cohort `assisted` counts
    where a cohort recorded them. Unmeasurable (never zero) with no orders.
    """
    from sqlalchemy import select

    from ..core.models import Cohort, Order
    from ..finance.channel_comparison import channel_of

    with db.session() as s:
        orders = sorted(((o.customer_id, o.at, o.product_slug, channel_of(o.acquisition_source))
                         for o in s.scalars(select(Order))), key=lambda t: (t[0], t[1]))
        cohort_assisted = {}
        for c in s.scalars(select(Cohort)):
            cohort_assisted[c.product_slug] = cohort_assisted.get(c.product_slug, 0) + int(
                c.assisted or 0)
    if not orders:
        return {"measurable": False, "reason": "no order has been recorded",
                "cohort_assisted": cohort_assisted}
    per: dict[str, dict] = {}
    seen_owned: set = set()
    for cust, _at, slug, ch in orders:
        row = per.setdefault(slug, {"orders": 0, "direct": 0, "assisted": 0})
        row["orders"] += 1
        if ch in OWNED_ORDER_CHANNELS:
            row["direct"] += 1
            seen_owned.add(cust)
        elif cust in seen_owned:
            row["assisted"] += 1
    total = {k: sum(r[k] for r in per.values()) for k in ("orders", "direct", "assisted")}
    return {"measurable": True, "by_product": per, "total": total,
            "cohort_assisted": cohort_assisted,
            "rule": ("assisted = a marketplace order from a customer whose earlier order came "
                     "through an owned channel; one credit per order, never two")}