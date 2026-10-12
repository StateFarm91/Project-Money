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
from datetime import datetime, timedelta, timezone

from ..gates.incidents import IncidentTracker
from .concierge import Concierge, SupportAnswer

# ---- triage ----------------------------------------------------------------

Specialist = str

DOWNLOAD = "download"
CROCHET_HELP = "crochet_help"
MATERIALS = "materials"
TROUBLESHOOTER = "troubleshooter"
HAPPINESS = "happiness"
VERSION = "version"
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
    # "Which version did I buy?" is answered from the order-to-version map (#42). After the
    # download desk and before the troubleshooter, so "the corrected version" is not read as
    # a defect report.
    (VERSION, re.compile(
        r"\b(which|what) version\b|\bversion (did|do) i (buy|have|get)\b"
        r"|\bcorrect(ed|ion) (pattern|version|file)\b|\bupdated (pattern|version|file)\b",
        re.I)),
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
    # F-808: approved, revision-bound Learn lessons linked from the answer. Empty until an
    # owned HTTPS Learn origin is configured (owner gate `owned_surfaces`).
    lesson_links: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {"specialist": self.specialist, "body": self.body,
               "cited_version": self.cited_version, "cited_rows": list(self.cited_rows),
               "escalated": self.escalated, "escalation_reason": self.escalation_reason,
               "sent": self.sent, "defect_suspected": self.defect_suspected}
        if self.lesson_links:
            out["lesson_links"] = [dict(link) for link in self.lesson_links]
        return out


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
               product_slug: str | None = None, version: str | None = None,
               case_id: int | None = None) -> Reply:
        """Draft a reply. With `case_id`, the draft is written onto that stored case."""
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
        elif specialist == VERSION:
            from .concierge import version_answer

            answer = version_answer(self.db, customer_ref=customer_ref,
                                    product_slug=product_slug, question=message)
            reply = Reply(specialist=specialist, body=answer.answer,
                          cited_version=answer.cited_version or None,
                          escalated=answer.escalated,
                          escalation_reason=("no recorded order to read the version from"
                                             if answer.escalated else ""))
        elif cir is None:
            # The version the buyer owns is recorded at sale time; if it is, say so rather
            # than asking them for something the company already knows.
            from .concierge import version_answer

            owned = version_answer(self.db, customer_ref=customer_ref,
                                   product_slug=product_slug, question=message)
            known = "" if owned.escalated else f" Our records show: {owned.answer}"
            reply = Reply(
                specialist=specialist,
                body=("We need to know which pattern this is about before answering — we "
                      "answer from the exact version you bought rather than from memory."
                      + known),
                cited_version=owned.cited_version or None,
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
            self._link_lessons(reply, cir)

        check_reply(reply.body)
        self._record(customer_ref, product_slug, version, message, reply, case_id=case_id)
        return reply

    def _link_lessons(self, reply: Reply, cir) -> None:
        """Append approved Learn lessons the answer's pattern and specialist route to (F-808).

        Chosen by `learn.service.support_help_links`, which reads the knowledge graph, so a
        recorded topic edge changes which lessons a support answer offers (F-815). Only
        approved revisions, only absolute URLs on the owned origin; none when unconfigured.
        A Learn failure never blocks the reply -- the answer stands on the pattern alone.
        """
        try:
            from ..learn.service import support_help_links

            links = support_help_links(self.db, cir.to_dict(), reply.specialist)
        except Exception:  # noqa: BLE001 - help links are an addition, never a dependency
            return
        if not links:
            return
        reply.lesson_links = [{"slug": link["slug"], "revision": link["revision"],
                               "url": link["url"]} for link in links]
        reply.body = (reply.body + "\n\nStep-by-step technique help: "
                      + "; ".join(link["url"] for link in links))

    def _record(self, customer_ref, product_slug, version, message, reply: Reply, *,
                case_id: int | None = None) -> None:
        from ..core.models import SupportCase

        with self.db.session() as s:
            if case_id is not None:
                case = s.get(SupportCase, case_id)
                if case is None:
                    raise ValueError(f"no support case {case_id}")
                case.answer = reply.body
                case.specialist = reply.specialist
                case.escalated = reply.escalated
                case.resolved = not reply.escalated
                case.sent = False     # shadow mode: drafted and held, and recorded as such
                case.detail = {**dict(case.detail or {}),
                               **({"lesson_links": reply.lesson_links}
                                  if reply.lesson_links else {}),
                               "cited_rows": reply.cited_rows,
                               "defect_suspected": reply.defect_suspected,
                               "escalation_reason": reply.escalation_reason,
                               "awaiting_reply": False,
                               "drafted_at": utcnow().isoformat()}
                return
            s.add(SupportCase(
                customer_ref=customer_ref, product_slug=product_slug, version=version,
                question=message, answer=reply.body, specialist=reply.specialist,
                escalated=reply.escalated, resolved=not reply.escalated,
                sent=False,   # shadow mode: drafted and held, and recorded as such
                detail={"cited_rows": reply.cited_rows,
                        **({"lesson_links": reply.lesson_links} if reply.lesson_links else {}),
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
        from ..commerce.buyer_trust import support_readings

        return {
            "cases": len(cases),
            "by_specialist": by_specialist,
            "escalated": sum(1 for c in cases if c.escalated),
            "row_hotspots": hotspots,
            # #41: confusion contacts as a defect rate, and every open case against Etsy's
            # case window -- UNKNOWN, with no deadline computed, while no recorded policy
            # reading states the window in days.
            "readings": support_readings(self.db),
            # K8 F-689: the one CX workspace, as aggregates (no buyer text or reference).
            "workspace": _workspace_summary(self.db),
            "note": ("row hotspots are candidate defects, not confirmed ones. Confirmation "
                     "runs through the compiler, not through a vote."),
        }

    # -- intake and the triage cadence (#41) ---------------------------------------------

    def intake(self, *, customer_ref: str, message: str, product_slug: str | None = None,
               version: str | None = None, source: str = "intake") -> int:
        """Store an inbound message as an unanswered case, for the triage cadence to pick up.

        There is no messaging integration, so nothing calls this from outside yet. It is the
        one door an inbound message comes through when one exists, and it drafts nothing:
        drafting is `support.reply`'s job, enqueued by triage.
        """
        from ..core.models import SupportCase

        with self.db.session() as s:
            case = SupportCase(customer_ref=customer_ref, product_slug=product_slug,
                               version=version, question=message, answer="",
                               specialist=triage(message), escalated=False, resolved=False,
                               sent=False, detail={"awaiting_reply": True, "source": source})
            s.add(case)
            s.flush()
            return case.id

    def triage_cases(self, queue=None, *, now: datetime | None = None) -> dict:
        """Triage every stored case not yet triaged, and enqueue a draft for each that needs one.

        A case needs a reply when nothing has been drafted for it. Its reply is enqueued as a
        `support.reply` job keyed on the case, so a case is drafted once however often triage
        runs. Every case is also classified for confusion -- a buyer who thought they were
        buying a finished item, or expected something posted -- which is the contact #41 counts
        as a listing defect. Nothing is sent to anyone: a reply stays a draft in shadow mode.
        """
        from sqlalchemy import select

        from ..commerce.buyer_trust import case_window
        from ..core.models import SupportCase
        from ..queue.durable import DuplicateJob

        now = now or utcnow()
        window = case_window()
        triaged, enqueued, already = [], [], []
        with self.db.session() as s:
            cases = list(s.scalars(select(SupportCase).order_by(SupportCase.at,
                                                                SupportCase.id)))
            pending = []
            for case in cases:
                detail = dict(case.detail or {})
                if "triaged_at" not in detail:
                    confused = bool(CONFUSION.search(case.question or ""))
                    detail.update({"triaged_at": now.isoformat(),
                                   "theme": "confusion" if confused else "other",
                                   "triaged_specialist": triage(case.question or "")})
                    triaged.append(case.id)
                if window.get("known") and case.at is not None and not case.resolved:
                    at = case.at if case.at.tzinfo else case.at.replace(tzinfo=timezone.utc)
                    detail["resolve_before"] = (at + timedelta(days=window["days"])).isoformat()
                elif not case.resolved:
                    detail["resolve_before"] = "UNKNOWN"
                needs = not (case.answer or "").strip() and not detail.get("reply_job")
                detail["needs_reply"] = needs
                case.detail = detail
                if needs:
                    pending.append((case.id, case.customer_ref, case.product_slug,
                                    case.version, case.question))
                elif detail.get("reply_job") and not (case.answer or "").strip():
                    already.append(case.id)

        if queue is not None:
            from ..swarm.orchestrate import priority_for

            for case_id, customer, slug, version, question in pending:
                try:
                    job = queue.enqueue(
                        "support", "support.reply",
                        {"case_id": case_id, "customer_ref": customer, "slug": slug,
                         "version": version, "question": question},
                        idempotency_key=f"support.reply:case:{case_id}",
                        priority=priority_for("support.reply"))
                except DuplicateJob:
                    already.append(case_id)
                    continue
                with self.db.session() as s:
                    case = s.get(SupportCase, case_id)
                    case.detail = {**dict(case.detail or {}), "reply_job": job.id,
                                   "needs_reply": False}
                enqueued.append({"case": case_id, "job": job.id})

        return {"cases": len(cases), "triaged": triaged, "reply_jobs": enqueued,
                "awaiting_draft": already,
                "needing_reply": [p[0] for p in pending],
                "case_window": window,
                "confusion": confusion_reading(self.db),
                "sent": 0,
                "note": ("replies are drafts held in shadow mode; nothing is sent to anyone. "
                         "The case deadline is UNKNOWN unless a recorded policy reading "
                         "states the window in days")}

    def report_defect(self, *, product_slug: str, version: str, component: str, row: int,
                      customer_ref: str, description: str):
        """The only path that can change a pattern. Support itself still cannot."""
        from ..gates.incidents import DefectReport

        return self.tracker.report(DefectReport(product_slug, version, component, row,
                                                customer_ref, description))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- #41: confusion-driven contacts, counted from the triage runs ------------------------

# A buyer who did not realise they bought a digital pattern. The disclosures #41 requires --
# "DIGITAL CROCHET PATTERN -- NOT A FINISHED ITEM", download instructions -- exist to prevent
# exactly these, so each one is evidence that a listing failed to say something.
CONFUSION = re.compile(
    r"\bnot a finished\b|\bthought (it|this) was (a |an )?(finished|physical|real|actual)\b"
    r"|\b(expected|wanted) (a |an |the )?(finished|physical|made|real) (item|blanket|"
    r"product|piece|toy|garment|one)\b"
    r"|\b(when|where) (will|is|does) (it|my (item|order|package|parcel|blanket))\b[^.?!]{0,30}"
    r"\b(ship|shipped|arrive|come|delivered)\b"
    r"|\b(shipping|tracking number|postage|delivery date)\b"
    r"|\bdid ?n'?t (realis|realiz|know)e? (it|this) was (a |an |only a |just a )?"
    r"(digital|pattern|pdf|download)\b"
    r"|\b(only|just) (a |the )?(pattern|pdf|download)\b", re.I)

CONFUSION_THEME = "confusion"


def confusion_reading(db) -> dict:
    """Confusion contacts against orders, from the cases triage has classified (#41).

    Counted only over triaged cases, and reported against orders only when there are orders:
    with none, the rate is UNMEASURED rather than zero, because zero confused buyers out of
    zero buyers is not a clean listing.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry, SupportCase

    with db.session() as s:
        cases = [dict(c.detail or {}) for c in s.scalars(select(SupportCase))]
        sales = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))
    triaged = [d for d in cases if "triaged_at" in d]
    confused = [d for d in triaged if d.get("theme") == CONFUSION_THEME]
    refunds = [x for x in sales if (x.refunds_cad or 0) > 0]
    orders = len(sales)
    return {
        "measurable": bool(orders),
        "orders": orders,
        "cases": len(cases), "triaged": len(triaged),
        "confusion_contacts": len(confused),
        "refunds": len(refunds),
        "confusion_rate": round(len(confused) / orders, 4) if orders else "UNMEASURED",
        "refund_rate": round(len(refunds) / orders, 4) if orders else "UNMEASURED",
        "defect": bool(confused),
        "why": ("confusion contacts are a listing defect, counted from the cases the triage "
                "cadence classified" if orders else
                "no orders, so there is no rate; the contacts are counted and the rate is "
                "UNMEASURED rather than zero"),
    }


def _workspace_summary(db) -> dict:
    from .workspace import summary

    return summary(db)
