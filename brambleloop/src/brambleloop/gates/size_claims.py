"""Size-claim truth: a listing may not promise more sizes than its release delivers.

The defect this exists for (owner report, 2026-10-27). The Command Center advertised
"Nesting Baskets, three sizes" at CA$6.50, and the US PDF downloaded from that product was
`market-basket-medium@1.2.0`: one basket, 35 rounds, 20.8 cm across the points. Nothing was
wrong with the medium pattern. What was wrong is structural and still present for any future
multi-size product:

* a Launch-0 candidate may hold several size variants, and **each variant is its own CIR, its
  own certified release and its own customer PDF** (`products.launch0.Variant`);
* a graded garment is the same: "each size is released as its own CIR" (`cir.model.Grading`),
  and its PDF says "This document is size M of 9";
* yet listing copy is written at the product level (`seo.facts.PRODUCT_LICENCES` licenses
  "three" and "nesting" for every basket CIR's listing), so one release's listing could say
  "three sizes" while delivering one.

The rule enforced here is the plain one: **one certified release delivers exactly one size of
instructions**, so the listing for it, and the customer PDF it delivers, may claim at most one
size. A product that genuinely sells several sizes must deliver every size it names, which is
a multi-release package this code does not assemble yet; until it does, such a claim refuses.

What counts as a size claim is deliberately narrow, so the gate refuses on what a buyer would
read as a promise and not on incidental words:

* an explicit count -- "three sizes", "in 3 sizes", "two different sizes";
* a named set -- "small, medium and large", "small and large", "S/M/L";
* "nesting" (a nesting set is by definition several sizes);
* "multiple sizes", "several sizes", "all sizes included", "sizes included".

A sentence that says the other sizes are sold separately, are separate listings or are not
included is not a claim. In the customer PDF of a graded release the size chart's
"size M of 9" and "any of the 9 sizes in the size chart" are reference information about the
family, printed by `publish.pdf.fit_statement` / `support_scope`, and are not read as claims.

Deterministic, no model, no network, CA$0. It reads the stored listing, the certified
pattern version and the release's stored customer PDF; it writes nothing.
"""
from __future__ import annotations

import re

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

DELIVERED_PER_RELEASE = 1

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_NUM = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_FULL = r"(?:small|medium|large|extra[- ]large)"
# Size letters are matched case-sensitively: "S, M, L" is a size list, "m/s" is not.
_TOK = r"(?:XXS|XS|S|M|L|XL|XXL|[2-6]XL?)"
# Objects sold in graded sets. A set of coasters, ornaments or placemats is a count of pieces
# in one size, never a claim of several sizes, so those nouns are deliberately absent.
_VESSEL = (r"(?:baskets?|bowls?|bins?|box(?:es)?|trays?|pots?|planters?|bags?|totes?|"
           r"cos(?:y|ies)|coz(?:y|ies)|cases?|pouch(?:es)?)")
_DIM = r"\d+(?:\.\d+)?\s*(?:cm|mm|in(?:ches)?\b|\")"
_GROUPED = {"trio": 3, "pair": 2}


def _count_word(m) -> int | None:
    return _to_int(m.group(1))


def _distinct_full(m) -> int:
    return len({w.lower().replace(" ", "-") for w in re.findall(
        r"small|medium|extra[- ]large|large", m.group(0), re.I)})


def _tokens(m) -> int:
    return len(set(re.findall(_TOK, m.group(0))))


# Each pattern: (name, compiled regex, function(match) -> claimed count or None for "2+").
_PATTERNS: tuple[tuple[str, re.Pattern, object], ...] = (
    # "three sizes", "3 basket sizes", "two different basket sizes", "three-size set"
    ("count", re.compile(rf"\b{_NUM}(?:\s+|-)(?:[a-z]+[\s-]+){{0,2}}?sizes?\b", re.I),
     _count_word),
    # "small, medium and large", "small/medium/large", "small · medium · large"
    ("named_sizes", re.compile(rf"\b{_FULL}(?:\s*(?:,|/|·|&|\+|\band\b)\s*(?:and\s+)?{_FULL})"
                               rf"{{2,}}\b", re.I), _distinct_full),
    # "small and large baskets", "medium & large sizes": two names need a size or vessel noun
    ("named_pair", re.compile(rf"\b{_FULL}\s*(?:,|/|&|\band\b)\s*{_FULL}\s+"
                              rf"(?:sizes?|versions?|patterns?|{_VESSEL})\b", re.I),
     _distinct_full),
    # "S/M/L", "S, M, L", "XS/S"
    ("size_letters", re.compile(rf"(?<![\w/]){_TOK}(?:\s*[/,]\s*{_TOK})+(?![\w/])"), _tokens),
    # "sizes: S M L", "Sizes S M L XL"
    ("size_letter_run", re.compile(rf"\b[Ss]izes?\s*:?\s*{_TOK}(?:\s+{_TOK})+\b"), _tokens),
    # "sizes S to XL", "XS-3XL"
    ("size_range", re.compile(rf"\b[Ss]izes?\s+{_TOK}\s*(?:to|-|–)\s*{_TOK}\b|"
                              rf"(?<![\w/]){_TOK}\s*[-–]\s*{_TOK}(?![\w/])"), lambda m: None),
    # "Diameters 20 cm, 25 cm and 30 cm"
    ("dimension_list", re.compile(rf"\b(?:diameters|widths|heights|lengths|sizes)\s*:?\s*"
                                  rf"{_DIM}(?:\s*(?:,|/|&|\band\b)\s*{_DIM})+", re.I),
     lambda m: len(re.findall(_DIM, m.group(0)))),
    # "set of 3 baskets", "a trio of baskets", "pair of storage bins"
    ("vessel_set", re.compile(rf"\b(?:set\s+of\s+{_NUM}|(trio|pair))\s+(?:of\s+)?"
                              rf"(?:[a-z]+\s+){{0,2}}?{_VESSEL}\b", re.I),
     lambda m: _to_int(m.group(1)) if m.group(1) else _GROUPED[m.group(2).lower()]),
    # Review OPUS2C N1.1: forms that got through.
    ("vessel_group", re.compile(rf"\b{_VESSEL}\s+(trio|pair)\b", re.I),
     lambda m: _GROUPED[m.group(1).lower()]),
    ("named_range", re.compile(rf"\b{_FULL}\s+(?:to|through|thru|-|–)\s+{_FULL}\b|"
                               rf"(?<![\w/]){_TOK}\s+(?:to|through|thru)\s+{_TOK}(?![\w/])",
                               re.I), lambda m: None),
    ("multi_size", re.compile(r"\bmulti-?\s?sized?\b|\bmultiple\s+size\s+options?\b|"
                              r"\bgraduat(?:ing|ed)\s+sizes\b", re.I), lambda m: None),
    ("dimension_tail_unit", re.compile(
        r"\b(?:sizes?|diameters?|widths?|heights?)\s*:?\s*\d+(?:\.\d+)?"
        r"(?:\s*(?:,|/|&|\band\b)\s*\d+(?:\.\d+)?)+\s*(?:cm|mm|in(?:ches)?\b)", re.I),
     lambda m: len(re.findall(r"\d+(?:\.\d+)?", m.group(0)))),
    # A slash list of the same unit is several sizes; "20 cm / 8 in" is one size converted.
    ("dimension_slash", re.compile(rf"{_DIM}(?:\s*/\s*{_DIM})+", re.I),
     lambda m: (len(re.findall(_DIM, m.group(0)))
                if len({u.lower()[:2] for u in re.findall(r"cm|mm|in|\"", m.group(0))}) == 1
                else 1)),
    ("article_named", re.compile(rf"\ban?\s+{_FULL}\s*(?:,|&|\band\b)\s*(?:and\s+)?"
                                 rf"(?:an?\s+{_FULL}\s*(?:,|&|\band\b)\s*(?:and\s+)?)*"
                                 rf"an?\s+{_FULL}\b", re.I), _distinct_full),
    ("vessel_count", re.compile(rf"\b{_NUM}(?:\s+|-)(?:piece\s+)?(?:[a-z]+\s+)?{_VESSEL}"
                                rf"(?:\s+set)?\b", re.I), _count_word),
    ("named_plus", re.compile(rf"\b{_FULL}\s*\+\s*{_FULL}\b", re.I), _distinct_full),
    ("nesting", re.compile(r"\bnesting\b", re.I), lambda m: None),
    ("several_sizes", re.compile(r"\b(?:multiple|several|various)\s+sizes\b|"
                                 r"\ball\s+sizes\b(?!\s+of\s+(?:yarn|hooks?|needles?))|"
                                 r"\bsizes\s+included\b", re.I), lambda m: None),
)
# "a set of three" with no noun is a size claim only beside a vessel noun in the sentence.
_BARE_SET = re.compile(rf"\bset\s+of\s+{_NUM}\b", re.I)
_VESSEL_RX = re.compile(rf"\b{_VESSEL}\b", re.I)

# A size word followed by these is advice about a hook or gauge, never a promise of sizes.
_TOOL_BETWEEN = re.compile(r"\b(?:hook|needle)s?\b", re.I)
_NOT_A_CLAIM_AFTER = re.compile(r"^\s*(?:larger|smaller|bigger|up|down)\b", re.I)
_HOOK_BEFORE = re.compile(r"\b(?:hook|needle)s?\s*(?:\w+\s+){0,1}$", re.I)

# A disclaimer counts only when it is ABOUT SIZES ("the small and large are sold separately",
# "other sizes sold separately", "this listing is the medium basket"). Only the disclaimer's
# own words are removed; the rest of the sentence is still read, so "three sizes, yarn not
# included" is still a claim (independent review OPUS2A F1.1).
_SIZE_DISCLAIM = re.compile(
    rf"(?:\b(?:other|remaining|larger|smaller|{_FULL})\s+(?:\w+\s+){{0,3}}?"
    rf"(?:are|is)?\s*(?:sold\s+separately|separate\s+listings?|available\s+separately|"
    rf"not\s+included)\b|\bone\s+size\s+only\b|"
    rf"\bthis\s+listing\s+is\s+(?:for\s+)?(?:the\s+)?(?:{_FULL}|one)\b)", re.I)
# The graded size chart's reference wording, printed by publish.pdf (never a claim).
_GRADED_REFERENCE = re.compile(r"\bsize\s+\S+\s+of\s+\d+\b|\bsizes\s+in\s+the\s+size\s+chart\b|"
                               r"\bsize\s+chart\b|\bgraded\s+from\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?\n])\s+")


def _to_int(token: str | None) -> int | None:
    t = (token or "").lower()
    if t.isdigit():
        return int(t)
    return _NUMBER_WORDS.get(t)


def claims_in(text: str, *, graded_reference_ok: bool = False) -> list[dict]:
    """Every size claim in `text`, one dict per match: what, phrase, count (None = 2 or more).

    A claim of one size ("one size", "1 size") is not returned: it promises no more than a
    release delivers.
    """
    out: list[dict] = []
    for sentence in _SENTENCE.split(text or ""):
        if not sentence.strip():
            continue
        if graded_reference_ok and _GRADED_REFERENCE.search(sentence):
            continue
        read = _SIZE_DISCLAIM.sub(" ", sentence)
        found = []
        for name, rx, count_of in _PATTERNS:
            for m in rx.finditer(read):
                if name == "count" and (_NOT_A_CLAIM_AFTER.match(read[m.end():])
                                        or _HOOK_BEFORE.search(read[:m.start()])
                                        # Review OPUS2C N1.2: "two hook sizes" is advice.
                                        or _TOOL_BETWEEN.search(m.group(0))):
                    continue
                found.append((name, m, count_of(m)))
        if _VESSEL_RX.search(read):
            for m in _BARE_SET.finditer(read):
                found.append(("vessel_set", m, _to_int(m.group(1))))
        for name, m, n in found:
            if n is not None and n <= 1:
                continue
            out.append({"what": name, "phrase": m.group(0).strip()[:80],
                        "count": n, "sentence": sentence.strip()[:200]})
    return out


def claimed_count(claims: list[dict]) -> int:
    """The largest number of sizes the claims promise (2 for an uncounted plural claim)."""
    if not claims:
        return DELIVERED_PER_RELEASE
    return max((c["count"] if c["count"] is not None else 2) for c in claims)


def check_texts(texts: dict[str, str], *, delivered: int = DELIVERED_PER_RELEASE,
                graded_sources: tuple[str, ...] = ()) -> dict:
    """Judge named texts (source -> text) against the number of sizes delivered."""
    found: dict[str, list[dict]] = {}
    for source, text in texts.items():
        claims = claims_in(text, graded_reference_ok=source in graded_sources)
        if claims:
            found[source] = claims
    worst = max((claimed_count(c) for c in found.values()), default=DELIVERED_PER_RELEASE)
    reasons = []
    for source, claims in sorted(found.items()):
        n = claimed_count(claims)
        if n > delivered:
            phrases = "; ".join(sorted({c["phrase"] for c in claims}))[:200]
            counted = any(c["count"] is not None for c in claims)
            label = str(n) if counted else "several"
            reasons.append(
                f"size-claim truth: the {source} promises {label} "
                f"sizes ({phrases}) but this release delivers {delivered} size of "
                f"instructions; name only the size it delivers, or sell each size as its own "
                f"certified release")
    return {"state": FAIL if reasons else PASS, "claimed": worst, "delivered": delivered,
            "claims": found, "reasons": reasons}


def _pdf_text(db, slug: str, version: str) -> tuple[str | None, str]:
    """The release's stored US customer PDF text, from its newest completed assets.build.

    Selected by the job's own slug and version (review OPUS2A F1.4: a newest-200 window could
    miss the release on a busy queue), newest first.
    """
    from sqlalchemy import desc, select

    from ..core.artifacts import ArtifactStore
    from ..core.models import Job, JobStatus
    from ..publish.pdf import extracted_text

    sha = None
    with db.session() as s:
        rows = s.execute(select(Job.inputs, Job.outputs).where(
            Job.job_type == "assets.build", Job.status == JobStatus.DONE,
            Job.inputs["slug"].as_string() == slug,
            Job.inputs["version"].as_string() == version).order_by(desc(Job.id)))
        for _i, o in rows:
            o = o or {}
            sha = (o.get("pdf_sha256_by_terminology") or {}).get("US") or o.get("pdf_sha256")
            if sha:
                break
    if not sha:
        return None, "no completed assets.build names a customer PDF for this release"
    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception as exc:  # noqa: BLE001 - unread is a refusal, never read as clean
        return None, f"customer PDF {sha[:12]} could not be read ({type(exc).__name__})"
    try:
        return extracted_text(data), f"customer PDF {sha[:12]}"
    except Exception as exc:  # noqa: BLE001
        return None, f"customer PDF {sha[:12]} text could not be extracted ({type(exc).__name__})"


def for_release(db, *, slug: str, version: str) -> dict:
    """The size-claim verdict for one release's listing and customer PDF.

    `state` is FAIL when the stored listing (title, description, tags) or the delivered PDF
    claims more sizes than the release delivers. With no stored listing the verdict is
    UNKNOWN with no reason: the listing gates refuse a release without a listing on their own.
    A customer PDF that cannot be found or read is a FAIL with that reason (OPUS2A F1.4).
    """
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import Listing, PatternVersion, Product

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(Listing.id.desc()).limit(1))
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version)))
        listing_texts = (None if listing is None else {
            "listing title": listing.title or "",
            "listing description": listing.description or "",
            "listing tags": ". ".join(str(t) for t in (listing.tags or []))})
        cir_json = dict(pv.cir_json) if pv is not None and pv.cir_json else None
    graded = None
    if cir_json:
        try:
            g = CIR.from_dict(cir_json).grading
            graded = None if g is None else {"size": g.size, "family": len(g.sizes)}
        except Exception:  # noqa: BLE001 - an unreadable CIR is judged as ungraded
            graded = None
    if listing_texts is None:
        return {"state": UNKNOWN, "claimed": None, "delivered": DELIVERED_PER_RELEASE,
                "claims": {}, "reasons": [], "graded": graded,
                "pdf": "not read: no stored listing for this release"}
    texts = dict(listing_texts)
    pdf_text, pdf_note = _pdf_text(db, slug, version)
    if pdf_text is not None:
        texts["customer PDF"] = pdf_text
    verdict = check_texts(texts, graded_sources=("customer PDF",) if graded else ())
    if pdf_text is None:
        # Review OPUS2A F1.4: the PDF the buyer receives is half of what this gate judges; a
        # release whose PDF cannot be read is refused here, never passed on the listing alone.
        verdict["reasons"] = list(verdict["reasons"]) + [
            f"size-claim truth: the customer PDF was not read ({pdf_note}), so what it promises "
            f"is unknown; unknown is never a pass"]
        verdict["state"] = FAIL
    verdict.update({"graded": graded, "pdf": pdf_note})
    return verdict


def launch0_findings() -> list[dict]:
    """Launched Launch-0 candidates whose product-level name promises more sizes than any one
    of their releases delivers.

    A candidate with several variants is listed one release at a time (one CIR per variant),
    so a multi-size name ("Nesting Baskets, three sizes") on any of those listings promises
    sizes the buyer does not receive. Returned rather than raised, so the static test can pin
    the current state and the reserve candidates the owner preserved are not judged as launched.
    """
    from ..products import launch0 as l0

    out = []
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        verdict = check_texts({"candidate title": cand.title,
                               "candidate description": cand.what_it_is})
        cirs = sorted({l0.cir_for(v.build).slug for v in cand.variants})
        if verdict["state"] == FAIL:
            out.append({"candidate": slug, "title": cand.title, "variants": len(cand.variants),
                        "releases": cirs, "claimed": verdict["claimed"],
                        "reasons": verdict["reasons"]})
    return out
