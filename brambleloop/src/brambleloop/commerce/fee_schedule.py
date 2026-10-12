"""Etsy's fees as claims with a source, a date and a grade of evidence -- not as literals.

Before this module the same fee lived in five files as five unlinked numbers: `0.20` in
`commerce.pricing`, `scale.target`, `integrations.etsy` and `launch.readiness` (once as
`0.28`, hand-converted to CAD), `0.065` in three of them, and `3% + 0.25` in two. Each was
true on the day it was typed and none of them knew about the others, so a fee change would
have had to be found by reading the whole repository, and a wrong one could not be traced to
what it was read from.

The company's dated reading of Etsy's fee pages is `gates.policy_knowledge.TOPICS["fees"]`.
This module reads *that* and nothing else: every number here is parsed from a conclusion in
that reading, carries the reading's `read_on` and `basis`, and names the official URL the
conclusion concerns. A fee the reading records as UNKNOWN is UNKNOWN here too, with no number
attached at all, because a rate nobody has read is not made real by being needed.

**Evidence grades.** A claim is PRIMARY when its figure appears in a verbatim excerpt of the
official page recorded alongside the conclusion; SECONDARY when the reading states it without
an excerpt to rest on; UNKNOWN when the reading says so. Only a PRIMARY claim may enter a take
rate: `take_rate()` refuses the others, so a figure this company has not seen on an Etsy page
cannot be quoted as the cost of selling on one.

Nothing here is legal or accounting advice; it is a reading, dated, and re-checkable by
digest like every other reading in `policy_knowledge`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..gates import policy_knowledge as PK

PRIMARY = "PRIMARY"
SECONDARY = "SECONDARY"
UNKNOWN = "UNKNOWN"
EVIDENCE_GRADES = (PRIMARY, SECONDARY, UNKNOWN)


class FeeNotQuotable(ValueError):
    """A SECONDARY or UNKNOWN fee asked to stand in a take rate as if it had been read."""


@dataclass(frozen=True)
class FeeClaim:
    """One fee, as the reading states it.

    `rate` is a fraction of the gross (0.065 for 6.5%); `amount` is a flat charge in
    `currency`. Either may be None: a percentage-only fee has no `amount`, a flat-only fee has
    no `rate`, and an UNKNOWN fee has neither. `conclusion` is the reading's own sentence, kept
    so a consumer can print what was read rather than what was parsed from it.
    """

    key: str
    rate: float | None
    amount: float | None
    currency: str | None
    basis: str
    source_url: str
    checked_on: str
    evidence: str
    conclusion: str
    rate_range: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.evidence not in EVIDENCE_GRADES:
            raise ValueError(f"{self.evidence!r} is not an evidence grade: {EVIDENCE_GRADES}")
        if self.evidence == UNKNOWN and (self.rate is not None or self.amount is not None):
            raise ValueError(f"{self.key}: an UNKNOWN fee cannot carry a figure")

    @property
    def quotable(self) -> bool:
        """Whether this claim may stand in a take rate."""
        return self.evidence == PRIMARY

    def component(self, gross: float) -> float:
        """This fee's charge on one order of `gross`, or a refusal if it cannot be quoted."""
        if not self.quotable:
            raise FeeNotQuotable(
                f"{self.key} is {self.evidence} ({self.basis}, read {self.checked_on}); it "
                f"cannot be quoted as part of a take rate until the owner records a page "
                f"reading that states it")
        return gross * (self.rate or 0.0) + (self.amount or 0.0)

    def to_dict(self) -> dict:
        return {"key": self.key, "rate": self.rate, "amount": self.amount,
                "currency": self.currency, "rate_range": list(self.rate_range) if self.rate_range else None,
                "basis": self.basis, "source_url": self.source_url,
                "checked_on": self.checked_on, "evidence": self.evidence,
                "quotable": self.quotable, "conclusion": self.conclusion}


# ---------------------------------------------------------------------------
# Parsing the reading. Deliberately narrow: each pattern matches the way the reading writes
# a figure, and a figure it cannot find is None rather than a guess.

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PERCENT_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%")
_MONEY = re.compile(r"(US|CA)\$\s?(\d+(?:\.\d+)?)")
_FLAT = re.compile(r"\+\s*(US|CA)\$\s?(\d+(?:\.\d+)?)")


def _first_percent(text: str) -> float | None:
    m = _PERCENT.search(text)
    return round(float(m.group(1)) / 100.0, 6) if m else None


def _percent_range(text: str) -> tuple[float, float] | None:
    m = _PERCENT_RANGE.search(text)
    return (round(float(m.group(1)) / 100.0, 6), round(float(m.group(2)) / 100.0, 6)) if m else None


def _first_money(text: str) -> tuple[float, str] | None:
    m = _MONEY.search(text)
    return (float(m.group(2)), f"{m.group(1)}D") if m else None


def _figure_in_excerpts(figure: str, excerpts) -> bool:
    return any(figure in e.text for e in excerpts)


def _grade(conclusion: dict, *, rate: float | None, amount: float | None, excerpts) -> str:
    """PRIMARY when the figure is in a verbatim excerpt, SECONDARY when only concluded."""
    if "UNKNOWN" in conclusion["amount"]:
        return UNKNOWN
    checks = []
    if rate is not None:
        pct = f"{rate * 100:g}%"
        # A rate stated as a range in the excerpt ("3-4%") is still the page's own figure.
        checks.append(_figure_in_excerpts(pct, excerpts)
                      or any(re.search(rf"\b{re.escape(f'{rate * 100:g}')}\s*-\s*\d", e.text)
                             for e in excerpts))
    if amount is not None:
        checks.append(_figure_in_excerpts(f"{amount:.2f}", excerpts))
    return PRIMARY if checks and all(checks) else SECONDARY


def _claim(conclusion: dict, reading: PK.Reading, *, extra_excerpts=()) -> FeeClaim:
    text = conclusion["amount"]
    unknown = "UNKNOWN" in text
    rate = None if unknown else _first_percent(text)
    rng = None if unknown else _percent_range(text)
    # A flat per-order component is the money figure the reading introduces with "+" ("3% +
    # CA$0.25"); a fee with no percentage at all ("US$0.20 per listing") is flat outright.
    # Thresholds ("above US$10,000") and caps ("capped at US$100") are neither.
    amount, currency = None, None
    if not unknown:
        flat = _FLAT.search(text)
        if flat is not None:
            amount, currency = float(flat.group(2)), f"{flat.group(1)}D"
        elif rate is None:
            money = _first_money(text)
            if money is not None:
                amount, currency = money
    excerpts = tuple(reading.excerpts) + tuple(extra_excerpts)
    return FeeClaim(
        key=conclusion["fee"], rate=rate, amount=amount, currency=currency,
        basis=reading.basis, source_url=reading.urls[0], checked_on=reading.read_on,
        evidence=_grade(conclusion, rate=rate, amount=amount, excerpts=excerpts),
        conclusion=text, rate_range=rng)


def _build() -> dict[str, FeeClaim]:
    reading = PK.TOPICS["fees"]
    # The Offsite Ads figures are excerpted on the advertising surface rather than the fee
    # topic, so that reading's excerpts count as evidence for that one claim.
    ads = PK.READINGS["advertising_rules"].excerpts
    out: dict[str, FeeClaim] = {}
    for c in reading.conclusions:
        extra = ads if c["fee"] == "offsite_ads" else ()
        out[c["fee"]] = _claim(c, reading, extra_excerpts=extra)
    return out


CLAIMS: dict[str, FeeClaim] = _build()

# The per-sale charges a Canadian digital-download shop pays on every order, by the reading.
TRANSACTION = CLAIMS["transaction"]
PAYMENT_PROCESSING = CLAIMS["payment_processing_canada"]
LISTING = CLAIMS["listing"]
CURRENCY_CONVERSION = CLAIMS["currency_conversion"]
REGULATORY_OPERATING = CLAIMS["regulatory_operating"]
OFFSITE_ADS = CLAIMS["offsite_ads"]

# How long a listing runs before Etsy renews it, from the same reading ("lasts four months").
LISTING_RENEWAL_MONTHS = 4 if "four months" in LISTING.conclusion else None

READ_ON = PK.TOPICS["fees"].read_on
BASIS = PK.TOPICS["fees"].basis


def listing_fee_cad(usd_per_cad: float) -> float:
    """The listing fee in the reporting currency, converted once, here, at a stated rate.

    `launch.readiness` carried `LISTING_FEE_CAD = 0.28`, a number somebody worked out by hand
    from a rate that was written down somewhere else. The conversion is arithmetic on two
    facts, and arithmetic belongs in code so both facts can change.
    """
    if usd_per_cad <= 0:
        raise ValueError("an exchange rate must be positive to convert with")
    if LISTING.amount is None or LISTING.currency != "USD":
        raise FeeNotQuotable("the reading does not state a USD listing fee")
    return round(LISTING.amount / usd_per_cad, 2)


def take_rate(gross_cad: float, claims: tuple[FeeClaim, ...] = (TRANSACTION, PAYMENT_PROCESSING),
              ) -> dict:
    """The fraction of a CAD gross that Etsy keeps, from PRIMARY claims only.

    Refuses a SECONDARY or UNKNOWN claim rather than folding it in: a take rate is quoted as
    the cost of selling, and a number this company has not seen on an Etsy page has no place
    in it. The fees that were *not* included are named in the answer, so it cannot be read as
    complete.
    """
    if gross_cad <= 0:
        raise ValueError("a take rate needs a positive gross")
    components = {c.key: round(c.component(gross_cad), 4) for c in claims}
    total = round(sum(components.values()), 4)
    excluded = sorted(k for k, c in CLAIMS.items() if c not in claims)
    return {"gross_cad": round(gross_cad, 2), "components": components, "total_cad": total,
            "take_rate": round(total / gross_cad, 4), "excluded": excluded,
            "read_on": READ_ON, "basis": BASIS,
            "note": "PRIMARY claims only; the excluded fees are named, not folded in"}


def describe() -> dict:
    return {"read_on": READ_ON, "basis": BASIS, "retrieval_block": PK.RETRIEVAL_BLOCK,
            "claims": {k: v.to_dict() for k, v in CLAIMS.items()},
            "quotable": sorted(k for k, v in CLAIMS.items() if v.quotable),
            "not_quotable": sorted(k for k, v in CLAIMS.items() if not v.quotable),
            "rule": ("only a PRIMARY claim -- a figure present in a verbatim excerpt of the "
                     "official page -- may enter a take rate; SECONDARY and UNKNOWN fees are "
                     "named where they are excluded")}
