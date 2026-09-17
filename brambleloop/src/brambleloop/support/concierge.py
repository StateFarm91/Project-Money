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

_ROW_Q = re.compile(r"\brow\s+(\d+)\b", re.I)
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

    def answer(self, question: str, component: str | None = None) -> SupportAnswer:
        comp = component or self.cir.components[0].name
        version = f"{self.cir.slug}@{self.cir.version}"
        q = question.strip()

        row_match = _ROW_Q.search(q)
        if row_match and (_COUNT_Q.search(q) or not _SIZE_Q.search(q)):
            n = int(row_match.group(1))
            # counts() returns one entry per row in order, so row N is index N-1. Indexing it
            # as if it were keyed by row number silently answers the wrong row.
            counts = self.result.counts(comp)
            if 1 <= n <= len(counts):
                return SupportAnswer(
                    question=q, cited_version=version, cited_rows=[n],
                    answer=(f"At the end of row {n} you should have {counts[n - 1]} stitches. "
                            f"That number comes from the released pattern you bought "
                            f"({version}) and was checked by the compiler before release. If "
                            f"you have a different count, work back to the last row where "
                            f"your count matched and re-work from there."))
            return SupportAnswer(
                question=q, cited_version=version, escalated=True, confident=False,
                answer=(f"Row {n} is not in this pattern, which only has "
                        f"{len(counts)} rows in the {comp}. I have passed this to a human so "
                        f"we can work out what you are looking at."))

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
            return SupportAnswer(
                question=q, cited_version=version,
                answer=(f"Gauge is {g.stitches_per_10cm} stitches and {g.rows_per_10cm} rows "
                        f"to 10 cm in {g.stitch_type} with a {g.hook_mm:g} mm hook. The "
                        f"stitch counts in the pattern are correct whatever your gauge — "
                        f"only the finished measurements change."))

        if _TERMS_Q.search(q):
            return SupportAnswer(
                question=q, cited_version=version,
                answer=("The pattern is written in US terms and the stitch key lists the UK "
                        "equivalent for every stitch used, so you can work it either way."))

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
