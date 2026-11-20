"""S4: the P0 command board -- one read-only page of what the company is doing right now.

Main's S4 (#28 6953884261): running SHA and health; the mandatory research shops (nine) with last attempted
and successful scan, source timestamp, listings observed, failures, next scan and downstream
concept evidence; opportunities scored; products in development; certified releases; PDFs and
galleries; Etsy draft status and remote listing ids; published and sales; costs and API
credits; open blockers and owners; agents active, idle and failed. Read-only, operator-gated
(it is served under the Command Center's default-deny `/api/cc` gate like every other tab).

**Composition, not new readers.** Each section calls the reader the rest of the system already
trusts (`ops.production_evidence`, `company.agents`, `finance.credits`, the stored health
sweep, the database rows themselves). A section that cannot be read is UNKNOWN with the reason;
it never borrows a value from another section and never reads as a pass.

**The status vocabulary is kept distinct** (Main's list, in order):

    CODE BUILT < INDEPENDENTLY REVIEWED < INTEGRATED < DEPLOYED < RUNNING
              < PRODUCTION-VERIFIED < REAL COMMERCE VERIFIED

Every section reports the highest level the RUNNING SYSTEM can prove from its own evidence,
and the rule that proved it. The running system can prove only these:

* DEPLOYED -- this process reports the commit it was built from (`core.build.commit`), so the
  section's code is the deployed code. Without a commit it is never DEPLOYED.
* RUNNING -- the section's own work happened recently (a fresh sweep, scan, job or row).
* PRODUCTION-VERIFIED -- the section's own production check passes (named per section).
* REAL COMMERCE VERIFIED -- real money moved: a real, unrefunded order with revenue, or a
  listing live on Etsy that a sale was recorded against.

INDEPENDENTLY REVIEWED and INTEGRATED are facts about the review and branch process (GitHub,
`COORDINATION.json`), not about this database, so the board never claims them; it says so in
`not_provable_here`. CODE BUILT is the floor: the section's reader exists and ran.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

LEVELS = ("CODE BUILT", "INDEPENDENTLY REVIEWED", "INTEGRATED", "DEPLOYED", "RUNNING",
          "PRODUCTION-VERIFIED", "REAL COMMERCE VERIFIED")
CODE_BUILT, REVIEWED, INTEGRATED, DEPLOYED, RUNNING, PROD_VERIFIED, COMMERCE = LEVELS
NOT_PROVABLE_HERE = (REVIEWED, INTEGRATED)
# D-OWNER-NINTH-SHOP: computed from the owner's list (nine since 2026-11-19), never retyped.
from ...intel.scan_evidence import OWNER_SHOPS as _OWNER_SHOPS  # noqa: E402

MANDATORY_SHOPS = len(_OWNER_SHOPS)
HEALTH_FRESH = timedelta(minutes=45)          # the sweep runs every 15 minutes
FRESH_WORK = timedelta(hours=24)
ROW_LIMIT = 25
# Only an order ingested from Etsy's receipts is a real sale; a hand-entered or seeded row
# never proves commerce (core.models.Order.source).
REAL_ORDER_SOURCE = "etsy_receipts"
UNKNOWN = "UNKNOWN"


def _now(now=None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _iso(v) -> str | None:
    v = _aware(v)
    return v.isoformat() if isinstance(v, datetime) else None


def _level(deployed: bool, *, running: bool = False, verified: bool = False,
           commerce: bool = False, why: dict | None = None) -> dict:
    """The highest level proven, and the rule for each level reached. Never skips a rung:
    a section is not PRODUCTION-VERIFIED unless it is also RUNNING, and so on."""
    reached, rules = CODE_BUILT, {CODE_BUILT: "this section's reader exists and ran"}
    why = why or {}
    for name, ok in ((DEPLOYED, deployed), (RUNNING, running), (PROD_VERIFIED, verified),
                     (COMMERCE, commerce)):
        if not ok:
            break
        reached = name
        rules[name] = why.get(name, "")
    return {"level": reached, "proved_by": rules, "not_provable_here": list(NOT_PROVABLE_HERE)}


def _section(name: str, fn, deployed: bool) -> dict:
    try:
        return fn(deployed)
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never a pass
        return {"state": UNKNOWN, "why": f"could not be read: {type(exc).__name__}: "
                                         f"{str(exc)[:160]}",
                "level": None, "proved_by": {}, "not_provable_here": list(NOT_PROVABLE_HERE)}


# ---- sections -------------------------------------------------------------------------------

def running(db, now):
    from sqlalchemy import desc, select

    from ...core import build
    from ...core.models import Job, JobStatus

    ident = build.identity()
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "ops.health",
                                         Job.status == JobStatus.DONE)
                       .order_by(desc(Job.id)).limit(1))
        sweep = dict(job.outputs or {}) if job is not None else {}
        swept_at = _aware(job.finished_at if job is not None else None)
    fresh = swept_at is not None and now - swept_at <= HEALTH_FRESH
    state = str(sweep.get("state") or UNKNOWN)

    def build_section(deployed):
        return {"state": state if fresh else UNKNOWN,
                "commit": ident.get("commit"), "branch": ident.get("branch"),
                "health": {"state": state, "bad": list(sweep.get("bad") or [])[:10],
                           "why": sweep.get("why"), "activity": sweep.get("activity"),
                           "swept_at": _iso(swept_at), "fresh": fresh},
                **_level(deployed, running=fresh, verified=fresh and state == "healthy",
                         why={DEPLOYED: "the process reports its commit",
                              RUNNING: "a health sweep completed in the last 45 minutes",
                              PROD_VERIFIED: "that sweep reads healthy (useful work "
                                             "progressing, not only HTTP 200)"})}
    return build_section


def shops(db, now):
    from ...ops import production_evidence as PE

    ev = PE.competitor_scans(db, now=now)

    def build_section(deployed):
        rows = list(ev.get("shops") or [])
        fresh = [r for r in rows if r.get("last_successful") and not r.get("stale")]
        # Verdict 6990820438 LOW: a shop whose failure count is not reported is UNKNOWN,
        # never "no failures".
        unknown = [r for r in rows if not isinstance(r.get("consecutive_failures"), int)]
        failing = [r for r in rows if isinstance(r.get("consecutive_failures"), int)
                   and r["consecutive_failures"] > 0]
        clean = len(fresh) == MANDATORY_SHOPS and not failing and not unknown
        return {"state": ("OK" if clean else "DEGRADED" if rows else UNKNOWN),
                "required": MANDATORY_SHOPS, "configured": len(rows), "fresh": len(fresh),
                "failing": len(failing), "failures_unknown": len(unknown),
                "credential": ev.get("credential"),
                "shops": [{k: r.get(k) for k in (
                    "owner_order", "alias", "role", "state", "last_attempted",
                    "last_successful", "etsy_source_timestamp", "listings_seen_last_scan",
                    "listings_live", "consecutive_failures", "failure_class", "next_due",
                    "stale", "downstream")} for r in rows],
                **_level(deployed, running=bool(fresh),
                         verified=len(rows) == MANDATORY_SHOPS and clean,
                         why={RUNNING: "at least one shop scanned inside its cadence",
                              PROD_VERIFIED: f"all {MANDATORY_SHOPS} mandatory shops scanned "
                                             "inside their "
                                             "cadence, each reporting zero consecutive "
                                             "failures"})}
    return build_section


def opportunities(db, now):
    from sqlalchemy import desc, func, inspect, select

    from ...radar.intake import RadarConcept

    with db.session() as s:
        if not inspect(s.get_bind()).has_table(RadarConcept.__tablename__):
            # Never created here (the board writes nothing): no concept was ever proposed.
            return lambda deployed: {"state": "EMPTY", "by_state": {}, "scored": [],
                                     "newest_at": None,
                                     "why": "no concept has ever been proposed",
                                     **_level(deployed)}
        by_state = dict(s.execute(select(RadarConcept.state, func.count(RadarConcept.id))
                                  .group_by(RadarConcept.state)).all())
        top = list(s.execute(select(RadarConcept.slug, RadarConcept.state,
                                    RadarConcept.quality, RadarConcept.source,
                                    RadarConcept.at)
                             .order_by(desc(RadarConcept.quality)).limit(ROW_LIMIT)))
        newest = _aware(s.scalar(select(func.max(RadarConcept.at))))

    def build_section(deployed):
        recent = newest is not None and now - newest <= FRESH_WORK
        return {"state": "OK" if top else "EMPTY", "by_state": by_state,
                "scored": [{"slug": r[0], "state": r[1], "quality": round(float(r[2] or 0), 3),
                            "source": r[3], "at": _iso(r[4])} for r in top],
                "newest_at": _iso(newest),
                **_level(deployed, running=recent,
                         why={RUNNING: "a concept was scored in the last 24 hours"})}
    return build_section


def development(db, now):
    from ...ops import production_evidence as PE

    ev = PE.certification(db, now=now)

    def build_section(deployed):
        counts = ev.get("count_by_stage") or {}
        return {"state": "OK" if ev.get("readable") else UNKNOWN,
                "stage_order": ev.get("stage_order"), "count_by_stage": counts,
                "slugs_by_stage": ev.get("slugs_by_stage"),
                "halted": ev.get("halted_certifications"),
                **_level(deployed, running=bool(ev.get("readable")) and any(counts.values()),
                         why={RUNNING: "products are recorded in lifecycle stages"})}
    return build_section


def releases(db, now):
    from sqlalchemy import desc, select

    from ...core.models import Listing, PatternVersion, Product

    with db.session() as s:
        rows = list(s.execute(
            select(Product.slug, PatternVersion.version, PatternVersion.release_hash,
                   PatternVersion.created_at)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified.is_(True))
            .order_by(desc(PatternVersion.id)).limit(ROW_LIMIT)))
        listings = {(r.product_slug, r.version): r for r in s.scalars(select(Listing))}
        for r in listings.values():
            s.expunge(r)

    def build_section(deployed):
        items = []
        for slug, version, rel, at in rows:
            li = listings.get((slug, version))
            items.append({"slug": slug, "version": version,
                          "release": (rel or "")[:12] or None, "certified_at": _iso(at),
                          "listing_state": li.state if li is not None else None,
                          "etsy_listing_id": (li.etsy_listing_id or None) if li else None,
                          "listing_release_matches": (li is not None and bool(rel)
                                                      and li.release_hash == rel)})
        return {"state": "OK" if items else "EMPTY", "certified": items,
                **_level(deployed, running=bool(items),
                         why={RUNNING: "certified releases are recorded"})}
    return build_section


def assets(db, now):
    from ...app.command_center import company

    rep = company.store_readiness(db, now=now)

    def build_section(deployed):
        return {"state": rep.get("status", UNKNOWN), "counts": rep.get("counts"),
                "not_proven": rep.get("items", [])[:ROW_LIMIT], "as_of": rep.get("as_of"),
                "note": "PDF and gallery readiness per item, from the store-readiness build; "
                        "each item not yet PROVEN names its gate",
                **_level(deployed, running=bool(rep.get("counts")),
                         verified=rep.get("status") == "OK" and not rep.get("items"),
                         why={RUNNING: "the store-readiness build ran",
                              PROD_VERIFIED: "every readiness item is PROVEN"})}
    return build_section


def etsy(db, now):
    from sqlalchemy import func, select

    from ...core.models import Listing

    on_etsy = (Listing.etsy_listing_id.is_not(None), Listing.etsy_listing_id != "")
    with db.session() as s:
        by_state = dict(s.execute(select(Listing.state, func.count(Listing.id))
                                  .group_by(Listing.state)).all())
        # Verdict 6990820438 LOW: counted in SQL over every remote listing, not from the
        # ROW_LIMIT-capped list below.
        remote_by_state = dict(s.execute(select(Listing.state, func.count(Listing.id))
                                         .where(*on_etsy).group_by(Listing.state)).all())
        remote = list(s.execute(select(Listing.product_slug, Listing.version, Listing.state,
                                       Listing.etsy_listing_id)
                                .where(Listing.etsy_listing_id.is_not(None),
                                       Listing.etsy_listing_id != "")
                                .order_by(Listing.id.desc()).limit(ROW_LIMIT)))

    def build_section(deployed):
        live = by_state.get("active", 0)
        return {"state": "OK" if remote else "NO_REMOTE_LISTING", "by_state": by_state,
                "remote": [{"slug": r[0], "version": r[1], "state": r[2],
                            "etsy_listing_id": r[3]} for r in remote],
                "remote_shown": len(remote),
                "remote_total": sum(remote_by_state.values()),
                "drafts_on_etsy": int(remote_by_state.get("draft", 0)),
                "not_live_on_etsy": sum(n for st, n in remote_by_state.items()
                                        if st != "active"),
                "live_on_etsy": live,
                **_level(deployed, running=bool(remote),
                         why={RUNNING: "at least one listing has an Etsy listing id"})}
    return build_section


def sales(db, now):
    from sqlalchemy import select

    from ...commerce import orders_ingest as OI
    from ...core.models import Order

    # Verdict 6990820438 M2: a source that is not connected, or never completed a read, has
    # observed nothing. Its figures are UNKNOWN, never 0 orders and $0.
    source = OI.source_state(db)
    with db.session() as s:
        # M1: the one countable predicate the books use (held, unreconciled, unpaid,
        # refunded and unknown-revenue orders never count), over Etsy's receipts only.
        rows = OI.countable_orders(s, select(Order).where(Order.source == REAL_ORDER_SOURCE))
        n = len(rows)
        revenue = sum(float(o.revenue_cad or 0.0) for o in rows)
        # Verdict 6996033652 LOW: real money moved only if a countable order carried revenue;
        # a $0 countable order is a sale record, not commerce.
        paid = sum(1 for o in rows if float(o.revenue_cad or 0.0) > 0)
        last = max((_aware(o.at) for o in rows if o.at is not None), default=None)

    def build_section(deployed):
        measured = bool(source.get("measured"))
        out = {"source": {k: source.get(k) for k in ("open", "measured", "last_read_at",
                                                      "missing", "why")},
               "counted": f"countable orders (the books' rule: not held, not unreconciled, "
                          f"paid, not refunded) read from {REAL_ORDER_SOURCE}",
               "last_order_at": _iso(last)}
        if measured:
            out.update(state="OK" if n else "NO_SALES", real_orders=n,
                       revenue_cad=round(revenue, 2))
        else:
            # Verdict 6996033652 LOW: one reading. With nothing recorded the figures are
            # UNKNOWN. Recorded countable orders still happened, so the section is PARTIAL
            # (the totals are a floor), never UNKNOWN beside a commerce level it proved.
            out.update(state="PARTIAL" if n else UNKNOWN, real_orders=None, revenue_cad=None,
                       recorded_countable_orders=n,
                       recorded_countable_revenue_cad=round(revenue, 2),
                       why=source.get("why") or "the order source is not measured")
        commerce_why = ("a countable Etsy order (paid, not refunded, not held or "
                        "unreconciled) with revenue above $0 exists")
        if not measured:
            # Verdict 6998037105 LOW: while the source is unmeasured the recorded orders are a
            # reading from the past. The level says so, and when that reading was taken.
            read_at = source.get("last_read_at")
            as_of = f"as of the last read ({read_at})" if read_at else \
                "as of the orders recorded before the source stopped being read"
            out["as_of"] = as_of
            commerce_why = f"{commerce_why}, {as_of}; the order source is not measured now"
        out.update(_level(deployed, running=n > 0, verified=n > 0, commerce=paid > 0,
                          why={RUNNING: "countable orders are recorded",
                               PROD_VERIFIED: "a countable order was ingested from Etsy's "
                                              "receipts",
                               COMMERCE: commerce_why}))
        return out
    return build_section


def costs(db, now):
    from ...finance import credits

    from sqlalchemy import func, select

    from ...core.models import CostEntry

    wallet = credits.wallet(db, now=now)
    with db.session() as s:
        last_cost = _aware(s.scalar(select(func.max(CostEntry.at))))
    active = last_cost is not None and now - last_cost <= FRESH_WORK

    def build_section(deployed):
        return {"state": "OK" if wallet else UNKNOWN, "credits": wallet,
                "note": "the month's cash spend is on the Money tab; API credits are the "
                        "provider-credit wallet (a balance is UNKNOWN where the provider "
                        "publishes no API for it)",
                "last_cost_at": _iso(last_cost),
                **_level(deployed, running=active,
                         why={RUNNING: "a cost was recorded in the last 24 hours"})}
    return build_section


def blockers(db, now):
    from sqlalchemy import func, select

    from ...core.models import Incident, OwnerAction

    with db.session() as s:
        actions = list(s.execute(select(OwnerAction.id, OwnerAction.action,
                                        OwnerAction.requirement_key, OwnerAction.max_cost_cad,
                                        OwnerAction.minutes, OwnerAction.blocks,
                                        OwnerAction.at)
                                 .where(OwnerAction.done.is_(False))
                                 .order_by(OwnerAction.id.desc()).limit(ROW_LIMIT)))
        incidents = list(s.execute(select(Incident.id, Incident.severity,
                                          Incident.signature, Incident.product_slug,
                                          Incident.halts_publication, Incident.at)
                                   .where(Incident.resolved.is_(False))
                                   .order_by(Incident.id.desc()).limit(ROW_LIMIT)))
        # Verdict 6990820438 LOW: RUNNING is evidence of activity (a blocker raised or moved
        # in the last 24 hours, open or closed), not merely that the tables are readable.
        stamps = [_aware(s.scalar(select(func.max(OwnerAction.at)))),
                  _aware(s.scalar(select(func.max(OwnerAction.state_at)))),
                  _aware(s.scalar(select(func.max(Incident.at))))]
    last = max((t for t in stamps if t is not None), default=None)
    active = last is not None and now - last <= FRESH_WORK

    def build_section(deployed):
        return {"state": "CLEAR" if not actions and not incidents else "OPEN",
                "last_activity_at": _iso(last),
                "owner_actions": [{"id": a[0], "owner": "owner", "action": a[1],
                                   "requirement": a[2], "max_cost_cad": a[3],
                                   "minutes": a[4], "blocks": a[5], "since": _iso(a[6])}
                                  for a in actions],
                "incidents": [{"id": i[0], "owner": "system", "severity": i[1],
                               "family": str(i[2] or "").split(":")[0], "product": i[3],
                               "halts_publication": i[4], "since": _iso(i[5])}
                              for i in incidents],
                **_level(deployed, running=active,
                         why={RUNNING: "an owner action or incident was raised or changed "
                                       "in the last 24 hours"})}
    return build_section


def owner_queue(db, now):
    """ENG-APPROVALS: owner exceptions open; cards closed automatically and routine operations
    auto-approved under D-OWNER-STANDING-INTERNAL in the last 24 hours."""
    from ...ops import owner_queue_consolidate as oqc

    got = oqc.counts(db, now=now)

    def build_section(deployed):
        active = (got["closed_automatically_24h"] + got["routine_auto_approved_24h"]) > 0
        return {"state": "CLEAR" if not got["owner_exceptions_open"] else "OPEN", **got,
                **_level(deployed, running=active,
                         why={RUNNING: "the standing authority moved an owner card in the "
                                       "last 24 hours"})}
    return build_section


def agents(db, now):
    from ...app.command_center import company

    rep = company.agents(db)

    def build_section(deployed):
        items = rep.get("items") or []
        counts = rep.get("counts") or {}
        return {"state": rep.get("status", UNKNOWN), "counts": counts,
                "agents": [{k: a.get(k) for k in ("name", "state", "why", "enabled")}
                           for a in items][:50],
                **_level(deployed, running=any(a.get("state") == "active" for a in items),
                         why={RUNNING: "at least one agent is active"})}
    return build_section


def motif_recovery(db, now):
    """ENG-MOTIF-BACKLOG (owner P0): paid renders blocked by a refused motif check, and what
    the recovery made of them. Counts from the persisted `motif_recovery` rows only; a backlog
    never swept is UNKNOWN, never 0 (`publish.motif_backlog.report`)."""
    from ...publish import motif_backlog

    rep = motif_backlog.report(db)

    def build_section(deployed):
        counts = rep.get("counts") or {}
        swept = rep.get("swept") is True
        open_ = (counts.get("renders_still_queued_budget"),
                 counts.get("renders_queued_retry"),
                 counts.get("renders_awaiting_first_recheck"))
        settled = swept and all(isinstance(n, int) and n == 0 for n in open_)
        state = (UNKNOWN if not swept else "RECOVERED" if settled else "RECOVERING")
        return {"state": state, "counts": counts, "last_sweep_at": rep.get("last_sweep_at"),
                "recheck_spend_cad": rep.get("recheck_spend_cad"),
                "why": rep.get("why") or rep.get("gates_unchanged"),
                "note": "renders re-checked, never re-rendered; only a genuine motif failure "
                        "is queued for regeneration",
                **_level(deployed, running=swept, verified=settled,
                         why={RUNNING: "the recovery sweep has run",
                              PROD_VERIFIED: "no refused render is still waiting"})}
    return build_section


def research_sources(db, now):
    """ENG-RESEARCH: every registered research source with its agent, method, status, last
    attempt and success, freshness, failures and backoff, and what it led to (findings ->
    concepts -> engineering); plus the loop's stages and its latest recorded conclusion."""
    from ...intel import research_flow

    ev = research_flow.evidence(db, now=now)

    def build_section(deployed):
        srcs = ev["sources"]
        shops = [r for r in srcs if r["kind"] == "shop"]
        fresh = [r for r in shops if r.get("last_success") and not r.get("stale")]
        down = [r for r in srcs if r["status"] != research_flow.SCHEDULED]
        concl = ev.get("conclusion") or {}
        return {"state": ("OK" if not down and len(fresh) == len(shops) and concl
                          else "DEGRADED"),
                "counts": ev["counts"], "credential": ev["credential"],
                "sources": srcs, "loop": ev["loop"], "conclusion": ev["conclusion"],
                "limitations": [{"id": r["id"], "status": r["status"], "why": r["why"]}
                                for r in down],
                **_level(deployed, running=bool(fresh) and bool(concl),
                         verified=bool(concl) and ev["loop"]["in_engineering"] > 0,
                         why={RUNNING: "a watchlist shop scanned inside its cadence and the "
                                       "research loop recorded a conclusion",
                              PROD_VERIFIED: "a research opportunity reached engineering "
                                             "(a cir.draft job exists for it)"})}
    return build_section


SECTIONS = (("running", running), ("motif_recovery", motif_recovery), ("shops", shops), ("opportunities", opportunities),
            ("development", development), ("releases", releases), ("assets", assets),
            ("etsy", etsy), ("sales", sales), ("costs", costs), ("blockers", blockers),
            ("owner_queue", owner_queue), ("agents", agents),
            ("research_sources", research_sources))


def view(db, *, now: datetime | None = None) -> dict:
    """The board. Read-only: nothing here writes a row, queues a job or calls a provider."""
    from ...core import build

    now = _now(now)
    deployed = build.commit() not in ("", build.UNKNOWN)
    out = {}
    for name, reader in SECTIONS:
        try:
            make = reader(db, now)
        except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN
            out[name] = {"state": UNKNOWN, "why": f"could not be read: {type(exc).__name__}: "
                                                  f"{str(exc)[:160]}",
                         "level": None, "proved_by": {},
                         "not_provable_here": list(NOT_PROVABLE_HERE)}
            continue
        out[name] = _section(name, make, deployed)
    return {"tab": "P0_BOARD", "generated_at": now.isoformat(), "read_only": True,
            "vocabulary": list(LEVELS), "not_provable_here": list(NOT_PROVABLE_HERE),
            "deployed_commit": build.commit(), "sections": out}
