"""One canonical source per policy fact, checked against what the live shop says (F-537).

Listing, PDF and FAQ terms already render from one decision (`commerce.terms`) and
`commerce.shop_package` checks them against each other. What nobody checked was the text
Etsy actually shows: the shop policies are typed into Shop Manager by a person, and
`policy_additional` / the digital sale message are written once and can be edited by hand
afterwards. This module reads the daily `getShop` snapshot and answers two questions:

1. **Does each live policy field say what its canonical source says?** MATCH (whitespace and
   quote-normalised), DIFFERS, BLANK, or NOT_RETURNED (unknown -- never a pass).
2. **Does any live text contradict a policy fact?** Each fact has exactly one owning source
   (`FACTS`), and a contradiction pattern found in any live field is reported against it,
   whatever the field's wording otherwise is. A contradiction is the finding that matters: a
   buyer who reads two answers is entitled to the more favourable one.

The internal surfaces' own consistency (`shop_package.check_package`) is included so the
reading covers listing promises, PDF/customer terms, shop policies, FAQ/support language and
internal rules in one place. Read-only; it never writes the shop.
"""
from __future__ import annotations

import re
import unicodedata

MATCH, DIFFERS, BLANK, NOT_RETURNED = "MATCH", "DIFFERS", "BLANK", "NOT_RETURNED"

#: (live getShop field, canonical source, how it reaches Etsy)
FIELDS: tuple[tuple[str, str, str], ...] = (
    ("policy_shipping", "shop_package.policies()['delivery']", "typed by the owner"),
    ("policy_refunds", "shop_package.policies()['returns']", "typed by the owner"),
    ("policy_privacy", "shop_package.policies()['privacy']", "typed by the owner"),
    ("policy_additional", "shop_package.shop_text()['policy_additional']", "updateShop"),
    ("digital_sale_message", "shop_package.shop_text()['digital_sale_message']",
     "updateShop"),
)

#: fact -> (canonical owner, contradiction pattern, what the canonical answer is)
FACTS: dict[str, tuple[str, str, str]] = {
    "digital_no_returns_but_fixes": (
        "shop_package.RETURNS",
        r"\b(returns? (and exchanges )?(are )?accepted|we accept returns|"
        r"no (refunds|corrections) (of|for) any kind)\b",
        "digital patterns are not returnable; errors are corrected and re-issued"),
    "nothing_is_shipped": (
        "shop_package.DELIVERY",
        r"\b(ships? (within|in) \d+|processing time:? ?\d+|tracking number|"
        r"shipped (by|via|with))\b",
        "every product is a digital file; nothing is posted"),
    "sell_what_you_make": (
        "commerce.terms (finished_item_sale)",
        r"\b(personal use only|(may|must) not sell (the )?(finished|items you make)|"
        r"cannot sell (the )?(finished|items you make))\b",
        "buyers may sell the items they make from a pattern"),
    "no_mailing_list_without_consent": (
        "shop_package.PRIVACY",
        r"\b(add(ed)? (you )?to our (mailing|email) list|subscribe you automatically)\b",
        "buyers are never added to a mailing list without asking (CASL)"),
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = (text.replace("’", "'").replace("‘", "'").replace("“", '"')
            .replace("”", '"').replace("—", "-").replace("–", "-"))
    return re.sub(r"\s+", " ", text).strip().lower()


def canonical() -> dict[str, str]:
    """Each live field's canonical text, from its one owning source."""
    from . import shop_package

    pol, text = shop_package.policies(), shop_package.shop_text()
    return {"policy_shipping": pol["delivery"], "policy_refunds": pol["returns"],
            "policy_privacy": pol["privacy"],
            "policy_additional": text["policy_additional"],
            "digital_sale_message": text["digital_sale_message"]}


def check(shop: dict | None) -> dict:
    """The live shop's policy text against the canonical sources and the facts."""
    from . import shop_package

    want = canonical()
    fields, contradictions = [], []
    for field, source, channel in FIELDS:
        if shop is None or field not in shop:
            status = NOT_RETURNED
        elif not str(shop.get(field) or "").strip():
            # An intentionally empty canonical value (e.g. policy_additional, EU-only) is
            # consistent when the live field is empty too; otherwise an empty field is a gap.
            status = MATCH if not str(want.get(field) or "").strip() else BLANK
        elif _norm(str(shop.get(field))) == _norm(want[field]):
            status = MATCH
        else:
            status = DIFFERS
        fields.append({"field": field, "canonical_source": source, "channel": channel,
                       "status": status})
        live = _norm(str((shop or {}).get(field) or ""))
        for fact, (owner, pattern, answer) in FACTS.items():
            hit = re.search(pattern, live) if live else None
            if hit:
                contradictions.append({"fact": fact, "field": field, "owner": owner,
                                       "canonical_answer": answer, "found": hit.group(0)})
    internal = shop_package.check_package()
    observed = shop is not None
    differs = [f["field"] for f in fields if f["status"] in (DIFFERS, BLANK)]
    consistent = observed and not contradictions and not differs and not internal
    return {"observed": observed, "consistent": consistent if observed else None,
            "fields": fields, "differs": differs, "contradictions": contradictions,
            "internal_problems": internal,
            "facts": {k: {"owner": v[0], "answer": v[2]} for k, v in FACTS.items()}}
