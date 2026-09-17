"""AI Customer Experience department (Master Plan section 10).

Section 10 names a Concierge that triages every authorised message and specialists behind it:
Download Support, Crochet Help, Materials, Pattern Troubleshooter, Customer Happiness, an
Incident Agent and Review Intelligence. `concierge.py` already answers pattern questions from
the exact released version. This is the department around it.

Three properties matter more than the routing.

**Nothing is sent.** Shadow mode means every reply is drafted and held. There is no messaging
integration in this system at all, so a reply cannot escape by accident -- but the state is
tracked explicitly anyway, because "we could not have sent it" is a weaker guarantee than "we
recorded that we did not".

**Routine questions do not wake the owner.** Section 10 is explicit about this. Escalation is
reserved for legal, privacy, chargeback and genuine disputes, and for anything the system is
not confident about. A support department that escalates everything is a support department
that does nothing.

**Repeated questions about the same row become a defect, not a FAQ.** The third person to ask
why row 48 does not work is evidence about the pattern, not about the customers. That path
runs into the incident tracker, which can halt publication.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..gates.incidents import IncidentTracker
from .concierge import Concierge, SupportAnswer

# ---- triage ----------------------------------------------------------------

Specialist = str

DOWNLOAD = "download"
CROCHET_HELP = "crochet_help"
MATERIALS = "materials"
TROUBLESHOOTER = "troubleshooter"
HAPPINESS = "happiness"
REVIEW_INTEL = "review_intelligence"
ESCALATE = "escalate"

_ROUTES: list[tuple[Specialist, re.Pattern]] = [
    # Escalation first: these must never be absorbed by a cheerful automated answer.
    (ESCALATE, re.compile(
        r"\b(chargeback|dispute|refund my|lawyer|legal|sue|copyright|dmca|stole|"
        r"privacy|gdpr|pipeda|delete my data|police|fraud|scam)\b", re.I)),
    (DOWNLOAD, re.compile(
        r"\b(download|corrupt(ed)?|attachment|zip|link (is )?(broken|dead)|"
        r"access my purchase|where is my (file|pattern|pdf|order))\b"
        r"|\b(pdf|file|document)\b[^.?!]{0,40}\b(won'?t|will not|cannot|can'?t|does ?n'?t)\b"
        r"|\b(won'?t|will not|cannot|can'?t)\b[^.?!]{0,30}\b(open|download|print)\b", re.I)),
    (TROUBLESHOOTER, re.compile(
        r"\b(does ?n'?t work|does not work|wrong|error|mistake|off by|does ?n'?t match|"
        r"ran out of stitches|too few|too many|short by|left over)\b"
        r"|\b(does ?n'?t|does not|not)\s+add(s|ing)?\s+up", re.I)),
    (MATERIALS, re.compile(
        r"\b(yarn|yardage|how much|skein|ball|weight|hook size|substitute|substitution|"
        r"colou?rway)\b", re.I)),
    (CROCHET_HELP, re.compile(
        r"\b(how do i|how to|what does|stitch|row|round|gauge|tension|chart|repeat|"
        r"turning chain|terms)\b", re.I)),
    (HAPPINESS, re.compile(
        r"\b(thank you|thanks|love|beautiful|gorgeous|finished mine|turned out)\b", re.I)),
]


def triage(message: str) -> Specialist:
    """Route a message to the specialist that should answer it.

    Order is the safety property. A message containing both "chargeback" and "yarn" is a
    dispute, and the routing table is ordered so that reading it top to bottom cannot
    accidentally hand a legal matter to the materials desk.
    """
    for specialist, pattern in _ROUTES:
        if pattern.search(message):
            return specialist
    return CROCHET_HELP


ESCALATION_REASONS = {
    ESCALATE: ("legal, privacy, chargeback or dispute — section 10 requires a human, and an "
               "automated answer here is worse than a slow one"),
}


# ---- cases -----------------------------------------------------------------


@dataclass
class Reply:
    specialist: Specialist
    body: str
    cited_version: str | None = None
    cited_rows: list[int] = field(default_factory=list)
    escalated: bool = False
    escalation_reason: str = ""
    sent: bool = False          # always False in shadow mode
    defect_suspected: bool = False

    def to_dict(self) -> dict:
        return {"specialist": self.specialist, "body": self.body,
                "cited_version": self.cited_version, "cited_rows": list(self.cited_rows),
                "escalated": self.escalated, "escalation_reason": self.escalation_reason,
                "sent": self.sent, "defect_suspected": self.defect_suspected}


DOWNLOAD_REPLY = (
    "Your pattern is a digital download, so nothing is posted. It is in your Etsy account "
    "under Purchases and reviews — open the order and the PDF is on the right. If the file "
    "will not open, it is almost always the PDF reader rather than the file: try opening it "
    "on a computer, or in a different reader. Tell us what you see and we will get you a "
    "working copy either way."
)

HAPPINESS_REPLY = (
    "Thank you — that genuinely makes our week. If you are happy with the pattern and feel "
    "like leaving a review, it helps a small shop more than you would think. And if you post "
    "a photo of your finished piece, we would love to see it."
)

NO_REVIEW_SOLICITATION = re.compile(
    r"\b(five star|5 star|positive review|leave us a good|in exchange for|discount if you "
    r"review|refund if you review)\b", re.I)


class ReviewSolicitationViolation(ValueError):
    """A reply tried to buy or steer a review."""


def check_reply(body: str) -> None:
    """A review must never be traded for anything.

    Asking for a review is allowed and normal. Asking for a *good* review, or offering
    anything in return, is exactly the fabricated engagement section 8 forbids, and on Etsy it
    is also against policy. This is checked on every drafted reply rather than trusted.
    """
    hit = NO_REVIEW_SOLICITATION.search(body)
    if hit:
        raise ReviewSolicitationViolation(
            f"the reply steers or trades a review ({hit.group(0)!r}). Reviews have to be "
            f"earned by the product, not requested with a qualifier.")


class CustomerExperience:
    """The department. Drafts replies; never sends them."""

    def __init__(self, db, tracker: IncidentTracker | None = None):
        self.db = db
        self.tracker = tracker or IncidentTracker(db)

    def handle(self, *, customer_ref: str, message: str, cir=None,
               product_slug: str | None = None, version: str | None = None) -> Reply:
        specialist = triage(message)

        if specialist == ESCALATE:
            reply = Reply(specialist=specialist,
                          body=("This needs a person rather than an automated reply, and it "
                                "has been passed to one."),
                          escalated=True, escalation_reason=ESCALATION_REASONS[ESCALATE])
        elif specialist == DOWNLOAD:
            reply = Reply(specialist=specialist, body=DOWNLOAD_REPLY)
        elif specialist == HAPPINESS:
            reply = Reply(specialist=specialist, body=HAPPINESS_REPLY)
        elif cir is None:
            reply = Reply(
                specialist=specialist,
                body=("We need to know which pattern this is about before answering — we "
                      "answer from the exact version you bought rather than from memory."),
                escalated=True,
                escalation_reason="no pattern version supplied; guessing would be worse")
        else:
            answer: SupportAnswer = Concierge(cir).answer(message)
            reply = Reply(specialist=specialist, body=answer.answer,
                          cited_version=answer.cited_version,
                          cited_rows=list(answer.cited_rows),
                          escalated=answer.escalated,
                          escalation_reason=("the released pattern does not answer this and a "
                                             "confident wrong answer costs hours"
                                             if answer.escalated else ""))
            if specialist == TROUBLESHOOTER:
                reply.defect_suspected = True

        check_reply(reply.body)
        self._record(customer_ref, product_slug, version, message, reply)
        return reply

    def _record(self, customer_ref, product_slug, version, message, reply: Reply) -> None:
        from ..core.models import SupportCase

        with self.db.session() as s:
            s.add(SupportCase(
                customer_ref=customer_ref, product_slug=product_slug, version=version,
                question=message, answer=reply.body, specialist=reply.specialist,
                escalated=reply.escalated, resolved=not reply.escalated,
                sent=False,   # shadow mode: drafted and held, and recorded as such
                detail={"cited_rows": reply.cited_rows,
                        "defect_suspected": reply.defect_suspected,
                        "escalation_reason": reply.escalation_reason},
            ))

    # -- review intelligence -------------------------------------------------

    def mine_cases(self, product_slug: str | None = None) -> dict:
        """Themes across real conversations. Never invents one.

        Section 10: repeated questions about the same row create a potential defect incident.
        This finds them, and deliberately reports raw counts rather than a sentiment score --
        "three people could not get row 48 to work" is actionable and "sentiment 0.42" is not.
        """
        from sqlalchemy import select

        from ..core.models import SupportCase

        with self.db.session() as s:
            q = select(SupportCase)
            if product_slug:
                q = q.where(SupportCase.product_slug == product_slug)
            cases = list(s.scalars(q))

        by_specialist: dict[str, int] = {}
        row_mentions: dict[tuple[str, int], int] = {}
        for case in cases:
            by_specialist[case.specialist] = by_specialist.get(case.specialist, 0) + 1
            for row in (case.detail or {}).get("cited_rows", []):
                key = (case.product_slug or "?", int(row))
                row_mentions[key] = row_mentions.get(key, 0) + 1

        hotspots = [{"product": slug, "row": row, "mentions": n}
                    for (slug, row), n in sorted(row_mentions.items(), key=lambda kv: -kv[1])
                    if n >= 2]
        return {
            "cases": len(cases),
            "by_specialist": by_specialist,
            "escalated": sum(1 for c in cases if c.escalated),
            "row_hotspots": hotspots,
            "note": ("row hotspots are candidate defects, not confirmed ones. Confirmation "
                     "runs through the compiler, not through a vote."),
        }

    def report_defect(self, *, product_slug: str, version: str, component: str, row: int,
                      customer_ref: str, description: str):
        """The only path that can change a pattern. Support itself still cannot."""
        from ..gates.incidents import DefectReport

        return self.tracker.report(DefectReport(product_slug, version, component, row,
                                                customer_ref, description))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
