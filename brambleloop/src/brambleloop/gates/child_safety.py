"""ENG-PLUSH: the child-safety pattern-content gate (D-OWNER-CORE-FAMILIES section 3).

Stuffed animals, baby items and loveys are permanent core families, and the owner's rule is
that child and baby safety is more than embroidered eyes. This gate is that rule in code. It
reads the CIR (what the pattern instructs) and, when given, the customer's rendered text (what
the document says), and every check answers PASS, FAIL or UNKNOWN. **UNKNOWN is never PASS**:
the verdict is PASS only when every check passes, FAIL when any fails, and HELD when the only
thing missing is evidence nothing in this system can supply yet.

Construction checks (from the CIR):

  FEATURES_EMBROIDERED  no safety eye, button, bead, bell, pellet or other hard part is named
                        in any material, note or instruction; a toy with a face states the
                        face is embroidered with yarn. Embroidered eyes alone pass THIS check
                        only -- the verdict needs every other check too.
  JOINS_VALIDATED       every sewn-on piece is joined by a sewing method at a stated position
                        (round and stitches, or named edges), measured by `cir.assembly` with
                        no mismatch, sewn across its whole edge with the tail buried.
  NO_CORDS_OR_LOOPS     no threaded cord, no chain-only piece, no chain run longer than
                        MAX_CHAIN_RUN inside a row, no cord/string/ribbon/strap/tie/loop words.
  STUFFING_GUIDANCE     a stuffed piece names new polyester toy stuffing (never beans,
                        pellets, rice, seeds or beads), states its stuffing point and closure,
                        and `cir.closed_forms` finds nothing wrong with them.
  SMALL_PARTS           `gates.small_parts.blocking` finds no sewn-on piece that fits or may
                        fit the 31.7 mm cylinder.
  PHYSICAL_EVIDENCE     a stuffed toy, lovey or anything assigned to a child under 3 needs a
                        physical use-and-abuse test of this exact content (seam pull, closure,
                        stuffing containment). No content-bound authority for that evidence
                        exists, so this is UNKNOWN for every such product today -- HELD.

Content checks (from the rendered text, when given):

  SAFETY_SECTION        every required statement of the product's profile is present
                        (age suitability, features, joins, stuffing, cords, safe sleep, the
                        not-a-toy-certification statement).
  CITATIONS             every source a statement rests on is printed with its URL and the
                        date it was accessed.
  NO_CERTIFICATION_CLAIM the document claims no toy certification, test or standard -- we sell
                        patterns. A sentence that DENIES certification is ours and is exempt.
  NO_HARD_PARTS_IN_TEXT the instructions (the text outside the safety section) name no hard part.

Sources were read on ACCESSED (the dates are printed in the document): US regulation text via
the eCFR API and govinfo, Canada's Toys Regulations from laws-lois.justice.gc.ca (current to
2026-10-29), and the CPSC and Health Canada guidance pages. Two facts commonly assumed were NOT
confirmed and are not stated: Canada's Toys Regulations set no cord-length limit for toys for
children under 18 months, and CPSC's safe-sleep page states no age in months. The 12-inch
ASTM F963 cord figure was found only in a 2010 CPSC staff memo, so it is not printed either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
VERDICT_PASS, VERDICT_FAIL, VERDICT_HELD = "PASS", "FAIL", "HELD"
ACCESSED = "2026-11-20"
MAX_CHAIN_RUN = 6               # a longer chain inside a row is a loop a finger can enter


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    url: str
    quote: str                  # verbatim from the page read on ACCESSED


SOURCES: dict[str, Source] = {s.key: s for s in (
    Source("cfr_1501", "US 16 CFR 1501 (small parts, children under 3)",
           "https://www.ecfr.gov/current/title-16/chapter-II/subchapter-C/part-1501",
           "any toy or other article intended for use by children under 3 years of age that "
           "presents a choking, aspiration, or ingestion hazard because of small parts"),
    Source("cfr_1500_19", "US 16 CFR 1500.19(b)(1) (choking-hazard cautionary statement)",
           "https://www.ecfr.gov/current/title-16/chapter-II/subchapter-C/part-1500/"
           "section-1500.19",
           "WARNING: CHOKING HAZARD--Small parts Not for children under 3 yrs."),
    Source("sor_2011_17", "Canada Toys Regulations SOR/2011-17 (s.7 small parts, s.29 "
                          "stuffing, s.31 eyes and noses)",
           "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2011-17/FullText.html",
           "it must be clean and free from vermin; (b) it must be free of hard or sharp "
           "foreign matter"),
    Source("hc_toy_tips", "Health Canada: toy safety tips",
           "https://www.canada.ca/en/health-canada/services/toy-safety/toy-safety-tips.html",
           "Don't give toys with small parts or accessories to children under 3 years old."),
    Source("cpsc_5100", "CPSC Publication 5100 (toys and cords)",
           "https://www.cpsc.gov/s3fs-public/5100.pdf",
           "Parents should never give young children toys with cords, strings, or straps "
           "that fit around the neck."),
    Source("cpsc_safe_sleep", "CPSC: safe sleep",
           "https://www.cpsc.gov/SafeSleep",
           "The safest way for a baby to sleep is flat on their back without pillows, "
           "blankets, or toys in their sleep space."),
    Source("hc_safe_sleep", "Health Canada: safe sleep tips",
           "https://www.canada.ca/en/health-canada/services/safe-sleep/safe-sleep-tips.html",
           "Provide a sleep space that is flat, firm and free of soft bedding, extra padding, "
           "bumper pads, stuffed toys or pillows."),
)}


@dataclass(frozen=True)
class Statement:
    key: str
    heading: str
    text: str
    marker: str                 # a phrase the content check looks for in the rendered text
    sources: tuple[str, ...] = ()


def _cite(*keys: str) -> str:
    return " ".join(f"({SOURCES[k].title}: \"{SOURCES[k].quote}\" {SOURCES[k].url}, accessed "
                    f"{ACCESSED}.)" for k in keys)


STATEMENTS: dict[str, Statement] = {s.key: s for s in (
    Statement("pattern_not_toy", "We sell a pattern, not a toy",
              "Brambleloop Studio sells these instructions. We have not made, tested or "
              "certified the item you will make, and we make no claim that it meets any "
              "toy-safety standard. What you make is yours: its safety depends on your yarn, "
              "your tension and your finishing.",
              "We sell a pattern, not a toy"),
    Statement("age_suitability", "Age suitability",
              "This design follows the construction rules for toys for children under 3: no "
              "part is meant to come off, and by the pattern's own stitch counts every "
              "sewn-on piece is larger than the small-parts cylinder (31.7 mm across). That "
              "is geometry, not a use-and-abuse test, so it does not make the finished item "
              "suitable for any age; only a tested sample can show that. "
              + _cite("cfr_1501"),
              "follows the construction rules for toys for children under 3",
              ("cfr_1501",)),
    Statement("features", "Embroidered features only",
              "Embroider the eyes, nose and any other feature with yarn. Do not use safety "
              "eyes, buttons, beads, bells or any other hard part on an item for a child "
              "under 3 or on any baby item: a hard eye or nose that is pulled off is a choking "
              "hazard. If you change this, the US cautionary statement then applies to what "
              "you make: \"WARNING: CHOKING HAZARD--Small parts / Not for children under 3 "
              "yrs.\" Embroidered features alone do not make an item safe; the joins, the "
              "stuffing and the no-cords rule below matter as much. "
              + _cite("hc_toy_tips", "cfr_1500_19"),
              "Embroider the eyes, nose and any other feature with yarn",
              ("hc_toy_tips", "cfr_1500_19")),
    Statement("joins", "Joins",
              "Sew every piece on across its whole edge, through both loops of every stitch "
              "and through the fabric it joins, across and back again, so no single stitch "
              "carries it. Knot the tail inside and bury it through at least 5 cm of "
              "stitches. Pull each sewn piece firmly when you finish; resew any that moves.",
              "Sew every piece on across its whole edge"),
    Statement("stuffing", "Stuffing",
              "Use only new, clean polyester toy stuffing. Never use beans, pellets, rice, "
              "seeds, beads or anything hard. Work at the stated gauge or tighter so stuffing "
              "cannot show between the stitches, stuff firmly at the round the pattern "
              "names, and close the last round tightly as written. " + _cite("sor_2011_17"),
              "Use only new, clean polyester toy stuffing",
              ("sor_2011_17",)),
    Statement("no_cords", "No cords or loops",
              "Add no cords, ribbons, strings, straps, ties or hanging loops, and do not "
              "attach the item to a pacifier clip, a crib or a pram. " + _cite("cpsc_5100"),
              "Add no cords, ribbons, strings, straps, ties or hanging loops",
              ("cpsc_5100",)),
    Statement("safe_sleep", "Keep it out of the sleep space",
              "Keep this out of a baby's crib, cot or bassinet: soft items do not belong in "
              "an infant's sleep space. " + _cite("cpsc_safe_sleep", "hc_safe_sleep"),
              "Keep this out of a baby's crib, cot or bassinet",
              ("cpsc_safe_sleep", "hc_safe_sleep")),
)}

SECTION_HEADING = "Child safety: read before you make this"
SECTION_END = "End of child safety notes."

_HARD_PARTS = re.compile(
    r"\bsafety[- ]?eyes?\b|\bplastic (?:eyes?|nose|noses)\b|\bglass eyes?\b|\bgoogly\b|"
    r"\bbuttons?\b|\bbeads?\b|\bbeaded\b|\bbells?\b|\bjingle\b|\bsequins?\b|\bpellets?\b|"
    r"\bpoly[- ]?pellets?\b|\bbeans?\b|\brice\b|\bseeds?\b|\bsqueakers?\b|\brattle insert\b|"
    r"\bwire\b|\bwired\b|\bpipe[- ]cleaners?\b|\bmagnets?\b|\bjoint discs?\b|\bglue(?:d)?\b|"
    r"\bgrommets?\b|\bsnaps?\b|\bzip(?:per)?s?\b|\bvelcro\b|\bhook[- ]and[- ]loop\b")
_CORD_WORDS = re.compile(r"\bcords?\b|\bstrings?\b|\bribbons?\b|\bstraps?\b|\bties\b|"
                         r"\bdrawstrings?\b|\bhanging loop\b|\bpacifier clip\b|\blanyard\b")
_STUFFING_OK = re.compile(r"\bpolyester\b.*\b(?:fibrefill|fiberfill|stuffing|fill)\b|"
                          r"\btoy stuffing\b")
_CLAIMS = re.compile(
    r"\b(?:is|are|has been|have been|was|were)\s+(?:safety[- ])?(?:tested|certified|approved)\b|"
    r"\bsafety[- ]tested\b|\blab[- ]tested\b|\bcertified (?:safe|toy|to)\b|"
    r"\b(?:meets|complies with|compliant with|conforms to)\s+(?:astm|en ?71|cpsia|iso|the toy)|"
    r"\bastm[- ]compliant\b|\bcpsia[- ]compliant\b|\bce[- ]mark(?:ed)?\b|"
    r"\bsafe for (?:babies|infants|newborns|toddlers|all ages|children)\b|\bchild[- ]safe\b|"
    r"\bbaby[- ]safe\b|\bnon[- ]toxic\b")


@dataclass
class Check:
    code: str
    state: str
    detail: str


@dataclass
class Verdict:
    applies: bool
    profile: tuple[str, ...]
    checks: list[Check] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.applies:
            return VERDICT_PASS
        states = {c.state for c in self.checks}
        if FAIL in states:
            return VERDICT_FAIL
        if UNKNOWN in states:
            return VERDICT_HELD
        return VERDICT_PASS

    def failing(self) -> list[Check]:
        return [c for c in self.checks if c.state == FAIL]

    def unknown(self) -> list[Check]:
        return [c for c in self.checks if c.state == UNKNOWN]

    def to_dict(self) -> dict:
        return {"applies": self.applies, "profile": list(self.profile),
                "verdict": self.verdict,
                "checks": [{"code": c.code, "state": c.state, "detail": c.detail}
                           for c in self.checks]}


# ---- profile -----------------------------------------------------------------------------

SLEEP_SUBCATEGORIES = frozenset({"lovey", "baby_blanket", "keepsake_blanket", "nursery_decor"})
_SLEEP_WORDS = re.compile(r"\b(?:baby|babies|infant|newborn|nursery|lovey|loveys|crib|cot|"
                          r"swaddle|receiving)\b")


def _fold(text: str) -> str:
    from ..products.text_fold import fold

    return fold(text or "")


def _instruction_texts(cir) -> list[str]:
    out = [str(getattr(cir, "designer_notes", "") or "")]
    out += [str(getattr(m, "name", "") or "") for m in cir.materials]
    out += [str(getattr(s, "note", "") or "") for s in cir.assembly]
    for c in cir.components:
        out.append(str(c.note or ""))
        out += [str(r.note or "") for r in c.rows]
    return out


def profile_for(cir, childrens: tuple[str, str] | None = None) -> tuple[str, ...]:
    """Which statement groups apply: always the base set; `stuffed`, `face`, `sewn`, `sleep`."""
    from ..products import launch0

    flags = {"base"}
    if launch0.closed_stuffed_form(cir):
        flags.add("stuffed")
    text = _fold(" ".join(_instruction_texts(cir)))
    if re.search(r"\bembroider", text) or re.search(r"\beyes?\b|\bnose\b|\bface\b", text):
        flags.add("face")
    if any(s.piece_a != s.piece_b and s.method != "pick_up" for s in cir.assembly):
        flags.add("sewn")
    if garment_months(cir) is not None:
        flags.add("garment")
    title = _fold(f"{cir.title} {cir.slug}")
    if (childrens and childrens[0] in SLEEP_SUBCATEGORIES) or _SLEEP_WORDS.search(title):
        flags.add("sleep")
    return tuple(sorted(flags))


def applies(cir, childrens: tuple[str, str] | None = None) -> bool:
    """A closed stuffed form, a children's assignment, or a title that reads as a child's."""
    from ..products import launch0

    if childrens or launch0.child_words_in(cir.title, cir.slug) or launch0.stuffed_figure(cir):
        return True        # a stuffed figure is a toy whatever any decision says
    # ENG-GARMENT: a garment graded on the baby table, or on the child table at 12 or under,
    # is a child's garment whatever its title says.
    if garment_months(cir) is not None:
        return True
    # A stuffed closed piece in rounds (an amigurumi body, a ball) is toy-shaped whatever it
    # is called. A stuffed panel pair (a cushion) is not: whether it is for a child is the
    # owner's decision, which the A1-R gate (`publish.pdf`) already holds it for; once it is
    # assigned to a child, it is inside this gate.
    if any(c.closes or c.stuff_at_round is not None for c in cir.components):
        return True
    if launch0.closed_stuffed_form(cir):
        state, _why = launch0.childrens_decision_for(cir)
        return state == launch0.ASSIGNED
    return False


def required_statements(profile: tuple[str, ...]) -> tuple[str, ...]:
    keys = ["pattern_not_toy", "age_suitability", "no_cords"]
    if "face" in profile or "stuffed" in profile:
        keys.append("features")
    if "sewn" in profile:
        keys.append("joins")
    if "stuffed" in profile:
        keys.append("stuffing")
    if "sleep" in profile:
        keys.append("safe_sleep")
    return tuple(keys)


def section_lines(profile: tuple[str, ...]) -> list[tuple[str, str]]:
    """(heading, text) pairs the PDF prints, in order, ending with the sources and the end mark."""
    out = [(STATEMENTS[k].heading, STATEMENTS[k].text) for k in required_statements(profile)]
    used = sorted({s for k in required_statements(profile) for s in STATEMENTS[k].sources})
    out.append(("Sources", " ".join(f"{SOURCES[k].title}, {SOURCES[k].url}, accessed "
                                    f"{ACCESSED}." for k in used)))
    out.append(("", SECTION_END))
    return out


# ---- the checks ----------------------------------------------------------------------------

def _features(cir, profile) -> Check:
    texts = _fold(" ".join(_instruction_texts(cir)))
    hit = _HARD_PARTS.search(texts)
    if hit:
        return Check("FEATURES_EMBROIDERED", FAIL,
                     f"the pattern names {hit.group(0)!r}: only embroidered yarn features are "
                     f"allowed on a child's or stuffed item")
    if "face" in profile and not re.search(r"\bembroider", texts):
        return Check("FEATURES_EMBROIDERED", FAIL,
                     "the item has a face but no instruction says it is embroidered with yarn")
    return Check("FEATURES_EMBROIDERED", PASS,
                 "no hard part named" + ("; the face is embroidered with yarn"
                                         if "face" in profile else ""))


def _joins(cir, result) -> Check:
    sewn = [s for s in cir.assembly if s.piece_a != s.piece_b and s.method != "pick_up"]
    picked = [s for s in cir.assembly if s.piece_a != s.piece_b and s.method == "pick_up"]
    if not sewn and picked:
        # ENG-GARMENT: a band picked up and worked into an edge is crocheted fabric, not a
        # piece sewn on; it still has to meet its edge, measured like any join.
        return _picked_up_joins(cir, result, picked)
    if not sewn:
        return Check("JOINS_VALIDATED", PASS, "no piece is sewn onto another")
    bad = [f"{s.piece_a}->{s.piece_b} by {s.method}" for s in sewn
           if s.method not in ("whipstitch", "sew", "mattress", "slst")]
    if bad:
        return Check("JOINS_VALIDATED", FAIL, f"not a sewn join: {bad}")
    unplaced = [f"{s.piece_a}->{s.piece_b}" for s in sewn
                if not s.is_placed and not s.names_its_edges]
    if unplaced:
        return Check("JOINS_VALIDATED", FAIL, f"joins with no stated position: {unplaced}")
    if result is None or not result.ok:
        return Check("JOINS_VALIDATED", UNKNOWN, "the pattern did not compile, so no join is "
                                                 "measured")
    assembly_errors = [f for f in result.findings
                       if f.code.startswith("ASSEMBLY") and f.is_error]
    try:
        from ..cir import assembly as _assembly
        from ..cir.twin import build_twin

        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        geo = _assembly.assemble(cir, twins)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable join is UNKNOWN, never a pass
        return Check("JOINS_VALIDATED", UNKNOWN, f"joins could not be measured ({exc})")
    if assembly_errors or geo.verdict == "does_not_assemble":
        return Check("JOINS_VALIDATED", FAIL,
                     "; ".join([f"{f.code}: {f.message}" for f in assembly_errors]
                               + ([f"does not assemble: {geo.why}"]
                                  if geo.verdict == "does_not_assemble" else [])))
    if geo.verdict != "assembles":
        return Check("JOINS_VALIDATED", UNKNOWN,
                     f"joins not all measured ({geo.verdict}: {geo.why}): UNKNOWN is not a pass")
    notes = _fold(" ".join(str(s.note or "") for s in sewn))
    if not (re.search(r"both loops", notes) and re.search(r"\bbury\b|\bburied\b", notes)):
        return Check("JOINS_VALIDATED", FAIL,
                     "a sewn join does not say it is sewn through both loops with the tail "
                     "buried")
    return Check("JOINS_VALIDATED", PASS,
                 f"{len(sewn)} sewn join(s), each placed and measured, sewn through both loops")


def _picked_up_joins(cir, result, picked) -> Check:
    if result is None or not result.ok:
        return Check("JOINS_VALIDATED", UNKNOWN, "the pattern did not compile, so no "
                                                 "picked-up edge is measured")
    try:
        from ..cir import assembly as _assembly
        from ..cir.twin import build_twin

        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        geo = _assembly.assemble(cir, twins)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable join is UNKNOWN, never a pass
        return Check("JOINS_VALIDATED", UNKNOWN, f"picked-up edges could not be measured "
                                                 f"({exc})")
    joins = [j for j in geo.joins if j.method == "pick_up"]
    bad = [j for j in joins if j.verdict == "mismatched"]
    if bad:
        return Check("JOINS_VALIDATED", FAIL, "; ".join(j.why for j in bad))
    unsure = [j for j in joins if j.verdict != "sound"]
    if unsure:
        return Check("JOINS_VALIDATED", UNKNOWN,
                     f"picked-up edges not all measured: {[j.why for j in unsure]}")
    return Check("JOINS_VALIDATED", PASS,
                 f"no piece is sewn on; {len(joins)} band(s) picked up and worked into "
                 f"their edges, each measured")


def garment_months(cir) -> int | None:
    """The age in months a graded child's or baby's garment size is for (12 years or under),
    or None when the CIR is not such a garment."""
    g = getattr(cir, "grading", None)
    if g is None:
        return None
    from ..cir.graded import months_of

    months = months_of(g.table, g.size)
    return months if months is not None and months <= 144 else None


UNDER_THREE_MONTHS = 36


def _buttonholes(cir) -> int:
    from ..cir.model import Op

    n = 0
    for c in cir.components:
        for r in c.rows:
            n += sum(1 for o in r.ops if isinstance(o, Op) and o.stitch == "ch"
                     and getattr(o, "spans", 0) and getattr(c, "feature", None) == "button_band")
    return n


def _garment_closures(cir, profile) -> Check:
    """ENG-GARMENT (owner brief): no loose ties or cords for under-3s, and secure buttons or
    no buttons for babies. Buttons are hard parts (FEATURES_EMBROIDERED refuses the word);
    this check reads the structure: a buttonhole is a bridged chain in a button band."""
    if "garment" not in profile:
        return Check("GARMENT_CLOSURES", PASS, "not a child's garment")
    months = garment_months(cir)
    holes = _buttonholes(cir)
    if months is not None and months < UNDER_THREE_MONTHS:
        if holes:
            return Check("GARMENT_CLOSURES", FAIL,
                         f"size for {months} months has {holes} buttonhole(s): a garment for "
                         f"a child under 3 is made with no buttons")
        return Check("GARMENT_CLOSURES", PASS,
                     f"size for {months} months: no buttonholes, no ties, no cords")
    if holes:
        return Check("GARMENT_CLOSURES", UNKNOWN,
                     f"{holes} buttonhole(s) on a child's garment: whether a sewn button is "
                     f"secure is a physical pull test nothing can bind yet: held")
    return Check("GARMENT_CLOSURES", PASS, "no buttonholes, no ties, no cords")


def _cords(cir) -> Check:
    from ..cir.model import Op, Repeat

    if any(s.method == "thread" for s in cir.assembly):
        return Check("NO_CORDS_OR_LOOPS", FAIL, "a cord is threaded through the item")

    def chain_runs(nodes):
        for n in nodes:
            if isinstance(n, Op) and n.stitch == "ch":
                yield n.count
            elif isinstance(n, Repeat):
                yield from chain_runs(n.ops)

    for c in cir.components:
        if c.rows and all(all(isinstance(n, Op) and n.stitch == "ch" for n in r.ops)
                          for r in c.rows):
            return Check("NO_CORDS_OR_LOOPS", FAIL, f"{c.name!r} is a chain cord")
        for k, r in enumerate(c.rows):
            longest = max(chain_runs(r.ops), default=0)
            # ENG-GARMENT: a chain the next row works into (sleeves chained on, a neck
            # bridged) is the foundation of fabric, not a loop. A chain in the last row, or
            # one the next row leaves unworked, is still a loop a finger can enter.
            nxt = c.rows[k + 1] if k + 1 < len(c.rows) else None
            if longest > MAX_CHAIN_RUN and nxt is not None and not nxt.skips \
                    and nxt.into is None and not r.allow_remainder:
                continue
            if longest > MAX_CHAIN_RUN:
                return Check("NO_CORDS_OR_LOOPS", FAIL,
                             f"{c.name!r} round/row {r.index} works a {longest}-chain loop "
                             f"(limit {MAX_CHAIN_RUN})")
    hit = _CORD_WORDS.search(_fold(" ".join(_instruction_texts(cir))))
    if hit:
        return Check("NO_CORDS_OR_LOOPS", FAIL, f"the pattern names {hit.group(0)!r}")
    return Check("NO_CORDS_OR_LOOPS", PASS, f"no cord, and no chain loop over {MAX_CHAIN_RUN}")


def _stuffing(cir, result, profile) -> Check:
    if "stuffed" not in profile:
        return Check("STUFFING_GUIDANCE", PASS, "not stuffed")
    materials = _fold(" ".join(str(m.name or "") for m in cir.materials))
    if not _STUFFING_OK.search(materials):
        return Check("STUFFING_GUIDANCE", FAIL, "no new polyester toy stuffing is named in the "
                                                "materials")
    closed = [c for c in cir.components if c.closes or c.stuff_at_round is not None]
    if not closed:
        return Check("STUFFING_GUIDANCE", FAIL,
                     "a stuffed item states no stuffing point or closure for any piece")
    missing = [c.name for c in closed if c.stuff_at_round is None or not c.closes]
    if missing:
        return Check("STUFFING_GUIDANCE", FAIL,
                     f"{missing}: a stuffed closed piece must state both its stuffing point "
                     f"and its closure")
    if result is None:
        return Check("STUFFING_GUIDANCE", UNKNOWN, "not compiled")
    from ..cir import closed_forms

    found: list = []
    closed_forms.check(cir, result, found)
    if found:
        return Check("STUFFING_GUIDANCE", FAIL, "; ".join(f"{f.code}: {f.message}"
                                                          for f in found))
    return Check("STUFFING_GUIDANCE", PASS,
                 "; ".join(f"{c.name}: stuffed after round {c.stuff_at_round}, closed"
                           for c in closed))


def _small_parts(cir) -> Check:
    from . import small_parts

    blocks = small_parts.blocking(cir)
    if blocks:
        state = UNKNOWN if all(small_parts.UNKNOWN in b and small_parts.FITS not in b
                               for b in blocks) else FAIL
        return Check("SMALL_PARTS", state, "; ".join(blocks))
    return Check("SMALL_PARTS", PASS, "every sewn-on piece is clear of the 31.7 mm cylinder")


def _physical(cir, profile, childrens) -> Check:
    # Required where the construction can fail in a child's hands: a stuffed piece (closure,
    # stuffing containment) or a sewn-on piece (seam pull). A flat, unstuffed, one-piece
    # blanket has neither, and its other checks are computable.
    needs = ("stuffed" in profile or "sewn" in profile
             or bool(childrens and childrens[0] in ("lovey", "amigurumi_toy")))
    if not needs:
        return Check("PHYSICAL_EVIDENCE", PASS, "no physical evidence is required for this "
                                                "flat, unstuffed construction")
    return Check("PHYSICAL_EVIDENCE", UNKNOWN,
                 "a physical use-and-abuse test of this exact content (seam pull on every "
                 "sewn piece, closure, stuffing containment) is required, and no content-bound "
                 "physical-evidence authority exists yet: held")


def _text_checks(text: str, profile, instructions: str | None = None) -> list[Check]:
    folded = _fold(text)
    out = []
    required = required_statements(profile)
    missing = [k for k in required if _fold(STATEMENTS[k].marker) not in folded]
    out.append(Check("SAFETY_SECTION", FAIL if missing else PASS,
                     f"missing statements: {missing}" if missing else
                     f"all {len(required)} statements present"))
    sources = sorted({s for k in required for s in STATEMENTS[k].sources})
    uncited = [k for k in sources if SOURCES[k].url.lower() not in folded.replace(" ", "")
               and SOURCES[k].url.lower() not in folded]
    if f"accessed {ACCESSED}" not in folded:
        uncited.append("access date")
    out.append(Check("CITATIONS", FAIL if uncited else PASS,
                     f"not cited with an access date: {uncited}" if uncited else
                     f"{len(sources)} sources cited, accessed {ACCESSED}"))
    claim = _CLAIMS.search(folded)
    out.append(Check("NO_CERTIFICATION_CLAIM", FAIL if claim else PASS,
                     f"the document claims {claim.group(0)!r}; we sell patterns and claim no "
                     f"toy certification" if claim else "no certification or test claimed"))
    # The instructions (the writer's pattern text) when given; otherwise the document with
    # this section cut out. Safety pages name hard parts in order to forbid them.
    if instructions is not None:
        outside = _fold(instructions)
    else:
        head, end = _fold(SECTION_HEADING), _fold(SECTION_END)
        outside = folded
        if head in folded and end in folded:
            a, b = folded.index(head), folded.index(end) + len(end)
            outside = folded[:a] + " " + folded[b:]
    if instructions is not None and ("face" in profile) \
            and not re.search(r"\bembroider", outside):
        out.append(Check("FEATURES_INSTRUCTED", FAIL,
                         "the item has a face but the printed instructions never tell the "
                         "maker to embroider it"))
    hard = _HARD_PARTS.search(outside)
    out.append(Check("NO_HARD_PARTS_IN_TEXT", FAIL if hard else PASS,
                     f"the instructions name {hard.group(0)!r}" if hard else
                     "the instructions name no hard part"))
    return out


def evaluate(cir, result=None, *, text: str | None = None, instructions: str | None = None,
             childrens: tuple[str, str] | None = None) -> Verdict:
    """The gate. `result` is the compile result (compiled here when None); `text` is the
    customer's rendered text, checked for the safety section when given."""
    if not applies(cir, childrens):
        return Verdict(applies=False, profile=())
    if result is None:
        from ..cir.compiler import compile_cir

        result = compile_cir(cir)
    profile = profile_for(cir, childrens)
    v = Verdict(applies=True, profile=profile)
    v.checks += [_features(cir, profile), _joins(cir, result), _cords(cir),
                 _stuffing(cir, result, profile), _small_parts(cir),
                 _physical(cir, profile, childrens)]
    if "garment" in profile:
        v.checks.append(_garment_closures(cir, profile))
    if text is not None:
        v.checks += _text_checks(text, profile, instructions)
    return v
