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

    from ..commerce import club, kill_table, reviews
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
    out["reviews"] = {
        "stars": reviews.distribution([]),
        "themes_from_support": themes,
        "routing": (reviews.route([reviews.Theme(key=k, category=c, count=n)
                                   for k, n in sorted(themes.items())
                                   if (c := _category(k)) is not None])
                    if any(_category(k) for k in themes) else
                    {"reading": "UNMEASURED",
                     "why": "no reviews and no support theme that is a praise, a "
                            "misunderstanding or a wish"}),
    }

    # #253: the club lane. Only the cadence question is answerable without buyers.
    out["club"] = {"research_plan": club.research_plan(), "may_launch": club.may_launch({})}

    # #256 (C-64): referral outcome from the customers and orders the ingest wrote, and every
    # declared mechanic checked against the measured contribution per customer. UNMEASURED
    # only while the order source has never produced a row -- never hard-coded.
    from datetime import datetime, timezone

    from ..commerce import order_readings

    rows = order_readings.orders(db)
    cohort = order_readings.cohort_block(
        db, as_of=datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
    block = order_readings.referral_block(
        db, rows, contribution_per_customer=cohort.get("lifetime_contribution_per_buyer_cad"))
    out["referral"] = {**block["outcome"], "mechanics": block["mechanics"],
                       "may_run": block["may_run"], "source_live": block["source_live"]}

    # #254: the personalisation catalogue per certified product -- what could be offered,
    # split by what it costs to honour. Nothing is offered until something is listed.
    out["personalisation"] = {slug: personalisation.catalogue(slug) for slug in certified}

    # #236: the month's Insights query plan, so the owner's reading session has a plan.
    out["insights_plan"] = insights_budget.allocate(db)
    return out


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
    summary = {
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
