"""The dashboard's headline, computed so that output volume cannot read as business readiness.

F-186, F-187, F-206 (Final Master): the top of the dashboard led with queue depth, dead letters,
certified releases, listing images and content pieces -- volume. A shop with nineteen certified
patterns, hundreds of images and no product a buyer could be sold today read as a busy,
nearly-ready business. The headline now leads with the numbers that decide whether anything
can be sold: launch-cleared inventory against certified inventory, creative-gate survivors,
benchmark status and real commercial evidence. Volume counts move below them.

F-665: every headline KPI carries an evidence envelope -- where it came from, when it was read,
how it was transformed, what confidence it carries and whether it has been reconciled -- so a
number on the page can be argued with rather than trusted.

Unknown stays UNKNOWN. The gauge standard is read from the stored certificate's stamp (the
certificate cluster owns the check; this reads its result), and a product is never counted as
launch-cleared on a criterion nobody checked -- a certificate with no stamp does not pass.
"""
from __future__ import annotations

from datetime import datetime, timezone

# The four criteria of launch clearance (F-186). A product is launch-cleared only when every
# one is established; a criterion that cannot be assessed here blocks clearance rather than
# being assumed.
LAUNCH_CRITERIA: tuple[str, ...] = (
    "certified", "usable_listing_asset", "creative_gate_survivor", "gauge_standard")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def evidence(source: str, *, transform: str, confidence: str = "measured",
             reconciliation: str = "not reconciled", as_of: str | None = None,
             external_ids: list | None = None) -> dict:
    """The F-665 envelope: source, as-of, transformation, confidence, reconciliation."""
    return {"source": source, "as_of": as_of or _now(), "transform": transform,
            "confidence": confidence, "reconciliation": reconciliation,
            "external_ids": list(external_ids or [])}


def creative_survivors(db=None) -> dict:
    """Creative-gate survivors, labelled by the cohort measured (F-188).

    `audit_catalogue` measures the legacy builder catalogue; the concept tournament is a
    separate cohort read from its own runs, so legacy failures are never attributed to it.
    """
    from ..creative.audit import audit_catalogue, tournament_cohort

    report = audit_catalogue()
    survivors = [str(s) for s in report["survivors"]]
    cohort = report["cohort"]
    return {"survivors": survivors, "count": len(survivors),
            "audited": report["products_audited"],
            "cohort": cohort,
            "tournament_cohort": tournament_cohort(db),
            "dominant_failure": report["autopsy"].get("dominant_cause"),
            "evidence": evidence(
                f"creative.audit.audit_catalogue (cohort {cohort['name']}, "
                f"{cohort['generator_version']})",
                transform="count of legacy builder-catalogue concepts whose jury verdict "
                          "survives the current creative gate",
                confidence="measured (deterministic jury)")}


def launch_inventory(db, survivors: list[str] | None = None) -> dict:
    """Certified vs launch-cleared, per product, with the criterion each one fails."""
    from sqlalchemy import select

    from ..core.models import ListingAsset, PatternVersion, Product
    from ..gates.certificate import GAUGE_STANDARD

    if survivors is None:
        survivors = creative_survivors()["survivors"]
    alive = set(survivors)
    with db.session() as s:
        certified: dict[str, set[str]] = {}
        # F-186: the gauge standard is read from the stored certificate, the same stamp
        # `publish.eligibility.legacy_status` checks. A certified version whose certificate
        # carries the current `GAUGE_STANDARD` was examined by `gauge_findings`; one with no
        # stamp predates the check and does not pass. Hard-coding None made the
        # launch-cleared count 0 by construction.
        stamps: dict[str, set[str]] = {}
        for slug, version, cert in s.execute(
                select(Product.slug, PatternVersion.version, PatternVersion.certificate)
                .join(PatternVersion, PatternVersion.product_id == Product.id)
                .where(PatternVersion.certified.is_(True))):
            certified.setdefault(slug, set()).add(version)
            stamp = (cert or {}).get("gauge_standard") if isinstance(cert, dict) else None
            stamps.setdefault(slug, set()).add(str(stamp) if stamp else "")
        usable: set[tuple[str, str]] = set()
        for a in s.scalars(select(ListingAsset).where(ListingAsset.approved.is_(True))):
            if a.sha256 and not (a.blocked_reasons or []):
                usable.add((a.product_slug, a.version))
    rows = []
    for slug in sorted(certified):
        crit = {
            "certified": True,
            "usable_listing_asset": any((slug, v) in usable for v in certified[slug]),
            "creative_gate_survivor": slug in alive,
            "gauge_standard": GAUGE_STANDARD in stamps.get(slug, set()),
        }
        failing = [k for k in LAUNCH_CRITERIA if crit[k] is not True]
        found = sorted(x for x in stamps.get(slug, set()) if x)
        rows.append({"slug": slug, "criteria": crit, "launch_cleared": not failing,
                     "failing": failing,
                     "gauge_standard_why": (
                         f"certified under the current gauge standard ({GAUGE_STANDARD})"
                         if crit["gauge_standard"] else
                         f"no certified version carries the current gauge standard "
                         f"({GAUGE_STANDARD}); stored: {found or 'none -- predates the check'}")})
    cleared = [r["slug"] for r in rows if r["launch_cleared"]]
    return {
        "certified": len(rows),
        "launch_cleared": len(cleared),
        "cleared_slugs": cleared,
        "products": rows,
        "criteria": list(LAUNCH_CRITERIA),
        "unassessed_criteria": [],
        "gauge_standard": GAUGE_STANDARD,
        "evidence": evidence(
            "pattern_versions (certified) x listing_assets (approved, hashed, unblocked) x "
            "creative.audit survivors",
            transform="a product is launch-cleared only when every criterion is established; "
                      "gauge_standard is the stored certificate's stamp, and a certificate "
                      "with no stamp predates the check and blocks clearance",
            confidence="measured"),
    }


UNMEASURED = "UNMEASURED"


def _order_source(db) -> dict:
    """`commerce.orders_ingest.source_state`, or UNKNOWN when it cannot be read."""
    try:
        from ..commerce import orders_ingest

        return dict(orders_ingest.source_state(db))
    except Exception as exc:  # noqa: BLE001 - an unreadable source is not a measured one
        return {"open": False, "measured": False, "missing": [], "last_read_at": None,
                "why": f"order source state unreadable ({type(exc).__name__})"}


def _sale_rows(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import LedgerEntry

    with db.session() as s:
        return [{"gross": float(g or 0), "refunds": float(r or 0), "ref": (ref or "").strip(),
                 "basis": b or "unknown", "recon": rs or "unreconciled"}
                for g, r, ref, b, rs in s.execute(select(
                    LedgerEntry.gross_cad, LedgerEntry.refunds_cad, LedgerEntry.evidence_ref,
                    LedgerEntry.basis, LedgerEntry.reconciliation_state)
                    .where(LedgerEntry.gross_cad > 0))]


def _reconciled_measured(row: dict) -> bool:
    """A3-09: a sale counts as evidenced only when measured AND reconciled to Etsy's ledger."""
    from ..finance.reconcile import RECONCILED

    return bool(row["ref"]) and row["basis"] == "measured" and row["recon"] == RECONCILED


def revenue_reading(db) -> dict:
    """Revenue as the headline may state it (A3-09).

    UNMEASURED while the order source is not connected-and-read: a CA$0.00 there would be a
    zero nobody observed. When measured, only measured+reconciled sale rows are summed (net of
    refunds); anything else is reported as a count beside it, never inside it.
    """
    source = _order_source(db)
    rows = _sale_rows(db)
    good = [r for r in rows if _reconciled_measured(r)]
    raw = round(sum(r["gross"] for r in rows), 2)
    out = {"raw_ledger_gross_cad": raw, "unreconciled_rows": len(rows) - len(good),
           "order_source_measured": bool(source.get("measured")),
           "why": source.get("why") or ""}
    if not source.get("measured"):
        return {**out, "state": UNMEASURED, "value_cad": None, "display": UNMEASURED,
                "evidence": evidence("commerce.orders_ingest.source_state; ledger",
                                     transform="not summed: the order source is not measured",
                                     confidence="unmeasured",
                                     reconciliation="order source gated (transactions_r)")}
    value = round(sum(r["gross"] - r["refunds"] for r in good), 2)
    return {**out, "state": "MEASURED", "value_cad": value, "display": f"CA${value:.2f}",
            "evidence": evidence("ledger (basis=measured, reconciliation=matched_etsy_ledger)",
                                 transform="sum of gross less refunds over reconciled sales",
                                 confidence="measured",
                                 reconciliation="matched against the Etsy payment ledger")}


def spend_reading(db) -> dict:
    """Every recorded spend kind, labelled -- not model spend presented as total opex (A3-09)."""
    from sqlalchemy import func, select

    from ..core.models import CostEntry, LedgerEntry

    with db.session() as s:
        by_kind = {k or "other": round(float(v or 0), 4) for k, v in s.execute(
            select(CostEntry.kind, func.sum(CostEntry.amount_cad)).group_by(CostEntry.kind))}
        fees = float(s.scalar(select(func.sum(LedgerEntry.fees_cad))) or 0)
        expense = float(s.scalar(select(func.sum(LedgerEntry.expense_cad))) or 0)
    cost_total = round(sum(by_kind.values()), 4)
    total = round(cost_total + fees + expense, 2)
    return {"total_recorded_cad": total, "cost_entries_by_kind": by_kind,
            "cost_entries_cad": cost_total, "model_cad": round(by_kind.get("llm", 0.0), 4),
            "ledger_fees_cad": round(fees, 2), "ledger_expense_cad": round(expense, 2),
            "label": "Recorded spend (all kinds)",
            "display": f"CA${total:.2f}",
            "evidence": evidence("cost_entries (every kind) + ledger fees_cad + expense_cad",
                                 transform="sum; recorded spend only, not an all-in opex",
                                 confidence="recorded (not reconciled)")}


def commercial_evidence(db) -> dict:
    """Money that arrived with the order it came from. Counted, never inferred.

    A3-09: an "evidenced sale" is a ledger row with an evidence ref whose amount is measured
    and reconciled against Etsy's ledger. A row that merely names a reference is counted as
    recorded-unreconciled. While the order source is not measured the state is UNMEASURED.
    """
    from sqlalchemy import func, select

    from ..core.models import Order

    source = _order_source(db)
    rows = _sale_rows(db)
    evidenced = [r for r in rows if _reconciled_measured(r)]
    recorded = [r for r in rows if r["ref"] and not _reconciled_measured(r)]
    with db.session() as s:
        orders = s.scalar(select(func.count()).select_from(Order)) or 0
    if evidenced:
        state = "OBSERVED"
    elif not source.get("measured"):
        state = UNMEASURED
    else:
        state = "NONE_OBSERVED"
    return {"evidenced_sales": len(evidenced),
            "evidenced_gross_cad": round(sum(r["gross"] for r in evidenced), 2),
            "recorded_unreconciled_sales": len(recorded),
            "orders": int(orders),
            "order_source_measured": bool(source.get("measured")),
            "state": state,
            "evidence": evidence(
                "ledger (gross_cad > 0, evidence_ref, basis=measured, "
                "reconciliation=matched_etsy_ledger) and orders tables",
                transform="count and sum of reconciled, measured revenue rows",
                confidence="measured" if source.get("measured") else "unmeasured",
                reconciliation=("matched against the Etsy payment ledger"
                                if source.get("measured") else
                                "not reconciled: order source gated on transactions_r"))}


def benchmark_status(db) -> dict:
    from sqlalchemy import func, select

    from ..build2 import executor
    from ..core.models import Benchmark, BenchmarkObservation, BenchmarkProduct

    with db.session() as s:
        shops = s.scalar(select(func.count()).select_from(Benchmark)) or 0
        observations = s.scalar(select(func.count()).select_from(BenchmarkObservation)) or 0
        purchased = s.scalar(select(func.count()).select_from(BenchmarkProduct)) or 0
    try:
        readable = executor.GATE_BY_KEY["benchmark_observation"].open(db)
    except Exception:  # noqa: BLE001 -- an unreadable gate is not an open one
        readable = False
    state = ("OBSERVED" if observations else
             "READABLE_NOT_OBSERVED" if readable else "UNKNOWN")
    return {"state": state, "benchmark_shops": int(shops),
            "observations": int(observations), "purchased_patterns": int(purchased),
            "observation_gate_open": bool(readable),
            "evidence": evidence("benchmarks, benchmark_observations, benchmark_products; "
                                 "executor gate benchmark_observation",
                                 transform="row counts; gate from the recorded etsy.probe",
                                 confidence="measured")}


def dead_letter_split(status: dict) -> dict:
    """F-185: N expected / M defects, never the unsplit total as a headline."""
    return {"expected": int(status["dead_letter_refusals"]),
            "defects": int(status["dead_letter_defects"]),
            "total": int(status["dead_letters"]),
            "text": (f"{status['dead_letter_refusals']} expected / "
                     f"{status['dead_letter_defects']} defects"),
            "evidence": evidence("jobs (status DEAD)",
                                 transform=status.get("dead_letter_classified_by",
                                                      "queue.durable.deliberate_refusal"),
                                 confidence="measured")}


def _tournament_kpi(t: dict) -> dict:
    """F-188: the concept-tournament cohort as its own row, never merged with the legacy one."""
    measured = t.get("state") == "MEASURED"
    return {"key": "tournament_cohort", "label": "Tournament-cohort survivors",
            "value": (f"{t['survivors']} / {t['candidates']}" if measured
                      else str(t.get("state") or "UNKNOWN")),
            "alarm": not measured or not t.get("survivors"),
            "evidence": evidence("audit_log (creative.tournament, creative.expedition)",
                                 transform="final-stage survivors over generated candidates, "
                                           "summed over the runs on file",
                                 confidence="measured" if measured else "unmeasured"),
            "why": f"cohort {t['name']} ({t['generator']}): {t.get('why', '')}"}


def headline(db, status: dict, inbox: dict | None = None) -> dict:
    """The commercial-truth headline (F-206) plus the demoted volume counts."""
    survivors = creative_survivors(db)
    inventory = launch_inventory(db, survivors["survivors"])
    commerce = commercial_evidence(db)
    bench = benchmark_status(db)
    dead = dead_letter_split(status)
    revenue = revenue_reading(db)
    spend = spend_reading(db)
    inbox_known = inbox is not None and isinstance(inbox.get("cards"), list)
    kpis = [
        {"key": "launch_cleared", "label": "Launch-cleared / certified",
         "value": f"{inventory['launch_cleared']} / {inventory['certified']}",
         "alarm": inventory["launch_cleared"] == 0, "evidence": inventory["evidence"],
         "why": (f"{inventory['launch_cleared']} of {inventory['certified']} certified "
                 f"products meet every launch criterion; unassessed: "
                 f"{', '.join(inventory['unassessed_criteria']) or 'none'}")},
        {"key": "creative_survivors", "label": "Creative-gate survivors",
         "value": f"{survivors['count']} / {survivors['audited']}",
         "alarm": survivors["count"] == 0, "evidence": survivors["evidence"],
         "why": ("no product survives the current creative gate: this is the principal "
                 f"commercial blocker (dominant failure: {survivors['dominant_failure']})"
                 if survivors["count"] == 0 else
                 f"{survivors['count']} concepts survive the current creative gate")
                + f" [cohort: {survivors['cohort']['name']}, "
                  f"{survivors['cohort']['generator_version']}]"},
        _tournament_kpi(survivors["tournament_cohort"]),
        {"key": "benchmark", "label": "Benchmark status",
         "value": bench["state"], "alarm": bench["state"] != "OBSERVED",
         "evidence": bench["evidence"],
         "why": (f"{bench['observations']} observations across {bench['benchmark_shops']} "
                 f"benchmark shops; {bench['purchased_patterns']} purchased patterns")},
        {"key": "commercial_evidence", "label": "Commercial evidence",
         "value": (f"{commerce['evidenced_sales']} sales / CA${commerce['evidenced_gross_cad']:.2f}"
                   if commerce["state"] == "OBSERVED" else
                   UNMEASURED if commerce["state"] == UNMEASURED else "none observed"),
         "alarm": commerce["state"] != "OBSERVED", "evidence": commerce["evidence"],
         "why": (f"{commerce['orders']} orders on file; revenue counted only when measured "
                 f"and reconciled ({commerce['recorded_unreconciled_sales']} recorded rows "
                 f"not reconciled)")},
        {"key": "revenue", "label": "Revenue (reconciled)", "value": revenue["display"],
         "alarm": revenue["state"] != "MEASURED", "evidence": revenue["evidence"],
         "why": (revenue["why"] or "measured, reconciled sales net of refunds")
                + f"; raw ledger gross CA${revenue['raw_ledger_gross_cad']:.2f} not shown as revenue"},
        {"key": "spend", "label": spend["label"], "value": spend["display"],
         "alarm": False, "evidence": spend["evidence"],
         "why": (f"model CA${spend['model_cad']:.2f}; cost entries by kind "
                 f"{spend['cost_entries_by_kind']}; ledger fees CA${spend['ledger_fees_cad']:.2f}"
                 f", ledger expense CA${spend['ledger_expense_cad']:.2f}")},
        {"key": "owner_inbox", "label": "Waiting on the owner",
         "value": str(len(inbox["cards"])) if inbox_known else "UNKNOWN",
         # A3-09: an inbox nobody could read is an alarm, not a quiet "nothing waiting".
         "alarm": not inbox_known,
         "evidence": evidence("build2.executor.approval_inbox (one queue)",
                              transform="closed owner gates that unblock work, merged with "
                                        "OwnerAction rows by requirement_key",
                              confidence="measured (gates re-evaluated on request)"),
         "why": "external capability gaps are listed separately and are not owner requests"},
        {"key": "dead_letters", "label": "Dead letters", "value": dead["text"],
         "alarm": dead["defects"] > 0, "evidence": dead["evidence"],
         "why": "expected refusals (shadow mode, stand-asides) are not defects"},
    ]
    return {"kpis": kpis, "inventory": inventory, "creative": survivors,
            "commercial": commerce, "benchmark": bench, "dead_letters": dead,
            "revenue": revenue, "spend": spend,
            "as_of": _now()}
