"""Growth, distribution, paid media and customer experience, run (certification C-60, C-66,
C-70, part of C-67).

The final function-level audit of 9434c53 found this cluster's libraries complete and
unreached: `ads.campaign` and `ads.adjust` were granted to the ads agent with no handler, so
opening the ad-authority gate would have run nothing; the pin, cluster, video, creator, tool,
gallery, interview, friction, promotion and benchmark libraries were called only by tests; the
weekly reallocation and the seasonal roll-forward were written down and never reached the
queue; and the war-room board was computed for a page and read by no agent.

Five handlers close that, each on a cadence, each reading the database, each doing something
with what it read:

  * `ads.adjust` (daily, ads agent) plans paid media from rows -- organic-first proof (#242),
    risk-adjusted allowable CAC and the new/blended CAC split (#243), the Offsite Ads split
    (#244), Share & Save (#245), the trust gate (#17), contribution per visitor (#24),
    pre-season learning windows (#294) and winner escalation (#295). It enqueues
    `ads.campaign` only when the owner's ad authority exists and every gate passes, and it
    escalates a budget increase to the owner queue with the exact economics.
  * `ads.campaign` is hard-refused while the ad-authority gate is closed, enforces the owner's
    caps in code before anything else, and in shadow records the planned campaign and spends
    nothing. There is no ad integration; in production it still refuses, by name.
  * `growth.distribution` (daily, growth agent) plans pins from the calendar's milestones and
    amplifies winners with new angles (#246, #295), builds search clusters from counted
    complaint themes (#247), plans video modules and re-plans them when the design moves
    (#248), reads the creator roster as a portfolio and stops measured-weak relationships
    (#249), runs the tester graduation check (#250), the lifecycle flow and frequency checks
    (#251), the free-tool checks (#255), the gallery and proof-lift reading (#258) and the
    interview gate (#260).
  * `growth.journey` (daily, growth agent) audits every listing for buyer-journey friction
    (#261) and the four before-the-first-customer priorities (#259), raising and resolving
    incidents; reads promotions for incrementality against a control (#19); builds
    conversion baselines and ranks opportunities from observations in the database
    (#238, #239); and attaches proof to the rows it came from (#17).
  * `growth.steer` (hourly, swarm steward) applies the week's reallocation (#264), the
    seasonal roll-forward (#267), fast-lane admission (#291) and the war-room board (#276)
    to the queue: pending work for the constraint's owners, the occasion that now holds
    capacity and the admitted products moves up; work for an occasion that no longer holds
    capacity moves down; the experiment queue is ordered toward the constraint.

Shadow mode: nothing here publishes, sends, spends or contacts anybody. With no customers,
listings or traffic most readings are UNMEASURED with the reason, which is the correct output.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .worker import CapabilityNotEnabled, JobContext, handlers

ADS_KIND = "ads.plan"
DISTRIBUTION_KIND = "growth.distribution"
JOURNEY_KIND = "growth.journey"
STEER_KIND = "growth.steer"
UNMEASURED = "UNMEASURED"

AD_SOURCES = ("etsy_ads", "offsite_ads", "paid_ads")
# #294: paid learning for a seasonal product opens at the calendar's indexing milestone and
# must have begun by its promotional ramp, so CTR/CAC evidence exists before peak demand.
AD_LEARNING_OPENS_AT = "listing_indexing_date"
AD_LEARNING_BY = "promotional_ramp"
# #295: an increase of more than this share of the current daily cap is the owner's decision.
AD_SCALING_BAND = 0.25
# How far a steered job moves, in priority points. Bounded: steering reorders within and
# across adjacent bands, it never lifts exploration above a customer incident.
STEER_CREDIT = 10
MAX_STEERED_PER_RUN = 200
FLAGSHIP_MIN_HOURS = 20.0
DEFAULT_PIN_ANGLES = ("finished_object", "fabric_detail", "in_progress")


# ---- shared reads ----------------------------------------------------------------------------

def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _today(ctx: JobContext) -> date:
    as_of = (ctx.job.inputs or {}).get("as_of")
    return date.fromisoformat(as_of) if as_of else date.today()


def catalogue(db) -> dict[str, dict]:
    """Certified products with their seed, current release and listing, from rows."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..radar.opportunity import POOL

    seeds = {m.slug: m for m in POOL}
    out: dict[str, dict] = {}
    with db.session() as s:
        listings = {}
        for r in s.scalars(select(Listing)):
            listings.setdefault(r.product_slug, []).append(r)
        for p in s.scalars(select(Product)):
            pvs = [pv for pv in s.scalars(select(PatternVersion).where(
                PatternVersion.product_id == p.id, PatternVersion.certified == True))]  # noqa: E712
            if not pvs:
                continue
            pv = max(pvs, key=lambda v: (v.created_at or datetime.min, v.id))
            seed = seeds.get(p.slug) or next(
                (m for m in POOL if p.slug.startswith(m.slug)), None)
            rows = sorted(listings.get(p.slug, []), key=lambda r: r.id)
            listing = rows[-1] if rows else None
            out[p.slug] = {
                "slug": p.slug, "version": pv.version,
                "release_hash": pv.release_hash or "",
                "seed": seed,
                "season": seed.season if seed else None,
                "category": seed.category if seed else "",
                "maker_hours": tuple(seed.maker_hours) if seed else (0.0, 0.0),
                "listing": ({"id": listing.id, "title": listing.title,
                             "description": listing.description,
                             "tags": list(listing.tags or []),
                             "price_cad": float(listing.price_cad or 0.0),
                             "state": listing.state, "version": listing.version}
                            if listing else None),
            }
    return out


def record(db, kind: str, period_key: str, payload: dict) -> int:
    """Write one reading, replacing an earlier run of the same kind and period."""
    import json

    from sqlalchemy import select

    from ..core.models import OperatingReading

    payload = json.loads(json.dumps(payload, default=str))
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == kind, OperatingReading.period_key == period_key))
        if row is None:
            row = OperatingReading(kind=kind, period_key=period_key)
            s.add(row)
        row.payload = payload
        row.at = datetime.now(timezone.utc)
        s.flush()
        return int(row.id)


def latest(db, kind: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        return dict(row.payload or {}) if row is not None else None


def _events(today: date) -> dict[str, dict]:
    from ..seasonal.calendar import rolling

    return {e["event"]: e for e in rolling(today)["events"]}


def complaint_themes(db) -> dict[str, int]:
    """Counted complaint themes: recurring benchmark-review themes plus buyer support cases.

    Only themes `growth.clusters` has a question for are kept, because a theme with no
    question behind it cannot seed a cluster or a troubleshooting clip.
    """
    from sqlalchemy import select

    from ..core.models import LearningObservation, SupportCase
    from ..growth.clusters import QUESTIONS

    counts: dict[str, int] = {}
    with db.session() as s:
        rows = list(s.scalars(select(LearningObservation).where(
            LearningObservation.domain == "customer_pain")))
        newest = max(rows, key=lambda r: (r.id or 0)) if rows else None
        for theme, n in ((newest.detail or {}).get("recurring") or {}).items() if newest else ():
            if theme in QUESTIONS and isinstance(n, (int, float)):
                counts[theme] = counts.get(theme, 0) + int(n)
        for case in s.scalars(select(SupportCase)):
            theme = (case.detail or {}).get("theme")
            if theme in QUESTIONS:
                counts[theme] = counts.get(theme, 0) + 1
    return counts


# ---- paid media: ads.adjust and ads.campaign ------------------------------------------------

def ad_authority(db) -> dict:
    """The owner's ad authority as the executor's gate reads it: an unpaused positive cap."""
    from sqlalchemy import select

    from ..core.models import SpendLimit

    with db.session() as s:
        limit = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        if limit is None:
            return {"granted": False, "why": ("no SpendLimit row for 'ads': the owner has not "
                                              "set an advertising budget")}
        granted = bool(limit.daily_cap_cad > 0 and not limit.paused)
        return {"granted": granted, "daily_cap_cad": float(limit.daily_cap_cad),
                "lifetime_cap_cad": float(limit.lifetime_cap_cad or 0.0),
                "spent_today_cad": float(limit.spent_today_cad or 0.0),
                "spent_lifetime_cad": float(limit.spent_lifetime_cad or 0.0),
                "paused": bool(limit.paused),
                "why": ("the owner's ad budget is set and unpaused" if granted else
                        "the ad budget is zero or paused")}


def organic_period(db, slug: str):
    """A listing's traffic that no ad bought, from its recorded outcome periods."""
    from sqlalchemy import select

    from ..commerce.paid_media import OrganicPeriod
    from ..core.models import ListingOutcome

    with db.session() as s:
        rows = [r for r in s.scalars(select(ListingOutcome).where(
            ListingOutcome.product_slug == slug))
            if not (r.detail or {}).get("paid")
            and (r.detail or {}).get("traffic_source") not in AD_SOURCES]
    if not rows:
        return None
    start = min(date.fromisoformat(r.period_start) for r in rows)
    end = max(date.fromisoformat(r.period_end) for r in rows)
    return OrganicPeriod(days=(end - start).days + 1,
                         visits=sum(int(r.visits or 0) for r in rows),
                         orders=sum(int(r.orders or 0) for r in rows if r.orders is not None),
                         impressions=sum(int(r.impressions or 0) for r in rows))


def _slug_orders(db, slug: str) -> list:
    from sqlalchemy import select

    from ..core.models import Order

    with db.session() as s:
        return [(bool(o.refunded), float(o.revenue_cad or 0.0), float(o.contribution_cad or 0.0),
                 bool(o.offsite_ad_attributed), _aware(o.at))
                for o in s.scalars(select(Order).where(Order.product_slug == slug))]


def _allowable_cac(price: float, orders: list) -> dict:
    """#243's risk-adjusted allowable CAC, with the refund rate measured or the CAC refused."""
    from ..commerce.benchmarks import MIN_ORDERS_FOR_REFUND_RATE
    from ..commerce.pricing import fees
    from ..scale.runrate import allowable_cac_risk_adjusted

    if price <= 0:
        return {"status": UNMEASURED, "why": "no listed price"}
    if len(orders) < MIN_ORDERS_FOR_REFUND_RATE:
        return {"status": UNMEASURED,
                "why": (f"{len(orders)} order(s) against the {MIN_ORDERS_FOR_REFUND_RATE} a "
                        f"refund rate needs; an allowable CAC on an assumed refund rate is "
                        f"a guess about the thing that decides whether ads lose money")}
    refund_rate = sum(1 for o in orders if o[0]) / len(orders)
    fee_rate = min(0.99, 1 - fees(price).net_cad / price)
    got = allowable_cac_risk_adjusted(price_cad=price, fee_rate=fee_rate,
                                      refund_rate=min(refund_rate, 0.99), discount_rate=0.0,
                                      cost_of_sale_cad=0.0, expected_repeat_contribution_cad=0.0)
    got["status"] = "measured"
    return got


def _learning_window(item: dict, events: dict, today: date) -> dict:
    """#294: whether a seasonal product is inside its pre-season paid-learning window."""
    from ..growth.pins import MILESTONE_DAYS

    season = item.get("season")
    if not season:
        return {"seasonal": False, "status": "evergreen"}
    event = events.get(season)
    if event is None:
        return {"seasonal": True, "status": "no_upcoming_occasion"}
    event_date = date.fromisoformat(event["event_date"])
    opens = event_date - timedelta(days=MILESTONE_DAYS[AD_LEARNING_OPENS_AT])
    by = event_date - timedelta(days=MILESTONE_DAYS[AD_LEARNING_BY])
    status = ("too_early" if today < opens else
              "learning_window_open" if today <= by else "late_for_learning")
    return {"seasonal": True, "event": season, "event_date": event_date.isoformat(),
            "opens": opens.isoformat(), "learn_by": by.isoformat(), "status": status,
            "why": ("paid learning starts at the indexing milestone and must be running by the "
                    "promotional ramp, so CTR, conversion and CAC are known before peak "
                    "demand rather than discovered during it (#294)")}


def ads_plan(db, *, today: date | None = None) -> dict:
    """Every paid-media decision the rows support, and what the plan would enqueue."""
    from sqlalchemy import select

    from ..commerce import first_hundred, paid_media, trust
    from ..core.models import Order
    from ..scale import evidence, runrate
    from ..scale.target import USD_PER_CAD
    from ..scale.war_room import board as war_board
    from ..support import service

    today = today or date.today()
    authority = ad_authority(db)
    readiness, _detail = first_hundred.readiness_from_evidence(db)
    level = service.service_level(db)
    gate = trust.may_scale_ads(db, disclosure_ok=bool(readiness.truthful_expectations),
                               support_meets_target=level.get("meets_target"))
    per_visitor = runrate.per_visitor_from_db(db, today=today)
    cpv = {r["slug"]: r["contribution_per_visitor"] for r in per_visitor.get("ranked") or []}
    events = _events(today)

    products = []
    for slug, item in sorted(catalogue(db).items()):
        listing = item["listing"]
        price = listing["price_cad"] if listing else 0.0
        orders = _slug_orders(db, slug)
        organic = organic_period(db, slug)
        organic_gate = paid_media.organic_first_gate(organic)
        cac = _allowable_cac(price, orders)
        window = _learning_window(item, events, today)
        reasons = []
        if not authority["granted"]:
            reasons.append("ad_authority: " + authority["why"])
        if not gate["may_scale"]:
            reasons.append(f"trust (#17): {gate['blocking']}")
        if not listing or listing["state"] != "published":
            reasons.append("no published listing to send traffic to")
        if not organic_gate["allowed"]:
            reasons.append(f"organic-first (#242): {organic_gate['reason']}")
        if cac["status"] != "measured" or cac.get("allowable_cac_cad", 0) <= 0:
            reasons.append(f"allowable CAC (#243): {cac.get('why') or cac.get('note')}")
        if window["seasonal"] and window["status"] not in ("learning_window_open",):
            reasons.append(f"pre-season window (#294): {window['status']}")
        products.append({
            "slug": slug, "price_cad": price,
            "contribution_per_visitor": cpv.get(slug, UNMEASURED),
            "organic_first": organic_gate, "allowable_cac": cac,
            "learning_window": window,
            "eligible": not reasons, "blocked_by": reasons,
        })
    # #24: paid media optimises contribution per visitor, so eligible products are funded in
    # that order and an unmeasured one goes last rather than first.
    eligible = sorted((p for p in products if p["eligible"]),
                      key=lambda p: -(p["contribution_per_visitor"]
                                      if isinstance(p["contribution_per_visitor"], float)
                                      else -1.0))

    # #244: Offsite Ads orders tracked apart, on the policy reading's own terms.
    with db.session() as s:
        orders_all = [o for o in s.scalars(select(Order)) if not o.refunded]
    if orders_all:
        revenue = sum(float(o.revenue_cad or 0.0) for o in orders_all)
        contribution = sum(float(o.contribution_cad or 0.0) for o in orders_all)
        since = datetime.now(timezone.utc) - timedelta(days=365)
        trailing = sum(float(o.revenue_cad or 0.0) for o in orders_all
                       if _aware(o.at) and _aware(o.at) >= since)
        offsite = paid_media.offsite_ads_forecast(
            orders=len(orders_all), aov_usd=(revenue / len(orders_all)) * USD_PER_CAD,
            offsite_share=sum(1 for o in orders_all if o.offsite_ad_attributed) / len(orders_all),
            trailing_365_sales_usd=trailing * USD_PER_CAD,
            contribution_rate=min(1.0, max(0.01, contribution / revenue)) if revenue else 1.0)
    else:
        offsite = {"status": UNMEASURED, "why": "no order exists to attribute",
                   "terms": {k: v for k, v in paid_media.offsite_ads_terms().items()
                             if k != "source"}}
    # #245: no official Share & Save rate is recorded, so the comparison is refused by name.
    share_and_save = paid_media.share_and_save(orders_via_link=0, aov_cad=0.0,
                                               contribution_rate=1.0, fee_benefit_rate=None)

    # #295: winners from the board. A budget increase past the scaling band is the owner's.
    board = war_board(db)["board"]
    winners = (board["winner_alerts"]["value"] or []) \
        if board["winner_alerts"]["status"] == "measured" else []
    escalations = []
    if authority["granted"]:
        for w in winners:
            proposed = round(authority["daily_cap_cad"] * (1 + 2 * AD_SCALING_BAND), 2)
            escalations.append({
                "product": w["product"], "current_daily_cap_cad": authority["daily_cap_cad"],
                "proposed_daily_cap_cad": proposed,
                "contribution_cad_30d": w["contribution_cad"],
                "multiple_of_median": w["multiple_of_median"],
                "why": (f"a winner at {w['multiple_of_median']}x the median contribution; the "
                        f"increase exceeds the {AD_SCALING_BAND:.0%} band the plan may move "
                        f"on its own")})
    return {
        "as_of": today.isoformat(),
        "authority": authority,
        "trust_gate": {"may_scale": gate["may_scale"], "blocking": gate["blocking"]},
        "service_level": {"meets_target": level.get("meets_target"),
                          "draft_ready": level.get("draft_ready")},
        "cac_split": evidence.cac(db, today=today),
        "offsite_ads": offsite,
        "share_and_save": share_and_save,
        "products": products,
        "eligible": [p["slug"] for p in eligible],
        "winners": winners,
        "escalations": escalations,
        "spend_cad": 0.0,
    }


@handlers.register("ads.adjust")
def handle_ads_adjust(ctx: JobContext) -> dict:
    """Plan paid media from the database; enqueue campaigns only through the owner's gate.

    GREEN in effect whatever the agent's authority: it reads rows, writes one reading, and
    enqueues `ads.campaign` only for an eligible product when the owner's ad budget exists.
    A campaign job still has to pass the caps and the phase itself.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction

    today = _today(ctx)
    plan = ads_plan(ctx.db, today=today)
    enqueued = []
    if plan["authority"]["granted"]:
        remaining = max(0.0, plan["authority"]["daily_cap_cad"]
                        - plan["authority"]["spent_today_cad"])
        per = round(remaining / max(1, len(plan["eligible"])), 2) if plan["eligible"] else 0.0
        by_slug = {p["slug"]: p for p in plan["products"]}
        for slug in plan["eligible"]:
            if per <= 0:
                break
            job = ctx.enqueue("ads", "ads.campaign",
                              {"slug": slug, "daily_budget_cad": per,
                               "max_cac_cad": by_slug[slug]["allowable_cac"]["allowable_cac_cad"],
                               "as_of": today.isoformat()},
                              idempotency_key=f"ads.campaign:{slug}:{today.isoformat()}")
            if job is not None:
                enqueued.append(slug)
        with ctx.db.session() as s:
            for e in plan["escalations"]:
                key = f"ads.scale:{e['product']}"
                open_row = s.scalar(select(OwnerAction).where(
                    OwnerAction.requirement_key == key, OwnerAction.done == False))  # noqa: E712
                if open_row is None:
                    s.add(OwnerAction(
                        requirement_key=key,
                        action=(f"Approve raising the ads daily cap from "
                                f"CA${e['current_daily_cap_cad']:.2f} to "
                                f"CA${e['proposed_daily_cap_cad']:.2f} for {e['product']}"),
                        reason=e["why"] + f"; 30-day contribution CA${e['contribution_cad_30d']}",
                        max_cost_cad=round(30 * (e["proposed_daily_cap_cad"]
                                                 - e["current_daily_cap_cad"]), 2),
                        minutes=5, consequence_of_delay="the winner stays on the current cap",
                        blocks="#295"))
    plan["enqueued"] = enqueued
    reading_id = record(ctx.db, ADS_KIND, today.isoformat(), plan)
    summary = {"authority": plan["authority"]["granted"],
               "trust_may_scale": plan["trust_gate"]["may_scale"],
               "products": len(plan["products"]), "eligible": plan["eligible"],
               "enqueued": enqueued, "escalations": len(plan["escalations"]),
               "spend_cad": 0.0, "reading_id": reading_id}
    ctx.audit("ads.adjusted", detail=summary)
    return summary


@handlers.register("ads.campaign")
def handle_ads_campaign(ctx: JobContext) -> dict:
    """One campaign, refused by the owner gate first and by the caps second, and never spent.

    Hard-refused (terminal) while the ad-authority gate is closed: a campaign job that exists
    without an owner budget is a job something should not have queued. With the budget set,
    the amount is checked in code against the owner's daily and lifetime caps and then passed
    through `paid_media.authorise_spend`, which refuses outside production. In shadow that is
    the end: the campaign is recorded as planned with CA$0 spent. In production it still
    refuses by name, because no ad integration exists to spend through.
    """
    from ..commerce import paid_media

    i = dict(ctx.job.inputs or {})
    slug = i.get("slug") or ""
    authority = ad_authority(ctx.db)
    if not authority["granted"]:
        ctx.audit("ads.refused", artifact=slug, detail={"gate": "ad_authority",
                                                        "why": authority["why"]})
        raise CapabilityNotEnabled(
            f"ad_authority is closed ({authority['why']}); a campaign is the owner's spend "
            f"decision and no budget exists for it")

    amount = float(i.get("daily_budget_cad") or 0.0)
    daily_cap = authority["daily_cap_cad"]
    lifetime = authority["lifetime_cap_cad"] or daily_cap * 30
    headroom = min(daily_cap - authority["spent_today_cad"],
                   lifetime - authority["spent_lifetime_cad"])
    if amount <= 0 or amount > headroom:
        ctx.audit("ads.refused", artifact=slug,
                  detail={"gate": "budget_ceiling", "amount_cad": amount,
                          "headroom_cad": round(headroom, 2)})
        return {"planned": False, "spent_cad": 0.0,
                "refused": (f"CA${amount:.2f} against CA${headroom:.2f} of headroom under the "
                            f"owner's caps")}
    max_cac = float(i.get("max_cac_cad") or 0.0)
    campaign_cap = min(lifetime, max(daily_cap, paid_media.CONSERVATIVE_CAPS.campaign_cad))
    try:
        caps = paid_media.Caps(daily_cad=daily_cap, campaign_cad=campaign_cap,
                               monthly_cad=max(campaign_cap, min(lifetime, daily_cap * 30)),
                               max_test_loss_cad=campaign_cap,
                               max_cac_cad=max_cac if max_cac > 0 else -1.0)
        caps.validate()
    except ValueError as e:
        ctx.audit("ads.refused", artifact=slug, detail={"gate": "caps", "why": str(e)})
        return {"planned": False, "spent_cad": 0.0, "refused": str(e)}
    state = paid_media.CampaignState(name=slug, spend_today_cad=authority["spent_today_cad"],
                                     spend_month_cad=authority["spent_lifetime_cad"])
    try:
        paid_media.authorise_spend(state, caps, amount, phase=ctx.phase, owner_granted=True)
    except paid_media.PaidMediaNotAuthorised as e:
        detail = {"slug": slug, "amount_cad": amount, "caps": {
            "daily_cad": caps.daily_cad, "campaign_cad": caps.campaign_cad,
            "monthly_cad": caps.monthly_cad, "max_cac_cad": caps.max_cac_cad},
            "refused_by": str(e), "spent_cad": 0.0, "phase": ctx.phase.value}
        ctx.audit("ads.campaign_planned", artifact=slug, detail=detail)
        return {"planned": True, **detail}
    raise CapabilityNotEnabled(
        "every gate passed and there is no ad integration to spend through; nothing was "
        "spent. Building the integration is the next step, not a spend")


# ---- growth.distribution ----------------------------------------------------------------------

def _winners(db) -> list[str]:
    from ..scale.war_room import board

    b = board(db)["board"]["winner_alerts"]
    return [w["product"] for w in (b.get("value") or [])] if b["status"] == "measured" else []


def plan_pins(db, items: dict, *, today: date, previous: dict | None,
              winners: list[str]) -> dict:
    """#246 / #295: a pin set per certified product, dated from the calendar's milestones,
    grown by one new angle when the product is a winner."""
    from ..growth import pins

    events = _events(today)
    before = {p["slug"]: p for p in (previous or {}).get("pins", {}).get("products", [])}
    rows = []
    for slug, item in sorted(items.items()):
        listing = item["listing"]
        angles = list(before.get(slug, {}).get("angles") or DEFAULT_PIN_ANGLES)
        amplified = None
        if slug in winners:
            winner = pins.Pin(product_slug=slug, angle=angles[0])
            existing = [pins.Pin(product_slug=slug, angle=a) for a in angles]
            amplified = pins.amplify(winner, existing)
            if amplified["next_angles"]:
                angles.append(amplified["next_angles"][0])
        destination = f"listing:{listing['id']}" if listing and listing["state"] == "published" \
            else ""
        keywords = tuple((listing or {}).get("tags", [])[:3])
        pin_set = [pins.Pin(product_slug=slug, angle=a, destination=destination,
                            keywords=keywords, board=item["category"] or "") for a in angles]
        check = pins.check_set(pin_set)
        event = events.get(item["season"]) if item["season"] else None
        sched = pins.schedule(event_date=date.fromisoformat(event["event_date"]), today=today) \
            if event else None
        rows.append({"slug": slug, "angles": angles, "check": check, "schedule": sched,
                     "amplified": amplified,
                     "landable": bool(destination),
                     "status": ("ready" if check["ok"] else "held")})
    return {"products": rows, "ready": [r["slug"] for r in rows if r["status"] == "ready"],
            "amplified": [r["slug"] for r in rows if r["amplified"]]}


def plan_clusters(items: dict, themes: dict[str, int]) -> dict:
    """#247: clusters per department from counted themes, each ending on a certified product."""
    from ..growth import clusters
    from ..seasonal.daily import DEPARTMENT_OF

    pods: dict[str, list[str]] = {}
    for slug, item in sorted(items.items()):
        pod = DEPARTMENT_OF.get(item["category"])
        if pod:
            pods.setdefault(pod, []).append(slug)
    out = {}
    for pod, slugs in sorted(pods.items()):
        out[pod] = clusters.plan(themes, pod=pod,
                                 destinations={t: slugs[0] for t in themes})
    return {"themes": themes, "by_department": out,
            "buildable": sorted({t for p in out.values() for t in p["ranked"]}),
            "measurement": clusters.measurement()}


def plan_video(items: dict, themes: dict[str, int], previous: dict | None) -> dict:
    """#248: modules per flagship, troubleshooting seeded from reported problems, and every
    module re-planned when the design it was cut from has moved."""
    from ..growth import video

    before = {p["slug"]: p for p in (previous or {}).get("video", {}).get("products", [])}
    rows, stale = [], []
    for slug, item in sorted(items.items()):
        if max(item["maker_hours"] or (0.0,)) < FLAGSHIP_MIN_HOURS:
            continue
        fingerprint = item["release_hash"] or item["version"]
        prior = before.get(slug)
        if prior and prior.get("design_fingerprint") != fingerprint:
            stale.append({"slug": slug, "was": prior.get("design_fingerprint"),
                          "now": fingerprint,
                          "why": ("the design moved, so every module cut from the old "
                                  "canonical tutorial is stale and is re-planned")})
        planned = video.plan(slug, canonical_ref=f"tutorial:{slug}@{item['version']}",
                             reported=themes)
        rows.append({"slug": slug, "design_fingerprint": fingerprint,
                     "planned": planned["planned"],
                     "troubleshooting_for": planned["troubleshooting_for"],
                     "modules": [m for m in planned["modules"] if m["ok"]]})
    return {"products": rows, "stale_replanned": stale, "measurement": video.measurement()}


def creators_reading(db) -> dict:
    """#249 / #250: the roster as a portfolio, measured-weak relationships stopped, and the
    graduation check run for every tester on the physical-test roster."""
    from sqlalchemy import select

    from ..core.models import Collaboration, CreatorProfile, Order, PhysicalTest
    from ..growth import creators

    with db.session() as s:
        collabs = list(s.scalars(select(Collaboration)))
        by_ref: dict[str, list] = {}
        for c in collabs:
            if c.state in ("completed", "active", "delivered"):
                by_ref.setdefault(c.creator_ref, []).append(c)
        # A creator's contribution is what orders attributed to them left after fees: the
        # order ingest writes `creator:<ref>` as the acquisition source. It is measured only
        # once every collaboration has been measured; before that it is None, never zero.
        attributed: dict[str, float] = {}
        for o in s.scalars(select(Order).where(Order.acquisition_source.like("creator:%"))):
            if not o.refunded:
                ref = o.acquisition_source.split(":", 1)[1]
                attributed[ref] = attributed.get(ref, 0.0) + float(o.contribution_cad or 0.0)
        rels = []
        for ref, cs in sorted(by_ref.items()):
            measured = [c for c in cs if c.conversions is not None and c.measured_on]
            contribution = None
            if measured and len(measured) == len(cs):
                contribution = round(attributed.get(ref, 0.0), 2)
            support = (sum(int(c.support_cases) for c in cs)
                       if all(c.support_cases is not None for c in cs) else None)
            rels.append(creators.Relationship(
                creator_ref=ref, collaborations=len(cs),
                spend_cad=round(sum(float(c.fee_cad or 0.0) for c in cs), 2),
                contribution_cad=contribution,
                usable_assets=sum(int(c.usable_assets or 0) for c in cs),
                support_cases=support))
        portfolio = creators.portfolio(rels)
        stopped = []
        for card in portfolio["positions"]:
            if card["state"] == creators.STOP:
                for c in by_ref.get(card["creator_ref"], []):
                    if c.state == "active":
                        c.state = "stopped"
                        stopped.append(c.id)
        testers: dict[str, dict] = {}
        for t in s.scalars(select(PhysicalTest)):
            row = testers.setdefault(t.tester_ref, {"invited": 0, "delivered": 0})
            row["invited"] += 1
            if t.completed_at is not None:
                row["delivered"] += 1
        profiles = {p.ref: p for p in s.scalars(select(CreatorProfile))}
    graduations = []
    for ref, counts in sorted(testers.items()):
        profile = profiles.get(ref)
        perms = list(getattr(profile, "permissions", None) or [])
        consent = next((p.split(":", 1)[1] for p in perms
                        if isinstance(p, str) and p.startswith("advocate:")), "")
        graduations.append(creators.may_graduate(creators.Graduation(
            tester_ref=ref, invited=counts["invited"], delivered=counts["delivered"],
            testing_terms="", ambassador_terms="", consent_ref=consent)))
    with db.session() as s:
        roster = creators.roster(s)
    return {"roster": roster, "portfolio": portfolio,
            "stopped_collaborations": stopped, "graduations": graduations,
            "graduated": [g["tester_ref"] for g in graduations if g["may_graduate"]]}


def tools_reading(db, items: dict) -> dict:
    """#251 / #255: every free tool checked against the product it leads to, every flow
    checked for a causal design, and the per-person frequency cap applied to the send plan."""
    from sqlalchemy import select

    from ..core.models import Customer
    from ..growth import tools
    from ..growth.experiments import CAUSAL_DESIGNS

    lead = next(iter(sorted(items)), "")
    checks = []
    for key, spec in tools.TOOLS.items():
        tool = tools.Tool(key=key, leads_to=lead if spec["exists"] else "",
                          why_next=("the answer is computed from a certified pattern, so the "
                                    "pattern is the natural next thing to open")
                          if spec["exists"] else "")
        checks.append(tools.check_tool(tool))
    design = sorted(CAUSAL_DESIGNS)[0] if CAUSAL_DESIGNS else ""
    flows = [tools.check_flow(tools.Flow(key=k, segment_evidence="purchase", design=design))
             for k in tools.FLOWS]
    with db.session() as s:
        consenting = [c.customer_ref for c in s.scalars(select(Customer))
                      if c.casl_consent]
    planned = {ref: sum(1 for f in flows if f["may_claim_contribution"]) for ref in consenting}
    freq = tools.frequency(planned)
    allowed = {ref: min(n, tools.MAX_SENDS_PER_WEEK) for ref, n in planned.items()}
    return {"tools": checks, "hostable": [c["tool"] for c in checks if c["ok"]],
            "inventory": tools.inventory(), "flows": flows,
            "frequency": freq, "send_plan_after_cap": allowed,
            "recipients": len(consenting),
            "sends": 0, "why_no_sends": "no owned surface or sending capability exists"}


def gallery_reading(db, items: dict) -> dict:
    """#258: each product's gallery from stored image provenance, and whether proof lifted
    conversion, measured only across both arms."""
    from sqlalchemy import desc, select

    from ..commerce import buyer_trust
    from ..core.models import AuditLog, ListingOutcome

    rows = []
    for slug, item in sorted(items.items()):
        with db.session() as s:
            stored = [dict(r.detail or {}) for r in s.scalars(
                select(AuditLog).where(AuditLog.action == buyer_trust.IMAGE_PROVENANCE_ACTION,
                                       AuditLog.artifact.like(f"{slug}@%"))
                .order_by(desc(AuditLog.id)).limit(5))]
            outcomes = list(s.scalars(select(ListingOutcome).where(
                ListingOutcome.product_slug == slug)))
        images = []
        for d in stored[:1]:
            for e in d.get("images") or []:
                try:
                    images.append(buyer_trust.ImageRecord(
                        ref=e["ref"], kind=e["kind"], pattern_version=e["pattern_version"],
                        consent_basis=e.get("consent_basis", ""),
                        consent_ref=e.get("consent_ref", ""), yarn=e.get("yarn", ""),
                        colourway=e.get("colourway", "")))
                except (KeyError, TypeError):
                    continue
        gallery = buyer_trust.customer_gallery(images, selling_version=item["version"])

        def arm(flag: bool):
            chosen = [o for o in outcomes if bool((o.detail or {}).get("gallery")) is flag]
            visits = sum(int(o.visits or 0) for o in chosen)
            orders = sum(int(o.orders or 0) for o in chosen if o.orders is not None)
            return {"conversion": orders / visits} if visits else None

        lift = buyer_trust.proof_lift(design="before_after", with_gallery=arm(True),
                                      without_gallery=arm(False))
        rows.append({"slug": slug, "gallery": gallery, "proof_lift": lift})
    return {"products": rows,
            "usable_entries": sum(r["gallery"]["usable"] for r in rows)}


def interviews_reading(db, today: date) -> dict:
    """#260: whether a round may open, and the invitations the CASL gate would allow."""
    from sqlalchemy import select

    from ..core.models import Customer, Order
    from ..growth import interviews, owned

    with db.session() as s:
        customers = list(s.scalars(select(Customer)))
        first_order = {}
        for o in s.scalars(select(Order).order_by(Order.at)):
            first_order.setdefault(o.customer_id, o)
    gate = interviews.may_open(customers=len(customers))
    invitations, refused = [], []
    if gate["may_open"]:
        for c in customers[:interviews.MAX_SAMPLE]:
            order = first_order.get(c.id)
            if order is None:
                continue
            bought = _aware(order.at).date()
            invitation = interviews.Invitation(
                respondent_ref=c.customer_ref, invited_on=today, purchased_on=bought,
                selected_by="all_in_window", order_ref=order.external_ref)
            consent = owned.Consent(address_ref=c.customer_ref,
                                    basis=owned.EXPRESS if c.casl_consent
                                    else owned.IMPLIED_PURCHASE,
                                    obtained_on=bought, source=f"order:{order.external_ref}")
            verdict = interviews.invite_gate(invitation, consent, today)
            (invitations if verdict["may_invite"] else refused).append(
                {"respondent": c.customer_ref, "why": verdict["why"]})
    return {"gate": gate, "invitations_planned": invitations, "refused": refused,
            "sent": 0}


@handlers.register("growth.distribution")
def handle_growth_distribution(ctx: JobContext) -> dict:
    """Daily distribution planning from the database (#246-#251, #255, #258, #260, #295).

    GREEN: reads rows and writes one reading; the only state it changes is stopping a
    creator relationship measured as weak (#249). Nothing is published or sent.
    """
    today = _today(ctx)
    items = catalogue(ctx.db)
    previous = latest(ctx.db, DISTRIBUTION_KIND)
    themes = complaint_themes(ctx.db)
    winners = _winners(ctx.db)
    reading = {
        "as_of": today.isoformat(), "products": sorted(items), "winners": winners,
        "pins": plan_pins(ctx.db, items, today=today, previous=previous, winners=winners),
        "clusters": plan_clusters(items, themes),
        "video": plan_video(items, themes, previous),
        "creators": creators_reading(ctx.db),
        "tools": tools_reading(ctx.db, items),
        "gallery": gallery_reading(ctx.db, items),
        "interviews": interviews_reading(ctx.db, today),
    }
    reading_id = record(ctx.db, DISTRIBUTION_KIND, today.isoformat(), reading)
    summary = {
        "reading_id": reading_id, "products": len(items),
        "pins_ready": reading["pins"]["ready"], "pins_amplified": reading["pins"]["amplified"],
        "clusters_buildable": reading["clusters"]["buildable"],
        "video_modules": sum(p["planned"] for p in reading["video"]["products"]),
        "video_stale_replanned": [s["slug"] for s in reading["video"]["stale_replanned"]],
        "creators_stopped": reading["creators"]["stopped_collaborations"],
        "testers_graduated": reading["creators"]["graduated"],
        "tools_hostable": reading["tools"]["hostable"],
        "interviews_may_open": reading["interviews"]["gate"]["may_open"],
    }
    ctx.audit("growth.distribution", detail=summary)
    return summary


# ---- growth.journey ---------------------------------------------------------------------------

def friction_reading(db, items: dict) -> dict:
    """#261: every stored listing audited as an artefact; each defect is an incident until the
    listing answers it."""
    from sqlalchemy import select

    from ..commerce import friction
    from ..core.models import Listing
    from ..ops.incident_lifecycle import open_or_restate, reconcile

    audits, wanted = [], set()
    with db.session() as s:
        listings = [(r.product_slug, r.version, r.title or "", r.description or "")
                    for r in s.scalars(select(Listing)) if r.version != "collection"]
        for slug, version, title, description in listings:
            try:
                got = friction.listing_audit(title=title, description=description)
            except friction.FrictionRefused as e:
                got = {"clear": False, "defects": [{"confusion": "empty_description",
                                                   "kind": "comprehension", "why": str(e)}]}
            audits.append({"slug": slug, "version": version, "clear": got["clear"],
                           "defects": [d["confusion"] for d in got["defects"]]})
            for d in got["defects"]:
                sig = f"friction:{slug}:{d['confusion']}"
                wanted.add(sig)
                open_or_restate(s, signature=sig, severity="P2", product_slug=slug,
                                summary=f"{slug}@{version}: {d['why']}"[:500],
                                detail={"confusion": d["confusion"], "kind": d.get("kind"),
                                        "fix": d.get("fix", "")})
        closed = reconcile(s, "friction:", lambda row: row.signature in wanted,
                           resolution="the listing now answers this before a buyer asks")
    return {"listings": len(audits), "audits": audits,
            "with_defects": [a["slug"] for a in audits if not a["clear"]],
            "incidents_open": sorted(wanted), "resolved": closed["resolved"]}


def first_customer_reading(db) -> dict:
    """#259: the four before-the-first-customer verdicts; a not-ready one is an incident."""
    from ..commerce import first_hundred
    from ..ops.incident_lifecycle import open_or_restate, reconcile

    before = first_hundred.before_the_first_customer(db=db)
    wanted = {f"first_hundred:{r['priority']}" for r in before["priorities"] if not r["ready"]}
    with db.session() as s:
        for r in before["priorities"]:
            if r["ready"]:
                continue
            open_or_restate(s, signature=f"first_hundred:{r['priority']}", severity="P2",
                            summary=f"not ready before the first customer: {r['blocker']}"[:500],
                            detail={"priority": r["priority"], "blocker": r["blocker"],
                                    "ready_when": r["ready_when"]})
        closed = reconcile(s, "first_hundred:", lambda row: row.signature in wanted,
                           resolution="ready on the evidence now on file")
    return {"before": before, "incidents_open": sorted(wanted), "resolved": closed["resolved"]}


def promotion_reading(db, today: date) -> dict:
    """#19: catalogue dependence, and each promotion experiment read against its control."""
    from sqlalchemy import select

    from ..commerce import promotion
    from ..commerce.elasticity import Arm
    from ..core.models import Experiment
    from ..ops.incident_lifecycle import open_or_restate

    dependence = promotion.dependence(db, today=today)
    results = []
    with db.session() as s:
        for exp in s.scalars(select(Experiment).where(Experiment.kind == "promotion")):
            spec = dict(exp.result or {})
            try:
                promo = promotion.Promotion(
                    exp.product_slug or "", float(spec["full_price_cad"]),
                    float(spec["promo_price_cad"]), date.fromisoformat(spec["starts"]),
                    date.fromisoformat(spec["ends"]), exp.hypothesis or "promotion")
            except (KeyError, TypeError, ValueError):
                results.append({"experiment": exp.name, "measurable": False,
                                "why": "the promotion's prices and dates are not recorded"})
                continue
            window = promotion.window(promo, today)
            arms = {a.get("arm"): a for a in (exp.arms or []) if isinstance(a, dict)}

            def _arm(name):
                a = arms.get(name)
                if not a:
                    return None
                return Arm(key=exp.name, product_slug=exp.product_slug or "", arm=name,
                           visits=int(a.get("visits") or 0), orders=int(a.get("orders") or 0),
                           revenue_cad=float(a.get("revenue_cad") or 0.0))
            try:
                got = promotion.incrementality(promo, full_price_arm=_arm("organic"),
                                               discounted_arm=_arm("promoted"))
            except Exception as e:  # noqa: BLE001 - a malformed arm is a reading, not a crash
                got = {"measurable": False, "reason": str(e)[:200]}
            if window["state"] == "over" and exp.state == "running":
                exp.state = "ended"
            if got.get("measurable") and got.get("verdict") != "worth repeating":
                exp.state = "not_repeatable"
            results.append({"experiment": exp.name, "window": window, **{
                k: got.get(k) for k in ("measurable", "verdict", "reason")}})
        if dependence.get("conditioned"):
            open_or_restate(s, signature="promotion:catalogue_conditioned", severity="P2",
                            summary=dependence["why"], detail=dependence)
    return {"dependence": dependence, "promotions": results}


def benchmark_observations(db) -> tuple[list, list]:
    """#238: one observation per listing over its recorded outcome periods, in its cell."""
    from sqlalchemy import select

    from ..commerce import benchmarks
    from ..core.models import Listing, ListingOutcome, Order, SupportCase
    from ..seasonal.daily import DEPARTMENT_OF

    items = {}
    from ..radar.opportunity import POOL

    seeds = {m.slug: m for m in POOL}
    with db.session() as s:
        listings = {r.product_slug: r for r in s.scalars(select(Listing))
                    if r.version != "collection"}
        outcomes: dict[str, list] = {}
        for r in s.scalars(select(ListingOutcome)):
            outcomes.setdefault(r.product_slug, []).append(r)
        orders_all = list(s.scalars(select(Order)))
        cases = list(s.scalars(select(SupportCase)))
    shop_orders = len(orders_all)
    first = min((_aware(r.created_at) for r in listings.values() if r.created_at), default=None)
    days_live = (datetime.now(timezone.utc) - first).days if first else 0
    maturity = benchmarks.maturity_for(days_live=days_live, orders=shop_orders)
    observations, skipped = [], []
    for slug, rows in sorted(outcomes.items()):
        seed = seeds.get(slug)
        listing = listings.get(slug)
        pod = DEPARTMENT_OF.get(seed.category if seed else "", "unclassified")
        sources = {(r.detail or {}).get("traffic_source") or "etsy_search" for r in rows}
        source = sources.pop() if len(sources) == 1 else None
        if source not in benchmarks.TRAFFIC_SOURCES:
            skipped.append({"slug": slug, "why": f"traffic source {sorted(sources)} unknown or "
                                                 f"mixed; a cell needs one"})
            continue
        price = float(listing.price_cad) if listing else (seed.price_cad if seed else 0.0)
        age = ((datetime.now(timezone.utc) - _aware(listing.created_at)).days
               if listing and listing.created_at else 0)
        cell = benchmarks.Cell(category=pod, traffic_source=source,
                               price_band=benchmarks.band_for(price), maturity=maturity,
                               season=(seed.season if seed and seed.season else "none"),
                               listing_age=benchmarks.listing_age_for(age))
        slug_orders = [o for o in orders_all if o.product_slug == slug]
        measured_orders = [r.orders for r in rows if r.orders is not None]
        observations.append(benchmarks.Observation(
            listing_ref=slug, cell=cell,
            impressions=sum(int(r.impressions or 0) for r in rows),
            clicks=sum(int(r.visits or 0) for r in rows),
            favourites=(sum(int(r.favourites) for r in rows if r.favourites is not None)
                        if any(r.favourites is not None for r in rows) else None),
            orders=sum(measured_orders) if measured_orders else None,
            refunds_and_support=(sum(1 for o in slug_orders if o.refunded)
                                 + sum(1 for c in cases if c.product_slug == slug))
            if slug_orders else None,
            contribution_cad=(round(sum(float(o.contribution_cad or 0.0)
                                        for o in slug_orders if not o.refunded), 2)
                              if slug_orders else None)))
        items[slug] = cell
    return observations, skipped


def benchmarks_reading(db) -> dict:
    """#238 / #239: baselines by cell from the database, each listing diagnosed against its
    own cell, and micro-markets ranked on the contribution improving them would add."""
    from ..commerce import benchmarks
    from ..radar import arbitrage

    observations, skipped = benchmark_observations(db)
    cells = benchmarks.cells(observations)
    diagnoses = []
    for o in observations:
        base = cells["cells"].get(o.cell.key()) or {}
        conv = (o.orders / o.clicks) if (o.orders is not None and o.clicks) else None
        bench = ((base.get("metrics") or {}).get("conversion") or {}).get("value")
        diagnoses.append({"slug": o.listing_ref, "cell": o.cell.key(),
                          "conversion": conv, "cell_baseline": bench,
                          "verdict": ("UNMEASURED" if conv is None or bench is None else
                                      "below_cohort" if conv < bench else "at_or_above")})
    # #239: demand from the observed benchmark catalogue, our share from our impressions.
    try:
        scored = arbitrage.score_observed(db)
    except Exception as e:  # noqa: BLE001 - no benchmark rows is a reading, not a failure
        scored = {"scored": [], "error": str(e)[:200]}
    impressions: dict[str, int] = {}
    clicks: dict[str, int] = {}
    orders: dict[str, int] = {}
    for o in observations:
        impressions[o.cell.category] = impressions.get(o.cell.category, 0) + (o.impressions or 0)
        clicks[o.cell.category] = clicks.get(o.cell.category, 0) + (o.clicks or 0)
        orders[o.cell.category] = orders.get(o.cell.category, 0) + (o.orders or 0)
    markets = []
    for row in scored.get("scored") or []:
        pod = row.get("pod") or row.get("market")
        demand = ((row.get("dimensions") or {}).get("demand")
                  if isinstance(row.get("dimensions"), dict) else row.get("demand"))
        if isinstance(demand, dict):
            demand = demand.get("value")
        if not isinstance(demand, (int, float)) or not 0 <= demand <= 1:
            continue
        imp = impressions.get(pod)
        markets.append({"market": pod, "relative_demand": float(demand),
                        "impressions": imp if imp else None,
                        "ctr": (clicks[pod] / imp) if imp and clicks.get(pod) else None,
                        "conversion": (orders[pod] / clicks[pod])
                        if clicks.get(pod) and orders.get(pod) is not None else None,
                        "contribution_per_order_cad": None})
    return {"cells": {k: cells[k] for k in ("occupied", "readable", "note")},
            "baselines": cells["cells"], "diagnoses": diagnoses, "skipped": skipped,
            "opportunities": benchmarks.opportunities(markets)}


def proof_sweep(db) -> dict:
    """#17: every passed physical test and every sale ledger row attached as proof, once, via
    `trust.record_proof` -- which refuses anything without a row behind it."""
    from sqlalchemy import select

    from ..commerce import trust
    from ..core.models import AuditLog, LedgerEntry, PhysicalTest

    with db.session() as s:
        done = {r.artifact for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "trust.proof"))}
        candidates = [(trust.TESTER_PROOF, t.id, f"{t.product_slug}@{t.version} passed")
                      for t in s.scalars(select(PhysicalTest).where(
                          PhysicalTest.passed == True))]  # noqa: E712
        candidates += [(trust.CUSTOMER_PROOF, x.id, x.description or "sale")
                       for x in s.scalars(select(LedgerEntry).where(
                           LedgerEntry.category == "sale"))]
    recorded = []
    for origin, row_id, summary in candidates:
        if f"{origin}:{row_id}" in done:
            continue
        recorded.append(trust.record_proof(db, origin=origin, row_id=row_id,
                                           summary=summary[:200]))
    return {"recorded": len(recorded), "proof": trust.proof_count(db)}


@handlers.register("growth.journey")
def handle_growth_journey(ctx: JobContext) -> dict:
    """Daily buyer-journey audit (#17, #19, #238, #239, #259, #261).

    GREEN: reads rows; opens and resolves incidents for friction and not-ready priorities;
    marks promotions that did not pay as not repeatable; attaches proof to its rows.
    """
    today = _today(ctx)
    items = catalogue(ctx.db)
    reading = {
        "as_of": today.isoformat(),
        "friction": friction_reading(ctx.db, items),
        "first_customer": first_customer_reading(ctx.db),
        "promotions": promotion_reading(ctx.db, today),
        "benchmarks": benchmarks_reading(ctx.db),
        "proof": proof_sweep(ctx.db),
    }
    reading_id = record(ctx.db, JOURNEY_KIND, today.isoformat(), reading)
    summary = {
        "reading_id": reading_id,
        "listings_audited": reading["friction"]["listings"],
        "friction_incidents": len(reading["friction"]["incidents_open"]),
        "first_customer_outstanding": reading["first_customer"]["before"]["outstanding"],
        "promotions": len(reading["promotions"]["promotions"]),
        "benchmark_cells": reading["benchmarks"]["cells"]["occupied"],
        "opportunities_ranked": len(reading["benchmarks"]["opportunities"]["ranked"]),
        "proof_recorded": reading["proof"]["recorded"],
    }
    ctx.audit("growth.journey", detail=summary)
    return summary


# ---- growth.steer -----------------------------------------------------------------------------

def _job_slug(inputs: dict) -> str:
    return str((inputs or {}).get("slug") or (inputs or {}).get("product_slug") or "")


def _job_season(inputs: dict) -> str:
    inputs = inputs or {}
    return str(inputs.get("season") or inputs.get("event") or inputs.get("occasion") or "")


def steer(db, *, today: date | None = None) -> dict:
    """Apply the week's reallocation, the roll-forward, fast-lane admission and the board to
    the queue and the experiment queue. Returns what moved and why."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus, OperatingReading, RegisteredExperiment
    from ..growth import weekly
    from ..radar.opportunity import POOL
    from ..scale.war_room import board as war_board
    from ..seasonal import daily

    today = today or date.today()
    week = weekly.latest(db) or {}
    realloc = week.get("reallocation") or {}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == daily.KIND)
                       .order_by(OperatingReading.at.desc()).limit(1))
        seasonal = dict(row.payload or {}) if row is not None else {}
    rolled = (seasonal.get("rollforward") or {}).get("capacities") or {}
    engineering = (rolled.get("engineering") or {}).get("moves") or []
    marketing = (rolled.get("marketing") or {}).get("moves") or []
    admitted = set((seasonal.get("fast_lane") or {}).get("admitted") or [])
    board = war_board(db)["board"]
    winners = {w["product"] for w in (board["winner_alerts"].get("value") or [])} \
        if board["winner_alerts"]["status"] == "measured" else set()

    # A job is steered once: the ids moved in the last fortnight's readings are not moved
    # again, so a job that waits does not drift further every hour it waits.
    since = datetime.now(timezone.utc) - timedelta(days=14)
    with db.session() as s:
        already = {m["job_id"] for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == STEER_KIND))
            if _aware(r.at) and _aware(r.at) >= since
            for m in (r.payload or {}).get("jobs_moved") or []}
    toward = set(realloc.get("owners") or []) if realloc.get("move") else set()
    seasons_up = {m["to"] for m in engineering + marketing}
    seasons_down = {m["from"] for m in engineering + marketing} - seasons_up
    season_of = {m.slug: m.season for m in POOL if m.season}
    moved = []
    with db.session() as s:
        pending = list(s.scalars(select(Job).where(Job.status == JobStatus.PENDING)
                                 .order_by(Job.id).limit(2000)))
        for job in pending:
            if len(moved) >= MAX_STEERED_PER_RUN:
                break
            if job.id in already:
                continue
            slug = _job_slug(job.inputs)
            season = _job_season(job.inputs) or season_of.get(slug, "")
            why, delta = None, 0
            if slug and slug in admitted:
                why, delta = "fast lane admitted (#291)", -2 * STEER_CREDIT
            elif slug and slug in winners:
                why, delta = "war-room winner (#276)", -STEER_CREDIT
            elif job.agent in toward:
                why, delta = f"reallocation toward {realloc.get('toward')} (#264)", -STEER_CREDIT
            elif season and season in seasons_up:
                why, delta = f"capacity rolled forward to {season} (#267)", -STEER_CREDIT
            elif season and season in seasons_down:
                why, delta = f"{season} no longer holds capacity (#267)", STEER_CREDIT
            if not delta:
                continue
            job.priority = int(job.priority) + delta
            moved.append({"job_id": job.id, "job_type": job.job_type, "agent": job.agent,
                          "delta": delta, "why": why})
        # The experiment queue: experiments on the constraint's levers first (#264).
        ranked = []
        levers = set(realloc.get("experiments") or []) if realloc.get("move") else set()
        for exp in s.scalars(select(RegisteredExperiment).where(
                RegisteredExperiment.state.in_(("registered", "running")))):
            lever = exp.key.split(":")[-1]
            detail = dict(exp.detail or {})
            rank = 0 if lever in levers else (1 if exp.product_slug in winners else 2)
            if detail.get("steer_rank") != rank:
                detail["steer_rank"] = rank
                detail["steered_on"] = today.isoformat()
                exp.detail = detail
            if rank < 2:
                ranked.append(exp.key)
    return {
        "as_of": today.isoformat(),
        "reallocation": {"move": bool(realloc.get("move")), "toward": realloc.get("toward"),
                         "owners": sorted(toward), "why": realloc.get("why")},
        "rollforward": {"up": sorted(seasons_up), "down": sorted(seasons_down)},
        "fast_lane_admitted": sorted(admitted),
        "board": {"winners": sorted(winners),
                  "primary_constraint": board["primary_constraint"].get("value"),
                  "top_actions_status": board["top_actions"]["status"]},
        "jobs_moved": moved, "experiments_prioritised": ranked,
        "note": ("nothing moved: no constraint is identifiable, no occasion has released "
                 "capacity and nothing was admitted or is winning"
                 if not moved and not ranked else ""),
    }


@handlers.register("growth.steer")
def handle_growth_steer(ctx: JobContext) -> dict:
    """Hourly: the reallocation, roll-forward, fast lane and board applied to the queue.

    GREEN: re-prioritises pending work within bounded credits and orders the experiment queue;
    it enqueues nothing that spends and raises no ceiling.
    """
    today = _today(ctx)
    out = steer(ctx.db, today=today)
    record(ctx.db, STEER_KIND, today.isoformat(), out)
    summary = {"moved": len(out["jobs_moved"]),
               "experiments_prioritised": len(out["experiments_prioritised"]),
               "toward": out["reallocation"]["toward"],
               "rolled_up": out["rollforward"]["up"],
               "fast_lane": out["fast_lane_admitted"],
               "winners": out["board"]["winners"]}
    ctx.audit("growth.steered", detail=summary)
    return summary
