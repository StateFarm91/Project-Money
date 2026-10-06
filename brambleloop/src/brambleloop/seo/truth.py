"""The truthful-tag validator (F-918 anti-gaming, F-008, F-021/F-245, PT-01, F-929).

Search KPIs are easy to game: a tag that ranks is not the same as a tag that is true, and a
title that repeats its keyword three times covers more queries on paper. This validator is the
guardrail every proposal passes through. A term is accepted only when

1. **Traceable** -- every content word maps to a verified product fact (`facts.ProductFacts`),
   and the finding names the fact. An untraceable word is `TERM_UNTRACEABLE`.
2. **Not a competitor's name** -- shop names from `radar.market.COMPETITORS`, the `benchmarks`
   table and `competitor_snapshots`, plus third-party yarn/pattern brands the CIR does not
   itself name: `TERM_COMPETITOR_BRAND`.
3. **Not protected IP** -- `gates.policy._IP_TERMS`: `TERM_PROTECTED_IP`.
4. **Not misleading** -- the existing claim gates, reused rather than restated:
   `commerce.search.tag_truth` (difficulty claims, finished-item phrasing),
   `commerce.seo._UNSUPPORTABLE` (superlatives), `gates.policy` unsupported-claim patterns,
   `gates.first_customer` product-type and colourwork findings: `TERM_MISLEADING`.
5. **Not stuffed** -- `commerce.portfolio.stuffing` (one word in too many tag slots, a content
   word repeated in the title), duplicate tags: `LISTING_STUFFED` / `TAG_DUPLICATE`.
6. **Within Etsy's limits** -- 13 tags, 20 characters per tag, 140-character title
   (`commerce.seo` TITLE_MAX / TAG_MAX_CHARS / TAG_MAX_COUNT; `publish.listing_schema`
   character rules): `LIMIT_*`.

Deterministic; no model, no network. Deterministic validation wins even if every LLM disagrees.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..commerce import seo as seo_mod
from .facts import ProductFacts, STOPWORDS, words

# Third-party brands a crochet tag might borrow. A tripwire, not an exhaustive register: the
# traceability rule already rejects any word no fact supports; this list gives the reason a
# precise name. A brand the CIR's own materials name is a material fact and is allowed.
THIRD_PARTY_BRANDS = (
    "ravelry", "lovecrafts", "woobles", "hobbii", "drops", "scheepjes", "stylecraft",
    "lion brand", "red heart", "bernat", "paintbox", "caron", "loops and threads",
    "hooked", "we are knitters", "yarnspirations",
)


def _norm(text: str) -> str:
    return " ".join(words(text))


def _squash(text: str) -> str:
    return "".join(words(text))


def _camel_words(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name or "").lower()


def competitor_names(db=None) -> list[str]:
    """Competitor shop names this company knows, normalised. DB rows when a db is given."""
    names: set[str] = set()
    try:
        from ..radar.market import COMPETITORS

        names |= {c.shop for c in COMPETITORS}
    except Exception:  # noqa: BLE001 - a missing seed list narrows the check, never opens it
        pass
    if db is not None:
        try:
            from sqlalchemy import select

            from ..core.models import Benchmark, CompetitorSnapshot
            from ._db import session

            with session(db) as s:
                names |= {r for r in s.scalars(select(Benchmark.shop_name)) if r}
                names |= {r for r in s.scalars(select(CompetitorSnapshot.shop)) if r}
        except Exception:  # noqa: BLE001 - tables absent on a bare db
            pass
    return sorted({n for n in names if n and len(_squash(n)) >= 4})


@dataclass
class TermVerdict:
    term: str
    ok: bool
    findings: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"term": self.term, "ok": self.ok, "findings": list(self.findings),
                "trace": list(self.trace)}


def _ip_terms() -> list[str]:
    from ..gates import policy

    return list(policy._IP_TERMS)


def _policy_claims(text: str) -> list[str]:
    from ..gates import policy

    out = []
    for pattern, why in policy._UNSUPPORTED_CLAIM_PATTERNS:
        if re.search(pattern, text, re.I):
            out.append(why)
    return out


def check_term(term: str, facts: ProductFacts, *, competitors: list[str] | None = None,
               role: str = "tag") -> TermVerdict:
    """Is this one tag (or title segment) true of this product, and traceable?"""
    from ..commerce import search as search_mod

    findings: list[str] = []
    norm = _norm(term)
    padded = f" {norm} "
    squashed = _squash(term)
    material_text = _norm(" ".join(facts.materials))

    for name in competitors if competitors is not None else competitor_names():
        sq = _squash(name)
        spaced = _norm(_camel_words(name))
        if sq and (sq in squashed or (len(spaced.split()) > 1 and f" {spaced} " in padded)):
            findings.append(f"TERM_COMPETITOR_BRAND: {term!r} names the competitor shop "
                            f"{name!r}; competitor research is for intelligence only")
    for brand in THIRD_PARTY_BRANDS:
        if f" {brand} " in padded and brand not in material_text:
            findings.append(f"TERM_COMPETITOR_BRAND: {term!r} borrows the third-party brand "
                            f"{brand!r}, which this product's materials do not name")
    for ip in _ip_terms():
        if f" {_norm(ip)} " in padded:
            findings.append(f"TERM_PROTECTED_IP: {term!r} contains {ip!r}")

    why = search_mod.tag_truth(norm, difficulty=facts.difficulty)
    if why:
        findings.append(f"TERM_MISLEADING: {why}")
    hit = seo_mod._UNSUPPORTABLE.search(term)
    if hit:
        findings.append(f"TERM_MISLEADING: {hit.group(0)!r} is a claim the pattern data cannot "
                        f"support")
    for why in _policy_claims(term):
        findings.append(f"TERM_MISLEADING: {why}")
    if role == "tag" and seo_mod._SUBJECTIVE.search(term):
        findings.append(f"TERM_MISLEADING: {term!r} spends a slot on a subjective word")

    trace = []
    for w in norm.split():
        src = facts.source_of(w)
        trace.append({"word": w, "source": src})
        if src is None and w not in STOPWORDS:
            findings.append(f"TERM_UNTRACEABLE: {w!r} in {term!r} is not traceable to any "
                            f"CIR attribute or verified product fact of {facts.slug}")
    return TermVerdict(term=term, ok=not findings, findings=findings, trace=trace)


def validate_listing(title: str, tags: list[str], facts: ProductFacts, *,
                     competitors: list[str] | None = None) -> dict:
    """Every rule above, over a whole title + tag set. `ok` only with no blocking finding."""
    from ..commerce.portfolio import stuffing
    from ..gates import first_customer as fc
    from ..publish import listing_schema

    competitors = competitor_names() if competitors is None else competitors
    blocking: list[str] = []
    tag_verdicts = [check_term(t, facts, competitors=competitors) for t in tags]
    for v in tag_verdicts:
        blocking += v.findings
    # Title: split into its segments; each word must trace like a tag's.
    segments = [p.strip() for p in re.split(r"[|,\-–—]", title or "") if p.strip()]
    title_verdicts = [check_term(p, facts, competitors=competitors, role="title")
                      for p in segments]
    for v in title_verdicts:
        blocking += [f"TITLE:{f}" for f in v.findings]

    # Etsy's limits, cited from where the repo records them.
    if len(tags) > seo_mod.TAG_MAX_COUNT:
        blocking.append(f"LIMIT_TAG_COUNT: {len(tags)} > {seo_mod.TAG_MAX_COUNT}")
    for t in tags:
        if len(t) > seo_mod.TAG_MAX_CHARS:
            blocking.append(f"LIMIT_TAG_CHARS: {t!r} is {len(t)} > {seo_mod.TAG_MAX_CHARS}")
    if len(title or "") > seo_mod.TITLE_MAX:
        blocking.append(f"LIMIT_TITLE_CHARS: {len(title)} > {seo_mod.TITLE_MAX}")
    if not (title or "").strip():
        blocking.append("LIMIT_TITLE_EMPTY")
    blocking += [f"LIMIT_{p}" for p in listing_schema.title_problems(title or "")]
    blocking += [f"LIMIT_{p}" for p in listing_schema.tag_problems(list(tags))]

    lowered = [t.strip().lower() for t in tags]
    dupes = sorted({t for t in lowered if lowered.count(t) > 1})
    if dupes:
        blocking.append(f"TAG_DUPLICATE: {dupes}")
    stuffed = stuffing(title or "", list(tags))
    if stuffed.get("stuffed"):
        blocking.append(f"LISTING_STUFFED: {stuffed['why']}")
    if stuffed.get("repeated_in_title"):
        blocking.append(f"LISTING_STUFFED: title repeats {stuffed['repeated_in_title']}")

    if facts.cir is not None:
        for f in fc.product_type_findings(facts.cir, title=title or "", tags=list(tags)):
            blocking.append(f"TERM_MISLEADING: {f}")
        if facts.twin is not None:
            for f in fc.colourwork_findings(facts.cir, facts.twin, title=title or "",
                                            tags=list(tags)):
                blocking.append(f"TERM_MISLEADING: {f}")

    soft: list[str] = []
    if len(tags) < seo_mod.TAG_MAX_COUNT:
        soft.append(f"TAG_SLOTS_UNUSED: {len(tags)} of {seo_mod.TAG_MAX_COUNT}")
    return {"ok": not blocking, "blocking": blocking, "soft": soft, "stuffing": stuffed,
            "tags": [v.to_dict() for v in tag_verdicts],
            "title_segments": [v.to_dict() for v in title_verdicts],
            "limits": {"title_max": seo_mod.TITLE_MAX, "tag_max_chars": seo_mod.TAG_MAX_CHARS,
                       "tag_max_count": seo_mod.TAG_MAX_COUNT,
                       "cited": "commerce/seo.py TITLE_MAX/TAG_MAX_CHARS/TAG_MAX_COUNT; "
                                "commerce/search.py TAG_SLOTS/TAG_MAX_CHARS/TITLE_MAX; "
                                "publish/listing_schema.py module docstring"}}
