"""The daily commerce readings: the machinery of every data- or owner-gated row, run (C-59).

Certification defect C-59: six rows parked on a gate named machinery that nothing in the
running system ever called -- the scale/kill table (#23), the Insights allocator (#236), the
club research lane (#253), the personalisation catalogue (#254), referral (#256) and review
learning (#257). A gate is honest only when the day the data arrives is the day the
machinery reads it; a library nobody calls reads nothing on that day either. So each one runs
here, daily, on what the database holds now, and records its reading. Today almost every
reading is UNMEASURED with the reason -- CA$0 revenue, no customers, no reviews, no listings
-- and that is the correct output, not a placeholder for one.

GREEN: reads the database, writes one audit row, spends nothing, messages nobody.
"""
from __future__ import annotations

from datetime import date

from .worker import JobContext, handlers

ACTION = "commerce.readings"


def read(db, *, today: date | None = None) -> dict:
    from sqlalchemy import select

    from ..commerce import club, kill_table, referral, reviews
    from ..core.models import PatternVersion, Product, SupportCase
    from ..intel import insights_budget
    from ..products import personalisation
    from ..scale import runrate

    today = today or date.today()
    got = runrate.observe(db, today=today)
    observed = got["observed"]
    out: dict = {"as_of": today.isoformat()}

    # #23: the numeric scale/kill table, on the funnel as recorded, beside the run-rate
    # constraint it must agree with.
    with db.session() as s:
        support_cases = s.query(SupportCase).count()
    # Refunds have no source until orders exist; None is UNMEASURED, never zero.
    out["kill_table"] = kill_table.compose(observed, support_cases=support_cases, refunds=None)

    # #257: review learning. This shop has no reviews; buyer themes that do exist come
    # from triaged support cases, and they are routed the same way review themes are.
    with db.session() as s:
        themes: dict[str, int] = {}
        for case in s.scalars(select(SupportCase)):
            theme = (case.detail or {}).get("theme")
            if theme:
                themes[theme] = themes.get(theme, 0) + 1
        certified = sorted({p.slug for p, v in s.execute(
            select(Product, PatternVersion).where(PatternVersion.product_id == Product.id,
                                                  PatternVersion.certified == True))})  # noqa: E712
    # C-60: the stars are read from the orders that carry a review rating (the order ingest
    # writes it on the order); none today, and the distribution refuses below its floor.
    stars = _review_stars(db)
    out["reviews"] = {
        "stars": reviews.distribution(stars),
        "themes_from_support": themes,
        "routing": (reviews.route([reviews.Theme(key=k, category=c, count=n)
                                   for k, n in sorted(themes.items())
                                   if (c := _category(k)) is not None])
                    if any(_category(k) for k in themes) else
                    {"reading": "UNMEASURED",
                     "why": "no reviews and no support theme that is a praise, a "
                            "misunderstanding or a wish"}),
    }

    # #253: the club lane. The cadence question is answered today from how long this
    # company's own certified releases actually take; the other three are answered from
    # customers and support cases the day they exist, and stay unanswered until then.
    answers, cadence, club_evidence = _club_answers(db)
    out["club"] = {"research_plan": club.research_plan(),
                   "cadence": club.check_cadence(cadence) if cadence else {
                       "fits": None, "why": club_evidence["cadence"]},
                   "answers": answers, "evidence": club_evidence,
                   "may_launch": club.may_launch(answers, cadence=cadence)}

    # #256: referral outcome, measured only from attributed customers and contribution.
    out["referral"] = _referral(db)

    # #254: the personalisation catalogue per certified product -- what could be offered,
    # split by what it costs to honour. Nothing is offered until something is listed.
    out["personalisation"] = {slug: personalisation.catalogue(slug) for slug in certified}

    # #236: the month's Insights query plan, so the owner's reading session has a plan.
    out["insights_plan"] = insights_budget.allocate(db)
    return out


REFERRAL_SOURCE = "referral"
CLUB_PERIOD_DAYS = 30
CLUB_MIN_CUSTOMERS = 20
CLUB_DEMAND_REPEAT_SHARE = 0.2
CLUB_SUPPORT_PER_CUSTOMER = 0.25


def _review_stars(db) -> list[int]:
    """Star ratings buyers actually left, from the orders that carry one."""
    from sqlalchemy import select

    from ..core.models import Order

    stars: list[int] = []
    with db.session() as s:
        for o in s.scalars(select(Order).where(Order.reviewed == True)):  # noqa: E712
            value = (o.detail or {}).get("review_stars", (o.detail or {}).get("rating"))
            if isinstance(value, (int, float)) and int(value) in (1, 2, 3, 4, 5):
                stars.append(int(value))
    return stars


def _club_answers(db):
    """The four club questions, each answered from rows or left unanswered with the reason."""
    from statistics import median

    from sqlalchemy import select

    from ..commerce.club import Cadence
    from ..core.models import Customer, Order, PatternVersion, SupportCase

    answers: dict[str, bool] = {}
    evidence: dict[str, str] = {}
    with db.session() as s:
        certified = sorted(pv.created_at for pv in s.scalars(select(PatternVersion).where(
            PatternVersion.certified == True)) if pv.created_at)  # noqa: E712
        customers = list(s.scalars(select(Customer)))
        repeaters = {o.customer_id for o in s.scalars(select(Order).where(
            Order.is_repeat == True))}  # noqa: E712
        cases = s.query(SupportCase).count()

    cadence = None
    if len(certified) >= 3:
        gaps = [(b - a).total_seconds() / 86400.0 for a, b in zip(certified, certified[1:])]
        lead = max(0.1, median(gaps))
        cadence = Cadence(period_days=CLUB_PERIOD_DAYS, product_lead_days=round(lead, 2))
        evidence["cadence"] = (f"median {lead:.1f} days between the last {len(certified)} "
                               f"certified releases")
    else:
        evidence["cadence"] = (f"{len(certified)} certified release(s): a lead time needs at "
                               f"least three to take a median of")

    if len(customers) >= CLUB_MIN_CUSTOMERS:
        share = len(repeaters) / len(customers)
        answers["demand"] = share >= CLUB_DEMAND_REPEAT_SHARE
        evidence["demand"] = f"{len(repeaters)} of {len(customers)} customers bought again"
        per = cases / len(customers)
        answers["support_burden"] = per <= CLUB_SUPPORT_PER_CUSTOMER
        evidence["support_burden"] = f"{cases} support case(s) over {len(customers)} customers"
    else:
        evidence["demand"] = evidence["support_burden"] = (
            f"{len(customers)} customer(s) against the {CLUB_MIN_CUSTOMERS} a club question "
            f"needs; unanswered, not answered no")
    evidence["platform_feasibility"] = ("no seller-policy reading on recurring charges is "
                                        "recorded; unanswered")
    return answers, cadence, evidence


def _referral(db) -> dict:
    """Referral outcome from attributed customers, their orders and the rewards paid."""
    from sqlalchemy import select

    from ..commerce import referral
    from ..core.models import Customer, LedgerEntry, Order

    with db.session() as s:
        refs = [c.id for c in s.scalars(select(Customer).where(
            Customer.acquisition_source == REFERRAL_SOURCE))]
        any_customers = s.query(Customer).count() > 0
        contribution = sum(float(o.contribution_cad or 0.0) for o in s.scalars(
            select(Order).where(Order.customer_id.in_(refs), Order.refunded == False))  # noqa: E712
        ) if refs else 0.0
        rewards = sum(float(x.expense_cad or 0.0) for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "referral_reward")))
    if not any_customers:
        return referral.outcome(attributed_customers=None, contribution_cad=None,
                                reward_spend_cad=rewards)
    return referral.outcome(attributed_customers=len(refs),
                            contribution_cad=round(contribution, 2),
                            reward_spend_cad=round(rewards, 2))


def act(db, reading: dict) -> dict:
    """What the readings change: incidents for listing-routed review themes and a referral
    programme that costs more than it earns, and an owner decision if a club may launch."""
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..ops.incident_lifecycle import open_or_restate, reconcile

    opened: list[str] = []
    routed = [f for f in (reading["reviews"]["routing"].get("findings") or [])
              if f.get("route_to") == "listing"]
    wanted = {f"review_route:{f['theme']}" for f in routed}
    with db.session() as s:
        for f in routed:
            _row, new = open_or_restate(
                s, signature=f"review_route:{f['theme']}", severity="P2",
                summary=(f"buyers repeatedly misunderstand {f['theme']!r}: {f['why']}"),
                detail={"theme": f["theme"], "count": f["count"],
                        "disclosure": f.get("disclosure")})
            if new:
                opened.append(f["theme"])
        closed = reconcile(s, "review_route:", lambda row: row.signature in wanted,
                           resolution="the theme no longer recurs in the readings")
        ref = reading["referral"]
        if ref.get("measurable") and not ref.get("worth_it"):
            open_or_restate(s, signature="referral:negative", severity="P2",
                            summary=f"referral rewards exceed contribution: {ref['why']}",
                            detail=ref)
        club_owner = None
        if reading["club"]["may_launch"].get("may_launch"):
            key = "club:launch_decision"
            if s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                  OwnerAction.done == False)) is None:  # noqa: E712
                s.add(OwnerAction(requirement_key=key,
                                  action="Decide whether to launch the pattern club",
                                  reason=("every research question is answered yes and the "
                                          "cadence fits: " + reading["club"]["may_launch"]
                                          ["why"]),
                                  max_cost_cad=0.0, minutes=15,
                                  consequence_of_delay="the club stays unlaunched",
                                  blocks="#253"))
                club_owner = key
    return {"review_incidents_opened": opened, "review_incidents_closed": closed["resolved"],
            "club_owner_action": club_owner}


def _category(theme: str) -> str | None:
    """A support theme's review category, or None when it is none of the three."""
    t = theme.lower()
    if "confus" in t or "misunderst" in t or "expected" in t:
        return "misunderstood"
    if "wish" in t or "request" in t:
        return "wished_for"
    if "love" in t or "praise" in t:
        return "praised"
    return None


@handlers.register(ACTION)
def handle_commerce_readings(ctx: JobContext) -> dict:
    as_of = ctx.job.inputs.get("as_of")
    today = date.fromisoformat(as_of) if as_of else None
    reading = read(ctx.db, today=today)
    acted = act(ctx.db, reading)
    summary = {
        "acted": acted,
        "review_stars": reading["reviews"]["stars"].get("reviews"),
        "club_cadence_fits": reading["club"]["cadence"].get("fits"),
        "kill_table": (reading["kill_table"].get("fired")
                       or reading["kill_table"].get("verdict") or "UNMEASURED"),
        "review_themes": len(reading["reviews"]["themes_from_support"]),
        "club_may_launch": reading["club"]["may_launch"].get("may_launch"),
        "referral_measurable": reading["referral"].get("measurable"),
        "personalisation_products": len(reading["personalisation"]),
        "insights_keywords": sum(len(v) for v in
                                 (reading["insights_plan"].get("keywords") or {}).values()),
    }
    ctx.audit(ACTION, detail={"summary": summary, "reading": _jsonable(reading)})
    return summary


def _jsonable(obj):
    import json

    return json.loads(json.dumps(obj, default=str))
