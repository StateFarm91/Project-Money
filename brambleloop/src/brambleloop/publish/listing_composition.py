"""Listing copy as a composition of closed, code-generated sentences (ENG-ETSY-AI-FIX3, H1).

The delta review of ENG-ETSY-AI-FIX found the lexical guard (`etsy_ai_policy.claims`) still
losing to the next phrasing: "No AI used. 100% human.", "Pattern by Emily Smith", "From my
hook to yours", "I desgined". A bigger blacklist loses to the phrase after that. So the
listing title and description are read as a COMPOSITION, and every unit of it must be one of:

1. **an honest statement** -- a sentence from the closed allowlist
   (`etsy_ai_policy.honest_statements`): the only source of any statement about who designed,
   made, wrote, tested or photographed the product, and of the AI disclosure;
2. **a template** -- a code-generated line from the closed set below (`TEMPLATES`), whose
   fixed words are the generator's own and whose slots carry product facts from the CIR and
   the certificate (title, size, yarn weight, hook/gauge, skill, contents, US/UK editions).
   The fixed words of a template may mention making ("Why it is worth making") because the
   template is code; the SLOT values may not -- each slot is validated as free text;
3. **constrained free text** -- anything else, including LLM-drafted marketing prose, a
   concept premise or a tag phrase. It may carry no authorship content at all. It is refused
   if EITHER
     a. the lexical backstop (`etsy_ai_policy.claims`) finds a claim, or
     b. the independent topic rule (`topics`) finds that it MENTIONS design, creation,
        making, testing, photos, samples, AI or humans at all -- true or not, claim or not.
   "Make a handmade gift" and "Designed for beginners" are refused by (b): fail closed. The
   refusal is a hold card with its reason (`etsy_ai_policy.hold_card`), so a false positive
   reaches the owner rather than a log.

Nothing here rewrites copy, satisfies another gate, or states human authorship.
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import etsy_ai_policy as _eap

# ---- (b) the independent topic rule ----------------------------------------------------
# Read on the normalised forms (`etsy_ai_policy.forms`: NFKC, case, accents, zero-width,
# look-alikes, leet, spacing and joiners), so the Unicode tricks the lexical guard already
# defeats do not reach a different answer here.
TOPICS: tuple[tuple[str, str], ...] = (
    ("design", r"\bdesign\w*|\bredesign\w*"),
    ("creation", r"\bcreat\w*|\boriginal\w*|\bconceiv\w*|\bconcept\w*|\binvent\w*|\bdream\w*|"
                 r"\bdevis\w*|\bimagin\w*|\benvision\w*|\binspir\w*|\bauthor\w*|\bwrote\b|"
                 r"\bwriters?\b|\bwritten by\b|\bdr(?:ew|awn|awing|awings)\b|\billustrat\w*|"
                 r"\bsketch\w*|\b(?:my|our|their|his|her) own\b|\bcurat\w*"),
    # "craft"/"crafts" alone is the hobby ("yarn craft project", a real tag); every form that
    # says somebody crafted something is a topic.
    ("making", r"\bma(?:ke|kes|de|king|kers?)\b|\bmanufactur\w*|\bcraft(?:ed|ing|er|ers|sman\w*|"
               r"swoman\w*|smanship|y)\b|\bhandcraft\w*|\bartisan\w*|"
               r"\bhand ?(?:made|maid|ma\w+|crafted|spun|dyed|drawn|done|written|knit\w*|"
               r"crochet\w*|stitch\w*|sewn|finish\w*|work\w*|picked|select\w*)\b|"
               r"\bhome ?(?:made|spun|grown)\b|\bby hand\b|\bcrocheted\b|\bknitted\b|"
               r"\bstitched\b|\bsewn\b|\bspun\b|\bbuilt\b|\bproduc(?:ed|er|ers|tion)\b|"
               r"\bstudio\b|\bworkshop\b|\batelier\b|\bsmall batch\b|"
               r"\b(?:my|our) (?:\w+ )?(?:hooks?|needles?|hands?|sketchbook)\b"),
    ("testing", r"\btest\w*|\btri(?:ed|al|als|alled|aled)\b|\bproof\w*|\bverif\w*|"
                r"\bcheck(?:ed|s|ing)?\b|\bvalidat\w*|\bvetted\b|\bquality\b|\bqc\b|"
                r"\bapproved\b|\breviewed\b|\bguarantee\w*|\bcertif\w*"),
    ("photos", r"\bphoto\w*|\bpictur\w*|\bpics?\b|\bimage\w*|\bshots?\b|\bcamera\w*|"
               r"\bsnapp\w*|\brender\w*"),
    ("samples", r"\bsamples?\b|\bswatch\w*|\bprototyp\w*|\bmock ?ups?\b"),
    ("AI", r"\bai\b|\ba i\b|\bartificial\b|\bintelligen\w*|\bmachines?\b|\bgenerat\w*|"
           r"\balgorithm\w*|\bautomat\w*|\brobot\w*|\bcomputer\w*|\bsoftware\b|"
           r"\b(?:chat ?)?gpt\b|\bllms?\b|\bneural\b|\bmodels?\b"),
    ("humans", r"\bhumans?\b|\bperson\w*|\bpeople\b|\bmyself\b|\bourselves\b|"
               r"\byours truly\b|\bman ?made\b|\bfounders?\b|\bteam\b|\bstaff\b|"
               r"\bfamily\b|\bgrandm\w*|\bmum\b|\bmom\b|\bcrocheters?\b|\bknitters?\b|"
               r"\bartists?\b|\bbehind\b|\bindependent\w*|\bself\b|\bi m\b|\bive\b|"
               r"\b(?:i|we) (?:am|are)\b"),
    # "Pattern by Emily Smith", "By Jane.": an attribution names somebody, whatever word
    # carries it. The excluded continuations are measurements, never people.
    ("humans", r"\bby (?!(?:row|rows|round|rounds|rnd|rnds|step|steps|one|side|size|sizes|"
               r"colou?rs?|weight|length|width|height|measurement|number|the gauge|"
               r"\d+)\b)\w+"),
)
_TOPICS = tuple((label, re.compile(rx)) for label, rx in TOPICS)


def topics(text: str) -> list[tuple[str, str]]:
    """(topic, word) for every mention of an authorship topic in `text`, plus misspellings."""
    found: dict[tuple[str, str], None] = {}
    for form in _eap.forms(text):
        for label, rx in _TOPICS:
            for m in rx.finditer(form):
                found[(label, m.group(0).strip())] = None
        for tok in _eap.misspelt(form):
            found[("misspelt authorship word", tok)] = None
    return sorted(found)


# ---- (3) the constrained-field validator -----------------------------------------------

def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[.!?;:\n]+(?=\s|$)", text or "") if x.strip()]


def constrained_problems(text: str, *, field: str = "free text") -> list[str]:
    """Refusals for a field that may carry no authorship content (marketing prose, a slot).

    Honest allowlisted sentences are removed first; each remaining sentence is refused on the
    lexical backstop or on the topic rule, with the sentence and the reason."""
    out: list[str] = []
    for sentence in _sentences(_eap._residue(text)):
        lexical = _eap.claims(sentence)
        hits = topics(sentence)
        if not (lexical or hits):
            continue
        why = []
        if lexical:
            why.append("lexical backstop: " + "; ".join(f"{label} ({phrase!r})"
                                                         for label, phrase in lexical[:4]))
        if hits:
            why.append("mentions " + ", ".join(sorted({t for t, _w in hits})) + " ("
                       + ", ".join(repr(w) for _t, w in hits[:6]) + ")")
        out.append(f"{_eap.CODE}: {field} sentence {sentence[:160]!r} is not an allowlisted "
                   f"honest statement or a listing template, and free text may not carry "
                   f"authorship, making, testing, photo, sample, AI or human content -- "
                   f"{' / '.join(why)}. Statements about who made, designed, tested or "
                   f"photographed a product come only from publish.etsy_ai_policy."
                   f"honest_statements (Etsy Help 44297885802647: sellers 'cannot "
                   f"misrepresent AI-generated work as handmade or entirely their own "
                   f"creation')")
    return out


# ---- (2) the closed template set -------------------------------------------------------

def _rx(fmt: str) -> str:
    """'Fixed words {slot} more words' -> a regex whose slots are named groups."""
    parts = re.split(r"\{(\w+)\}", fmt)
    return "".join(f"(?P<{p}>.+?)" if i % 2 else re.escape(p) for i, p in enumerate(parts))


def _value_rx() -> str:
    # seo.value_proposition, clause by clause; only the difficulty is a slot.
    return (r"Why it is worth making: (?:\d+ sizes in one pattern, )?"
            r"(?:worked in (?:a single colour|\d+ colours), )?"
            r"(?:written for an? (?P<difficulty>[\w -]+?) maker, )?"
            r"every row written out and charted, so you can follow whichever you prefer\.")


@lru_cache(maxsize=1)
def templates() -> tuple[tuple[str, re.Pattern], ...]:
    """The closed set: every line the listing generators emit, as (name, full-line regex).

    Product-fact slots are named groups; everything else is the generator's fixed words."""
    from ..commerce import terms as customer_terms
    from ..intel import childrens as ch

    lead = (r"(?P<title>.+?) — a crochet pattern, not a finished item\. You receive an instant "
            r"digital download\.(?: " + _value_rx() + ")?")
    fixed = {
        # commerce.seo.build_description
        "lead": lead,
        "opening": _rx("If you are searching for {phrases}, this is the one: every row is "
                       "written out and charted, and every stitch count is checked before "
                       "release."),
        "heading.what_you_get": re.escape("WHAT YOU GET"),
        "heading.details": re.escape("THE DETAILS"),
        "heading.technique_help": re.escape("TECHNIQUE HELP"),
        "heading.how_made": re.escape("HOW THIS PATTERN WAS MADE"),
        "heading.disclosures": re.escape("DISCLOSURES"),
        "heading.safety": re.escape("SAFETY AND SUITABILITY"),
        "heading.season": _rx("MAKING IT IN TIME FOR {season}"),
        "contents.rows_collapsed": re.escape(
            "- Written instructions row by row, with a stitch count on each — the repeated "
            "section is written once, the way a printed pattern does it, rather than retyped "
            "for every pass"),
        "contents.rows": re.escape("- Written instructions for every row, with a stitch "
                                   "count on each"),
        "contents.chart": re.escape("- A chart drawn from the same pattern as the written "
                                    "instructions, so the two always agree"),
        "contents.us_uk_editions": re.escape(
            "- Two PDFs, one in US terms and one in UK terms — the same pattern, each "
            "written throughout in its own terminology, with a stitch key to match"),
        "contents.pages": r"- (?P<pages>\d+)-page PDF, laid out to be readable on a phone or "
                          r"printed",
        "fact.size": _rx("- Finished size: {size}, worked at the gauge below"),
        "fact.skill": _rx("- Difficulty: {difficulty}"),
        "fact.yarn": r"- Yarn: (?P<yarn>.+?)(?: \((?P<weight>[\w -]+) weight\))?",
        "fact.fibre_unstated": re.escape(
            "- Fibre: as named above; the pattern does not specify a composition, so choose "
            "any yarn of the same weight that meets the gauge"),
        "fact.fibre": _rx("- Fibre: {fibre}"),
        "fact.gauge_hook": _rx("- Gauge: {gauge}"),
        "fact.stitches": _rx("- Stitches used: {stitches}"),
        "fact.colours": r"- Colours: \d+ \((?P<colours>.+)\)",
        "fact.yardage_estimate": (r"- Yarn quantities are estimates with a \+/-\d+% range, not "
                                  r"measurements\. Yarn use varies with yarn, hook and "
                                  r"tension\."),
        "season.start_early": re.escape(
            "Start early. A large piece takes real hours, and the whole point of buying the "
            "pattern now is having the weeks to make it."),
        "support.correction": re.escape(
            "If anything in it does not add up, tell us: we correct the pattern itself and "
            "send you the corrected file."),
        "safety.closing": re.escape(
            "The pattern itself carries the full set of safety notes for a children's item, "
            "each with its source, and states the date the guidance was compiled."),
        "help.link": r"- (?P<url>https://\S+)",
    }
    # commerce.terms, rendered for the listing (the heading is set in capitals by seo)
    rendered = customer_terms.render(customer_terms.BRAMBLELOOP_TERMS, "listing").split("\n")
    for i, line in enumerate(rendered):
        if line.strip():
            fixed[f"terms.{i}"] = re.escape(line.upper() if i == 0 else line)
    # intel.childrens statements, as seo.childrens_listing_block prints them
    for key, st in ch.STATEMENT_SET.items():
        body = _rx(" ".join(st.text.split()))
        fixed[f"childrens.{key}"] = re.escape(f"- {st.heading}: ") + body
    return tuple((name, re.compile(rx)) for name, rx in fixed.items())


def _match(line: str):
    for name, rx in templates():
        m = rx.fullmatch(line)
        if m:
            return name, m
    return None, None


# ---- the composition -------------------------------------------------------------------

def composition(text: str, *, field: str = "listing") -> list[dict]:
    """Every unit of the copy, classified: honest / template:<name> / free, with problems.

    A unit is a line; a title line is its " | " segments; a line that is no template is
    read sentence by sentence after the allowlisted sentences are taken out of it."""
    honest = set(_eap.honest_statements())
    units: list[dict] = []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        bare = line[2:] if line.startswith("- ") else line
        if bare in honest:
            units.append({"text": line, "kind": "honest", "problems": []})
            continue
        name, m = _match(line)
        if m is not None:
            problems = []
            for slot, value in m.groupdict().items():
                if value:
                    problems += constrained_problems(value, field=f"{field} slot {slot!r}")
            units.append({"text": line, "kind": f"template:{name}", "problems": problems})
            continue
        for segment in (s.strip() for s in line.split(" | ")):
            if not segment:
                continue
            residue = _eap._residue(segment)
            if residue.strip() != segment:
                units.append({"text": segment, "kind": "honest+free", "problems": []})
            for sentence in _sentences(residue):
                sname, sm = _match(sentence + ".") if not sentence.endswith(".") else (None,
                                                                                       None)
                if sm is None:
                    sname, sm = _match(sentence)
                if sm is not None:
                    problems = [p for slot, v in sm.groupdict().items() if v
                                for p in constrained_problems(v, field=f"{field} slot "
                                                                       f"{slot!r}")]
                    units.append({"text": sentence, "kind": f"template:{sname}",
                                  "problems": problems})
                    continue
                units.append({"text": sentence, "kind": "free",
                              "problems": constrained_problems(sentence, field=field)})
    return units


def problems(text: str, *, field: str = "listing") -> list[str]:
    """Every refusal in the composition, de-duplicated, in order."""
    return list(dict.fromkeys(p for u in composition(text, field=field) for p in u["problems"]))
