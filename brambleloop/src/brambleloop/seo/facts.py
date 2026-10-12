"""Verified product facts for a Launch-0 variant: the vocabulary a truthful tag may use.

A term in a title or tag is allowed only when it can be traced to one of these facts. Each
word in `ProductFacts.vocabulary` maps to the source it was read from, so a proposal can show,
for every word it spends a slot on, *why* that word is true of this product:

- `identity:<candidate>`   the product's own listing identity (`products.launch0.ListingIdentity`:
                           kind, nouns, qualifiers, techniques, Etsy category intent)
- `cir.title` / `cir.slug` the compiled pattern's own name
- `cir.colors`             yarn colours the pattern is worked in, and their Etsy colour family
- `cir.materials`          the yarn weights/fibres the CIR names
- `twin.stitches`          stitches the compiled twin actually uses (US and UK names)
- `publish.difficulty`     the printed difficulty ladder (same function the PDF cover uses)
- `deliverable`            what every release ships: a crochet pattern PDF, written and
                           charted, in US and UK terms (`runtime.release` `assets.build`)
- `category_terms`         the object/family words `commerce.category.CATEGORY_NODE_TERMS`
                           and `commerce.search._FAMILY_PHRASES` already accept for this category
- `variants`               the candidate's own variant labels (sizes, a set count the CIR backs)

Nothing here is inferred by a model; it is all read from code-held product records and the
compiled CIR at call time, so a re-engineered product changes its own vocabulary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset({"and", "or", "the", "a", "an", "of", "for", "with", "by", "in", "to",
                       "n", "on", "your", "my"})

# What every Launch-0 release ships (runtime.release assets.build renders pattern-us.pdf and
# pattern-uk.pdf with charts; the title builder's "Written Instructions and Chart" and "US and
# UK Terms" segments describe that deliverable).
DELIVERABLE_WORDS = ("crochet", "pattern", "pdf", "chart", "written", "instruction", "digital",
                     "download", "instant", "printable", "us", "uk", "term", "diy", "row",
                     "yarn", "craft", "project", "fiber", "fibre", "art", "stitch", "gift")
DELIVERABLE_SOURCE = ("deliverable: crochet pattern PDF, written + charted, US and UK terms "
                      "(runtime.release assets.build)")

# Derivations a vocabulary word licenses ("hexagonal" names a hexagon; "textured" a texture).
DERIVED = {"hexagonal": "hexagon", "hexagon": "hexagonal", "textured": "texture",
           "texture": "textured", "nesting": "nest"}


def stem(word: str) -> str:
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


@dataclass
class ProductFacts:
    slug: str
    candidate: str
    cir_title: str
    kind: str
    category: str
    nouns: list[str]
    qualifiers: list[str]
    techniques: list[str]
    difficulty: str
    colors: list[str]
    colour_families: list[str]
    materials: list[str]
    stitches: list[str]
    width_cm: float | None
    height_cm: float | None
    makes: int
    season: str | None = None
    variant_labels: list[str] = field(default_factory=list)
    vocabulary: dict[str, str] = field(default_factory=dict)
    cir: object = None
    twin: object = None

    def source_of(self, word: str) -> str | None:
        w = word.lower()
        if w in STOPWORDS:
            return "stopword"
        return self.vocabulary.get(w) or self.vocabulary.get(stem(w))

    def to_dict(self) -> dict:
        return {"slug": self.slug, "candidate": self.candidate, "cir_title": self.cir_title,
                "kind": self.kind, "category": self.category, "nouns": list(self.nouns),
                "qualifiers": list(self.qualifiers), "techniques": list(self.techniques),
                "difficulty": self.difficulty, "colors": list(self.colors),
                "colour_families": list(self.colour_families),
                "materials": list(self.materials), "stitches": list(self.stitches),
                "width_cm": self.width_cm, "height_cm": self.height_cm, "makes": self.makes,
                "season": self.season, "variant_labels": list(self.variant_labels),
                "vocabulary_size": len(self.vocabulary)}

    def fingerprint_material(self) -> dict:
        d = self.to_dict()
        d["vocabulary"] = sorted(self.vocabulary.items())
        return d


def _add(vocab: dict[str, str], text: str, source: str) -> None:
    for w in words(text):
        if w in STOPWORDS:
            continue
        for form in {w, stem(w)} | ({DERIVED[w]} if w in DERIVED else set()):
            vocab.setdefault(form, source)


def _difficulty_words(level: str) -> list[str]:
    level = (level or "").lower()
    out = list(words(level))
    if level == "beginner":
        out += ["easy", "simple", "quick"]
    return out


def for_variant(cand, variant) -> ProductFacts:
    """Facts for one Launch-0 variant (one CIR slug, one listing draft)."""
    from ..cir.compiler import compile_cir
    from ..cir.stitches import get as stitch_get
    from ..cir.twin import build_twin
    from ..commerce import category as category_mod
    from ..commerce import search as search_mod
    from ..products import launch0 as L
    from ..publish.difficulty import difficulty as difficulty_of

    cir = L.cir_for(variant.build)
    twin = build_twin(cir, compile_cir(cir))
    identity = cand.listing
    level = difficulty_of(cir, twin)
    colors = sorted(c for c in twin.colors_used if c)
    families = sorted({f for f in (category_mod.colour_family(c, (cir.colors or {}).get(c))
                                   for c in colors) if f})
    stitch_names: list[str] = []
    for code in sorted(twin.stitch_types_used):
        try:
            s = stitch_get(code)
            stitch_names += [code, s.name_us, s.name_uk]
        except Exception:  # noqa: BLE001 - an unnamed stitch contributes its code only
            stitch_names.append(code)
    makes = sum(c.make for c in cir.components)

    vocab: dict[str, str] = {}
    _add(vocab, " ".join(DELIVERABLE_WORDS), DELIVERABLE_SOURCE)
    if identity is not None:
        src = f"identity:{cand.slug}"
        _add(vocab, " ".join((identity.kind, identity.etsy_category.replace("_", " "))
                             + tuple(identity.nouns) + tuple(identity.qualifiers)
                             + tuple(identity.techniques)), src)
    _add(vocab, cir.title, "cir.title")
    _add(vocab, cir.slug.replace("-", " "), "cir.slug")
    _add(vocab, " ".join(colors + [f.lower() for f in families]), "cir.colors")
    _add(vocab, " ".join(m.name for m in cir.materials), "cir.materials")
    _add(vocab, " ".join(stitch_names), "twin.stitches")
    _add(vocab, " ".join(_difficulty_words(level)), "publish.difficulty")
    category = identity.etsy_category if identity is not None else ""
    terms = category_mod.CATEGORY_NODE_TERMS.get(category, {})
    _add(vocab, " ".join(terms.get("object", ())), "category_terms:object")
    # Family terms are prefixes in CATEGORY_NODE_TERMS ("accessor"); only whole words count.
    _add(vocab, " ".join(t for t in terms.get("family", ()) if len(t) > 3 and
                         not t.endswith("or")), "category_terms:family")
    fam = search_mod._CATEGORY_FAMILY.get(category, "")
    _add(vocab, " ".join(search_mod._FAMILY_PHRASES.get(fam, ())), "category_terms:shelf")
    labels = [v.label for v in cand.variants] if len(cand.variants) > 1 else []
    if len(cand.variants) > 1:
        _add(vocab, "size sizes " + " ".join(v.key for v in cand.variants), "variants")
    if makes > 1:
        _add(vocab, f"set {makes}", "cir.components.make")

    return ProductFacts(
        slug=cir.slug, candidate=cand.slug, cir_title=cir.title,
        kind=identity.kind if identity else "", category=category,
        nouns=list(identity.nouns) if identity else [],
        qualifiers=list(identity.qualifiers) if identity else [],
        techniques=list(identity.techniques) if identity else [],
        difficulty=level, colors=colors, colour_families=families,
        materials=[m.name for m in cir.materials],
        stitches=sorted(twin.stitch_types_used),
        width_cm=twin.width_cm or None, height_cm=twin.height_cm or None, makes=makes,
        season=None, variant_labels=labels, vocabulary=vocab, cir=cir, twin=twin)


def launch0_facts() -> list[ProductFacts]:
    """Facts for every variant of every Launch-0 slug, in listing order."""
    from ..products import launch0 as L

    out: list[ProductFacts] = []
    for slug in L.LAUNCH0_SLUGS:
        cand = L.candidate(slug)
        for v in cand.variants:
            out.append(for_variant(cand, v))
    return out


# ---------------------------------------------------------------------------
# Product-level facts (wave 3): one listing per Launch-0 *product*, not per CIR variant.
#
# The owner's Launch-0 ruling sells the nesting baskets as ONE product in three sizes. A
# product-level listing may use a word only when it is true of every size it sells, or when it
# names the set of sizes itself. Its vocabulary is therefore the union of what the variants share
# plus the product record's own words, each licensed below against a cited, code-held source
# text that must actually contain the word (so the licence cannot drift away from the record).

# word -> (source attribute path, why). The word must occur in that source's text at call time.
PRODUCT_LICENCES: dict[str, dict[str, tuple[str, str]]] = {
    "nursery-nesting-baskets": {
        "nesting": ("candidate.title", "the product record names them Nesting Baskets"),
        "three": ("candidate.title", "the product record sells three sizes"),
    },
    "cloudline-baby-blanket": {
        "diamond": ("cir.designer_notes", "the CIR's motif is a diamond lattice"),
        "lattice": ("cir.designer_notes", "the CIR's motif is a diamond lattice"),
        "raised": ("cir.designer_notes", "every raised stitch touches another"),
        "relief": ("cir.designer_notes", "the lattice is a relief"),
        "stripe": ("candidate.what_it_is", "the colour changes every two rows: a two-row "
                                           "stripe"),
    },
    "hexagon-coaster-set": {},
}

# Inflections a licensed word carries with it ("stripe" licenses "striped").
LICENCE_FORMS: dict[str, tuple[str, ...]] = {"stripe": ("striped", "stripes")}

# Category synonyms the repo's own category vocabulary already treats as the same object
# (`commerce.category.CATEGORY_NODE_TERMS`): licensed only where the listing's object is one.
CATEGORY_SYNONYMS: dict[str, tuple[str, str]] = {
    "afghan": ("blanket", "commerce.category.CATEGORY_NODE_TERMS['blanket'].object"),
}


def _licence_source_text(cand, cir, path: str) -> str:
    if path == "candidate.title":
        return cand.title or ""
    if path == "candidate.what_it_is":
        return cand.what_it_is or ""
    if path == "cir.designer_notes":
        return getattr(cir, "designer_notes", "") or ""
    raise KeyError(path)


def for_product(cand) -> ProductFacts:
    """Facts for one Launch-0 *product* (every variant it sells), for a single listing.

    - vocabulary = words true of EVERY variant (intersection), plus variant/size words, plus
      the licensed product-record words (each checked against its source text), plus the
      category synonyms the repo already treats as the same object.
    - numbers that differ by variant (width/height) are reported per variant in
      `variant_labels`; the product-level width/height are None (no single size is true).
    - `cir`/`twin` are the first variant's, for the product-type / colourwork gates; callers
      that need every variant's gates run them over `variant_facts`.
    """
    from ..commerce import category as category_mod

    variants = [for_variant(cand, v) for v in cand.variants]
    base = variants[0]
    if len(variants) == 1:
        vocab = dict(base.vocabulary)
    else:
        shared = set(base.vocabulary)
        for f in variants[1:]:
            shared &= set(f.vocabulary)
        vocab = {w: base.vocabulary[w] for w in sorted(shared)}
        n = len(variants)
        _add(vocab, f"size sizes {n} " + " ".join(v.key for v in cand.variants),
             "variants")
    for word, (path, why) in PRODUCT_LICENCES.get(cand.slug, {}).items():
        text = _licence_source_text(cand, base.cir, path).lower()
        if word in words(text) or stem(word) in {stem(w) for w in words(text)}:
            for form in {word, stem(word), *LICENCE_FORMS.get(word, ())}:
                vocab.setdefault(form, f"product_record:{path} ({why})")
    for syn, (obj, src) in CATEGORY_SYNONYMS.items():
        if obj in base.nouns and syn in category_mod.CATEGORY_NODE_TERMS.get(
                obj, {}).get("object", ()):
            vocab.setdefault(syn, src)
    if len(base.colors) == 2:
        _add(vocab, "two color colour", "cir.colors (two colours)")
    labels = [f"{v.key}: {v.label}" for v in cand.variants]
    out = ProductFacts(
        slug=cand.slug, candidate=cand.slug, cir_title=cand.title,
        kind=base.kind, category=base.category, nouns=list(base.nouns),
        qualifiers=list(base.qualifiers), techniques=list(base.techniques),
        difficulty=base.difficulty, colors=list(base.colors),
        colour_families=list(base.colour_families), materials=list(base.materials),
        stitches=sorted({s for f in variants for s in f.stitches}),
        width_cm=base.width_cm if len(variants) == 1 else None,
        height_cm=base.height_cm if len(variants) == 1 else None,
        makes=base.makes, season=base.season, variant_labels=labels, vocabulary=vocab,
        cir=base.cir, twin=base.twin)
    out.variant_facts = variants          # type: ignore[attr-defined]
    return out


def launch0_product_facts() -> list[ProductFacts]:
    """One ProductFacts per Launch-0 product (baskets are one product with three sizes)."""
    from ..products import launch0 as L

    return [for_product(L.candidate(slug)) for slug in L.LAUNCH0_SLUGS]
