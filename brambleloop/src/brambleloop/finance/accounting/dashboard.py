"""Owner Money provider for the Command Center (F-914, F-915) and Finance work queue.

Contracts (lane C reads `summary` / `drill`; lane A's orchestrator reads `next_work`):

``summary(db, *, window="30d", now=None, refresh=True) -> dict``
    Always JSON-serialisable; never raises on an empty or broken DB. Keys:
    ``status`` OK|DEGRADED|BLOCKED|UNKNOWN, ``as_of`` (UTC ISO), ``basis``
    measured|estimated|modelled|unknown, ``items`` (one dict per metric: ``metric``,
    ``label``, ``value_cad`` (None = UNKNOWN, never 0.0 for unknown), ``reading``
    (measured|stale|lower_bound|estimated|derived|UNKNOWN), ``actual_cad``,
    ``estimated_cad`` (the signed part of the value contributed by non-measured inputs --
    modelled fees, FX-assumed revenue, unknown-basis costs; ``actual_cad`` is the rest), ``drill`` (the metric name to pass to `drill`), ``why``),
    ``sources`` (provenance strings), ``source_health``, ``window``, ``reason``,
    ``close``, ``exceptions``, ``forecast``. `window` is "30d" (default; the books' window),
    "mtd", "ytd", "all" or a month "YYYY-MM" (booking period). `refresh=True` first runs
    the idempotent posting rules so the journal reflects the sources.

``drill(db, metric, *, window="30d", now=None) -> dict``
    The rows behind one number: ``metric``, ``value_cad``, ``formula``, ``components``
    (per account: sign, total), ``rows`` (every journal line with its entry, kind
    original/reversal, ``reverses_id``, and the loaded **source row** -- order, cost entry,
    ledger row or statement line), ``corrections`` (reversal chains touching the metric) and
    ``check`` (sum of rows == value). Metrics: gross_sales, refunds, discounts, net_sales,
    fees, operating_spend, contribution, profit, tax_reserve, cash, expected_payout,
    owner_payable. Unknown metric -> status UNKNOWN with the list of valid metrics.

``next_work(db, *, now=None) -> list[dict]``
    Work items for the Finance department, highest priority first. Each: ``id`` (stable),
    ``department`` "finance", ``kind`` (post_rows | reconcile | investigate | close_month |
    connect_source | run_cycle), ``title``, ``priority`` (1 high .. 3 low), ``ready``
    (bool), ``blocked_by`` (owner action text or None), ``handler`` (the callable an
    orchestrator runs for a ready item, as "module:function"), ``evidence``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import accounts as A
from .ledger import period_of, to_cad
from .schema import ensure

METRICS = {
    "gross_sales": ([(A.SALES, 1)], "Gross sales"),
    "refunds": ([(A.REFUNDS, 1)], "Refunds"),
    "discounts": ([(A.DISCOUNTS, 1)], "Discounts"),
    "net_sales": ([(A.SALES, 1), (A.REFUNDS, -1), (A.DISCOUNTS, -1)], "Net sales"),
    "fees": ([(A.MARKETPLACE_FEES, 1)], "Marketplace fees"),
    "operating_spend": ([(c, 1) for c in A.OPERATING_ACCOUNTS], "Operating spend"),
    "contribution": ([(A.SALES, 1), (A.REFUNDS, -1), (A.DISCOUNTS, -1),
                      (A.MARKETPLACE_FEES, -1), (A.ADS, -1)], "Contribution"),
    "profit": ([(A.SALES, 1), (A.REFUNDS, -1), (A.DISCOUNTS, -1), (A.MARKETPLACE_FEES, -1)]
               + [(c, -1) for c in A.OPERATING_ACCOUNTS], "Profit before tax reserve"),
    "tax_reserve": ([(A.SALES, 1), (A.REFUNDS, -1), (A.DISCOUNTS, -1)],
                    "Sales-tax reserve (rate x net sales)"),
    "cash": ([(A.BANK, 1)], "Cash in bank"),
    "expected_payout": ([(A.ETSY_RECEIVABLE, 1)], "Etsy balance (expected payout)"),
    "owner_payable": ([(A.OWNER_PAYABLE, 1)], "Owed to owner (owner-funded spend)"),
}
SALES_METRICS = ("gross_sales", "refunds", "discounts", "net_sales", "fees", "contribution",
                 "profit", "tax_reserve")
BALANCE_METRICS = ("cash", "expected_payout", "owner_payable")


def _window(spec: str | None, now: datetime) -> dict:
    spec = (spec or "30d").strip().lower()
    if spec == "30d":
        return {"since": now - timedelta(days=30), "until": now, "label": "last 30 days"}
    if spec == "mtd":
        return {"period": period_of(now), "label": f"month to date {period_of(now)}"}
    if spec == "ytd":
        return {"since": datetime(now.year, 1, 1, tzinfo=timezone.utc), "until": now,
                "label": f"year to date {now.year}"}
    if spec == "all":
        return {"label": "all time"}
    if len(spec) == 7 and spec[4] == "-":
        return {"period": spec, "label": f"booking period {spec}"}
    raise ValueError(f"window {spec!r}: use 30d, mtd, ytd, all or YYYY-MM")


def _unknown(reason: str, now: datetime | None = None, **extra) -> dict:
    return {"status": "UNKNOWN", "as_of": (now or datetime.now(timezone.utc)).isoformat(),
            "basis": "unknown", "items": [], "sources": [], "reason": reason, **extra}


def summary(db, *, window: str = "30d", now: datetime | None = None,
            refresh: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    try:
        return _summary(db, window, now, refresh)
    except Exception as exc:  # noqa: BLE001 - the provider never raises
        return _unknown(f"Finance summary unavailable: {type(exc).__name__}: {exc}"[:300], now)


def _summary(db, window, now, refresh):
    from . import cash as cash_mod
    from . import close as close_mod
    from . import exceptions as X
    from . import forecast as fc
    from . import health as H
    from . import posting_rules, views

    db = ensure(db)
    w = _window(window, now)
    refresh_error = None
    if refresh:
        try:
            posting_rules.post_all(db, now=now)
        except Exception as exc:  # noqa: BLE001
            refresh_error = f"posting refresh failed: {type(exc).__name__}"
    hl = H.reading(db, now=now)
    kw = {k: w[k] for k in ("period", "since", "until") if k in w}
    acc = views.accrual(db, health=hl, **kw)
    pos = cash_mod.position(db, now=now, health=hl)
    exc = X.listing(db)
    sr = acc["sales_reading"]
    fees_est = sum(acc["estimated_components"]["fees"].values())
    op_est = sum(acc["estimated_components"]["operating"].values())
    m = acc["_micros"]

    def item(metric, label, value, reading, *, estimated=None, why="", drill=True):
        return {"metric": metric, "label": label, "value_cad": value, "reading": reading,
                "actual_cad": (None if value is None else
                               round(value - (estimated or 0.0), 4)),
                "estimated_cad": None if value is None else round(estimated or 0.0, 4),
                "drill": metric if drill else None, "why": why}

    sales_why = acc["sales_why"] if sr != "measured" else ""
    rev_est = sum(acc["estimated_components"]["revenue"].values())
    ref_est = sum(acc["estimated_components"]["refunds"].values())
    net_est = rev_est - ref_est
    fx_why = ("includes revenue converted at an ASSUMED FX rate (modelled): "
              + ", ".join(f"{k} CA${v:.2f}" for k, v in
                          acc["estimated_components"]["revenue"].items())) if rev_est else ""

    def sales_reading(est: float) -> str:
        # A sales figure is `measured` only when its source is and no part is modelled.
        return "estimated" if (sr == "measured" and abs(est) > 1e-9) else sr

    def why(*parts):
        return "; ".join(p for p in parts if p)

    items = [
        item("gross_sales", "Revenue (gross sales)", acc["accrual_gross_sales_cad"],
             sales_reading(rev_est), estimated=rev_est, why=why(sales_why, fx_why)),
        item("refunds", "Refunds", acc["accrual_refunds_cad"], sales_reading(ref_est),
             estimated=ref_est, why=why(sales_why, "refunds of FX-modelled sales are "
                                        "modelled" if ref_est else "")),
        item("net_sales", "Net sales", acc["accrual_net_sales_cad"],
             sales_reading(abs(rev_est) + abs(ref_est)), estimated=net_est,
             why=why(sales_why, fx_why)),
        item("fees", "Marketplace fees", acc["accrual_platform_fees_cad"],
             "UNKNOWN" if acc["accrual_platform_fees_cad"] is None else
             ("estimated" if fees_est else sr), estimated=fees_est,
             why="fees not read from Etsy's ledger are modelled" if fees_est else sales_why),
        item("operating_spend", "Operating spend", acc["accrual_operating_costs_cad"],
             "estimated" if op_est else "measured", estimated=op_est,
             why="includes modelled listing-fee exposure / unknown-basis rows" if op_est
             else ""),
        item("contribution", "Contribution", acc["accrual_contribution_cad"],
             "UNKNOWN" if acc["accrual_contribution_cad"] is None else
             ("estimated" if (fees_est or rev_est or ref_est) else sr),
             estimated=net_est - fees_est, why=why(sales_why, fx_why)),
        item("profit", "Profit before tax reserve",
             acc["accrual_profit_before_tax_reserve_cad"],
             "UNKNOWN" if acc["accrual_profit_before_tax_reserve_cad"] is None else
             ("estimated" if (fees_est or op_est or rev_est or ref_est) else sr),
             estimated=net_est - fees_est - op_est, why=why(sales_why, fx_why)),
        item("tax_reserve", "Sales-tax reserve", acc["accrual_tax_reserve_cad"],
             "UNKNOWN" if acc["accrual_tax_reserve_cad"] is None else "estimated",
             estimated=acc["accrual_tax_reserve_cad"] or 0.0, why=acc["tax_reserve_note"]),
        item("cash", "Cash in bank", pos["cash_on_hand_cad"], pos["cash_reading"],
             why=pos["cash_why"]),
        item("expected_payout", "Etsy balance (expected payout)", pos["expected_payout_cad"],
             "UNKNOWN" if pos["expected_payout_cad"] is None else "derived",
             why=pos["expected_payout_reading"]),
        item("committed_spend", "Committed spend (live reservations)",
             pos["committed_spend_cad"], "measured" if pos["committed_spend_cad"] is not None
             else "UNKNOWN", drill=False),
        item("owner_payable", "Owed to owner (owner-funded spend)",
             pos["obligations"]["owner_funded_spend_payable_cad"], "derived"),
        item("safe_discretionary_budget", "Safe discretionary budget",
             pos["safe_discretionary_budget_cad"],
             "UNKNOWN" if pos["safe_discretionary_budget_cad"] is None else "derived",
             why=pos["safe_discretionary_budget_why"], drill=False),
    ]
    integrity = _integrity(db)
    status = "OK"
    reasons = []
    if not integrity["ok"]:
        # R2-FIN (audit M12): a tampered journal or a moved locked period is surfaced on
        # read, not at the next anomaly cycle. Nothing on this page can be relied on.
        status = "BLOCKED"
        reasons.append("JOURNAL INTEGRITY FAILURE: " + "; ".join(integrity["problems"][:5]))
    elif sr == "UNKNOWN":
        status = "UNKNOWN"
        reasons.append("revenue is UNKNOWN: " + acc["sales_why"])
    elif (sr != "measured" or fees_est or op_est or rev_est or ref_est or exc
          or hl["warnings"] or refresh_error or pos["cash_reading"] not in
          ("measured", "UNKNOWN")):
        status = "DEGRADED"
    if sr in ("lower_bound", "stale"):
        reasons.append(f"sales are {sr}: {acc['sales_why']}")
    if fx_why:
        reasons.append(fx_why)
    if exc:
        reasons.append(f"{len(exc)} open accounting exception(s)")
    if pos["cash_reading"] != "measured" and hl["cash_known"]:
        reasons.append("cash: " + pos["cash_why"])
    reasons += hl["warnings"]
    if refresh_error:
        reasons.append(refresh_error)
    basis = ("unknown" if sr == "UNKNOWN" else
             "measured" if acc["all_measured"] else "estimated")
    try:
        close_status = close_mod.status(db, now=now)
    except Exception as e:  # noqa: BLE001
        close_status = {"error": type(e).__name__}
    try:
        forecast = fc.forecast(db, now=now)
    except Exception as e:  # noqa: BLE001
        forecast = {"error": type(e).__name__}
    return {
        "status": status, "as_of": now.isoformat(), "basis": basis, "items": items,
        "sources": ["ledger", "cost_entries", "spend_reservations", "orders",
                    "operating_readings:commerce.orders_held", "acct_journal_entries",
                    "acct_postings", "acct_statement_lines", "acct_exceptions"],
        "reason": "; ".join(reasons)[:1200],
        "window": w["label"], "currency": "CAD",
        "source_health": hl["sources"],
        "tax_reserve": pos["tax_reserve"],
        "payout_status": {"expected_payout_cad": pos["expected_payout_cad"],
                          "reading": pos["expected_payout_reading"]},
        "runway": {"value": pos["runway"], "why": pos["runway_why"]},
        "obligations": pos["obligations"], "upcoming_bills": pos["upcoming_bills"],
        "exceptions": {"open": len(exc), "high": sum(1 for x in exc if x["severity"] == "high"),
                       "top": [{k: x[k] for k in ("key", "kind", "severity", "summary")}
                               for x in exc[:5]]},
        "reconciliation_health": ("TAMPERED" if not integrity["ok"] else "clean" if not exc
                                  else f"{len(exc)} open exception(s)"),
        "integrity": integrity,
        "close": close_status,
        "forecast": forecast,
        "totals_micros": {k: m[k] for k in ("gross", "refunds", "fees", "operating",
                                            "net_profit")},
    }


def _integrity(db) -> dict:
    """Verify the journal seal chain and every locked period's trial-balance hash on read."""
    from . import close as close_mod
    from .ledger import verify_chain

    problems: list[str] = []
    try:
        ch = verify_chain(db)
        problems += [f"entry {p.get('entry_id')}: {p['problem']}" for p in ch["problems"]]
        legacy = ch.get("legacy_v1_entries", 0)
        for period in close_mod.status(db)["locked_periods"]:
            v = close_mod.verify_lock(db, period)
            if v.get("locked") and not v.get("intact"):
                problems.append(f"locked period {period}: figures moved after the lock")
    except Exception as exc:  # noqa: BLE001 - unverifiable is not verified
        problems.append(f"integrity check failed: {type(exc).__name__}")
        legacy = None
    return {"ok": not problems, "problems": problems[:20], "legacy_v1_entries": legacy}


def _load_source(s, table: str, sid: str) -> dict:
    from ...core.models import CostEntry, LedgerEntry, Order
    from .models import AcctStatementLine

    try:
        i = int(sid)
    except (TypeError, ValueError):
        return {}
    if table == "ledger":
        e = s.get(LedgerEntry, i)
        if e is None:
            return {"missing": True}
        out = {"table": "ledger", "id": e.id, "category": e.category, "at": e.at.isoformat(),
               "gross_cad": e.gross_cad, "refunds_cad": e.refunds_cad, "fees_cad": e.fees_cad,
               "expense_cad": e.expense_cad, "basis": e.basis, "fees_basis": e.fees_basis,
               "evidence_ref": e.evidence_ref, "source": e.source,
               "external_id": e.external_id, "currency": e.currency,
               "amount_original": e.amount_original,
               "reconciliation_state": e.reconciliation_state}
        from sqlalchemy import select

        o = s.scalar(select(Order).where(Order.external_ref == e.evidence_ref))
        if o is not None:
            out["order"] = {"external_ref": o.external_ref, "product_slug": o.product_slug,
                            "version": o.version, "state": (o.detail or {}).get("state"),
                            "price_cad": o.price_cad, "revenue_cad": o.revenue_cad,
                            "fees_cad": o.fees_cad, "fees_basis": o.fees_basis,
                            "acquisition_source": o.acquisition_source}
        return out
    if table == "cost_entries":
        c = s.get(CostEntry, i)
        if c is None:
            return {"missing": True}
        return {"table": "cost_entries", "id": c.id, "at": c.at.isoformat(), "kind": c.kind,
                "agent": c.agent, "provider": c.provider, "model": c.model,
                "purpose": c.purpose, "product_slug": c.product_slug,
                "amount_cad": c.amount_cad, "estimated_cad": c.estimated_cad,
                "detail": c.detail}
    if table == "acct_statement_lines":
        l = s.get(AcctStatementLine, i)
        if l is None:
            return {"missing": True}
        return {"table": "acct_statement_lines", "id": l.id, "source": l.source,
                "external_id": l.external_id, "kind": l.kind, "amount_cad": to_cad(l.amount_micros, 4),
                "state": l.state, "matched_to": l.matched_to}
    return {}


def drill(db, metric: str, *, window: str = "30d", now: datetime | None = None,
          refresh: bool = True) -> dict:
    """See the module docstring. Like `summary`, `refresh=True` first runs the idempotent
    posting rules; if source rows are still unposted afterwards (refresh off or failed), the
    figure is UNKNOWN with the reason -- a journal that is behind its sources never shows a
    measured-looking number (least of all CA$0.00)."""
    now = now or datetime.now(timezone.utc)
    if metric not in METRICS:
        return _unknown(f"unknown metric {metric!r}", now, valid_metrics=sorted(METRICS))
    try:
        from . import posting_rules

        dbx = ensure(db)
        refresh_error = None
        if refresh:
            try:
                posting_rules.post_all(dbx, now=now)
            except Exception as exc:  # noqa: BLE001
                refresh_error = f"posting refresh failed: {type(exc).__name__}"
        behind = posting_rules.unposted(dbx)
        if behind["count"]:
            return _unknown(
                f"the journal is behind its sources: {behind['count']} source row(s) not "
                f"yet posted" + (f" ({refresh_error})" if refresh_error else "")
                + "; the figure is STALE/UNKNOWN until the Finance cycle posts them",
                now, metric=metric, value_cad=None, reading="UNKNOWN",
                unposted=behind)
        return _drill(dbx, metric, window, now)
    except Exception as exc:  # noqa: BLE001
        return _unknown(f"drill unavailable: {type(exc).__name__}: {exc}"[:300], now)


def _drill(db, metric, window, now):
    from sqlalchemy import select

    from ..books import TAX_RESERVE_RATE
    from . import health as H
    from .models import AcctJournalEntry, AcctPosting

    db = ensure(db)
    spec, label = METRICS[metric]
    signs = dict(spec)
    w = _window(window, now) if metric not in BALANCE_METRICS else {"label": "balance, all time"}
    hl = H.reading(db, now=now)
    rows, components, corrections = [], {}, {}
    total = 0
    with db.session() as s:
        q = (select(AcctJournalEntry, AcctPosting)
             .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
             .where(AcctPosting.account.in_(list(signs)))
             .order_by(AcctJournalEntry.id, AcctPosting.line))
        if "period" in w:
            q = q.where(AcctJournalEntry.period == w["period"])
        if "since" in w:
            q = q.where(AcctJournalEntry.at >= w["since"])
        if "until" in w:
            q = q.where(AcctJournalEntry.at <= w["until"])
        cache: dict = {}
        for e, p in s.execute(q):
            acc = A.BY_CODE[p.account]
            natural = (p.debit_micros - p.credit_micros) * (1 if acc.normal_debit else -1)
            signed = natural * signs[p.account]
            total += signed
            c = components.setdefault(p.account, {"account": p.account, "name": acc.name,
                                                  "sign": signs[p.account], "total": 0,
                                                  "lines": 0})
            c["total"] += natural
            c["lines"] += 1
            key = (e.source_table, e.source_id)
            if key not in cache:
                cache[key] = _load_source(s, e.source_table, e.source_id)
            if e.kind == "reversal" or e.entry_key.endswith(":v1") is False:
                corrections.setdefault(e.source_key, set()).add(e.id)
            rows.append({"entry_id": e.id, "entry_key": e.entry_key, "kind": e.kind,
                         "reverses_id": e.reverses_id, "date": e.at.date().isoformat(),
                         "period": e.period, "account": p.account, "account_name": acc.name,
                         "contribution_cad": to_cad(signed, 6), "basis": p.basis,
                         "rule": e.rule, "memo": e.memo, "source_table": e.source_table,
                         "source_id": e.source_id, "source_ref": e.source_ref,
                         "product_slug": e.product_slug, "source_row": cache[key]})
        chains = []
        for sk, ids in corrections.items():
            chain = [{"entry_id": x.id, "entry_key": x.entry_key, "kind": x.kind,
                      "reverses_id": x.reverses_id, "memo": x.memo}
                     for x in s.scalars(select(AcctJournalEntry).where(
                         AcctJournalEntry.source_key == sk).order_by(AcctJournalEntry.id))]
            chains.append({"source_key": sk, "history": chain})
    value_micros = total
    formula = " ".join(("+ " if sg > 0 else "- ") + A.BY_CODE[a].name for a, sg in spec)
    if metric == "tax_reserve":
        value_micros = int(round(max(0, total) * TAX_RESERVE_RATE))
        formula = f"{TAX_RESERVE_RATE} x max(0, {formula})"
    sales_dep = metric in SALES_METRICS
    places = 4 if metric in ("operating_spend", "owner_payable") else 2  # as `summary` shows
    # R2-FIN (audit M3, L3): the drill's reading and the independent figure it is checked
    # against come from the same providers `summary` uses (views.accrual / cash.position),
    # not from the rows themselves -- so an UNKNOWN in the summary is UNKNOWN here, and
    # `check.matches` compares two independently computed numbers.
    independent, ind_reading, ind_why = _independent(db, metric, window, now, hl)
    if sales_dep:
        reading = H.figure_reading(hl["sources"]["orders"]["state"], bool(rows))
    else:
        reading = ind_reading
    value = None if (reading == "UNKNOWN" or (not sales_dep and independent is None)) \
        else to_cad(value_micros, places)
    if value is None:
        reading = "UNKNOWN"
    return {
        "status": "UNKNOWN" if value is None else "OK",
        "as_of": now.isoformat(), "basis": "unknown" if value is None else
        ("measured" if all(r["basis"] == "measured" for r in rows) else "estimated"),
        "metric": metric, "label": label, "window": w["label"], "value_cad": value,
        "reading": reading, "formula": formula,
        "components": [{**c, "total_cad": to_cad(c["total"], 6)} for c in components.values()],
        "rows": rows, "items": rows,
        "corrections": chains,
        "check": {"sum_of_rows_cad": to_cad(total, 6),
                  "value_from_rows_cad": to_cad(value_micros, 6),
                  "rounded_to_places": places,
                  "independent_value_cad": independent,
                  "matches": ((value is None and independent is None) or
                              (value is not None and independent is not None
                               and abs(value - independent) < 1e-9))},
        "sources": sorted({f"{r['source_table']}:{r['source_id']}" for r in rows}),
        "why": (hl["sources"]["orders"]["why"] if sales_dep and reading != "measured" else
                ind_why if metric == "cash" else ""),
    }


_ACCRUAL_KEY = {"gross_sales": ("accrual_gross_sales_cad", 2),
                "refunds": ("accrual_refunds_cad", 2),
                "discounts": ("accrual_discounts_cad", 2),
                "net_sales": ("accrual_net_sales_cad", 2),
                "fees": ("accrual_platform_fees_cad", 2),
                "operating_spend": ("accrual_operating_costs_cad", 4),
                "contribution": ("accrual_contribution_cad", 2),
                "profit": ("accrual_profit_before_tax_reserve_cad", 2),
                "tax_reserve": ("accrual_tax_reserve_cad", 2)}


def _independent(db, metric, window, now, hl) -> tuple[float | None, str, str]:
    """The metric as `summary` computes it, and the reading it carries there."""
    from . import cash as cash_mod
    from . import views

    if metric in BALANCE_METRICS:
        pos = cash_mod.position(db, now=now, health=hl)
        if metric == "cash":
            return pos["cash_on_hand_cad"], pos["cash_reading"], pos["cash_why"]
        if metric == "expected_payout":
            v = pos["expected_payout_cad"]
            return v, "UNKNOWN" if v is None else "derived", pos["expected_payout_reading"]
        return pos["obligations"]["owner_funded_spend_payable_cad"], "derived", ""
    w = _window(window, now)
    kw = {k: w[k] for k in ("period", "since", "until") if k in w}
    acc = views.accrual(db, health=hl, **kw)
    key, _ = _ACCRUAL_KEY[metric]
    return (acc[key], acc["sales_reading"] if metric != "operating_spend" else "derived",
            acc["sales_why"])


def next_work(db, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    try:
        return _next_work(db, now)
    except Exception as exc:  # noqa: BLE001
        return [{"id": "finance:provider_error", "department": "finance", "kind": "investigate",
                 "title": f"Finance work queue unavailable: {type(exc).__name__}",
                 "priority": 1, "ready": False, "blocked_by": None, "handler": None,
                 "evidence": {"error": str(exc)[:300]}}]


def _next_work(db, now):
    from . import close as close_mod
    from . import exceptions as X
    from . import health as H
    from . import posting_rules
    from .controller import last_run
    from .models import AcctStatementLine
    from sqlalchemy import func, select

    db = ensure(db)
    out: list[dict] = []
    lr = last_run(db)
    if lr is None or now - lr > timedelta(hours=24):
        out.append({"id": "finance:run_cycle", "department": "finance", "kind": "run_cycle",
                    "title": "Run the Accountant cycle (post, reconcile, anomalies, close check)",
                    "priority": 2, "ready": True, "blocked_by": None,
                    "handler": "brambleloop.finance.accounting.controller:run_cycle",
                    "evidence": {"last_run": lr.isoformat() if lr else None}})
    up = posting_rules.unposted(db)
    if up["count"]:
        out.append({"id": "finance:post_rows", "department": "finance", "kind": "post_rows",
                    "title": f"Post {up['count']} new or changed source row(s) to the ledger",
                    "priority": 1, "ready": True, "blocked_by": None,
                    "handler": "brambleloop.finance.accounting.posting_rules:post_all",
                    "evidence": up})
    with db.session() as s:
        unmatched = s.scalar(select(func.count(AcctStatementLine.id)).where(
            AcctStatementLine.state == "unmatched")) or 0
    if unmatched:
        out.append({"id": "finance:reconcile", "department": "finance", "kind": "reconcile",
                    "title": f"Reconcile {unmatched} unmatched statement line(s)",
                    "priority": 1, "ready": True, "blocked_by": None,
                    "handler": "brambleloop.finance.accounting.reconciliation:match",
                    "evidence": {"unmatched": unmatched}})
    for x in X.listing(db)[:10]:
        out.append({"id": f"finance:investigate:{x['key']}", "department": "finance",
                    "kind": "investigate", "title": f"Investigate {x['kind']}: {x['summary']}"[:200],
                    "priority": 1 if x["severity"] == "high" else 2, "ready": True,
                    "blocked_by": None,
                    "handler": "brambleloop.finance.accounting.exceptions:resolve",
                    "evidence": {"key": x["key"], "evidence": x["evidence"]}})
    st = close_mod.status(db, now=now)
    if not st["previous_period_locked"]:
        cl = close_mod.checklist(db, st["previous_period"], now=now, refresh=False)
        blockers = [x["step"] for x in cl["steps"] if x["outcome"] == "block"]
        out.append({"id": f"finance:close_month:{st['previous_period']}",
                    "department": "finance", "kind": "close_month",
                    "title": f"Close {st['previous_period']}", "priority": 2,
                    "ready": cl["closable"],
                    "blocked_by": None if cl["closable"] else ", ".join(blockers),
                    "handler": "brambleloop.finance.accounting.close:lock_period",
                    "evidence": {"owner_summary": cl["owner_summary"]}})
    for name, src in H.reading(db, now=now)["sources"].items():
        if src["state"] == H.DISCONNECTED:
            out.append({"id": f"finance:connect_source:{name}", "department": "finance",
                        "kind": "connect_source", "title": f"{name} source is disconnected",
                        "priority": 3, "ready": False,
                        "blocked_by": src.get("owner_action") or "owner action required",
                        "handler": None, "evidence": {"why": src["why"]}})
    out.sort(key=lambda w: (w["priority"], not w["ready"], w["id"]))
    return out
