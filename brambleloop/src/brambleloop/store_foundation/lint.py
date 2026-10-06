"""Truthfulness and voice lint for every customer-facing store string.

The bar the owner set is "does Brambleloop look like a premium shop that has existed for
years?" -- and the cheapest way to fake that is exactly what the non-negotiables forbid:
"since 2014", "thousands of happy makers", "5-star", "tested by our testers", "my
grandmother taught me". This lint exists so the answer can only be reached through craft.

Deterministic, closed vocabulary, no model. Each rule names a class of claim this company
cannot currently support. The rules are deliberately about *claims*, not tone: "premium" is a
positioning word and passes; "the best crochet patterns on Etsy" is a comparative claim
nobody measured and fails.

Text is normalised first (NFKC, zero-width characters stripped, common homoglyphs folded,
letter-spaced words joined) so a disguised spelling is the claim it spells. Negation is
respected inside a short window of the same clause, because the shop's own disclosures say true
negative things ("no sample has been photographed", "not a photograph") that a naive
pattern would read as the claim they deny.
"""
from __future__ import annotations

import re
import unicodedata
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


# Spelled-out quantities, so "fifteen years" and "over five hundred sold" read as the numbers
# they are (J-product P-3).
_NUMWORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen"
            r"|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty"
            r"|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|dozens?|a dozen"
            r"|a few|several|many|countless|a couple of)")
_NUM = rf"(?:\d[\d,.]*[ \t]*(?:k\b)?|{_NUMWORD}(?:[- ](?:{_NUMWORD}|and))*)"

TRUTH_RULES: tuple[Rule, ...] = (
    Rule("TRUTH_YEARS_IN_BUSINESS", TRUTH,
         _r(r"\b(since|est\.?|established(?: in)?|founded(?: in)?)[ \t]+(19|20)\d{2}\b"
            r"|\b\d+\+?[ \t]+years?[ \t]+(of|in)\b|\bdecades?\b|\byears of experience\b"
            r"|\bfor (many )?years\b|\blong[- ]established\b|\btime[- ]tested\b"
            rf"|\b(since|est\.?|established|founded|opened|started)[ \t]+(in[ \t]+)?(the[ \t]+)?"
            rf"((early|late|mid)[- ])?((19|20)\d{{2}}s?|'?\d0s|nineteen|two thousand|{_NUMWORD})\b"
            # "N years" as experience, never an age ("under 3 years", "3 years and up").
            rf"|(?<!under )(?<!aged )(?<!ages )(?<!age )(?<!than )(?<!to )(?<!-)"
            rf"\b(over |more than |almost |nearly )?{_NUM}\+?[ \t]+years?\b"
            r"(?![ \t]+(old|of age|and (up|over|older)|\+|or (older|over|under|younger)))"
            r"|\bin business\b|\bbeen around\b|\bsince the (early |very )?(days|beginning|start)\b"
            r"|\bexperienced (designer|maker|crocheter|shop)s?\b|\bveteran\b"),
         "a years-in-business or experience claim; the shop opened in 2026 and has no "
         "trading history to cite"),
    Rule("TRUTH_SUPERLATIVE", TRUTH,
         _r(r"\b(the )?best\b(?![- ]?(fit|for you))|#[ \t]?1\b|\bnumber one\b|\bworld[- ]class\b"
            r"|\bfinest\b|\btop[- ]rated\b|\bhighest[- ]quality\b|\bunbeatable\b"
            r"|\baward[- ]winning\b|\bleading\b|\bmost popular\b|\bbest[- ]?sell(er|ing)\b"
            r"|\bunrivall?ed\b|\bunmatched\b"
            r"|\btop[- ](quality|notch|seller|selling|pick)\b|\bmost[- ](loved|popular|wanted"
            r"|requested|downloaded)\b|\betsy'?s? (choice|pick)\b|\beditor'?s? (choice|pick)\b"
            r"|\bbeloved\b|\b(everyone|everybody|buyers?|customers?|makers?|crocheters?)'?s?'? "
            r"favou?rites?\b"),
         "an unverifiable superlative or comparative; nothing measured supports it"),
    Rule("TRUTH_SOCIAL_PROOF", TRUTH,
         _r(r"\b\d[\d,.]*[ ]?(k|\+)?[ ]?(sales|orders|customers|buyers|makers|reviews"
            r"|downloads|happy|five[- ]star|5[- ]star)\b|\b(5|five)[- ]stars?\b"
            r"|\b(thousands|hundreds|millions) of\b|\bloved by\b|\btrusted by\b"
            r"|\bcustomer (favou?rite|favou?rites)\b|\bstar seller\b|\bas seen (in|on)\b"
            r"|\bfeatured (in|on|by)\b|\bfan[- ]favou?rite\b|\bhighly rated\b"
            # ratings and stars, in digits or words
            rf"|\brated\b|\bratings?\b|\b{_NUM}(\.\d+)?[ \t]*(out of (5|five)[ \t]*)?stars?\b"
            r"|\b\d(\.\d+)?[ \t]*/[ \t]*(5|10)\b|[★⭐✩✪✫✬✭✮✯]"
            # sales / units sold, in digits or words
            rf"|\b{_NUM}\+?[ \t]+(\w+[ \t]+){{0,2}}(sold|purchased|downloaded|bought)\b"
            r"|\b(units|copies|patterns) sold\b|\bsold (over|more than)\b"
            rf"|\b(over |more than )?{_NUM}\+?[ \t]+(happy |satisfied )?(sales|orders|customers"
            r"|buyers|makers|crocheters|reviews|downloads|fans|followers)\b"
            # endorsement without a number
            r"|\b(customers?|buyers?|makers?|crocheters?|everyone|people) (love|adore|rave)"
            r"|\btrusted\b|\bglowing\b|\brave reviews?\b|\bpopular\b|\bbest[- ]loved\b"),
         "a sales, review, customer-count or endorsement claim; the shop has no sales and "
         "no reviews, and inventing them is a non-negotiable violation"),
    Rule("TRUTH_FOUNDER_STORY", TRUTH,
         _r(r"\b(my|our) (grand)?(mother|mum|mom|nan|nana|granny|grandma|family)\b"
            r"|\bi (learned|learnt|taught myself) to crochet\b|\bfounded by\b|\bour founder\b"
            r"|\bsince i was\b|\blifelong\b|\bgenerations?\b|\bfamily[- ]run\b"
            r"|\bmy (kitchen table|studio in)\b|\bpassed down\b|\bheirloom recipe\b"),
         "a founder-history or personal-story claim nobody has supplied as true"),
    Rule("TRUTH_PHYSICAL_MAKING", TRUTH,
         _r(r"\btested by (our )?(pattern )?testers\b|\btest[- ]crochet(ed|ers)?\b"
            r"|\bpattern[- ]tested\b|\btester[- ]approved\b|\bhand[- ]?made by\b"
            r"|\bmade by hand\b|\bwe crocheted\b|\bphotographed\b|\b(our|real|actual) photos?\b"
            r"|\bphotos? of (the|our|my) (finished|sample)\b|\bworked samples?\b"
            # Brand truth: Brambleloop sells digital pattern designs; nothing it sells is
            # handmade by it, and no sample has been made or tested.
            r"|\bhand[- ]?made\b|\bhand[- ]?(crocheted|knit|knitted|stitched|crafted|sewn)\b"
            r"|\bsamples? (shown|pictured)\b|\btested by\b"
            r"|\bwe(?: have| ve|'ve)? (personally )?(tested|crocheted|made|stitched|knitted"
            r"|photographed|worked)\b|\b(crocheted|made|tested) (it|this|these|them) "
            r"(ourselves|myself)\b|\bmade with love\b"),
         "a physical-making or photography claim; no sample has been made and the images "
         "are disclosed renders", negatable=True),
    # D-FB-11..13: Laura is a persistent AI person and Brambleloop's Founder/CEO. Publicly she
    # is named with the AI disclosure ("Brambleloop's AI founder"); she is never claimed to be
    # biologically human, given human experiences, made the physical maker/designer/tester,
    # or used to state legal ownership or who the seller of record is.
    Rule("TRUTH_LAURA_HUMAN_CLAIM", TRUTH,
         _r(r"\blaura(?:'s)?[ \t]+(?:(?:personally|herself|lovingly|carefully|also|always|"
            r"has|had|first|still|once|herself)[ \t]+)*(?:hand[- ]?)?(?:crochets|crocheted"
            r"|crocheting|knits|knitted|stitches|stitched|designs|designed|tests|tested"
            r"|founded|owns|owned|runs|ran|makes|made|grew up|was born|lives|lived|learned"
            r"|learnt|taught)\b"
            r"|\b(?:designed|crocheted|hand[- ]?crocheted|made|tested|stitched|knitted"
            r"|founded|owned|run|created|written|photographed|worked)[ \t]+by[ \t]+laura\b"
            r"|\b(?:our|the)[ \t]+(?:founder|owner|designer|maker|tester|pattern designer)"
            r"[ \t,]+laura\b|\blaura[ \t]*,[ \t]*(?:our|the)[ \t]+(?:founder|owner|"
            r"designer|maker|tester)\b"
            # Founder/CEO wording only with AI disclosure (D-FB-13), and never a legal
            # ownership or seller-of-record statement made in Laura copy.
            r"|\blaura(?:[ \t]+is|[ \t]*,)[ \t]+(?:the|our|brambleloop'?s|a)[ \t]+"
            r"(?:co-?founder|founder|ceo|chief executive|owner|legal owner|seller|proprietor)\b"
            r"|(?<!ai )\b(?:founder|ceo|owner|co-?founder)[ \t]+laura\b"
            r"|\b(?:owned|operated|sold)[ \t]+by[ \t]+laura\b"
            r"|\blaura[ \t]+(?:is|was)[ \t]+(?:a[ \t]+)?(?:real|human|biologically human)"
            r"(?:[ \t]+(?:person|woman|human|designer|maker))?\b"
            r"|\bi[ \t]+(?:crochet|knit|stitch|grew up|was born|live in|lived in|learned"
            r"|learnt|hand[- ]?crochet|test every|tested every|design every|made every)\b"
            r"|\bmy[ \t]+(?:childhood|hometown|husband|kids|children|daughter|son"
            r"|grandmother|grandma|mother|mum|mom|family|home town)\b"
            r"|\bwhen i was (?:a )?(?:little|young|child|girl|kid)\b"),
         "a claim that Laura is human or has human experiences, that she physically made, "
         "designed or tested anything, an undisclosed founder/CEO claim, or a legal-ownership "
         "or seller statement. She is Brambleloop's AI founder (D-FB-13): say so, with the AI "
         "disclosure", negatable=True),
    Rule("TRUTH_SCARCITY", TRUTH,
         _r(r"\blimited time\b|\bonly \d+ left\b|\bselling fast\b|\bhurry\b"
            r"|\bsale ends\b|\bwhile stocks last\b|\b\d+% off\b|\bdon'?t miss out\b"
            rf"|\bonly ({_NUM}|a (few|handful)) (left|remaining|available)\b|\blast chance\b"
            r"|\blimited\b(?![ \t]+(personal|licen[cs]e|non[- ]commercial|use|right))"
            r"|\b(almost|nearly) (gone|sold out)\b|\bsold out\b|\bact now\b|\btoday only\b"
            rf"|\bsave[ \t]+({_NUM}|\d+)[ \t]*(%|percent|per cent)|\b{_NUM}[ \t]*(percent|per cent) off\b"
            r"|\bhalf[- ]price\b|\b(on )?sale (today|now|this week)\b|\bflash sale\b"
            r"|\bdiscount(ed)?\b"),
         "a scarcity or discount urgency claim; a digital pattern has no stock and no sale "
         "is authorised"),
    Rule("TRUTH_SAFETY_CERT", TRUTH,
         _r(r"\bsafety[- ]certified\b|\bguaranteed safe\b|\bchild[- ]safe\b|\bbaby[- ]safe\b"
            r"|\blab[- ]tested\b|\bcpsc\b|\bcertified organic\b|\bhypoallergenic\b"
            r"|\bsafe (for|around) (babies|baby|infants?|newborns?|children|kids|toddlers)\b"
            r"|\bnon[- ]?toxic\b|\boeko[- ]?tex\b|\b\w+[- ]certified\b|\bcertified\b"
            r"|\bsafety[- ]tested\b|\bdermatologi(st|cally)[- ]tested\b|\bbpa[- ]free\b"),
         "a safety or certification claim about a finished object this shop does not make; "
         "it needs evidence the shop does not hold", negatable=True),
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
        Rule("VOICE_DOUBLE_HYPHEN", VOICE, re.compile(r" -- "),
             "a typewriter double hyphen where a premium shop sets a dash; Etsy shows it "
             "verbatim"),
        Rule("VOICE_EMOJI", VOICE,
             re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]"),
             "emoji; the brand voice carries no decoration in text"),
    )


VOICE_RULES: tuple[Rule, ...] = _voice_rules()

_NEGATORS = re.compile(r"\b(no|not|never|nor|without|isn'?t|aren'?t|hasn'?t|haven'?t|"
                       r"wasn'?t|weren'?t|cannot|can'?t|n'?t)\b", re.I)

# "Handmade" as the customer's aspiration, not the shop's product (owner decision, wave 3
# lane C, 2026-10-06). Brambleloop sells digital patterns and makes nothing by hand, so
# "handmade" stays refused as a description of anything the shop sells. The one reading the
# owner allowed is the life or home the customer makes with a pattern: "Patterns for a More
# Handmade Life", "for your handmade home". The exemption is deliberately narrow:
#   - a customer-side determiner must come first ("a", "your", "a more", "more");
#     "our", "my", "Brambleloop's" and bare "handmade" never qualify;
#   - the noun must be the customer's life or home, not a product word;
#   - the noun must not head a product phrase, so "a handmade home collection" and "your
#     handmade home decor" are still read as the claims they make; "a handmade life, made by
#     us" is caught by its own "made by" match.
# Any other physical-making wording in the same text is still caught by the rest of the rule.
_PRODUCT_NOUNS = (r"d[eé]cor|goods|wares|items?|products?|patterns?|gifts?|collections?|range"
                  r"|lines?|sets?|kits?|bundles?|pieces?|accessor(?:y|ies)|crochet|knits?"
                  r"|toys?|blankets?|baskets?|textiles?|furnishings?|shop|store|studio"
                  r"|brand|made|crafted|by|from|sold|listings?|downloads?|pdfs?|designs?")
_ASPIRATIONAL_HANDMADE = re.compile(
    r"(?:\b(?:a|your)[ \t]+(?:more[ \t]+)?|\bmore[ \t]+)"
    r"(?P<hm>hand[- ]?made)[ \t]+(?:life|lives|living|home|homes)\b"
    rf"(?![ \t]*[-/&+]?[ \t]*(?:{_PRODUCT_NOUNS})\b)", re.I)


def _aspirational_handmade(view: str, m: re.Match) -> bool:
    """True when this TRUTH_PHYSICAL_MAKING match is only the word "handmade" inside the
    customer-aspiration phrase above (and nothing else in the match)."""
    if not re.fullmatch(r"hand[- ]?made", m.group(0), re.I):
        return False
    return any(a.start("hm") == m.start() and a.end("hm") == m.end()
               for a in _ASPIRATIONAL_HANDMADE.finditer(view))


# A negation only reaches the words of its own clause: a comma, a dash or a conjunction ends
# it, so "Not a toy, we crocheted this" and "we never skip it and these are baby safe" are
# read as the claims they make (J-product P-3).
_CLAUSE_BREAK = re.compile(r"[.;:!?,\n()–—]| - |\b(and|but|yet|so|while|whereas|"
                           r"although|though|because|always|however|instead)\b", re.I)
_NEGATION_WINDOW = 4

# Format characters (zero-width space/joiner, soft hyphen) are stripped; NFKC folds fullwidth
# and compatibility letters; these homoglyphs NFKC leaves alone are folded by hand.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
    "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "Х": "X", "У": "Y", "Ѕ": "S", "І": "I", "Ј": "J",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o", "ν": "v",
    "α": "a", "ι": "i", "κ": "k", "ρ": "p", "τ": "t", "υ": "u",
    "Ƅ": "b", "ƅ": "b", "Ь": "b", "ь": "b", "ɓ": "b", "ᖯ": "b", "ß": "ss",
    "ɑ": "a", "ǝ": "e", "ɩ": "i", "ı": "i", "ȷ": "j", "ʟ": "l", "ɴ": "n", "ʀ": "r",
    "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ᴢ": "z", "ᴀ": "a", "ʙ": "b",
    "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k",
    "ᴍ": "m", "ᴏ": "o", "ᴘ": "p", "ǫ": "q",
    "’": "'", "‘": "'", "‐": "-", "‑": "-",
})


def normalise(text: str) -> str:
    """The text a buyer reads, in the letters the rules are written in.

    NFKC (fullwidth, superscript and compatibility forms), zero-width and other format
    characters stripped, common Cyrillic/Greek/IPA homoglyphs folded to Latin.
    """
    folded = unicodedata.normalize("NFKC", text or "")
    folded = "".join(c for c in folded if unicodedata.category(c) != "Cf")
    folded = folded.translate(_CONFUSABLES)
    # Superscript capitals NFKC leaves as small capitals or modifier letters.
    return unicodedata.normalize("NFKC", folded)


def _despaced(text: str) -> str:
    """'b e s t' and 'b.e.s.t' read as 'best': runs of single letters are joined."""
    return re.sub(r"\b(?:[A-Za-z][ .\-_*]+){2,}[A-Za-z]\b",
                  lambda m: re.sub(r"[ .\-_*]+", "", m.group(0)), text)


def _negated(text: str, start: int) -> bool:
    """A negator within the few words before the match, inside the same clause."""
    before = text[:start]
    clause = _CLAUSE_BREAK.split(before)[-1] or ""
    window = " ".join(clause.split()[-_NEGATION_WINDOW:])
    return bool(_NEGATORS.search(window))


def lint(text: str, *, surface: str = "", voice: bool = True) -> list[dict]:
    """Every truthfulness (and, optionally, voice) finding in one string.

    Truth rules run over the normalised text and over a de-spaced view of it, so fullwidth,
    zero-width, homoglyph and letter-spaced spellings of a banned claim are caught. Voice rules
    run over the text as written (they are about how it is typed).
    """
    out: list[dict] = []
    raw = text or ""
    norm = normalise(raw)
    views = [norm]
    despaced = _despaced(norm)
    if despaced != norm:
        views.append(despaced)
    seen: set[tuple[str, str]] = set()
    for rule in TRUTH_RULES:
        for view in views:
            for m in rule.pattern.finditer(view):
                if rule.negatable and _negated(view, m.start()):
                    continue
                if rule.code == "TRUTH_PHYSICAL_MAKING" and _aspirational_handmade(view, m):
                    continue
                if (rule.code, m.group(0).lower()) in seen:
                    continue
                seen.add((rule.code, m.group(0).lower()))
                out.append({"code": rule.code, "kind": rule.kind, "severity": "fail",
                            "surface": surface, "match": m.group(0),
                            "detail": f"{surface}: {m.group(0)!r} -- {rule.why}"})
    if norm != raw and norm.lower() != raw.lower():
        hidden = sorted({c for c in raw if c not in norm})[:8]
        if hidden and any(unicodedata.category(c).startswith("L")
                          or unicodedata.category(c) == "Cf" for c in hidden):
            out.append({"code": "TRUTH_OBFUSCATED_TEXT", "kind": TRUTH, "severity": "fail",
                        "surface": surface, "match": "".join(hidden),
                        "detail": f"{surface}: {hidden!r} -- lookalike, fullwidth or "
                                  f"zero-width characters; customer copy is written in plain "
                                  f"letters so every claim in it can be checked"})
    if voice:
        for rule in VOICE_RULES:
            for m in rule.pattern.finditer(raw):
                out.append({"code": rule.code, "kind": rule.kind, "severity": "warn",
                            "surface": surface, "match": m.group(0),
                            "detail": f"{surface}: {m.group(0)!r} -- {rule.why}"})
        for word in re.findall(r"\b[A-Z]{5,}\b", raw):
            if word not in _ACRONYMS:
                out.append({"code": "VOICE_SHOUTING", "kind": VOICE, "severity": "warn",
                            "surface": surface, "match": word,
                            "detail": f"{surface}: {word!r} -- capitals as emphasis"})
    return out


def is_truthful(text: str) -> bool:
    return not [f for f in lint(text, voice=False) if f["kind"] == TRUTH]
