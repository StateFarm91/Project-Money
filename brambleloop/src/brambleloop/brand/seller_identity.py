"""Public seller identity vs legal/tax identity (F-240).

Requirement F-240: *the approved public shop identity may differ from the legal/tax
presentation only where Etsy permits; legal, payout and tax identity remain truthful.*

Two presentations of one seller, kept side by side so that a difference between them is a
recorded, cited decision rather than an accident:

- **public** -- what a buyer sees: the shop name, the location and currency the shop shows,
  and any owner name on the About page. This company decides these, and they are recorded
  with where each was decided.
- **legal** -- what Etsy's identity verification, the payout account and the tax registration
  hold. Only the account holder enters these, at Etsy's KYC (owner gate `etsy_shop`), so
  every legal value here is `UNKNOWN` until the owner confirms it. Nothing in this module may
  fill one in: a guessed legal name is the precise falsehood the requirement forbids.

A field whose public and legal values differ is acceptable only when the difference cites an
Etsy rule that is actually on file in `gates.policy_knowledge`. A citation to a rule the
repository has never read is refused as un-sourced, the same way a claim labelled better than
its evidence is refused in `commerce.shop_package`.

On the date this was written, no reading in `gates.policy_knowledge` covers Etsy's rule on
shop names versus legal names (Etsy's help and policy pages refuse automated readers; see
`policy_knowledge.RETRIEVAL_BLOCK`). So `PERMITTED_DIFFERENCES` is empty, and the expected
difference -- a brand shop name beside a person's legal name -- is listed in
`PENDING_RULE_READINGS` as a question for the owner's page reading, not answered here.
"""
from __future__ import annotations

from dataclasses import dataclass

UNKNOWN = "UNKNOWN"

# Field states, per field, after comparing the two presentations.
SAME = "SAME"
PERMITTED = "PERMITTED"            # differs, and the difference cites a rule on file
UNSOURCED = "UNSOURCED"            # differs, and nothing on file says Etsy permits it
UNDETERMINED = "UNDETERMINED"      # one side is UNKNOWN: not compared, never passed

# The only provenance a legal value may carry: the account holder confirmed it at Etsy KYC.
OWNER_CONFIRMED_PREFIX = "owner_confirmed_at_kyc:"

LEGAL_GATE = "etsy_shop"


@dataclass(frozen=True)
class IdentityField:
    key: str
    what: str
    public: str
    public_source: str
    legal: str = UNKNOWN
    legal_source: str = ""      # OWNER_CONFIRMED_PREFIX + ISO date, or "" while UNKNOWN

    def to_dict(self) -> dict:
        return {"key": self.key, "what": self.what, "public": self.public,
                "public_source": self.public_source, "legal": self.legal,
                "legal_source": self.legal_source or None,
                "legal_gate": LEGAL_GATE if self.legal == UNKNOWN else None}


def _shop_name() -> str:
    from .storefront import SHOP_NAME

    return SHOP_NAME


def fields() -> tuple[IdentityField, ...]:
    """The record as it stands. Every legal value is UNKNOWN until the owner confirms it."""
    return (
        IdentityField("name", "the name the shop trades under vs the legal name on the account",
                      public=_shop_name(), public_source="brand.storefront.SHOP_NAME"),
        IdentityField("country", "the shop location shown vs the account holder's legal "
                                 "country of residence",
                      public="Canada",
                      public_source="launch.readiness.ETSY_ACCOUNT (shop location Canada)"),
        IdentityField("currency", "the listing currency vs the payout account's currency",
                      public="CAD",
                      public_source="launch.readiness.ETSY_ACCOUNT (currency CAD)"),
        IdentityField("owner_display_name", "any person's name shown on the About page vs "
                                            "the verified identity",
                      public=UNKNOWN,
                      public_source="not decided: the owner chooses whether a name appears"),
        IdentityField("tax_registration", "GST/HST registration shown vs held",
                      public="not displayed",
                      public_source="commerce.shop_package (cra_registration claim)"),
    )


# field key -> (policy_knowledge reading key, rule key). Only rules that are actually on file
# may be cited; `check_identity` verifies each citation against the readings.
PERMITTED_DIFFERENCES: dict[str, tuple[str, str]] = {}

# Differences that will exist the moment the legal side is known, and the rule each needs.
PENDING_RULE_READINGS: tuple[dict, ...] = (
    {"field": "name",
     "question": ("does Etsy permit a shop name that differs from the account holder's legal "
                  "name, and must the legal name appear anywhere a buyer can see it"),
     "where": ("Etsy Seller Policy and shop-name guidance, read by the owner and recorded with "
               "gates.platform_policy.record_page_reading"),
     "why_unanswered": ("no reading in gates.policy_knowledge covers it; Etsy's help and "
                        "policy pages refuse automated readers")},
)


def _rule_on_file(reading: str, rule: str) -> bool:
    from ..gates import policy_knowledge

    r = policy_knowledge.all_readings().get(reading)
    return bool(r) and any(c.get("rule") == rule for c in r.conclusions)


def compare(record: tuple[IdentityField, ...] | None = None,
            permitted: dict[str, tuple[str, str]] | None = None) -> list[dict]:
    """Each field's public/legal comparison, with the rule a difference rests on."""
    record = fields() if record is None else record
    permitted = PERMITTED_DIFFERENCES if permitted is None else permitted
    out = []
    for f in record:
        cite = permitted.get(f.key)
        if UNKNOWN in (f.public, f.legal):
            state = UNDETERMINED
        elif f.public.strip().lower() == f.legal.strip().lower():
            state = SAME
        elif cite and _rule_on_file(*cite):
            state = PERMITTED
        else:
            state = UNSOURCED
        out.append({**f.to_dict(), "state": state,
                    "permitted_by": ({"reading": cite[0], "rule": cite[1],
                                      "on_file": _rule_on_file(*cite)} if cite else None)})
    return out


def check_identity(record: tuple[IdentityField, ...] | None = None,
                   permitted: dict[str, tuple[str, str]] | None = None, *,
                   shop_name: str | None = None) -> list[str]:
    """What is wrong with the identity record. UNDETERMINED is not a problem here -- it is an
    owner gate, reported by `state()` and by launch readiness -- but it is never a pass."""
    record = fields() if record is None else record
    permitted = PERMITTED_DIFFERENCES if permitted is None else permitted
    problems: list[str] = []
    for f in record:
        if f.legal != UNKNOWN and not f.legal_source.startswith(OWNER_CONFIRMED_PREFIX):
            problems.append(
                f"IDENTITY_LEGAL_UNCONFIRMED: {f.key} carries a legal value with no owner "
                f"confirmation at KYC; legal identity is entered by the account holder, never "
                f"supplied by this system")
        if not f.public.strip():
            problems.append(f"IDENTITY_PUBLIC_BLANK: {f.key} has an empty public value")
    for key, (reading, rule) in permitted.items():
        if not _rule_on_file(reading, rule):
            problems.append(f"IDENTITY_RULE_NOT_ON_FILE: {key} cites {reading}.{rule}, which "
                            f"no reading in gates.policy_knowledge records")
    for row in compare(record, permitted):
        if row["state"] == UNSOURCED:
            problems.append(
                f"IDENTITY_DIFFERENCE_UNSOURCED: public {row['key']} {row['public']!r} differs "
                f"from the legal {row['legal']!r} and no Etsy rule on file permits it")
    if shop_name is not None:
        name = next((f for f in record if f.key == "name"), None)
        if name is None or name.public != shop_name:
            problems.append(f"IDENTITY_STALE: the storefront shows {shop_name!r} but the "
                            f"identity record's public name is "
                            f"{getattr(name, 'public', None)!r}")
    return problems


def state() -> dict:
    rows = compare()
    undetermined = [r["key"] for r in rows if r["state"] == UNDETERMINED]
    problems = check_identity()
    return {"fields": rows, "problems": problems, "undetermined": undetermined,
            "permitted_differences": {k: {"reading": v[0], "rule": v[1]}
                                      for k, v in PERMITTED_DIFFERENCES.items()},
            "pending_rule_readings": list(PENDING_RULE_READINGS),
            "legal_gate": LEGAL_GATE,
            "complete": not problems and not undetermined,
            "note": ("legal, payout and tax identity are entered by the account holder at "
                     "Etsy KYC and are UNKNOWN here until confirmed; UNDETERMINED is not a "
                     "pass")}
