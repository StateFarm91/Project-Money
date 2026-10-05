"""Storefront Director (Master Plan section 6).

Section 6 gives this role a specific inventory: banner, icon, About, policies, sections,
announcement, thumbnails and grid coherence. Those are the parts of a shop a customer reads
before they trust it, and on Etsy they are also the parts a new shop most obviously gets
wrong -- an empty About, no policies, and a section list invented one listing at a time.

Everything here is drafted, never published. Shadow mode means the storefront is prepared and
held, so that on the day publishing is enabled the shop opens complete rather than accreting
in public.

The policies matter beyond tidiness. A digital pattern is non-returnable, and Canadian
consumer-protection rules expect that to be disclosed plainly before purchase rather than
discovered afterwards. So the refund policy states it in the first sentence and then says
what we will actually do instead, which is fix the pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..commerce import shop_package
from . import bible

SHOP_NAME = "Brambleloop Studio"

ANNOUNCEMENT_MAX = 160
ABOUT_MIN = 400
# Etsy's shop story ("About") field cap, applied when seasonal copy is appended to it.
ABOUT_MAX = 5000


@dataclass
class Section:
    name: str
    slug: str
    categories: tuple[str, ...]


# Sections are declared up front rather than accumulated. A shop whose sections were invented
# one listing at a time reads as a stall; a shop with a stated shape reads as a studio.
SECTIONS: list[Section] = [
    Section("Blankets & Throws", "blankets", ("mosaic_blanket", "blanket", "graphghan")),
    Section("Seasonal & Holiday", "seasonal",
            ("seasonal_decor", "ornament", "stocking", "tree_skirt")),
    Section("Home & Table", "home", ("runner", "placemat", "coaster", "basket", "pillow",
                                     "wall_decor", "flower")),
    Section("Baby & Nursery", "baby", ("baby", "nursery")),
    Section("To Wear", "wear", ("garment", "hat", "scarf", "shawl", "bag")),
    Section("Collections & Bundles", "collections", ()),
]


def section_for(category: str, is_bundle: bool = False) -> str:
    if is_bundle:
        return "collections"
    for s in SECTIONS:
        if category in s.categories:
            return s.slug
    return "home"


ABOUT = f"""{SHOP_NAME} makes crochet patterns the way software gets made: written once,
then checked by a machine before anyone is asked to pay for them.

Every pattern here starts as a formal, machine-readable description of the fabric — every
stitch, every row, every colour change. A compiler then works through it row by row and
checks that the counts actually add up, that repeats divide evenly, and that what the chart
shows is what the words say. A second program reads only the finished customer pattern, with
no access to the original, and reconstructs it from scratch; if the two disagree anywhere,
the pattern does not ship.

That sounds like a strange amount of machinery for a blanket. It exists because of what goes
wrong with crochet patterns: you are thirty hours into a throw when a row stops working, and
there is no way to tell whether the mistake is yours or the designer's. We would rather spend
the effort up front than have you find out at row 94.

The designs are developed with AI assistance and the arithmetic is verified by code. Neither
of those is a substitute for the other, and we say which is which.

If something in one of our patterns does not add up, tell us. We fix the pattern itself, put
out a corrected version, and send it to everyone who bought it — rather than answering your
question and leaving the next person to find the same problem."""

# The policies are not written here any more.
#
# They were, and all five of them were prose somebody typed once. The licence was the one
# that mattered: it said "sell the items you make from it", with no limit, while
# `commerce.terms` had decided that finished items may be sold "by individual makers and
# small businesses, not manufactured at scale" and `commerce.seo`'s description block said a
# third thing. Three answers to the most-asked question in the craft-pattern market, in one
# repository, before a single sale -- which is requirement 40's drift failure, arriving
# exactly the way #40 says it arrives: written at different times by different parts of the
# system, and never read side by side.
#
# `commerce.shop_package` now renders all of them from the decisions that own them, so the
# storefront shows what was decided rather than what was remembered. The name is kept because
# the shop still has policies; what changed is where they come from.
POLICIES: dict[str, str] = shop_package.policies()

ANNOUNCEMENT_TEMPLATES: dict[str, str] = {
    "Christmas": ("Christmas blankets take real hours — this is the month to start. "
                  "Every pattern is compiler-checked row by row."),
    "Halloween": "Quick autumn makes, checked row by row before they ship.",
    "Thanksgiving (CA)": "Table pieces for the long weekend, with every stitch count verified.",
    "evergreen": ("Crochet patterns with the arithmetic checked by machine before release. "
                  "Charts and written instructions always agree."),
}


@dataclass
class Storefront:
    shop_name: str
    announcement: str
    about: str
    policies: dict[str, str]
    sections: list[dict]
    banner_brief: str
    icon_brief: str
    problems: list[str] = field(default_factory=list)
    # C-80 defect 18 (#131): the collection a live takeover pins to the front of the shop,
    # and the seasonal copy it added to About -- rendered here, where the launch check reads.
    featured_collection: str | None = None
    seasonal_copy: str | None = None
    # F-236: the shop title Etsy shows under the shop name (the "tagline"). Owned by
    # `commerce.shop_package.shop_text`, carried here so the storefront check can read it.
    tagline: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"shop_name": self.shop_name, "announcement": self.announcement,
                "about": self.about, "policies": dict(self.policies),
                "sections": list(self.sections), "banner_brief": self.banner_brief,
                "icon_brief": self.icon_brief, "problems": list(self.problems),
                "featured_collection": self.featured_collection,
                "seasonal_copy": self.seasonal_copy, "tagline": self.tagline}


# The banner's composition as data, so the pre-launch preview (`brand.storefront_preview`)
# measures the same layout the brief asks for. The wordmark sits centred, inside the middle
# half of the frame: a phone crops a wide banner towards its centre, and a wordmark composed
# "at left" is the part a phone cuts off (F-239).
BANNER_SIZE = (1600, 400)
BANNER_WORDMARK_BOX = (520, 150, 1080, 250)     # x0, y0, x1, y1 in banner pixels
ICON_SIZE = (500, 500)


def _banner_brief() -> str:
    x0, y0, x1, y1 = BANNER_WORDMARK_BOX
    return (
        f"Shop banner, {BANNER_SIZE[0]}x{BANNER_SIZE[1]}. Flat-lay of finished crochet fabric "
        f"in {bible.PALETTE['pine']} and {bible.PALETTE['cream']} on "
        f"{bible.LIGHTING['background']}, {bible.LIGHTING['direction']}. Wordmark "
        f"'{SHOP_NAME.upper()}' set in {bible.TYPOGRAPHY['display']}, centred inside the box "
        f"x {x0}-{x1}, y {y0}-{y1} so a phone's centre crop keeps it, generous space around "
        f"it. No collage, no stock gloss, nothing in the outer "
        f"{int(bible.CROP_RULES['safe_margin_pct'] * 100)}% of the frame.")


def _icon_brief() -> str:
    return (
        f"Shop icon, {ICON_SIZE[0]}x{ICON_SIZE[1]}. A single loop-and-bramble mark in {bible.PALETTE['pine']} on "
        f"{bible.PALETTE['cream']}, centred, heavy enough to read at 40px. No text — an icon "
        f"with a shop name in it is illegible at the size it is actually shown.")


def build_storefront(season: str | None = None, *, db=None, today=None) -> Storefront:
    """The drafted storefront; with `db`, carrying any takeover the executor applied (#131).

    Every APPLIED surface that has a place on the drafted storefront is rendered: the banner
    replaces the announcement, `shop_content` is appended to About as seasonal copy, and
    `featured_collection` is the collection pinned to the front (C-80 defect 18).
    """
    announcement = ANNOUNCEMENT_TEMPLATES.get(season or "", ANNOUNCEMENT_TEMPLATES["evergreen"])
    about, featured, seasonal_copy = ABOUT, None, None
    if db is not None:
        from .takeover import active

        live = active(db, today=today)
        if live.get("banner"):
            announcement = live["banner"]["change"]
        if live.get("shop_content"):
            seasonal_copy = live["shop_content"]["change"]
            about = f"{ABOUT}\n\n{seasonal_copy}"
        if live.get("featured_collection"):
            featured = live["featured_collection"]["change"]
    store = Storefront(
        shop_name=SHOP_NAME,
        announcement=announcement,
        about=about,
        policies=dict(POLICIES),
        sections=[{"name": s.name, "slug": s.slug, "categories": list(s.categories)}
                  for s in SECTIONS],
        banner_brief=_banner_brief(),
        icon_brief=_icon_brief(),
        featured_collection=featured,
        seasonal_copy=seasonal_copy,
        tagline=shop_package.shop_text()["title"],
    )
    store.problems = check_storefront(store)
    return store


def check_storefront(store: Storefront) -> list[str]:
    """Everything a shopper checks before trusting a new shop, checked before they do."""
    problems: list[str] = []
    if len(store.announcement) > ANNOUNCEMENT_MAX:
        problems.append(f"STORE_ANNOUNCEMENT_TOO_LONG: {len(store.announcement)} characters")
    if not store.announcement.strip():
        problems.append("STORE_NO_ANNOUNCEMENT")
    if len(store.about) < ABOUT_MIN:
        problems.append(f"STORE_ABOUT_THIN: {len(store.about)} characters; an empty About is "
                        f"the first thing a cautious buyer notices")
    # The section list is the package's, not a copy of it. A second list is a second answer
    # to "which policies does this shop have", and the AI disclosure is exactly the section
    # a hand-maintained list forgets: it was not a policy section until Etsy made it one.
    for required in shop_package.POLICY_SECTIONS:
        if not store.policies.get(required, "").strip():
            problems.append(f"STORE_POLICY_MISSING: {required}")
    returns = store.policies.get("returns", "").lower()
    if "cannot be returned" not in returns:
        problems.append(
            "STORE_RETURNS_UNCLEAR: a digital pattern is non-returnable and that has to be "
            "said plainly before purchase, not discovered after it")
    if not store.sections:
        problems.append("STORE_NO_SECTIONS")
    slugs = [s["slug"] for s in store.sections]
    if len(slugs) != len(set(slugs)):
        problems.append("STORE_DUPLICATE_SECTIONS")
    if len(store.sections) > 20:
        problems.append(f"STORE_TOO_MANY_SECTIONS: {len(store.sections)} exceeds Etsy's 20")
    for brief, name in ((store.banner_brief, "banner"), (store.icon_brief, "icon")):
        if not brief.strip():
            problems.append(f"STORE_NO_{name.upper()}_BRIEF")
    if store.featured_collection is not None and not store.featured_collection.strip():
        problems.append("STORE_FEATURED_COLLECTION_EMPTY: a pinned collection that names "
                        "nothing is a front page pointing at a blank")
    if store.seasonal_copy is not None and len(store.about) > ABOUT_MAX:
        problems.append(f"STORE_ABOUT_TOO_LONG: {len(store.about)} characters with the "
                        f"seasonal copy; Etsy's About is capped and a truncated About is "
                        f"a truncated sentence")
    # F-236: the shop's own search surface -- buyer category words present, nothing stuffed.
    problems.extend(check_shop_seo(store))
    # F-240: the public identity the storefront shows, against the seller-identity record.
    from . import seller_identity

    problems.extend(seller_identity.check_identity(shop_name=store.shop_name))
    return problems


# ---- F-236: the shop SEO surface ---------------------------------------------------------
#
# The tagline (Etsy's shop title) and the About are the only shop-level text a search engine
# reads. They have to say what the shop sells in the words a buyer types -- the category words
# come from `commerce.intent`'s buyer vocabulary, not from a list kept here -- and they must
# not reach for coverage by repeating those words, which is the shop-level form of the
# stuffing `commerce.portfolio.stuffing` refuses in a listing.

CATEGORY_WORDS: tuple[str, ...] = ("crochet", "pattern")
# Above this share of the About's words, one search keyword is being repeated for coverage
# rather than used to describe the shop.
ABOUT_KEYWORD_MAX_SHARE = 0.05
# Above this share of its words, a tagline or announcement is a keyword list, not a line.
TAGLINE_KEYWORD_MAX_SHARE = 0.6
_STOP = frozenset({"the", "and", "with", "for", "that", "this", "your", "our", "from",
                   "new", "size", "sizes", "includes", "included"})


def _search_words() -> frozenset[str]:
    from ..commerce.intent import BUYER_QUALIFIERS, MARKETPLACE_FURNITURE

    return frozenset((BUYER_QUALIFIERS | MARKETPLACE_FURNITURE) - _STOP)


def _words(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def check_shop_seo(store: Storefront) -> list[str]:
    """Category words a buyer types are present; nothing is stuffed (F-236)."""
    from collections import Counter

    from ..commerce.intent import BUYER_QUALIFIERS

    if not set(CATEGORY_WORDS) <= BUYER_QUALIFIERS:  # pragma: no cover - vocabulary drift
        raise RuntimeError(f"{CATEGORY_WORDS} are no longer buyer words in commerce.intent")
    vocab = {_stem(w) for w in _search_words()}
    problems: list[str] = []
    for name, text in (("tagline", store.tagline), ("about", store.about)):
        stems = {_stem(w) for w in _words(text)}
        missing = [w for w in CATEGORY_WORDS if w not in stems]
        if missing:
            problems.append(f"STORE_SEO_CATEGORY_SILENT: the {name} never says {missing}; a "
                            f"shop that does not name its category in buyer words is "
                            f"invisible to the search that would find it")
    # Stuffing in the short fields. The tagline is a title, so it takes the title rule of
    # `commerce.portfolio.stuffing` (a word over three letters repeated); the announcement is
    # one or two sentences, where naming the occasion twice is ordinary, so it is held only to
    # not being a keyword list.
    for name, text in (("tagline", store.tagline), ("announcement", store.announcement)):
        words = _words(text)
        if name == "tagline":
            repeated = sorted(w for w, n in Counter(_stem(x) for x in words).items()
                              if n > 1 and len(w) > 3)
            if repeated:
                problems.append(f"STORE_SEO_STUFFED: the tagline repeats {repeated}")
        if words:
            share = sum(1 for w in words if _stem(w) in vocab) / len(words)
            if share > TAGLINE_KEYWORD_MAX_SHARE:
                problems.append(f"STORE_SEO_KEYWORD_LIST: {share:.0%} of the {name} is "
                                f"search keywords; it reads as a list, not a sentence")
    words = [_stem(w) for w in _words(store.about)]
    if words:
        counts = Counter(w for w in words if w in vocab)
        for word, n in counts.most_common(3):
            if n / len(words) > ABOUT_KEYWORD_MAX_SHARE:
                problems.append(f"STORE_SEO_STUFFED: {word!r} is {n / len(words):.1%} of the "
                                f"About's words (cap {ABOUT_KEYWORD_MAX_SHARE:.0%})")
    for line in (store.about or "").splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) >= 6 and all(len(p.split()) <= 3 for p in parts):
            problems.append("STORE_SEO_KEYWORD_LIST: the About carries a comma-separated "
                            "keyword line")
            break
    return problems


# ---- F-238: the opening grid ------------------------------------------------------------
#
# The first screen of the shop is a merchandising decision, not the order rows happened to be
# inserted in. Only launch-cleared products may stand in it (`app.dashboard_truth`'s four
# criteria, and the legacy rule `publish.eligibility.legacy_status` enforces at publish);
# the active seasonal takeover's products go first; then strongest first, on measured sales
# where there are any and on the opportunity prior otherwise, each tile saying which; and the
# visible window must show more than one rung of the price ladder when the catalogue has
# more than one. `bible.check_grid_coherence` then judges the visible window as one shop.

OPENING_GRID_VISIBLE = 6          # the first screen on desktop; a phone shows the first four
MEASURED_STRENGTH = "measured"
PRIOR_STRENGTH = "prior"
UNMEASURED_STRENGTH = "UNMEASURED"


def price_tier(price_cad: float, *, is_bundle: bool = False) -> str:
    """The ladder rung a price sits on, read from `commerce.ladder`'s own typical bands."""
    from ..commerce import ladder

    if is_bundle:
        return ladder.FLAGSHIP if price_cad > ladder.BY_KEY[ladder.MINI].typical_cad[1] \
            else ladder.MINI
    for key in (ladder.ENTRY, ladder.PREMIUM, ladder.MINI):
        if price_cad <= ladder.BY_KEY[key].typical_cad[1]:
            return key
    return ladder.FLAGSHIP


def _palette_of(slug: str) -> dict:
    from ..products.builder import for_slug
    from ..visual.render_verification import authoritative_cir

    cir = for_slug(slug) or authoritative_cir(slug)
    return dict(getattr(cir, "colors", None) or {})


def opening_grid(db, *, today=None, inventory: dict | None = None) -> dict:
    """The shop's first screen: launch-cleared only, season first, strongest first, laddered."""
    from datetime import date as _date

    from sqlalchemy import func, select

    from ..core.models import (
        Listing, ListingAsset, Order, PatternVersion, Product,
    )
    from ..publish.eligibility import legacy_status
    from ..radar.opportunity import score_concept
    from ..runtime.pipeline import _seed_for
    from .takeover import active

    today = today or _date.today()
    if inventory is None:
        from ..app.dashboard_truth import launch_inventory

        inventory = launch_inventory(db)
    cleared = set(inventory.get("cleared_slugs") or [])
    failing = {r["slug"]: r.get("failing") for r in inventory.get("products") or []}
    events = sorted({v["event"] for v in active(db, today=today).values() if v.get("event")})

    with db.session() as s:
        listings = [l for l in s.scalars(select(Listing).where(Listing.state != "withdrawn")
                                         .order_by(Listing.product_slug, Listing.id))]
        certs = {}
        for slug, pv in s.execute(select(Product.slug, PatternVersion)
                                  .join(PatternVersion, PatternVersion.product_id == Product.id)
                                  .where(PatternVersion.certified.is_(True))):
            certs[(slug, pv.version)] = dict(pv.certificate or {})
        orders = dict(s.execute(select(Order.product_slug, func.count())
                                .group_by(Order.product_slug)).all())
        heroes = {(a.product_slug, a.version): a.asset_class
                  for a in s.scalars(select(ListingAsset).where(ListingAsset.position == 1))}
        for l in listings:
            s.expunge(l)

    tiles, excluded = [], []
    for l in listings:
        slug = l.product_slug
        if slug not in cleared:
            excluded.append({"slug": slug, "version": l.version,
                             "why": f"not launch-cleared: failing {failing.get(slug) or 'unknown'}"})
            continue
        legacy = legacy_status(slug, certs.get((slug, l.version)))
        if not legacy["cleared"]:
            excluded.append({"slug": slug, "version": l.version,
                             "why": f"legacy filler: {legacy['why']}"})
            continue
        seed = _seed_for(slug)
        if orders.get(slug):
            basis, value = MEASURED_STRENGTH, float(orders[slug])
        elif seed is not None:
            basis, value = PRIOR_STRENGTH, float(score_concept(seed, today).score)
        else:
            basis, value = UNMEASURED_STRENGTH, None
        season = seed.season if seed else None
        tiles.append({
            "slug": slug, "version": l.version, "title": l.title,
            "price_cad": l.price_cad,
            "tier": price_tier(l.price_cad, is_bundle=bool(seed and seed.is_bundle)),
            "season": season, "seasonal_now": bool(season and season in events),
            "strength": {"basis": basis, "value": value},
            "section": section_for(seed.category if seed else "", bool(seed and seed.is_bundle)),
            "hero_class": heroes.get((slug, l.version)) or "",
            "palette": _palette_of(slug)})

    rank = {MEASURED_STRENGTH: 0, PRIOR_STRENGTH: 1, UNMEASURED_STRENGTH: 2}
    tiles.sort(key=lambda t: (not t["seasonal_now"], rank[t["strength"]["basis"]],
                              -(t["strength"]["value"] or 0.0), t["slug"]))

    # The price ladder has to be visible in the first screen: promote the strongest product of
    # a rung the window is missing into the window's last slot, never past a seasonal tile.
    tiers_all = {t["tier"] for t in tiles}
    window = tiles[:OPENING_GRID_VISIBLE]
    promoted = []
    if len(tiers_all) >= 2 and len({t["tier"] for t in window}) < 2 and window:
        rest = tiles[OPENING_GRID_VISIBLE:]
        other = next((t for t in rest if t["tier"] not in {w["tier"] for w in window}), None)
        if other is not None:
            slot = len(window) - 1
            if not window[slot]["seasonal_now"] or all(w["seasonal_now"] for w in window):
                tiles.remove(other)
                tiles.insert(slot, other)
                promoted.append(other["slug"])
    window = tiles[:OPENING_GRID_VISIBLE]

    problems: list[str] = []
    if not tiles:
        problems.append("OPENING_GRID_EMPTY: no launch-cleared product has a listing, so the "
                        "shop's first screen would be blank")
    if len(tiers_all) >= 2 and len({t["tier"] for t in window}) < 2:
        problems.append("OPENING_GRID_LADDER_FLAT: the first screen shows one price rung "
                        "while the catalogue has several")
    seasonal_available = [t["slug"] for t in tiles if t["seasonal_now"]]
    if seasonal_available and not any(t["seasonal_now"] for t in window):
        problems.append("OPENING_GRID_SEASON_HIDDEN: a takeover is live and its products are "
                        "below the fold")
    if any(t["slug"] not in cleared for t in window):  # pragma: no cover - by construction
        problems.append("OPENING_GRID_FILLER: an uncleared product reached the first screen")

    coherence: dict
    known = [t for t in window if t["palette"] and t["hero_class"]]
    if not window:
        coherence = {"status": "UNMEASURED", "ok": None, "why": "no tiles to judge"}
    elif len(known) < len(window):
        coherence = {"status": "UNMEASURED", "ok": None,
                     "why": (f"{len(window) - len(known)} visible tile(s) carry no CIR palette "
                             f"or no hero frame, so the grid cannot be judged whole"),
                     "unjudged": [t["slug"] for t in window if t not in known]}
        problems.append("OPENING_GRID_COHERENCE_UNMEASURED: " + coherence["why"])
    else:
        report = bible.check_grid_coherence([
            bible.GridItem(slug=t["slug"], title=t["title"], palette=t["palette"],
                           hero_class=t["hero_class"]) for t in window])
        coherence = {"status": "MEASURED", **report.to_dict()}
        problems.extend(f"OPENING_GRID_INCOHERENT: {p}" for p in report.problems)

    return {"tiles": tiles, "visible": window, "visible_count": len(window),
            "excluded": excluded, "active_events": events, "promoted_for_ladder": promoted,
            "tiers": sorted(tiers_all), "coherence": coherence, "problems": problems,
            "ok": not problems,
            "basis": ("launch-cleared listings (app.dashboard_truth.launch_inventory) minus "
                      "uncleared legacy (publish.eligibility.legacy_status); strength is "
                      "measured orders where any exist, else the radar opportunity prior, "
                      "each tile labelled")}
