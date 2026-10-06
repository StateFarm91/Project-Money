"""Truthfulness and voice lint for every customer-facing store string.

The bar the owner set is "does Brambleloop look like a premium shop that has existed for
years?" -- and the cheapest way to fake that is exactly what the non-negotiables forbid:
"since 2014", "thousands of happy makers", "5-star", "tested by our testers", "my
grandmother taught me". This lint exists so the answer can only be reached through craft.

Deterministic, closed vocabulary, no model. Each rule names a class of claim this company
cannot currently support. The rules are deliberately about *claims*, not tone: "premium" is a
positioning word and passes; "the best crochet patterns on Etsy" is a comparative claim
nobody measured and fails.

Negation is respected inside a short window, because the shop's own disclosures say true
negative things ("no sample has been photographed", "not a photograph") that a naive
pattern would read as the claim they deny.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TRUTH = "truth"
VOICE = "voice"


@dataclass(frozen=True)
class Rule:
    code: str
    kind: str
    pattern: re.Pattern
    why: str
    negatable: bool = False


def _r(expr: str) -> re.Pattern:
    return re.compile(expr, re.I)


TRUTH_RULES: tuple[Rule, ...] = (
    Rule("TRUTH_YEARS_IN_BUSINESS", TRUTH,
         _r(r"\b(since|est\.?|established(?: in)?|founded(?: in)?)\s+(19|20)\d{2}\b"
            r"|\b\d+\+?\s+years?\s+(of|in)\b|\bdecades?\b|\byears of experience\b"
            r"|\bfor (many )?years\b|\blong[- ]established\b|\btime[- ]tested\b"),
         "a years-in-business or experience claim; the shop opened in 2026 and has no "
         "trading history to cite"),
    Rule("TRUTH_SUPERLATIVE", TRUTH,
         _r(r"\b(the )?best\b(?![- ]?(fit|for you))|#\s?1\b|\bnumber one\b|\bworld[- ]class\b"
            r"|\bfinest\b|\btop[- ]rated\b|\bhighest[- ]quality\b|\bunbeatable\b"
            r"|\baward[- ]winning\b|\bleading\b|\bmost popular\b|\bbest[- ]?sell(er|ing)\b"
            r"|\bunrivall?ed\b|\bunmatched\b"),
         "an unverifiable superlative or comparative; nothing measured supports it"),
    Rule("TRUTH_SOCIAL_PROOF", TRUTH,
         _r(r"\b\d[\d,.]*[ ]?(k|\+)?[ ]?(sales|orders|customers|buyers|makers|reviews"
            r"|downloads|happy|five[- ]star|5[- ]star)\b|\b(5|five)[- ]stars?\b"
            r"|\b(thousands|hundreds|millions) of\b|\bloved by\b|\btrusted by\b"
            r"|\bcustomer (favou?rite|favou?rites)\b|\bstar seller\b|\bas seen (in|on)\b"
            r"|\bfeatured (in|on|by)\b|\bfan[- ]favou?rite\b|\bhighly rated\b"),
         "a sales, review, customer-count or endorsement claim; the shop has no sales and "
         "no reviews, and inventing them is a non-negotiable violation"),
    Rule("TRUTH_FOUNDER_STORY", TRUTH,
         _r(r"\b(my|our) (grand)?(mother|mum|mom|nan|nana|granny|grandma|family)\b"
            r"|\bi (learned|learnt|taught myself) to crochet\b|\bfounded by\b|\bour founder\b"
            r"|\bsince i was\b|\blifelong\b|\bgenerations?\b|\bfamily[- ]run\b"
            r"|\bmy (kitchen table|studio in)\b"),
         "a founder-history or personal-story claim nobody has supplied as true"),
    Rule("TRUTH_PHYSICAL_MAKING", TRUTH,
         _r(r"\btested by (our )?(pattern )?testers\b|\btest[- ]crochet(ed|ers)?\b"
            r"|\bpattern[- ]tested\b|\btester[- ]approved\b|\bhand[- ]?made by\b"
            r"|\bmade by hand\b|\bwe crocheted\b|\bphotographed\b|\b(our|real|actual) photos?\b"
            r"|\bphotos? of (the|our|my) (finished|sample)\b|\bworked samples?\b"),
         "a physical-making or photography claim; no sample has been made and the images "
         "are disclosed renders", negatable=True),
    Rule("TRUTH_SCARCITY", TRUTH,
         _r(r"\blimited time\b|\bonly \d+ left\b|\bselling fast\b|\bhurry\b"
            r"|\bsale ends\b|\bwhile stocks last\b|\b\d+% off\b|\bdon'?t miss out\b"),
         "a scarcity or discount urgency claim; a digital pattern has no stock and no sale "
         "is authorised"),
    Rule("TRUTH_SAFETY_CERT", TRUTH,
         _r(r"\bsafety[- ]certified\b|\bguaranteed safe\b|\bchild[- ]safe\b|\bbaby[- ]safe\b"
            r"|\blab[- ]tested\b|\bcpsc\b|\bcertified organic\b|\bhypoallergenic\b"),
         "a safety or certification claim about a finished object this shop does not make",
         negatable=True),
)

# The bible's banned filler words (`brand.bible._BANNED_IN_NAMES`) applied to prose, plus the
# marketplace tics that make a shop read as generated: exclamation marks and emoji.
_ACRONYMS = frozenset({"PDF", "PDFS", "AI", "US", "UK", "CAD", "CASL", "PIPEDA", "GST", "HST",
                       "FAQ", "EU", "VAT", "CRA", "BRAMBLELOOP", "STUDIO", "CA"})


def _voice_rules() -> tuple[Rule, ...]:
    from ..brand import bible

    return (
        Rule("VOICE_FILLER", VOICE, bible._BANNED_IN_NAMES,
             "marketplace filler the brand bible bans in names; it reads as a generic shop"),
        Rule("VOICE_EXCLAMATION", VOICE, re.compile(r"!"),
             "exclamation marks; the brand voice is calm and specific"),
        Rule("VOICE_EMOJI", VOICE,
             re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]"),
             "emoji; the brand voice carries no decoration in text"),
    )


VOICE_RULES: tuple[Rule, ...] = _voice_rules()

_NEGATORS = re.compile(r"\b(no|not|never|nor|without|isn'?t|aren'?t|hasn'?t|haven'?t|"
                       r"wasn'?t|weren'?t|cannot|can'?t|n'?t)\b", re.I)


def _negated(text: str, start: int) -> bool:
    """A negator within the six words before the match, inside the same sentence."""
    before = text[:start]
    sentence = re.split(r"[.;:!?\n]", before)[-1]
    window = " ".join(sentence.split()[-6:])
    return bool(_NEGATORS.search(window))


def lint(text: str, *, surface: str = "", voice: bool = True) -> list[dict]:
    """Every truthfulness (and, optionally, voice) finding in one string."""
    out: list[dict] = []
    text = text or ""
    rules = TRUTH_RULES + (VOICE_RULES if voice else ())
    for rule in rules:
        for m in rule.pattern.finditer(text):
            if rule.negatable and _negated(text, m.start()):
                continue
            out.append({"code": rule.code, "kind": rule.kind,
                        "severity": "fail" if rule.kind == TRUTH else "warn",
                        "surface": surface, "match": m.group(0),
                        "detail": f"{surface}: {m.group(0)!r} -- {rule.why}"})
    if voice:
        for word in re.findall(r"\b[A-Z]{5,}\b", text):
            if word not in _ACRONYMS:
                out.append({"code": "VOICE_SHOUTING", "kind": VOICE, "severity": "warn",
                            "surface": surface, "match": word,
                            "detail": f"{surface}: {word!r} -- capitals as emphasis"})
    return out


def is_truthful(text: str) -> bool:
    return not [f for f in lint(text, voice=False) if f["kind"] == TRUTH]
