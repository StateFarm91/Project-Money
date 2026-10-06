"""Per-surface readiness: deterministic checks, one verdict per surface, one roll-up.

Statuses, worst first:
    FAIL         a check this company can fix failed (truth lint, a verified limit, a missing
                 required phrase, a broken asset)
    NEEDS_OWNER  the content is prepared and something only the owner can decide or do
                 remains (legal review, a naming decision, a launch threshold)
    GATED        depends on something external that does not exist yet (a live listing, a
                 messaging integration)
    UNVERIFIED   nothing failed, but a limit or fact the check needs is not on file
    READY        every check ran and passed

READY never means "entered on Etsy": `entered_on_etsy` is UNKNOWN on every surface because
the live shop is not read here. It means the prepared content is fit to enter.
"""
from __future__ import annotations

import re

from . import content as C
from . import limits, lint

FAIL, NEEDS_OWNER, GATED, UNVERIFIED, READY = (
    "FAIL", "NEEDS_OWNER", "GATED", "UNVERIFIED", "READY")
ORDER = (FAIL, NEEDS_OWNER, GATED, UNVERIFIED, READY)
_SEV_STATUS = {"fail": FAIL, "owner": NEEDS_OWNER, "gated": GATED,
               "unverified": UNVERIFIED, "warn": UNVERIFIED, "info": READY}

# A nursery or baby product titled with kitchen/table words is positioned as two products.
_POSITIONING = {"nursery": ("bread", "kitchen", "dining", "picnic", "table", "fruit"),
                "baby": ("bread", "kitchen", "dining", "picnic", "fruit")}


def _f(code: str, severity: str, detail: str) -> dict:
    return {"code": code, "severity": severity, "detail": detail}


def _status(findings: list[dict]) -> str:
    worst = READY
    for f in findings:
        st = _SEV_STATUS.get(f["severity"], UNVERIFIED)
        if ORDER.index(st) < ORDER.index(worst):
            worst = st
    return worst


# ---- per-surface checks -------------------------------------------------------------------

def _check_shop_name(s: C.Surface) -> list[dict]:
    from ..brand import seller_identity

    out = [_f("IDENTITY", "fail", p) for p in
           seller_identity.check_identity(shop_name=s.value["display"])]
    if s.value["display"].replace(" ", "") != s.value["etsy_handle"]:
        out.append(_f("NAME_HANDLE_MISMATCH", "fail",
                      "display name and Etsy handle are different names"))
    out.append(_f("NAME_CONFIRM", "owner",
                  "confirm 'Brambleloop Studio' as the public name for the handle "
                  "BrambleloopStudio; whether a legal name must also appear is an open Etsy "
                  "rule reading (brand.seller_identity.PENDING_RULE_READINGS)"))
    return out


def _check_icon(s: C.Surface) -> list[dict]:
    from . import assets

    return assets.check_icon(s.value)


def _check_banner(s: C.Surface) -> list[dict]:
    from . import assets

    return assets.check_banner(s.value)


def _store_for_seo(surfaces: dict[str, C.Surface]):
    from ..brand import storefront

    return storefront.Storefront(
        shop_name=surfaces["shop_name"].value["display"],
        announcement=surfaces["announcement"].value, about=surfaces["about"].value,
        policies={}, sections=[], banner_brief="x", icon_brief="x",
        tagline=surfaces["shop_title"].value)


def _check_shop_title(s: C.Surface, surfaces) -> list[dict]:
    from ..brand import storefront

    return [_f("SEO", "fail", p) for p in storefront.check_shop_seo(_store_for_seo(surfaces))
            if "tagline" in p]


def _check_announcement(s: C.Surface) -> list[dict]:
    from ..brand import storefront_preview as sp

    opening = sp.announcement_opening(s.value)
    out = [_f("ANNOUNCEMENT_PHONE", "fail", p) for p in opening["problems"]]
    if not s.value.strip():
        out.append(_f("ANNOUNCEMENT_EMPTY", "fail", "the announcement is blank"))
    return out


def _check_about(s: C.Surface) -> list[dict]:
    from ..brand import storefront
    from ..commerce import shop_package

    out = [_f("ABOUT_COVERAGE", "fail", p) for p in shop_package.check_about(s.value)]
    if len(s.value) < storefront.ABOUT_MIN:
        out.append(_f("ABOUT_THIN", "fail", f"{len(s.value)} characters"))
    return out


def _check_returns(s: C.Surface) -> list[dict]:
    return [] if "cannot be returned" in s.value.lower() else [
        _f("RETURNS_UNCLEAR", "fail", "the returns policy must say digital patterns cannot "
                                      "be returned, before the sale")]


def _check_delivery(s: C.Surface) -> list[dict]:
    return [] if "digital" in s.value.lower() else [
        _f("DELIVERY_UNCLEAR", "fail", "the delivery policy must say the product is a file")]


def _check_licence(s: C.Surface) -> list[dict]:
    from ..commerce import terms

    decided = terms.BRAMBLELOOP_TERMS
    out = []
    if decided.sentence(terms.FINISHED_ITEM_SALE) not in s.value:
        out.append(_f("LICENCE_DIVERGES", "fail",
                      "the licence does not carry the decided finished-item sentence"))
    if not decided.enforceable:
        out.append(_f("LEGAL_REVIEW_PENDING", "owner",
                      "commerce.terms is not legally reviewed; the licence says so publicly "
                      "('have not yet been through legal review'). Owner: legal review, or "
                      "accept showing that sentence"))
    if "photographs" in s.value.lower():
        out.append(_f("LICENCE_MENTIONS_PHOTOGRAPHS", "unverified",
                      "the redistribution sentence names 'its photographs' while the shop "
                      "has none (images are renders); harmless but imprecise -- owned by "
                      "commerce.terms"))
    return out


def _check_privacy(s: C.Surface) -> list[dict]:
    low = s.value.lower()
    out = []
    for word, code in (("casl", "PRIVACY_NO_CASL"), ("pipeda", "PRIVACY_NO_PIPEDA"),
                       ("unsubscribe", "PRIVACY_NO_UNSUBSCRIBE"),
                       ("do not sell", "PRIVACY_NO_NOT_SELL")):
        if word not in low:
            out.append(_f(code, "fail", f"privacy text does not mention {word!r}"))
    out.append(_f("LEGAL_REVIEW_PENDING", "owner",
                  "the privacy text names PIPEDA and CASL; it is written from the encoded "
                  "consent rules (growth.owned) and has not been reviewed by a lawyer"))
    return out


def _check_disclosures(s: C.Surface) -> list[dict]:
    from ..visual import render_contract

    low = s.value.lower()
    out = []
    if render_contract.DISCLOSURE.lower() not in " ".join(low.replace("’", "'").split()):
        out.append(_f("DISCLOSURE_NO_RENDER_PHRASE", "fail",
                      "the store disclosure does not carry the render contract sentence the "
                      "images carry"))
    if not re.search(r"\bai\b", low):
        out.append(_f("DISCLOSURE_NO_AI", "fail", "the disclosure does not mention AI"))
    if "digital" not in low:
        out.append(_f("DISCLOSURE_NO_DIGITAL", "fail", "the disclosure does not say digital"))
    out.append(_f("DISCLOSURE_DESIGNER_CLAIM", "owner",
                  "gates.platform_policy says designs were 'directed and edited by the "
                  "designer'. That is true only if a person directs and edits each design; "
                  "owner to confirm who that is, or the wording changes at its source"))
    return out


def _check_faq(s: C.Surface) -> list[dict]:
    out = []
    keys = [f["key"] for f in s.value]
    if not keys or keys[0] != "sell_what_i_make":
        out.append(_f("FAQ_ORDER", "fail", "the finished-item question must come first"))
    for need in ("where_is_my_file", "can_i_get_a_refund", "was_ai_used", "skill_level",
                 "are_images_photos", "sample_made", "contact"):
        if need not in keys:
            out.append(_f("FAQ_MISSING", "fail", f"no FAQ answers {need}"))
    for f in s.value:
        if not str(f.get("answer", "")).strip():
            out.append(_f("FAQ_EMPTY", "fail", f"{f['key']} has no answer"))
    if len(keys) != len(set(keys)):
        out.append(_f("FAQ_DUPLICATE", "fail", "duplicate FAQ keys"))
    out.append(_f("FAQ_COUNT_LIMIT_UNVERIFIED", "unverified",
                  f"{len(keys)} entries; Etsy's FAQ entry limit is not on file"))
    return out


def _check_support_contact(s: C.Surface) -> list[dict]:
    out = []
    if "etsy messages" not in s.value.lower():
        out.append(_f("SUPPORT_NO_CHANNEL", "fail", "support text names no channel"))
    out.append(_f("SUPPORT_RESPONSE_TIME_UNDECIDED", "owner",
                  "no response-time commitment is decided, so none is shown. Owner: choose "
                  "one (e.g. two business days) or keep none"))
    return out


def _check_sections(s: C.Surface) -> list[dict]:
    from ..brand import storefront_preview as sp

    shown = [x for x in s.value if x["shown"]]
    out = []
    if not shown:
        out.append(_f("SECTIONS_NONE_POPULATED", "fail", "no section has a product in it"))
    if len(s.value) > limits.LIMITS["sections_count"].max_chars:
        out.append(_f("SECTIONS_TOO_MANY", "unverified", f"{len(s.value)} sections"))
    for x in s.value:
        if len(x["name"]) > sp.SECTION_LABEL_MAX:
            out.append(_f("SECTION_NAME_LONG", "unverified",
                          f"{x['name']!r} is longer than the assumed phone menu line"))
        if "_" in x["name"] or x["name"].lower() in ("pod", "misc", "other"):
            out.append(_f("SECTION_INTERNAL_NAME", "fail",
                          f"{x['name']!r} reads as an internal department name (F-237)"))
    return out


def _check_opening_grid(s: C.Surface) -> list[dict]:
    from ..launch import readiness as lr

    out = []
    products = s.value
    if not products:
        return [_f("GRID_EMPTY", "fail", "no Launch-0 product")]
    n = len(products)   # products, not sizes: a three-size basket is one product
    if n < lr.MIN_LISTINGS_TO_OPEN:
        out.append(_f("CATALOGUE_DEPTH", "owner",
                      f"{n} Launch-0 products (sizes are not counted as products) against "
                      f"launch.readiness.MIN_LISTINGS_TO_OPEN={lr.MIN_LISTINGS_TO_OPEN}. The "
                      f"threshold is not lowered; it is an open owner decision (D-FB-9)"))
    for p in products:
        for f in limits.check_length("listing_title", p["title"]):
            out.append({**f, "detail": f"{p['candidate']}: {f['detail']}"})
        for q, words in _POSITIONING.items():
            if q in p["qualifiers"] or p.get("etsy_category") == q:
                hits = [w for w in words if re.search(rf"\b{w}\b", p["title"], re.I)]
                if hits:
                    out.append(_f("TITLE_POSITIONING_CONFLICT", "owner",
                                  f"{p['candidate']}: positioned as {q} but titled "
                                  f"{p['title']!r} ({hits}); the CIR title "
                                  f"'{p['title'].split(' |')[0]}' and the plan title "
                                  f"{p['plan_title']!r} disagree. Owner naming decision"))
        plan_words = [w for w in re.findall(r"[A-Za-z]{4,}", p["plan_title"])
                      if w.lower() not in ("three", "sizes", "size")]
        missing = [w for w in plan_words
                   if not re.search(rf"\b{w[:-1] if w.endswith('s') else w}", p["title"], re.I)]
        if missing:
            out.append(_f("TITLE_PLAN_MISMATCH", "owner",
                          f"{p['candidate']}: the plan calls it {p['plan_title']!r}, the "
                          f"listing title (from the CIR title) says {p['title']!r}; "
                          f"{missing} missing. Owner naming decision"))
        if p["price_cad"] is None:
            out.append(_f("PRICE_UNKNOWN", "fail", f"{p['candidate']}: no price"))
        if not str(p["title_basis"]).startswith("drafted_listing"):
            out.append(_f("TITLE_NOT_DRAFTED", "unverified",
                          f"{p['candidate']}: title derived with the release chain's title "
                          f"builder; no drafted listing row was read"))
        if p.get("db_read_error"):
            out.append(_f("LISTINGS_UNREADABLE", "unverified", p["db_read_error"]))
    return out


def _check_trust(s: C.Surface) -> list[dict]:
    out = []
    if not s.value:
        return [_f("TRUST_NONE", "fail", "no trust signals")]
    for t in s.value:
        if t["kind"] not in C.TRUST_KINDS:
            out.append(_f("TRUST_KIND", "fail", f"{t['key']}: unknown kind {t['kind']!r}"))
        if not t["evidence"]:
            out.append(_f("TRUST_NO_EVIDENCE", "fail", f"{t['key']}: no evidence"))
        for path in t["evidence"]:
            if not (C.REPO_ROOT / path).exists():
                out.append(_f("TRUST_EVIDENCE_MISSING", "fail",
                              f"{t['key']}: evidence {path} does not exist"))
    return out


def _check_settings(s: C.Surface) -> list[dict]:
    return [_f("SETTINGS_OWNER_LOGIN", "owner",
               f"{len(s.value)} settings need the account holder signed in to Shop Manager; "
               f"none is entered by this system and their live state is UNKNOWN")]


def _check_search(s: C.Surface, surfaces) -> list[dict]:
    from ..brand import storefront

    out = [_f("SHOP_SEO", "fail", p) for p in storefront.check_shop_seo(_store_for_seo(surfaces))]
    out.append(_f("SEARCH_VISIBILITY_GATED", "gated",
                  "Etsy's Search Visibility page reads listings that are live; there are "
                  "none, so it cannot be read yet (commerce.search_visibility intake is ready)"))
    return out


def _check_support_readiness(s: C.Surface, surfaces) -> list[dict]:
    out = []
    try:
        from ..support import department

        if department.triage("I can't download my file") != department.DOWNLOAD:
            out.append(_f("SUPPORT_TRIAGE", "fail", "download question not triaged to "
                                                     "download support"))
    except Exception as exc:  # noqa: BLE001
        out.append(_f("SUPPORT_DEPARTMENT_UNAVAILABLE", "fail", f"{type(exc).__name__}"))
    if not str(surfaces["digital_sale_message"].value).strip():
        out.append(_f("NO_DIGITAL_SALE_MESSAGE", "fail", "blank digital sale message"))
    out.append(_f("MESSAGING_INTEGRATION_GATED", "gated",
                  "there is no Etsy messaging integration: replies are drafted and held "
                  "(support.department), never sent"))
    return out


def _check_brand_face(s: C.Surface) -> list[dict]:
    from . import brand_face

    return brand_face.check(s.value)


_CHECKS = {
    "brand_face": _check_brand_face,
    "shop_name": _check_shop_name, "icon": _check_icon, "banner": _check_banner,
    "announcement": _check_announcement, "about": _check_about,
    "policy_returns": _check_returns, "policy_delivery": _check_delivery,
    "policy_licence": _check_licence, "policy_privacy": _check_privacy,
    "disclosures": _check_disclosures, "faq": _check_faq,
    "support_contact": _check_support_contact, "sections": _check_sections,
    "opening_grid": _check_opening_grid, "trust_signals": _check_trust,
    "settings_checklist": _check_settings,
}
_CHECKS_WITH_ALL = {"shop_title": _check_shop_title, "search_readiness": _check_search,
                    "support_readiness": _check_support_readiness}


def _voice_findings(surfaces: dict[str, C.Surface]) -> list[dict]:
    out = []
    for s in surfaces.values():
        if s.customer_facing:
            out.extend(f for f in lint.lint(s.text(), surface=s.key) if f["kind"] == lint.VOICE)
    return out


def evaluate(surfaces: dict[str, C.Surface]) -> list[dict]:
    """One verdict per surface, with every finding that produced it."""
    rows = []
    for key, s in surfaces.items():
        findings: list[dict] = []
        if s.customer_facing and s.group not in ("merch",):
            text = s.text()
            if not text.strip():
                findings.append(_f("EMPTY", "fail", f"{s.label} is blank"))
        if s.customer_facing:
            findings.extend(f for f in lint.lint(s.text(), surface=key, voice=False))
        if s.limit_key and s.limit_key not in ("listing_title",) and isinstance(s.value, str):
            findings.extend(limits.check_length(s.limit_key, s.value))
        elif s.limit_key and s.key in ("faq", "support_contact"):
            vals = s.value if isinstance(s.value, list) else [{"answer": s.value}]
            longest = max((str(v.get("answer", "")) for v in vals), key=len, default="")
            findings.extend(limits.check_length(s.limit_key, longest))
        if key in _CHECKS:
            findings.extend(_CHECKS[key](s))
        if key in _CHECKS_WITH_ALL:
            findings.extend(_CHECKS_WITH_ALL[key](s, surfaces))
        if key == "voice":
            findings.extend(_voice_findings(surfaces))
        rows.append({"key": key, "label": s.label, "group": s.group,
                     "status": _status(findings), "findings": findings,
                     "entry": s.entry, "etsy_location": s.etsy_location,
                     "source": s.source, "entered_on_etsy": C.UNKNOWN,
                     "limit": limits.LIMITS[s.limit_key].to_dict() if s.limit_key else None})
    return rows


def rollup(rows: list[dict]) -> dict:
    counts = {st: 0 for st in ORDER}
    for r in rows:
        counts[r["status"]] += 1
    if counts[FAIL]:
        status = "BLOCKED"
    elif any(counts[st] for st in (NEEDS_OWNER, GATED, UNVERIFIED)):
        status = "DEGRADED"
    else:
        status = "OK"
    return {"status": status, "counts": counts,
            "owner_actions": [{"surface": r["key"], **f} for r in rows for f in r["findings"]
                              if f["severity"] == "owner"]}
