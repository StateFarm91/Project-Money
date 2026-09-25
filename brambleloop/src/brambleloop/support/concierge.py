"""Customer experience (Master Plan section 14, acceptance Gate E).

Support is where a pattern company either builds trust or destroys it, and the failure mode
is specific: a well-meaning support agent "helpfully" tells a customer to work 41 stitches
because that is what makes their piece lie flat. Now there are two versions of the pattern in
the world, only one of which was ever validated, and the next customer gets different advice
again.

So the rule here is absolute and enforced by construction: support answers *from* the
released pattern version the customer actually bought, and cannot amend it. A genuine defect
becomes an incident, the pattern is fixed at source, re-validated, re-certified and re-issued.
That is slower for one customer and correct for every customer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..cir.compiler import CompileResult, compile_cir
from ..cir.model import CIR
from ..cir.twin import build_twin
from ..gates.incidents import DefectReport, IncidentTracker

# "Round 30" and "rnd 30" as well as "row 30".
#
# Two of the three Launch-0 products are worked in the round, their documents number every
# line `Rnd`, and a buyer asks in the words the pattern uses. This pattern matched `row`
# only, so every stitch-count question about a basket or a coaster missed the canonical
# answer -- the one that is already known, and whose service target is five minutes -- and
# fell through to the escalation branch, whose target is twenty-four hours. Nothing was wrong
# with the answer; the question was simply not recognised.
_ROW_Q = re.compile(r"\b(?:row|round|rnd)\s+(\d+)\b", re.I)
_COUNT_Q = re.compile(r"\b(how many|count|stitch count|should i have)\b", re.I)
_SIZE_Q = re.compile(r"\b(how big|finished size|dimensions|measure)\b", re.I)
_YARN_Q = re.compile(r"\b(how much yarn|yardage|how many (balls|skeins)|metres|yards)\b", re.I)
_GAUGE_Q = re.compile(r"\b(gauge|tension|swatch)\b", re.I)
_TERMS_Q = re.compile(r"\b(uk|us|american|british)\s*(terms?|terminology)?\b", re.I)


class SupportCannotAmendPatterns(PermissionError):
    """Support tried to change the pattern. Structurally impossible, deliberately."""


@dataclass
class SupportAnswer:
    question: str
    answer: str
    cited_version: str
    cited_rows: list[int] = field(default_factory=list)
    escalated: bool = False
    confident: bool = True

    def to_dict(self) -> dict:
        return {"question": self.question, "answer": self.answer,
                "cited_version": self.cited_version, "cited_rows": list(self.cited_rows),
                "escalated": self.escalated, "confident": self.confident}


class Concierge:
    """Answers from one specific released version, and only from it."""

    def __init__(self, cir: CIR, result: CompileResult | None = None):
        self.cir = cir
        self.result = result or compile_cir(cir)
        if not self.result.ok:
            raise ValueError(
                "refusing to answer customers from a pattern that does not compile; this "
                "version should never have been released")
        self.twin = build_twin(cir, self.result)

    # Support has no writer. There is deliberately no method that mutates self.cir.
    def amend(self, *_a, **_k):
        raise SupportCannotAmendPatterns(
            "support cannot edit a released pattern. A real defect becomes an incident, is "
            "fixed in the CIR, re-validated and re-issued as a new version."
        )

    def _line_word(self, component: str) -> str:
        """`row` or `round`, whichever the pattern the buyer is holding actually prints.

        Read off the component's construction, which is the same thing `cir.writer` reads to
        decide whether to number its lines `Row` or `Rnd`, so support cannot answer about a
        "row 30" of a document that has no rows in it.
        """
        for comp in self.cir.components:
            if comp.name == component:
                return "round" if str(comp.construction).endswith("rounds") else "row"
        return "row"

    def answer(self, question: str, component: str | None = None) -> SupportAnswer:
        comp = component or self.cir.components[0].name
        version = f"{self.cir.slug}@{self.cir.version}"
        q = question.strip()
        line = self._line_word(comp)

        row_match = _ROW_Q.search(q)
        if row_match and (_COUNT_Q.search(q) or not _SIZE_Q.search(q)):
            n = int(row_match.group(1))
            # counts() returns one entry per row in order, so row N is index N-1. Indexing it
            # as if it were keyed by row number silently answers the wrong row.
            counts = self.result.counts(comp)
            if 1 <= n <= len(counts):
                return SupportAnswer(
                    question=q, cited_version=version, cited_rows=[n],
                    answer=(f"At the end of {line} {n} you should have {counts[n - 1]} "
                            f"stitches. That number comes from the released pattern you "
                            f"bought ({version}) and was checked by the compiler before "
                            f"release. If you have a different count, work back to the last "
                            f"{line} where your count matched and re-work from there."))
            return SupportAnswer(
                question=q, cited_version=version, escalated=True, confident=False,
                answer=(f"{line.capitalize()} {n} is not in this pattern, which only has "
                        f"{len(counts)} {line}s in the {comp}. I have passed this to a human "
                        f"so we can work out what you are looking at."))

        if _SIZE_Q.search(q):
            if self.twin.width_cm and self.twin.height_cm:
                return SupportAnswer(
                    question=q, cited_version=version,
                    answer=(f"Worked at the stated gauge, the finished {comp} measures about "
                            f"{self.twin.width_cm:.0f} x {self.twin.height_cm:.0f} cm. That "
                            f"is computed from your gauge, so if your swatch differs the "
                            f"finished piece changes in the same proportion."))
            return SupportAnswer(question=q, cited_version=version, escalated=True,
                                 confident=False,
                                 answer="This pattern does not state a finished size, so I "
                                        "have passed this to a human rather than guess.")

        if _YARN_Q.search(q):
            tol = int(self.twin.yardage_tolerance * 100)
            lines = ", ".join(
                f"{name} about {m * (1 - self.twin.yardage_tolerance):.0f}-"
                f"{m * (1 + self.twin.yardage_tolerance):.0f} m"
                for name, m in sorted(self.twin.yarn_metres_by_color.items()))
            return SupportAnswer(
                question=q, cited_version=version,
                answer=(f"{lines}. These are estimates with a +/-{tol}% range rather than "
                        f"measurements — yarn use genuinely varies with yarn, hook and "
                        f"tension, so buy above the top of the range if dye lot matters to "
                        f"you."))

        if _GAUGE_Q.search(q) and self.cir.gauge:
            g = self.cir.gauge
            # `gauge.stitch_type` is a canonical code, which is to say a US abbreviation, and
            # this answer printed it raw to a buyer who may be reading the UK document. That
            # is the defect `publish/pdf._gauge_stitch` was written to close on the cover --
            # a UK maker resolving `sc` against their own vocabulary swatches a treble, three
            # times the height the gauge was measured at -- arriving again through support.
            # Both spellings, from the one registry, because support does not know which of
            # the two files they opened.
            from ..publish import abbreviations as ab

            us, uk = ab.token(g.stitch_type, "US"), ab.token(g.stitch_type, "UK")
            named = us if us == uk else f"{us} (UK terms: {uk})"
            return SupportAnswer(
                question=q, cited_version=version,
                answer=(f"Gauge is {g.stitches_per_10cm} stitches and {g.rows_per_10cm} rows "
                        f"to 10 cm in {named} with a {g.hook_mm:g} mm hook. The "
                        f"stitch counts in the pattern are correct whatever your gauge -- "
                        f"only the finished measurements change."))

        if _TERMS_Q.search(q):
            # What the buyer actually receives, read from the list of terminologies the
            # release chain renders and attaches, rather than restated here.
            #
            # This used to say "written in US terms and the stitch key lists the UK
            # equivalent for every stitch used". That is the claim
            # `research/DELIVERABLE_QA2.md` found unsupportable on four surfaces and had
            # withdrawn from all of them: no key has ever listed equivalents, and since that
            # audit the release chain renders and attaches **both documents**. So support was
            # sending a buyer who already owns the UK PDF away to look for a column that does
            # not exist -- the worst shape of wrong answer, because the thing they want is in
            # the download they are holding.
            from ..publish.pdf import TERMINOLOGIES, pattern_filename

            files = ", ".join(f"{t} terms ({pattern_filename(t)})" for t in TERMINOLOGIES)
            return SupportAnswer(
                question=q, cited_version=version,
                answer=(f"Both. Your purchase includes {len(TERMINOLOGIES)} separate PDFs of "
                        f"this pattern -- {files} -- each written throughout in its own "
                        f"terms, with its own stitch key. Download whichever one you work "
                        f"from; nothing needs translating."))

        return SupportAnswer(
            question=q, cited_version=version, escalated=True, confident=False,
            answer=("I would rather hand this to a human than guess at it. Nothing in the "
                    "released pattern answers this directly, and a confident wrong answer "
                    "about a pattern costs you hours."))

    def report_defect(self, tracker: IncidentTracker, *, component: str, row: int,
                      customer: str, description: str):
        """A customer says the pattern is wrong. This is the only path that changes anything.

        It creates a defect report; correlation and the publication halt are the incident
        tracker's job. Support never decides on its own that a pattern is fine.
        """
        return tracker.report(DefectReport(self.cir.slug, self.cir.version, component, row,
                                           customer, description))
