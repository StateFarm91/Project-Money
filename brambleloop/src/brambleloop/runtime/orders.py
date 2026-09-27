"""The order source and everything that reads orders, as jobs (certification defect C-64).

Four handlers, each on a cadence in `worker.CADENCES`:

* `commerce.orders_ingest` (six-hourly): Etsy receipts into customers, orders, the version
  map and the ledger -- behind the real `transactions_r` gate, making no network call when
  it is closed. When it creates an order it queues the order readings at once.
* `commerce.order_readings` (daily, and after any ingest that created an order): cohorts,
  offers, winners, reinvestment, ladder, bundles, promotions, repeat windows, referral and
  growth loops, read from the rows and recorded; their directives are read by
  `portfolio.review`, `pricing.position`, `collection.assemble` and ideation.
* `scale.trajectory` (nightly, #26): the scenario analysis over the terms the database can
  answer; a changed primary constraint queues the capacity review.
* `creative.north_star` (daily, #104, #132): the north-star metrics by cohort from the rows;
  a cohort-on-cohort regression opens a P2 business defect and resolves it when it stops.

GREEN: reads rows (and, only behind its gate, Etsy's receipts), writes rows, spends nothing,
messages nobody.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .worker import JobContext, handlers

INGEST = "commerce.orders_ingest"
READINGS = "commerce.order_readings"
TRAJECTORY = "scale.trajectory"
NORTH_STAR = "creative.north_star"
TRAJECTORY_KIND = "scale.trajectory"
NORTH_STAR_KIND = "creative.north_star"
NORTH_STAR_SIGNATURE = "creative.north_star_regression"


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


def _today(ctx: JobContext) -> date:
    as_of = (ctx.job.inputs or {}).get("as_of")
    return date.fromisoformat(as_of) if as_of else date.today()


def _store(db, kind: str, period: str, payload: dict) -> int:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind,
                                                      OperatingReading.period_key == period))
        if row is None:
            row = OperatingReading(kind=kind, period_key=period)
            s.add(row)
        row.payload = _jsonable(payload)
        row.at = datetime.now(timezone.utc)
        s.flush()
        return row.id


def _previous(db, kind: str, before: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == kind, OperatingReading.period_key < before)
            .order_by(OperatingReading.period_key.desc()).limit(1))
        return dict(row.payload or {}) if row is not None else None


@handlers.register(INGEST)
def handle_orders_ingest(ctx: JobContext) -> dict:
    from ..commerce import orders_ingest

    got = orders_ingest.ingest(ctx.db)
    summary = {k: got.get(k) for k in ("ran", "reading", "receipts", "orders_created",
                                       "customers_created", "ledger_entries",
                                       "versions_recorded", "network_calls")}
    summary["gate_missing"] = got["gate"]["missing"]
    if got.get("orders_created"):
        ctx.enqueue("cfo", READINGS, {},
                    idempotency_key=f"{READINGS}:after-ingest:{ctx.job.id}")
        summary["queued_readings"] = True
    ctx.audit("commerce.orders_ingested", detail=_jsonable({**summary,
                                                            "why": got.get("why", ""),
                                                            "not_recorded":
                                                                got.get("not_recorded", [])}))
    return summary


@handlers.register(READINGS)
def handle_order_readings(ctx: JobContext) -> dict:
    from ..commerce import order_readings

    today = _today(ctx)
    reading = order_readings.read(ctx.db, today=today)
    stored = order_readings.record(ctx.db, _jsonable(reading))
    summary = {
        "reading_id": stored["id"], "orders": reading["orders"],
        "order_source_open": reading["order_source"]["open"],
        "cohorts": reading["cohorts"]["reading"],
        "offers": reading["offers"]["reading"],
        "winner": reading["winners"].get("top"),
        "study_opened": bool((reading["winners"].get("study") or {}).get("opened")),
        "reinvestment_owner_action": reading["reinvestment"]["owner_action"],
        "ladder_gaps": ((reading["ladder"].get("shape") or {}).get("empty_rungs") or []),
        "bundle_candidates": len(reading["bundles"]["candidates"]),
        "promotions": reading["promotions"]["reading"],
        "repeat": reading["repeat"]["reading"],
        "referral_measurable": reading["referral"]["outcome"].get("measurable"),
        "loops_with_evidence": reading["loops"]["with_evidence"],
    }
    ctx.audit("commerce.order_readings", detail=_jsonable(summary))
    return summary


@handlers.register(TRAJECTORY)
def handle_trajectory(ctx: JobContext) -> dict:
    from ..scale import trajectory

    today = _today(ctx)
    tonight = trajectory.nightly(ctx.db, on=today)
    rid = _store(ctx.db, TRAJECTORY_KIND, today.isoformat(), tonight)
    last = _previous(ctx.db, TRAJECTORY_KIND, today.isoformat())

    def _named(r):
        pc = (r or {}).get("primary_constraint") or {}
        return pc.get("constraint") if pc.get("identifiable") else "UNMEASURED"

    now_c, was_c = _named(tonight), (_named(last) if last else None)
    changed = last is not None and now_c != was_c
    if changed:
        # A different binding term is a different plan: the capacity review re-solves now
        # rather than at the end of the week.
        ctx.enqueue("orchestrator", "ops.capacity", {"as_of": today.isoformat()},
                    idempotency_key=f"ops.capacity:trajectory:{today.isoformat()}")
    summary = {"reading_id": rid, "kind": tonight.get("kind"),
               "observed_share": tonight.get("observed_share"),
               "observed_terms": tonight.get("observed_terms", []),
               "probability": tonight.get("probability"),
               "primary_constraint": now_c, "previous_constraint": was_c,
               "constraint_changed": changed, "hostage_to": tonight.get("hostage_to"),
               "measure_next": tonight.get("measure_next")}
    ctx.audit("scale.trajectory", detail=_jsonable(summary))
    return summary


@handlers.register(NORTH_STAR)
def handle_north_star(ctx: JobContext) -> dict:
    from sqlalchemy import select

    from ..core.models import Incident
    from ..creative import standard

    today = _today(ctx)
    ns = standard.north_star_from_db(ctx.db)
    rid = _store(ctx.db, NORTH_STAR_KIND, today.isoformat(), ns)
    regressing, improving = ns["regressing"], ns["improving"]
    defect = ns["answerable"] and len(regressing) >= 2 and len(regressing) > len(improving)
    incident = None
    with ctx.db.session() as s:
        open_row = s.scalar(select(Incident).where(Incident.signature == NORTH_STAR_SIGNATURE,
                                                   Incident.resolved.is_(False)))
        if defect:
            detail = {"regressing": regressing, "improving": improving,
                      "cohorts": ns["cohorts"][-2:]}
            if open_row is None:
                s.add(Incident(severity="P2", signature=NORTH_STAR_SIGNATURE,
                               summary=(f"Creative north star regressing between "
                                        f"{ns['cohorts'][0]} and {ns['cohorts'][-1]}: "
                                        f"{', '.join(regressing)}"),
                               halts_publication=False, detail=detail))
                incident = "opened"
            else:
                open_row.report_count += 1
                open_row.detail = detail
                incident = "updated"
        elif open_row is not None and ns["answerable"]:
            open_row.resolved = True
            incident = "resolved"
    summary = {"reading_id": rid, "cohorts": ns["cohorts"], "answerable": ns["answerable"],
               "improving": improving, "regressing": regressing, "incident": incident}
    ctx.audit("creative.north_star", detail=_jsonable(summary))
    return summary
