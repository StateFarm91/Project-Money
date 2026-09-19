"""Revenue does not automatically become ad budget.

Requirement 49. The sentence is short and the discipline it describes is the one small
businesses most reliably fail. Money arrives, it is in the account, the obvious use is more of
whatever produced it — and the tax that was always owed on it arrives in April against an
account that bought advertising in November.

Four reserves, filled in order, and only what survives all four is an envelope:

  **Tax.** Never yours. Set aside at the moment of sale rather than at the end of the year,
  because the alternative is a business that is solvent until it is assessed.
  **Operating.** The floor that keeps the company running with no revenue at all: hosting,
  the model budget, listing renewals. Below this, one quiet month ends it.
  **Cash reserve.** Months of operating cost held against a bad quarter, so a downturn is an
  inconvenience rather than a decision.
  **Reinvestment envelope.** What is genuinely spare.

Two things this module refuses.

**It does not recommend spending on a confidence it does not have.** The envelope is
multiplied by the modelled confidence in the target, so a company with no customers has an
envelope of nearly nothing however much cash is in the account. That is the correct answer:
cash from an unrepeatable source is not evidence that spending will repeat it.

**It never authorises.** The CFO recommends; consequential spend is the owner's, in code, at
the point of recommendation rather than in a paragraph somewhere. A recommendation that could
become a spend without passing a person is not a recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass

# Canada/CAD. A deliberately high set-aside: over-reserving costs interest, under-reserving
# costs the company.
TAX_RATE = 0.30

# What the company must be able to pay with no revenue at all, per month. Derived from what is
# actually authorised: hosting plus the approved model ceiling plus listing renewals.
OPERATING_FLOOR_CAD = 45.0

# Months of operating cost held before anything is spare.
CASH_RESERVE_MONTHS = 6

# Above this, a single recommendation is consequential whatever the confidence.
OWNER_APPROVAL_ABOVE_CAD = 50.0


class ReinvestmentRefused(ValueError):
    """A spend recommendation that would come out of a reserve, or authorise itself."""


@dataclass
class Envelope:
    gross_cad: float
    tax_reserve_cad: float
    operating_reserve_cad: float
    cash_reserve_cad: float
    envelope_cad: float
    confidence: float
    recommended_cad: float
    reserves_short_by_cad: float = 0.0

    def to_dict(self) -> dict:
        return {
            "gross_cad": round(self.gross_cad, 2),
            "tax_reserve_cad": round(self.tax_reserve_cad, 2),
            "operating_reserve_cad": round(self.operating_reserve_cad, 2),
            "cash_reserve_cad": round(self.cash_reserve_cad, 2),
            "envelope_cad": round(self.envelope_cad, 2),
            "confidence": round(self.confidence, 3),
            "recommended_cad": round(self.recommended_cad, 2),
            "reserves_short_by_cad": round(self.reserves_short_by_cad, 2),
            "requires_owner_approval": self.recommended_cad > 0,
            "note": self._note(),
        }

    def _note(self) -> str:
        if self.reserves_short_by_cad > 0:
            return (f"Nothing is spare: the reserves are short by "
                    f"CA${self.reserves_short_by_cad:.2f}. Revenue fills the tax, operating "
                    f"and cash reserves before any of it is an envelope.")
        if self.envelope_cad > 0 and self.recommended_cad < self.envelope_cad:
            return (f"CA${self.envelope_cad:.2f} is spare and CA${self.recommended_cad:.2f} "
                    f"is recommended, because the envelope is scaled by a modelled "
                    f"confidence of {self.confidence:.2f}. Cash from an unrepeatable source "
                    f"is not evidence that spending will repeat it.")
        return "no revenue, so no envelope. This is arithmetic, not caution."


def envelope(db, *, gross_cad: float, months_of_revenue: int = 1,
             confidence: float | None = None) -> Envelope:
    """What, if anything, is genuinely spare — and what the CFO may therefore recommend.

    Confidence comes from the ladder rather than from a caller by default, so a recommendation
    cannot be produced by supplying an optimistic number alongside the cash.
    """
    from ..scale.confidence import probability

    if confidence is None:
        confidence = probability(db)["probability"]
    if not 0.0 <= confidence <= 1.0:
        raise ReinvestmentRefused(f"confidence {confidence!r} is outside 0.0-1.0")

    tax = gross_cad * TAX_RATE
    operating = OPERATING_FLOOR_CAD * max(1, months_of_revenue)
    cash = OPERATING_FLOOR_CAD * CASH_RESERVE_MONTHS

    after_reserves = gross_cad - tax - operating - cash
    short = max(0.0, -after_reserves)
    spare = max(0.0, after_reserves)

    # Scaled by confidence, not by appetite. An envelope is what is spare; the recommendation
    # is what the evidence supports spending out of it.
    recommended = round(spare * confidence, 2)
    return Envelope(gross_cad=gross_cad, tax_reserve_cad=tax,
                    operating_reserve_cad=operating, cash_reserve_cad=cash,
                    envelope_cad=spare, confidence=confidence,
                    recommended_cad=recommended, reserves_short_by_cad=short)


def recommend(db, *, gross_cad: float, purpose: str, months_of_revenue: int = 1,
              confidence: float | None = None) -> dict:
    """A recommendation, which is all this is. It cannot become a spend without the owner.

    The authority boundary is enforced here rather than described elsewhere: every non-zero
    recommendation carries `owner_approval_required: True`, and there is no branch of this
    function that returns False.
    """
    if len(purpose.strip()) < 10:
        raise ReinvestmentRefused(
            "a reinvestment recommendation names what it is for. 'Growth' is a category, not "
            "a purpose, and it is how an envelope becomes a standing budget")
    e = envelope(db, gross_cad=gross_cad, months_of_revenue=months_of_revenue,
                 confidence=confidence)
    return {
        "purpose": purpose.strip(),
        "envelope": e.to_dict(),
        "recommended_cad": e.recommended_cad,
        # No branch returns False. A recommendation that could become a spend without passing
        # a person is not a recommendation, whatever it is called.
        "owner_approval_required": True,
        "consequential": e.recommended_cad > OWNER_APPROVAL_ABOVE_CAD,
        "authority": ("RED under the authority matrix. The CFO recommends; the owner "
                      "decides. This function has no code path that authorises a spend."),
    }


def describe() -> dict:
    return {
        "order": ["tax_reserve", "operating_reserve", "cash_reserve", "reinvestment_envelope"],
        "tax_rate": TAX_RATE,
        "operating_floor_cad_per_month": OPERATING_FLOOR_CAD,
        "cash_reserve_months": CASH_RESERVE_MONTHS,
        "owner_approval_above_cad": OWNER_APPROVAL_ABOVE_CAD,
        "rule": ("Revenue does not automatically become ad budget (#49). The reserves fill "
                 "in order, the envelope is what survives them, and the recommendation is "
                 "the envelope scaled by the modelled confidence -- because cash from an "
                 "unrepeatable source is not evidence that spending will repeat it."),
    }
