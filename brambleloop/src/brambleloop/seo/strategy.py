"""Launch-0 search strategy: query families, buyer-first titles, 13 tags, natural descriptions.

Wave-3 lane G, directive section 13. One listing per Launch-0 *product*:

- `nursery-nesting-baskets`  ONE listing, three sizes (small / medium / large) -- not three
  listings. The size words are licensed by the variant set (`facts.for_product`).
- `hexagon-coaster-set`      one listing, a set of four.
- `cloudline-baby-blanket`   one listing.

What this module is, and what it refuses to be:

1. **Matching, ranking, CTR and conversion are four problems, not one score.**
   `FUNNEL` names, per stage, what decides it, which levers this company controls before
   launch, and which signal will measure it after launch. A title or tag can only help
   *matching* directly. Ranking, CTR and conversion are measured later and are UNKNOWN now.
2. **Demand is never asserted.** Every query family carries `demand_basis`: `"modelled"`
   (the phrase is a hypothesis written by this department from the product's facts and the
   category's ordinary buyer phrasing) or `"measured"` only when a measured evidence row
   (Etsy Stats export, owner-read Marketplace Insights) exists for that phrase in the
   evidence store. There is no numeric demand anywhere in a modelled family; the
   `priority` is an ordinal judgement and is labelled as one.
3. **Every word is true.** Title, tags and description run through `seo.truth` against
   `facts.for_product` (the product's verified facts, union of what every size shares plus
   licensed product-record words). An untraceable word is a build failure, not a warning.
4. **No keyword stuffing.** The title repeats no content word; no stem holds more than 5 of
   13 tag slots (a stricter, stem-aware version of `commerce.portfolio.stuffing`).
5. **Category and attributes stay GATED.** Candidates are proposed from the repo's own
   category intent and the *buyer* path seen on Etsy's public site (UNVERIFIED); the seller
   `taxonomy_id` and the property ids come only from `seo.taxonomy` once the Etsy read
   happens. No id is written here.

Nothing here writes to Etsy or to the database. `plan(db=None)` is deterministic.
"""
from __future__ import annotations

import re
from collections import Counter

from . import constraints as C

STRATEGY_VERSION = "w3-seo-strategy-v1"
MAX_STEM_SLOTS = 5          # of 13 tag slots; stricter than portfolio.STUFFED_WORD_SHARE

# --------------------------------------------------------------------------------------------
# The funnel: four separate problems.

FUNNEL: dict[str, dict] = {
    "matching": {
        "question": "Is the listing eligible to appear for this query at all?",
        "decided_by": ["title", "tags", "category (taxonomy node)", "attributes",
                       "listing language"],
        "levers_now": ["truthful buyer-language title", "13 distinct truthful tags",
                       "deepest truthful category (GATED until the taxonomy read)",
                       "every applicable attribute set truthfully"],
        "signal_after_launch": "impressions per query (Etsy Stats search terms)",
        "status_now": "CONTROLLABLE (pre-launch work in this module)",
    },
    "ranking": {
        "question": "Among matched listings, where does Etsy place it?",
        "decided_by": ["Etsy's ranking (not public)", "listing quality / engagement",
                       "recency", "shop & customer-service factors (Search Visibility page; "
                       "UNVERIFIED summary)", "shopper context"],
        "levers_now": ["nothing here can claim a ranking effect before data exists"],
        "signal_after_launch": "impressions trend vs. listings matched; Search Visibility "
                               "recommendations recorded by the owner",
        "status_now": "UNKNOWN (no listing is live)",
    },
    "ctr": {
        "question": "When shown, is it clicked?",
        "decided_by": ["thumbnail (Visual lane H)", "first words of the title",
                       "price display", "badges/reviews (none yet)"],
        "levers_now": ["front-load the object + 'crochet pattern' in the first ~40 "
                       "characters (thumbnail crops the title)"],
        "signal_after_launch": "visits / impressions per listing (listing_outcomes)",
        "status_now": "UNKNOWN (no listing is live)",
    },
    "conversion": {
        "question": "When visited, is it favourited, carted, bought?",
        "decided_by": ["images", "description clarity", "price", "reviews", "trust"],
        "levers_now": ["natural description that answers size/yarn/skill/what's-included "
                       "first", "no unsupported claims"],
        "signal_after_launch": "favourites, carts, orders / visits (carts: no data source "
                               "in this repo yet)",
        "status_now": "UNKNOWN (no listing is live)",
    },
}

# --------------------------------------------------------------------------------------------
# Query families per product. Phrases are hypotheses (modelled), each must be truthful.
#
# intent:   object | object+format | attribute | use/room | construction | skill | deliverable
# role:     which tag/title slot strategy serves it -- never a demand number.
# priority: 1 (core) .. 3 (long tail); an ordinal judgement, `priority_basis` says so.

FAMILIES: dict[str, list[dict]] = {
    "nursery-nesting-baskets": [
        {"family": "object_core", "intent": "object+format", "priority": 1,
         "phrases": ["crochet basket", "basket pattern", "crochet basket pattern"]},
        {"family": "shape", "intent": "attribute", "priority": 1,
         "phrases": ["hexagon basket", "hexagonal storage"]},
        {"family": "set_sizes", "intent": "attribute", "priority": 1,
         "phrases": ["nesting baskets", "basket in 3 sizes"]},
        {"family": "room_use", "intent": "use/room", "priority": 2,
         "phrases": ["nursery storage", "nursery decor", "storage basket",
                     "crochet storage", "crochet home decor"]},
        {"family": "skill_construction", "intent": "skill", "priority": 3,
         "phrases": ["beginner crochet", "single crochet"]},
        {"family": "deliverable", "intent": "deliverable", "priority": 3,
         "phrases": ["pdf crochet pattern"]},
    ],
    "hexagon-coaster-set": [
        {"family": "object_core", "intent": "object+format", "priority": 1,
         "phrases": ["coaster pattern", "crochet coasters", "crochet coaster set"]},
        {"family": "shape", "intent": "attribute", "priority": 1,
         "phrases": ["hexagon coaster", "hexagon crochet", "hexagon pattern"]},
        {"family": "set_count", "intent": "attribute", "priority": 1,
         "phrases": ["coaster set", "set of 4 coasters"]},
        {"family": "room_use", "intent": "use/room", "priority": 2,
         "phrases": ["kitchen crochet", "kitchen decor", "crochet home decor"]},
        {"family": "material", "intent": "attribute", "priority": 2,
         "phrases": ["cotton crochet"]},
        {"family": "skill_construction", "intent": "skill", "priority": 3,
         "phrases": ["beginner crochet", "single crochet"]},
        {"family": "deliverable", "intent": "deliverable", "priority": 3,
         "phrases": ["pdf crochet pattern"]},
    ],
    "cloudline-baby-blanket": [
        {"family": "object_core", "intent": "object+format", "priority": 1,
         "phrases": ["baby blanket pattern", "crochet baby blanket"]},
        {"family": "texture_motif", "intent": "construction", "priority": 1,
         "phrases": ["textured blanket", "diamond blanket", "diamond lattice",
                     "textured crochet", "diamond crochet"]},
        {"family": "synonym_object", "intent": "object", "priority": 2,
         "phrases": ["crochet afghan", "baby afghan"]},
        {"family": "colour_pattern", "intent": "attribute", "priority": 2,
         "phrases": ["striped baby blanket", "two color crochet"]},
        {"family": "skill_construction", "intent": "skill", "priority": 3,
         "phrases": ["beginner crochet"]},
        {"family": "deliverable", "intent": "deliverable", "priority": 3,
         "phrases": ["pdf crochet pattern"]},
    ],
}

# The 13 tags chosen from the families (order = slot order). Chosen by hand from the families;
# the builder verifies each is in a family, true, within limits and not stuffed.
TAGS: dict[str, list[str]] = {
    "nursery-nesting-baskets": [
        "crochet basket", "basket pattern", "hexagon basket", "nesting baskets",
        "storage basket", "nursery storage", "nursery decor", "crochet storage",
        "crochet home decor", "hexagonal storage", "beginner crochet", "single crochet",
        "pdf crochet pattern"],
    "hexagon-coaster-set": [
        "coaster pattern", "crochet coasters", "hexagon coaster", "coaster set",
        "set of 4 coasters", "hexagon crochet", "hexagon pattern", "kitchen crochet",
        "kitchen decor", "cotton crochet", "beginner crochet", "single crochet",
        "pdf crochet pattern"],
    "cloudline-baby-blanket": [
        "baby blanket pattern", "crochet baby blanket", "textured blanket", "diamond blanket",
        "striped baby blanket", "crochet afghan", "baby afghan", "diamond lattice",
        "textured crochet", "diamond crochet", "two color crochet", "beginner crochet",
        "pdf crochet pattern"],
}

# Buyer-first titles: object + "crochet pattern" first (matching and CTR), then the
# differentiators a shopper filters by, then the deliverable. Under 140, no repeated word.
TITLES: dict[str, str] = {
    "nursery-nesting-baskets": ("Hexagon Nesting Baskets Crochet Pattern in 3 Sizes | "
                                "Nursery Storage | Worsted Cotton | PDF with Chart, "
                                "US and UK Terms"),
    "hexagon-coaster-set": ("Hexagon Coaster Crochet Pattern, Set of 4 | DK Cotton | "
                            "Confident Beginner | PDF with Chart, US and UK Terms"),
    "cloudline-baby-blanket": ("Textured Baby Blanket Crochet Pattern | Cloudline Diamond "
                               "Lattice in Two Colors | PDF with Chart, US and UK Terms"),
}

# Category candidates. `intent` is the repo's own (products.launch0 ListingIdentity); the buyer
# path is what Etsy's public site shows (UNVERIFIED); the seller node is UNREAD.
BUYER_PATH = C.get("crochet_pattern_buyer_path").value


def _stem(w: str) -> str:
    from .facts import stem

    return stem(w)


def stem_slot_counts(tags: list[str]) -> Counter:
    """How many tag slots each content stem occupies (furniture words excluded)."""
    from ..commerce.intent import MARKETPLACE_FURNITURE
    from .facts import STOPWORDS, words

    c: Counter = Counter()
    for t in tags:
        for s in {_stem(w) for w in words(t)
                  if w not in MARKETPLACE_FURNITURE and w not in STOPWORDS}:
            c[s] += 1
    return c


def title_repeats(title: str) -> list[str]:
    from .facts import STOPWORDS, words

    c = Counter(_stem(w) for w in words(title) if w not in STOPWORDS and len(w) > 2
                and not w.isdigit())
    return sorted(w for w, n in c.items() if n > 1)


def _tag_charset_problems(tag: str) -> list[str]:
    out = []
    if re.search(r"[^\w\s\-'™©®]|_", tag):
        out.append(f"TAG_CHARSET: {tag!r} has a character outside Etsy's tag set "
                   f"({C.get('tag_charset').status})")
    if tag[:1] in "-'":
        out.append(f"TAG_LEADING_SYMBOL: {tag!r} starts with {tag[0]!r} "
                   f"({C.get('tag_no_leading_symbol').status})")
    return out


def _description(facts, cand) -> dict:
    """A natural description: what you make, what's included, sizes, yarn, skill. No hype."""
    from ..commerce import seo as seo_mod
    from ..publish.difficulty import difficulty as _difficulty  # noqa: F401 (facts carry it)

    cir = facts.cir
    hook = getattr(getattr(cir, "gauge", None), "hook_mm", None)
    yarn = sorted(set(facts.materials))
    obj = {"nursery-nesting-baskets": "a set of three hexagon nesting baskets",
           "hexagon-coaster-set": "a set of four hexagon coasters",
           "cloudline-baby-blanket": "the Cloudline baby blanket"}.get(cand.slug,
                                                                      cand.title.lower())
    lead = {
        "nursery-nesting-baskets": (
            "Make a set of three hexagon baskets that nest inside each other: one pattern, "
            "small, medium and large, worked in the round from a flat base up into straight "
            "walls, for nursery and everyday storage."),
        "hexagon-coaster-set": (
            "Make a set of four hexagon coasters, worked in joined rounds with a contrast "
            "round near the edge. A small, satisfying cotton project for your own table or "
            "to make as a gift."),
        "cloudline-baby-blanket": (
            "Make the Cloudline baby blanket: a raised diamond lattice of double crochet "
            "over a single crochet ground, in two colors that change every two rows, with "
            "plain cream rows at each end."),
    }.get(cand.slug, f"Make {obj}.")
    labels = [lab.split(": ", 1)[1] if len(facts.variant_labels) == 1 else lab
              for lab in facts.variant_labels]
    sizes = [f"- {lab}" for lab in labels]
    stitch_words = []
    for code in facts.stitches:
        try:
            from ..cir.stitches import get as stitch_get

            st = stitch_get(code)
            if code == "inc":
                continue          # an increase is a technique, not a stitch to list
            stitch_words.append(f"{st.name_us} ({code})")
        except Exception:  # noqa: BLE001
            stitch_words.append(code)
    paras = [
        lead,
        "What you get: a digital crochet pattern (PDF) with written instructions and a "
        "chart, in US and UK terms. This is a pattern to make the item yourself; no finished "
        "item is shipped.",
        ("Finished sizes" if len(sizes) > 1 else "Finished size") + " (calculated from the "
        "stated gauge, so your own tension will change "
        + ("them" if len(sizes) > 1 else "it") + "):\n" + "\n".join(sizes),
        f"Yarn: {', '.join(yarn)}." + (f" Hook: {hook:g} mm." if hook else "")
        + f" Skill level: {facts.difficulty}. Stitches: "
        + ", ".join(stitch_words) + " (US terms; the UK version uses UK terms).",
    ]
    text = "\n\n".join(paras)
    findings = []
    hit = seo_mod._UNSUPPORTABLE.search(text)
    if hit:
        findings.append(f"DESCRIPTION_UNSUPPORTABLE: {hit.group(0)!r}")
    from .truth import _policy_claims

    findings += [f"DESCRIPTION_POLICY: {w}" for w in _policy_claims(text)]
    if re.search(r"\b(tested|test[- ]?knit|test[- ]?crochet|photograph(ed)?|hand[- ]?made "
                 r"by)\b", text, re.I):
        findings.append("DESCRIPTION_UNSUPPORTED: claims testing/photography/handmaking "
                        "that no evidence supports")
    required_blocks = [{"block": "disclosure", "owner": "lanes C/I + owner approval",
                        "status": "PENDING",
                        "why": f"Etsy AI-disclosure rule ({C.get('ai_disclosure').status}); "
                               "wording is not an SEO decision"}]
    for key in getattr(cand, "committed_statements", ()) or ():
        required_blocks.append({"block": f"childrens:{key}",
                                "owner": "listing chain (products.childrens statements)",
                                "status": "PENDING", "why": "committed children's statement"})
    return {"text": text, "chars": len(text), "first_160": text[:160],
            "findings": findings, "required_blocks": required_blocks,
            "final": False,
            "note": ("SEO body only; the listing chain appends the disclosure and committed "
                     "statement blocks. Not final until those exist and the owner approves.")}


def _attributes(facts) -> dict:
    """Attribute candidates (GATED): value proposals keyed by meaning, no property ids."""
    from ..commerce import search as search_mod

    attrs = search_mod.listing_attributes(category=facts.category, difficulty=facts.difficulty,
                                          colors=list(facts.colors), season=facts.season)
    problems = (search_mod.check_attributes(attrs)
                + search_mod.attribute_truth(attrs, difficulty=facts.difficulty,
                                             colors=list(facts.colors), season=facts.season))
    paren = [f"ATTR_PARENTHESES: {k}={v!r}" for k, v in attrs.items()
             if isinstance(v, str) and re.search(r"[()]", v)]
    return {"values": attrs, "problems": problems + paren,
            "status": "GATED(etsy_api)",
            "why": ("property ids, required flags and allowed values exist only in "
                    "getPropertiesByTaxonomyId for the chosen node, which is unread; "
                    f"({C.get('taxonomy_property_shape').status} that the shape is "
                    "is_required/possible_values/max_values_allowed)"),
            "colour_families": list(facts.colour_families)}


def _measured_phrases(db) -> dict[str, dict]:
    if db is None:
        return {}
    try:
        from . import evidence as ev_mod

        ev = ev_mod.by_phrase(ev_mod.all_rows(db))
        return {p: e for p, e in ev.items() if e.get("measured")}
    except Exception:  # noqa: BLE001 - no tables: nothing is measured
        return {}


def build(cand, facts, *, db=None, competitors: list[str] | None = None,
          taxonomy_row: dict | None = None) -> dict:
    """The full strategy for one Launch-0 product. Deterministic; `ok` only if every check
    passes."""
    from . import truth

    slug = cand.slug
    competitors = [] if competitors is None else competitors
    measured = _measured_phrases(db)
    blocking: list[str] = []

    fams = []
    family_phrases: set[str] = set()
    for fam in FAMILIES.get(slug, []):
        rows = []
        for p in fam["phrases"]:
            v = truth.check_term(p, facts, competitors=competitors)
            m = measured.get(p)
            rows.append({"phrase": p, "true": v.ok, "findings": v.findings,
                         "demand_basis": "measured" if m else "modelled",
                         "measured": dict(m["measured"]) if m else {},
                         "fits_tag": len(p) <= C.get("tag_max_chars").value})
            if not v.ok:
                blocking.append(f"FAMILY_PHRASE_UNTRUE: {fam['family']}: {p!r}: "
                                f"{v.findings[:1]}")
            family_phrases.add(p)
        fams.append({**{k: fam[k] for k in ("family", "intent", "priority")},
                     "priority_basis": "ordinal judgement (modelled), not demand",
                     "demand_basis": ("measured" if any(r["demand_basis"] == "measured"
                                                        for r in rows) else "modelled"),
                     "phrases": rows})

    title = TITLES[slug]
    tags = list(TAGS[slug])
    validation = truth.validate_listing(title, tags, facts, competitors=competitors)
    blocking += validation["blocking"]
    for vf in getattr(facts, "variant_facts", [])[1:]:
        # every size's own CIR gates (product type, colourwork) over the shared title/tags
        from ..gates import first_customer as fc

        for f in fc.product_type_findings(vf.cir, title=title, tags=tags):
            blocking.append(f"VARIANT {vf.slug}: TERM_MISLEADING: {f}")
        if vf.twin is not None:
            for f in fc.colourwork_findings(vf.cir, vf.twin, title=title, tags=tags):
                blocking.append(f"VARIANT {vf.slug}: TERM_MISLEADING: {f}")
    if len(tags) != C.get("tag_max_count").value:
        blocking.append(f"TAG_SLOTS: {len(tags)} of {C.get('tag_max_count').value} used")
    for t in tags:
        blocking += _tag_charset_problems(t)
        if t not in family_phrases:
            blocking.append(f"TAG_NOT_IN_FAMILY: {t!r} has no query family")
    over = {s: n for s, n in stem_slot_counts(tags).items() if n > MAX_STEM_SLOTS}
    if over:
        blocking.append(f"TAG_STEM_STUFFED: {over} (max {MAX_STEM_SLOTS} of 13)")
    rep = title_repeats(title)
    if rep:
        blocking.append(f"TITLE_REPEATS: {rep}")
    if title.count("+") + title.count("%") + title.count(":") + title.count("&") and any(
            title.count(ch) > 1 for ch in "%:&+"):
        blocking.append("TITLE_CHARSET: one of % : & + used twice (VERIFIED rule)")

    desc = _description(facts, cand)
    blocking += desc["findings"]
    attrs = _attributes(facts)
    blocking += [f"ATTRIBUTE: {p}" for p in attrs["problems"]]

    tax = taxonomy_row or {}
    category = {
        "intent": facts.category,
        "buyer_path_candidate": list(BUYER_PATH),
        "buyer_path_status": C.get("crochet_pattern_buyer_path").status,
        "seller_taxonomy_id": tax.get("taxonomy_id"),
        "seller_path": tax.get("path") or [],
        "status": tax.get("status", "GATED(etsy_api)"),
        "why": tax.get("why", "no Etsy-read seller taxonomy snapshot"),
        "rule": "descend to the deepest seller node naming the object "
                "(commerce.category.choose); never a remembered id",
    }
    tag_basis = Counter("measured" if t in measured else "modelled" for t in tags)
    return {
        "version": STRATEGY_VERSION, "slug": slug, "listing_unit": "product",
        "variants": list(facts.variant_labels), "writes_to_etsy": False,
        "ok": not blocking, "blocking": blocking,
        "title": title, "title_chars": len(title),
        "title_front_40": title[:40],
        "tags": tags, "tag_basis_counts": dict(tag_basis),
        "tag_stem_slots": dict(stem_slot_counts(tags).most_common(6)),
        "families": fams, "description": desc, "attributes": attrs, "category": category,
        "styles": {"value": [], "why": "styles are optional (VERIFIED: up to two, 45 chars); "
                                       "no style word is a verified product fact yet"},
        "funnel": {k: {"status_now": v["status_now"], "levers_now": v["levers_now"]}
                   for k, v in FUNNEL.items()},
        "limits": C.working_limits(),
        "demand_statement": ("no phrase here has measured demand" if not tag_basis.get(
            "measured") else f"{tag_basis['measured']} tag(s) have measured evidence"),
    }


def plan(db=None, *, competitors: list[str] | None = None) -> dict:
    """The Launch-0 strategy for all three products, with the taxonomy readiness joined in."""
    from ..products import launch0 as L
    from . import facts as facts_mod

    tax_by: dict[str, dict] = {}
    if db is not None:
        try:
            from . import taxonomy

            for r in taxonomy.readiness(db):
                tax_by.setdefault(r.get("candidate"), r)
        except Exception:  # noqa: BLE001
            pass
    products = []
    for slug in L.LAUNCH0_SLUGS:
        cand = L.candidate(slug)
        f = facts_mod.for_product(cand)
        products.append(build(cand, f, db=db, competitors=competitors,
                              taxonomy_row=tax_by.get(slug)))
    return {"version": STRATEGY_VERSION, "products": products,
            "ok": all(p["ok"] for p in products),
            "funnel": FUNNEL, "constraints": C.snapshot()["counts"],
            "unverified_limits": [k for k, v in C.working_limits().items()
                                  if v["status"] != C.VERIFIED],
            "writes_to_etsy": False}
