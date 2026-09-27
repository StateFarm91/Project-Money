"""The trust sprint, and the four fifths of it that happen before the first customer.

Requirement 259. During the first hundred customers, prioritise flawless downloads, rapid
support, truthful expectations, defect prevention and post-purchase clarity -- without
sacrificing contribution irrationally -- because early trust compounds.

Reading it as written produces a plan that starts on the day of the first sale, and that is
the wrong day for four of the five. A flawless download is a property of the delivery path,
and the first buyer either gets the file or does not; there is no version of "we will make
downloads flawless during the first hundred" that helps customer one. Truthful expectations
are written into a listing before anybody reads it. Defect prevention is the release chain,
which runs before a product exists to sell. Post-purchase clarity is a page and a file that
are either written or not.

Only rapid support genuinely needs customers, because it is a response time and there is
nothing to respond to yet. So the sprint's honest shape is: four priorities that are *ready
or not ready today*, checkable now, and one that starts when the first buyer does.

That matters because the alternative is comfortable. A plan that begins at the first sale
lets every one of these sit unfinished while the shop feels prepared, and the first hundred
customers are the ones whose experience compounds hardest -- they are the review base, the
repeat base and the proof base, and each of them arrives exactly once.

**A sprint ends.** Saying so is not pedantry: a permanent sprint is just how the company
works, and calling it a sprint is how nobody asks when the extra cost stops. This one ends at
a hundred customers, and what it buys afterwards is the ordinary standard.

**What it may spend is time and prevention, never price.** "Do not sacrifice contribution
irrationally" has a specific reading here: a discount during the trust sprint teaches the
hundred buyers whose repeat behaviour matters most that the price is negotiable, and they are
precisely the cohort a value ladder depends on. The sprint may cost support hours, sample
costs and slower shipping of new products. It may not cost the price.
"""
from __future__ import annotations

from dataclasses import dataclass

from .buyer_trust import REQUIRED_DISCLOSURES

BEFORE = "before_the_first_customer"
DURING = "during_the_first_hundred"

# The five the requirement names, when each is actually done, and what makes it true.
PRIORITIES: dict[str, dict] = {
    "flawless_downloads": {
        "when": BEFORE,
        "what": "the file arrives, opens, and is the right version",
        "ready_when": ("the delivery path has been exercised end to end and the file a buyer "
                       "receives is the one the certificate covers"),
        "why_not_later": ("the first buyer either gets the file or does not, and there is no "
                          "version of improving this during the first hundred that helps "
                          "customer one"),
    },
    "truthful_expectations": {
        "when": BEFORE,
        "what": "every disclosure a purchase needs, where it is actually read",
        "ready_when": f"all of {sorted(REQUIRED_DISCLOSURES)} are present on their surfaces",
        "why_not_later": "a listing is written before anybody reads it",
    },
    "defect_prevention": {
        "when": BEFORE,
        "what": "the release chain, run in full, on everything that is sold",
        "ready_when": "every listed product carries a certificate from the current chain",
        "why_not_later": "prevention that begins after the first sale is not prevention",
    },
    "post_purchase_clarity": {
        "when": BEFORE,
        "what": "what to do next, how to ask, and from which version the answer comes",
        "ready_when": "the file and the listing both say how to get help",
        "why_not_later": "it is a page and a file, either written or not",
    },
    "rapid_support": {
        "when": DURING,
        "what": "a fast, human answer to the question a buyer actually asked",
        "ready_when": "a measured response time over real cases",
        "why_not_later": ("this one genuinely needs customers: it is a response time, and "
                          "there is nothing to respond to yet"),
    },
}

# The sprint ends. A permanent sprint is how the company works, and calling it a sprint is
# how nobody asks when the extra cost stops.
SPRINT_ENDS_AT_CUSTOMERS = 100

# What the sprint may spend, and the one thing it may not.
MAY_SPEND: tuple[str, ...] = ("support hours", "physical sample costs",
                              "slower release of new products")
MAY_NOT_SPEND: tuple[str, ...] = ("the price",)


class SprintRefused(ValueError):
    """A priority nobody named, or a discount dressed as a trust investment."""


@dataclass(frozen=True)
class Readiness:
    """What is actually true today about the four that do not need a customer."""

    flawless_downloads: bool = False
    truthful_expectations: bool = False
    defect_prevention: bool = False
    post_purchase_clarity: bool = False


def _listings(db) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        return [(row.product_slug, row.version) for row in s.scalars(
            select(Listing).where(Listing.state != "withdrawn"))]


def _delivery_path(db) -> tuple[bool, str, dict]:
    """flawless_downloads: a publish that attached every terminology's certified file."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..publish.pdf import TERMINOLOGIES

    with db.session() as s:
        published = [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "store.published"))]
        verified = [r.artifact for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "store.pdf_hash_verified"))]
    complete = [d for d in published
                if all((d.get("files_attached_by_terminology") or {}).get(t)
                       for t in TERMINOLOGIES)]
    evidence = {"published": len(published), "all_files_attached": len(complete),
                "hash_verified_uploads": len(verified)}
    if complete and verified:
        return True, "", evidence
    return False, ("the delivery path has never been exercised end to end: no listing has "
                   "been published with every terminology's certified file attached "
                   "(store.publish refuses in shadow and the Etsy integration is "
                   "unexercised)"), evidence


def _disclosures(db, listings) -> tuple[bool, str, dict]:
    """truthful_expectations: every listing's stored copy carries every owed disclosure."""
    from .buyer_trust import listing_disclosure_finding

    if not listings:
        return False, "no listing copy exists, so nothing has disclosed anything yet", {}
    short = []
    for slug, version in listings:
        f = listing_disclosure_finding(db, slug=slug, version=version)
        if not f.get("checked") or not f.get("complete"):
            short.append({"listing": f"{slug}@{version}",
                          "missing": [m["disclosure"] for m in f.get("missing") or []],
                          "misplaced": [m["disclosure"] for m in f.get("misplaced") or []]})
    if short:
        return False, (f"{len(short)} of {len(listings)} listings are missing or misplacing "
                       f"an owed disclosure, first {short[0]['listing']}: "
                       f"{short[0]['missing'] + short[0]['misplaced']}"), {"short": short[:5]}
    return True, "", {"listings": len(listings)}


def _defects(db, listings) -> tuple[bool, str, dict]:
    """defect_prevention: every listed release certified, and no open P0/P1."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion, Product

    if not listings:
        return False, "nothing is listed, so the release chain has run on nothing sold", {}
    with db.session() as s:
        ids = {p.id: p.slug for p in s.scalars(select(Product))}
        certified = {(ids.get(pv.product_id), pv.version) for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))}  # noqa: E712
        open_severe = [i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved == False, Incident.severity.in_(("P0", "P1"))))]  # noqa: E712
    uncertified = [f"{slug}@{v}" for slug, v in listings if (slug, v) not in certified]
    if uncertified:
        return False, (f"{len(uncertified)} listed release(s) carry no certificate, first "
                       f"{uncertified[0]}"), {"uncertified": uncertified[:5]}
    if open_severe:
        return False, (f"{len(open_severe)} open P0/P1 incident(s), first "
                       f"{open_severe[0]}"), {"open_severe": open_severe[:5]}
    return True, "", {"listings": len(listings)}


def _post_purchase(db, listings) -> tuple[bool, str, dict]:
    """post_purchase_clarity: the listing says how to get help, and the concierge answers."""
    from .buyer_trust import listing_disclosure_finding

    try:
        from ..support.concierge import version_answer  # noqa: F401
        concierge = True
    except Exception:  # noqa: BLE001 - an unimportable concierge is a blocker, not a crash
        concierge = False
    if not concierge:
        return False, "the support concierge cannot be loaded, so nobody answers", {}
    if not listings:
        return False, "no listing copy exists to tell a buyer how to ask for help", {}
    silent = [f"{slug}@{v}" for slug, v in listings
              if any(m["disclosure"] == "support" for m in
                     listing_disclosure_finding(db, slug=slug, version=v).get("missing")
                     or [{"disclosure": "support"}])]
    if silent:
        return False, (f"{len(silent)} listing(s) do not say how to ask a question, first "
                       f"{silent[0]}"), {"silent": silent[:5]}
    return True, "", {"listings": len(listings), "concierge": True}


def readiness_from_evidence(db) -> tuple[Readiness, dict[str, dict]]:
    """Read the four before-the-first-customer priorities from what is on file.

    Each priority's verdict comes with its blocker: the delivery path (publish audits that
    attached every certified file), the disclosures (`buyer_trust` on each stored listing),
    the release chain (certificates and open P0/P1 incidents, the launch-readiness rule) and
    the concierge plus the listing's support line. An empty catalogue is not ready on any of
    them, because a check that passes on nothing is the vacuous pass launch readiness
    already had to remove.
    """
    listings = _listings(db)
    checks = {
        "flawless_downloads": _delivery_path(db),
        "truthful_expectations": _disclosures(db, listings),
        "defect_prevention": _defects(db, listings),
        "post_purchase_clarity": _post_purchase(db, listings),
    }
    readiness = Readiness(**{k: v[0] for k, v in checks.items()})
    detail = {k: {"blocker": v[1], "evidence": v[2]} for k, v in checks.items()}
    return readiness, detail


def before_the_first_customer(readiness: Readiness | None = None, *, db=None) -> dict:
    """The four that are ready or not ready today, and are not waiting for anybody.

    With `db`, the verdicts are read from evidence (`readiness_from_evidence`) and every
    not-ready priority names its blocker. With a `Readiness` alone, the caller's verdicts are
    reported as given.
    """
    detail: dict[str, dict] = {}
    if db is not None:
        readiness, detail = readiness_from_evidence(db)
    if readiness is None:
        raise SprintRefused("pass either a Readiness or the database to read it from")
    rows = []
    for key, spec in PRIORITIES.items():
        if spec["when"] != BEFORE:
            continue
        ready = bool(getattr(readiness, key))
        rows.append({"priority": key, "ready": ready, "what": spec["what"],
                     "ready_when": spec["ready_when"],
                     "why_not_later": spec["why_not_later"],
                     "blocker": (None if ready else
                                 (detail.get(key, {}).get("blocker")
                                  or "reported not ready by the caller")),
                     "evidence": detail.get(key, {}).get("evidence", {})})
    outstanding = [r["priority"] for r in rows if not r["ready"]]
    return {
        "priorities": rows,
        "ready": len(rows) - len(outstanding), "of": len(rows),
        "outstanding": outstanding,
        "note": ("all four are done, and they were done before anybody bought anything, "
                 "which is the only time they can be" if not outstanding else
                 f"{outstanding} are not ready. A plan that begins at the first sale lets "
                 f"these sit unfinished while the shop feels prepared, and the first hundred "
                 f"customers each arrive exactly once"),
    }


def status(*, customers: int, readiness: Readiness,
           measured_response_hours: float | None = None) -> dict:
    """Where the sprint stands, including the honest case where it has not started."""
    if customers < 0:
        raise SprintRefused("a negative customer count is not a count")

    before = before_the_first_customer(readiness)
    started = customers > 0
    finished = customers >= SPRINT_ENDS_AT_CUSTOMERS

    support = {
        "measurable": measured_response_hours is not None,
        "measured_response_hours": measured_response_hours,
        "why": ("a response time needs something to respond to"
                if measured_response_hours is None else "measured over real cases"),
    }

    return {
        "customers": customers,
        "started": started,
        "finished": finished,
        "ends_at": SPRINT_ENDS_AT_CUSTOMERS,
        "before_the_first_customer": before,
        "rapid_support": support,
        "may_spend": list(MAY_SPEND),
        "may_not_spend": list(MAY_NOT_SPEND),
        "note": (("the sprint has not started, and four of its five priorities do not need "
                  "it to. They are ready or not ready today")
                 if not started else
                 ("the sprint is over; what these buy afterwards is the ordinary standard"
                  if finished else
                  f"{SPRINT_ENDS_AT_CUSTOMERS - customers} customers left, and each arrives "
                  f"exactly once")),
    }


def check_investment(kind: str, *, is_discount: bool = False) -> dict:
    """Whether this is a trust investment or a discount wearing its clothes.

    "Do not sacrifice contribution irrationally" reads specifically here: a discount during
    the trust sprint teaches the hundred buyers whose repeat behaviour matters most that the
    price is negotiable, and they are precisely the cohort a value ladder depends on.
    """
    if is_discount or kind in MAY_NOT_SPEND:
        return {
            "kind": kind, "allowed": False,
            "why": ("a discount during the trust sprint teaches the hundred buyers whose "
                    "repeat behaviour matters most that the price is negotiable, and they "
                    "are exactly the cohort the value ladder depends on. The sprint spends "
                    "time and prevention, not price"),
        }
    if kind not in MAY_SPEND:
        return {"kind": kind, "allowed": False,
                "why": f"{kind!r} is not something this sprint spends: {list(MAY_SPEND)}"}
    return {"kind": kind, "allowed": True,
            "why": "time and prevention are what early trust is actually made of"}


def state() -> dict:
    """The five priorities, when each happens, and what the sprint may cost."""
    return {
        "priorities": {k: dict(v) for k, v in PRIORITIES.items()},
        "before_the_first_customer": [k for k, v in PRIORITIES.items()
                                      if v["when"] == BEFORE],
        "needs_customers": [k for k, v in PRIORITIES.items() if v["when"] == DURING],
        "ends_at_customers": SPRINT_ENDS_AT_CUSTOMERS,
        "may_spend": list(MAY_SPEND),
        "may_not_spend": list(MAY_NOT_SPEND),
        "note": ("Four of the five priorities happen before the first customer, not during "
                 "the first hundred. A plan that begins at the first sale lets them sit "
                 "unfinished while the shop feels prepared, and each of those hundred "
                 "customers arrives exactly once (#259)."),
    }
