"""ENG-SEO-PRICE: listing SEO and price that beat the research shelf honestly.

Every listing package gets three things from the market, and only the market's *metadata*:

1. **Keyword evidence (SEO).** The nine owner-named research shops (`intel.scan_evidence.
   OWNER_SHOPS`) are scanned through the official public API into `BenchmarkListing` rows:
   title, tags, materials, price, pod, size range. This module reads those rows -- never a
   description, never a chart, never a photograph -- and counts which phrases the shelf uses,
   by how many *shops* (one shop repeating itself is one voice). A phrase becomes a tag only
   when every content word of it is true of this product (its own facts vocabulary).
   The title is ours: an originality check refuses a title that is, or contains a long run
   of, a competitor's title (`originality`). Competitor research is demand intelligence only.

2. **A price from the competitor band (pricing).** The research listings in the same pod --
   and, for a graded pod, the same size range -- give the band: quartiles and median, never a
   remembered constant. The product's own complexity (rows, sizes, colourwork) places the
   price inside the interquartile band; charm pricing (x.99) is allowed, a was-price never is
   (B-376). `pricing.decide_price` then applies the net-contribution floor and any measured
   contribution-per-visitor price points (B-201). Every price carries its evidence record.

3. **A learning hook.** Each SEO and price choice is recorded as an observation
   (`market_fit.choice`). When REAL outcome rows arrive (`ListingOutcome` with provenance
   `real`: Etsy views, favourites and orders), `learn` turns them into lessons on the existing
   bus (`improve.bus`, subjects `search_language` / `pricing_response`), which the listing
   already reads through `improve.consume` -- and into contribution-per-visitor price points
   that `decide_price` already consumes. Price A/B arms are bounded (`price_arms`). Nothing
   synthetic is ever learned from.

Deterministic, no model, no network, no spend.
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field

# ---- the research shelf ---------------------------------------------------------------------

# A band needs this much evidence: five priced listings from at least two shops. Fewer is a
# shop's own price list, not a market.
MIN_BAND_OBSERVATIONS = 5
MIN_BAND_SHOPS = 2

MEASURED = "MEASURED"
UNKNOWN = "UNKNOWN"


def research_shop_names() -> tuple[str, ...]:
    from ..intel.scan_evidence import OWNER_SHOPS

    return tuple(shop for shop, _url, _role in OWNER_SHOPS)


@dataclass(frozen=True)
class ShelfRow:
    shop: str
    listing_ref: str
    title: str
    tags: tuple[str, ...]
    price_cad: float
    on_sale: bool
    pod: str
    sizes: int | None


def research_listings(db, *, pod: str | None = None) -> list[ShelfRow]:
    """The scanned listings of the nine research shops, metadata only.

    A listing whose benchmark is not one of the nine is not research evidence here. A
    withdrawn listing is not on the shelf.
    """
    from sqlalchemy import select

    from ..core.models import Benchmark, BenchmarkListing

    wanted = {n.lower() for n in research_shop_names()}
    with db.session() as s:
        shop_of = {b.key: b.shop_name for b in s.scalars(select(Benchmark))
                   if (b.shop_name or "").lower() in wanted}
        q = select(BenchmarkListing).where(BenchmarkListing.benchmark_key.in_(
            list(shop_of) or [""]))
        if pod:
            q = q.where(BenchmarkListing.pod == pod)
        out = []
        for r in s.scalars(q.order_by(BenchmarkListing.id)):
            if (r.audit_state or "") == "withdrawn":
                continue
            d = r.detail or {}
            sr = d.get("size_range") if isinstance(d.get("size_range"), dict) else None
            out.append(ShelfRow(
                shop=shop_of[r.benchmark_key], listing_ref=str(r.listing_ref),
                title=str(r.title or ""),
                tags=tuple(str(t) for t in (d.get("tags") or []) if str(t).strip()),
                price_cad=float(r.price_cad or 0.0), on_sale=bool(r.on_sale),
                pod=str(r.pod or ""),
                sizes=(int(sr["sizes"]) if sr and sr.get("stated") and sr.get("sizes")
                       else None)))
    return out


def pod_for(category: str, title: str = "") -> str:
    from ..intel import pods

    got = pods.route(f"{title} {category.replace('_', ' ')}", "")
    if got == pods.UNCLASSIFIED and title:
        got = pods.route(category.replace("_", " "), "")
    return got


# ---- words ----------------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")

# Words a title or tag uses about every crochet pattern: they carry no originality and no
# product claim. Never sufficient to make a phrase "about" this product, never enough to make
# a title a copy.
GENERIC = frozenset({
    "a", "an", "and", "the", "of", "for", "with", "in", "to", "by", "or", "on", "your", "my",
    "crochet", "crocheted", "pattern", "patterns", "pdf", "digital", "download", "instant",
    "printable", "chart", "charted", "written", "instructions", "us", "uk", "terms",
    "diy", "easy", "beginner", "beginners", "friendly", "tutorial", "design", "file",
})

# Phrases a pattern listing may never spend a tag on: they describe a finished object.
_FINISHED_ITEM = re.compile(r"\b(handmade|hand made|finished|ready to ship|made to order)\b")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


# ---- originality: a competitor title is never ours ------------------------------------------

# A title that shares a run of this many consecutive tokens with a competitor title, at least
# MIN_DISTINCT_IN_RUN of them non-generic, is that competitor's title with ours around it.
MAX_SHARED_RUN = 4
MIN_DISTINCT_IN_RUN = 2
# Word-trigram overlap (Jaccard) at or above this is the same title rearranged.
MAX_TRIGRAM_JACCARD = 0.5


def _longest_run(a: list[str], b: list[str]) -> list[str]:
    best: list[str] = []
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > len(best):
                    best = a[i - cur[j]:i]
        prev = cur
    return best


def _trigrams(t: list[str]) -> set[tuple[str, ...]]:
    """Word trigrams carrying at least one non-generic word: two titles that share only
    "crochet pattern pdf digital download" share the category's vocabulary, not a title."""
    return {tuple(t[i:i + 3]) for i in range(max(0, len(t) - 2))
            if any(w not in GENERIC for w in t[i:i + 3])}


def overlap(ours: str, theirs: str) -> dict:
    """How much of `theirs` is in `ours`, measured three ways."""
    a, b = tokens(ours), tokens(theirs)
    run = _longest_run(a, b)
    distinct = [w for w in run if w not in GENERIC]
    ta, tb = _trigrams(a), _trigrams(b)
    jac = (len(ta & tb) / len(ta | tb)) if (ta or tb) else 0.0
    verbatim = bool(a) and a == b
    copied = (verbatim
              or (len(run) > MAX_SHARED_RUN and len(distinct) >= MIN_DISTINCT_IN_RUN)
              or jac >= MAX_TRIGRAM_JACCARD)
    return {"verbatim": verbatim, "shared_run": " ".join(run), "run_len": len(run),
            "distinct_in_run": len(distinct), "trigram_jaccard": round(jac, 3),
            "copied": copied}


def originality(title: str, shelf_titles: list[tuple[str, str]], *,
                scope: str = "pod") -> dict:
    """`shelf_titles` is [(shop, title)]. ok=False names the competitor title it copies.

    Review b17-a B1: with no competitor title to compare against, originality is UNKNOWN
    (`ok` None, `status` "UNKNOWN"), never a pass. B4: `scope` records whether the titles were
    the pod's own shelf ("pod") or every pod's ("all") when the pod's shelf was empty.
    """
    if not shelf_titles:
        return {"ok": None, "status": "UNKNOWN", "checked": 0, "copies": [], "closest": None,
                "scope": scope,
                "why": "no competitor titles on the research shelf to compare against",
                "rule": (f"no verbatim title; no shared run longer than {MAX_SHARED_RUN} "
                         f"tokens with {MIN_DISTINCT_IN_RUN}+ non-generic words; word-trigram "
                         f"Jaccard below {MAX_TRIGRAM_JACCARD}")}
    worst, hits = None, []
    for shop, theirs in shelf_titles:
        o = overlap(title, theirs)
        if o["copied"]:
            hits.append({"shop": shop, "title": theirs[:140], **o})
        if worst is None or (o["run_len"], o["trigram_jaccard"]) > (
                worst["run_len"], worst["trigram_jaccard"]):
            worst = {"shop": shop, **o}
    return {"ok": not hits, "status": "COPIED" if hits else "PASS",
            "checked": len(shelf_titles), "copies": hits[:5], "closest": worst,
            "scope": scope,
            "rule": (f"no verbatim title; no shared run longer than {MAX_SHARED_RUN} tokens "
                     f"with {MIN_DISTINCT_IN_RUN}+ non-generic words; word-trigram Jaccard "
                     f"below {MAX_TRIGRAM_JACCARD}")}


# ---- the product's own facts ----------------------------------------------------------------

@dataclass
class ProductFacts:
    slug: str
    version: str
    title: str
    category: str
    difficulty: str
    sizes: list[str] = field(default_factory=list)
    size_label: str | None = None
    colours: int = 1
    rows: int = 0
    motifs: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    is_bundle: bool = False
    bundle_count: int = 0

    def vocabulary(self) -> set[str]:
        from .category import CATEGORY_NODE_TERMS

        terms = CATEGORY_NODE_TERMS.get(self.category, {})
        words = tokens(" ".join([self.title, self.category.replace("_", " "),
                                 " ".join(self.motifs), " ".join(self.techniques),
                                 " ".join(self.materials), self.difficulty,
                                 " ".join(terms.get("object", ()))]))
        out = {_singular(w) for w in words} | set(words)
        if self.colours > 1:
            out |= {"colour", "color", "colourwork", "colorwork", "two", "tone"}
        if len(self.sizes) > 1:
            out |= {"size", "sizes", "sized"}
        return out | GENERIC


# Generic phrases true of every pattern this shop sells (both PDFs ship, every pattern is
# written and charted). Only these may take a tag with no product word in them.
TRUE_OF_EVERY_PATTERN = frozenset({"us and uk terms", "pdf crochet pattern", "crochet chart",
                                   "written crochet", "crochet pattern pdf",
                                   "printable pattern", "digital download"})


def is_true_of(phrase: str, facts: ProductFacts, vocab: set[str] | None = None) -> bool:
    """Every content word of `phrase` is a word the product's own facts use."""
    vocab = vocab if vocab is not None else facts.vocabulary()
    words = tokens(phrase)
    if not words or _FINISHED_ITEM.search(phrase.lower()):
        return False
    content = [w for w in words if w not in GENERIC]
    if not content:
        return " ".join(words) in TRUE_OF_EVERY_PATTERN
    return all(w in vocab or _singular(w) in vocab for w in content)


# ---- keyword evidence -------------------------------------------------------------------------

def _norm_tag(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def keyword_evidence(shelf: list[ShelfRow]) -> dict:
    """Which tag phrases the shelf uses, ranked by how many SHOPS use them."""
    by_phrase: dict[str, dict] = {}
    for row in shelf:
        for t in row.tags:
            p = _norm_tag(t)
            if not p:
                continue
            e = by_phrase.setdefault(p, {"phrase": p, "shops": set(), "listings": 0})
            e["shops"].add(row.shop)
            e["listings"] += 1
    ranked = sorted(by_phrase.values(),
                    key=lambda e: (-len(e["shops"]), -e["listings"], e["phrase"]))
    return {"listings": len(shelf), "shops": len({r.shop for r in shelf}),
            "tags": [{"phrase": e["phrase"], "shops": len(e["shops"]),
                      "listings": e["listings"]} for e in ranked]}


# ---- the Etsy title, tag and attribute rules -----------------------------------------------

TITLE_MAX = 140
TAG_COUNT = 13
TAG_MAX_CHARS = 20
MATERIALS_MAX = 13
# Etsy: "%", ":", "&" and "+" may each appear once in a title.
TITLE_ONCE_CHARS = ("%", ":", "&", "+")
# Etsy: no more than three words in a title may be entirely capitalised.
TITLE_MAX_CAPS_WORDS = 3


def title_problems(title: str) -> list[str]:
    out = []
    if not title.strip():
        out.append("TITLE_EMPTY")
    if len(title) > TITLE_MAX:
        out.append(f"TITLE_TOO_LONG: {len(title)} > {TITLE_MAX}")
    for ch in TITLE_ONCE_CHARS:
        if title.count(ch) > 1:
            out.append(f"TITLE_CHAR_REPEATED: {ch!r} appears {title.count(ch)} times; Etsy "
                       f"allows it once")
    caps = [w for w in re.findall(r"[A-Za-z]{2,}", title) if w.isupper() and w not in
            ("US", "UK", "PDF")]
    if len(caps) > TITLE_MAX_CAPS_WORDS:
        out.append(f"TITLE_CAPS: {len(caps)} all-capital words; Etsy allows "
                   f"{TITLE_MAX_CAPS_WORDS}")
    if "pattern" not in title.lower():
        out.append("TITLE_NOT_A_PATTERN: the title must say this is a pattern (B-409)")
    return out


def tag_problems(tags: list[str]) -> list[str]:
    from ..publish import listing_schema

    out = []
    if len(tags) != TAG_COUNT:
        out.append(f"TAGS_COUNT: {len(tags)} tags; all {TAG_COUNT} slots must be spent")
    for t in tags:
        if len(t) > TAG_MAX_CHARS:
            out.append(f"TAG_TOO_LONG: {t!r}")
    if len({_norm_tag(t) for t in tags}) != len(tags):
        out.append("TAGS_DUPLICATE")
    out.extend(listing_schema.tag_problems(list(tags)))
    return out


def materials_attribute(facts: ProductFacts) -> list[str]:
    """Etsy's materials field for a pattern: what the maker needs, Etsy-legal characters."""
    out = []
    for m in list(facts.materials) + ["yarn", "crochet hook"]:
        clean = re.sub(r"[^A-Za-z0-9 ]+", " ", str(m)).strip()
        clean = re.sub(r"\s+", " ", clean)
        if clean and clean.lower() not in {x.lower() for x in out}:
            out.append(clean[:45])
    return out[:MATERIALS_MAX]


# ---- above the fold ---------------------------------------------------------------------------

# What a buyer reads before "Learn more about this item": the first lines on mobile. Five
# questions are answered here or the listing has answered the auditor, not the buyer (B-409).
FOLD_CHARS = 420


def size_name(size) -> str:
    """A size as a buyer reads it, from a chain input that may be a name or a record."""
    if isinstance(size, dict):
        for k in ("name", "label", "size", "key"):
            if size.get(k):
                return str(size[k])
        return "/".join(str(v) for v in size.values())[:40]
    return str(size)


def size_statement(facts: ProductFacts) -> str:
    if len(facts.sizes) > 1:
        return f"{len(facts.sizes)} sizes ({', '.join(facts.sizes)})"
    if facts.size_label:
        return facts.size_label
    if facts.sizes:
        return facts.sizes[0]
    return "one size"


def fold_sentence(facts: ProductFacts) -> str:
    """The facts sentence that rides on the first description line."""
    return (f"Skill level: {facts.difficulty}. Size: {size_statement(facts)}. Included: two "
            f"PDFs, one in US terms and one in UK terms.")


def fold_problems(description: str, facts: ProductFacts) -> list[str]:
    fold = (description or "")[:FOLD_CHARS].lower()
    out = []
    obj = [w for w in tokens(facts.title) if w not in GENERIC] or tokens(facts.category)
    if not any(w in fold for w in obj):
        out.append("FOLD_WHAT: the first lines do not say what the pattern makes")
    if "pattern" not in fold or "not a finished item" not in fold:
        out.append("FOLD_PATTERN_NOT_ITEM: the first lines must say it is a pattern, not a "
                   "finished item")
    sizes = facts.sizes if len(facts.sizes) > 1 else [size_statement(facts)]
    if not all(s.lower() in fold for s in sizes):
        out.append("FOLD_SIZES: the first lines do not state the size(s)")
    if facts.difficulty.lower() not in fold:
        out.append("FOLD_SKILL: the first lines do not state the skill level")
    if not ("us terms" in fold and "uk terms" in fold and "pdf" in fold):
        out.append("FOLD_INCLUDED: the first lines do not say both US and UK PDFs are included")
    return out


# ---- the SEO package --------------------------------------------------------------------------

def _fact_phrases(facts: ProductFacts) -> list[str]:
    from .category import CATEGORY_NODE_TERMS

    obj = (CATEGORY_NODE_TERMS.get(facts.category, {}).get("object") or
           (facts.category.replace("_", " "),))[0]
    name = " ".join(w for w in tokens(facts.title) if w not in GENERIC)
    out = [f"{obj} crochet pattern", f"crochet {obj}", f"{obj} pattern", f"crochet {obj} pdf",
           f"diy {obj}", name, f"{name} pattern"]
    words = [w for w in tokens(facts.title) if w not in GENERIC and w != obj]
    out += [f"{w} {obj}" for w in words]
    out += [f"{m} crochet" for m in facts.motifs] + [f"{t} crochet" for t in facts.techniques]
    out += [f"{facts.difficulty} crochet", f"{obj} crochet chart"]
    out += sorted(TRUE_OF_EVERY_PATTERN)
    if facts.colours > 1:
        out.append(f"{facts.colours} colour crochet")
    if len(facts.sizes) > 1:
        out.append(f"{len(facts.sizes)} size crochet")
    return out


def choose_tags(facts: ProductFacts, evidence: dict, *, given: list[str] | None = None,
                exclude: list[str] | None = None) -> tuple[list[str], list[dict]]:
    """Thirteen tags: the given ones kept, then evidence-backed true phrases, then facts.

    Returns (tags, provenance). A shelf phrase is spent only when true of this product.
    """
    vocab = facts.vocabulary()
    banned = {_norm_tag(x) for x in (exclude or [])}
    tags: list[str] = []
    prov: list[dict] = []

    def take(p: str, source: str, **extra) -> None:
        p = _norm_tag(p)
        if (not p or len(p) > TAG_MAX_CHARS or p in banned or p in tags
                or len(tags) >= TAG_COUNT):
            return
        tags.append(p)
        prov.append({"tag": p, "source": source, **extra})

    for t in given or []:
        take(t, "listing.seo")
    for e in evidence.get("tags") or []:
        if is_true_of(e["phrase"], facts, vocab):
            take(e["phrase"], "research_shelf", shops=e["shops"], listings=e["listings"])
    for p in _fact_phrases(facts):
        if is_true_of(p, facts, vocab):
            take(p, "product_facts")
    return tags, prov


def seo_package(db, facts: ProductFacts, *, title: str, tags: list[str],
                description: str, category_choice=None) -> dict:
    """Audit and complete one listing's SEO against the research shelf. Pure on the db read.

    Returns tags completed to thirteen, the materials attribute, the taxonomy node, the
    originality verdict, the fold verdict, every problem, and the evidence behind each tag.
    """
    pod = pod_for(facts.category, facts.title)
    shelf = research_listings(db, pod=pod) if pod else []
    everything = shelf if shelf else research_listings(db)
    evidence = keyword_evidence(shelf or everything)
    full_tags, provenance = choose_tags(facts, evidence, given=tags)
    orig = originality(title, [(r.shop, r.title) for r in everything if r.title],
                       scope="pod" if shelf else "all")
    problems = title_problems(title) + tag_problems(full_tags) + fold_problems(description,
                                                                               facts)
    if orig["ok"] is None:
        problems.append("TITLE_ORIGINALITY_UNKNOWN: no competitor titles on the research "
                        "shelf, so the title is not proven original")
    elif not orig["ok"]:
        problems.append("TITLE_COPIES_COMPETITOR: " + "; ".join(
            f"{c['shop']} ({c['shared_run'] or 'rearranged'})" for c in orig["copies"]))
    status = getattr(category_choice, "status", None)
    if status != "CHOSEN":
        problems.append("CATEGORY_UNKNOWN: no taxonomy node is assigned")
    taxonomy = (category_choice.to_dict() if hasattr(category_choice, "to_dict") else None)
    return {"ok": not problems, "problems": problems, "pod": pod, "title": title,
            "tags": full_tags, "tag_provenance": provenance,
            "materials": materials_attribute(facts), "taxonomy": taxonomy,
            "originality": orig, "evidence": {"pod_listings": len(shelf),
                                              "all_listings": len(everything),
                                              "shops": evidence["shops"],
                                              "top_tags": evidence["tags"][:15]}}


# ---- pricing from the competitor band ----------------------------------------------------------

SIZED_PODS = frozenset({"garments", "hats"})


def _size_bucket(n: int | None) -> str | None:
    if n is None:
        return None
    return "one" if n <= 1 else "few" if n <= 3 else "many"


def price_band(db, *, category: str, title: str = "", sizes: int = 1) -> dict:
    """The research shelf's price band for this category and size range.

    MEASURED only with MIN_BAND_OBSERVATIONS priced listings from MIN_BAND_SHOPS shops. A
    graded pod narrows to listings stating the same size range when that still meets the
    minimum, and says when it had to widen. Prices are the listings' regular prices; a
    listing on sale is counted at its listed price and the sale share is reported.
    """
    pod = pod_for(category, title)
    rows = [r for r in research_listings(db, pod=pod) if r.price_cad > 0] if pod else []
    size_filter = "not applicable (unsized pod)"
    if pod in SIZED_PODS:
        want = _size_bucket(sizes)
        same = [r for r in rows if _size_bucket(r.sizes) == want]
        if len(same) >= MIN_BAND_OBSERVATIONS and len({r.shop for r in same}) >= MIN_BAND_SHOPS:
            rows, size_filter = same, f"same size range ({want})"
        else:
            size_filter = (f"widened to the whole pod: only {len(same)} listing(s) state the "
                           f"{want} size range")
    shops = sorted({r.shop for r in rows})
    base = {"pod": pod, "category": category, "observations": len(rows), "shops": shops,
            "size_filter": size_filter, "source": "BenchmarkListing (nine research shops, "
                                                  "official public API scan)",
            "listing_refs": [f"{r.shop}:{r.listing_ref}" for r in rows][:40]}
    if len(rows) < MIN_BAND_OBSERVATIONS or len(shops) < MIN_BAND_SHOPS:
        return {**base, "status": UNKNOWN,
                "why": (f"{len(rows)} priced listing(s) from {len(shops)} shop(s) in pod "
                        f"{pod!r}; a band needs {MIN_BAND_OBSERVATIONS} from "
                        f"{MIN_BAND_SHOPS}")}
    prices = sorted(r.price_cad for r in rows)
    q1, median, q3 = statistics.quantiles(prices, n=4, method="inclusive")
    return {**base, "status": MEASURED, "low_cad": round(prices[0], 2),
            "q1_cad": round(q1, 2), "median_cad": round(median, 2), "q3_cad": round(q3, 2),
            "high_cad": round(prices[-1], 2),
            "on_sale_share": round(sum(1 for r in rows if r.on_sale) / len(rows), 3)}


# Complexity is where inside the interquartile band a product sits: a one-colour, one-size,
# short pattern at the lower quartile, a long graded colourwork pattern at the upper one.
ROWS_FOR_FULL = 120
COMPLEXITY_WEIGHTS = {"rows": 0.4, "sizes": 0.35, "colourwork": 0.25}


def complexity(facts: ProductFacts) -> dict:
    parts = {"rows": min(1.0, max(0, facts.rows) / ROWS_FOR_FULL),
             "sizes": min(1.0, max(0, len(facts.sizes) - 1) / 4),
             "colourwork": min(1.0, max(0, facts.colours - 1) / 4)}
    score = sum(COMPLEXITY_WEIGHTS[k] * v for k, v in parts.items())
    return {"score": round(score, 4), "parts": {k: round(v, 4) for k, v in parts.items()},
            "weights": dict(COMPLEXITY_WEIGHTS)}


def charm(target: float, lo: float, hi: float) -> tuple[float, str]:
    """The x.99 price nearest the target inside [lo, hi], or the target itself."""
    cands = [c for c in (math.floor(target) - 0.01, math.ceil(target) - 0.01,
                         math.floor(target) + 0.99)
             if lo - 1e-9 <= c <= hi + 1e-9 and c > 0]
    if not cands:
        return round(target, 2), "no x.99 price inside the band; the target is used"
    best = min(cands, key=lambda c: (abs(c - target), c))
    return round(best, 2), f"charm price CA${best:.2f} nearest the target CA${target:.2f}"


class PriceRefused(ValueError):
    pass


def decide(db, facts: ProductFacts, band: dict, *, bundle_members_cad: list[float] | None
           = None, price_points: list[dict] | None = None, rate=None,
           foreign_share: float | None = None) -> dict:
    """The price, inside the evidence band, with the evidence for it recorded.

    Raises PriceRefused when the band is not MEASURED or no price inside it clears the net
    contribution floor: an unevidenced price is not invented here.
    """
    from . import pricing

    if band.get("status") != MEASURED:
        raise PriceRefused(f"no evidence band: {band.get('why')}")
    lo, hi = float(band["q1_cad"]), float(band["q3_cad"])
    cx = complexity(facts)
    target = lo + cx["score"] * (hi - lo)
    reasons = [f"research band for pod {band['pod']!r}: Q1 CA${lo:.2f}, median "
               f"CA${band['median_cad']:.2f}, Q3 CA${hi:.2f} from {band['observations']} "
               f"listings in {len(band['shops'])} shops ({band['size_filter']})",
               f"complexity {cx['score']:.2f} (rows {cx['parts']['rows']:.2f}, sizes "
               f"{cx['parts']['sizes']:.2f}, colourwork {cx['parts']['colourwork']:.2f}) "
               f"places the target at CA${target:.2f} inside the interquartile band"]
    if facts.is_bundle:
        members = [float(m) for m in (bundle_members_cad or [])]
        decision = pricing.decide_price(
            facts.slug, category_band_cad=(lo, hi), proposed_cad=sum(members) * 0.75
            if members else target, sizes_offered=max(1, len(facts.sizes)), is_bundle=True,
            bundle_members_cad=members, rate=rate, foreign_share=foreign_share)
        band_used = (decision.floor_cad, decision.ceiling_cad)
    else:
        proposed, why = charm(target, lo, hi)
        reasons.append(why)
        decision = pricing.decide_price(
            facts.slug, category_band_cad=(lo, hi), proposed_cad=proposed,
            sizes_offered=max(1, len(facts.sizes)), rate=rate, foreign_share=foreign_share,
            price_points=price_points)
        band_used = (lo, hi)
    if decision.refused:
        raise PriceRefused(decision.refused)
    price = decision.price_cad
    if not (band_used[0] - 1e-9 <= price <= band_used[1] + 1e-9):
        raise PriceRefused(f"CA${price:.2f} fell outside the evidence band "
                           f"CA${band_used[0]:.2f}-CA${band_used[1]:.2f}")
    # B-376: the price stands alone. No was-price exists for a price never charged.
    pricing.check_no_fake_discount(price, None, ever_charged=False)
    return {"price_cad": price, "band_cad": [round(band_used[0], 2), round(band_used[1], 2)],
            "within_band": True, "complexity": cx, "target_cad": round(target, 2),
            "reasons": reasons + list(decision.reasons), "warnings": list(decision.warnings),
            "net_cad": decision.net_cad, "was_price": None,
            "evidence": {k: band.get(k) for k in ("pod", "observations", "shops", "q1_cad",
                                                  "median_cad", "q3_cad", "low_cad",
                                                  "high_cad", "size_filter", "on_sale_share",
                                                  "listing_refs", "source")}}


# ---- discounts (B-376) ----------------------------------------------------------------------

# B-376: a tier discounted on more than a third of its live days has no regular price left.
MAX_DISCOUNTED_DAY_SHARE = 1 / 3


def discount_problems(*, price_cad: float, was_price_cad: float | None, ever_charged: bool,
                      flagship: bool, discounted_days: int = 0, live_days: int = 0) -> list[str]:
    from . import pricing

    out = []
    try:
        pricing.check_no_fake_discount(price_cad, was_price_cad, ever_charged=ever_charged)
    except pricing.DeceptivePricing as exc:
        out.append(f"DECEPTIVE_DISCOUNT: {exc}")
    if was_price_cad is not None and flagship:
        out.append("FLAGSHIP_DISCOUNT: the flagship is never routinely discounted (B-376)")
    if live_days and was_price_cad is not None and \
            (discounted_days + 1) / live_days > MAX_DISCOUNTED_DAY_SHARE:
        out.append(f"DISCOUNT_TOO_OFTEN: {discounted_days + 1} of {live_days} live days "
                   f"discounted is more than a third (B-376)")
    return out


# ---- learning hook ----------------------------------------------------------------------------

CHOICE_ACTION = "market_fit.choice"
LESSON_ACTION = "market_fit.lesson"
# Bounded A/B arms (B-201): each variant within this share of the control, inside the band,
# and far enough apart (8%) for a new shop's traffic to tell them apart at all.
ARM_STEP = 0.10
MAX_ARMS = 2
MIN_ARM_GAP = 0.08
# A price arm or a title template earns a lesson only from this many REAL visits.
MIN_LEARN_VISITS = 100


def record_choice(db, *, slug: str, version: str, kind: str, choice: dict,
                  job_id: int | None = None) -> None:
    """One SEO or price choice, as an observation the learning department reads."""
    from ..core.models import AuditLog

    if kind not in ("seo", "price"):
        raise ValueError(f"kind must be seo or price, not {kind!r}")
    import json

    with db.session() as s:
        s.add(AuditLog(actor="listing" if kind == "seo" else "pricing", action=CHOICE_ACTION,
                       artifact=f"{slug}@{version}", job_id=job_id,
                       detail=json.loads(json.dumps({"kind": kind, **choice}, default=str))))


def choices(db, slug: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [{"at": r.at.isoformat() if r.at else None, "artifact": r.artifact,
                 **(r.detail or {})}
                for r in s.scalars(select(AuditLog).where(
                    AuditLog.action == CHOICE_ACTION,
                    AuditLog.artifact.like(f"{slug}@%")).order_by(AuditLog.id))]


def price_arms(control_cad: float, band_cad: tuple[float, float]) -> list[dict]:
    """At most MAX_ARMS bounded arms: control, plus one variant inside the band and within
    ARM_STEP of the control, far enough apart to measure. Empty variant set when none fits."""
    lo, hi = band_cad
    arms = [{"arm": "control", "price_cad": round(control_cad, 2)}]
    for direction in (1, -1):
        raw = control_cad * (1 + direction * ARM_STEP)
        cand, _ = charm(raw, max(lo, control_cad * (1 - ARM_STEP)),
                        min(hi, control_cad * (1 + ARM_STEP)))
        gap = abs(cand - control_cad) / control_cad if control_cad else 0
        if lo <= cand <= hi and MIN_ARM_GAP <= gap <= ARM_STEP + 1e-9:
            arms.append({"arm": "variant", "price_cad": cand})
            break
    return arms[:MAX_ARMS]


def outcome_points(db, slug: str, *, net_of=None) -> list[dict]:
    """Contribution-per-visitor price points from REAL outcome rows only (B-201)."""
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from . import evidence_provenance, pricing

    by_price: dict[float, dict] = {}
    with db.session() as s:
        for r in s.scalars(select(ListingOutcome).where(ListingOutcome.product_slug == slug)):
            d = r.detail or {}
            if not evidence_provenance.learnable(d):
                continue
            price = d.get("price_cad")
            if price is None or r.orders is None:
                continue
            p = by_price.setdefault(round(float(price), 2),
                                    {"price_cad": round(float(price), 2), "visits": 0,
                                     "orders": 0, "favourites": 0})
            p["visits"] += int(r.visits or 0)
            p["orders"] += int(r.orders or 0)
            p["favourites"] += int(r.favourites or 0)
    out = []
    for p in by_price.values():
        net = (net_of or (lambda x: pricing.fees(x).net_cad))(p["price_cad"])
        out.append({**p, "contribution_cad": round(p["orders"] * net, 4)})
    return sorted(out, key=lambda p: p["price_cad"])


def learn(db, slug: str) -> dict:
    """Turn REAL outcomes into lessons. UNMEASURED, and nothing published, without them."""
    from ..improve import bus

    points = [p for p in outcome_points(db, slug) if p["visits"] >= MIN_LEARN_VISITS]
    if not points:
        return {"state": "UNMEASURED", "lessons": [], "points": [],
                "why": f"no price point for {slug} has {MIN_LEARN_VISITS} real visits"}
    lessons = []
    best = max(points, key=lambda p: p["contribution_cad"] / p["visits"])
    if len(points) >= 2:
        cpv = best["contribution_cad"] / best["visits"]
        lessons.append(bus.publish(
            db, origin_cell="pricing", subject="pricing_response",
            statement=(f"{slug} earned the most contribution per visitor at "
                       f"CA${best['price_cad']:.2f} (CA${cpv:.4f} a visitor over "
                       f"{best['visits']} real visits), so its price arms centre there"),
            evidence_ref=f"market_fit:price:{slug}:{best['price_cad']:.2f}:{best['visits']}"))
    seo = [c for c in choices(db, slug) if c.get("kind") == "seo"]
    if seo and sum(p["favourites"] for p in points) > 0:
        tags = seo[-1].get("tags") or []
        favs = sum(p["favourites"] for p in points)
        visits = sum(p["visits"] for p in points)
        lessons.append(bus.publish(
            db, origin_cell="seo_search", subject="search_language",
            statement=(f"buyers favourited {slug} {favs} times in {visits} real visits "
                       f"with tags {', '.join(tags[:6])}; those phrases keep their slots"),
            evidence_ref=f"market_fit:seo:{slug}:{visits}:{favs}"))
    return {"state": "measured", "lessons": lessons, "points": points,
            "best_price_cad": best["price_cad"]}
