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


# F-456/F-482: the shared contracts this module was built against. A contract that moves on
# without this module migrating fails here, at import, instead of drifting silently.
from ..core import contracts as _contracts  # noqa: E402

_contracts.require("shop_policy_sections", 1)


# ---- W4-C13 F-598: the weekly cross-surface consistency audit -------------------------------
#
# F-598: "Weekly compare Dashboard, Listings, Search Visibility, Stats, Marketing, Finances,
# Apps and Settings for contradictions: active counts, fees, traffic, state, policies,
# credentials and warnings." Each comparison reads two stored readings of the same fact from
# two surfaces and reports a contradiction when they disagree. A comparison missing either
# reading is UNOBSERVED by name -- never consistent. Read-only; one stored reading per ISO week
# and one open incident while contradictions stand.

AUDIT_KIND = "etsy.cross_surface_audit"
AUDIT_SIGNATURE = "etsy-cross-surface-contradiction"


def _reading(db, kind: str):
    from ..runtime.etsy_ops import latest_reading

    try:
        return latest_reading(db, kind)
    except Exception:  # noqa: BLE001 - an unreadable reading is unobserved
        return None


def cross_surface(db, *, now=None) -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import Incident, Listing, OperatingReading
    from ..runtime.etsy_ops import CENSUS_READING, CREDENTIAL_READING, SHOP_READING

    now = now or datetime.now(timezone.utc)
    shop = _reading(db, SHOP_READING)
    census = _reading(db, CENSUS_READING)
    cred = _reading(db, CREDENTIAL_READING)
    comps: list[dict] = []

    def put(name, surfaces, state, detail):
        comps.append({"check": name, "surfaces": surfaces, "state": state, "detail": detail})

    estate = (census or {}).get("estate") or []
    # active counts: Settings/Dashboard (getShop) vs Listings (census)
    if shop and census and "listing_active_count" in (shop.get("shop") or {}):
        a = int(shop["shop"]["listing_active_count"])
        b = sum(1 for r in estate if r.get("state") == "active")
        put("active_counts", ["shop (getShop)", "listings (census)"],
            "CONSISTENT" if a == b else "CONTRADICTION",
            f"shop says {a} active, the census holds {b}")
    else:
        put("active_counts", ["shop (getShop)", "listings (census)"], "UNOBSERVED",
            "needs both a shop snapshot with listing_active_count and a census")
    # state: what this company recorded as listed vs what Etsy holds
    with db.session() as s:
        ours = {i for i in s.scalars(select(Listing.etsy_listing_id)) if i}
    if census is not None:
        held = {str(r.get("listing_id")) for r in estate}
        missing = sorted(ours - held)
        put("listing_state", ["local listings", "listings (census)"],
            "CONTRADICTION" if missing else "CONSISTENT",
            (f"recorded as listed but not held by Etsy: {missing[:10]}" if missing
             else f"{len(ours)} recorded listing(s) all held"))
    else:
        put("listing_state", ["local listings", "listings (census)"], "UNOBSERVED",
            "no census reading")
    # policies: the shop's policy text vs the canonical sources
    pc = (shop or {}).get("policy_consistency")
    if pc is None and shop is not None:
        pc = check(shop.get("shop"))
    if pc is None or pc.get("consistent") is None:
        put("policies", ["settings (policies)", "canonical terms"], "UNOBSERVED",
            "no shop snapshot")
    else:
        put("policies", ["settings (policies)", "canonical terms"],
            "CONSISTENT" if pc["consistent"] else "CONTRADICTION",
            {"differs": pc.get("differs"), "contradictions": len(pc.get("contradictions") or [])})
    # credentials: the credential reading vs a shop read that needed it
    if cred and shop:
        healthy = str(cred.get("status") or "").upper() in ("HEALTHY", "OK")
        put("credentials", ["apps/API (credential)", "shop (getShop)"],
            "CONSISTENT" if healthy else "CONTRADICTION",
            f"credential reads {cred.get('status')} while a shop snapshot was taken")
    else:
        put("credentials", ["apps/API (credential)", "shop (getShop)"], "UNOBSERVED",
            "needs both a credential reading and a shop snapshot")
    # warnings: open Search Visibility items on listings Etsy no longer holds
    try:
        from . import search_visibility as sv

        listed = [i for i in sv.items(db) if i["state"] != sv.CLEARED and i["listing_id"]]
    except Exception:  # noqa: BLE001
        listed = None
    if listed is None or census is None:
        put("warnings", ["search visibility", "listings (census)"], "UNOBSERVED",
            "needs Search Visibility readings and a census")
    else:
        held = {str(r.get("listing_id")) for r in estate}
        gone = sorted({i["listing_id"] for i in listed} - held)
        put("warnings", ["search visibility", "listings (census)"],
            "CONTRADICTION" if gone else "CONSISTENT",
            f"open warnings on listings Etsy does not hold: {gone}" if gone
            else f"{len(listed)} open warning(s), all on held listings")
    # Fees, traffic and finances: no stored reading pairs exist yet for this comparison.
    for name, surfaces in (("fees", ["finances (ledger)", "orders"]),
                           ("traffic", ["dashboard", "stats"])):
        put(name, surfaces, "UNOBSERVED", "no second stored reading of this fact exists yet")
    contradictions = [c for c in comps if c["state"] == "CONTRADICTION"]
    week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    payload = {"at": now.isoformat(), "week": week, "comparisons": comps,
               "contradictions": len(contradictions),
               "unobserved": [c["check"] for c in comps if c["state"] == "UNOBSERVED"]}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == AUDIT_KIND,
                                                      OperatingReading.period_key == week))
        if row is None:
            s.add(OperatingReading(kind=AUDIT_KIND, period_key=week, payload=payload, at=now))
        else:
            row.payload, row.at = payload, now
        inc = s.scalar(select(Incident).where(Incident.signature == AUDIT_SIGNATURE,
                                              Incident.resolved.is_(False)))
        if contradictions and inc is None:
            s.add(Incident(severity="P2", signature=AUDIT_SIGNATURE, halts_publication=False,
                           summary=(f"{len(contradictions)} cross-surface contradiction(s): "
                                    f"{[c['check'] for c in contradictions]}"),
                           detail={"owner": "store_commerce", "week": week}))
        elif inc is not None:
            if contradictions:
                inc.detail = {**(inc.detail or {}), "week": week}
            else:
                inc.resolved = True
    return payload
